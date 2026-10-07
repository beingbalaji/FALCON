"""FALXON benchmark: run the real pipeline on labelled claims, calibrate thresholds, report.

Usage (from the repository root):

    python -m evaluation.bench all --n 600          # download FEVER dev, run, calibrate, report
    python -m evaluation.bench run --n 600          # only collect pipeline outputs (resumable)
    python -m evaluation.bench calibrate            # tune thresholds on the calibration split
    python -m evaluation.bench report               # score the held-out split, write reports/
    python -m evaluation.bench falcon60             # quick re-check of the 60 FALCON claims (~5 min)

Protocol
- FEVER 1.0 shared-task dev set (Thorne et al., 2018), labels SUPPORTS / REFUTES / NOT ENOUGH INFO.
- A balanced random sample (fixed seed) is split 1/3 calibration, 2/3 test. Thresholds are
  tuned on calibration only; every headline number comes from the untouched test split.
- Raw per-claim model outputs are cached in evaluation/runs/, so re-scoring with new
  thresholds needs no network or model time, and runs can be resumed after interruption.
- Also scores the 60 hand-written claims from FALCON v4 (evaluation/data/falcon60.csv).
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from falxon import pipeline
from falxon.aggregate import LABELS, NEI, REFUTED, SUPPORTED, as_fever_label, decide
from falxon.config import DEFAULT_THRESHOLDS, ROOT, load_thresholds, settings

DATA = ROOT / "evaluation" / "data"
RUNS = ROOT / "evaluation" / "runs"
REPORTS = ROOT / "reports"
FEVER_URLS = [
    "https://fever.ai/download/fever/shared_task_dev.jsonl",
    "https://s3-eu-west-1.amazonaws.com/fever.public/shared_task_dev.jsonl",
]
FEVER_MAP = {"SUPPORTS": SUPPORTED, "REFUTES": REFUTED, "NOT ENOUGH INFO": NEI}
SEED = 13


# ---------------------------------------------------------------- data
def load_fever() -> list[dict]:
    path = DATA / "fever_dev.jsonl"
    if not path.exists():
        DATA.mkdir(parents=True, exist_ok=True)
        for url in FEVER_URLS:
            try:
                print(f"Downloading FEVER dev from {url} …")
                r = requests.get(url, timeout=120)
                r.raise_for_status()
                path.write_bytes(r.content)
                break
            except Exception as exc:  # try the mirror
                print(f"  failed: {exc}")
        else:
            sys.exit("Could not download FEVER. Download shared_task_dev.jsonl manually into evaluation/data/fever_dev.jsonl")
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            rows.append({"id": str(item["id"]), "claim": item["claim"], "label": FEVER_MAP[item["label"]]})
    return rows


def load_falcon60() -> list[dict]:
    with open(DATA / "falcon60.csv", newline="", encoding="utf-8") as f:
        return [{"id": f"f60-{i}", "claim": r["claim"], "label": r["label"].strip().upper()} for i, r in enumerate(csv.DictReader(f))]


def fever_sample(n: int) -> tuple[list[dict], list[dict]]:
    rows = load_fever()
    rng = random.Random(SEED)
    per = n // 3
    sample = []
    for label in LABELS:
        pool = [r for r in rows if r["label"] == label]
        sample += rng.sample(pool, min(per, len(pool)))
    rng.shuffle(sample)
    cut = len(sample) // 3
    return sample[:cut], sample[cut:]


# ---------------------------------------------------------------- running
def run(items: list[dict], name: str) -> list[dict]:
    """Run the pipeline on each item, caching raw outputs as JSON lines (resumable)."""
    RUNS.mkdir(parents=True, exist_ok=True)
    path = RUNS / f"{name}.jsonl"
    done = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            done[rec["id"]] = rec
    todo = [it for it in items if it["id"] not in done]
    print(f"[{name}] {len(done)} cached, {len(todo)} to run")
    with path.open("a", encoding="utf-8") as out:
        for i, item in enumerate(todo, 1):
            t = time.perf_counter()
            try:
                rep = pipeline.verify(item["claim"])
                rec = {**item, "structured": rep["structured"], "evidence": rep["evidence"],
                       "verdict": rep["verdict"], "warnings": rep["warnings"], "seconds": round(time.perf_counter() - t, 2)}
            except ValueError as exc:  # claim rejected by validation
                rec = {**item, "structured": None, "evidence": [], "verdict": {"label": NEI, "method": "rejected"},
                       "warnings": [str(exc)], "seconds": 0}
            out.write(json.dumps(rec) + "\n")
            out.flush()
            done[item["id"]] = rec
            if i % 10 == 0 or i == len(todo):
                print(f"  {i}/{len(todo)}  last {rec['seconds']}s  → {rec['verdict']['label']} (truth {item['label']})")
    return [done[it["id"]] for it in items]


def predict(rec: dict, thresholds: dict) -> str:
    s = rec.get("structured")
    if s and s.get("label") != NEI:
        return s["label"]
    if not rec.get("evidence"):
        return NEI
    return as_fever_label(decide(rec["evidence"], thresholds)["label"])


# ---------------------------------------------------------------- metrics
def metrics(truth: list[str], pred: list[str]) -> dict:
    n = len(truth)
    per = {}
    for label in LABELS:
        tp = sum(t == label and p == label for t, p in zip(truth, pred))
        fp = sum(t != label and p == label for t, p in zip(truth, pred))
        fn = sum(t == label and p != label for t, p in zip(truth, pred))
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per[label] = {"precision": round(prec, 4), "recall": round(rec, 4), "f1": round(f1, 4),
                      "support": sum(t == label for t in truth)}
    decisive = [(t, p) for t, p in zip(truth, pred) if p != NEI]
    return {
        "n": n,
        "accuracy": round(sum(t == p for t, p in zip(truth, pred)) / n, 4) if n else 0.0,
        "macro_f1": round(sum(m["f1"] for m in per.values()) / 3, 4),
        "precision_when_decisive": round(sum(t == p for t, p in decisive) / len(decisive), 4) if decisive else 0.0,
        "abstention_rate": round(sum(p == NEI for p in pred) / n, 4) if n else 0.0,
        "per_label": per,
        "confusion": {"labels": list(LABELS),
                      "matrix": [[sum(t == a and p == b for t, p in zip(truth, pred)) for b in LABELS] for a in LABELS]},
    }


# ---------------------------------------------------------------- calibration
GRID = {
    "entail": [0.5, 0.6, 0.7, 0.8, 0.9],
    "contradict": [0.5, 0.6, 0.7, 0.8, 0.9],
    "margin": [0.1, 0.2, 0.3, 0.4],
    "relevance": [-6.0, -3.0, -1.0, 0.0, 2.0],
}


def calibrate(records: list[dict]) -> dict:
    truth = [r["label"] for r in records]
    best, best_score = dict(DEFAULT_THRESHOLDS), -1.0
    for values in itertools.product(*GRID.values()):
        th = dict(zip(GRID.keys(), values))
        m = metrics(truth, [predict(r, th) for r in records])
        # Maximise macro F1; break ties toward higher precision when decisive.
        score = m["macro_f1"] + 0.01 * m["precision_when_decisive"]
        if score > best_score:
            best, best_score = th, score
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "thresholds.json").write_text(json.dumps(best, indent=2) + "\n")
    print(f"Calibrated thresholds: {best} (calibration macro F1 {best_score:.3f})")
    return best


# ---------------------------------------------------------------- reporting
def write_report(test: list[dict], f60: list[dict] | None, thresholds: dict) -> dict:
    datasets = []
    tm = metrics([r["label"] for r in test], [predict(r, thresholds) for r in test])
    secs = [r["seconds"] for r in test if r.get("seconds")]
    tm.update(name="FEVER 1.0 dev — held-out test split",
              description=f"Balanced random sample (seed {SEED}); thresholds tuned on a separate calibration split. "
                          "Label accuracy against the gold FEVER label.",
              mean_seconds=round(sum(secs) / len(secs), 2) if secs else None, dataset="FEVER")
    datasets.append(tm)
    if f60:
        fm = metrics([r["label"] for r in f60], [predict(r, thresholds) for r in f60])
        fm.update(name="FALCON-60 hand-written claims",
                  description="The 60 general-knowledge claims written for FALCON v4 (20 per label).", dataset="FALCON-60")
        datasets.append(fm)
    bench = {
        "headline": {k: tm[k] for k in ("n", "accuracy", "macro_f1", "precision_when_decisive", "abstention_rate")} | {"dataset": "FEVER"},
        "datasets": datasets,
        "baselines": [
            {"name": "FALCON v2 — TF-IDF + logistic regression (LIAR)", "task": "6-class LIAR truthfulness", "accuracy": 0.2627},
            {"name": "FALCON v2 — same model, collapsed true/false", "task": "binary LIAR (majority class = 56.7%)", "accuracy": 0.6196},
            {"name": "Random guess", "task": "3-class FEVER", "accuracy": 0.3333},
        ],
        "run": {"date": datetime.now(timezone.utc).isoformat(timespec="seconds"), "engine": pipeline.ENGINE_VERSION,
                "nli_model": settings.nli_model, "rerank_model": settings.rerank_model, "thresholds": thresholds},
    }
    REPORTS.mkdir(exist_ok=True)
    (REPORTS / "benchmark.json").write_text(json.dumps(bench, indent=2) + "\n")
    (REPORTS / "benchmark.md").write_text(_markdown(bench))
    print(_markdown(bench))
    return bench


def _markdown(b: dict) -> str:
    lines = [f"# FALXON benchmark ({b['run']['date'][:10]})", "",
             f"Engine `{b['run']['engine']}` · NLI `{b['run']['nli_model']}` · reranker `{b['run']['rerank_model']}`",
             f"Thresholds: `{json.dumps(b['run']['thresholds'])}`", ""]
    for d in b["datasets"]:
        lines += [f"## {d['name']}", "", d["description"], "",
                  "| Claims | Accuracy | Macro F1 | Precision when decisive | Abstained |", "|---|---|---|---|---|",
                  f"| {d['n']} | {d['accuracy']:.1%} | {d['macro_f1']:.1%} | {d['precision_when_decisive']:.1%} | {d['abstention_rate']:.1%} |",
                  "", "| Label | Precision | Recall | F1 | Support |", "|---|---|---|---|---|"]
        for label, m in d["per_label"].items():
            lines.append(f"| {label} | {m['precision']:.1%} | {m['recall']:.1%} | {m['f1']:.1%} | {m['support']} |")
        lines += ["", "Confusion matrix (rows = truth):", "", "| | " + " | ".join(d["confusion"]["labels"]) + " |",
                  "|---|---|---|---|"]
        for label, row in zip(d["confusion"]["labels"], d["confusion"]["matrix"]):
            lines.append(f"| {label} | " + " | ".join(map(str, row)) + " |")
        lines.append("")
    lines += ["## Baselines", "", "| System | Task | Accuracy |", "|---|---|---|"]
    lines += [f"| {x['name']} | {x['task']} | {x['accuracy']:.1%} |" for x in b["baselines"]]
    return "\n".join(lines) + "\n"


def quick_falcon60() -> dict:
    """Re-run only the 60 FALCON claims from scratch and update that row of the report."""
    cache = RUNS / "falcon60.jsonl"
    if cache.exists():
        cache.unlink()
    records = run(load_falcon60(), "falcon60")
    m = metrics([r["label"] for r in records], [predict(r, load_thresholds()) for r in records])
    m.update(name="FALCON-60 hand-written claims",
             description="The 60 general-knowledge claims written for FALCON v4 (20 per label).", dataset="FALCON-60")
    path = REPORTS / "benchmark.json"
    if path.exists():
        bench = json.loads(path.read_text())
        bench["datasets"] = [d for d in bench["datasets"] if d.get("dataset") != "FALCON-60"] + [m]
        path.write_text(json.dumps(bench, indent=2) + "\n")
        (REPORTS / "benchmark.md").write_text(_markdown(bench))
    print(f"FALCON-60: accuracy {m['accuracy']:.1%}, macro F1 {m['macro_f1']:.1%}")
    for t, row in zip(LABELS, m["confusion"]["matrix"]):
        print(f"  truth {t:<16} → {dict(zip(LABELS, row))}")
    wrong = [r for r in records if predict(r, load_thresholds()) != r["label"]]
    for r in wrong:
        print(f"  ✗ {r['claim']}  (truth {r['label']}, got {predict(r, load_thresholds())})")
    return m


def explain_falcon60() -> str:
    """Explain the misses of the last FALCON-60 run without re-running it. Writes reports/falcon60_misses.txt."""
    path = RUNS / "falcon60.jsonl"
    if not path.exists():
        raise SystemExit("No FALCON-60 run yet: run `python -m evaluation.bench falcon60` first.")
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    thresholds = load_thresholds()
    structured = [r for r in records if r.get("structured")]
    decisive = [r for r in structured if r["structured"].get("label") != NEI]
    failed = [r for r in structured if "could not be reached" in (r["structured"].get("note") or "")]
    lines = [f"engine {pipeline.ENGINE_VERSION}; {len(records)} claims; record checks used on {len(structured)}, "
             f"decisive on {len(decisive)}, failed to reach Wikidata on {len(failed)}", ""]
    for r in records:
        got = predict(r, thresholds)
        if got == r["label"]:
            continue
        lines.append(f"✗ {r['claim']}  (truth {r['label']}, got {got})")
        s = r.get("structured")
        if s:
            lines.append(f"    record check [{s.get('relation')}] {s.get('label')}: {s.get('note')}")
            if s.get("source"):
                lines.append(f"      {s['source'].get('text', '')[:200]}")
        lines.append(f"    text step: {r['verdict'].get('label')} — {r['verdict'].get('reason', '')}")
        for w in r.get("warnings") or []:
            lines.append(f"    warning: {w}")
        ev = sorted(r.get("evidence") or [], key=lambda e: (not e.get("decisive"), -e.get("relevance", 0)))
        for e in ev[:2]:
            n = e.get("nli") or {}
            lines.append(f"    [{'decisive' if e.get('decisive') else 'top'} e{n.get('entailment', 0):.2f} "
                         f"c{n.get('contradiction', 0):.2f} rel{e.get('relevance', 0):.1f}] {e.get('title', '')}: {e.get('text', '')[:220]}")
        lines.append("")
    text = "\n".join(lines)
    REPORTS.mkdir(parents=True, exist_ok=True)
    (REPORTS / "falcon60_misses.txt").write_text(text, encoding="utf-8")
    print(text)
    print(f"Saved to {REPORTS / 'falcon60_misses.txt'}")
    return text


DOCTOR_CLAIMS = [
    ("Sydney is the capital of Australia.", REFUTED),
    ("Mount Everest is located in Nepal.", SUPPORTED),
    ("Mount Everest is located in Australia.", REFUTED),
    ("Jupiter is the largest planet in the Solar System.", SUPPORTED),
    ("Mars is the largest planet in the Solar System.", REFUTED),
    ("Venus is the second planet from the Sun.", SUPPORTED),
    ("The Sun revolves around the Earth.", REFUTED),
    ("The Moon is a planet.", REFUTED),
]


def doctor() -> int:
    """Check the connections FALXON needs and run a few record checks with known answers."""
    from falxon import structured
    from falxon.http import get_json

    problems = 0
    for name, url, params in [
        ("Wikidata", structured.API, {"action": "wbsearchentities", "search": "Canberra", "language": "en", "format": "json"}),
        ("Wikipedia", "https://en.wikipedia.org/w/api.php", {"action": "query", "list": "search", "srsearch": "Canberra",
                                                            "format": "json"}),
    ]:
        try:
            get_json(url, params, use_cache=False)
            print(f"  ok    {name} reachable")
        except Exception as exc:
            problems += 1
            print(f"  FAIL  {name}: {type(exc).__name__}: {str(exc)[:160]}")
    for claim, want in DOCTOR_CLAIMS:
        try:
            r = structured.check(claim) or {"label": NEI, "note": "not a record-check claim"}
        except Exception as exc:
            r = {"label": "ERROR", "note": f"{type(exc).__name__}: {exc}"}
        ok = r["label"] == want
        problems += not ok
        print(f"  {'ok  ' if ok else 'MISS'}  {claim}  → {r['label']} (want {want})")
        if not ok:
            print(f"        {r.get('note')}")
    print("All checks passed." if not problems else f"{problems} problem(s). Send this output to the FALXON thread.")
    return problems


# ---------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["run", "calibrate", "report", "all", "falcon60", "why", "doctor"])
    ap.add_argument("--n", type=int, default=600, help="FEVER claims to sample (balanced; 1/3 used for calibration)")
    ap.add_argument("--skip-falcon60", action="store_true")
    args = ap.parse_args(argv)

    if args.command == "falcon60":
        return quick_falcon60()
    if args.command == "why":
        return explain_falcon60()
    if args.command == "doctor":
        return doctor()
    calib_items, test_items = fever_sample(args.n)
    if args.command in ("run", "all"):
        run(calib_items, f"fever_calib_{args.n}")
        run(test_items, f"fever_test_{args.n}")
        if not args.skip_falcon60:
            run(load_falcon60(), "falcon60")
    if args.command in ("calibrate", "all"):
        calibrate(run(calib_items, f"fever_calib_{args.n}"))
    if args.command in ("report", "all"):
        f60 = None if args.skip_falcon60 else run(load_falcon60(), "falcon60")
        write_report(run(test_items, f"fever_test_{args.n}"), f60, load_thresholds())


if __name__ == "__main__":
    main()
