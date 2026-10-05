import pytest

from falxon import pipeline, structured
from falxon.aggregate import CONFLICTING, NEI, REFUTED, SUPPORTED, decide
from falxon.claims import ClaimError, checkworthiness, extract_claims, split_sentences, validate_claim
from falxon.config import DEFAULT_THRESHOLDS
from falxon.retrieval import wikipedia


def test_validate_claim_normalises_and_rejects_bad_input():
    assert validate_claim('  "The Moon orbits Earth"  ') == "The Moon orbits Earth."
    with pytest.raises(ClaimError):
        validate_claim("hi")
    with pytest.raises(ClaimError):
        validate_claim("Is the Moon a planet?")
    with pytest.raises(ClaimError):
        validate_claim("x" * 1000)


def test_sentence_split_keeps_abbreviations():
    parts = split_sentences("Dr. Smith went to Washington. He arrived in 1999. The U.S. economy grew.")
    assert parts == ["Dr. Smith went to Washington.", "He arrived in 1999.", "The U.S. economy grew."]


def test_checkworthiness_prefers_facts_over_opinions():
    assert checkworthiness("The company reported revenue of 4 billion dollars in 2023.") >= 0.5
    assert checkworthiness("I think this is the best movie ever made.") < 0.5
    text = "What a day! I think it is beautiful. Apple was founded in 1976 by Steve Jobs. Prices rose 7% in March."
    assert extract_claims(text) == ["Apple was founded in 1976 by Steve Jobs.", "Prices rose 7% in March."]


def test_entity_spans_and_queries():
    claim = "The Eiffel Tower is located in London."
    assert wikipedia.entity_spans(claim) == ["Eiffel Tower", "London"]
    assert wikipedia.subject_phrase(claim) == "Eiffel Tower"
    assert wikipedia.search_queries("Paris is not in France.")[-1] == "Paris is in France"


def test_rank_titles_demotes_unmentioned_disambiguations():
    titles = wikipedia.rank_titles("The Eiffel Tower is in Paris.", ["Eiffel Tower"],
                                   [["Eiffel Tower (Paris, Texas)", "Eiffel Tower"]])
    assert titles[0] == "Eiffel Tower"


def test_structured_parse():
    r = structured.parse("Sydney is the capital of Australia.")
    assert (r.kind, r.subject, r.holder, r.negated) == ("capital", "Sydney", "Australia", False)
    assert structured.parse("Sydney is not the capital of Australia.").negated
    assert structured.parse("William Shakespeare wrote Hamlet.").kind == "author"
    assert structured.parse("Albert Einstein was born in 1879.").year == 1879
    assert structured.parse("Paris is big and Rome is old.") is None
    assert structured.parse("The Moon is made of cheese.") is None


@pytest.mark.parametrize("claim,label", [
    ("Sydney is the capital of Australia.", REFUTED),
    ("Canberra is the capital of Australia.", SUPPORTED),
    ("Sydney is not the capital of Australia.", SUPPORTED),
    ("William Shakespeare wrote Hamlet.", SUPPORTED),
    ("Albert Einstein wrote Hamlet.", REFUTED),
    ("Albert Einstein was born in 1879.", SUPPORTED),
    ("Albert Einstein was born in 1900.", REFUTED),
])
def test_structured_verdicts(claim, label):
    assert structured.check(claim)["label"] == label


def test_structured_unknown_entity_abstains():
    assert structured.check("Atlantis is the capital of Narnia.")["label"] == NEI


def test_pipeline_text_evidence_supports_and_refutes():
    ok = pipeline.verify("The Eiffel Tower is located in Paris.")
    assert ok["verdict"]["label"] == SUPPORTED
    assert any(e["decisive"] and "Champ de Mars" in e["text"] for e in ok["evidence"])
    assert ok["sources"][0]["title"] == "Eiffel Tower"

    bad = pipeline.verify("The Eiffel Tower is located in London.")
    assert bad["verdict"]["label"] == REFUTED


def test_pipeline_abstains_without_evidence():
    r = pipeline.verify("Zorblax quintuplets enjoy purple weather.")
    assert r["verdict"]["label"] == NEI


def test_decide_rules():
    t = dict(DEFAULT_THRESHOLDS)
    strong_s = {"id": 0, "relevance": 5, "nli": {"entailment": .95, "neutral": .04, "contradiction": .01}}
    strong_r = {"id": 1, "relevance": 5, "nli": {"entailment": .01, "neutral": .04, "contradiction": .95}}
    weak = {"id": 2, "relevance": 5, "nli": {"entailment": .5, "neutral": .4, "contradiction": .1}}
    irrelevant = {"id": 3, "relevance": -9, "nli": {"entailment": .99, "neutral": 0, "contradiction": .01}}
    assert decide([strong_s, weak], t)["label"] == SUPPORTED
    assert decide([strong_r], t)["label"] == REFUTED
    assert decide([strong_s, strong_r], t)["label"] == CONFLICTING
    assert decide([weak], t)["label"] == NEI
    assert decide([irrelevant], t)["label"] == NEI
    assert decide([], t)["label"] == NEI
