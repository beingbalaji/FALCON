"""Evidence retrieval from English Wikipedia (free public API, no key)."""
from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone

from ..claims import content_terms, split_sentences
from ..config import settings
from ..http import get_json

API = "https://en.wikipedia.org/w/api.php"

_NEGATIONS = re.compile(r"\b(not|no|never|n't|neither|nor|only)\b", re.I)
_SECTION_STOP = re.compile(r"^==+\s*(See also|References|External links|Further reading|Notes|Bibliography|Sources)\s*==+", re.M)


@dataclass
class Page:
    title: str
    text: str
    url: str
    revision_url: str
    revision_id: int | None
    updated_at: str | None
    fetched_at: str
    query_rank: float = 0.0


@dataclass
class Passage:
    text: str
    title: str
    url: str
    revision_url: str
    updated_at: str | None
    position: int
    publisher: str = "Wikipedia"
    scores: dict = field(default_factory=dict)

    @property
    def premise(self) -> str:
        return f"{self.title}: {self.text}"


def entity_spans(claim: str) -> list[str]:
    """Capitalised word sequences (e.g. 'Eiffel Tower', 'Fox Broadcasting Company')."""
    words = re.findall(r"[\w'’.-]+|[^\w\s]", claim)
    spans, current = [], []
    joiners = {"of", "the", "de", "and", "for", "von", "van", "da", "la", "le", "du", "del", "&"}
    for i, word in enumerate(words):
        is_cap = word[:1].isupper() or word[:1].isdigit() and current
        if is_cap and not (i == 0 and word.lower() in {"the", "a", "an", "in", "on", "there"}):
            current.append(word)
        elif current and word.lower() in joiners:
            current.append(word)
        else:
            if current:
                spans.append(current)
            current = []
    if current:
        spans.append(current)
    out = []
    for span in spans:
        while span and span[-1].lower() in joiners:
            span = span[:-1]
        text = " ".join(span).strip(" .,'’")
        if text and text not in out:
            out.append(text)
    return out


def subject_phrase(claim: str) -> str:
    cleaned = re.sub(r"^(the|a|an)\s+", "", claim.strip(), flags=re.I)
    match = re.match(
        r"(.+?)\s+(?:is|are|was|were|has|have|had|became|won|wrote|directed|starred|"
        r"founded|located|lies|died|born|plays|played|did|does|can|will)\b",
        cleaned,
        flags=re.I,
    )
    return match.group(1).strip(" ,.;:") if match and len(match.group(1)) <= 100 else ""


def search_queries(claim: str) -> list[str]:
    base = _NEGATIONS.sub(" ", claim)
    base = re.sub(r"\s+", " ", base).strip(" .")
    queries = []
    for q in [subject_phrase(claim), *entity_spans(claim), base]:
        q = q.strip()
        if q and q.lower() not in {x.lower() for x in queries}:
            queries.append(q)
    return queries[:5]


def search_titles(query: str, limit: int = 4) -> list[str]:
    data = get_json(API, {
        "action": "query", "list": "search", "srsearch": query, "srlimit": str(limit),
        "srprop": "", "format": "json", "formatversion": "2",
    })
    return [hit["title"] for hit in data.get("query", {}).get("search", []) if hit.get("title")]


def rank_titles(claim: str, queries: list[str], results: list[list[str]]) -> list[str]:
    """Merge search results. Titles that match an entity exactly, or come up for
    several queries, rank first; disambiguated variants not mentioned in the claim
    (e.g. 'Eiffel Tower (Paris, Texas)') are pushed down."""
    claim_norm = " ".join(content_terms(claim))
    entities = {e.lower() for e in entity_spans(claim)} | {subject_phrase(claim).lower()}
    scores: dict[str, float] = {}
    for qi, titles in enumerate(results):
        for ri, title in enumerate(titles):
            s = 1.0 / (1 + ri) + (0.3 if qi == 0 else 0.0)
            scores[title] = scores.get(title, 0.0) + s
    for title in scores:
        base = re.sub(r"\s*\(.*?\)\s*", "", title).lower()
        if base in entities:
            scores[title] += 2.0
        paren = re.search(r"\((.*?)\)", title)
        if paren and not set(content_terms(paren.group(1))) <= set(claim_norm.split()):
            scores[title] -= 1.0
        if "disambiguation" in title.lower() or title.lower().startswith("list of"):
            scores[title] -= 3.0
    return [t for t, _ in sorted(scores.items(), key=lambda kv: -kv[1])]


def fetch_page(title: str) -> Page | None:
    data = get_json(API, {
        "action": "query", "prop": "extracts|info|revisions", "titles": title, "redirects": "1",
        "explaintext": "1", "exsectionformat": "wiki", "inprop": "url", "rvprop": "ids|timestamp",
        "format": "json", "formatversion": "2",
    })
    pages = data.get("query", {}).get("pages", [])
    if not pages or pages[0].get("missing") or not pages[0].get("extract"):
        return None
    p = pages[0]
    text = p["extract"]
    stop = _SECTION_STOP.search(text)
    if stop:
        text = text[: stop.start()]
    rev = (p.get("revisions") or [{}])[0]
    url = p.get("fullurl") or f"https://en.wikipedia.org/wiki/{p['title'].replace(' ', '_')}"
    return Page(
        title=p["title"],
        text=text,
        url=url,
        revision_url=f"https://en.wikipedia.org/w/index.php?oldid={rev['revid']}" if rev.get("revid") else url,
        revision_id=rev.get("revid"),
        updated_at=rev.get("timestamp"),
        fetched_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )


def page_passages(page: Page) -> list[Passage]:
    text = re.sub(r"^==+.*?==+\s*$", "\n", page.text, flags=re.M)
    sentences = [s for s in split_sentences(text) if 20 <= len(s) <= 1200]
    sentences = sentences[: settings.max_sentences_per_page]
    out = []
    for i, sentence in enumerate(sentences):
        out.append(Passage(sentence, page.title, page.url, page.revision_url, page.updated_at, i))
        if i + 1 < len(sentences):
            # Two-sentence window keeps pronoun context ("It was completed in 1889.").
            window = f"{sentence} {sentences[i + 1]}"
            out.append(Passage(window, page.title, page.url, page.revision_url, page.updated_at, i))
    return out


def retrieve(claim: str) -> tuple[list[Page], list[Passage]]:
    queries = search_queries(claim)
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda q: _safe(search_titles, q), queries))
    titles = rank_titles(claim, queries, [r or [] for r in results])[: settings.max_pages]
    with ThreadPoolExecutor(max_workers=6) as pool:
        pages = [p for p in pool.map(lambda t: _safe(fetch_page, t), titles) if p]
    # Deduplicate redirects that resolve to the same article.
    unique: dict[str, Page] = {}
    for rank, page in enumerate(pages):
        page.query_rank = 1.0 / (1 + rank)
        unique.setdefault(page.title, page)
    pages = list(unique.values())
    passages = [psg for page in pages for psg in page_passages(page)]
    return pages, passages


def _safe(fn, arg):
    try:
        return fn(arg)
    except Exception:  # network failure on one page must not sink the whole check
        return None
