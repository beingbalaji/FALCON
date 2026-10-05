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
