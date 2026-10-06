"""Offline test fixtures: fake Wikipedia/Wikidata responses and fake models."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("FALXON_RATE_PER_MINUTE", "1000")
os.environ.setdefault("FALXON_DATA_DIR", tempfile.mkdtemp(prefix="falxon-test-"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402

WIKI_PAGES = {
    "Eiffel Tower": "The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris, France. "
                    "It is named after the engineer Gustave Eiffel. It was completed in 1889.",
    "Eiffel Tower (Paris, Texas)": "The Eiffel Tower in Paris, Texas is a replica of the tower in France. "
                                   "It stands next to the Love Civic Center.",
    "London": "London is the capital and largest city of England and the United Kingdom.",
}


def _entity(eid, label, claims=None, aliases=()):
    return {"id": eid, "labels": {"en": {"value": label}}, "aliases": {"en": [{"value": a} for a in aliases]},
            "claims": claims or {}, "lastrevid": 1, "modified": "2026-09-01T00:00:00Z"}


def _item_claim(prop, qid, rank="normal"):
    return {"rank": rank, "mainsnak": {"snaktype": "value", "property": prop,
                                       "datavalue": {"value": {"id": qid}}}}


def _time_claim(year):
    return {"rank": "normal", "mainsnak": {"snaktype": "value", "datavalue": {"value": {"time": f"+{year}-00-00T00:00:00Z"}}}}


WIKIDATA = {
    "Q408": _entity("Q408", "Australia", {"P36": [_item_claim("P36", "Q3114")],
                                          "P31": [_item_claim("P31", "Q3624078")]}),
    "Q243": _entity("Q243", "Eiffel Tower", {"P131": [_item_claim("P131", "Q259")], "P17": [_item_claim("P17", "Q142")]}),
    "Q259": _entity("Q259", "7th arrondissement of Paris", {"P131": [_item_claim("P131", "Q90")]}),
    "Q90": _entity("Q90", "Paris", {"P131": [_item_claim("P131", "Q142")], "P31": [_item_claim("P31", "Q515")]}),
    "Q142": _entity("Q142", "France", {"P30": [_item_claim("P30", "Q46")], "P31": [_item_claim("P31", "Q3624078")]}),
    "Q46": _entity("Q46", "Europe", {"P31": [_item_claim("P31", "Q5107")]}),
    "Q84": _entity("Q84", "London", {"P31": [_item_claim("P31", "Q515")]}),
    "Q17": _entity("Q17", "Japan", {"P31": [_item_claim("P31", "Q3624078")]}),
    "Q9999": _entity("Q9999", "Champ de Mars", {"P31": [_item_claim("P31", "Q22698")]}),
    "Q3114": _entity("Q3114", "Canberra"),
    "Q3130": _entity("Q3130", "Sydney"),
    "Q41567": _entity("Q41567", "Hamlet", {"P50": [_item_claim("P50", "Q692")]}),
    "Q692": _entity("Q692", "William Shakespeare", aliases=("Shakespeare",)),
    "Q937": _entity("Q937", "Albert Einstein", {"P31": [_item_claim("P31", "Q5")], "P569": [_time_claim(1879)]}),
}
SEARCH = {"australia": ["Q408"], "hamlet": ["Q41567"], "albert einstein": ["Q937"], "eiffel tower": ["Q243"],
          "paris": ["Q90"], "france": ["Q142"], "europe": ["Q46"], "london": ["Q84"], "japan": ["Q17"],
          "champ de mars": ["Q9999"]}


def fake_get_json(url, params, use_cache=True):
    if "wikidata" in url:
        if params["action"] == "wbsearchentities":
            return {"search": [{"id": i} for i in SEARCH.get(params["search"].lower(), [])]}
        return {"entities": {i: WIKIDATA[i] for i in params["ids"].split("|") if i in WIKIDATA}}
    if params.get("list") == "search":
        q = params["srsearch"].lower()
        hits = [t for t in WIKI_PAGES if any(w in t.lower() for w in q.split())]
        return {"query": {"search": [{"title": t} for t in hits]}}
    title = params["titles"]
    if title not in WIKI_PAGES:
        return {"query": {"pages": [{"title": title, "missing": True}]}}
    return {"query": {"pages": [{"title": title, "extract": WIKI_PAGES[title],
                                 "fullurl": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}",
                                 "revisions": [{"revid": 42, "timestamp": "2026-09-01T00:00:00Z"}]}]}}


def fake_rerank(claim, texts):
    from falxon.models import lexical_scores

    return [s * 10 - 3 for s in lexical_scores(claim, texts)], "fake-reranker"


def fake_nli(claim, premises):
    """Toy NLI: 'Paris' premise + 'Paris' claim => entail; 'Paris' premise + 'London' claim => contradict."""
    out = []
    for p in premises:
        if "Champ de Mars" in p and "London" in claim:
            out.append({"entailment": 0.02, "neutral": 0.03, "contradiction": 0.95})
        elif "Champ de Mars" in p and "Paris" in claim:
            out.append({"entailment": 0.96, "neutral": 0.03, "contradiction": 0.01})
        else:
            out.append({"entailment": 0.05, "neutral": 0.9, "contradiction": 0.05})
    return out


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    from falxon import models, structured
    from falxon.retrieval import wikipedia

    monkeypatch.setattr(wikipedia, "get_json", fake_get_json)
    monkeypatch.setattr(structured, "get_json", fake_get_json)
    monkeypatch.setattr(models, "rerank", fake_rerank)
    monkeypatch.setattr(models, "nli", fake_nli)
