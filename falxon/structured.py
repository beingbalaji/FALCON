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


_PATTERNS = [
    (re.compile(r"^(?:the )?(.+?) (is|was) (not )?(?:the )?capital(?: city)? of (.+?)\.?$", re.I), "capital", "P36"),
    (re.compile(r"^(.+?) (is|was) (not )?(?:the )?(?:current )?(?:prime minister|premier|chancellor|head of government) of (.+?)\.?$", re.I), "head_of_government", "P6"),
    (re.compile(r"^(.+?) (is|was) (not )?(?:the )?(?:current )?(?:president|head of state|king|queen|monarch) of (.+?)\.?$", re.I), "head_of_state", "P35"),
]
_AUTHOR = re.compile(r"^(.+?) (did not write|didn't write|wrote|is the author of|authored) (.+?)\.?$", re.I)
_INCEPTION = re.compile(r"^(?:the )?(.+?) was (not )?(?:founded|established|formed|created) in (\d{3,4})\.?$", re.I)
_BIRTH = re.compile(r"^(.+?) was (not )?born in (\d{3,4})\.?$", re.I)
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
