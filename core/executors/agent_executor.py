"""
LADA Agent Executor — Handles screenshot analysis, pattern learning,
proactive agent, heartbeat, daily memory, vector memory, RAG engine,
MCP tools, collaboration hub, computer use, webhooks, self-modifier,
token optimizer, and dynamic prompts commands.

Extracted from JarvisCommandProcessor.process() agent/intelligence blocks.
"""

import re
import os
import json
import logging
from typing import Tuple

from core.executors import BaseExecutor

logger = logging.getLogger(__name__)


class AgentExecutor(BaseExecutor):
    """Handles AI agent, intelligence, and monitoring commands."""

    def try_handle(self, cmd: str) -> Tuple[bool, str]:
        handlers = [
            self._handle_image_generation,
            self._handle_video_generation,
            self._handle_code_execution,
            self._handle_document_reader,
            self._handle_screenshot_analyzer,
            self._handle_pattern_learner,
            self._handle_proactive_agent,
            self._handle_heartbeat,
            self._handle_daily_memory,
            self._handle_vector_memory,
            self._handle_rag_engine,
            self._handle_mcp_tools,
            self._handle_collab_hub,
            self._handle_computer_use,
            self._handle_webhooks,
            self._handle_self_modifier,
            self._handle_token_optimizer,
            self._handle_prompt_builder,
        ]
        for handler in handlers:
            handled, resp = handler(cmd)
            if handled:
                return True, resp

        # Generic agent fallback (Comet-style full control)
        agent = getattr(self.core, 'agent', None)
        if agent:
            handled, response = agent.process(cmd)
            if handled:
                return True, response

        return False, ""

    def _handle_screenshot_analyzer(self, cmd: str) -> Tuple[bool, str]:
        sa = getattr(self.core, 'screenshot_analyzer', None)
        if not sa:
            return False, ""

        if any(x in cmd for x in ['analyze screen', 'screen analysis', 'what do you see', 'describe screen']):
            result = sa.analyze_screen()
            if result['success']:
                word_count = result.get('word_count', 0)
                elements = result.get('elements', 0)
                return True, f"📊 Screen analysis:\n  Words detected: {word_count}\n  UI elements: {elements}"
            return True, "Couldn't analyze screen"

        if any(x in cmd for x in ['detect elements', 'find buttons', 'find ui', 'detect ui', 'clickable elements']):
            result = sa.detect_ui_elements()
            if result['success']:
                by_type = result.get('by_type', {})
                response = f"🎯 Found {result['count']} UI elements:"
                for elem_type, count in by_type.items():
                    response += f"\n  • {elem_type}: {count}"
                return True, response
            return True, "Couldn't detect UI elements"

        if any(x in cmd for x in ['what can i click', 'show clickable', 'interactive elements']):
            result = sa.get_clickable_elements()
            if result['success'] and result.get('elements'):
                clickable = result['elements'][:10]
                response = f"🔘 Found {result['count']} clickable elements:"
                for elem in clickable[:5]:
                    response += f"\n  • \"{elem.text}\" ({elem.type})"
                return True, response
            return True, "No clickable elements detected"

        if any(x in cmd for x in ['screen colors', 'dominant colors', 'color palette', 'what colors']):
            result = sa.get_dominant_colors(num_colors=5)
            if result['success']:
                colors = result['hex_colors']
                return True, f"🎨 Dominant screen colors: {', '.join(colors)}"
            return True, "Couldn't analyze colors"

        if 'save baseline' in cmd:
            match = re.search(r'save baseline\s+(?:as\s+)?(\w+)', cmd)
            name = match.group(1) if match else 'default'
            result = sa.save_baseline(name)
            if result['success']:
                return True, f"✅ Saved screen baseline as '{name}'"
            return True, "Couldn't save baseline"

        if any(x in cmd for x in ['detect changes', 'screen changed', 'compare baseline']):
            match = re.search(r'(?:with|from|against)\s+(\w+)', cmd)
            name = match.group(1) if match else 'default'
            baseline_path = f"screenshots/baseline_{name}.png"
            if os.path.exists(baseline_path):
                result = sa.detect_changes(baseline_path)
                if result['success']:
                    status = "🔄 Screen has changed" if result['changed'] else "✅ Screen matches baseline"
                    return True, f"{status} (similarity: {result['similarity']:.1%})"
            return True, f"No baseline '{name}' found. Use 'save baseline {name}' first."

        return False, ""

    # ── Pattern Learner ──────────────────────────────────────

    def _handle_pattern_learner(self, cmd: str) -> Tuple[bool, str]:
        pl = getattr(self.core, 'pattern_learner', None)
        if not pl:
            return False, ""

        if any(x in cmd for x in ['usage stats', 'my usage', 'usage statistics', 'how often do i']):
            stats = pl.get_usage_stats()
            if stats.get('total_commands', 0) > 0:
                return True, (
                    f"📊 Your usage statistics:\n"
                    f"  Total commands: {stats['total_commands']}\n"
                    f"  Days tracked: {stats['days_tracked']}\n"
                    f"  Avg/day: {stats['commands_per_day']:.1f}\n"
                    f"  Patterns detected: {stats['patterns_detected']}\n"
                    f"  Habits found: {stats['habits_detected']}"
                )
            return True, "Not enough usage data yet. Keep using LADA!"

        if any(x in cmd for x in ['my insights', 'learn about me', 'what have you learned', 'behavior insights', 'my patterns']):
            insights = pl.get_insights()
            if insights:
                return True, "💡 Insights about your usage:\n" + "\n".join(f"  {i}" for i in insights[:5])
            return True, "I haven't learned enough about your patterns yet."

        if any(x in cmd for x in ['what should i do', 'suggest something', 'predict next', 'what do you suggest']):
            predictions = pl.predict_next_command()
            if predictions.get('predictions'):
                response = "🔮 Based on your patterns, you might want to:"
                for p in predictions['predictions'][:3]:
                    response += f"\n  • \"{p['command']}\" - {p['reason']}"
                return True, response
            return True, "I don't have enough data for predictions yet."

        if any(x in cmd for x in ['time suggestions', 'suggestions now', 'what do i usually do']):
            suggestions = pl.get_suggestions_for_time()
            if suggestions:
                response = "📋 Based on current time, you usually:"
                for s in suggestions[:3]:
                    response += f"\n  • {s['command']} ({s['reason']})"
                return True, response
            return True, "No patterns detected for this time yet."

        if any(x in cmd for x in ['my habits', 'show habits', 'what are my habits', 'detected habits']):
            habits = pl.get_habits()
            if habits:
                response = "⏰ Your detected habits:"
                for h in habits[:5]:
                    response += f"\n  • {h['name']} ({h['strength']:.0%} consistent)"
                return True, response
            return True, "No habits detected yet. Use LADA regularly!"

        if any(x in cmd for x in ['suggest routines', 'create routine from habits', 'automate my habits']):
            suggestions = pl.suggest_routines()
            if suggestions:
                response = f"🤖 {len(suggestions)} routine suggestion(s) based on your habits:"
                for s in suggestions[:3]:
                    response += f"\n  • {s.name} at {s.trigger_time}"
                return True, response
            return True, "No strong habits detected for routine suggestions."

        if 'disable learning' in cmd or 'stop learning' in cmd:
            pl.enable_learning(False)
            return True, "🔒 Pattern learning disabled."

        if 'enable learning' in cmd or 'start learning' in cmd:
            pl.enable_learning(True)
            return True, "✅ Pattern learning enabled."

        if 'clear learning' in cmd or 'reset learning' in cmd or 'forget my patterns' in cmd:
            return True, "Say 'confirm clear learning' to erase all learned patterns."

        if 'confirm clear learning' in cmd:
            pl.reset_all()
            return True, "🗑️ All learning data cleared."

        return False, ""

    # ── Proactive Agent ──────────────────────────────────────

    def _handle_proactive_agent(self, cmd: str) -> Tuple[bool, str]:
        pa = getattr(self.core, 'proactive_agent', None)
        if not pa:
            return False, ""

        if any(x in cmd for x in ['morning briefing', 'good morning', 'start my day', 'daily briefing']):
            briefing = pa.generate_morning_briefing()
            return True, f"🌅 {briefing.summary}"

        if any(x in cmd for x in ['evening summary', 'end of day', 'daily summary', 'wrap up day']):
            briefing = pa.generate_evening_summary()
            return True, f"🌙 {briefing.summary}"

        if any(x in cmd for x in ['show suggestions', 'any suggestions', 'what should i do', 'suggest something']):
            suggestions = pa.get_pending_suggestions()
            if suggestions:
                response = f"💡 {len(suggestions)} suggestion(s):"
                for s in suggestions[:3]:
                    response += f"\n  • [{s.priority.name}] {s.title}: {s.message[:50]}..."
                return True, response
            return True, "No pending suggestions right now."

        if any(x in cmd for x in ['next suggestion', 'get suggestion']):
            s = pa.get_next_suggestion()
            if s:
                return True, f"💡 {s.title}\n{s.message}"
            return True, "No suggestions pending."

        if 'accept suggestion' in cmd:
            s = pa.get_next_suggestion()
            if s:
                result = pa.accept_suggestion(s.id)
                return result.get('success', False), f"✅ Accepted: {s.title}"
            return True, "No pending suggestion to accept."

        if 'dismiss suggestion' in cmd or 'ignore suggestion' in cmd:
            s = pa.get_next_suggestion()
            if s:
                pa.dismiss_suggestion(s.id)
                return True, f"❌ Dismissed: {s.title}"
            return True, "No pending suggestion to dismiss."

        if any(x in cmd for x in ['start proactive', 'enable proactive', 'start monitoring']):
            result = pa.start()
            if result.get('success'):
                return True, "🚀 Proactive monitoring started! I'll anticipate your needs."
            return True, "Proactive monitoring already running."

        if any(x in cmd for x in ['stop proactive', 'disable proactive', 'stop monitoring']):
            pa.stop()
            return True, "⏹️ Proactive monitoring stopped."

        if any(x in cmd for x in ['list triggers', 'show triggers', 'my triggers']):
            triggers = pa.list_triggers()
            if triggers:
                response = f"⚡ {len(triggers)} trigger(s):"
                for t in triggers[:5]:
                    status = "✅" if t['enabled'] else "❌"
                    response += f"\n  {status} {t['name']} ({t['type']})"
                return True, response
            return True, "No triggers configured."

        if any(x in cmd for x in ['proactive status', 'agent status']):
            status = pa.get_status()
            return True, (f"🤖 Proactive Agent Status:\n"
                        f"  Running: {'✅' if status['running'] else '❌'}\n"
                        f"  Pending: {status['pending_suggestions']}\n"
                        f"  Triggers: {status['enabled_triggers']}/{status['total_triggers']}")

        if any(x in cmd for x in ['proactive stats', 'suggestion stats']):
            stats = pa.get_stats()
            return True, (f"📊 Proactive Stats:\n"
                        f"  Total suggestions: {stats['total_suggestions']}\n"
                        f"  Accepted: {stats['accepted']}\n"
                        f"  Acceptance rate: {stats['acceptance_rate']:.1f}%")

        return False, ""

    # ── Heartbeat ────────────────────────────────────────────

    def _handle_heartbeat(self, cmd: str) -> Tuple[bool, str]:
        hb = getattr(self.core, 'heartbeat', None)
        if not hb:
            return False, ""

        if not any(x in cmd for x in ['heartbeat', 'check in',
            'proactive check', 'start heartbeat', 'stop heartbeat',
            'heartbeat status']):
            return False, ""

        if any(x in cmd for x in ['start heartbeat', 'enable heartbeat']):
            hb.start()
            return True, "Heartbeat system started. I'll proactively check in periodically."

        if any(x in cmd for x in ['stop heartbeat', 'disable heartbeat']):
            hb.stop()
            return True, "Heartbeat system stopped."

        if 'heartbeat status' in cmd:
            status = hb.get_status()
            return True, (f"Heartbeat: {'Active' if status.get('running') else 'Stopped'}\n"
                         f"Interval: {status.get('interval_minutes', 30)}min\n"
                         f"Cycles: {status.get('total_cycles', 0)}\n"
                         f"Last: {status.get('last_run', 'Never')}")

        if any(x in cmd for x in ['check in now', 'heartbeat now', 'trigger heartbeat']):
            result = hb.trigger_now()
            if result:
                return True, f"Heartbeat check: {result.summary if hasattr(result, 'summary') else str(result)}"
            return True, "Heartbeat check completed - nothing to report."

        return False, ""

    # ── Daily Memory ─────────────────────────────────────────

    def _handle_daily_memory(self, cmd: str) -> Tuple[bool, str]:
        dm = getattr(self.core, 'daily_memory', None)
        if not dm:
            return False, ""

        if not any(x in cmd for x in ['remember that', 'save to memory',
            'note that', 'memory search', 'search memory', 'what do you remember',
            'today notes', 'yesterday notes', 'read memory']):
            return False, ""

        if any(x in cmd for x in ['remember that', 'save to memory', 'note that']):
            for prefix in ['remember that', 'save to memory', 'note that']:
                if cmd.startswith(prefix):
                    note = cmd[len(prefix):].strip()
                    break
            else:
                note = cmd
            if note:
                dm.append_note(note, category="user_note")
                return True, "Got it, I'll remember that."

        if any(x in cmd for x in ['memory search', 'search memory']):
            query = cmd.split('search', 1)[-1].strip().lstrip('memory').strip().lstrip('for').strip()
            if query:
                results = dm.search(query)
                if results:
                    response = f"Found {len(results)} memory matches:\n"
                    for r in results[:5]:
                        response += f"  - {r.get('text', r)[:100]}\n"
                    return True, response
                return True, f"No memories found for '{query}'"

        if 'today notes' in cmd or 'today memory' in cmd:
            content = dm.read_today()
            return True, content if content else "No notes for today yet."

        if 'yesterday notes' in cmd or 'yesterday memory' in cmd:
            content = dm.read_yesterday()
            return True, content if content else "No notes from yesterday."

        if any(x in cmd for x in ['what do you remember', 'read memory']):
            content = dm.read_curated()
            return True, content if content else "No curated memories yet."

        return False, ""

    # ── Vector Memory ────────────────────────────────────────

    def _handle_vector_memory(self, cmd: str) -> Tuple[bool, str]:
        vm = getattr(self.core, 'vector_memory', None)
        if not vm:
            return False, ""

        if any(x in cmd for x in ['remember that', 'remember this', 'store memory', 'save memory']):
            content = re.sub(r'^(remember that|remember this|store memory|save memory)\s*', '', cmd).strip()
            if content:
                mem_id = vm.store(content, memory_type="fact", importance=0.7, source="user")
                return True, "Noted and stored in memory." if mem_id else "Failed to store memory."
            return True, "What would you like me to remember?"

        if any(x in cmd for x in ['recall', 'what do you remember about', 'do you remember']):
            query = re.sub(r'^(recall|what do you remember about|do you remember)\s*', '', cmd).strip()
            if query:
                results = vm.search(query, n_results=5)
                if results:
                    memories = '\n'.join([f"  - {r['content']}" for r in results[:5]])
                    return True, f"Here's what I recall:\n{memories}"
                return True, "I don't have any relevant memories about that."
            return True, "What topic would you like me to recall?"

        if cmd in ['memory stats', 'memory status', 'show memory stats']:
            stats = vm.get_stats()
            return True, f"Vector Memory: {stats.get('total_memories', 0)} memories stored. ChromaDB: {'active' if stats.get('chromadb_available') else 'fallback mode'}."

        return False, ""

    # ── RAG Engine ───────────────────────────────────────────

    def _handle_rag_engine(self, cmd: str) -> Tuple[bool, str]:
        rag = getattr(self.core, 'rag_engine', None)
        if not rag:
            return False, ""

        if any(x in cmd for x in ['ingest document', 'ingest file', 'add to knowledge', 'learn from file']):
            match = re.search(r'(?:ingest|add to knowledge|learn from)\s+(?:document|file)?\s*(.+)', cmd)
            if match:
                file_path = match.group(1).strip().strip('"').strip("'")
                result = rag.ingest(file_path)
                status = result.get('status', 'error')
                if status == 'success':
                    return True, f"Ingested document: {result.get('chunks', 0)} chunks added to knowledge base."
                elif status == 'already_ingested':
                    return True, f"Document already in knowledge base ({result.get('chunks', 0)} chunks)."
                return True, f"Could not ingest document: {status}"
            return True, "Provide a file path: 'ingest document C:\\path\\to\\file.pdf'"

        if any(x in cmd for x in ['ingest folder', 'ingest directory', 'learn from folder']):
            match = re.search(r'(?:ingest|learn from)\s+(?:folder|directory)\s*(.+)', cmd)
            if match:
                dir_path = match.group(1).strip().strip('"').strip("'")
                result = rag.ingest_directory(dir_path)
                return True, f"Ingested {result.get('files_processed', 0)} files, {result.get('total_chunks', 0)} total chunks."
            return True, "Provide a folder path: 'ingest folder C:\\path\\to\\docs'"

        if any(x in cmd for x in ['list documents', 'list knowledge', 'knowledge base', 'rag status']):
            docs = rag.list_documents()
            if docs:
                doc_list = '\n'.join([f"  - {d['filename']} ({d['chunks']} chunks)" for d in docs[:10]])
                return True, f"Knowledge base ({len(docs)} documents):\n{doc_list}"
            return True, "Knowledge base is empty. Use 'ingest document <path>' to add files."

        if any(x in cmd for x in ['ask knowledge', 'query knowledge', 'search knowledge']):
            query = re.sub(r'^(ask|query|search)\s+knowledge\s*', '', cmd).strip()
            if query:
                result = rag.query(query)
                if result.get('context'):
                    sources = ', '.join([os.path.basename(s) for s in result.get('sources', [])])
                    return True, f"{result['context']}\n\n[Sources: {sources}]" if sources else result['context']
                return True, "No relevant information found in the knowledge base."

        return False, ""

    # ── MCP Tools ────────────────────────────────────────────

    def _handle_mcp_tools(self, cmd: str) -> Tuple[bool, str]:
        mcp = getattr(self.core, 'mcp_client', None)
        if not mcp:
            return False, ""

        if any(x in cmd for x in ['list tools', 'mcp tools', 'available tools', 'show tools']):
            tools = mcp.list_tools()
            if tools:
                tool_list = '\n'.join([f"  - {t['name']}: {t['description'][:80]}" for t in tools[:20]])
                return True, f"MCP Tools ({len(tools)} available):\n{tool_list}"
            return True, "No MCP tools available. Configure servers in config/mcp_servers.json."

        if any(x in cmd for x in ['mcp status', 'mcp stats']):
            stats = mcp.get_stats()
            return True, f"MCP: {stats.get('servers_running', 0)}/{stats.get('servers_configured', 0)} servers, {stats.get('tools_available', 0)} tools."

        if 'use tool' in cmd or 'call tool' in cmd:
            match = re.search(r'(?:use|call)\s+tool\s+(\S+)\s*(.*)', cmd)
            if match:
                tool_name = match.group(1).strip()
                args_str = match.group(2).strip()
                args = {}
                if args_str:
                    try:
                        args = json.loads(args_str)
                    except json.JSONDecodeError:
                        args = {"input": args_str}
                result = mcp.call_tool(tool_name, args)
                if result.get('error'):
                    return True, f"Tool error: {result['error']}"
                return True, f"Tool result: {result.get('result', 'No output')}"

        return False, ""

    # ── Collaboration Hub ────────────────────────────────────

    def _handle_collab_hub(self, cmd: str) -> Tuple[bool, str]:
        ch = getattr(self.core, 'collab_hub', None)
        if not ch:
            return False, ""

        if any(x in cmd for x in ['list agents', 'show agents', 'available agents']):
            agents = ch.list_agents()
            if agents:
                agent_list = '\n'.join([f"  - {a['name']}: {', '.join(a['capabilities'])}" for a in agents])
                return True, f"Registered agents ({len(agents)}):\n{agent_list}"
            return True, "No agents registered."

        if any(x in cmd for x in ['delegate to', 'ask agent', 'agent collaboration']):
            match = re.search(r'(?:delegate to|ask agent)\s+(\S+)\s+(.*)', cmd)
            if match:
                agent_name = match.group(1).strip()
                task_desc = match.group(2).strip()
                task = ch.delegate_task(
                    from_agent="orchestrator",
                    to_agent=agent_name,
                    description=task_desc,
                )
                return True, f"Task delegated to {agent_name}: {task.task_id}"

        if any(x in cmd for x in ['collaboration stats', 'collab stats', 'agent stats']):
            stats = ch.get_stats()
            return True, f"Collaboration Hub: {stats.get('registered_agents', 0)} agents, {stats.get('total_tasks', 0)} tasks ({stats.get('pending_tasks', 0)} pending)."

        return False, ""

    # ── Computer Use ─────────────────────────────────────────

    def _handle_computer_use(self, cmd: str) -> Tuple[bool, str]:
        cu = getattr(self.core, 'computer_use', None)
        if not cu:
            return False, ""

        if any(x in cmd for x in ['computer do', 'use computer to', 'automate screen', 'click on', 'computer use']):
            task = re.sub(r'^(computer do|use computer to|automate screen|computer use)\s*', '', cmd).strip()
            if task:
                result = cu.execute_task(task, max_steps=15)
                status = result.get('status', 'error')
                steps = result.get('steps', 0)
                return True, f"Computer use {status}: {steps} actions taken."
            return True, "What would you like me to do on the computer? Example: 'computer do open notepad and type hello'"

        return False, ""

    # ── Webhooks ─────────────────────────────────────────────

    def _handle_webhooks(self, cmd: str) -> Tuple[bool, str]:
        wh = getattr(self.core, 'webhook_manager', None)
        if not wh:
            return False, ""

        if any(x in cmd for x in ['webhook status', 'webhook stats']):
            stats = wh.get_stats()
            status = "running" if stats.get('running') else "stopped"
            return True, f"Webhook server: {status} (port {stats.get('port')}). Events received: {stats.get('events_received', 0)}."

        if 'start webhook' in cmd or 'start webhooks' in cmd:
            wh.start_server()
            return True, f"Webhook server started on port {wh.port}."

        if any(x in cmd for x in ['webhook events', 'webhook history', 'recent webhooks']):
            events = wh.get_event_history(limit=10)
            if events:
                event_list = '\n'.join([f"  - [{e['source']}/{e['event_type']}] {e.get('result', '')}" for e in events])
                return True, f"Recent webhook events:\n{event_list}"
            return True, "No webhook events received yet."

        return False, ""

    # ── Self-Modifier ────────────────────────────────────────

    def _handle_self_modifier(self, cmd: str) -> Tuple[bool, str]:
        sm = getattr(self.core, 'self_modifier', None)
        if not sm:
            return False, ""

        if any(x in cmd for x in ['analyze module', 'analyze code', 'code analysis']):
            match = re.search(r'(?:analyze module|analyze code)\s+(.+)', cmd)
            if match:
                module_path = match.group(1).strip()
                analysis = sm.analyze_module(module_path)
                if 'error' not in analysis:
                    funcs = len(analysis.get('functions', []))
                    classes = len(analysis.get('classes', []))
                    complexity = analysis.get('complexity', {})
                    return True, f"Module analysis: {funcs} functions, {classes} classes, {complexity.get('total_lines', 0)} lines."
                return True, f"Analysis failed: {analysis.get('error')}"
            return True, "Provide a module path: 'analyze module modules/example.py'"

        if any(x in cmd for x in ['code history', 'modification history']):
            history = sm.get_modification_history()
            if history:
                hist_list = '\n'.join([f"  - [{h['type']}] {h['description'][:60]}" for h in history[-10:]])
                return True, f"Recent code modifications:\n{hist_list}"
            return True, "No code modifications recorded."

        if 'rollback' in cmd and 'code' in cmd:
            match = re.search(r'rollback\s+(?:code\s+)?(.+)', cmd)
            if match:
                file_path = match.group(1).strip()
                result = sm.rollback(file_path)
                return True, result.message

        return False, ""

    # ── Token Optimizer ──────────────────────────────────────

    def _handle_token_optimizer(self, cmd: str) -> Tuple[bool, str]:
        to = getattr(self.core, 'token_optimizer', None)
        if not to:
            return False, ""

        if any(x in cmd for x in ['token stats', 'token usage', 'api costs', 'token savings']):
            stats = to.get_stats()
            return True, (
                f"Token usage: {stats.get('total_tokens_used', 0):,} tokens across {stats.get('total_requests', 0)} requests. "
                f"Saved: {stats.get('total_tokens_saved', 0):,} tokens ({stats.get('savings_percentage', 0)}%). "
                f"Cache hits: {stats.get('total_cache_hits', 0)}. "
                f"Estimated cost: ${stats.get('estimated_cost_usd', 0):.4f}."
            )

        return False, ""

    # ── Dynamic Prompts ──────────────────────────────────────

    def _handle_prompt_builder(self, cmd: str) -> Tuple[bool, str]:
        pb = getattr(self.core, 'prompt_builder', None)
        if not pb:
            return False, ""

        if any(x in cmd for x in ['prompt stats', 'prompt status']):
            stats = pb.get_stats()
            return True, f"Dynamic Prompts: dir={stats.get('prompt_dir')}, cached={stats.get('cached_components')}, modes={stats.get('available_modes')}"

        return False, ""

    # ── Image Generation ──────────────────────────────────────

    def _handle_image_generation(self, cmd: str) -> Tuple[bool, str]:
        img_gen = getattr(self.core, 'image_gen', None)
        if not img_gen:
            return False, ""

        triggers = ['generate image', 'generate an image', 'create image', 'create an image',
                     'create a image', 'draw me', 'draw a ', 'draw an ', 'imagine ',
                     'generate picture', 'make an image', 'make a image',
                     'create a picture', 'generate art', 'ai image', 'generate a image',
                     'generate a picture']
        if not any(x in cmd for x in triggers):
            return False, ""

        if not img_gen.is_available():
            return True, "Image generation is not available. Set STABILITY_API_KEY or GEMINI_API_KEY in your .env file."

        # Extract prompt text after the trigger
        prompt = cmd
        for trigger in sorted(triggers, key=len, reverse=True):
            if trigger in prompt:
                prompt = prompt.split(trigger, 1)[-1].strip()
                break

        # Clean common filler words from start
        for prefix in ['of ', 'for ', 'with ', 'showing ', 'about ']:
            if prompt.startswith(prefix):
                prompt = prompt[len(prefix):]

        if not prompt or len(prompt) < 3:
            return True, "What should I generate? Example: 'generate image of a sunset over mountains'"

        try:
            result = img_gen.generate(prompt)
            if result:
                path = result['path']
                backend = result['backend']
                return True, f"IMAGE:{path}\n\nGenerated with {backend}: \"{prompt}\""
            return True, "Image generation failed. The backend returned no image."
        except Exception as e:
            logger.error(f"[AgentExecutor] Image generation error: {e}")
            return True, f"Image generation error: {e}"

    # ── Video Generation ──────────────────────────────────────

    def _handle_video_generation(self, cmd: str) -> Tuple[bool, str]:
        video_gen = getattr(self.core, 'video_gen', None)
        if not video_gen:
            return False, ""

        triggers = ['generate video', 'generate a video', 'create video', 'create a video',
                     'make video', 'make a video', 'generate clip', 'create clip',
                     'animate ', 'video of ', 'ai video']
        if not any(x in cmd for x in triggers):
            return False, ""

        if not video_gen.is_available():
            return True, "Video generation is not available. Set STABILITY_API_KEY or GEMINI_API_KEY in your .env file."

        # Extract prompt text after the trigger
        prompt = cmd
        for trigger in sorted(triggers, key=len, reverse=True):
            if trigger in prompt:
                prompt = prompt.split(trigger, 1)[-1].strip()
                break

        # Clean common filler words from start
        for prefix in ['of ', 'for ', 'with ', 'showing ', 'about ']:
            if prompt.startswith(prefix):
                prompt = prompt[len(prefix):]

        if not prompt or len(prompt) < 3:
            return True, "What should I generate? Example: 'generate video of a sunset over the ocean'"

        # Parse duration if specified
        duration = 5
        import re
        dur_match = re.search(r'(\d+)\s*(?:second|sec|s)\s*(?:video|clip)?', cmd)
        if dur_match:
            duration = min(int(dur_match.group(1)), 10)  # Cap at 10 seconds

        try:
            result = video_gen.generate(prompt, duration=duration)
            if result:
                path = result['path']
                backend = result['backend']
                return True, f"VIDEO:{path}\n\nGenerated {result.get('duration', duration)}s video with {backend}: \"{prompt}\""
            return True, "Video generation failed. The backend returned no video."
        except Exception as e:
            logger.error(f"[AgentExecutor] Video generation error: {e}")
            return True, f"Video generation error: {e}"

    # ── Code Execution ────────────────────────────────────────

    def _handle_code_execution(self, cmd: str) -> Tuple[bool, str]:
        sandbox = getattr(self.core, 'code_sandbox', None)
        if not sandbox:
            return False, ""

        triggers = ['run code', 'execute code', 'run python', 'run javascript',
                     'run this code', 'execute this', 'run script', 'run js',
                     'execute python', 'execute javascript', 'run powershell']
        if not any(x in cmd for x in triggers):
            return False, ""

        # Extract code from triple-backtick blocks
        code_match = re.search(r'```(?:\w+)?\s*\n?(.*?)```', cmd, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()
        else:
            # Get code after the trigger phrase
            code = cmd
            for t in sorted(triggers, key=len, reverse=True):
                if t in code:
                    code = code.split(t, 1)[-1].strip()
                    break

        if not code:
            return True, "Provide the code to execute. Example: run python ```print('hello')```"

        # Detect language
        language = "python"
        if any(x in cmd for x in ['javascript', ' js ', 'run js', 'execute js']):
            language = "javascript"
        elif any(x in cmd for x in ['powershell', ' ps ']):
            language = "powershell"

        # Validate first
        validation = sandbox.validate_code(code, language)
        if not validation.get('safe', True):
            issues = '; '.join(validation.get('issues', ['Unknown safety issue']))
            return True, f"Code blocked for safety: {issues}"

        try:
            result = sandbox.execute(code, language=language)
            if result.success:
                output = result.output or "(no output)"
                return True, f"Code executed ({result.execution_time:.2f}s):\n```\n{output}\n```"
            else:
                error = result.error or "Unknown error"
                return True, f"Execution failed: {error}"
        except Exception as e:
            logger.error(f"[AgentExecutor] Code execution error: {e}")
            return True, f"Code execution error: {e}"

    # ── Document Reader ───────────────────────────────────────

    def _handle_document_reader(self, cmd: str) -> Tuple[bool, str]:
        dr = getattr(self.core, 'document_reader', None)
        if not dr:
            return False, ""

        # Read / summarize document
        if any(x in cmd for x in ['read document', 'read file', 'read pdf',
                                    'open document', 'summarize document',
                                    'summarize file', 'summarize pdf',
                                    'document stats', 'analyze document']):
            # Extract file path
            match = re.search(
                r'(?:read|open|summarize|analyze)\s+(?:document|file|pdf|the\s+)?(.+)',
                cmd
            )
            if match:
                file_path = match.group(1).strip().strip('"').strip("'")
                if not file_path or len(file_path) < 3:
                    return True, "Provide a file path: 'read document C:\\path\\to\\file.pdf'"

                if not os.path.isfile(file_path):
                    return True, f"File not found: {file_path}"

                if not dr.can_read(file_path):
                    return True, f"Unsupported format. Supported: {', '.join(dr.SUPPORTED_FORMATS.keys())}"

                try:
                    summarize = 'summarize' in cmd
                    result = dr.read_document(file_path, summarize=summarize)
                    if result.success:
                        info = result.info
                        response = f"**{info.title}** ({info.format}, {info.page_count} page{'s' if info.page_count != 1 else ''})\n"
                        response += f"Size: {round(info.file_size / 1024, 1)} KB"
                        if info.author:
                            response += f" | Author: {info.author}"
                        response += "\n"

                        if result.summary:
                            response += f"\n**Summary:**\n{result.summary}\n"

                        if 'stats' in cmd or 'analyze' in cmd:
                            words = len(result.full_text.split())
                            response += f"\nWord count: {words:,}\n"

                        if not result.summary:
                            preview = result.full_text[:800]
                            if len(result.full_text) > 800:
                                preview += "..."
                            response += f"\n{preview}"

                        return True, response
                    return True, f"Could not read document: {result.error}"
                except Exception as e:
                    logger.error(f"[AgentExecutor] Document reader error: {e}")
                    return True, f"Error reading document: {e}"

            return True, "Provide a file path: 'read document C:\\path\\to\\file.pdf'"

        # Chat with document (ingest to RAG)
        if any(x in cmd for x in ['chat with document', 'chat with file',
                                    'chat with this', 'ask document',
                                    'question about document']):
            rag = getattr(self.core, 'rag_engine', None)
            if not rag:
                return True, "RAG engine not available. Install chromadb for document chat."

            match = re.search(
                r'(?:chat with|ask)\s+(?:document|file|this)\s*(.+)', cmd
            )
            if match:
                file_path = match.group(1).strip().strip('"').strip("'")
                if not os.path.isfile(file_path):
                    return True, f"File not found: {file_path}"
                try:
                    result = rag.ingest(file_path)
                    status = result.get('status', 'unknown')
                    if status in ('success', 'already_ingested'):
                        chunks = result.get('chunks', 0)
                        msg = "already indexed" if status == 'already_ingested' else f"indexed ({chunks} chunks)"
                        return True, f"Document {msg}. You can now ask questions about it."
                    return True, f"Could not ingest document: {status}"
                except Exception as e:
                    return True, f"Error ingesting document: {e}"

            return True, "Provide a file path: 'chat with document C:\\path\\to\\file.pdf'"

        return False, ""
