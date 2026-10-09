# FALXON: Verifying factual claims with structured records and evidence-grounded inference

**Balaji R** · Technical report · October 2026 · Code: `beingbalaji/FALCON` (branch `falxon-v5`)

## Abstract

FALXON is an open-source fact-checking system that runs on a laptop and costs nothing to operate. It labels a short factual claim *Supported*, *False* or *Unverified*, and shows the records and passages behind each verdict. Claims with a well-defined structure, such as capitals, locations, sizes, rankings, orbits and authorship, are checked directly against Wikidata. All other claims are checked by retrieving Wikipedia passages, reranking them with a cross-encoder, and reading them with a DeBERTa-v3 natural-language-inference (NLI) model. A conservative decision rule abstains when the evidence is weak. On 60 hand-written claims (20 per label), accuracy rose from 78.3% with NLI alone to 91.7% with record checks (macro F1 91.5%). When FALXON gave a True or False verdict, it was right 94.6% of the time, and it left all 20 unverifiable claims unverified.

## 1. Problem

Off-the-shelf NLI models are good at judging whether one sentence follows from another. Fact-checking needs more than that:

1. **Retrieval.** The right evidence has to be found first.
2. **Closed-world facts.** "Sydney is the capital of Australia" is false, but no Wikipedia sentence says "Sydney is not the capital". A passage saying Sydney is *a* capital, of New South Wales, often fools NLI into agreeing.
3. **Comparisons and counts.** "Mars is the largest planet" is false because another planet is larger. That is a set-level fact that no single sentence states.
4. **Unverifiable detail.** "Canberra was chosen because a politician won a coin toss" should be *Unverified*, not *False*. Related passages tell a different story, but they do not rule this one out.

The earlier FALCON v2 system used TF-IDF and logistic regression on the LIAR dataset. It reached 26.3% six-way accuracy (62.0% on true vs. false), which showed that style-based classification does not verify facts.

## 2. System

```
claim → record check (Wikidata) ──decisive──▶ verdict + citation
          │ not applicable / abstains
          ▼
        Wikipedia retrieval → cross-encoder rerank → NLI on top passages → decision rule → verdict + evidence
```

### 2.1 Record checks (Wikidata)

A small grammar recognizes common claim shapes and compares Wikidata entity IDs and measurements, not strings:

| Shape | Example | Wikidata used |
|---|---|---|
| Capital, head of state or government | Sydney is the capital of Australia | P36, P35, P6, current statements only |
| Author, discoverer | Shakespeare developed the theory of relativity | P50, P61, P170, P178, and the parts of the thing (P527) |
| Founding and birth year | The UN was founded in 1800 | P571, P569 |
| Location | The Eiffel Tower is in London | Current admin-territory, country and continent chain (P131, P17, P30) |
| Superlative, rank, comparison | Venus is the second planet from the Sun | Class members within the context, compared by radius, area, distance or population |
| Orbit | The Sun revolves around the Earth | P397 |
| Type, nickname | The Moon is a planet | P31/P279 closure; mutually exclusive kinds of body |

Design rules learned from errors:

- **Prominence.** A name is resolved to the matching entity covered by the most Wikipedia editions, so the famous Mount Everest wins over a hill of the same name.
- **Asymmetric proof.** One recorded counterexample is enough to call a superlative false. Calling one true requires the whole comparison set, and the report states why when the set is incomplete.
- **Current facts only.** Ended historical links, such as a province briefly under the Empire of Japan, and geology links, such as a mountain range on a tectonic plate, do not count as "is in".
- **Abstention.** Ambiguity, missing records and network errors give *Unverified* and fall through to text evidence, never a guess.

### 2.2 Text evidence

1. **Retrieval.** Queries come from the subject phrase, named entities and the claim with negations removed. Up to 6 Wikipedia articles are fetched at pinned revisions and split into sentences and two-sentence windows.
2. **Reranking.** `cross-encoder/ms-marco-MiniLM-L-6-v2` keeps the best 8 passages, at most 3 per article.
3. **Inference.** `MoritzLaurer/DeBERTa-v3-base-mnli-fever-anli` scores the top 5 passages.
4. **Decision.** A passage counts only if one label is strong (≥ 0.80) and well ahead of the others (margin ≥ 0.30). Opposing strong passages give *Disputed*. Thresholds are tuned on a FEVER calibration split, never on test data. Two guards target known NLI failures:
   - **Detail coverage.** A refutation of a long, detailed claim must come from a passage that mentions most of its specific terms.
   - **Count agreement.** "Two chambers" is refuted by a relevant "four chambers". A passage about something narrower, such as "the left heart", cannot confirm it.

### 2.3 Application

The FastAPI web app has a newspaper-style interface, permanent report pages with citations to exact revisions, article checking (up to 6 check-worthy sentences per article), a JSON API, rate limiting and SSRF-safe URL fetching. Everything runs on CPU with free models and public APIs. A Dockerfile targets the free Hugging Face Spaces tier.

## 3. Evaluation

### 3.1 FALCON-60

These are 60 general-knowledge claims written for the project: 20 true, 20 false and 20 plausible-but-unverifiable. Each run re-checks every claim from scratch (`python -m evaluation.bench falcon60`).

| Version | What changed | Accuracy | Macro F1 |
|---|---|---|---|
| v5.0 | NLI pipeline with capital, author and year records | 78.3% | 78.7% |
| v5.1 | + location, comparison, orbit and type records | 80.0% | 80.1% |
| v5.3 | + name prominence, context-aware comparison sets, detail-coverage and count guards | **91.7%** | **91.5%** |

Confusion matrix for v5.3 (rows are the truth):

| | Supported | False | Unverified |
|---|---|---|---|
| **True** | 19 | 0 | 1 |
| **False** | 2 | 16 | 2 |
| **Unverifiable** | 0 | 0 | 20 |

The five v5.3 errors were traced with `python -m evaluation.bench why` to four causes:
- Historical and geological links counted as location (2 claims).
- A truncated list of planet types that blocked a complete comparison (1 claim).
- A part-of-heart passage outweighing the whole-heart passage (1 claim).
- A crash on an unlabeled Wikidata entity (1 claim).

All four are fixed in v5.4. That version has not been re-measured yet.

### 3.2 FEVER 1.0

`python -m evaluation.bench all --n 600` draws a balanced 600-claim sample of the FEVER shared-task dev set. It uses 200 claims to tune thresholds and scores the other 400. *Results pending; they will be reported here and on the app's Methodology page.* For context, published label accuracy with retrieval ranges from about 68% (2018 shared-task winner) to about 80% (later BERT-era systems). Those systems trained retrieval on FEVER; FALXON does not.

## 4. Limitations

- **Small test set.** FALCON-60 is small and was written by the author. It shows behavior on common claim types, not general accuracy. FEVER is the independent benchmark.
- **Scope.** Only English Wikipedia and Wikidata are used. Breaking news, local events and private individuals are mostly out of reach.
- **One publisher.** Agreement between Wikipedia pages is not independent corroboration.
- **Record quality.** Wikidata can be incomplete or wrong. Every record verdict links the exact revision used.
- **Hand-built grammar.** The record checks cover common shapes only; other phrasings fall back to text evidence.
- **Confidence.** The "model confidence" shown is the NLI probability of the decisive passage, not a calibrated probability that the claim is true.

## 5. Reproducing

```
pip install -r requirements-dev.txt
pytest -q                                   # 87 offline tests, no network or models
python -m evaluation.bench doctor           # connectivity + 8 record checks with known answers
python -m evaluation.bench falcon60         # FALCON-60, about 5 minutes on a laptop CPU
python -m evaluation.bench why              # explains each miss
python -m evaluation.bench all --n 600      # FEVER, 1–2 hours
uvicorn web.app:app --port 8000             # the web app
```

## References

Thorne et al. (2018), FEVER, NAACL. He et al. (2021), DeBERTaV3. Nie et al. (2020), Adversarial NLI, ACL. Reimers & Gurevych (2019), Sentence-BERT. Vrandečić & Krötzsch (2014), Wikidata, CACM. Wang (2017), LIAR, ACL.
