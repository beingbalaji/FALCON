"""Claim validation and check-worthy claim extraction from longer text."""
from __future__ import annotations

import re

from .config import settings

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+(?=[\"'(\[]?[A-Z0-9])")
_ABBREVIATIONS = ("Mr.", "Mrs.", "Ms.", "Dr.", "St.", "Jr.", "Sr.", "U.S.", "U.K.", "e.g.", "i.e.", "vs.", "No.")

# Words that mark opinion, prediction or hedging rather than a checkable fact.
_OPINION = re.compile(
    r"\b(I think|I believe|in my opinion|we feel|should|must|ought|might|may be|"
    r"could be|probably|perhaps|best|worst|beautiful|amazing|terrible|awesome)\b",
    re.I,
)
_STOP = set(
    "a an the is are was were be been being in on at to of for from by with and or but not no "
    "never does do did has have had it its that this as also which who whom whose".split()
)


class ClaimError(ValueError):
    """Raised when user input cannot be checked."""


def normalize_claim(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    text = text.strip("\"“”'‘’ ")
    if text and text[-1] not in ".!?":
        text += "."
    return text


def validate_claim(text: str) -> str:
    claim = normalize_claim(text)
    if len(claim) < settings.claim_min_chars:
        raise ClaimError("Enter one factual statement of at least a few words.")
    if len(claim) > settings.claim_max_chars:
        raise ClaimError(
            f"Use one statement of up to {settings.claim_max_chars} characters, "
            "or paste it as an article to split it into claims."
        )
    if not re.search(r"[A-Za-z]", claim):
        raise ClaimError("FALXON currently supports English text.")
    if claim.endswith("?"):
        raise ClaimError("Rephrase the question as a statement, e.g. 'X is Y.'")
    return claim


def content_terms(text: str) -> list[str]:
    seen: dict[str, None] = {}
    for token in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if len(token) > 1 and token not in _STOP:
            seen.setdefault(token, None)
    return list(seen)


def split_sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    protected = text
    for i, abbr in enumerate(_ABBREVIATIONS):
        protected = protected.replace(abbr, f"\x00{i}\x00")
    parts = _SENTENCE_SPLIT.split(protected)
    out = []
    for part in parts:
        for i, abbr in enumerate(_ABBREVIATIONS):
            part = part.replace(f"\x00{i}\x00", abbr)
        part = part.strip()
        if part:
            out.append(part)
    return out


def checkworthiness(sentence: str) -> float:
    """Heuristic 0..1 score of how checkable a sentence is.

    Factual claims usually name an entity, a number or a date, use a
    declarative verb, and avoid opinion/hedging words.
    """
    s = sentence.strip()
    words = s.split()
    if len(words) < 5 or len(words) > 60 or s.endswith("?"):
        return 0.0
    score = 0.3
    # Proper nouns beyond the first word.
    if any(w[:1].isupper() for w in words[1:]):
        score += 0.25
    if re.search(r"\b\d{1,4}(?:[.,]\d+)?%?\b", s):
        score += 0.2
    if re.search(r"\b(is|are|was|were|has|have|had|won|founded|born|died|became|wrote|"
                 r"located|killed|announced|increased|decreased|rose|fell|signed)\b", s, re.I):
        score += 0.2
    if _OPINION.search(s):
        score -= 0.4
    if s.startswith(("\"", "“")) or re.search(r"\b(said|says|told|according to)\b", s, re.I):
        score -= 0.1  # attributed speech: checkable, but lower priority
    return max(0.0, min(1.0, score))


def extract_claims(text: str, limit: int | None = None) -> list[str]:
    """Return the most check-worthy sentences, in their original order."""
    limit = limit or settings.article_max_claims
    sentences = split_sentences(text)
    scored = [(checkworthiness(s), i, s) for i, s in enumerate(sentences)]
    keep = sorted((x for x in scored if x[0] >= 0.5), key=lambda x: (-x[0], x[1]))[:limit]
    return [normalize_claim(s) for _, _, s in sorted(keep, key=lambda x: x[1])]
