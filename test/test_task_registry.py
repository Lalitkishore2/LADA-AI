"""
Tests for LADA Task Registry System

Tests cover:
- Task CRUD operations
- Task lifecycle (queue, start, complete, fail, cancel)
- Pause/resume with tokens
- Persistence (survives restart)
- Task flows
- Flow templates
- Maintenance/reconciliation
"""

import pytest
import tempfile
import json
from pathlib import Path
from datetime import datetime, timedelta

from modules.tasks.task_registry import (
    TaskRegistry,
    RegistryTask,
    TaskStep,
    TaskStatus,
    TaskPriority,
    StepStatus,
    StepResult,
    StepType,
    generate_task_id,
)

from modules.tasks.task_flow_registry import (
    TaskFlowRegistry,
    TaskFlow,
    FlowStepConfig,
    FlowTemplate,
    FlowStatus,
    ExecutionMode,
)

from modules.tasks.task_maintenance import (
    TaskMaintenance,
    MaintenanceStats,
    HealthStatus,
)


class TestTaskRegistry:
    """Tests for TaskRegistry."""

    def test_create_task(self):
        """Should create a task with default values."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(
                name="test_task",
                action="do_something",
                params={"x": 1},
            )
            
            assert task.id is not None
            assert task.name == "test_task"
            assert task.action == "do_something"
            assert task.status == TaskStatus.PENDING
            assert task.params == {"x": 1}

    def test_typed_task_id_generation(self):
        """Should generate OpenClaw-style typed IDs."""
        ids = {generate_task_id("agent") for _ in range(100)}
        assert len(ids) == 100
        for task_id in ids:
            assert task_id.startswith("a")
            assert len(task_id) == 9

    def test_registry_create_uses_typed_id_for_action(self):
        """Should assign typed prefix based on action when enabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir, use_typed_ids=True)
            task = registry.create(name="agent_task", action="agent")
            assert task.id.startswith("a")
            assert len(task.id) == 9

    def test_registry_create_can_disable_typed_ids(self):
        """Should keep UUID format when typed IDs are disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir, use_typed_ids=False)
            task = registry.create(name="agent_task", action="agent")
            assert len(task.id) == 36

    def test_create_with_all_fields(self):
        """Should create task with all specified fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(
                name="full_task",
                action="complex_action",
                params={"a": 1, "b": 2},
                dependencies=["dep1", "dep2"],
                priority=TaskPriority.HIGH,
                timeout_seconds=600.0,
                agent_id="agent_1",
                session_id="sess_123",
                created_by="user",
                metadata={"key": "value"},
                tags=["tag1", "tag2"],
            )
            
            assert task.priority == TaskPriority.HIGH
            assert task.timeout_seconds == 600.0
            assert task.agent_id == "agent_1"
            assert task.dependencies == ["dep1", "dep2"]
            assert task.tags == ["tag1", "tag2"]

    def test_get_task(self):
        """Should retrieve task by ID."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            retrieved = registry.get(task.id)
            
            assert retrieved is not None
            assert retrieved.id == task.id
            assert retrieved.name == "t1"

    def test_get_nonexistent_task(self):
        """Should return None for missing task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            assert registry.get("nonexistent") is None

    def test_list_tasks_filter_by_status(self):
        """Should filter tasks by status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            t1 = registry.create(name="pending_task")
            t2 = registry.create(name="queued_task")
            registry.queue(t2.id)
            
            pending = registry.list_tasks(status=TaskStatus.PENDING)
            queued = registry.list_tasks(status=TaskStatus.QUEUED)
            
            assert len(pending) == 1
            assert pending[0].name == "pending_task"
            assert len(queued) == 1
            assert queued[0].name == "queued_task"

    def test_list_tasks_filter_by_agent(self):
        """Should filter tasks by agent_id."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            registry.create(name="t1", agent_id="agent_a")
            registry.create(name="t2", agent_id="agent_b")
            registry.create(name="t3", agent_id="agent_a")
            
            agent_a_tasks = registry.list_tasks(agent_id="agent_a")
            assert len(agent_a_tasks) == 2

    def test_delete_task(self):
        """Should delete task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="to_delete")
            assert registry.delete(task.id) is True
            assert registry.get(task.id) is None


class TestTaskLifecycle:
    """Tests for task lifecycle operations."""

    def test_queue_task(self):
        """Should queue a pending task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            assert registry.queue(task.id) is True
            assert registry.get(task.id).status == TaskStatus.QUEUED

    def test_start_task(self):
        """Should start a queued task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            registry.queue(task.id)
            
            assert registry.start(task.id) is True
            
            updated = registry.get(task.id)
            assert updated.status == TaskStatus.RUNNING
            assert updated.started_at is not None

    def test_complete_task(self):
        """Should complete a task with result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            registry.queue(task.id)
            registry.start(task.id)
            
            result = {"output": "success"}
            assert registry.complete(task.id, result) is True
            
            updated = registry.get(task.id)
            assert updated.status == TaskStatus.COMPLETED
            assert updated.result == result
            assert updated.progress == 1.0

    def test_fail_task(self):
        """Should fail a task with error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            registry.queue(task.id)
            registry.start(task.id)
            
            assert registry.fail(task.id, "Something went wrong") is True
            
            updated = registry.get(task.id)
            assert updated.status == TaskStatus.FAILED
            assert updated.error == "Something went wrong"

    def test_cancel_task(self):
        """Should cancel a non-terminal task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            registry.queue(task.id)
            
            assert registry.cancel(task.id, "User requested") is True
            
            updated = registry.get(task.id)
            assert updated.status == TaskStatus.CANCELLED
            assert updated.error == "User requested"

    def test_retry_failed_task(self):
        """Should retry a failed task."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1", params={"max_retries": 3})
            task.max_retries = 3
            registry.update(task)
            
            registry.queue(task.id)
            registry.start(task.id)
            registry.fail(task.id, "First attempt failed")
            
            assert registry.retry(task.id) is True
            
            updated = registry.get(task.id)
            assert updated.status == TaskStatus.PENDING
            assert updated.retry_count == 1


class TestPauseResume:
    """Tests for pause/resume functionality."""

    def test_pause_running_task(self):
        """Should pause a running task and return token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            registry.queue(task.id)
            registry.start(task.id)
            
            token = registry.pause(task.id)
            
            assert token is not None
            assert len(token) == 8  # Short token
            
            updated = registry.get(task.id)
            assert updated.status == TaskStatus.PAUSED
            assert updated.resume_token == token

    def test_resume_by_token(self):
        """Should resume task using token."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            registry.queue(task.id)
            registry.start(task.id)
            
            token = registry.pause(task.id)
            resumed = registry.resume(token)
            
            assert resumed is not None
            assert resumed.status == TaskStatus.RUNNING
            assert resumed.resume_token is None  # Token consumed

    def test_resume_approval_denied(self):
        """Should cancel task when approval is denied."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            registry.queue(task.id)
            registry.start(task.id)
            
            token = registry.await_approval(task.id, "step1", "Approve this?")
            resumed = registry.resume(token, approved=False)
            
            assert resumed.status == TaskStatus.CANCELLED
            assert "denied" in resumed.error.lower()

    def test_token_persists_to_disk(self):
        """Paused state should be saved to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="t1")
            registry.queue(task.id)
            registry.start(task.id)
            
            token = registry.pause(task.id)
            
            # Check file exists
            paused_file = Path(tmpdir) / "paused" / f"{token}.json"
            assert paused_file.exists()

    def test_resume_from_disk_after_restart(self):
        """Should resume task from disk after registry restart."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and pause
            registry1 = TaskRegistry(tasks_dir=tmpdir)
            task = registry1.create(name="t1")
            registry1.queue(task.id)
            registry1.start(task.id)
            token = registry1.pause(task.id)
            task_id = task.id
            
            # Simulate restart with new registry
            registry2 = TaskRegistry(tasks_dir=tmpdir)
            
            # Resume should work
            resumed = registry2.resume(token)
            assert resumed is not None
            assert resumed.id == task_id
            assert resumed.status == TaskStatus.RUNNING


class TestTaskPersistence:
    """Tests for task persistence."""

    def test_active_tasks_persist(self):
        """Active tasks should persist to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry1 = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry1.create(name="persistent_task")
            registry1.queue(task.id)
            task_id = task.id
            
            # New registry should load
            registry2 = TaskRegistry(tasks_dir=tmpdir)
            loaded = registry2.get(task_id)
            
            assert loaded is not None
            assert loaded.name == "persistent_task"
            assert loaded.status == TaskStatus.QUEUED

    def test_history_persists(self):
        """Completed tasks should be in history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry1 = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry1.create(name="history_task")
            registry1.queue(task.id)
            registry1.start(task.id)
            registry1.complete(task.id, "done")
            
            # New registry should have history
            registry2 = TaskRegistry(tasks_dir=tmpdir)
            history = registry2.get_history()
            
            assert len(history) >= 1
            assert any(h["name"] == "history_task" for h in history)


class TestDependencies:
    """Tests for task dependency handling."""

    def test_check_dependencies_no_deps(self):
        """Task with no dependencies should pass check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            task = registry.create(name="no_deps")
            assert registry.check_dependencies(task.id) is True

    def test_check_dependencies_incomplete(self):
        """Task with incomplete dependencies should fail check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            dep = registry.create(name="dependency")
            task = registry.create(name="dependent", dependencies=[dep.id])
            
            assert registry.check_dependencies(task.id) is False

    def test_check_dependencies_complete(self):
        """Task with completed dependencies should pass check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            dep = registry.create(name="dependency")
            registry.queue(dep.id)
            registry.start(dep.id)
            registry.complete(dep.id, "done")
            
            task = registry.create(name="dependent", dependencies=[dep.id])
            assert registry.check_dependencies(task.id) is True

    def test_get_ready_tasks(self):
        """Should return tasks ready for execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TaskRegistry(tasks_dir=tmpdir)
            
            # Task with no deps (ready)
            t1 = registry.create(name="t1")
            
            # Task with deps (not ready)
            dep = registry.create(name="dep")
            t2 = registry.create(name="t2", dependencies=[dep.id])
            
            ready = registry.get_ready_tasks()
            ready_ids = [t.id for t in ready]
            
            assert t1.id in ready_ids
            assert t2.id not in ready_ids


class TestTaskFlowRegistry:
    """Tests for TaskFlowRegistry."""

    def test_create_flow(self):
        """Should create a flow with steps."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            
            steps = [
                FlowStepConfig(id="s1", name="Step 1", action="action1"),
                FlowStepConfig(id="s2", name="Step 2", action="action2"),
            ]
            
            flow = flow_reg.create_flow(name="test_flow", steps=steps)
            
            assert flow.id is not None
            assert flow.name == "test_flow"
            assert flow.total_steps == 2
            assert flow.status == FlowStatus.PENDING

    def test_start_flow(self):
        """Should start flow execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            
            steps = [FlowStepConfig(id="s1", name="Step", action="test")]
            flow = flow_reg.create_flow(name="test_flow", steps=steps)
            
            assert flow_reg.start_flow(flow.id) is True
            
            updated = flow_reg.get_flow(flow.id)
            assert updated.status == FlowStatus.RUNNING
            assert updated.current_step_id == "s1"

    def test_complete_step_sequential(self):
        """Should advance to next step in sequential mode."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            
            steps = [
                FlowStepConfig(id="s1", name="Step 1", action="a1"),
                FlowStepConfig(id="s2", name="Step 2", action="a2"),
            ]
            flow = flow_reg.create_flow(name="flow", steps=steps)
            flow_reg.start_flow(flow.id)
            
            result1 = StepResult(step_id="s1", status=StepStatus.SUCCEEDED)
            next_step = flow_reg.complete_step(flow.id, "s1", result1)
            
            assert next_step == "s2"
            
            result2 = StepResult(step_id="s2", status=StepStatus.SUCCEEDED)
            next_step = flow_reg.complete_step(flow.id, "s2", result2)
            
            assert next_step is None
            
            flow = flow_reg.get_flow(flow.id)
            assert flow.status == FlowStatus.COMPLETED

    def test_flow_fails_on_step_failure(self):
        """Flow should fail when step fails (stop_on_failure=True)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            
            steps = [
                FlowStepConfig(id="s1", name="Step 1", action="a1"),
                FlowStepConfig(id="s2", name="Step 2", action="a2"),
            ]
            flow = flow_reg.create_flow(
                name="flow", 
                steps=steps,
                stop_on_failure=True,
            )
            flow_reg.start_flow(flow.id)
            
            result = StepResult(
                step_id="s1", 
                status=StepStatus.FAILED, 
                error="Step failed",
            )
            next_step = flow_reg.complete_step(flow.id, "s1", result)
            
            assert next_step is None
            
            flow = flow_reg.get_flow(flow.id)
            assert flow.status == FlowStatus.FAILED

    def test_flow_outputs_capture(self):
        """Flow should capture step outputs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            
            steps = [
                FlowStepConfig(id="s1", name="Step", action="test"),
            ]
            flow = flow_reg.create_flow(name="flow", steps=steps)
            flow_reg.start_flow(flow.id)
            
            result = StepResult(
                step_id="s1",
                status=StepStatus.SUCCEEDED,
                return_value="output_value",
            )
            flow_reg.complete_step(flow.id, "s1", result)
            
            flow = flow_reg.get_flow(flow.id)
            assert flow.outputs["s1"] == "output_value"


class TestFlowTemplates:
    """Tests for flow templates."""

    def test_create_template(self):
        """Should create a flow template."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            
            steps = [
                FlowStepConfig(id="s1", name="Template Step", action="tmpl_action"),
            ]
            
            template = flow_reg.create_template(
                name="my_template",
                steps=steps,
                description="A test template",
            )
            
            assert template.id is not None
            assert template.name == "my_template"
            assert len(template.steps) == 1

    def test_create_flow_from_template(self):
        """Should create flow from template."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            
            steps = [
                FlowStepConfig(id="s1", name="Step", action="action"),
            ]
            template = flow_reg.create_template(name="template", steps=steps)
            
            flow = flow_reg.create_flow_from_template(template.id)
            
            assert flow is not None
            assert flow.template_id == template.id
            assert flow.total_steps == 1


class TestTaskMaintenance:
    """Tests for task maintenance."""

    def test_startup_reconcile_resets_stale_running(self):
        """Should reset stale RUNNING tasks to PENDING."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            
            # Create and start a task
            task = task_reg.create(name="stale_task")
            task_reg.queue(task.id)
            task_reg.start(task.id)
            task_id = task.id
            
            # Simulate restart (task stuck in RUNNING)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            maint = TaskMaintenance(
                task_registry=task_reg,
                flow_registry=flow_reg,
            )
            
            stats = maint.startup_reconcile()
            
            assert stats.stale_tasks_reset >= 1
            assert task_reg.get(task_id).status == TaskStatus.PENDING

    def test_get_health(self):
        """Should return health status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            maint = TaskMaintenance(
                task_registry=task_reg,
                flow_registry=flow_reg,
            )
            
            # Create some tasks
            task_reg.create(name="t1")
            task_reg.create(name="t2")
            
            health = maint.get_health()
            
            assert health.healthy is True
            assert health.total_tasks >= 2

    def test_get_metrics(self):
        """Should return metrics."""
        with tempfile.TemporaryDirectory() as tmpdir:
            task_reg = TaskRegistry(tasks_dir=tmpdir)
            flow_reg = TaskFlowRegistry(flows_dir=tmpdir, task_registry=task_reg)
            maint = TaskMaintenance(
                task_registry=task_reg,
                flow_registry=flow_reg,
            )
            
            metrics = maint.get_metrics()
            
            assert "health" in metrics
            assert "cleanup_interval" in metrics


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
