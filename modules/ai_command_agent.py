"""
LADA AI Command Agent — AI-first command execution with ReAct tool-calling loop.

Replaces rigid pattern matching with an AI agent that understands ANY command,
selects the right tools, and executes autonomously.

LADA master loop:
- while(tool_call) execution pattern
- 7 recovery paths for resilient operation
- Collapse-drain-retry for context overflow
- Automatic tool failure retry with backoff

Flow:
    User: "find my WhatsApp photos"
    -> Agent classifies: actionable command
    -> Agent selects tier: smart (complex task)
    -> AI calls: get_app_data_paths("whatsapp") -> returns known paths
    -> AI calls: find_files("*.jpg", whatsapp_path) -> returns files
    -> AI calls: open_path(folder) -> opens Explorer
    -> Agent responds: "Found 23 WhatsApp photos. Opened the folder."

Works with both chat and voice (both call _check_system_command).
"""

import re
import json
import time
import logging
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# ERROR CLASSIFICATION & RECOVERY (LADA Pattern)
# ============================================================================

class RecoveryStrategy(Enum):
    """7 recovery strategies for different failure modes."""
    RETRY_SIMPLE = "retry_simple"           # Just retry the same call
    RETRY_WITH_BACKOFF = "retry_backoff"    # Exponential backoff
    COLLAPSE_AND_RETRY = "collapse_retry"   # Reduce context and retry
    DRAIN_AND_RETRY = "drain_retry"         # Clear pending, retry single
    SWITCH_MODEL = "switch_model"           # Try a different model
    SWITCH_TIER = "switch_tier"             # Try a different tier (fast/smart)
    ABORT = "abort"                         # Give up and return error


@dataclass
class ToolCallError:
    """Classification of a tool execution error."""
    tool_name: str
    error_message: str
    is_transient: bool = False      # Network timeout, rate limit
    is_tool_bug: bool = False       # Tool implementation issue
    is_context_overflow: bool = False  # Too much data
    is_permission: bool = False     # Access denied
    retry_count: int = 0
    
    def get_recovery_strategy(self) -> RecoveryStrategy:
        """Determine best recovery strategy for this error."""
        if self.retry_count >= 3:
            return RecoveryStrategy.ABORT
        
        if self.is_transient:
            return RecoveryStrategy.RETRY_WITH_BACKOFF
        
        if self.is_context_overflow:
            return RecoveryStrategy.COLLAPSE_AND_RETRY
        
        if self.is_tool_bug:
            return RecoveryStrategy.DRAIN_AND_RETRY
        
        if self.is_permission:
            return RecoveryStrategy.ABORT  # Can't fix permission issues
        
        return RecoveryStrategy.RETRY_SIMPLE


@dataclass
class LoopState:
    """State tracking for the master tool-calling loop."""
    round_num: int = 0
    total_tool_calls: int = 0
    failed_tools: List[ToolCallError] = field(default_factory=list)
    context_collapsed: bool = False
    model_switched: bool = False
    tier_switched: bool = False
    
    def can_retry(self, max_rounds: int) -> bool:
        """Check if we can continue the loop."""
        if self.round_num >= max_rounds:
            return False
        if len(self.failed_tools) >= 5:
            return False  # Too many failures
        return True


def classify_error(tool_name: str, error_msg: str, retry_count: int = 0) -> ToolCallError:
    """Classify a tool execution error for recovery strategy selection."""
    error_lower = error_msg.lower()
    
    # Transient errors (network, rate limit)
    transient_patterns = [
        'timeout', 'timed out', 'connection', 'network',
        'rate limit', 'too many requests', '429', '503',
        'temporarily unavailable', 'try again'
    ]
    is_transient = any(p in error_lower for p in transient_patterns)
    
    # Context overflow
    overflow_patterns = [
        'context', 'token', 'too long', 'overflow',
        'maximum length', 'exceeded', 'truncated'
    ]
    is_overflow = any(p in error_lower for p in overflow_patterns)
    
    # Permission errors
    permission_patterns = [
        'permission', 'access denied', 'forbidden', 'unauthorized',
        'not allowed', 'blocked', '403', '401'
    ]
    is_permission = any(p in error_lower for p in permission_patterns)
    
    # Tool bugs (usually implementation errors)
    bug_patterns = [
        'keyerror', 'typeerror', 'attributeerror', 'indexerror',
        'valueerror', 'not found', 'does not exist', 'invalid'
    ]
    is_bug = any(p in error_lower for p in bug_patterns)
    
    return ToolCallError(
        tool_name=tool_name,
        error_message=error_msg,
        is_transient=is_transient,
        is_context_overflow=is_overflow,
        is_permission=is_permission,
        is_tool_bug=is_bug,
        retry_count=retry_count,
    )


# Try imports
try:
    from modules.providers.provider_manager import ProviderManager
    PROVIDER_OK = True
except ImportError:
    PROVIDER_OK = False

try:
    from modules.tool_registry import ToolRegistry
    REGISTRY_OK = True
except ImportError:
    REGISTRY_OK = False

try:
    from modules.agents.specialist_pool import get_specialist_pool, SPECIALIST_CAPABILITIES
    SPECIALIST_POOL_OK = True
except ImportError:
    SPECIALIST_POOL_OK = False


@dataclass
class AgentResult:
    """Result of the AI Command Agent's attempt to handle a command."""
    handled: bool           # True if agent handled the command
    response: str           # Text response to show the user
    tool_calls_made: int = 0  # Number of tool calls executed
    tier_used: str = ""     # fast / smart
    model_used: str = ""    # Model ID used
    elapsed_ms: float = 0   # Total processing time
    recovery_used: str = "" # Recovery strategy used (if any)


# ============================================================
# Action classification — what should the agent handle?
# ============================================================

# Verbs that indicate an actionable command (agent should handle)
ACTION_VERBS = [
    'find', 'search', 'locate', 'look for', 'where is', 'where are',
    'open', 'close', 'launch', 'start', 'run', 'quit', 'exit', 'kill', 'stop',
    'create', 'make', 'new', 'delete', 'remove', 'rename', 'move', 'copy',
    'set', 'change', 'adjust', 'increase', 'decrease', 'turn',
    'play', 'pause', 'skip', 'next', 'previous',
    'show', 'list', 'display', 'check', 'get',
    'take', 'capture', 'screenshot',
    'lock', 'unlock', 'mute', 'unmute',
    'dim', 'brighten', 'maximize', 'minimize',
    'shutdown', 'restart', 'reboot',
    'read', 'preview', 'view',
    'what files', 'which files', 'how big', 'how much space',
    'recent files', 'latest files',
    'clipboard', 'copy to', 'paste',
    'folder size', 'disk usage',
    'go to',
]

# Phrases that indicate a conversation/question (agent should NOT handle)
CONVERSATION_STARTERS = [
    'what is', 'what are', 'what was', 'what were',
    'who is', 'who are', 'who was',
    'why is', 'why are', 'why do', 'why does',
    'how does', 'how do', 'how is', 'how are',
    'explain', 'describe', 'define', 'tell me about',
    'write me', 'write a', 'compose', 'draft',
    'translate', 'summarize', 'summarise',
    'compare', 'difference between',
    'can you tell', 'could you explain',
    'what do you think', 'in your opinion',
    'help me understand',
]

# Simple greetings — never actionable
GREETINGS = [
    'hi', 'hello', 'hey', 'good morning', 'good afternoon',
    'good evening', 'good night', 'thanks', 'thank you',
    'bye', 'goodbye', 'see you', 'how are you',
]

# Simple commands that local/fast models handle well (single tool call)
FAST_PATTERNS = [
    'volume', 'mute', 'unmute', 'brightness', 'dim', 'bright',
    'screenshot', 'capture screen', 'print screen',
    'lock', 'lock screen', 'lock computer',
    'minimize', 'maximize', 'fullscreen',
    'play', 'pause', 'next song', 'skip',
    'open notepad', 'open calculator', 'open chrome', 'open edge',
    'open settings', 'open terminal', 'open explorer',
    'system info', 'battery', 'cpu usage',
]


class AICommandAgent:
    """
    AI-first command execution agent with ReAct tool-calling loop.

    Uses the AI as the brain and registered tools as the hands.
    Supports both native function calling (OpenAI-compatible providers)
    and prompt-based tool calling (Gemini, Ollama, Anthropic).
    """

    def __init__(self, provider_manager: 'ProviderManager',
                 tool_registry: 'ToolRegistry',
                 config: Optional[Dict[str, Any]] = None):
        self.provider_manager = provider_manager
        self.tool_registry = tool_registry

        config = config or {}
        self.enabled = config.get('enabled', True)
        self.max_rounds = config.get('max_rounds', 5)

        # Build agent system prompt
        home = str(Path.home())
        self.system_prompt = (
            "You are LADA's command execution agent running on a Windows computer.\n"
            "You have tools to control the system, find files, open apps, and more.\n\n"
            "RULES:\n"
            "1. Use the available tools to execute the user's request. Do NOT give instructions for the user to follow.\n"
            "2. For multi-step tasks, call tools sequentially (e.g., find app data path first, then search files there).\n"
            "3. For file searches: use get_app_data_paths to find where apps store data, then find_files to search those locations.\n"
            "4. After execution, give a brief natural summary of what was done.\n"
            "5. Be concise: 'Done. Volume set to 50%.' not 'I have successfully adjusted the volume level to 50 percent.'\n"
            "6. If a tool fails, try an alternative approach before giving up.\n"
            "7. If you cannot fulfill the request with available tools, say so honestly.\n\n"
            f"CONTEXT:\n"
            f"- OS: Windows | User Home: {home}\n"
            f"- Current date: {{current_date}}\n"
        )

        logger.info(f"[Agent] AICommandAgent initialized (max_rounds={self.max_rounds})")

    def try_handle(self, text: str) -> AgentResult:
        """
        Main entry point. Attempt to handle a user command.

        Returns AgentResult with handled=True if the agent executed the command,
        or handled=False if the text is conversational and should go to AI chat.
        """
        if not self.enabled:
            return AgentResult(handled=False, response="")

        if not text or not text.strip():
            return AgentResult(handled=False, response="")

        text = text.strip()

        # Step 1: Classify — is this an actionable command?
        if not self._is_actionable(text):
            return AgentResult(handled=False, response="")

        # Step 2: Select tier (fast local vs smart cloud)
        tier = self._select_tier(text)

        # Step 2.5: Check if this should be delegated to a specialist agent
        if SPECIALIST_POOL_OK:
            should_delegate, specialist, capability = self._should_delegate(text)
            if should_delegate and specialist:
                try:
                    pool = get_specialist_pool()
                    task_id = pool.delegate_to_specialist(
                        task_description=text,
                        required_capability=capability,
                        context={'original_text': text, 'tier': tier}
                    )
                    if task_id:
                        logger.info(f"[Agent] Delegated to {specialist}: {task_id}")
                        # For now, return a response indicating delegation
                        # In future, we could wait for result via hub
                        return AgentResult(
                            handled=True,
                            response=f"Task delegated to {specialist} specialist.",
                            tier_used=tier,
                        )
                except Exception as e:
                    logger.warning(f"[Agent] Delegation failed: {e}, falling back to direct execution")

        # Step 3: Execute via AI tool-calling loop
        start = time.time()
        try:
            response, tool_count, model_id = self._execute(text, tier)
            elapsed = (time.time() - start) * 1000

            if response:
                return AgentResult(
                    handled=True,
                    response=response,
                    tool_calls_made=tool_count,
                    tier_used=tier,
                    model_used=model_id or "",
                    elapsed_ms=elapsed,
                )
        except Exception as e:
            logger.error(f"[Agent] Execution failed: {e}", exc_info=True)

        return AgentResult(handled=False, response="")

    def _is_actionable(self, text: str) -> bool:
        """
        Classify whether text is an actionable command (True) or
        a conversational question that should go to AI chat (False).
        """
        t = text.lower().strip()

        # Greetings → not actionable
        for g in GREETINGS:
            if t == g or t == g + '.' or t == g + '!':
                return False

        # Explicit conversation starters → not actionable
        for cs in CONVERSATION_STARTERS:
            if t.startswith(cs):
                return False

        # Check for action verbs (must match at word boundary)
        for verb in ACTION_VERBS:
            if ' ' in verb:
                # Multi-word: check as substring
                if verb in t:
                    return True
            else:
                # Single word: check at start or after space
                if t.startswith(verb + ' ') or t.startswith(verb + ',') or t == verb:
                    return True
                # Also check if it appears as a key phrase
                if f' {verb} ' in f' {t} ':
                    return True

        # Fallback: if it's short and starts with a common imperative, treat as actionable
        words = t.split()
        if len(words) <= 8 and words[0] in (
            'find', 'open', 'close', 'set', 'play', 'stop', 'show',
            'list', 'search', 'take', 'turn', 'lock', 'mute',
            'dim', 'maximize', 'minimize', 'get', 'check',
        ):
            return True

        return False

    def _select_tier(self, text: str) -> str:
        """
        Select model tier: 'fast' for simple commands, 'smart' for complex ones.
        """
        t = text.lower().strip()

        # Short commands with known single-action patterns → fast
        if len(t) < 50:
            for fp in FAST_PATTERNS:
                if fp in t:
                    return 'fast'

        # Everything else (file search, multi-step, PowerShell, complex) → smart
        return 'smart'

    def _should_delegate(self, text: str) -> tuple:
        """
        Check if this command should be delegated to a specialist agent.

        Returns: (should_delegate: bool, specialist_name: str, capability: str)
        """
        if not SPECIALIST_POOL_OK:
            return False, None, None

        t = text.lower()

        # Specialist keywords mapped to (agent_name, capability)
        specialist_triggers = {
            # Flight agent
            'flight': ('flight_agent', 'flight_search'),
            'flights': ('flight_agent', 'flight_search'),
            'book a flight': ('flight_agent', 'flight_booking'),
            'airline': ('flight_agent', 'flight_search'),
            'fly to': ('flight_agent', 'flight_search'),
            'flying': ('flight_agent', 'flight_search'),
            # Hotel agent
            'hotel': ('hotel_agent', 'hotel_search'),
            'hotels': ('hotel_agent', 'hotel_search'),
            'book a room': ('hotel_agent', 'hotel_booking'),
            'accommodation': ('hotel_agent', 'hotel_search'),
            'stay at': ('hotel_agent', 'hotel_search'),
            'lodging': ('hotel_agent', 'hotel_search'),
            # Restaurant agent
            'restaurant': ('restaurant_agent', 'restaurant_search'),
            'restaurants': ('restaurant_agent', 'restaurant_search'),
            'place to eat': ('restaurant_agent', 'restaurant_search'),
            'dining': ('restaurant_agent', 'restaurant_search'),
            'food near': ('restaurant_agent', 'restaurant_search'),
            # Product agent
            'buy ': ('product_agent', 'product_search'),
            'shop for': ('product_agent', 'shopping'),
            'price of': ('product_agent', 'price_comparison'),
            'compare prices': ('product_agent', 'price_comparison'),
            'product': ('product_agent', 'product_search'),
            # Package tracking
            'track package': ('package_tracking_agent', 'package_tracking'),
            'tracking number': ('package_tracking_agent', 'package_tracking'),
            'where is my package': ('package_tracking_agent', 'package_tracking'),
            'delivery status': ('package_tracking_agent', 'package_tracking'),
        }

        for trigger, (agent, capability) in specialist_triggers.items():
            if trigger in t:
                logger.info(f"[Agent] Detected specialist trigger '{trigger}' -> {agent}")
                return True, agent, capability

        return False, None, None

    def _execute(self, text: str, tier: str) -> tuple:
        """
        Execute the command via AI tool-calling loop.

        Returns: (response_text, tool_call_count, model_id)
        """
        # Get best model for the tier
        selection = self.provider_manager.get_best_model(text, tier=tier)
        if not selection:
            # Fallback: try without tier preference
            selection = self.provider_manager.get_best_model(text)
        if not selection:
            logger.warning("[Agent] No model available")
            return None, 0, None

        model_id = selection['model_id']
        provider_id = selection.get('provider_id', '')

        logger.info(f"[Agent] Using {model_id} ({provider_id}) for tier={tier}")

        # Get tools schema
        tools_schema = self.tool_registry.to_ai_schema() if self.tool_registry else []
        if not tools_schema:
            logger.warning("[Agent] No tools available")
            return None, 0, model_id

        # Get the provider instance
        provider = self.provider_manager.get_provider_for_model(model_id)

        # Check if provider supports native tool calling
        supports_native = self._supports_native_tools(provider, provider_id)

        if supports_native:
            return self._run_native_tool_loop(text, model_id, provider, tools_schema)
        else:
            return self._run_prompt_tool_loop(text, model_id, provider, tools_schema)

    def _supports_native_tools(self, provider, provider_id: str) -> bool:
        """Check if provider supports native function calling."""
        if not provider:
            return False

        # OpenAI-compatible providers support tool calling
        native_providers = ['openai', 'groq', 'mistral', 'xai', 'deepseek',
                           'together', 'fireworks', 'cerebras']
        if provider_id.lower() in native_providers:
            return True

        # Check by class name
        cls_name = type(provider).__name__.lower()
        if 'openai' in cls_name:
            return True

        return False

    def _run_native_tool_loop(self, text: str, model_id: str,
                               provider, tools_schema: list) -> tuple:
        """
        LADA master tool-calling loop with 7 recovery paths.
        
        Uses while(tool_call) pattern with error classification and automatic
        recovery for transient failures, context overflow, and tool bugs.

        Returns: (response_text, tool_call_count, model_id)
        """
        current_date = datetime.now().strftime('%B %d, %Y %I:%M %p')
        system = self.system_prompt.replace('{current_date}', current_date)

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]

        # Initialize loop state
        state = LoopState()
        recovery_used = ""
        
        # Track retry counts per tool for backoff
        tool_retry_counts: Dict[str, int] = {}
        
        # Master loop: while(tool_call or can_recover)
        while state.can_retry(self.max_rounds):
            state.round_num += 1
            
            try:
                response = provider.complete_with_retry(
                    messages, model_id,
                    tools=tools_schema,
                    temperature=0.3,
                    max_tokens=1024,
                )
            except Exception as e:
                error = classify_error("provider", str(e), state.round_num)
                strategy = error.get_recovery_strategy()
                
                logger.warning(f"[Agent] Provider error: {e}, strategy: {strategy.value}")
                
                if strategy == RecoveryStrategy.RETRY_WITH_BACKOFF:
                    # Exponential backoff: 1s, 2s, 4s
                    delay = min(2 ** (state.round_num - 1), 8)
                    time.sleep(delay)
                    recovery_used = "backoff"
                    continue
                    
                elif strategy == RecoveryStrategy.COLLAPSE_AND_RETRY:
                    # Collapse context by removing older messages
                    if len(messages) > 4:
                        messages = [messages[0], messages[1], messages[-1]]
                        state.context_collapsed = True
                        recovery_used = "collapse"
                        continue
                        
                elif strategy == RecoveryStrategy.SWITCH_MODEL:
                    # Try switching to a different model (fallback)
                    if not state.model_switched and self.provider_manager:
                        fallback = self._get_fallback_model(model_id)
                        if fallback:
                            model_id = fallback
                            state.model_switched = True
                            recovery_used = "model_switch"
                            continue
                
                # Can't recover, break
                state.failed_tools.append(error)
                break

            # No tool calls → final response (exit condition)
            if not response.tool_calls:
                if response.success and response.content:
                    return response.content.strip(), state.total_tool_calls, model_id
                break

            # Process tool calls
            messages.append({
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": response.tool_calls,
            })

            # Execute each tool call with error recovery
            for call in response.tool_calls:
                fn_name = call.get("function", {}).get("name", "")
                fn_args_raw = call.get("function", {}).get("arguments", "{}")
                call_id = call.get("id", f"call_{fn_name}_{state.round_num}")

                # Parse arguments
                try:
                    fn_args = json.loads(fn_args_raw) if isinstance(fn_args_raw, str) else fn_args_raw
                except (json.JSONDecodeError, TypeError):
                    fn_args = {}

                # Execute tool with retry logic
                logger.info(f"[Agent] Tool call: {fn_name}({fn_args})")
                result_text = self._execute_tool_with_recovery(
                    fn_name, fn_args, tool_retry_counts, state
                )

                # Append tool result
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "content": result_text,
                })

            logger.info(f"[Agent] Round {state.round_num}: {len(response.tool_calls)} tool calls, "
                       f"total: {state.total_tool_calls}, failed: {len(state.failed_tools)}")

        # If we executed tools, get final summary
        if state.total_tool_calls > 0:
            try:
                messages.append({
                    "role": "user",
                    "content": "Summarize what was done in one or two sentences."
                })
                final = provider.complete_with_retry(
                    messages, model_id,
                    temperature=0.3,
                    max_tokens=256,
                )
                if final.success and final.content:
                    return final.content.strip(), state.total_tool_calls, model_id
            except Exception:
                pass

        return None, state.total_tool_calls, model_id

    def _execute_tool_with_recovery(self, fn_name: str, fn_args: dict,
                                     retry_counts: Dict[str, int],
                                     state: LoopState) -> str:
        """
        Execute a single tool with automatic retry and recovery.
        
        Implements:
        - Simple retry for transient failures
        - Exponential backoff for rate limits
        - Drain and retry for tool bugs
        """
        max_retries = 3
        retry_key = f"{fn_name}:{json.dumps(fn_args, sort_keys=True)}"
        current_retry = retry_counts.get(retry_key, 0)
        
        while current_retry < max_retries:
            try:
                tool_result = self.tool_registry.execute(fn_name, fn_args)
                result_text = tool_result.output if tool_result.output else (tool_result.error or "done")
                state.total_tool_calls += 1
                return result_text
                
            except Exception as e:
                error_msg = str(e)
                error = classify_error(fn_name, error_msg, current_retry)
                strategy = error.get_recovery_strategy()
                
                logger.warning(f"[Agent] Tool {fn_name} error: {e}, strategy: {strategy.value}")
                
                if strategy == RecoveryStrategy.RETRY_SIMPLE:
                    current_retry += 1
                    retry_counts[retry_key] = current_retry
                    continue
                    
                elif strategy == RecoveryStrategy.RETRY_WITH_BACKOFF:
                    delay = min(2 ** current_retry, 8)
                    time.sleep(delay)
                    current_retry += 1
                    retry_counts[retry_key] = current_retry
                    continue
                    
                elif strategy == RecoveryStrategy.DRAIN_AND_RETRY:
                    # Clear any pending state and retry once
                    if current_retry == 0:
                        current_retry += 1
                        retry_counts[retry_key] = current_retry
                        continue
                
                # Can't recover, return error
                state.failed_tools.append(error)
                return f"Tool error: {error_msg}"
        
        # Exhausted retries
        return f"Tool {fn_name} failed after {max_retries} retries"

    def _get_fallback_model(self, current_model: str) -> Optional[str]:
        """Get a fallback model when the current one fails."""
        if not self.provider_manager:
            return None
            
        try:
            # Try to get another model in the same tier
            available = self.provider_manager.get_all_available_models()
            for model in available:
                if model['id'] != current_model and model.get('available', True):
                    return model['id']
        except Exception:
            pass
        
        return None

    def _run_prompt_tool_loop(self, text: str, model_id: str,
                               provider, tools_schema: list) -> tuple:
        """
        Run tool-calling loop using prompt-based approach with recovery.
        For providers that don't support native function calling (Gemini, Ollama, Anthropic).

        The AI outputs TOOL_CALL: {"name": "...", "arguments": {...}} which we parse and execute.

        Returns: (response_text, tool_call_count, model_id)
        """
        current_date = datetime.now().strftime('%B %d, %Y %I:%M %p')
        system = self.system_prompt.replace('{current_date}', current_date)

        # Build tool descriptions for prompt injection
        tool_desc = self._format_tools_for_prompt(tools_schema)

        system += (
            "\n\nAVAILABLE TOOLS:\n"
            f"{tool_desc}\n\n"
            "TO USE A TOOL, output exactly this format on its own line:\n"
            'TOOL_CALL: {"name": "tool_name", "arguments": {"param": "value"}}\n\n'
            "You can make multiple TOOL_CALL lines. After all tools execute, you will "
            "receive the results and should provide a final summary.\n"
            "If no tool is needed, just respond normally.\n"
        )

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": text},
        ]

        # Initialize loop state for recovery
        state = LoopState()
        tool_retry_counts: Dict[str, int] = {}

        while state.can_retry(self.max_rounds):
            state.round_num += 1
            
            try:
                response = provider.complete_with_retry(
                    messages, model_id,
                    temperature=0.3,
                    max_tokens=1024,
                )
            except Exception as e:
                error = classify_error("provider", str(e), state.round_num)
                strategy = error.get_recovery_strategy()
                
                logger.warning(f"[Agent] Prompt-based error: {e}, strategy: {strategy.value}")
                
                if strategy == RecoveryStrategy.RETRY_WITH_BACKOFF:
                    delay = min(2 ** (state.round_num - 1), 8)
                    time.sleep(delay)
                    continue
                elif strategy == RecoveryStrategy.COLLAPSE_AND_RETRY:
                    if len(messages) > 4:
                        messages = [messages[0], messages[1], messages[-1]]
                        state.context_collapsed = True
                        continue
                
                state.failed_tools.append(error)
                break

            if not response.success or not response.content:
                break

            content = response.content.strip()

            # Parse TOOL_CALL lines from response
            tool_calls = self._parse_tool_calls(content)

            if not tool_calls:
                # No tool calls — this is the final response
                clean = re.sub(r'TOOL_CALL:.*', '', content).strip()
                return clean or content, state.total_tool_calls, model_id

            # Execute each tool call with recovery
            messages.append({"role": "assistant", "content": content})

            results = []
            for fn_name, fn_args in tool_calls:
                logger.info(f"[Agent] Prompt tool call: {fn_name}({fn_args})")
                result_text = self._execute_tool_with_recovery(
                    fn_name, fn_args, tool_retry_counts, state
                )
                results.append(f"[Result of {fn_name}]: {result_text}")

            # Feed results back as a user message
            results_msg = "\n".join(results)
            messages.append({
                "role": "user",
                "content": f"Tool results:\n{results_msg}\n\nBased on these results, provide a brief summary of what was done. If more tools are needed, call them."
            })

            logger.info(f"[Agent] Prompt round {state.round_num}: {len(tool_calls)} tool calls, "
                       f"total: {state.total_tool_calls}")

        # Final attempt to get a summary
        if state.total_tool_calls > 0:
            try:
                messages.append({
                    "role": "user",
                    "content": "Summarize what was accomplished in one or two sentences."
                })
                final = provider.complete_with_retry(
                    messages, model_id,
                    temperature=0.3,
                    max_tokens=256,
                )
                if final.success and final.content:
                    clean = re.sub(r'TOOL_CALL:.*', '', final.content).strip()
                    return clean, state.total_tool_calls, model_id
            except Exception:
                pass

        return None, state.total_tool_calls, model_id

    def _format_tools_for_prompt(self, tools_schema: list) -> str:
        """Format tools schema into human-readable text for prompt injection."""
        lines = []
        for tool in tools_schema:
            fn = tool.get('function', {})
            name = fn.get('name', '')
            desc = fn.get('description', '')
            params = fn.get('parameters', {}).get('properties', {})
            required = fn.get('parameters', {}).get('required', [])

            param_parts = []
            for pname, pinfo in params.items():
                req = " (required)" if pname in required else ""
                param_parts.append(f"    - {pname}: {pinfo.get('type', 'string')} — {pinfo.get('description', '')}{req}")

            param_str = "\n".join(param_parts) if param_parts else "    (no parameters)"
            lines.append(f"- {name}: {desc}\n  Parameters:\n{param_str}")

        return "\n".join(lines)

    def _parse_tool_calls(self, text: str) -> List[tuple]:
        """
        Parse TOOL_CALL lines from AI response text.

        Expected format:
            TOOL_CALL: {"name": "tool_name", "arguments": {"key": "value"}}

        Returns list of (name, args_dict) tuples.
        """
        calls = []
        pattern = r'TOOL_CALL:\s*(\{.+?\})\s*$'

        for line in text.split('\n'):
            line = line.strip()
            match = re.match(pattern, line)
            if match:
                try:
                    data = json.loads(match.group(1))
                    name = data.get('name', '')
                    args = data.get('arguments', {})
                    if name:
                        calls.append((name, args))
                except (json.JSONDecodeError, TypeError):
                    continue

        return calls

    def get_status(self) -> Dict[str, Any]:
        """Get agent status for UI display."""
        tool_count = len(self.tool_registry._tools) if self.tool_registry else 0
        return {
            'enabled': self.enabled,
            'max_rounds': self.max_rounds,
            'tools_available': tool_count,
            'provider_available': bool(self.provider_manager),
        }
