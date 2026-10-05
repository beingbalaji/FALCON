"""Turn per-passage NLI scores into one verdict, abstaining when evidence is weak."""
from __future__ import annotations

import math

SUPPORTED = "SUPPORTED"
REFUTED = "REFUTED"
NEI = "NOT ENOUGH INFO"
CONFLICTING = "CONFLICTING EVIDENCE"
LABELS = (SUPPORTED, REFUTED, NEI)


def _strong(scores: dict, key: str, floor: float, margin: float) -> bool:
    others = [v for k, v in scores.items() if k != key]
    return scores[key] >= floor and scores[key] - max(others) >= margin


def decide(evidence: list[dict], thresholds: dict) -> dict:
    """`evidence` items need `nli` ({entailment, contradiction, neutral}) and `relevance` (logit).

    Returns label, confidence, distribution and indices of decisive passages.
    """
    usable = [e for e in evidence if e.get("nli") and e.get("relevance", 0.0) >= thresholds["relevance"]]
    if not usable:
        return {"label": NEI, "confidence": 0.0, "distribution": {SUPPORTED: 0.0, REFUTED: 0.0, NEI: 1.0},
                "decisive": [], "reason": "No sufficiently relevant evidence was found."}

    # Relevance-weighted average, for display.
    weights = [math.exp(min(e["relevance"], 20.0) / 2.0) for e in usable]
    total = sum(weights)
    dist = {
        SUPPORTED: sum(w * e["nli"]["entailment"] for w, e in zip(weights, usable)) / total,
        REFUTED: sum(w * e["nli"]["contradiction"] for w, e in zip(weights, usable)) / total,
        NEI: sum(w * e["nli"]["neutral"] for w, e in zip(weights, usable)) / total,
    }
    dist = {k: round(v, 4) for k, v in dist.items()}

    support = [e for e in usable if _strong(e["nli"], "entailment", thresholds["entail"], thresholds["margin"])]
    refute = [e for e in usable if _strong(e["nli"], "contradiction", thresholds["contradict"], thresholds["margin"])]
    best_s = max((e["nli"]["entailment"] for e in support), default=0.0)
    best_r = max((e["nli"]["contradiction"] for e in refute), default=0.0)

    if support and refute:
        if abs(best_s - best_r) < 0.05:
            return {"label": CONFLICTING, "confidence": round(max(best_s, best_r), 4), "distribution": dist,
                    "decisive": [e["id"] for e in support + refute],
                    "reason": "Relevant sources point in opposite directions."}
        if best_s > best_r:
            refute = []
        else:
            support = []
    if support:
        return {"label": SUPPORTED, "confidence": round(best_s, 4), "distribution": dist,
                "decisive": [e["id"] for e in support],
                "reason": "At least one highly relevant passage clearly states what the claim says."}
    if refute:
        return {"label": REFUTED, "confidence": round(best_r, 4), "distribution": dist,
                "decisive": [e["id"] for e in refute],
                "reason": "At least one highly relevant passage clearly contradicts the claim."}
    return {"label": NEI, "confidence": round(1.0 - max(dist[SUPPORTED], dist[REFUTED]), 4), "distribution": dist,
            "decisive": [], "reason": "The sources found neither clearly support nor clearly contradict the claim."}


def as_fever_label(label: str) -> str:
    return NEI if label == CONFLICTING else label
