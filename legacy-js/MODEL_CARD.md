# FALCON model and evaluation record

## Model in use

- Upstream: [cross-encoder/nli-deberta-v3-xsmall](https://huggingface.co/cross-encoder/nli-deberta-v3-xsmall).
- Browser conversion: [Xenova/nli-deberta-v3-xsmall](https://huggingface.co/Xenova/nli-deberta-v3-xsmall).
- Pinned revision: `2a4f614a701367a02d51389039afc998faeda637`.
- Runtime: Transformers.js 3.8.1; ONNX WASM; quantized q8 model; one worker thread.
- Upstream training datasets: SNLI and MultiNLI. This is supervised sentence-pair inference, not a database of verified current facts.
- Label order: contradiction, entailment, neutral; verified at runtime against the model configuration.
- Upstream license: Apache 2.0. Model files are loaded from their publisher, not committed to this repository. See the upstream model card and conversion repository for applicable terms.

No new FALCON-specific weights have been trained. The application reuses an existing trained model. Changing labels, rules, or source retrieval does not constitute model training.

## Evaluation status

Eight local software tests cover writing-cue behavior, validation, HTTP handling, fail-closed evidence decisions, conflicting sources, relevance, and citation metadata. These tests use controlled inputs and mocked source responses; they do not measure live factual accuracy.

`diagnostics.json` contains nine small hand-written sentence pairs for support, negation, wrong entities/dates, and missing information. Run **Model details and diagnostic checks → Run model diagnostics** in the app to execute the real model. The result can be exported. This fixed set is not a held-out research benchmark, and passing it is not a general accuracy estimate.

On 28 September 2026, the deployed model ran successfully and classified all 9 diagnostic pairs as expected. Live Wikipedia retrieval also worked. However, a live “Sydney is the capital of Australia” test incorrectly predicted support from state-capital passages and produced a conflict overall. This observed scope-confusion failure is preserved in `live-model-observation.txt`. Capital and head-of-government claims in the supported grammar now use a separate structured entity comparison rather than this model. Structured checks are being validated independently. Do not infer a percentage for FALCON from upstream SNLI/MultiNLI scores: those tasks and datasets differ from end-to-end retrieval and fact verification.

## What training from more sources requires

1. Obtain datasets with explicit reuse permissions and a record of publisher, URL, publication date, exact claim, evidence, and label. Plain scraped text is not a ground-truth label.
2. Define support, contradiction, and insufficient-evidence annotation rules; include ambiguous, changed, multi-claim, and missing-evidence cases. Preserve uncertainty and disagreements.
3. Deduplicate related claims and evidence before splitting. Hold out publishers, events, and a later time period to reduce leakage. Keep the final test set untouched during model and threshold selection.
4. Fine-tune the pretrained NLI model on evidence/claim pairs. Track model revision, random seed, dataset hashes, and training configuration. Use a validation set to tune abstention and calibration.
5. Evaluate retrieval separately from inference: evidence recall, source coverage, supported/contradicted/unknown precision and recall, macro F1, and error rate on cases where the model answers. Report abstention rate as well as accuracy.
6. Audit false positives, outdated evidence, entity confusion, negation, numbers, and source conflicts. Compare with the unchanged pretrained baseline and publish both improvements and regressions.
7. Export a tested ONNX model, check the label mapping and browser behavior, and pin the model revision before replacing production assets.

A licensed multi-publisher retrieval backend and a documented evaluation corpus are the next requirements for stronger factual coverage. Training cannot guarantee universal correctness or replace current evidence.
