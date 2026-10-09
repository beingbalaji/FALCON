import json

from evaluation import bench

FEVER_LINES = [
    {"id": 1, "claim": "The Eiffel Tower is located in Paris.", "label": "SUPPORTS"},
    {"id": 2, "claim": "Canberra is the capital of Australia.", "label": "SUPPORTS"},
    {"id": 3, "claim": "William Shakespeare wrote Hamlet.", "label": "SUPPORTS"},
    {"id": 4, "claim": "The Eiffel Tower is located in London.", "label": "REFUTES"},
    {"id": 5, "claim": "Sydney is the capital of Australia.", "label": "REFUTES"},
    {"id": 6, "claim": "Albert Einstein wrote Hamlet.", "label": "REFUTES"},
    {"id": 7, "claim": "Zorblax quintuplets enjoy purple weather.", "label": "NOT ENOUGH INFO"},
    {"id": 8, "claim": "Gustave Eiffel liked green tea in the mornings.", "label": "NOT ENOUGH INFO"},
    {"id": 9, "claim": "The Love Civic Center hosts a monthly chess club.", "label": "NOT ENOUGH INFO"},
]


def test_metrics_math():
    m = bench.metrics(["SUPPORTED", "REFUTED", "NOT ENOUGH INFO", "SUPPORTED"],
                      ["SUPPORTED", "NOT ENOUGH INFO", "NOT ENOUGH INFO", "REFUTED"])
    assert m["accuracy"] == 0.5
    assert m["abstention_rate"] == 0.5
    assert m["precision_when_decisive"] == 0.5
    assert m["confusion"]["matrix"][0] == [1, 1, 0]


def test_full_benchmark_offline(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    (data / "fever_dev.jsonl").write_text("\n".join(json.dumps(x) for x in FEVER_LINES))
    (data / "falcon60.csv").write_text("claim,label\nSydney is the capital of Australia.,REFUTED\n")
    monkeypatch.setattr(bench, "DATA", data)
    monkeypatch.setattr(bench, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(bench, "REPORTS", tmp_path / "reports")
    monkeypatch.setattr(bench, "load_thresholds", lambda: json.loads((tmp_path / "reports" / "thresholds.json").read_text()))

    bench.main(["all", "--n", "9"])

    report = json.loads((tmp_path / "reports" / "benchmark.json").read_text())
    assert report["headline"]["n"] == 6
    assert report["headline"]["accuracy"] == 1.0
    assert report["datasets"][1]["accuracy"] == 1.0
    assert (tmp_path / "runs" / "fever_test_9.jsonl").exists()


def test_quick_falcon60_updates_report(tmp_path, monkeypatch):
    data, reports = tmp_path / "data", tmp_path / "reports"
    data.mkdir()
    reports.mkdir()
    (data / "falcon60.csv").write_text("claim,label\nThe Eiffel Tower is located in London.,REFUTED\n"
                                       "William Shakespeare wrote Hamlet.,SUPPORTED\n")
    (reports / "benchmark.json").write_text(json.dumps({
        "headline": {}, "baselines": [], "run": {"date": "2026-10-06", "engine": "x", "nli_model": "x",
                                                  "rerank_model": "x", "thresholds": {}},
        "datasets": [{"dataset": "FALCON-60", "accuracy": 0.1}],
    }))
    monkeypatch.setattr(bench, "DATA", data)
    monkeypatch.setattr(bench, "RUNS", tmp_path / "runs")
    monkeypatch.setattr(bench, "REPORTS", reports)
    bench.main(["falcon60"])
    report = json.loads((reports / "benchmark.json").read_text())
    assert [d["accuracy"] for d in report["datasets"]] == [1.0]


def test_why_explains_misses(tmp_path, monkeypatch):
    runs, reports = tmp_path / "runs", tmp_path / "reports"
    runs.mkdir()
    rec = {"id": "f1", "claim": "The Moon is a planet.", "label": "REFUTED",
           "structured": {"relation": "instance", "label": "NOT ENOUGH INFO", "note": "Could not identify it."},
           "evidence": [{"title": "Moon", "text": "The Moon is Earth's only natural satellite.", "decisive": False,
                         "relevance": 4.2, "nli": {"entailment": 0.1, "neutral": 0.7, "contradiction": 0.2}}],
           "verdict": {"label": "NOT ENOUGH INFO", "reason": "Weak."}, "warnings": []}
    (runs / "falcon60.jsonl").write_text(json.dumps(rec) + "\n")
    monkeypatch.setattr(bench, "RUNS", runs)
    monkeypatch.setattr(bench, "REPORTS", reports)
    text = bench.main(["why"])
    assert "✗ The Moon is a planet." in text and "record check [instance]" in text and "Moon: The Moon" in text
    assert (reports / "falcon60_misses.txt").exists()


def test_doctor_runs_offline(monkeypatch):
    from conftest import fake_get_json
    from falxon import http

    monkeypatch.setattr(http, "get_json", fake_get_json)
    assert bench.main(["doctor"]) == 0
