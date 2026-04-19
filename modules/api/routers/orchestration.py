"""
LADA API — Orchestration routes (/plans/*, /workflows/*, /tasks/*, /skills/*, /registry/*)
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Body, BackgroundTasks, Request, Response, Depends
from modules.api.deps import set_request_id_header
from modules.error_sanitizer import safe_error_response

logger = logging.getLogger(__name__)


def create_orchestration_router(state):
    """Create plan/workflow/task/skill router."""
    async def _trace_request(request: Request, response: Response):
        set_request_id_header(request, response, prefix="orchestration")

    r = APIRouter(tags=["orchestration"], dependencies=[Depends(_trace_request)])

    def _raise_sanitized_error(exc: Exception, operation: str, *, status_code: int = 500) -> None:
        error_info = safe_error_response(exc, operation=operation)
        logger.error(f"[APIServer] {operation} error: {type(exc).__name__}")
        raise HTTPException(status_code=status_code, detail=error_info["error"])

    def _progress_percent(value: Any) -> str:
        try:
            progress = float(value)
        except (TypeError, ValueError):
            progress = 0.0
        if progress <= 1.0:
            progress *= 100.0
        progress = max(0.0, min(progress, 100.0))
        return f"{int(progress)}%"

    def _legacy_active_from_registry(task_data: Dict[str, Any]) -> Dict[str, Any]:
        steps = task_data.get("steps", [])
        total_steps = len(steps) if isinstance(steps, list) and steps else 1
        current_index = task_data.get("current_step_index", 0)
        try:
            current_step = int(current_index)
        except (TypeError, ValueError):
            current_step = 0
        current_step = max(0, min(current_step, total_steps))
        return {
            "execution_id": task_data.get("id", ""),
            "task_name": task_data.get("name", ""),
            "status": task_data.get("status", "pending"),
            "progress": _progress_percent(task_data.get("progress", 0.0)),
            "current_step": f"{current_step}/{total_steps}",
            "started_at": task_data.get("started_at"),
        }

    def _legacy_completed_from_registry(task_data: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "execution_id": task_data.get("id", ""),
            "task_name": task_data.get("name", ""),
            "status": task_data.get("status", "completed"),
            "started_at": task_data.get("started_at"),
            "completed_at": task_data.get("completed_at"),
            "error": task_data.get("error"),
        }

    def _merge_task_entries(primary: List[Dict[str, Any]], fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()
        for entry in primary + fallback:
            if not isinstance(entry, dict):
                continue
            execution_id = str(entry.get("execution_id", "")).strip()
            dedupe_key = execution_id or str(entry.get("task_name", "")).strip()
            if dedupe_key and dedupe_key in seen:
                continue
            if dedupe_key:
                seen.add(dedupe_key)
            merged.append(entry)
        return merged

    def _list_registry_tasks_for_legacy(limit: int = 20) -> Dict[str, Any]:
        from modules.tasks import get_registry

        registry = get_registry()
        active_tasks = [_legacy_active_from_registry(task.to_dict()) for task in registry.list_tasks(active_only=True)]
        history = [_legacy_completed_from_registry(entry) for entry in registry.get_history(limit=limit)]
        return {
            "active": active_tasks,
            "completed": history,
            "active_count": len(active_tasks),
            "completed_count": len(history),
        }

    def _legacy_workflow_from_registry(flow_data: Dict[str, Any], actions: List[str]) -> Dict[str, Any]:
        return {
            "name": flow_data.get("name") or flow_data.get("id", ""),
            "steps": int(flow_data.get("total_steps", 0) or 0),
            "actions": actions,
            "status": flow_data.get("status", "pending"),
            "flow_id": flow_data.get("id"),
            "source": "registry",
        }

    def _list_registry_workflows_for_legacy() -> List[Dict[str, Any]]:
        from modules.tasks import get_flow_registry

        flow_registry = get_flow_registry()
        workflows: List[Dict[str, Any]] = []
        for flow in flow_registry.list_flows():
            flow_data = flow.to_dict()
            flow_task = flow_registry.get_task(flow.id)
            actions: List[str] = []
            if flow_task and getattr(flow_task, "steps", None):
                actions = [str(step.action) for step in flow_task.steps if getattr(step, "action", None)]
            workflows.append(_legacy_workflow_from_registry(flow_data, actions))
        return workflows

    def _merge_workflow_lists(primary: List[Dict[str, Any]], fallback: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: List[Dict[str, Any]] = []
        seen = set()
        for workflow in primary + fallback:
            if not isinstance(workflow, dict):
                continue
            name = str(workflow.get("name", "")).strip()
            flow_id = str(workflow.get("flow_id", workflow.get("id", ""))).strip()
            dedupe_key = name or flow_id
            if dedupe_key and dedupe_key in seen:
                continue
            if dedupe_key:
                seen.add(dedupe_key)
            merged.append(workflow)
        return merged

    def _registry_task_status_payload(task_data: Dict[str, Any]) -> Dict[str, Any]:
        payload = _legacy_active_from_registry(task_data)
        payload["completed_at"] = task_data.get("completed_at")
        payload["error"] = task_data.get("error")
        payload["result"] = task_data.get("result")
        return payload

    @r.get("/orchestrator/subscriptions")
    async def get_orchestrator_subscriptions(include_sessions: bool = Query(True)):
        """Return current orchestrator WS event-stream subscription status."""
        state.load_components()

        subscribers = list(getattr(state, 'ws_orchestrator_subscribers', set()))
        filter_map = getattr(state, 'ws_orchestrator_subscription_filters', {})
        sessions = getattr(state, 'ws_sessions', {})
        connections = getattr(state, 'ws_connections', {})

        payload = {
            "enabled": bool(getattr(state, '_standalone_orchestrator_enabled', False)),
            "orchestrator_available": bool(getattr(state, 'orchestrator', None)),
            "stream_active": bool(getattr(state, 'ws_orchestrator_bus_subscription_token', None)),
            "subscriber_count": len(subscribers),
        }

        if include_sessions:
            entries = []
            for session_id in subscribers:
                session = sessions.get(session_id, {})
                raw_filters = filter_map.get(session_id, {})

                serialized_filters = {}
                if isinstance(raw_filters, dict):
                    for key, value in raw_filters.items():
                        if isinstance(value, set):
                            if value:
                                serialized_filters[key] = sorted(value)
                        elif isinstance(value, (list, tuple)):
                            if value:
                                serialized_filters[key] = [str(v) for v in value]
                        elif value:
                            serialized_filters[key] = [str(value)]

                entries.append({
                    "session_id": session_id,
                    "connected": session_id in connections,
                    "orchestrator_events": bool(session.get("orchestrator_events", False)),
                    "messages_sent": int(session.get("messages_sent", 0)),
                    "messages_received": int(session.get("messages_received", 0)),
                    "last_activity": session.get("last_activity"),
                    "filters": serialized_filters,
                })

            payload["sessions"] = entries

        return payload

    @r.post("/orchestrator/dispatch")
    async def dispatch_orchestrator_command(body: dict = Body(default={})):
        """Dispatch a command envelope through the standalone orchestrator."""
        state.load_components()

        orchestrator = getattr(state, 'orchestrator', None)
        if not orchestrator:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Standalone orchestrator is not enabled. "
                    "Set LADA_STANDALONE_ORCHESTRATOR=true to enable it."
                ),
            )

        from modules.standalone.contracts import CommandEnvelope

        wait_for_result = bool(body.get("wait", True))
        timeout_ms = int(body.get("timeout_ms", body.get("timeout", 60000)))

        envelope_data = body.get("envelope")
        if isinstance(envelope_data, dict):
            raw_envelope = dict(envelope_data)
        else:
            raw_envelope = {
                "source": body.get("source", "api"),
                "target": body.get("target", "system"),
                "action": body.get("action", ""),
                "payload": body.get("payload", {}),
                "timeout_ms": timeout_ms,
                "metadata": body.get("metadata", {}),
                "idempotency_key": body.get("idempotency_key"),
            }

        if "source" not in raw_envelope:
            raw_envelope["source"] = "api"
        if "timeout_ms" not in raw_envelope:
            raw_envelope["timeout_ms"] = timeout_ms

        try:
            envelope = CommandEnvelope.from_dict(raw_envelope)
        except Exception as e:
            logger.warning(f"[APIServer] Invalid command envelope: {type(e).__name__}")
            raise HTTPException(status_code=400, detail="Invalid command envelope")

        try:
            event = orchestrator.submit(
                envelope,
                wait_for_result=wait_for_result,
                timeout_ms=timeout_ms,
            )
        except Exception as e:
            _raise_sanitized_error(e, "orchestrator_dispatch", status_code=500)

        response = {
            "success": True,
            "accepted": True,
            "status": "accepted",
            "command": envelope.to_dict(),
        }

        if event is not None:
            response["status"] = event.status
            response["event_type"] = event.event_type
            response["result_event"] = event.to_dict()

        return response

    # ── Plans ────────────────────────────────────────────────

    @r.post("/plans")
    async def create_plan(body: dict = Body(default={})):
        state.load_components()
        task = body.get("task", "").strip()
        context = body.get("context", "")
        if not task:
            raise HTTPException(status_code=400, detail="Task description required")
        planner = getattr(state.jarvis, 'advanced_planner', None) if state.jarvis else None
        if not planner:
            raise HTTPException(status_code=503, detail="Planner not available")
        try:
            loop = asyncio.get_event_loop()
            plan = await loop.run_in_executor(None, lambda: planner.create_plan(task, context))
            return {"success": True, "plan": plan.to_dict()}
        except Exception as e:
            _raise_sanitized_error(e, "create_plan", status_code=500)

    @r.get("/plans")
    async def list_plans(count: int = Query(10)):
        state.load_components()
        planner = getattr(state.jarvis, 'advanced_planner', None) if state.jarvis else None
        if not planner:
            return {"plans": [], "count": 0}
        plans = planner.get_recent_plans(count)
        return {"plans": [p.to_dict() for p in plans], "count": len(plans)}

    @r.get("/plans/{plan_id}")
    async def get_plan(plan_id: str):
        state.load_components()
        planner = getattr(state.jarvis, 'advanced_planner', None) if state.jarvis else None
        if not planner:
            raise HTTPException(status_code=503, detail="Planner not available")
        plan = planner.get_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")
        return {"success": True, "plan": plan.to_dict()}

    @r.post("/plans/{plan_id}/execute")
    async def execute_plan(plan_id: str, background_tasks: BackgroundTasks):
        state.load_components()
        planner = getattr(state.jarvis, 'advanced_planner', None) if state.jarvis else None
        if not planner:
            raise HTTPException(status_code=503, detail="Planner not available")
        plan = planner.get_plan(plan_id)
        if not plan:
            raise HTTPException(status_code=404, detail="Plan not found")

        def run_plan():
            try:
                planner.execute_plan(plan)
            except Exception as e:
                logger.error(f"[APIServer] Plan execution error: {e}")

        background_tasks.add_task(run_plan)
        return {"success": True, "plan_id": plan_id, "status": "executing"}

    @r.delete("/plans/{plan_id}")
    async def cancel_plan(plan_id: str):
        state.load_components()
        planner = getattr(state.jarvis, 'advanced_planner', None) if state.jarvis else None
        if not planner:
            raise HTTPException(status_code=503, detail="Planner not available")
        planner.cancel()
        return {"success": True, "plan_id": plan_id, "status": "cancelled"}

    # ── Workflows ────────────────────────────────────────────

    @r.get("/workflows")
    async def list_workflows():
        state.load_components()
        registry_workflows: List[Dict[str, Any]] = []
        try:
            registry_workflows = _list_registry_workflows_for_legacy()
        except Exception as e:
            logger.warning(f"[APIServer] list_workflows registry fallback: {type(e).__name__}")

        wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
        legacy_workflows = wf.list_workflows() if wf else []
        merged_workflows = _merge_workflow_lists(registry_workflows, legacy_workflows)
        return {"workflows": merged_workflows, "count": len(merged_workflows)}

    @r.post("/workflows")
    async def create_workflow(body: dict = Body(default={})):
        state.load_components()
        name = body.get("name", "").strip()
        steps = body.get("steps", [])
        if not name or not steps:
            raise HTTPException(status_code=400, detail="Workflow name and steps required")
        wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
        if not wf:
            raise HTTPException(status_code=503, detail="Workflow engine not available")
        success = wf.register_workflow(name, steps)
        return {"success": success, "name": name, "steps": len(steps)}

    @r.post("/workflows/{name}/execute")
    async def execute_workflow(name: str, body: dict = Body(default={})):
        state.load_components()
        wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
        if not wf:
            raise HTTPException(status_code=503, detail="Workflow engine not available")
        context = body.get("context", {})
        try:
            result = await wf.execute_workflow(name, context)
            return {
                "success": result.success, "workflow_name": result.workflow_name,
                "steps_completed": result.steps_completed, "total_steps": result.total_steps,
                "duration_seconds": result.duration_seconds, "results": result.results,
                "error": result.error,
            }
        except Exception as e:
            _raise_sanitized_error(e, "execute_workflow", status_code=500)

    @r.get("/workflows/history")
    async def workflow_history(limit: int = Query(10)):
        state.load_components()
        wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
        if not wf:
            return {"history": [], "count": 0}
        history = wf.get_workflow_history(limit)
        return {
            "history": [
                {"success": r.success, "workflow_name": r.workflow_name,
                 "steps_completed": r.steps_completed, "total_steps": r.total_steps,
                 "duration_seconds": r.duration_seconds, "error": r.error}
                for r in history
            ],
            "count": len(history),
        }

    # ── Tasks ────────────────────────────────────────────────

    @r.get("/tasks")
    async def list_tasks():
        state.load_components()
        registry_payload = {"active": [], "completed": [], "active_count": 0, "completed_count": 0}
        try:
            registry_payload = _list_registry_tasks_for_legacy(limit=20)
        except Exception as e:
            logger.warning(f"[APIServer] list_tasks registry fallback: {type(e).__name__}")

        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        active = tc.get_active_tasks() if tc else {}
        completed = tc.get_completed_tasks(20) if tc else {}
        legacy_payload = {
            "active": active.get("active_tasks", []),
            "completed": completed.get("completed_tasks", []),
            "active_count": active.get("count", 0),
            "completed_count": completed.get("count", 0),
        }
        merged_active = _merge_task_entries(registry_payload.get("active", []), legacy_payload["active"])
        merged_completed = _merge_task_entries(registry_payload.get("completed", []), legacy_payload["completed"])
        return {
            "active": merged_active,
            "completed": merged_completed,
            "active_count": len(merged_active),
            "completed_count": len(merged_completed),
        }

    @r.post("/tasks")
    async def create_task(body: dict = Body(default={})):
        state.load_components()
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if not tc:
            raise HTTPException(status_code=503, detail="Task automation not available")
        command = body.get("command", "").strip()
        if command:
            task_def = tc.parse_complex_command(command)
            return tc.execute_task(task_def)
        template = body.get("template", "").strip()
        if template:
            return tc.execute_template(template)
        raise HTTPException(status_code=400, detail="Provide 'command' or 'template'")

    @r.get("/tasks/{execution_id}")
    async def get_task_status(execution_id: str):
        state.load_components()
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if tc:
            return tc.get_task_status(execution_id)
        try:
            from modules.tasks import get_registry

            task = get_registry().get(execution_id)
            if not task:
                raise HTTPException(status_code=404, detail=f"Task '{execution_id}' not found")
            return _registry_task_status_payload(task.to_dict())
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "get_task_status", status_code=500)

    @r.post("/tasks/{execution_id}/pause")
    async def pause_task(execution_id: str):
        state.load_components()
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if tc:
            return tc.pause_task(execution_id)
        try:
            from modules.tasks import get_registry

            token = get_registry().pause(execution_id)
            if not token:
                raise HTTPException(status_code=400, detail="Cannot pause task")
            return {"success": True, "execution_id": execution_id, "status": "paused", "resume_token": token}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "pause_task", status_code=500)

    @r.post("/tasks/{execution_id}/resume")
    async def resume_task(execution_id: str):
        state.load_components()
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if tc:
            return tc.resume_task(execution_id)
        try:
            from modules.tasks import get_registry

            registry = get_registry()
            resumed = registry.resume(execution_id)
            if not resumed:
                existing = registry.get(execution_id)
                if existing and existing.resume_token:
                    resumed = registry.resume(existing.resume_token)
            if not resumed:
                raise HTTPException(status_code=404, detail="Task or resume token not found")
            return {
                "success": True,
                "execution_id": resumed.id,
                "status": resumed.status.value,
                "resume_token": resumed.resume_token,
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "resume_task", status_code=500)

    @r.post("/tasks/{execution_id}/cancel")
    async def cancel_task(execution_id: str):
        state.load_components()
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if tc:
            return tc.cancel_task(execution_id)
        try:
            from modules.tasks import get_registry

            if not get_registry().cancel(execution_id):
                raise HTTPException(status_code=400, detail="Cannot cancel task")
            return {"success": True, "execution_id": execution_id, "status": "cancelled"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "cancel_task", status_code=500)

    # ── Skills ───────────────────────────────────────────────

    @r.post("/skills/generate")
    async def generate_skill(body: dict = Body(default={})):
        state.load_components()
        description = body.get("description", "").strip()
        name = body.get("name")
        if not description:
            raise HTTPException(status_code=400, detail="Skill description required")
        sg = getattr(state.jarvis, 'skill_generator', None) if state.jarvis else None
        if not sg:
            raise HTTPException(status_code=503, detail="Skill generator not available")
        try:
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, lambda: sg.generate(description, name))
            if result.get("success"):
                return result
            raise HTTPException(status_code=500, detail=result.get("error", "Generation failed"))
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "generate_skill", status_code=500)

    @r.get("/skills")
    async def list_skills():
        state.load_components()
        sg = getattr(state.jarvis, 'skill_generator', None) if state.jarvis else None
        if not sg:
            return {"skills": [], "count": 0}
        skills = sg.list_generated()
        return {"skills": skills, "count": len(skills)}

    @r.delete("/skills/{name}")
    async def delete_skill(name: str):
        state.load_components()
        sg = getattr(state.jarvis, 'skill_generator', None) if state.jarvis else None
        if not sg:
            raise HTTPException(status_code=503, detail="Skill generator not available")
        if sg.delete_skill(name):
            return {"success": True, "name": name}
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")

    # ── Unified Task Registry ─────────────────────────────────
    # New endpoints for the unified task registry system

    @r.get("/registry/tasks")
    async def list_registry_tasks(
        agent_id: Optional[str] = Query(None, description="Filter by agent ID"),
        status: Optional[str] = Query(None, description="Filter by status"),
        active_only: bool = Query(False, description="Only active tasks"),
        tag: Optional[str] = Query(None, description="Filter by tag"),
    ):
        """List tasks from the unified registry."""
        try:
            from modules.tasks import get_registry, TaskStatus
            
            registry = get_registry()
            status_enum = TaskStatus(status) if status else None
            
            tasks = registry.list_tasks(
                agent_id=agent_id,
                status=status_enum,
                active_only=active_only,
                tag=tag,
            )
            
            return {
                "tasks": [t.to_dict() for t in tasks],
                "count": len(tasks),
            }
        except Exception as e:
            _raise_sanitized_error(e, "list_registry_tasks", status_code=500)

    @r.post("/registry/tasks")
    async def create_registry_task(body: dict = Body(default={})):
        """Create a task in the unified registry."""
        try:
            from modules.tasks import get_registry, TaskPriority
            
            name = body.get("name", "").strip()
            if not name:
                raise HTTPException(status_code=400, detail="Task name required")
            
            registry = get_registry()
            
            priority_str = body.get("priority", "normal").lower()
            priority = TaskPriority(priority_str)
            
            task = registry.create(
                name=name,
                action=body.get("action"),
                params=body.get("params", {}),
                dependencies=body.get("dependencies", []),
                priority=priority,
                timeout_seconds=body.get("timeout_seconds", 3600.0),
                agent_id=body.get("agent_id", "default"),
                session_id=body.get("session_id"),
                metadata=body.get("metadata", {}),
                tags=body.get("tags", []),
            )
            
            # Auto-queue if requested
            if body.get("auto_queue", False):
                registry.queue(task.id)
            
            return {"success": True, "task": task.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "create_registry_task", status_code=500)

    @r.get("/registry/tasks/{task_id}")
    async def get_registry_task(task_id: str):
        """Get task details from the unified registry."""
        try:
            from modules.tasks import get_registry
            
            registry = get_registry()
            task = registry.get(task_id)
            
            if not task:
                raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
            
            return {"task": task.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "get_registry_task", status_code=500)

    @r.post("/registry/tasks/{task_id}/queue")
    async def queue_registry_task(task_id: str):
        """Queue a task for execution."""
        try:
            from modules.tasks import get_registry
            
            registry = get_registry()
            if not registry.queue(task_id):
                raise HTTPException(status_code=400, detail="Cannot queue task")
            
            return {"success": True, "task_id": task_id, "status": "queued"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "queue_registry_task", status_code=500)

    @r.post("/registry/tasks/{task_id}/start")
    async def start_registry_task(task_id: str):
        """Start task execution."""
        try:
            from modules.tasks import get_registry
            
            registry = get_registry()
            if not registry.start(task_id):
                raise HTTPException(status_code=400, detail="Cannot start task")
            
            return {"success": True, "task_id": task_id, "status": "running"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "start_registry_task", status_code=500)

    @r.post("/registry/tasks/{task_id}/complete")
    async def complete_registry_task(task_id: str, body: dict = Body(default={})):
        """Mark task as completed."""
        try:
            from modules.tasks import get_registry
            
            registry = get_registry()
            result = body.get("result")
            
            if not registry.complete(task_id, result):
                raise HTTPException(status_code=400, detail="Cannot complete task")
            
            return {"success": True, "task_id": task_id, "status": "completed"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "complete_registry_task", status_code=500)

    @r.post("/registry/tasks/{task_id}/fail")
    async def fail_registry_task(task_id: str, body: dict = Body(default={})):
        """Mark task as failed."""
        try:
            from modules.tasks import get_registry
            
            registry = get_registry()
            error = body.get("error", "Unknown error")
            
            if not registry.fail(task_id, error):
                raise HTTPException(status_code=400, detail="Cannot fail task")
            
            return {"success": True, "task_id": task_id, "status": "failed"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "fail_registry_task", status_code=500)

    @r.post("/registry/tasks/{task_id}/pause")
    async def pause_registry_task(task_id: str, body: dict = Body(default={})):
        """Pause task and get resume token."""
        try:
            from modules.tasks import get_registry
            
            registry = get_registry()
            step_id = body.get("step_id")
            expires_hours = body.get("expires_hours", 24)
            
            token = registry.pause(task_id, step_id, expires_hours)
            if not token:
                raise HTTPException(status_code=400, detail="Cannot pause task")
            
            return {"success": True, "task_id": task_id, "resume_token": token}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "pause_registry_task", status_code=500)

    @r.post("/registry/tasks/{task_id}/cancel")
    async def cancel_registry_task(task_id: str, body: dict = Body(default={})):
        """Cancel a task."""
        try:
            from modules.tasks import get_registry
            
            registry = get_registry()
            reason = body.get("reason")
            
            if not registry.cancel(task_id, reason):
                raise HTTPException(status_code=400, detail="Cannot cancel task")
            
            return {"success": True, "task_id": task_id, "status": "cancelled"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "cancel_registry_task", status_code=500)

    @r.post("/registry/resume/{token}")
    async def resume_by_token(token: str, body: dict = Body(default={})):
        """Resume a paused task by token."""
        try:
            from modules.tasks import get_registry
            
            registry = get_registry()
            approved = body.get("approved", True)
            
            task = registry.resume(token, approved)
            if not task:
                raise HTTPException(status_code=404, detail="Invalid or expired token")
            
            return {"success": True, "task": task.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "resume_by_token", status_code=500)

    @r.get("/registry/history")
    async def get_registry_history(
        agent_id: Optional[str] = Query(None),
        limit: int = Query(100),
        status: Optional[str] = Query(None),
    ):
        """Get task history."""
        try:
            from modules.tasks import get_registry, TaskStatus
            
            registry = get_registry()
            status_enum = TaskStatus(status) if status else None
            
            history = registry.get_history(
                agent_id=agent_id,
                limit=limit,
                status=status_enum,
            )
            
            return {"history": history, "count": len(history)}
        except Exception as e:
            _raise_sanitized_error(e, "get_registry_history", status_code=500)

    @r.get("/registry/ready")
    async def get_ready_tasks(agent_id: Optional[str] = Query(None)):
        """Get tasks ready for execution (all dependencies met)."""
        try:
            from modules.tasks import get_registry
            
            registry = get_registry()
            tasks = registry.get_ready_tasks(agent_id)
            
            return {"tasks": [t.to_dict() for t in tasks], "count": len(tasks)}
        except Exception as e:
            _raise_sanitized_error(e, "get_ready_tasks", status_code=500)

    # ── Task Flows ────────────────────────────────────────────

    @r.get("/registry/flows")
    async def list_flows(
        agent_id: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        active_only: bool = Query(False),
    ):
        """List task flows."""
        try:
            from modules.tasks import get_flow_registry, FlowStatus
            
            flow_registry = get_flow_registry()
            status_enum = FlowStatus(status) if status else None
            
            flows = flow_registry.list_flows(
                agent_id=agent_id,
                status=status_enum,
                active_only=active_only,
            )
            
            return {"flows": [f.to_dict() for f in flows], "count": len(flows)}
        except Exception as e:
            _raise_sanitized_error(e, "list_flows", status_code=500)

    @r.post("/registry/flows")
    async def create_flow(body: dict = Body(default={})):
        """Create a multi-step flow."""
        try:
            from modules.tasks import get_flow_registry, FlowStepConfig, ExecutionMode, StepType
            
            name = body.get("name", "").strip()
            steps_data = body.get("steps", [])
            
            if not name or not steps_data:
                raise HTTPException(status_code=400, detail="Flow name and steps required")
            
            flow_registry = get_flow_registry()
            
            # Convert step dicts
            steps = []
            for i, s in enumerate(steps_data):
                step = FlowStepConfig(
                    id=s.get("id", f"step_{i+1}"),
                    name=s.get("name", f"Step {i+1}"),
                    step_type=StepType(s.get("step_type", "function")),
                    action=s.get("action", ""),
                    parameters=s.get("parameters", {}),
                    timeout_seconds=s.get("timeout_seconds", 300),
                    retries=s.get("retries", 3),
                    continue_on_error=s.get("continue_on_error", False),
                    dependencies=s.get("dependencies", []),
                    approval_message=s.get("approval_message"),
                )
                steps.append(step)
            
            mode_str = body.get("execution_mode", "sequential")
            mode = ExecutionMode(mode_str)
            
            flow = flow_registry.create_flow(
                name=name,
                steps=steps,
                execution_mode=mode,
                stop_on_failure=body.get("stop_on_failure", True),
                agent_id=body.get("agent_id", "default"),
                session_id=body.get("session_id"),
                metadata=body.get("metadata", {}),
            )
            
            return {"success": True, "flow": flow.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "create_flow", status_code=500)

    @r.get("/registry/flows/{flow_id}")
    async def get_flow(flow_id: str):
        """Get flow details."""
        try:
            from modules.tasks import get_flow_registry
            
            flow_registry = get_flow_registry()
            flow = flow_registry.get_flow(flow_id)
            
            if not flow:
                raise HTTPException(status_code=404, detail=f"Flow '{flow_id}' not found")
            
            task = flow_registry.get_task(flow_id)
            
            return {
                "flow": flow.to_dict(),
                "task": task.to_dict() if task else None,
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "get_flow", status_code=500)

    @r.post("/registry/flows/{flow_id}/start")
    async def start_flow(flow_id: str):
        """Start flow execution."""
        try:
            from modules.tasks import get_flow_registry
            
            flow_registry = get_flow_registry()
            if not flow_registry.start_flow(flow_id):
                raise HTTPException(status_code=400, detail="Cannot start flow")
            
            return {"success": True, "flow_id": flow_id, "status": "running"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "start_flow", status_code=500)

    @r.post("/registry/flows/{flow_id}/cancel")
    async def cancel_flow(flow_id: str, body: dict = Body(default={})):
        """Cancel a flow."""
        try:
            from modules.tasks import get_flow_registry
            
            flow_registry = get_flow_registry()
            reason = body.get("reason")
            
            if not flow_registry.cancel_flow(flow_id, reason):
                raise HTTPException(status_code=400, detail="Cannot cancel flow")
            
            return {"success": True, "flow_id": flow_id, "status": "cancelled"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "cancel_flow", status_code=500)

    # ── Flow Templates ────────────────────────────────────────

    @r.get("/registry/templates")
    async def list_templates():
        """List flow templates."""
        try:
            from modules.tasks import get_flow_registry
            
            flow_registry = get_flow_registry()
            templates = flow_registry.list_templates()
            
            return {
                "templates": [t.to_dict() for t in templates],
                "count": len(templates),
            }
        except Exception as e:
            _raise_sanitized_error(e, "list_templates", status_code=500)

    @r.post("/registry/templates/{template_id}/instantiate")
    async def instantiate_template(template_id: str, body: dict = Body(default={})):
        """Create a flow from a template."""
        try:
            from modules.tasks import get_flow_registry
            
            flow_registry = get_flow_registry()
            
            flow = flow_registry.create_flow_from_template(
                template_id=template_id,
                agent_id=body.get("agent_id", "default"),
                session_id=body.get("session_id"),
                override_params=body.get("params", {}),
            )
            
            if not flow:
                raise HTTPException(status_code=404, detail=f"Template '{template_id}' not found")
            
            return {"success": True, "flow": flow.to_dict()}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "instantiate_template", status_code=500)

    # ── Maintenance & Health ──────────────────────────────────

    @r.get("/registry/health")
    async def get_registry_health():
        """Get task registry health status."""
        try:
            from modules.tasks import get_maintenance
            
            maintenance = get_maintenance()
            health = maintenance.get_health()
            
            return health.to_dict()
        except Exception as e:
            _raise_sanitized_error(e, "get_registry_health", status_code=500)

    @r.get("/registry/metrics")
    async def get_registry_metrics():
        """Get task registry metrics."""
        try:
            from modules.tasks import get_maintenance
            
            maintenance = get_maintenance()
            return maintenance.get_metrics()
        except Exception as e:
            _raise_sanitized_error(e, "get_registry_metrics", status_code=500)

    @r.post("/registry/reconcile")
    async def reconcile_registry():
        """Manually trigger task reconciliation."""
        try:
            from modules.tasks import get_maintenance
            
            maintenance = get_maintenance()
            stats = maintenance.startup_reconcile()
            
            return {"success": True, "stats": stats.to_dict()}
        except Exception as e:
            _raise_sanitized_error(e, "reconcile_registry", status_code=500)

    # ══════════════════════════════════════════════════════════════════════════
    # APPROVAL ENGINE ENDPOINTS
    # ══════════════════════════════════════════════════════════════════════════

    @r.get("/approvals/pending")
    async def list_pending_approvals(
        agent_id: Optional[str] = Query(None),
        session_id: Optional[str] = Query(None),
    ):
        """List pending approval requests."""
        try:
            from modules.approval import get_approval_queue
            
            queue = get_approval_queue()
            pending = queue.list_pending(agent_id=agent_id, session_id=session_id)
            
            return {
                "pending": [r.to_dict() for r in pending],
                "count": len(pending),
            }
        except Exception as e:
            _raise_sanitized_error(e, "list_pending_approvals", status_code=500)

    @r.get("/approvals/{token}")
    async def get_approval_request(token: str):
        """Get approval request by token."""
        try:
            from modules.approval import get_approval_queue
            
            queue = get_approval_queue()
            request = queue.get_by_token(token)
            
            if not request:
                raise HTTPException(status_code=404, detail=f"Request not found: {token}")
            
            return request.to_dict()
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "get_approval_request", status_code=500)

    @r.post("/approvals/{token}/approve")
    async def approve_request(token: str, body: dict = Body(default={})):
        """Approve an approval request."""
        try:
            from modules.approval import get_approval_queue
            
            queue = get_approval_queue()
            
            result = queue.approve(
                request_id_or_token=token,
                approver_id=body.get("approver_id", "api"),
                reason=body.get("reason", ""),
                pin=body.get("pin"),
            )
            
            if not result:
                raise HTTPException(status_code=404, detail=f"Request not found or expired: {token}")
            
            return {
                "success": True,
                "status": result.status.value,
                "request": result.to_dict(),
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "approve_request", status_code=500)

    @r.post("/approvals/{token}/deny")
    async def deny_request(token: str, body: dict = Body(default={})):
        """Deny an approval request."""
        try:
            from modules.approval import get_approval_queue
            
            queue = get_approval_queue()
            
            result = queue.deny(
                request_id_or_token=token,
                approver_id=body.get("approver_id", "api"),
                reason=body.get("reason", ""),
            )
            
            if not result:
                raise HTTPException(status_code=404, detail=f"Request not found: {token}")
            
            return {
                "success": True,
                "status": result.status.value,
                "request": result.to_dict(),
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "deny_request", status_code=500)

    @r.post("/approvals/{token}/cancel")
    async def cancel_request(token: str, body: dict = Body(default={})):
        """Cancel an approval request."""
        try:
            from modules.approval import get_approval_queue
            
            queue = get_approval_queue()
            
            result = queue.cancel(token, reason=body.get("reason", ""))
            
            if not result:
                raise HTTPException(status_code=404, detail=f"Request not found: {token}")
            
            return {
                "success": True,
                "status": result.status.value,
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "cancel_request", status_code=500)

    @r.get("/approvals/history")
    async def get_approval_history(
        limit: int = Query(50, ge=1, le=500),
    ):
        """Get approval history (resolved requests)."""
        try:
            from modules.approval import get_approval_queue
            
            queue = get_approval_queue()
            history = queue.get_history(limit=limit)
            
            return {
                "history": history,
                "count": len(history),
            }
        except Exception as e:
            _raise_sanitized_error(e, "get_approval_history", status_code=500)

    @r.post("/approvals/check")
    async def check_approval_required(body: dict = Body(...)):
        """Check if an action requires approval."""
        try:
            from modules.approval import get_hook_registry
            
            registry = get_hook_registry()
            
            action = body.get("action", "")
            if not action:
                raise HTTPException(status_code=400, detail="action is required")
            
            result = registry.check_approval_required(
                action=action,
                command=body.get("command", ""),
                params=body.get("params", {}),
                agent_id=body.get("agent_id"),
                channel_type=body.get("channel_type"),
            )
            
            return result
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "check_approval_required", status_code=500)

    @r.post("/approvals/request")
    async def create_approval_request(body: dict = Body(...)):
        """Create a new approval request."""
        try:
            from modules.approval import get_hook_registry
            
            registry = get_hook_registry()
            
            action = body.get("action", "")
            if not action:
                raise HTTPException(status_code=400, detail="action is required")
            
            request = registry.request_approval(
                action=action,
                command=body.get("command", ""),
                params=body.get("params", {}),
                agent_id=body.get("agent_id", "default"),
                session_id=body.get("session_id"),
                requestor_id=body.get("requestor_id"),
                message=body.get("message"),
                preview=body.get("preview"),
                task_id=body.get("task_id"),
                flow_id=body.get("flow_id"),
            )
            
            if not request:
                return {"required": False, "message": "No approval required"}
            
            return {
                "required": True,
                "token": request.token,
                "request": request.to_dict(),
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "create_approval_request", status_code=500)

    # ── Policy Management ─────────────────────────────────────

    @r.get("/policies")
    async def list_policies():
        """List all action policies."""
        try:
            from modules.approval import get_policy_engine
            
            engine = get_policy_engine()
            policies = engine.list_policies()
            
            return {
                "policies": [p.to_dict() for p in policies],
                "count": len(policies),
            }
        except Exception as e:
            _raise_sanitized_error(e, "list_policies", status_code=500)

    @r.get("/policies/{policy_id}")
    async def get_policy(policy_id: str):
        """Get a specific policy."""
        try:
            from modules.approval import get_policy_engine
            
            engine = get_policy_engine()
            policy = engine.get_policy(policy_id)
            
            if not policy:
                raise HTTPException(status_code=404, detail=f"Policy not found: {policy_id}")
            
            return policy.to_dict()
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "get_policy", status_code=500)

    @r.post("/policies/check")
    async def check_permission(body: dict = Body(...)):
        """Check permission for an action."""
        try:
            from modules.approval import get_policy_engine
            
            engine = get_policy_engine()
            
            action = body.get("action", "")
            if not action:
                raise HTTPException(status_code=400, detail="action is required")
            
            result = engine.check_permission(
                action=action,
                command=body.get("command"),
                params=body.get("params"),
                agent_id=body.get("agent_id"),
            )
            
            return result
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "check_permission", status_code=500)

    # =========================================================================
    # Subagent Endpoints
    # =========================================================================

    @r.get("/subagents")
    async def list_subagents():
        """List all active subagents."""
        try:
            from modules.subagents import get_subagent_runtime
            
            runtime = get_subagent_runtime()
            agents = runtime.list_agents()
            
            return {
                "success": True,
                "subagents": [
                    {
                        "id": a.id,
                        "name": a.name,
                        "parent_id": a.parent_id,
                        "depth": a.depth,
                        "status": a.status.value,
                        "created_at": a.created_at,
                    }
                    for a in agents
                ],
                "stats": runtime.get_stats(),
            }
        except Exception as e:
            _raise_sanitized_error(e, "list_subagents", status_code=500)

    @r.post("/subagents")
    async def spawn_subagent(body: dict = Body(...)):
        """Spawn a new subagent."""
        try:
            from modules.subagents import get_subagent_runtime
            
            runtime = get_subagent_runtime()
            
            name = body.get("name", "")
            if not name:
                raise HTTPException(status_code=400, detail="name is required")
            
            agent = runtime.spawn_and_get(
                name=name,
                parent_id=body.get("parent_id"),
                config=body.get("config", {}),
                context=body.get("context", {}),
            )
            
            return {
                "success": True,
                "subagent": {
                    "id": agent.id,
                    "name": agent.name,
                    "parent_id": agent.parent_id,
                    "depth": agent.depth,
                    "status": agent.status.value,
                    "created_at": agent.created_at,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "spawn_subagent", status_code=500)

    @r.get("/subagents/{agent_id}")
    async def get_subagent(agent_id: str):
        """Get a specific subagent."""
        try:
            from modules.subagents import get_subagent_runtime
            
            runtime = get_subagent_runtime()
            agent = runtime.get_agent(agent_id)
            
            if not agent:
                raise HTTPException(status_code=404, detail=f"Subagent '{agent_id}' not found")
            
            return {
                "success": True,
                "subagent": {
                    "id": agent.id,
                    "name": agent.name,
                    "parent_id": agent.parent_id,
                    "depth": agent.depth,
                    "status": agent.status.value,
                    "created_at": agent.created_at,
                    "context": agent.context,
                    "config": agent.config,
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "get_subagent", status_code=500)

    @r.delete("/subagents/{agent_id}")
    async def cancel_subagent(agent_id: str):
        """Cancel/terminate a subagent."""
        try:
            from modules.subagents import get_subagent_runtime
            
            runtime = get_subagent_runtime()
            success = runtime.cancel(agent_id)
            
            if not success:
                raise HTTPException(status_code=404, detail=f"Subagent '{agent_id}' not found or already cancelled")
            
            return {"success": True, "message": f"Subagent '{agent_id}' cancelled"}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "cancel_subagent", status_code=500)

    @r.post("/subagents/{agent_id}/message")
    async def send_subagent_message(agent_id: str, body: dict = Body(...)):
        """Send a message to a subagent."""
        try:
            from modules.subagents import get_subagent_runtime
            
            runtime = get_subagent_runtime()
            
            message = body.get("message", "")
            if not message:
                raise HTTPException(status_code=400, detail="message is required")
            
            result = runtime.send_message(
                agent_id=agent_id,
                message=message,
                metadata=body.get("metadata", {}),
            )
            
            return {"success": True, "result": result}
        except HTTPException:
            raise
        except Exception as e:
            _raise_sanitized_error(e, "send_subagent_message", status_code=500)

    @r.get("/subagents/limits")
    async def get_subagent_limits():
        """Get current subagent limits configuration."""
        try:
            from modules.subagents import get_limit_enforcer
            
            enforcer = get_limit_enforcer()
            return {
                "success": True,
                "limits": enforcer.get_limits(),
            }
        except Exception as e:
            _raise_sanitized_error(e, "get_subagent_limits", status_code=500)

    return r
