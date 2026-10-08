import json
import sys
import pytest
import generate_reports

def test_selecting_failed_run_does_not_write_selection_or_generate_reports(tmp_path, monkeypatch):
    run = tmp_path / "runs/failed_run"
    run.mkdir(parents=True)
    (run / "summary.json").write_text(json.dumps({"error": "command rejected", "scenarios": [{"status": "command_failed"}]}))
    config = tmp_path / "base.json"
    config.write_text(json.dumps({"expected_replicas_per_scenario": 50}))
    monkeypatch.setattr(generate_reports, "__file__", str(tmp_path / "generate_reports.py"))
    monkeypatch.setattr(sys, "argv", ["generate_reports.py", "--config", str(config),
                                     "--run-id", "failed_run", "--runs-root", str(tmp_path / "runs")])
    calls = []
    monkeypatch.setattr(generate_reports.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    with pytest.raises(ValueError, match="incomplete or failed"):
        generate_reports.main()
    assert not calls
    assert not (tmp_path / "run_config.local.json").exists()
    assert not (tmp_path / "docs").exists()
