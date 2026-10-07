"""Comparisons that Wikidata can settle with numbers: superlatives, comparatives, orbits and discoveries.

"Mars is the largest planet in the Solar System" is hard for NLI, because no
Wikipedia sentence says it is *not*. Wikidata records each planet's radius,
so one counterexample (Jupiter is larger) proves the claim false. A claim is
only called true when the whole comparison class could be read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import structured as s

# adjective stem -> (Wikidata properties to compare, in order of preference; +1 = bigger value wins)
_MEASURES = {
    "large": (("P2046", "P2120", "P2067"), 1),   # area, radius, mass
    "big": (("P2046", "P2120", "P2067"), 1),
    "small": (("P2046", "P2120", "P2067"), -1),
    "tall": (("P2048", "P2044"), 1),             # height, elevation
    "high": (("P2044", "P2048"), 1),
    "long": (("P2043",), 1),                     # length
    "short": (("P2043",), -1),
    "deep": (("P4511",), 1),                     # vertical depth
    "populous": (("P1082",), 1),                 # population
    "old": (("P571",), -1),                      # inception: earlier is older
    "far": (("P2233",), 1),                      # semi-major axis of the orbit
    "close": (("P2233",), -1),
}
_SUPERLATIVE = {
    "largest": "large", "biggest": "big", "smallest": "small", "tallest": "tall", "highest": "high",
    "longest": "long", "shortest": "short", "deepest": "deep", "oldest": "old", "most populous": "populous",
    "farthest": "far", "furthest": "far", "closest": "close", "nearest": "close",
}
_COMPARATIVE = {
    "larger": "large", "bigger": "big", "smaller": "small", "taller": "tall", "higher": "high",
    "longer": "long", "shorter": "short", "deeper": "deep", "older": "old", "more populous": "populous",
    "farther": "far", "further": "far", "closer": "close", "nearer": "close",
}
_MORE = {"large": "larger", "big": "larger", "small": "smaller", "tall": "greater", "high": "greater",
         "long": "greater", "short": "smaller", "deep": "greater", "populous": "larger", "old": "earlier",
         "far": "greater", "close": "smaller"}
_MOST = {k: {"larger": "largest", "smaller": "smallest", "greater": "greatest", "earlier": "earliest"}[v]
         for k, v in _MORE.items()}
_LESS = {"less populous": ("populous", True)}

# Units converted to SI base values; anything else is skipped rather than guessed.
_UNITS = {
    "1": 1.0, "Q11573": 1.0, "Q828224": 1e3, "Q253276": 1609.344, "Q3710": 0.3048, "Q1811": 1.495978707e11,
    "Q25343": 1.0, "Q712226": 1e6, "Q232291": 2.589988110336e6, "Q35852": 1e4,
    "Q11570": 1.0, "Q191118": 1e3,
}
_WHOLE_WORLD = {"earth", "world", "planet earth", "globe"}
_CONTEXT_PROPS = ("P361", "P397", "P706", "P30", "P17", "P131", "P276")
MAX_MEMBERS = 120  # whole entities are fetched, so keep large classes (countries) affordable


def _alt(words) -> str:
    return "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True))


_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8,
             "ninth": 9, "tenth": 10}
_SUP_RE = re.compile(
    rf"^(?:the )?(.+?) (?:is|are) (not )?the (?:({_alt(_ORDINALS)})[- ])?({_alt(_SUPERLATIVE)}) (.+?)"
    rf"(?: (?:in|of|on|from|to|within) (?:the |our )?(.+?))?\.?$", re.I)
# "Venus is the second planet from the Sun": order by distance from the named body.
_ORDER_RE = re.compile(
    rf"^(?:the )?(.+?) (?:is|are) (not )?the ({_alt(_ORDINALS)}) (\w+(?: \w+)?) from (?:the )?(.+?)\.?$", re.I)
_CMP_RE = re.compile(
    rf"^(?:the )?(.+?) (?:is|are) (not )?({_alt(list(_COMPARATIVE) + list(_LESS))})(?: (?:to|from) (?:the )?(.+?))? than (?:the )?(.+?)\.?$", re.I)
_ORBIT_RE = re.compile(
    r"^(?:the )?(.+?) (?:(does not|doesn't) )?(?:(?:revolves?|rotates?|goes|go|moves?|travels?) a?round|orbits?|circles?)"
    r"(?: a?round)? (?:the )?(.+?)\.?$", re.I)
_DISCOVER_RE = re.compile(
    r"^(.+?) (did not |didn't )?(developed|discovered|invented|formulated|proposed|develop|discover|invent|formulate|propose) (?:the )?(.+?)\.?$", re.I)

_NAME_RE = re.compile(
    r"^(?:the )?(.+?) (?:is|are) (not )?(?:commonly |often |also |popularly )?(?:called|known as|nicknamed) (?:the )?(.+?)\.?$", re.I)
# "The Moon is a planet", "The Moon is Earth's natural satellite"
_INSTANCE_RE = re.compile(r"^(?:the )?(.+?) (?:is|are) (not )?(?:(?:a|an) |(?:the )?(?:(\w+(?: \w+)?)'s (?:only )?))(.+?)\.?$", re.I)

# Kinds of celestial body that exclude one another: being one rules out the others.
_EXCLUSIVE_KINDS = [{"planet", "natural satellite", "star", "asteroid", "comet", "galaxy", "dwarf planet"}]


@dataclass
class Measure:
    kind: str                 # "superlative", "comparative", "orbit", "discovery"
    subject: str
    negated: bool
    stem: str = ""
    noun: str = ""            # comparison class for superlatives ("planet")
    context: str = ""         # "the Solar System", "the Sun"
    other: str = ""           # the second entity in a comparative / the orbited body / the discovered thing
    inverse: bool = False     # "less populous"
    extra: dict = field(default_factory=dict)


def parse(claim: str) -> Measure | None:
    c = claim.strip()
    if s._COMPLEX.search(c):
        return None
    m = _SUP_RE.match(c)
    if m:
        noun, ctx = m.group(5).strip(), (m.group(6) or "").strip()
        if re.search(r"\d", noun + ctx) or len(noun.split()) > 3:
            return None
        rank = _ORDINALS[m.group(3).lower()] if m.group(3) else 1
        return Measure("superlative", m.group(1).strip(), bool(m.group(2)), _SUPERLATIVE[m.group(4).lower()],
                       noun=noun, context=ctx, extra={"rank": rank})
    m = _ORDER_RE.match(c)
    if m:
        return Measure("superlative", m.group(1).strip(), bool(m.group(2)), "close", noun=m.group(4).strip(),
                       context=m.group(5).strip(), extra={"rank": _ORDINALS[m.group(3).lower()]})
    m = _CMP_RE.match(c)
    if m:
        word = m.group(3).lower()
        stem, inverse = _LESS[word] if word in _LESS else (_COMPARATIVE[word], False)
        return Measure("comparative", m.group(1).strip(), bool(m.group(2)), stem, context=(m.group(4) or "").strip(),
                       other=m.group(5).strip(), inverse=inverse)
    m = _ORBIT_RE.match(c)
    if m and len(m.group(3).split()) <= 4:
        return Measure("orbit", m.group(1).strip(), bool(m.group(2)), other=m.group(3).strip())
    m = _DISCOVER_RE.match(c)
    if m and len(m.group(4).split()) <= 6:
        return Measure("discovery", m.group(1).strip(), bool(m.group(2)), other=m.group(4).strip())
    m = _NAME_RE.match(c)
    if m:
        return Measure("nickname", m.group(1).strip(), bool(m.group(2)), other=m.group(3).strip(" \"'“”"))
    m = _INSTANCE_RE.match(c)
    if m and len(m.group(4).split()) <= 3 and not re.search(r"\d", m.group(4)):
        return Measure("instance", m.group(1).strip(), bool(m.group(2)), noun=m.group(4).strip(),
                       context=(m.group(3) or "").strip())
    return None


# --- Wikidata reading ----------------------------------------------------------------------

def _best(entity: dict, prop: str) -> list[dict]:
    sts = [st for st in entity.get("claims", {}).get(prop, [])
           if st.get("rank") != "deprecated" and st.get("mainsnak", {}).get("snaktype") == "value"]
    preferred = [st for st in sts if st.get("rank") == "preferred"]
    return preferred or sts


def value(entity: dict, prop: str) -> float | None:
    """The entity's best value for a quantity (in SI units) or a date (as a year)."""
    for st in _best(entity, prop):
        v = st["mainsnak"].get("datavalue", {}).get("value")
        if not isinstance(v, dict):
            continue
        if "amount" in v:
            unit = v.get("unit", "1").rsplit("/", 1)[-1]
            if unit in _UNITS:
                return float(v["amount"]) * _UNITS[unit]
        elif "time" in v:
            m = re.match(r"([+-])(\d+)-", v["time"])
            if m:
                return int(m.group(2)) * (-1 if m.group(1) == "-" else 1)
    return None


def _fmt(x: float, prop: str) -> str:
    if prop == "P571":
        return f"{int(-x)} BCE" if x < 0 else str(int(x))
    if prop == "P1082":
        return f"{x:,.0f}"
    if prop == "P2233":
        return f"{x / 1.495978707e11:.3g} AU"
    if prop == "P2046":
        return f"{x / 1e6:,.0f} km²"
    if prop == "P2067":
        return f"{x:.3g} kg"
    if x >= 1e6:
        return f"{x / 1e3:,.0f} km"
    return f"{x / 1e3:,.4g} km" if x >= 1e4 else f"{x:,.4g} m"


def _class_members(class_id: str) -> tuple[list[str], bool]:
    """Items that are instances of the class or of one of its direct subclasses; and whether the list is complete."""
    def search(stmt, limit=500):
        data = s.get_json(s.API, {"action": "query", "list": "search", "srsearch": f"haswbstatement:{stmt}",
                                  "srnamespace": "0", "srlimit": str(limit), "format": "json"})
        q = data.get("query", {})
        ids = [h["title"] for h in q.get("search", []) if re.fullmatch(r"Q\d+", h.get("title", ""))]
        return ids, q.get("searchinfo", {}).get("totalhits", len(ids)) <= len(ids)

    subclasses, complete = search(f"P279={class_id}", 10)
    members: list[str] = []
    for cid in [class_id] + subclasses:
        ids, done = search(f"P31={cid}")
        complete = complete and done
        members += [i for i in ids if i not in members]
    if len(members) > MAX_MEMBERS:
        members, complete = members[:MAX_MEMBERS], False
    return members, complete


def _fetch(ids: list[str]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for i in range(0, len(ids), 50):
        out.update(s._get(ids[i:i + 50]))
    return out


def _in_context(members: dict[str, dict], context_id: str) -> dict[str, dict]:
    """Members linked to the context directly, or through one intermediate (planet -> Sun -> Solar System)."""
    direct = {m: e for m, e in members.items() if any(context_id in s._values(e, p) for p in _CONTEXT_PROPS)}
    hops = {v for e in members.values() for p in ("P361", "P397") for v in s._values(e, p)} - {context_id}
    linked = {h for h, e in _fetch(sorted(hops)[:50]).items() if any(context_id in s._values(e, p) for p in ("P361", "P397"))}
    via = {m: e for m, e in members.items() if any(v in linked for p in ("P361", "P397") for v in s._values(e, p))}
    return {**direct, **via}


# --- checks --------------------------------------------------------------------------------

def _rel(m: Measure, prop: str) -> s.Relation:
    return s.Relation(m.kind, prop, m.other or m.noun, m.subject, m.negated)


def _verdict(truth: bool, m: Measure) -> str:
    return "SUPPORTED" if truth != m.negated else "REFUTED"


def check(m: Measure) -> dict:
    if m.kind == "superlative":
        return _check_superlative(m)
    if m.kind == "comparative":
        return _check_comparative(m)
    if m.kind == "orbit":
        return _check_orbit(m)
    if m.kind == "nickname":
        return _check_nickname(m)
    if m.kind == "instance":
        return _check_instance(m)
    return _check_discovery(m)


def _check_nickname(m: Measure) -> dict:
    """Names can only be confirmed: a missing alias proves nothing."""
    rel = s.Relation("nickname", "P31", m.other, m.subject, m.negated)
    entity = s._resolve(m.subject)
    if not entity:
        return s._result("NOT ENOUGH INFO", rel, f"Could not identify “{m.subject}” in Wikidata.")
    aliases = [a["value"] for a in entity.get("aliases", {}).get("en", [])]
    if s._norm(m.other) in {s._norm(a) for a in aliases}:
        return s._result(_verdict(True, m), rel, f"Wikidata lists “{m.other}” as another name for {s._label(entity)}.",
                         entity, aliases[:6])
    return s._result("NOT ENOUGH INFO", rel, "Wikidata does not list that name; other sources may.", entity, aliases[:6])


def _class_closure(entity: dict, depth: int = 4, limit: int = 60) -> dict[str, dict]:
    """Every class the entity is an instance of, directly or through subclass links."""
    seen: dict[str, dict] = {}
    frontier = s._values(entity, "P31") + s._values(entity, "P106")  # occupations count for people
    for _ in range(depth):
        frontier = [i for i in dict.fromkeys(frontier) if i not in seen][: max(0, limit - len(seen))]
        if not frontier:
            break
        fetched = s._get(frontier)
        seen.update(fetched)
        frontier = [v for e in fetched.values() for v in s._values(e, "P279")]
    return seen


def _check_instance(m: Measure) -> dict:
    rel = s.Relation("instance", "P31", m.noun, m.subject, m.negated)
    entity = s._resolve(m.subject, lambda e: bool(s._values(e, "P31")))
    if not entity:
        return s._result("NOT ENOUGH INFO", rel, f"Could not identify “{m.subject}” in Wikidata.")
    classes = _class_closure(entity)
    names = {n for e in classes.values() for n in s._names(e)}
    direct = [s._label(e) for i, e in classes.items() if i in s._values(entity, "P31")][:5]
    noun = s._norm(m.noun)
    owner_ok = True
    if m.context:  # "Earth's natural satellite": also check the possessor
        owner = s._resolve(m.context)
        links = {v for p in ("P397", "P361", "P17", "P131", "P749", "P127") for v in s._values(entity, p)}
        owner_ok = bool(owner) and owner["id"] in links
    if noun in names or noun.rstrip("s") in names:
        if not owner_ok:
            return s._result("NOT ENOUGH INFO", rel, f"Wikidata classes {s._label(entity)} as {m.noun}, but does not "
                             f"link it to {m.context}.", entity, direct)
        return s._result(_verdict(True, m), rel, f"Wikidata classes {s._label(entity)} as {', '.join(direct)}.", entity, direct)
    for group in _EXCLUSIVE_KINDS:
        if noun in group:
            other = (names & group) - {noun}
            if other:
                return s._result(_verdict(False, m), rel,
                                 f"Wikidata classes {s._label(entity)} as a {sorted(other)[0]}, not a {m.noun}.",
                                 entity, direct)
    return s._result("NOT ENOUGH INFO", rel, "Wikidata's classification neither confirms nor rules this out.", entity, direct)


def _check_superlative(m: Measure) -> dict:
    props, sign = _MEASURES[m.stem]
    subject = s._resolve(m.subject, lambda e: any(value(e, p) is not None for p in props))
    cls = s._resolve(re.sub(r"s$", "", m.noun) if m.noun.lower().endswith("s") and not m.noun.lower().endswith("ss") else m.noun)
    if not subject or not cls:
        return s._result("NOT ENOUGH INFO", _rel(m, props[0]), f"Could not identify “{m.subject}” or the class “{m.noun}” in Wikidata.")
    context_id = None
    if m.context and s._norm(m.context) not in _WHOLE_WORLD:
        ctx = s._resolve(m.context)
        if not ctx:
            return s._result("NOT ENOUGH INFO", _rel(m, props[0]), f"Could not identify “{m.context}” in Wikidata.", subject)
        context_id = ctx["id"]
    ids, complete = _class_members(cls["id"])
    members = _fetch([i for i in ids if i != subject["id"]])
    implicit = False
    if context_id:
        members = _in_context(members, context_id)
    elif not m.context:
        # "Jupiter is the largest planet" means among its neighbours, not every exoplanet on record.
        # Such a restricted set can disprove the claim but never prove it.
        links = {v for p in _CONTEXT_PROPS for v in s._values(subject, p)}
        if links:
            implicit = True
            members = {i: e for i, e in members.items() if links & {v for p in _CONTEXT_PROPS for v in s._values(e, p)}}
    # Compare on the first measurement that the subject and at least half of the class both record.
    usable = [p for p in props if value(subject, p) is not None]
    prop = next((p for p in usable if sum(value(e, p) is not None for e in members.values()) * 2 >= max(1, len(members))),
                usable[0])
    rel = _rel(m, prop)
    mine = value(subject, prop)
    scored = {i: value(e, prop) for i, e in members.items()}
    known = {i: v for i, v in scored.items() if v is not None}
    shown = [f"{s._label(subject)}: {_fmt(mine, prop)}"]
    beat = [i for i, v in known.items() if (v - mine) * sign > 0]
    rank = m.extra.get("rank", 1)
    if rank > 1:
        return _check_rank(m, rel, subject, cls, members, known, scored, beat, rank, complete and not implicit, shown, prop)
    if beat:
        best = max(beat, key=lambda i: known[i] * sign)
        shown.append(f"{s._label(members[best])}: {_fmt(known[best], prop)}")
        return s._result(_verdict(False, m), rel,
                         f"Wikidata records a {_MORE[m.stem]} {s._PROP_NAMES.get(prop, 'value')} for "
                         f"{s._label(members[best])} ({_fmt(known[best], prop)}) than for {s._label(subject)} "
                         f"({_fmt(mine, prop)}).", subject, shown)
    is_member = cls["id"] in s._values(subject, "P31") or any(
        cls["id"] in s._values(e, "P279") for e in s._get(s._values(subject, "P31")).values())
    if is_member and complete and not implicit and known and len(known) == len(scored):
        return s._result(_verdict(True, m), rel,
                         f"Of the {len(known) + 1} items Wikidata lists as {s._label(cls)} here, {s._label(subject)} "
                         f"has the {_MOST[m.stem]} {s._PROP_NAMES.get(prop, 'value')} ({_fmt(mine, prop)}).", subject, shown)
    return s._result("NOT ENOUGH INFO", rel, "No counterexample was found, but the comparison set is incomplete.", subject, shown)


def _check_rank(m, rel, subject, cls, members, known, scored, beat, rank, complete, shown, prop) -> dict:
    """The subject is n-th when exactly n-1 members beat it. More than n-1 already disproves it."""
    ordered = sorted(beat, key=lambda i: known[i], reverse=_MEASURES[m.stem][1] > 0)
    shown += [f"{s._label(members[i])}: {_fmt(known[i], prop)}" for i in ordered[:4]]
    if len(beat) >= rank:
        return s._result(_verdict(False, m), rel,
                         f"Wikidata ranks at least {len(beat)} other {s._label(cls)} items ahead of {s._label(subject)} "
                         f"by {s._PROP_NAMES.get(prop, 'value')}, so it is not number {rank}.", subject, shown)
    if complete and len(known) == len(scored) and len(beat) == rank - 1:
        ahead = ", ".join(s._label(members[i]) for i in ordered)
        return s._result(_verdict(True, m), rel,
                         f"By {s._PROP_NAMES.get(prop, 'value')}, Wikidata ranks only {ahead} ahead of {s._label(subject)}.",
                         subject, shown)
    return s._result("NOT ENOUGH INFO", rel, "The comparison set is incomplete, so the rank can't be confirmed.", subject, shown)


def _check_comparative(m: Measure) -> dict:
    props, sign = _MEASURES[m.stem]
    if m.inverse:
        sign = -sign
    has_any = lambda e: any(value(e, p) is not None for p in props)  # noqa: E731
    a, b = s._resolve(m.subject, has_any), s._resolve(m.other, has_any)
    if not a or not b:
        return s._result("NOT ENOUGH INFO", _rel(m, props[0]), f"Could not identify “{m.subject}” and “{m.other}” with comparable records.")
    prop = next((p for p in props if value(a, p) is not None and value(b, p) is not None), None)
    if prop is None:
        return s._result("NOT ENOUGH INFO", _rel(m, props[0]), "Wikidata has no common measurement for both.", a)
    rel = _rel(m, prop)
    if prop == "P2233" and m.context:
        ctx = s._resolve(m.context)
        if not ctx or not all(ctx["id"] in s._values(e, "P397") for e in (a, b)):
            return s._result("NOT ENOUGH INFO", rel, f"Both are not recorded as orbiting {m.context}.", a)
    va, vb = value(a, prop), value(b, prop)
    shown = [f"{s._label(a)}: {_fmt(va, prop)}", f"{s._label(b)}: {_fmt(vb, prop)}"]
    if abs(va - vb) <= 0.01 * max(abs(va), abs(vb)):
        return s._result("NOT ENOUGH INFO", rel, "The recorded values are too close to call.", a, shown)
    truth = (va - vb) * sign > 0
    return s._result(_verdict(truth, m), rel, f"Wikidata records {'; '.join(shown)}.", a, shown)


def _check_orbit(m: Measure) -> dict:
    rel = _rel(m, "P397")
    a = s._resolve(m.subject)
    b = s._resolve(m.other)
    if not a or not b:
        return s._result("NOT ENOUGH INFO", rel, f"Could not identify “{m.subject}” or “{m.other}” in Wikidata.")
    parents = s._values(a, "P397")
    names = [s._label(e) for e in s._get(parents).values()]
    if b["id"] in parents:
        return s._result(_verdict(True, m), rel, f"Wikidata records that {s._label(a)} orbits {', '.join(names)}.", a, names)
    if a["id"] in s._values(b, "P397"):
        return s._result(_verdict(False, m), rel, f"Wikidata records the reverse: {s._label(b)} orbits {s._label(a)}.", b, [s._label(a)])
    return s._result("NOT ENOUGH INFO", rel, "Wikidata does not link the two bodies by an orbit.", a, names)


def _check_discovery(m: Measure) -> dict:
    rel = _rel(m, "P61")
    thing = s._resolve(m.other, lambda e: bool(e.get("claims", {}).get("P61")))
    if not thing:
        return s._result("NOT ENOUGH INFO", rel, f"Wikidata names no discoverer or inventor for “{m.other}”.")
    ents = s._get(s._values(thing, "P61"))
    names = [s._label(e) for e in ents.values()]
    target = s._norm(m.subject)
    matched = any(target in s._names(e) or target == s._norm(s._label(e)).split()[-1] for e in ents.values())
    if not matched and len(ents) != 1:
        return s._result("NOT ENOUGH INFO", rel, "Several people are credited; absence can't be proven.", thing, names)
    return s._result(_verdict(matched, m), rel,
                     f"Wikidata credits {', '.join(names)} with {s._label(thing)}.", thing, names)
