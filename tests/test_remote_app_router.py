"""Tests for secure remote control and file access endpoints in app router."""

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from modules.api.routers.app import create_app_router


class _FakeJarvis:
    def __init__(self):
        self.commands = []

    def process(self, command: str):
        self.commands.append(command)
        return True, f"handled:{command}"


class _FakeState:
    def __init__(self):
        self.jarvis = _FakeJarvis()
        self.ai_router = None

    def load_components(self):
        return None


def _build_client(state):
    app = FastAPI()
    app.include_router(create_app_router(state))
    return TestClient(app)


def test_remote_status_exposes_flags_and_roots(monkeypatch, tmp_path):
    root = tmp_path / "allowed"
    root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOW_DANGEROUS", "false")
    monkeypatch.setenv("LADA_REMOTE_ALLOWED_ROOTS", str(root))
    monkeypatch.setenv("LADA_REMOTE_MAX_DOWNLOAD_MB", "2")
    monkeypatch.setenv("LADA_REMOTE_COMMAND_RPM", "12")
    monkeypatch.setenv("LADA_REMOTE_FILES_RPM", "24")
    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_RPM", "8")

    client = _build_client(_FakeState())
    resp = client.get("/remote/status", headers={"X-Request-ID": "remote-status-req-1"})

    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "remote-status-req-1"
    payload = resp.json()
    assert payload["enabled"] is True
    assert payload["downloads_enabled"] is True
    assert payload["dangerous_enabled"] is False
    assert any(str(root) == p for p in payload["allowed_roots"])
    assert payload["max_download_mb"] == 2.0
    assert payload["command_rpm"] == 12
    assert payload["files_rpm"] == 24
    assert payload["download_rpm"] == 8


def test_sessions_list_propagates_request_id_header():
    client = _build_client(_FakeState())
    request_id = "sessions-list-req-1"

    response = client.get("/sessions", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == request_id
    assert isinstance(response.json().get("sessions"), list)


def test_rollout_status_normalizes_stage_and_reports_disabled_funnel(monkeypatch):
    monkeypatch.setenv("LADA_ROLLOUT_STAGE", "unknown")
    monkeypatch.setenv("LADA_TAILSCALE_FUNNEL", "false")
    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "false")
    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "false")

    client = _build_client(_FakeState())
    resp = client.get("/rollout/status", headers={"X-Request-ID": "rollout-status-req-1"})

    assert resp.status_code == 200
    assert resp.headers["x-request-id"] == "rollout-status-req-1"
    payload = resp.json()
    assert payload["rollout_stage"] == "local"
    assert payload["funnel"]["status"] == "disabled"
    assert payload["readiness"]["ready"] is True


def test_rollout_status_public_stage_reports_blockers(monkeypatch):
    monkeypatch.setenv("LADA_ROLLOUT_STAGE", "public")
    monkeypatch.setenv("LADA_TAILSCALE_FUNNEL", "false")
    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "false")
    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "false")

    client = _build_client(_FakeState())
    resp = client.get("/rollout/status")

    assert resp.status_code == 200
    payload = resp.json()
    blockers = payload["readiness"]["blockers"]
    assert payload["readiness"]["ready"] is False
    assert any("LADA_TAILSCALE_FUNNEL" in blocker for blocker in blockers)
    assert any("remote control or remote downloads" in blocker for blocker in blockers)


def test_rollout_status_deep_check_builds_funnel_url(monkeypatch):
    monkeypatch.setenv("LADA_ROLLOUT_STAGE", "canary")
    monkeypatch.setenv("LADA_TAILSCALE_FUNNEL", "true")
    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "false")
    monkeypatch.setattr("modules.api.routers.app.shutil.which", lambda _: "tailscale")

    fake_json = json.dumps({"Self": {"DNSName": "lada-demo.tailnet.ts.net."}})

    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=fake_json)

    monkeypatch.setattr("modules.api.routers.app.subprocess.run", _fake_run)

    client = _build_client(_FakeState())
    resp = client.get("/rollout/status", params={"deep_check": "true"})

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["funnel"]["enabled"] is True
    assert payload["funnel"]["binary_found"] is True
    assert payload["funnel"]["deep_checked"] is True
    assert payload["funnel"]["connected"] is True
    assert payload["funnel"]["status"] == "connected"
    assert payload["funnel"]["public_url"] == "https://lada-demo.tailnet.ts.net/app"
    assert payload["readiness"]["ready"] is True


def test_rollout_local_stage_blocks_non_local_remote_command(monkeypatch):
    monkeypatch.setenv("LADA_ROLLOUT_STAGE", "local")
    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "true")

    client = _build_client(_FakeState())
    response = client.post(
        "/remote/command",
        json={"command": "open notepad"},
        headers={"X-Forwarded-For": "8.8.8.8"},
    )

    assert response.status_code == 403
    assert "LADA_ROLLOUT_STAGE=local" in str(response.json().get("detail", ""))


def test_rollout_internal_stage_blocks_public_remote_files(monkeypatch, tmp_path):
    root = tmp_path / "safe"
    root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("LADA_ROLLOUT_STAGE", "internal")
    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOWED_ROOTS", str(root))

    client = _build_client(_FakeState())
    response = client.get(
        "/remote/files",
        params={"path": str(root)},
        headers={"X-Forwarded-For": "1.2.3.4"},
    )

    assert response.status_code == 403
    assert "LADA_ROLLOUT_STAGE=internal" in str(response.json().get("detail", ""))


def test_rollout_disabled_stage_blocks_remote_download(monkeypatch, tmp_path):
    root = tmp_path / "safe"
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / "notes.txt"
    file_path.write_text("data", encoding="utf-8")

    monkeypatch.setenv("LADA_ROLLOUT_STAGE", "disabled")
    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOWED_ROOTS", str(root))

    client = _build_client(_FakeState())
    response = client.get("/remote/download", params={"path": str(file_path)})

    assert response.status_code == 403
    assert "LADA_ROLLOUT_STAGE=disabled" in str(response.json().get("detail", ""))


def test_remote_command_requires_enable_and_blocks_dangerous(monkeypatch):
    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "false")

    client = _build_client(_FakeState())
    disabled = client.post("/remote/command", json={"command": "open notepad"})
    assert disabled.status_code == 403

    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOW_DANGEROUS", "false")

    ok = client.post("/remote/command", json={"command": "open notepad"})
    assert ok.status_code == 200
    ok_payload = ok.json()
    assert ok_payload["success"] is True
    assert ok_payload["engine"] == "jarvis"
    assert ok_payload["response"] == "handled:open notepad"

    blocked = client.post("/remote/command", json={"command": "shutdown now"})
    assert blocked.status_code == 403


def test_remote_command_allowlist_policy(monkeypatch):
    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOW_DANGEROUS", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOWED_COMMANDS", "open;launch app")

    client = _build_client(_FakeState())

    allowed = client.post("/remote/command", json={"command": "open notepad"})
    assert allowed.status_code == 200

    blocked = client.post("/remote/command", json={"command": "dir"})
    assert blocked.status_code == 403


def test_remote_command_rate_limit(monkeypatch):
    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_COMMAND_RPM", "1")

    client = _build_client(_FakeState())

    first = client.post("/remote/command", json={"command": "open notepad"})
    assert first.status_code == 200

    second = client.post("/remote/command", json={"command": "open calc"})
    assert second.status_code == 429


def test_remote_command_idempotency_replays_without_reexecution(monkeypatch):
    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOW_DANGEROUS", "false")

    state = _FakeState()
    client = _build_client(state)

    headers = {"Idempotency-Key": "remote-idem-1"}
    first = client.post("/remote/command", json={"command": "open notepad"}, headers=headers)
    second = client.post("/remote/command", json={"command": "open notepad"}, headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200

    first_payload = first.json()
    second_payload = second.json()
    assert first_payload["idempotency"]["replayed"] is False
    assert second_payload["idempotency"]["replayed"] is True
    assert second_payload["response"] == "handled:open notepad"
    assert state.jarvis.commands == ["open notepad"]


def test_remote_command_idempotency_conflict_returns_409(monkeypatch):
    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOW_DANGEROUS", "false")

    client = _build_client(_FakeState())
    headers = {"Idempotency-Key": "remote-idem-conflict"}

    first = client.post("/remote/command", json={"command": "open notepad"}, headers=headers)
    conflict = client.post("/remote/command", json={"command": "open calc"}, headers=headers)

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert "Idempotency key reuse" in str(conflict.json().get("detail", ""))


def test_remote_files_and_download_with_allowed_roots(monkeypatch, tmp_path):
    root = tmp_path / "safe"
    root.mkdir(parents=True, exist_ok=True)
    nested = root / "docs"
    nested.mkdir(parents=True, exist_ok=True)
    file_path = root / "notes.txt"
    content = b"lada remote file"
    file_path.write_bytes(content)

    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)

    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOWED_ROOTS", str(root))
    monkeypatch.setenv("LADA_REMOTE_MAX_DOWNLOAD_MB", "1")

    client = _build_client(_FakeState())

    listing = client.get("/remote/files", params={"path": str(root)})
    assert listing.status_code == 200
    payload = listing.json()
    assert payload["success"] is True
    names = [e["name"] for e in payload["entries"]]
    assert "docs" in names
    assert "notes.txt" in names
    assert payload["breadcrumbs"][0]["is_root"] is True
    assert payload["breadcrumbs"][0]["path"] == str(root)
    assert payload["pagination"]["page"] == 1
    assert payload["pagination"]["page_size"] == 100
    assert payload["pagination"]["total_entries"] >= 2
    assert payload["pagination"]["total_pages"] == 1
    assert payload["pagination"]["has_prev"] is False
    assert payload["pagination"]["has_next"] is False

    download = client.get("/remote/download", params={"path": str(file_path)})
    assert download.status_code == 200
    assert download.content == content

    forbidden = client.get("/remote/files", params={"path": str(outside)})
    assert forbidden.status_code == 403


def test_remote_files_pagination_and_nested_breadcrumbs(monkeypatch, tmp_path):
    root = tmp_path / "safe"
    root.mkdir(parents=True, exist_ok=True)
    nested = root / "docs"
    nested.mkdir(parents=True, exist_ok=True)

    for idx in range(5):
        (root / f"note_{idx}.txt").write_text(f"entry-{idx}", encoding="utf-8")

    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOWED_ROOTS", str(root))

    client = _build_client(_FakeState())

    page_one = client.get("/remote/files", params={"path": str(root), "page": 1, "page_size": 2})
    assert page_one.status_code == 200
    page_one_payload = page_one.json()
    assert len(page_one_payload["entries"]) == 2
    assert page_one_payload["truncated"] is True
    assert page_one_payload["pagination"]["page"] == 1
    assert page_one_payload["pagination"]["page_size"] == 2
    assert page_one_payload["pagination"]["total_entries"] == 6
    assert page_one_payload["pagination"]["total_pages"] == 3
    assert page_one_payload["pagination"]["has_prev"] is False
    assert page_one_payload["pagination"]["has_next"] is True

    page_two = client.get("/remote/files", params={"path": str(root), "page": 2, "page_size": 2})
    assert page_two.status_code == 200
    page_two_payload = page_two.json()
    assert len(page_two_payload["entries"]) == 2
    assert page_two_payload["pagination"]["page"] == 2
    assert page_two_payload["pagination"]["has_prev"] is True
    assert page_two_payload["pagination"]["has_next"] is True

    nested_listing = client.get("/remote/files", params={"path": str(nested)})
    assert nested_listing.status_code == 200
    nested_payload = nested_listing.json()
    breadcrumbs = nested_payload["breadcrumbs"]
    assert breadcrumbs[0]["is_root"] is True
    assert breadcrumbs[0]["path"] == str(root)
    assert breadcrumbs[-1]["name"] == "docs"
    assert breadcrumbs[-1]["path"] == str(nested)


def test_remote_files_skip_outside_symlink(monkeypatch, tmp_path):
    root = tmp_path / "safe"
    root.mkdir(parents=True, exist_ok=True)
    outside = tmp_path / "outside"
    outside.mkdir(parents=True, exist_ok=True)

    external_file = outside / "secret.txt"
    external_file.write_text("top-secret", encoding="utf-8")

    link_path = root / "secret_link.txt"
    try:
        link_path.symlink_to(external_file)
    except (OSError, NotImplementedError):
        return

    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOWED_ROOTS", str(root))

    client = _build_client(_FakeState())
    listing = client.get("/remote/files", params={"path": str(root)})
    assert listing.status_code == 200
    names = [e["name"] for e in listing.json()["entries"]]
    assert "secret_link.txt" not in names


def test_remote_files_and_download_rate_limit(monkeypatch, tmp_path):
    root = tmp_path / "safe"
    root.mkdir(parents=True, exist_ok=True)
    file_path = root / "notes.txt"
    file_path.write_bytes(b"data")

    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_ALLOWED_ROOTS", str(root))
    monkeypatch.setenv("LADA_REMOTE_FILES_RPM", "1")
    monkeypatch.setenv("LADA_REMOTE_DOWNLOAD_RPM", "1")

    client = _build_client(_FakeState())

    first_list = client.get("/remote/files", params={"path": str(root)})
    assert first_list.status_code == 200
    second_list = client.get("/remote/files", params={"path": str(root)})
    assert second_list.status_code == 429

    first_download = client.get("/remote/download", params={"path": str(file_path)})
    assert first_download.status_code == 200
    second_download = client.get("/remote/download", params={"path": str(file_path)})
    assert second_download.status_code == 429


def test_remote_command_writes_audit_log(monkeypatch, tmp_path):
    audit_path = tmp_path / "audit" / "remote_actions.jsonl"
    request_id = "remote-audit-req-1"

    monkeypatch.setenv("LADA_REMOTE_CONTROL_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_AUDIT_ENABLED", "true")
    monkeypatch.setenv("LADA_REMOTE_AUDIT_LOG", str(audit_path))

    client = _build_client(_FakeState())
    response = client.post(
        "/remote/command",
        json={"command": "open notepad"},
        headers={"X-Request-ID": request_id},
    )
    assert response.status_code == 200

    assert audit_path.exists()
    lines = [line for line in audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines
    last = json.loads(lines[-1])
    assert last["event"] == "remote.command"
    assert last["success"] is True
    assert "client_ip" in last["details"]
    assert last["details"]["request_id"] == request_id
