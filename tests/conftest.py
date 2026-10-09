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


def _qty(prop, amount, unit="Q828224"):
    return {"rank": "normal", "mainsnak": {"snaktype": "value", "property": prop, "datavalue": {
        "value": {"amount": f"+{amount}", "unit": f"http://www.wikidata.org/entity/{unit}"}}}}


def _planet(eid, label, radius_km, axis_au, star="Q525"):
    return _entity(eid, label, {"P31": [_item_claim("P31", "Q634")], "P397": [_item_claim("P397", star)],
                                "P2120": [_qty("P2120", radius_km)], "P2233": [_qty("P2233", axis_au, "Q1811")]})


def _ocean(eid, label, area_km2):
    return _entity(eid, label, {"P31": [_item_claim("P31", "Q9430")], "P361": [_item_claim("P361", "Q1239")],
                                "P2046": [_qty("P2046", area_km2, "Q712226")]})


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
    # Astronomy: planets orbit the Sun, which is part of the Solar System; an exoplanet must not count.
    "Q634": _entity("Q634", "planet", {"P279": [_item_claim("P279", "Q6999")]}),
    "Q525": _entity("Q525", "Sun", {"P361": [_item_claim("P361", "Q544")]}),
    "Q544": _entity("Q544", "Solar System"),
    "Q308": _planet("Q308", "Mercury", 2439.7, 0.387),
    "Q313": _planet("Q313", "Venus", 6051.8, 0.723),
    "Q2": _planet("Q2", "Earth", 6371, 1.0),
    "Q111": {**_planet("Q111", "Mars", 3389.5, 1.524), "aliases": {"en": [{"value": "Red Planet"}]}},
    "Q319": _planet("Q319", "Jupiter", 69911, 5.20),
    "Q332": {**_planet("Q332", "Neptune", 24622, 30.07),
             "claims": {**_planet("Q332", "Neptune", 24622, 30.07)["claims"], "P31": [_item_claim("P31", "Q7001")]}},
    "Q7001": _entity("Q7001", "ice giant", {"P279": [_item_claim("P279", "Q7002")]}),
    "Q7002": _entity("Q7002", "giant planet", {"P279": [_item_claim("P279", "Q634")]}),
    "Q9001": _planet("Q9001", "HD 100546 b", 490000, 53, star="Q9002"),
    "Q405": {**_entity("Q405", "Moon", {"P31": [_item_claim("P31", "Q2537")], "P397": [_item_claim("P397", "Q2")]}),
             "sitelinks": {f"wiki{i}": {} for i in range(200)}},
    "Q7004": {**_entity("Q7004", "Moon", {"P31": [_item_claim("P31", "Q11424")]}), "sitelinks": {"enwiki": {}}},
    "Q2537": _entity("Q2537", "natural satellite", {"P279": [_item_claim("P279", "Q6999")]}, aliases=("moon",)),
    "Q6999": _entity("Q6999", "astronomical object"),
    "Q9430": _entity("Q9430", "ocean"),
    "Q98": _ocean("Q98", "Pacific Ocean", 165250000),
    "Q97": _ocean("Q97", "Atlantic Ocean", 106460000),
    "Q788": _ocean("Q788", "Arctic Ocean", 14060000),
    "Q1239": _ocean("Q1239", "World Ocean", 361000000),
    "Q7003": _entity("Q7003", "Tethys Ocean", {"P31": [_item_claim("P31", "Q9430")]}),
    "Q513": {**_entity("Q513", "Mount Everest", {"P17": [_item_claim("P17", "Q837")], "P30": [_item_claim("P30", "Q48")],
                                                "P706": [_item_claim("P706", "Q5451")]}),
             "sitelinks": {f"wiki{i}": {} for i in range(250)}},
    "Q837": _entity("Q837", "Nepal", {"P31": [_item_claim("P31", "Q3624078")], "P30": [_item_claim("P30", "Q48")]}),
    "Q48": _entity("Q48", "Asia", {"P31": [_item_claim("P31", "Q5107")]}),
    "Q7005": {**_entity("Q7005", "Mount Everest", {"P131": [_item_claim("P131", "Q7006")]}), "sitelinks": {"cebwiki": {}}},
    "Q7006": _entity("Q7006", "Shire of Somewhere", {"P17": [_item_claim("P17", "Q408")]}),
    # Historical and geological links that must not count as "is in"
    "Q12501": _entity("Q12501", "Great Wall of China", {"P131": [_item_claim("P131", "Q41079")],
                                                        "P17": [_item_claim("P17", "Q148")]}),
    "Q41079": _entity("Q41079", "Inner Mongolia", {"P131": [_item_claim("P131", "Q148")], "P17": [
        _item_claim("P17", "Q148"),
        {**_item_claim("P17", "Q188712"), "qualifiers": {"P582": [{"datavalue": {"value": {"time": "+1945-09-02T00:00:00Z"}}}]}}]}),
    "Q148": _entity("Q148", "People's Republic of China", {"P31": [_item_claim("P31", "Q3624078")],
                                                           "P30": [_item_claim("P30", "Q48")]}, aliases=("China",)),
    "Q188712": _entity("Q188712", "Empire of Japan", {"P31": [_item_claim("P31", "Q3024240")]}, aliases=("Japan",)),
    "Q5451": _entity("Q5451", "Himalayas", {"P706": [_item_claim("P706", "Q7007")]}),
    "Q7007": _entity("Q7007", "Indo-Australian Plate", aliases=("Australia",)),
    "Q43514": _entity("Q43514", "theory of relativity", {"P527": [_item_claim("P527", "Q11455")]}),
    "Q11455": _entity("Q11455", "general relativity", {"P61": [_item_claim("P61", "Q937")]}),
}
SEARCH = {"australia": ["Q408"], "hamlet": ["Q41567"], "albert einstein": ["Q937"], "eiffel tower": ["Q243"],
          "paris": ["Q90"], "france": ["Q142"], "europe": ["Q46"], "london": ["Q84"], "japan": ["Q17"],
          "champ de mars": ["Q9999"], "planet": ["Q634"], "sun": ["Q525"], "solar system": ["Q544"],
          "mercury": ["Q308"], "venus": ["Q313"], "earth": ["Q2"], "mars": ["Q111"], "jupiter": ["Q319"],
          "neptune": ["Q332"], "moon": ["Q7004", "Q405"], "ocean": ["Q9430"], "pacific ocean": ["Q98"],
          "atlantic ocean": ["Q97"], "arctic ocean": ["Q788"], "theory of relativity": ["Q43514"],
          "william shakespeare": ["Q692"], "mount everest": ["Q7005", "Q513"], "nepal": ["Q837"], "asia": ["Q48"], "great wall of china": ["Q12501"], "china": ["Q148"]}


def _ids(entity, prop):
    return [st["mainsnak"]["datavalue"]["value"].get("id") for st in entity.get("claims", {}).get(prop, [])
            if isinstance(st["mainsnak"]["datavalue"]["value"], dict)]


def fake_get_json(url, params, use_cache=True):
    if "wikidata" in url:
        if params["action"] == "query":
            # haswbstatement filters: space = AND, "|" = OR, as in Wikidata's search engine.
            filters = [f.removeprefix("haswbstatement:").split("|") for f in params["srsearch"].split()]
            hits = [eid for eid, e in WIKIDATA.items()
                    if all(any(rhs in _ids(e, lhs) for lhs, _, rhs in (alt.partition("=") for alt in f)) for f in filters)]
            return {"query": {"search": [{"title": h} for h in hits], "searchinfo": {"totalhits": len(hits)}}}
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
