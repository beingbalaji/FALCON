"""Exact checks against Wikidata for a few common, well-defined relations.

Free-text NLI is weakest on exactly the claims people most often test
("Sydney is the capital of Australia"), because Wikipedia text about Sydney
says it is *a* capital (of New South Wales). For these relations FALXON
compares Wikidata entity IDs instead, and never falls back to guessing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from .http import get_json

API = "https://www.wikidata.org/w/api.php"

HUMAN = "Q5"


@dataclass
class Relation:
    kind: str          # "capital", "head_of_government", "head_of_state", "author", "inception", "birth"
    prop: str
    subject: str       # the value being claimed (e.g. "Sydney")
    holder: str        # the entity that holds the property (e.g. "Australia")
    negated: bool
    year: int | None = None
    exclusive: bool = False  # "only in" / "entirely in"


_PATTERNS = [
    (re.compile(r"^(?:the )?(.+?) (is|was) (not )?(?:the )?capital(?: city)? of (.+?)\.?$", re.I), "capital", "P36"),
    (re.compile(r"^(.+?) (is|was) (not )?(?:the )?(?:current )?(?:prime minister|premier|chancellor|head of government) of (.+?)\.?$", re.I), "head_of_government", "P6"),
    (re.compile(r"^(.+?) (is|was) (not )?(?:the )?(?:current )?(?:president|head of state|king|queen|monarch) of (.+?)\.?$", re.I), "head_of_state", "P35"),
]
_AUTHOR = re.compile(r"^(.+?) (did not write|didn't write|wrote|is the author of|authored) (.+?)\.?$", re.I)
_INCEPTION = re.compile(r"^(?:the )?(.+?) was (not )?(?:founded|established|formed|created) in (\d{3,4})\.?$", re.I)
_BIRTH = re.compile(r"^(.+?) was (not )?born in (\d{3,4})\.?$", re.I)
_LOCATION = re.compile(
    r"^(?:the )?(.+?) (?:is|are) (not )?(?:(?:located|situated|found|based|built) )?(entirely |only |wholly )?in (?:the )?(.+?)\.?$",
    re.I,
)
_FLOWS = re.compile(r"^(?:the )?(.+?) (?:flows|runs) (not )?(entirely |only )?through (?:the )?(.+?)\.?$", re.I)
_COMPLEX = re.compile(r"\b(and|or|because|since|before|after|until|while|although|also)\b", re.I)


def parse(claim: str) -> Relation | None:
    c = claim.strip()
    if _COMPLEX.search(c):
        return None
    for pattern, kind, prop in _PATTERNS:
        m = pattern.match(c)
        if m:
            if m.group(2).lower() == "was":
                return None  # past-tense officeholder/capital claims need dates; leave to text evidence
            return Relation(kind, prop, m.group(1).strip(), m.group(4).strip(), bool(m.group(3)))
    m = _AUTHOR.match(c)
    if m:
        negated = m.group(2).lower().startswith("did")
        return Relation("author", "P50", m.group(1).strip(), m.group(3).strip(" \"'“”"), negated)
    m = _INCEPTION.match(c)
    if m:
        return Relation("inception", "P571", "", m.group(1).strip(), bool(m.group(2)), int(m.group(3)))
    m = _BIRTH.match(c)
    if m:
        return Relation("birth", "P569", "", m.group(1).strip(), bool(m.group(2)), int(m.group(3)))
    m = _LOCATION.match(c) or _FLOWS.match(c)
    if m and not re.search(r"\d", m.group(4)):
        return Relation("location", "P131", m.group(4).strip(), m.group(1).strip(), bool(m.group(2)),
                        exclusive=bool(m.group(3)))
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"^the ", "", s.lower().strip(" .\"'“”"))).strip()


def _get(ids: list[str]) -> dict:
    if not ids:
        return {}
    data = get_json(API, {"action": "wbgetentities", "ids": "|".join(ids[:50]), "props": "labels|aliases|claims|info",
                          "languages": "en", "format": "json"})
    return data.get("entities", {})


def _values(entity: dict, prop: str) -> list[str]:
    out = []
    for st in entity.get("claims", {}).get(prop, []):
        v = st.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and v.get("id"):
            out.append(v["id"])
    return out


def _resolve(name: str, accept=lambda e: True) -> dict | None:
    """Resolve a name to exactly one entity whose label or alias matches it."""
    found = get_json(API, {"action": "wbsearchentities", "search": name, "language": "en", "uselang": "en",
                           "type": "item", "limit": "7", "format": "json"})
    ids = [x["id"] for x in found.get("search", [])]
    entities = [e for e in _get(ids).values() if accept(e)]
    target = _norm(name)
    by_label = [e for e in entities if _norm(e.get("labels", {}).get("en", {}).get("value", "")) == target]
    if len(by_label) == 1:
        return by_label[0]
    if len(by_label) > 1:
        # Prefer the most-referenced entity (search order) when labels tie, e.g. countries vs. ships.
        return by_label[0]
    by_alias = [e for e in entities if any(_norm(a["value"]) == target for a in e.get("aliases", {}).get("en", []))]
    return by_alias[0] if len(by_alias) == 1 else None


def current_statements(statements: list[dict], now: datetime) -> list[dict]:
    valid = []
    for st in statements or []:
        snak = st.get("mainsnak", {})
        if st.get("rank") == "deprecated" or snak.get("snaktype") != "value":
            continue
        ended = False
        for q in st.get("qualifiers", {}).get("P582", []):  # end time
            t = q.get("datavalue", {}).get("value", {}).get("time")
            if t:
                try:
                    end = datetime.fromisoformat(t.lstrip("+").replace("Z", "+00:00").replace("-00-00", "-01-01").replace("-00T", "-01T"))
                    ended = end <= now
                except ValueError:
                    ended = True
        if not ended:
            valid.append(st)
    preferred = [s for s in valid if s.get("rank") == "preferred"]
    return preferred or valid


def _label(e: dict) -> str:
    return e.get("labels", {}).get("en", {}).get("value", "")


def _year(st: dict) -> int | None:
    t = st.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("time", "")
    m = re.match(r"[+-]?(\d{1,4})-", t)
    return int(m.group(1)) if m else None


def check(claim: str) -> dict | None:
    """Return a structured verdict dict, or None when the claim is outside the supported grammar."""
    rel = parse(claim)
    if rel is None:
        return None
    now = datetime.now(timezone.utc)
    try:
        return _check(rel, now)
    except Exception as exc:  # network or schema surprises: report, never guess
        return _result("NOT ENOUGH INFO", rel, f"The structured source could not be reached ({type(exc).__name__}).")


def _result(label, rel, note, entity=None, values=None, confidence=None):
    source = None
    if entity is not None:
        eid = entity.get("id")
        source = {
            "title": f"{_label(entity)} — Wikidata {rel.prop}",
            "url": f"https://www.wikidata.org/wiki/{eid}#{rel.prop}",
            "revision_url": f"https://www.wikidata.org/w/index.php?title={eid}&oldid={entity.get('lastrevid')}",
            "publisher": "Wikidata",
            "text": f"{_label(entity)} — {rel.kind.replace('_', ' ')}: {', '.join(values or []) or 'no usable value'}",
            "updated_at": entity.get("modified"),
        }
    return {
        "engine": "structured",
        "relation": rel.kind,
        "label": label,
        "confidence": confidence if confidence is not None else (0.97 if label != "NOT ENOUGH INFO" else 0.0),
        "note": note,
        "source": source,
    }


def _check(rel: Relation, now: datetime) -> dict:
    if rel.kind in ("capital", "head_of_government", "head_of_state"):
        holder = _resolve(rel.holder, lambda e: bool(e.get("claims", {}).get(rel.prop)))
        if not holder:
            return _result("NOT ENOUGH INFO", rel, f"Could not identify “{rel.holder}” unambiguously in Wikidata.")
        statements = current_statements(holder["claims"].get(rel.prop, []), now)
        ids = list(dict.fromkeys(st["mainsnak"]["datavalue"]["value"]["id"] for st in statements))
        if not ids:
            return _result("NOT ENOUGH INFO", rel, "Wikidata has no current value for this relation.", holder)
        names = {i: _label(e) for i, e in _get(ids).items()}
        values = [names.get(i, i) for i in ids]
        subject_norm = _norm(rel.subject)
        matched = any(_norm(n) == subject_norm for n in values)
        if not matched:
            # Allow aliases, e.g. "Narendra Modi" vs "Narendra Damodardas Modi".
            ents = _get(ids)
            matched = any(
                any(_norm(a["value"]) == subject_norm for a in e.get("aliases", {}).get("en", []))
                for e in ents.values()
            )
        if not matched and len(ids) > 1:
            return _result("NOT ENOUGH INFO", rel, "Several current values are recorded; absence can't be proven.", holder, values)
        supported = matched != rel.negated
        label = "SUPPORTED" if supported else "REFUTED"
        return _result(label, rel, f"Wikidata records the current {rel.kind.replace('_', ' ')} of {_label(holder)} as {', '.join(values)}.", holder, values)

    if rel.kind == "author":
        work = _resolve(rel.holder, lambda e: bool(e.get("claims", {}).get("P50")))
        if not work:
            return _result("NOT ENOUGH INFO", rel, f"Could not identify the work “{rel.holder}” in Wikidata.")
        ids = _values(work, "P50")
        ents = _get(ids)
        values = [_label(e) for e in ents.values()]
        target = _norm(rel.subject)
        matched = any(
            _norm(_label(e)) == target or any(_norm(a["value"]) == target for a in e.get("aliases", {}).get("en", []))
            or target and target == _norm(_label(e)).split()[-1]  # surname only, e.g. "Shakespeare"
            for e in ents.values()
        )
        label = "SUPPORTED" if matched != rel.negated else "REFUTED"
        return _result(label, rel, f"Wikidata lists the author of {_label(work)} as {', '.join(values)}.", work, values)

    if rel.kind == "location":
        return _check_location(rel)

    # inception / birth year
    accept = (lambda e: HUMAN in _values(e, "P31")) if rel.kind == "birth" else (lambda e: bool(e.get("claims", {}).get("P571")))
    entity = _resolve(rel.holder, accept)
    if not entity:
        return _result("NOT ENOUGH INFO", rel, f"Could not identify “{rel.holder}” unambiguously in Wikidata.")
    years = sorted({y for st in entity.get("claims", {}).get(rel.prop, []) if st.get("rank") != "deprecated" for y in [_year(st)] if y})
    if not years:
        return _result("NOT ENOUGH INFO", rel, "Wikidata has no date for this.", entity)
    values = [str(y) for y in years]
    matched = rel.year in years
    if not matched and len(years) > 1:
        return _result("NOT ENOUGH INFO", rel, "Wikidata records conflicting dates.", entity, values)
    label = "SUPPORTED" if matched != rel.negated else "REFUTED"
    what = "was born" if rel.kind == "birth" else "was founded"
    return _result(label, rel, f"Wikidata says {_label(entity)} {what} in {', '.join(values)}.", entity, values)


# --- "X is (located) in Y" -----------------------------------------------------------------
_PLACE_PROPS = ("P131", "P17", "P30", "P276", "P706")  # admin territory, country, continent, location, terrain
_COUNTRY_TYPES = {"Q6256", "Q3624078", "Q7275"}             # country, sovereign state, state
_CONTINENT_TYPES = {"Q5107"}
_CITY_TYPES = {"Q515", "Q1637706", "Q5119", "Q174530", "Q200250", "Q1093829", "Q1549591"}


def _names(e: dict) -> set[str]:
    return {_norm(_label(e))} | {_norm(a["value"]) for a in e.get("aliases", {}).get("en", [])}


def _place_closure(entity: dict, depth: int = 6, limit: int = 80) -> dict[str, dict]:
    """Every place `entity` lies in, following admin-territory, country and continent links."""
    seen = {entity["id"]: entity}
    frontier = [entity]
    for _ in range(depth):
        nxt = []
        for e in frontier:
            for prop in _PLACE_PROPS:
                nxt += [i for i in _values(e, prop) if i not in seen]
        nxt = list(dict.fromkeys(nxt))[: max(0, limit - len(seen))]
        if not nxt:
            break
        fetched = _get(nxt)
        seen.update(fetched)
        frontier = list(fetched.values())
    return seen


def _check_location(rel: Relation) -> dict:
    place = _resolve(rel.holder, lambda e: any(e.get("claims", {}).get(p) for p in ("P131", "P17", "P30")))
    if not place:
        return _result("NOT ENOUGH INFO", rel, f"Could not identify the place “{rel.holder}” in Wikidata.")
    closure = _place_closure(place)
    containers = [e for eid, e in closure.items() if eid != place["id"]]
    shown = [_label(e) for e in containers if _label(e)][:6]
    # "Paris, France" means every part must contain the place.
    parts = [_norm(x) for x in rel.subject.split(",") if x.strip()]
    inside = all(any(part in _names(e) for e in containers) for part in parts)
    where = f"Wikidata places {_label(place)} in {', '.join(shown) or 'no recorded territory'}."
    if inside:
        if rel.exclusive:
            return _result("NOT ENOUGH INFO", rel, where + " Whether it lies only there needs text evidence.", place, shown)
        return _result("REFUTED" if rel.negated else "SUPPORTED", rel, where, place, shown)

    # Not found. Only conclude "false" when the claimed place is a country, continent or city
    # and the record is detailed enough at that level to make absence meaningful.
    raw_parts = [x.strip() for x in rel.subject.split(",") if x.strip()]
    missing = [x for x in raw_parts if not any(_norm(x) in _names(e) for e in containers)]
    other = _resolve(missing[0]) if missing else None
    if not other:
        return _result("NOT ENOUGH INFO", rel, where, place, shown)
    types = set(_values(other, "P31"))
    has_country = any(set(_values(e, "P31")) & _COUNTRY_TYPES for e in containers) or bool(_values(place, "P17"))
    has_continent = any(_values(e, "P30") for e in closure.values())
    decisive = (
        (types & _COUNTRY_TYPES and has_country)
        or (types & _CONTINENT_TYPES and has_continent)
        or (types & _CITY_TYPES and bool(_values(place, "P131")))
    )
    if not decisive:
        return _result("NOT ENOUGH INFO", rel, where, place, shown)
    return _result("SUPPORTED" if rel.negated else "REFUTED", rel,
                   where + f" It is not recorded as being in {_label(other)}.", place, shown)
