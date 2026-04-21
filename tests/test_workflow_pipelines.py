from modules.workflow_pipelines import PipelineStep, StepType, StepStatus, _handle_exec


def test_handle_exec_defaults_to_shellless(monkeypatch):
    captured = {}

    class _Proc:
        returncode = 0
        stdout = b"ok"
        stderr = b""

    def _fake_run(command, **kwargs):
        captured["command"] = command
        captured["shell"] = kwargs.get("shell")
        return _Proc()

    monkeypatch.setattr("modules.workflow_pipelines.subprocess.run", _fake_run)

    step = PipelineStep(id="exec1", step_type=StepType.EXEC, command="echo hello")
    result = _handle_exec(step, None, {})

    assert result.success is True
    assert result.status == StepStatus.SUCCEEDED
    assert captured["shell"] is False
    assert isinstance(captured["command"], list)


def test_handle_exec_allows_explicit_shell_metadata(monkeypatch):
    captured = {}

    class _Proc:
        returncode = 0
        stdout = b"ok"
        stderr = b""

    def _fake_run(command, **kwargs):
        captured["command"] = command
        captured["shell"] = kwargs.get("shell")
        return _Proc()

    monkeypatch.setattr("modules.workflow_pipelines.subprocess.run", _fake_run)

    step = PipelineStep(
        id="exec2",
        step_type=StepType.EXEC,
        command="echo hi && echo there",
        metadata={"shell": True},
    )
    result = _handle_exec(step, None, {})

    assert result.success is True
    assert result.status == StepStatus.SUCCEEDED
    assert captured["shell"] is True
    assert captured["command"] == "echo hi && echo there"


def test_handle_exec_rejects_empty_command():
    step = PipelineStep(id="exec3", step_type=StepType.EXEC, command="   ")
    result = _handle_exec(step, None, {})

    assert result.success is False
    assert result.status == StepStatus.FAILED
    assert "empty command" in (result.error or "").lower()
