# FALCON — Evidence & Claim Review Lab

**[Open the interactive demo](https://beingbalaji.github.io/FALCON/)** · [Balaji R](https://github.com/beingbalaji)

FALCON reconstructs the **Federated Analysis and Linguistic Correlation Network** research concept. It now retrieves evidence and runs a real pretrained natural-language inference model in the browser. Paste one English claim, inspect source passages, and see whether the model finds support, contradiction, a conflict, or insufficient evidence.

> **Research beta:** Results describe a model's comparison with the retrieved text. They are not guaranteed truth verdicts. Retrieval can miss important context, sources can be outdated or incorrect, and the model can make mistakes. End-to-end results on 3,332 public benchmark claims are reported below; they describe this prototype, not a guarantee for any particular claim.

## Use it

1. Open the demo in a modern desktop browser.
2. Enter one short English claim (10–350 characters).
3. Choose live structured-fact / Wikipedia retrieval or supply a passage and its HTTPS source URL.
4. Select **Check evidence**. The first run downloads about 90 MB of model files and may take a few minutes. Later runs reuse browser caches.
5. Read the cited passages and dates. For a contradiction, the report surfaces what the source says rather than inventing a replacement answer.

The public app requires no account or API key. Internet access is required for source retrieval and the initial model download. Memory, browser, network, and device limitations can prevent inference; failure is reported without a factual verdict. Use **Cancel check** to stop a download or inference.

## What is implemented

- **Structured factual checks:** explicitly phrased “X is [not] the capital / prime minister / head of government of Y” claims resolve entity IDs and compare current Wikidata statements. The checker filters dates, ranks, and qualifiers; ambiguous names, missing records, and unsupported contexts remain unresolved. No facts or names are hard-coded.
- **Actual pretrained model:** DeBERTa v3 xsmall NLI, trained upstream on SNLI and MultiNLI, running with Transformers.js and ONNX in a web worker.
- **Live retrieval:** up to four Wikipedia article introductions, with revision URLs, update times, retrieval times, and publisher labels.
- **Your own source:** compare a primary-source passage you paste with a claim. The app cannot authenticate pasted text or its claimed origin.
- **Conservative source decisions:** require a 0.90 model relationship score and a margin of 0.35. Opposing strong evidence produces a conflict. Weak/missing evidence produces an insufficient-evidence result. Thresholds are design choices, not validated accuracy guarantees.
- **Traceable correction:** a contradicted claim displays the exact retrieved passage as the source's account, with citation.
- **Inspectable results:** source text, model relationship scores, and downloadable JSON.
- **Writing-cue review:** the earlier local rules remain available separately, with no truth score.
- **Diagnostic checks:** nine hand-written evidence/claim pairs can be run against the actual model. These are a smoke check, not a representative evaluation benchmark.

## Run locally

Requires Node.js 18+ for the optional server. No npm package installation is needed for the server itself.

```bash
npm start
# Open http://127.0.0.1:3000
npm test
```

Use HTTP (GitHub Pages or the local server), because model inference uses a module web worker. Opening `index.html` as a local file is not supported for the evidence feature.

`POST /api/analyze` remains the writing-cue API only. It does not run the evidence model. `GET /health` reports server status. Evidence inference runs in the browser.

## Privacy and external services

Selecting live evidence search sends entity names to **Wikidata** for supported structured relations, or claim keywords and page requests to **English Wikipedia** otherwise. Model assets are downloaded from **Hugging Face** and **jsDelivr**; the model compares text locally. These services receive normal request metadata such as IP address. Do not use public search with private claims.

Evidence reports stay in memory until you explicitly export them. The separate writing-cue dashboard stores only topic, cue count, word count, and time locally. It does not store submitted text. No third-party model API key is embedded in the frontend.

## Evaluation

### Large-scale test: 3,332 claims from three public datasets (11 October 2026)

The deployed pipeline (structured check, then Wikipedia retrieval, passage ranking, DeBERTa NLI and the decision rule) was run unchanged on claims from three public fact-checking datasets with very different content:

| Dataset | Claims | Content | Accuracy | Macro F1 |
|---|---|---|---|---|
| [FEVER](https://fever.ai/) (dev, balanced sample) | 1,500 | General knowledge from Wikipedia: people, films, sport, history, places, science | **47.5%** | 0.49 |
| Climate-FEVER | 1,379 | Real claims about climate change collected online | 36.9% | 0.27 |
| AVeriTeC (dev) | 453 | Real-world claims from news and social media checked by professional fact-checkers | 13.9% | 0.11 |
| **All** | **3,332** | | **38.5%** | **0.36** |

Always answering "not enough info" would score 30.3% on the same claims, and random guessing among the three labels would score 33.3%. Two claims outside the app's 10–350 character input limit were excluded.

**What this shows**

- **Retrieval is the main bottleneck.** For 51% of claims (1,707), no Wikipedia passage passed the relevance filter, so the system could only answer "insufficient evidence". When evidence *was* found for a FEVER claim that has a true or false answer, accuracy rose to 54.5%.
- **"Supported" verdicts are reliable; "Contradicted" verdicts are not yet.** When FALCON says *Supported*, it is right **81.6%** of the time. *Contradicted* is right only 49.9% of the time, because the NLI model treats passages about related but different entities as contradictions. This is the same failure seen with the Eiffel Tower replicas.
- **FALCON is cautious.** It gave a definite verdict on only 841 claims (25%) and recalled 78% of genuinely unverifiable claims, but it misses many true claims (recall 15.7% for *Supported*).
- **The content gap is large.** FEVER claims were written from Wikipedia, so FALCON does best there. Climate claims and real-world news claims usually need evidence from scientific reports, news articles or official statements, which a search of Wikipedia article introductions rarely finds. AVeriTeC in particular is designed for open-web retrieval.

For context, the original FEVER baseline (Thorne et al., 2018), which used a full Wikipedia dump and a model trained on FEVER, reported label accuracy of roughly 50%. FALCON reaches 47.5% on FEVER with live API retrieval and an off-the-shelf NLI model that was never trained on FEVER, running in a browser.

Files: [`evaluation/large/results.csv`](evaluation/large/results.csv) (every claim with gold label, prediction and top source), [`evaluation/large/summary.json`](evaluation/large/summary.json) (all metrics and confusion matrices) and [`evaluation/large/run-large-eval.js`](evaluation/large/run-large-eval.js) (paste into the browser console on the demo to reproduce). Live Wikipedia content changes over time, so a rerun can differ slightly.

**Priorities suggested by these results:** better retrieval (full article text instead of introductions, query rewriting, more than four pages, sources beyond Wikipedia), entity checks before a passage may count as contradicting, and fine-tuning or calibrating the NLI decision on FEVER-style evidence pairs.

### Small hand-written smoke test (60 claims)

[`evaluation/falcon_eval.csv`](evaluation/falcon_eval.csv) contains 60 simple, well-known claims (20 true, 20 false, 20 undocumented). FALCON scored 73.3% on them (44/60) and correctly abstained on all 20 undocumented claims. These claims are much easier than the public datasets above, so this figure should not be read as general accuracy. Per-claim results: [`evaluation/results_2026-10-11.csv`](evaluation/results_2026-10-11.csv); script: [`evaluation/run-eval.js`](evaluation/run-eval.js).

### Dataset credits

FEVER (Thorne et al., NAACL 2018; CC BY-SA 3.0), Climate-FEVER (Diggelmann et al., 2020) and AVeriTeC (Schlichtkrull et al., NeurIPS 2023; CC BY-NC 4.0). Claims and labels are reproduced in `evaluation/large/results.csv` for research evaluation only, under each dataset's license.

## Method and limitations

Structured matching supports a deliberately narrow English grammar and does not use the NLI model to override missing or ambiguous records. A different recorded entity yields contradiction only for one referenced current value (and preferred rank for an officeholder). Multiple values can support an exact match but cannot establish absence. Wikidata and Wikipedia are related community-maintained sources, not independent corroboration.

Search terms omit negation so a false statement is not forced to retrieve only similarly worded content. Candidate passages retain neighbouring sentences. A lexical relevance filter picks at most six passages; the pinned NLI model compares each passage (premise) with the claim (hypothesis). Its three output labels are contradiction, entailment, and neutral. A guard checks label mapping before inference.

Wikipedia is one publisher, even if multiple pages agree. This is not independent corroboration or an authoritative primary-source search engine. The retrieval scope is limited to English article introductions and can miss evidence elsewhere. A model may overread a passage, confuse names or quantities, mishandle negation, or infer something the source never establishes. Dates describe article revisions and retrieval, not necessarily when the underlying fact was last verified. For current office holders, breaking news, health, finance, or legal claims, inspect current primary sources before relying on an output.

FALCON does not yet implement multilingual validation, a licensed multi-publisher search backend, fact-check API integration, a public claim benchmark, calibrated confidence, original FALCON model training, or federated training. No system can detect every false claim.

In live testing on 28 September 2026, the model passed 9/9 simple diagnostic pairs but misread state-capital passages as supporting a national-capital claim. This is a documented failure, not hidden by the diagnostic score; supported capital claims now use structured records. See `live-model-observation.txt` for the original UI observation.

See [MODEL_CARD.md](MODEL_CARD.md) for model provenance, evaluation status, and the requirements for further training.

## Files

| File | Role |
|---|---|
| `index.html`, `style.css` | Responsive interface |
| `evidence-core.js` | Claim validation, relevance, score conversion, evidence decisions |
| `structured-facts.js` | Entity resolution, date/rank filtering, explicit relation comparison |
| `evidence-sources.js` | Wikipedia API adapter and revision citations |
| `evidence-worker.js` | Pinned pretrained model inference |
| `evidence-ui.js` | Search, worker lifecycle, cancellation, reports, diagnostics |
| `diagnostics.json` | Fixed hand-written model smoke checks |
| `analysis.js`, `app.js` | Separate writing-cue analysis and local summary dashboard |
| `server.js` | Optional static server and writing-cue API |
| `tests.js` | API, evidence decision, failure, conflict, and retrieval adapter checks |
| `evaluation/` | Benchmark results (3,332 claims), the 60-claim smoke test, and evaluation scripts |

## Reconstruction provenance

Rebuilt in 2026 from three files supplied by Balaji R: a FALCON research write-up, a backend guide, and an HTML prototype. The lost original source, model weights, datasets, and reproducible evaluations were not provided. This repository contains a new implementation, not recovered original code. The supplied documents are not republished here.

Copyright © 2026 Balaji R. All rights reserved for original project code until a license is chosen. External models, libraries, and retrieved text retain their respective licenses and attribution requirements.
