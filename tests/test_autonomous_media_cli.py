import json
from pathlib import Path

from pipelines.autonomous_media_cli import main


def test_autonomous_media_dry_run_does_not_write_files(tmp_path, capsys, monkeypatch):
    schema_dir = tmp_path / "projects" / "jrt" / "metadata" / "schema"
    schema_dir.mkdir(parents=True)
    source_schema = Path("projects/jrt/metadata/schema/media_job.schema.json")
    (schema_dir / "media_job.schema.json").write_text(source_schema.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(
        "sys.argv",
        [
            "autonomous-media",
            "dry-run",
            "--repo-root",
            str(tmp_path),
            "--job-id",
            "dry-run-test",
            "--track-id",
            "track-test",
        ],
    )

    assert main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output["mode"] == "dry-run"
    assert output["writes_files"] is False
    assert not (tmp_path / "projects" / "jrt" / "metadata" / "jobs").exists()


def test_autonomous_media_run_requires_agent_enabled(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("AGENT_ENABLED", "false")
    monkeypatch.setattr(
        "sys.argv",
        [
            "autonomous-media",
            "run",
            "--require-agent-enabled",
            "--repo-root",
            str(tmp_path),
            "--job-id",
            "prod-test",
            "--track-id",
            "track-test",
        ],
    )

    assert main() == 2
    assert "AGENT_ENABLED is not true" in capsys.readouterr().err
