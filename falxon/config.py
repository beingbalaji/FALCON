"""Runtime settings. Every value can be overridden with an environment variable."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _env(name: str, default: str) -> str:
    return os.environ.get(f"FALXON_{name}", default)


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path(_env("DATA_DIR", str(ROOT / "var")))

    # Free, open models from the Hugging Face hub. All run locally on CPU.
    nli_model: str = _env("NLI_MODEL", "MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli")
    rerank_model: str = _env("RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")

    user_agent: str = _env(
        "USER_AGENT",
        "FALXON/5.0 (academic claim-verification project; https://github.com/beingbalaji/FALCON)",
    )
    request_timeout: float = float(_env("REQUEST_TIMEOUT", "12"))

    max_pages: int = int(_env("MAX_PAGES", "6"))
    max_sentences_per_page: int = int(_env("MAX_SENTENCES_PER_PAGE", "120"))
    rerank_keep: int = int(_env("RERANK_KEEP", "8"))
    nli_keep: int = int(_env("NLI_KEEP", "5"))

    claim_min_chars: int = 8
    claim_max_chars: int = 400
    article_max_claims: int = int(_env("ARTICLE_MAX_CLAIMS", "6"))

    thresholds: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "falxon.db"


# Decision thresholds. Defaults are conservative; `evaluation/calibrate.py`
# tunes them on a FEVER split and writes reports/thresholds.json.
DEFAULT_THRESHOLDS = {
    "entail": 0.80,      # minimum entailment probability to count a passage as support
    "contradict": 0.80,  # minimum contradiction probability to count a passage as refutation
    "margin": 0.30,      # winning label must beat the runner-up by this much
    "relevance": 0.0,    # minimum reranker logit for a passage to be considered at all
}


def load_thresholds() -> dict:
    path = ROOT / "reports" / "thresholds.json"
    values = dict(DEFAULT_THRESHOLDS)
    if path.exists():
        try:
            values.update({k: float(v) for k, v in json.loads(path.read_text()).items() if k in values})
        except (ValueError, OSError):
            pass
    return values


settings = Settings(thresholds=load_thresholds())
