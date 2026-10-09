"""Local open-source models: a passage reranker and a FEVER-trained NLI verifier.

Both are loaded lazily and cached for the life of the process. Nothing here
calls a paid API.
"""
from __future__ import annotations

import math
import threading
from functools import lru_cache

from .claims import content_terms
from .config import settings

_load_lock = threading.Lock()


class ModelUnavailable(RuntimeError):
    pass


def _torch():
    try:
        import torch  # noqa: WPS433
        return torch
    except ImportError as exc:  # pragma: no cover - depends on install
        raise ModelUnavailable("PyTorch is not installed. Run: pip install -r requirements.txt") from exc


@lru_cache(maxsize=1)
def _reranker():
    with _load_lock:
        torch = _torch()
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(settings.rerank_model)
        model = AutoModelForSequenceClassification.from_pretrained(settings.rerank_model).eval()
        torch.set_grad_enabled(False)
        return tok, model


@lru_cache(maxsize=1)
def _nli():
    with _load_lock:
        _torch()
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(settings.nli_model)
        model = AutoModelForSequenceClassification.from_pretrained(settings.nli_model).eval()
        labels = {int(k): str(v).lower() for k, v in model.config.id2label.items()}
        index = {}
        for i, name in labels.items():
            for key in ("entailment", "neutral", "contradiction"):
                if name.startswith(key[:6]):
                    index[key] = i
        if len(index) != 3:
            raise ModelUnavailable(f"Unexpected NLI labels {labels}; refusing to guess the mapping.")
        return tok, model, index


def lexical_scores(claim: str, texts: list[str]) -> list[float]:
    """Fallback relevance: share of claim terms present (used if the reranker can't load)."""
    terms = set(content_terms(claim))
    out = []
    for text in texts:
        words = set(content_terms(text))
        out.append(len(terms & words) / max(len(terms), 1))
    return out


def rerank(claim: str, texts: list[str], batch_size: int = 32) -> tuple[list[float], str]:
    """Return relevance scores (higher = more relevant) and the method used."""
    if not texts:
        return [], "none"
    try:
        tok, model = _reranker()
    except Exception:
        return lexical_scores(claim, texts), "lexical-overlap"
    torch = _torch()
    scores: list[float] = []
    for start in range(0, len(texts), batch_size):
        chunk = texts[start : start + batch_size]
        enc = tok([claim] * len(chunk), chunk, padding=True, truncation=True, max_length=256, return_tensors="pt")
        with torch.no_grad():
            logits = model(**enc).logits.view(-1)
        scores.extend(float(x) for x in logits)
    return scores, settings.rerank_model


def nli(claim: str, premises: list[str]) -> list[dict]:
    """Probabilities that each premise entails / contradicts / is neutral to the claim."""
    if not premises:
        return []
    tok, model, index = _nli()
    torch = _torch()
    enc = tok(premises, [claim] * len(premises), padding=True, truncation=True, max_length=384, return_tensors="pt")
    with torch.no_grad():
        probs = torch.softmax(model(**enc).logits, dim=-1)
    out = []
    for row in probs:
        out.append({k: round(float(row[i]), 4) for k, i in index.items()})
    return out


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))
