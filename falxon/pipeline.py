"""End-to-end claim verification: structured check → retrieval → rerank → NLI → verdict."""
from __future__ import annotations

import re
import time
from dataclasses import asdict
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from . import models, structured
from .aggregate import NEI, decide
from .claims import _STOP, content_terms, extract_claims, validate_claim
from .config import settings
from .http import fetch_public_page
from .retrieval import wikipedia

ENGINE_VERSION = "falxon-5.4"
PREFILTER_KEEP = 160


def verify(claim: str, use_structured: bool = True) -> dict:
    """Check one claim. Never raises for network/model trouble: it reports it."""
    claim = validate_claim(claim)
    started = time.perf_counter()
    timings: dict[str, float] = {}
    report = {
        "claim": claim,
        "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engine": ENGINE_VERSION,
        "models": {"nli": settings.nli_model, "reranker": None},
        "structured": None,
        "evidence": [],
        "sources": [],
        "warnings": [],
    }

    if use_structured:
        t = time.perf_counter()
        result = structured.check(claim)
        timings["structured"] = round(time.perf_counter() - t, 3)
        if result:
            report["structured"] = result
            if "could not be reached" in result["note"]:
                report["warnings"].append(result["note"].replace("structured source", "Wikidata record check"))
            if result["label"] != NEI:
                return _finish(report, {
                    "label": result["label"], "confidence": result["confidence"],
                    "distribution": None, "decisive": [], "reason": result["note"], "method": "structured",
                }, started, timings)

    t = time.perf_counter()
    try:
        pages, passages = wikipedia.retrieve(claim)
    except Exception as exc:
        pages, passages = [], []
        report["warnings"].append(f"Wikipedia could not be reached ({type(exc).__name__}).")
    timings["retrieval"] = round(time.perf_counter() - t, 3)
    report["sources"] = [{"title": p.title, "url": p.url, "revision_url": p.revision_url,
                          "updated_at": p.updated_at, "publisher": "Wikipedia"} for p in pages]

    if not passages:
        return _finish(report, {"label": NEI, "confidence": 0.0, "distribution": None, "decisive": [],
                                "reason": "No relevant Wikipedia articles were found.", "method": "retrieval"},
                       started, timings)

    t = time.perf_counter()
    # Cheap lexical pre-filter keeps the neural reranker fast on CPU. Lead sentences
    # are always kept because they define the article's subject.
    if len(passages) > PREFILTER_KEEP:
        overlap = models.lexical_scores(claim, [p.premise for p in passages])
        order = sorted(range(len(passages)), key=lambda i: (-(overlap[i] + (0.5 if passages[i].position < 2 else 0))))
        passages = [passages[i] for i in sorted(order[:PREFILTER_KEEP])]
    relevance, method = models.rerank(claim, [p.premise for p in passages])
    report["models"]["reranker"] = method
    ranked = sorted(zip(passages, relevance), key=lambda x: -x[1])
    # Keep the best passages, at most 3 from any one article, and drop near-duplicate windows.
    chosen, per_page, seen_pos = [], {}, set()
    for passage, score in ranked:
        key = (passage.title, passage.position)
        if per_page.get(passage.title, 0) >= 3 or key in seen_pos:
            continue
        chosen.append((passage, score))
        per_page[passage.title] = per_page.get(passage.title, 0) + 1
        seen_pos.add(key)
        if len(chosen) >= settings.rerank_keep:
            break
    timings["rerank"] = round(time.perf_counter() - t, 3)

    t = time.perf_counter()
    top = chosen[: settings.nli_keep]
    try:
        scores = models.nli(claim, [p.premise for p, _ in top])
    except Exception as exc:
        report["warnings"].append(f"The verification model could not run ({exc}).")
        return _finish(report, {"label": NEI, "confidence": 0.0, "distribution": None, "decisive": [],
                                "reason": "The verification model is unavailable.", "method": "error"},
                       started, timings)
    timings["nli"] = round(time.perf_counter() - t, 3)

    evidence = []
    for i, ((passage, rel), nli_scores) in enumerate(zip(top, scores)):
        item = asdict(passage)
        item.pop("scores", None)
        item.update({"id": i, "relevance": round(rel, 4), "nli": nli_scores})
        evidence.append(item)
    if method == "lexical-overlap":
        # Overlap scores are 0..1, not logits; map onto the logit scale used by thresholds.
        for item in evidence:
            item["relevance"] = round((item["relevance"] - 0.5) * 8, 4)
        report["warnings"].append("The reranking model was unavailable; used word overlap instead.")

    for item in evidence:
        item["covers"] = detail_coverage(claim, item.get("text", ""))
        item["count"] = count_check(claim, item.get("text", ""))
    verdict = decide(evidence, settings.thresholds)
    verdict["method"] = "retrieval+nli"
    for item in evidence:
        item["decisive"] = item["id"] in verdict["decisive"]
        item["stance"] = max(("entailment", "contradiction", "neutral"), key=lambda k: item["nli"][k])
    report["evidence"] = evidence
    return _finish(report, verdict, started, timings)


_NUMBER_WORDS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
_COUNT = re.compile(r"\b(\d{1,3}|" + "|".join(w for w in _NUMBER_WORDS if w != "one") +
                    r")(?:[ -](?!(?:and|or|of|in|the|to|for|by)\b)[a-z]+)?[ -]([a-z]{3,})\b", re.I)


_HAS = {"he", "she", "it", "they", "its", "his", "her", "their", "has", "have", "had", "contains", "contain", "with", "is", "are", "was", "were", "of", "into", "consists"}


def _counts(text: str, scope: set[str] | None = None) -> dict[str, set[int]]:
    """Small counted nouns: "four chambers" -> {"chamber": {4}}. Years and big numbers are ignored.

    With `scope` (the claim's own words), a count whose subject adds a qualifier the claim lacks
    ("The *left* heart has two chambers") is about something narrower and is skipped.
    """
    out: dict[str, set[int]] = {}
    for m in _COUNT.finditer(text or ""):
        if scope is not None:
            before = re.findall(r"[a-z]+", text[max(0, m.start() - 40):m.start()].lower())[-4:]
            if any(w not in scope and w not in _HAS and w not in _STOP and len(w) > 2 for w in before):
                continue
        raw, noun = m.group(1).lower(), m.group(2).lower()
        n = int(raw) if raw.isdigit() else _NUMBER_WORDS[raw]
        noun = re.sub(r"(?:es|s)$", "", noun) if len(noun) > 4 else noun
        if noun in _STOP or noun in _NUMBER_WORDS:
            continue
        out.setdefault(noun, set()).add(n)
    return out


def count_check(claim: str, passage: str) -> str | None:
    """"conflict" when the passage counts the claim's noun differently ("two chambers" vs "four chambers")."""
    mine = _counts(claim)
    if not mine:
        return None
    theirs = _counts(passage, scope=set(content_terms(claim)))
    result = "absent"  # the claim counts something this passage doesn't count
    for noun, nums in mine.items():
        if noun not in theirs:
            continue
        if nums & theirs[noun]:
            return "match"
        result = "conflict"
    return result


DETAILED_CLAIM_TERMS = 5


def detail_coverage(claim: str, passage: str) -> float:
    """Share of the claim's specific terms (beyond its subject) that the passage mentions.

    Long, detail-heavy claims ("... because one politician won a coin toss") are often unverifiable.
    A passage that merely tells a different story about the subject shouldn't count as refuting them,
    so the decision rule asks such passages to address most of the claim's details. Short claims get 1.0.
    """
    subject = set(content_terms(wikipedia.subject_phrase(claim) or ""))
    terms = [w for w in content_terms(claim) if w not in subject]
    if len(terms) < DETAILED_CLAIM_TERMS:
        return 1.0
    words = set(content_terms(passage))
    stems = {w[:5] for w in words if len(w) >= 5}
    hit = sum(w in words or (len(w) >= 5 and w[:5] in stems) for w in terms)
    return round(hit / len(terms), 3)


def _finish(report: dict, verdict: dict, started: float, timings: dict) -> dict:
    report["verdict"] = verdict
    timings["total"] = round(time.perf_counter() - started, 3)
    report["timings"] = timings
    return report


def article_text_from_url(url: str) -> tuple[str, str, str]:
    final_url, html = fetch_public_page(url)
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "form"]):
        tag.decompose()
    title = soup.title.get_text(" ", strip=True) if soup.title else final_url
    root = soup.find("article") or soup.body or soup
    paragraphs = [re.sub(r"\s+", " ", p.get_text(" ", strip=True)) for p in root.find_all("p")]
    text = " ".join(p for p in paragraphs if len(p) > 40)
    return final_url, title, text


def verify_article(text: str = "", url: str = "") -> dict:
    """Extract the most check-worthy claims from an article and verify each."""
    title, source_url = "", ""
    if url:
        source_url, title, text = article_text_from_url(url)
    claims = extract_claims(text)
    results = []
    for claim in claims:
        try:
            results.append(verify(claim))
        except ValueError:
            continue
    counts: dict[str, int] = {}
    for r in results:
        counts[r["verdict"]["label"]] = counts.get(r["verdict"]["label"], 0) + 1
    return {"title": title, "url": source_url, "claims": results, "counts": counts,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
