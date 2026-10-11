# FALCON — Evidence & Claim Review Lab

**[Open the interactive demo](https://beingbalaji.github.io/FALCON/)** · [Balaji R](https://github.com/beingbalaji)

FALCON reconstructs the **Federated Analysis and Linguistic Correlation Network** research concept. It now retrieves evidence and runs a real pretrained natural-language inference model in the browser. Paste one English claim, inspect source passages, and see whether the model finds support, contradiction, a conflict, or insufficient evidence.

> **Research beta:** Results describe a model's comparison with the retrieved text. They are not guaranteed truth verdicts. Retrieval can miss important context, sources can be outdated or incorrect, and the model can make mistakes. The end-to-end result below comes from a small hand-written test set and is not a general accuracy guarantee.

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

## Evaluation (11 October 2026)

The full live pipeline (structured check → Wikipedia retrieval → passage ranking → DeBERTa NLI → decision rule) was run on [`evaluation/falcon_eval.csv`](evaluation/falcon_eval.csv). The set has 60 hand-written claims: 20 true, 20 false, and 20 plausible-sounding but undocumented claims whose correct answer is *insufficient evidence*. The NLI model also passed the 9/9 diagnostic pairs in the same session.

| Metric | Result |
|---|---|
| **Overall accuracy (3 labels)** | **73.3%** (44 / 60) |
| Macro F1 | 0.78 |
| True claims → *Supported* | 10 / 20 |
| False claims → *Contradicted* | 14 / 20 |
| Undocumented claims → *Insufficient evidence* | **20 / 20** |
| Precision when the system gives a verdict (Supported or Contradicted) | **92.3%** (24 / 26) |
| *Conflicting evidence* outputs | 10 (all counted as wrong) |

Per-class results: Supported P = 1.00 / R = 0.50 · Contradicted P = 0.88 / R = 0.70 · Insufficient P = 0.83 / R = 1.00.

**What the errors show**

- **The system is cautious, not reckless.** It never called a false claim *Supported*. Only 2 of 60 claims got the opposite verdict: *"Jupiter is the largest planet"* and *"The Nile flows through Egypt"* were marked *Contradicted*. Most misses were *Conflicting evidence* instead.
- **Off-topic passages are the main source of conflicts.** For *"The Eiffel Tower is located in Paris, France"*, passages about the replicas in Paris, Texas and Paris, Tennessee were scored as contradicting. Similar off-topic passages came from *Taj Mahal Palace Hotel*, *Great Wall Marathon*, and *Mars (disambiguation)*. The model judges each passage correctly on its own terms, but the passage is about a different entity.
- **Some refutations are right for the wrong reason.** For example, *"The United Nations was founded in 1800"* was contradicted by a passage about the 1800 US presidential election. A correct label does not always mean the correct evidence was used.
- **The structured capital check returned *insufficient evidence* for both Canberra and Sydney** in this run, so the Wikidata path needs debugging.

Per-claim results: [`evaluation/results_2026-10-11.csv`](evaluation/results_2026-10-11.csv). To reproduce, open the demo, open the browser console, and paste [`evaluation/run-eval.js`](evaluation/run-eval.js). Live retrieval changes as Wikipedia pages change, so results can vary between runs.

**Next steps suggested by these results:** entity-aware filtering of passages (drop pages about a different entity with the same name), weighting passages by how relevant they are instead of letting any single strong passage create a conflict, and fixing the structured capital lookup.

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
| `evaluation/` | 60-claim test set, evaluation script, and per-claim results |

## Reconstruction provenance

Rebuilt in 2026 from three files supplied by Balaji R: a FALCON research write-up, a backend guide, and an HTML prototype. The lost original source, model weights, datasets, and reproducible evaluations were not provided. This repository contains a new implementation, not recovered original code. The supplied documents are not republished here.

Copyright © 2026 Balaji R. All rights reserved for original project code until a license is chosen. External models, libraries, and retrieved text retain their respective licenses and attribution requirements.
