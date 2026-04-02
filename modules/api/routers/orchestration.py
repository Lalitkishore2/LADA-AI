"""
LADA API — Orchestration routes (/plans/*, /workflows/*, /tasks/*, /skills/*)
"""

import asyncio
import logging

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
        wf = getattr(state.jarvis, 'workflow_engine', None) if state.jarvis else None
        if not wf:
            return {"workflows": [], "count": 0}
        workflows = wf.list_workflows()
        return {"workflows": workflows, "count": len(workflows)}

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
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if not tc:
            return {"active": [], "completed": [], "active_count": 0, "completed_count": 0}
        active = tc.get_active_tasks()
        completed = tc.get_completed_tasks(20)
        return {
            "active": active.get("active_tasks", []),
            "completed": completed.get("completed_tasks", []),
            "active_count": active.get("count", 0),
            "completed_count": completed.get("count", 0),
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
        if not tc:
            raise HTTPException(status_code=503, detail="Task automation not available")
        return tc.get_task_status(execution_id)

    @r.post("/tasks/{execution_id}/pause")
    async def pause_task(execution_id: str):
        state.load_components()
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if not tc:
            raise HTTPException(status_code=503, detail="Task automation not available")
        return tc.pause_task(execution_id)

    @r.post("/tasks/{execution_id}/resume")
    async def resume_task(execution_id: str):
        state.load_components()
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if not tc:
            raise HTTPException(status_code=503, detail="Task automation not available")
        return tc.resume_task(execution_id)

    @r.post("/tasks/{execution_id}/cancel")
    async def cancel_task(execution_id: str):
        state.load_components()
        tc = getattr(state.jarvis, 'tasks', None) if state.jarvis else None
        if not tc:
            raise HTTPException(status_code=503, detail="Task automation not available")
        return tc.cancel_task(execution_id)

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

    return r
