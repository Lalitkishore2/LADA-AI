"""
LADA Workflow Executor — Handles workflow engine, routine manager,
advanced planner, skill generator, task orchestrator, pipeline runner,
and event hooks commands.

Extracted from JarvisCommandProcessor.process() workflow/planning blocks.
"""

import re
import logging
from typing import Tuple

from core.executors import BaseExecutor

logger = logging.getLogger(__name__)


class WorkflowExecutor(BaseExecutor):
    """Handles workflow, routine, planner, skill, task orchestration, pipeline, and hook commands."""

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        # Workflow engine
        if self.core.workflow_engine:
            handled, resp = self._handle_workflows(cmd)
            if handled:
                return True, resp

        # Routine manager
        if self.core.routine_manager:
            handled, resp = self._handle_routines(cmd)
            if handled:
                return True, resp

        # Advanced planner
        if self.core.advanced_planner:
            handled, resp = self._handle_planner(cmd)
            if handled:
                return True, resp

        # Skill generator
        if self.core.skill_generator:
            handled, resp = self._handle_skills(cmd)
            if handled:
                return True, resp

        # Task orchestrator
        if self.core.task_orchestrator:
            handled, resp = self._handle_task_orchestrator(cmd)
            if handled:
                return True, resp

        # Pipeline runner
        pipeline = getattr(self.core, 'pipeline_runner', None)
        if pipeline and any(x in cmd for x in ['run pipeline', 'pipeline status',
            'list pipelines', 'pending approvals', 'approve pipeline']):
            handled, resp = self._handle_pipelines(cmd)
            if handled:
                return True, resp

        # Event hooks
        hook_mgr = getattr(self.core, 'hook_manager', None)
        if hook_mgr and any(x in cmd for x in ['list hooks', 'hook status',
            'enable hook', 'disable hook']):
            handled, resp = self._handle_hooks(cmd)
            if handled:
                return True, resp

        return False, ""

    # ── Workflow Engine ──────────────────────────────────────

    def _handle_workflows(self, cmd: str) -> Tuple[bool, str]:
        wf = self.core.workflow_engine

        if any(x in cmd for x in ['run workflow', 'execute workflow', 'start workflow']):
            match = re.search(r'(?:run|execute|start)\s+workflow\s+(.+)', cmd)
            if match:
                workflow_name = match.group(1).strip()
                import asyncio
                result = asyncio.run(wf.execute_workflow(workflow_name))
                if result.success:
                    return True, f"✅ Workflow '{workflow_name}' completed successfully. {result.steps_completed}/{result.total_steps} steps in {result.duration_seconds:.1f}s."
                else:
                    return True, f"❌ Workflow '{workflow_name}' failed. {result.steps_completed}/{result.total_steps} steps completed. {result.error}"
            return True, "Which workflow would you like to run? Say 'list workflows' to see available workflows."

        if any(x in cmd for x in ['list workflows', 'show workflows', 'what workflows', 'available workflows']):
            workflows = wf.list_workflows()
            if workflows:
                workflow_list = '\n'.join([f"  • {w['name']}: {w['steps']} steps" for w in workflows])
                return True, f"Available workflows:\n{workflow_list}\n\nSay 'run workflow [name]' to execute."
            return True, "No workflows are registered yet."

        if any(x in cmd for x in ['workflow history', 'recent workflows']):
            history = wf.get_workflow_history(5)
            if history:
                history_list = '\n'.join([
                    f"  • {h.workflow_name}: {'✅' if h.success else '❌'} ({h.steps_completed}/{h.total_steps} steps, {h.duration_seconds:.1f}s)"
                    for h in history
                ])
                return True, f"Recent workflow executions:\n{history_list}"
            return True, "No workflow history yet."

        return False, ""

    # ── Routine Manager ──────────────────────────────────────

    def _handle_routines(self, cmd: str) -> Tuple[bool, str]:
        rm = self.core.routine_manager

        if any(x in cmd for x in ['run routine', 'execute routine', 'start routine']):
            match = re.search(r'(?:run|execute|start)\s+routine\s+(.+)', cmd)
            if match:
                routine_name = match.group(1).strip()
                import asyncio
                result = asyncio.run(rm.execute_routine(routine_name, manual=True))
                if result.get('success'):
                    return True, f"✅ Routine '{routine_name}' completed successfully in {result.get('duration', 0):.1f}s."
                else:
                    return True, f"❌ Routine '{routine_name}' failed: {result.get('error', 'Unknown error')}"
            return True, "Which routine would you like to run? Say 'list routines' to see available routines."

        if any(x in cmd for x in ['list routines', 'show routines', 'what routines', 'available routines']):
            routines = rm.list_routines()
            if routines:
                routine_list = '\n'.join([
                    f"  • {r['name']}: {r['schedule_type']} {r['schedule_time'] or ''} ({'✅' if r['enabled'] else '❌'})"
                    for r in routines
                ])
                return True, f"Available routines:\n{routine_list}\n\nSay 'run routine [name]' to execute manually."
            return True, "No routines are registered yet."

        if any(x in cmd for x in ['enable routine', 'activate routine']):
            match = re.search(r'(?:enable|activate)\s+routine\s+(.+)', cmd)
            if match:
                routine_name = match.group(1).strip()
                success = rm.enable_routine(routine_name)
                if success:
                    return True, f"✅ Routine '{routine_name}' enabled."
                return True, f"Routine '{routine_name}' not found."
            return True, "Which routine would you like to enable?"

        if any(x in cmd for x in ['disable routine', 'deactivate routine', 'pause routine']):
            match = re.search(r'(?:disable|deactivate|pause)\s+routine\s+(.+)', cmd)
            if match:
                routine_name = match.group(1).strip()
                success = rm.disable_routine(routine_name)
                if success:
                    return True, f"⏸️ Routine '{routine_name}' disabled."
                return True, f"Routine '{routine_name}' not found."
            return True, "Which routine would you like to disable?"

        if 'morning routine' in cmd:
            import asyncio
            result = asyncio.run(rm.execute_routine('morning_routine', manual=True))
            if result.get('success'):
                return True, f"✅ Good morning! Morning routine completed."
            return True, f"Morning routine failed: {result.get('error', 'Unknown error')}"

        if 'evening routine' in cmd:
            import asyncio
            result = asyncio.run(rm.execute_routine('evening_routine', manual=True))
            if result.get('success'):
                return True, f"✅ Evening routine completed."
            return True, f"Evening routine failed: {result.get('error', 'Unknown error')}"

        return False, ""

    # ── Advanced Planner ─────────────────────────────────────

    def _handle_planner(self, cmd: str) -> Tuple[bool, str]:
        planner = self.core.advanced_planner

        if any(x in cmd for x in ['create plan', 'make a plan', 'plan for', 'plan to']):
            task_desc = re.sub(r'^(?:create|make)\s+(?:a\s+)?plan\s+(?:for|to)\s*', '', cmd).strip()
            if not task_desc:
                task_desc = cmd
            try:
                plan = planner.create_plan(task_desc)
                summary_lines = [f"Plan created: {plan.plan_id}"]
                summary_lines.append(f"Steps: {len(plan.nodes)}")
                for nid in plan.execution_order:
                    node = plan.nodes[nid]
                    summary_lines.append(f"  {node.id}: {node.action}")
                summary_lines.append("\nSay 'execute plan' to run it, or 'show plan' for details.")
                return True, '\n'.join(summary_lines)
            except Exception as e:
                return True, f"Failed to create plan: {e}"

        if any(x in cmd for x in ['execute plan', 'run plan', 'start plan']):
            if planner.current_plan:
                try:
                    planner.execute_plan(planner.current_plan)
                    return True, planner.get_plan_summary()
                except Exception as e:
                    return True, f"Plan execution failed: {e}"
            return True, "No active plan. Say 'create plan [description]' first."

        if any(x in cmd for x in ['show plan', 'plan status', 'current plan']):
            return True, planner.get_plan_summary()

        if any(x in cmd for x in ['list plans', 'recent plans', 'show plans']):
            plans = planner.get_recent_plans(5)
            if plans:
                plan_list = '\n'.join([
                    f"  {p.plan_id}: {p.task[:50]} ({p.status.value}, {p.progress:.0%})"
                    for p in plans
                ])
                return True, f"Recent plans:\n{plan_list}"
            return True, "No plans created yet."

        if 'cancel plan' in cmd:
            planner.cancel()
            return True, "Plan cancelled."

        # Auto-route complex multi-step commands
        if hasattr(self.core, '_is_complex_command') and self.core._is_complex_command(cmd):
            try:
                plan = planner.create_plan(cmd)
                if plan and plan.nodes:
                    planner.execute_plan(plan)
                    return True, planner.get_plan_summary()
            except Exception as e:
                logger.warning(f"Planner auto-route failed, continuing: {e}")

        return False, ""

    # ── Skill Generator ──────────────────────────────────────

    def _handle_skills(self, cmd: str) -> Tuple[bool, str]:
        sg = self.core.skill_generator

        if any(x in cmd for x in ['generate skill', 'create skill', 'make skill', 'new skill']):
            desc = re.sub(r'^(?:generate|create|make|new)\s+skill\s*', '', cmd).strip()
            if not desc:
                return True, "Describe what the skill should do. Example: 'create skill that tells programming jokes'"
            result = sg.generate(desc)
            if result.get('success'):
                return True, f"Skill '{result['name']}' generated at {result['path']}"
            return True, f"Skill generation failed: {result.get('error', 'Unknown error')}"

        if any(x in cmd for x in ['list skills', 'show skills', 'generated skills']):
            skills = sg.list_generated()
            if skills:
                skill_list = '\n'.join([
                    f"  {s['name']} {'(generated)' if s['generated'] else ''}"
                    for s in skills
                ])
                return True, f"Skills:\n{skill_list}"
            return True, "No generated skills yet."

        if any(x in cmd for x in ['delete skill', 'remove skill']):
            match = re.search(r'(?:delete|remove)\s+skill\s+(.+)', cmd)
            if match:
                name = match.group(1).strip()
                if sg.delete_skill(name):
                    return True, f"Skill '{name}' deleted."
                return True, f"Skill '{name}' not found."
            return True, "Which skill would you like to delete?"

        return False, ""

    # ── Task Orchestrator ────────────────────────────────────

    def _handle_task_orchestrator(self, cmd: str) -> Tuple[bool, str]:
        to = self.core.task_orchestrator

        if any(x in cmd for x in ['list tasks', 'show tasks', 'current tasks', 'running tasks']):
            running = to.get_running_tasks()
            pending = to.get_pending_tasks()
            if running or pending:
                response = f"🔄 Running: {len(running)} | ⏳ Pending: {len(pending)}"
                for t in running[:3]:
                    response += f"\n  • {t['name']} ({t['status']})"
                return True, response
            return True, "No tasks currently running or pending."

        if any(x in cmd for x in ['task stats', 'task statistics', 'task status', 'orchestrator stats']):
            stats = to.get_statistics()
            return True, (
                f"📊 Task Statistics:\n"
                f"  Total: {stats['total_tasks']}\n"
                f"  Completed: {stats['completed']}\n"
                f"  Failed: {stats['failed']}\n"
                f"  Success rate: {stats['success_rate']:.1f}%\n"
                f"  Avg duration: {stats['avg_duration']:.1f}s"
            )

        if any(x in cmd for x in ['task history', 'recent tasks', 'completed tasks']):
            history = to.get_history(limit=10)
            if history:
                response = "📋 Recent task history:"
                for h in history[-5:]:
                    status_icon = "✅" if h['status'] == 'completed' else "❌"
                    response += f"\n  {status_icon} {h['name']} ({h['duration']:.1f}s)" if h.get('duration') else f"\n  {status_icon} {h['name']}"
                return True, response
            return True, "No task history yet."

        if any(x in cmd for x in ['cancel task', 'stop task', 'abort task']):
            running = to.get_running_tasks()
            if running:
                task = running[0]
                result = to.cancel_task(task['id'])
                return True, f"✋ Cancelled task: {task['name']}" if result['success'] else "Couldn't cancel task"
            return True, "No tasks running to cancel."

        return False, ""

    # ── Pipeline Runner ──────────────────────────────────────

    def _handle_pipelines(self, cmd: str) -> Tuple[bool, str]:
        pr = self.core.pipeline_runner

        if 'list pipelines' in cmd:
            files = []
            try:
                from modules.workflow_pipelines import list_pipeline_files
                files = list_pipeline_files()
            except Exception:
                pass
            if files:
                return True, "Available pipelines:\n" + "\n".join(f"  - {f}" for f in files)
            return True, "No pipeline files found."

        if 'pending approvals' in cmd:
            pending = pr.list_pending()
            if pending:
                response = f"{len(pending)} pending approvals:\n"
                for p in pending:
                    response += f"  - {p.get('pipeline', 'Unknown')} (token: {p.get('token', '')[:8]}...)\n"
                return True, response
            return True, "No pending pipeline approvals."

        return False, ""

    # ── Event Hooks ──────────────────────────────────────────

    def _handle_hooks(self, cmd: str) -> Tuple[bool, str]:
        hm = self.core.hook_manager

        if 'list hooks' in cmd or 'hook status' in cmd:
            status = hm.get_status()
            response = f"Event Hooks: {status['enabled_hooks']}/{status['total_hooks']} enabled\n"
            response += f"Events fired: {status['total_events_fired']}\n"
            for h in status['hooks']:
                state = 'ON' if h['enabled'] else 'OFF'
                response += f"  [{state}] {h['name']}: {h['description'][:50]}\n"
            return True, response

        if 'enable hook' in cmd:
            hook_name = cmd.split('enable hook')[-1].strip()
            if hook_name and hm.enable(hook_name):
                return True, f"Hook '{hook_name}' enabled."
            return True, f"Hook '{hook_name}' not found."

        if 'disable hook' in cmd:
            hook_name = cmd.split('disable hook')[-1].strip()
            if hook_name and hm.disable(hook_name):
                return True, f"Hook '{hook_name}' disabled."
            return True, f"Hook '{hook_name}' not found."

        return False, ""
