import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import dashboard.plugin_api as api_module
from dashboard.plugin_api import FileAdapter, router, set_adapter


def client():
    app = FastAPI(); app.include_router(router); return TestClient(app)


def evidence(**changes):
    record = {"schema_version": "hcw/v1", "kind": "evidence", "id": "EV-1", "created_at": "2026-08-19T00:00:00Z", "run_id": "named-run", "type": "green", "actor": {"role": "builder", "profile": "terra", "task_id": "task-green"}, "commit_sha": "b" * 40, "command": ["pytest", "-q"], "exit_code": 0, "summary": "tests passed TOKEN=private-value", "artifact_path": "artifacts/tests.txt", "artifact_sha256": "c" * 64, "previous_evidence_hash": None}
    record.update(changes)
    record["evidence_hash"] = hashlib.sha256(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return record


def write_run(repo: Path, run_id="named-run"):
    root = repo / ".hermes" / "workflows" / run_id; root.mkdir(parents=True)
    stages = ("design", "plan", "red", "green", "spec-review", "quality-review", "verify", "live", "complete")
    dispatches = {stage: {"stage": stage, "task_id": f"task-{stage}", "profile": f"dev-{stage}", "provider": "hermes", "model": "gpt-5", "session_id": f"session-{stage}", "attempt": 1, "brief_hash": "d" * 64} for stage in stages}
    run = {"schema_version": "hcw/v1", "kind": "run", "id": run_id, "revision": 3, "created_at": "2026-08-19T00:00:00Z", "updated_at": "2026-08-19T00:00:00Z", "package_id": "P4", "base_sha": "a" * 40, "head_sha": "b" * 40, "branch": "hcw/named-run/attempt-1", "status": "awaiting_spec_review", "attempt": 1, "attempt_history": [{"at": "2026-08-18T00:00:00Z", "attempt": 0, "head_sha": "a" * 40, "reason": "review_changes_requested"}], "kanban_board": "named", "kanban_task_ids": {stage: f"task-{stage}" for stage in stages}, "stage_profiles": {stage: f"dev-{stage}" for stage in stages}, "stage_statuses": {stage: ("active" if stage == "spec-review" else "completed" if stage in {"design", "plan", "red", "green"} else "pending") for stage in stages}, "dispatches": dispatches}
    (root / "run.json").write_text(json.dumps(run))
    (root / "approved-design.json").write_text(json.dumps({"kind": "approved_design"}))
    (root / "plan.json").write_text(json.dumps({"kind": "plan"}))
    (root / "reviews.json").write_text(json.dumps({"reviews": [{"schema_version": "hcw/v1", "kind": "review", "reviewer": {"profile": "dev-spec-reviewer", "task_id": "task-spec-review", "session_id": "session-spec", "provider": "hermes", "model": "gpt-5"}, "reviewed_sha": "b" * 40, "decision": "changes_requested", "findings": [{"id": "F-1", "description": "Use a test", "severity": "blocker"}], "dispositions": [{"finding_id": "F-1", "disposition": "accepted"}]}]}))
    (root / "evidence.jsonl").write_text(json.dumps(evidence()) + "\n")
    (root / "verification.json").write_text(json.dumps({"candidate_sha": "b" * 40, "status": "passed"}))
    (root / "handoff.json").write_text(json.dumps({"candidate_sha": "b" * 40, "pr_url": "https://github.com/acme/demo/pull/7"}))
    return root


@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    executable = shutil.which("hermes")
    assert executable
    version = subprocess.run([executable, "--version"], text=True, capture_output=True, check=True).stdout
    hermes = Path(next(line.split(": ", 1)[1] for line in version.splitlines() if line.startswith("Install directory: ")))
    if str(hermes) not in sys.path: sys.path.insert(0, str(hermes))
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "hermes"))
    from hermes_cli import kanban_db, projects_db
    default_repo, named_repo = tmp_path / "default-repo", tmp_path / "named-repo"
    for repo in (default_repo, named_repo): (repo / ".git").mkdir(parents=True)
    kanban_db.write_board_metadata("default", name="Default repository", default_workdir=str(default_repo))
    kanban_db.create_board("named", name="Named repository", default_workdir=str(named_repo))
    write_run(default_repo, "default-run"); write_run(named_repo)
    set_adapter(FileAdapter()); yield tmp_path, default_repo, named_repo, kanban_db, projects_db
    set_adapter(FileAdapter())


def test_authoritative_artifacts_project_safe_complete_dto(hermes_home):
    _tmp, default_repo, named_repo, _kanban, _projects = hermes_home
    payload = client().get("/runs/named-run?board=named").json()
    assert client().get("/boards").json()["boards"] == [{"id": "default", "label": "Default repository", "repo": "default-repo"}, {"id": "named", "label": "Named repository", "repo": "named-repo"}]
    assert payload["run"]["current_dispatch"] == {"stage": "spec-review", "task_id": "task-spec-review", "profile": "dev-spec-review", "provider": "hermes", "model": "gpt-5", "session_id": "session-spec-review", "attempt": 1}
    assert payload["stages"][3]["id"] == "green"
    assert payload["reviews"][0]["reviewer"]["profile"] == "dev-spec-reviewer"
    assert payload["reviews"][0]["findings"] == [{"id": "F-1", "severity": "blocker", "description": "Use a test", "disposition": "accepted"}]
    assert payload["evidence"] == [{"name": "green", "status": "passed", "summary": "tests passed [redacted]", "commit_sha": "b" * 40, "artifact_sha256": "c" * 64}]
    assert payload["handoff"]["pr_url"] == "https://github.com/acme/demo/pull/7"
    assert [x["label"] for x in payload["artifacts"]] == ["Run record", "Approved design", "Plan", "Evidence", "Reviews", "Verification", "Handoff"]
    assert str(default_repo) not in json.dumps(payload) and str(named_repo) not in json.dumps(payload)
    assert "command" not in json.dumps(payload) and "private-value" not in json.dumps(payload)


def test_project_authority_and_get_only_boundary(hermes_home):
    tmp, _default, named, kanban, projects = hermes_home
    with projects.connect_closing() as conn: project_id = projects.create_project(conn, name="Named", primary_path=str(named))
    kanban.write_board_metadata("named", default_workdir=str(named), project_id=project_id)
    assert client().get("/runs?board=named").status_code == 200
    other = tmp / "other"; (other / ".git").mkdir(parents=True)
    kanban.write_board_metadata("named", default_workdir=str(other), project_id=project_id)
    assert client().get("/runs?board=named").status_code == 404
    assert client().post("/runs/named-run?board=default").status_code == 405
    assert client().get("/runs/named-run?board=../../etc").status_code == 422


def _bad_hash(root):
    record = evidence(); record["evidence_hash"] = "0" * 64
    (root / "evidence.jsonl").write_text(json.dumps(record) + "\n")


@pytest.mark.parametrize("change", [lambda root: (root / "evidence.jsonl").write_text('{bad}\n'), _bad_hash])
def test_malformed_or_broken_evidence_rejects_detail_projection(hermes_home, change):
    _tmp, _default, named, _kanban, _projects = hermes_home
    change(named / ".hermes" / "workflows" / "named-run")
    assert client().get("/runs/named-run?board=named").status_code == 409


def test_changed_run_revision_returns_conflict(hermes_home, monkeypatch):
    _tmp, _default, named, _kanban, _projects = hermes_home
    original, reads = api_module._json_file, 0
    def changing(fd, name):
        nonlocal reads
        value = original(fd, name)
        if name == "run.json" and value:
            reads += 1
            if reads == 2: value["revision"] += 1
        return value
    monkeypatch.setattr(api_module, "_json_file", changing)
    assert client().get("/runs/named-run?board=named").status_code == 409


def test_strict_github_host_allowlist(hermes_home):
    _tmp, _default, named, _kanban, _projects = hermes_home
    handoff = named / ".hermes" / "workflows" / "named-run" / "handoff.json"
    handoff.write_text(json.dumps({"pr_url": "https://github.com.evil.invalid/acme/demo/pull/7"}))
    assert client().get("/runs/named-run?board=named").json()["handoff"]["pr_url"] is None


def test_projection_redacts_and_bounds_every_exported_untrusted_text(hermes_home):
    _tmp, _default, named, _kanban, _projects = hermes_home
    run_path = named / ".hermes" / "workflows" / "named-run" / "run.json"
    run = json.loads(run_path.read_text())
    run["package_id"] = "x" * 1000
    run["branch"] = "branch TOKEN=private-value " + "b" * 1000
    run["kanban_task_ids"]["green"] = "task SECRET=private-value " + "x" * 1000
    run["stage_profiles"]["green"] = "profile API_KEY=private-value " + "x" * 1000
    run["attempt_history"][0]["reason"] = "blocker password=private-value " + "x" * 1000
    run_path.write_text(json.dumps(run))
    payload = client().get("/runs/named-run?board=named").json()
    rendered = json.dumps(payload)
    assert len(payload["run"]["package_id"]) == 80 and len(payload["run"]["branch"]) == 200
    assert "private-value" not in rendered and "[redacted]" in rendered
    assert all(len(value) <= 500 for value in re.findall(r'"(?:description|summary)": "([^"]*)"', rendered))


def test_descriptor_read_is_bound_to_opened_regular_file(monkeypatch):
    calls = []
    class Info: st_mode = 0o120777; st_size = 1
    monkeypatch.setattr(api_module.os, "open", lambda name, flags, **kwargs: calls.append((name, flags, kwargs)) or 77)
    monkeypatch.setattr(api_module.os, "fstat", lambda fd: Info())
    monkeypatch.setattr(api_module.os, "close", lambda fd: None)
    with pytest.raises(api_module.ProjectionError): api_module._read_file(9, "run.json")
    assert calls[0][0] == "run.json" and calls[0][2]["dir_fd"] == 9 and calls[0][1] & getattr(api_module.os, "O_NOFOLLOW", 0)


def test_run_without_authoritative_dispatch_map_is_rejected(hermes_home):
    _tmp, _default, named, _kanban, _projects = hermes_home
    path = named / ".hermes" / "workflows" / "named-run" / "run.json"
    run = json.loads(path.read_text()); run.pop("dispatches"); path.write_text(json.dumps(run))
    assert client().get("/runs/named-run?board=named").status_code == 409
