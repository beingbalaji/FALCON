# FALCON — Claim Review Lab

**[Open the interactive demo](https://beingbalaji.github.io/FALCON/)** · [Balaji R's profile](https://github.com/beingbalaji)

A working reconstruction of **Federated Analysis and Linguistic Correlation Network**, a research concept for early review of misinformation trends. This version offers a transparent, self-contained review workflow: paste text, inspect explainable linguistic signals, check a topic overview, search published fact checks, record manual verification steps, and export local summary data.

> **Research prototype:** Every claim remains **Unverified**. The app reports matched writing cues and does not predict truth, assign a fake-news probability, or claim a completed fact check. Neutral prose can contain a false statement; sensational prose can contain a true one. Do not use the output to label people, news outlets, or health claims as factual or false.

## Run it

Requires **Node.js 18+** for the optional local server. No package installation, account, token, database, or internet connection is required.

```bash
node server.js
# Open http://127.0.0.1:3000
```

Alternatively, open `index.html` directly in a modern browser. The same static app works on GitHub Pages. The text analysis runs in the browser; the optional local API is available at `POST /api/analyze`.

```bash
curl -s http://127.0.0.1:3000/api/analyze \
  -H 'Content-Type: application/json' \
  -d '{"text":"BREAKING!!! You will not believe this shocking secret truth. Share this now before it is deleted!"}'
```

The API returns `success`, `analysis.verificationStatus` (`Unverified`), `analysis.factualVerdict` (`null`), `analysis.cueCount`, `analysis.topic`, `analysis.signals`, `analysis.metrics`, and a `disclaimer`. Earlier `reviewScore` and `priority` fields were removed because they were easy to mistake for factual predictions. `GET /health` reports local server status. The local server processes text in memory and does not persist or log it.

## Features

- **Explainable writing cues:** displays matched phrases and why they warrant a closer look, with a prominent Unverified status.
- **Evidence lookup:** links to Google Fact Check Explorer for a manual search. A matching article must be checked against the exact claim, date, and original source; no match proves nothing.
- **Topic view:** groups analyzed items into Health, Politics, Finance, Technology, Climate, or General using a small keyword list.
- **Verification checklist:** prompts source, primary-evidence, and independent-corroboration checks; ticking boxes does not automatically verify a claim.
- **Local dashboard:** stores the latest 40 *summaries* (topic, writing-cue count, word count, time) in this browser's local storage. It does **not** store submitted text. Older summaries migrate without their misleading score labels.
- **JSON export and clear:** export or remove the browser's saved summaries.
- **No frontend API key:** the supplied HTML prototype called a third-party model from the browser with a `YOUR_HF_API_TOKEN` placeholder. This reconstruction removes that broken and insecure dependency.

## Method and limitations

The rules in `analysis.js` match a limited set of language cues and count the types matched. They cannot understand satire, context, quotations, bias, a cited study, or whether a claim is correct. In particular, a statement and its negation can have identical writing-cue reports. Topic labels are keyword-based. The app does not automatically query fact-check databases or public feeds. An explicit link opens Fact Check Explorer for a manual evidence search; submitted text is not sent there automatically.

The original research write-up describes fine-tuned BERT, Google Fact Check integration, knowledge graphs, social-stream collection, and federated training. The provided materials contained **no trained model weights, datasets, integration credentials, operational client nodes, or runnable backend source**. A separate backend guide described desired Express, MongoDB, Redis, WebSocket, and federated modules but supplied architecture and snippets rather than those source files. The write-up includes evaluation percentages, but no reproducible dataset or evaluation procedure was supplied; this repository does **not** claim or reproduce those results.

To turn this into a validated classifier, the next steps are to obtain appropriately licensed labeled data, train and evaluate a documented model on a held-out set, add a server-side fact-check integration with proper secrets management, assess error rates and bias, then implement federated training only if real participating nodes and a privacy protocol exist. Those are future research tasks, not current features.

## Project layout

| File | Purpose |
| --- | --- |
| `index.html` | Accessible interface and research notes |
| `style.css` | Responsive design |
| `app.js` | Browser interaction, dashboard, local export |
| `analysis.js` | Shared deterministic signal analysis |
| `server.js` | Optional local HTTP API and file server |
| `tests.js` | API and analysis checks |
| `package.json` | Dependency-free start/test commands |

Run `npm test` (or `node --test tests.js`) to check the analysis and local API.

## Reconstruction provenance

Rebuilt in 2026 from three materials supplied by Balaji R: a FALCON research write-up (`.docx`), a backend implementation guide (`.md`), and a single-file HTML prototype. This is a reconstructed proof of concept, not a recovery of the lost original source. The documents are not republished here; this repository includes newly written implementation code and an explicit record of supported features and gaps.

Copyright © 2026 Balaji R. All rights reserved until a license is chosen.
