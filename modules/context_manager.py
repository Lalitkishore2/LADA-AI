"""
Context Window Manager - Smart context management with auto-compaction.

Tracks token usage per conversation and enforces per-model context window
limits. When a conversation approaches the limit, automatically compacts
older messages by summarizing them.

Superior to OpenClaw's approach:
- Per-model context limits (not one-size-fits-all)
- Smart summarization (not just truncation)
- Token budget tracking with alerts
- Conversation branching support
"""

import os
import logging
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

try:
    from modules.token_counter import TokenCounter
except ImportError:
    TokenCounter = None

try:
    from modules.model_registry import get_model_registry
except ImportError:
    get_model_registry = None


@dataclass
class ContextBudget:
    """Token budget tracking for a conversation"""
    model_id: str
    context_window: int       # Total context window of the model
    system_tokens: int = 0    # Tokens used by system prompt
    history_tokens: int = 0   # Tokens used by conversation history
    input_tokens: int = 0     # Tokens in current input
    reserved_output: int = 2048  # Reserved for model output

    @property
    def available(self) -> int:
        """Available tokens for content"""
        return max(0, self.context_window - self.system_tokens - self.reserved_output)

    @property
    def used(self) -> int:
        """Tokens currently used"""
        return self.system_tokens + self.history_tokens + self.input_tokens

    @property
    def remaining(self) -> int:
        """Remaining tokens"""
        return max(0, self.context_window - self.used - self.reserved_output)

    @property
    def usage_ratio(self) -> float:
        """How full the context is (0.0 to 1.0)"""
        if self.context_window == 0:
            return 0
        return self.used / self.context_window

    @property
    def needs_compaction(self) -> bool:
        """Whether context needs compaction (>80% full)"""
        return self.usage_ratio > 0.80

    @property
    def critical(self) -> bool:
        """Whether context is critically full (>95%)"""
        return self.usage_ratio > 0.95


class ContextManager:
    """
    Manages conversation context within model token limits.

    Features:
    - Per-model context window tracking
    - Auto-compaction when approaching limits
    - Smart summarization of old messages
    - Token-accurate message management
    - Budget monitoring and alerts
    """

    def __init__(self):
        self.counter = TokenCounter() if TokenCounter else None
        self.registry = get_model_registry() if get_model_registry else None
        self._compaction_threshold = float(os.getenv('CONTEXT_COMPACTION_THRESHOLD', '0.80'))
        self._summary_ratio = float(os.getenv('CONTEXT_SUMMARY_RATIO', '0.3'))

        logger.info("[ContextManager] Initialized")

    def count_tokens(self, text: str) -> int:
        """Count tokens in text"""
        if self.counter:
            return self.counter.count(text)
        return len(text.split()) + len(text) // 6  # rough fallback

    def get_context_window(self, model_id: str) -> int:
        """Get context window size for a model"""
        if self.registry:
            return self.registry.get_context_window(model_id)
        return 8192  # safe default

    def calculate_budget(self, messages: List[Dict[str, str]],
                         model_id: str,
                         reserved_output: int = 2048) -> ContextBudget:
        """
        Calculate token budget for a set of messages against a model.
        """
        ctx_window = self.get_context_window(model_id)

        system_tokens = 0
        history_tokens = 0
        input_tokens = 0

        for i, msg in enumerate(messages):
            content = msg.get('content', '')
            tokens = self.count_tokens(content)

            if msg.get('role') == 'system':
                system_tokens += tokens
            elif i == len(messages) - 1 and msg.get('role') == 'user':
                input_tokens = tokens
            else:
                history_tokens += tokens

        return ContextBudget(
            model_id=model_id,
            context_window=ctx_window,
            system_tokens=system_tokens,
            history_tokens=history_tokens,
            input_tokens=input_tokens,
            reserved_output=reserved_output,
        )

    def fit_messages(self, messages: List[Dict[str, str]],
                     model_id: str,
                     reserved_output: int = 2048) -> List[Dict[str, str]]:
        """
        Fit messages into a model's context window by trimming oldest
        non-system messages if necessary.

        Returns the possibly-trimmed message list.
        """
        budget = self.calculate_budget(messages, model_id, reserved_output)

        if not budget.needs_compaction:
            return messages

        logger.info(f"[ContextManager] Context {budget.usage_ratio:.0%} full, "
                    f"trimming for {model_id} (window={budget.context_window})")

        # Separate system messages, history, and current input
        system_msgs = []
        history_msgs = []
        current_input = None

        for i, msg in enumerate(messages):
            if msg.get('role') == 'system':
                system_msgs.append(msg)
            elif i == len(messages) - 1 and msg.get('role') == 'user':
                current_input = msg
            else:
                history_msgs.append(msg)

        # Calculate fixed token usage
        fixed_tokens = budget.system_tokens + budget.input_tokens + reserved_output
        available_for_history = budget.context_window - fixed_tokens

        if available_for_history <= 0:
            # Only system + input fit, no room for history
            result = system_msgs[:]
            if current_input:
                result.append(current_input)
            return result

        # Trim history from the beginning until it fits
        trimmed_history = []
        running_tokens = 0

        for msg in reversed(history_msgs):
            msg_tokens = self.count_tokens(msg.get('content', ''))
            if running_tokens + msg_tokens <= available_for_history:
                trimmed_history.insert(0, msg)
                running_tokens += msg_tokens
            else:
                break

        # Rebuild message list
        result = system_msgs + trimmed_history
        if current_input:
            result.append(current_input)

        trimmed_count = len(history_msgs) - len(trimmed_history)
        if trimmed_count > 0:
            logger.info(f"[ContextManager] Trimmed {trimmed_count} messages "
                        f"({len(trimmed_history)} retained)")

        return result

    def compact_with_summary(self, messages: List[Dict[str, str]],
                             model_id: str,
                             ai_summarize=None,
                             reserved_output: int = 2048) -> List[Dict[str, str]]:
        """
        Smart compaction: summarize older messages instead of dropping them.

        If an ai_summarize callable is provided, uses AI to summarize
        the trimmed portion. Otherwise falls back to fit_messages().

        Args:
            messages: Full message list
            model_id: Target model
            ai_summarize: Optional callable(text) -> summary_text
            reserved_output: Tokens reserved for output
        """
        budget = self.calculate_budget(messages, model_id, reserved_output)

        if not budget.needs_compaction:
            return messages

        if not ai_summarize:
            return self.fit_messages(messages, model_id, reserved_output)

        # Split messages
        system_msgs = [m for m in messages if m.get('role') == 'system']
        non_system = [m for m in messages if m.get('role') != 'system']

        if len(non_system) < 4:
            return self.fit_messages(messages, model_id, reserved_output)

        # Keep latest 1/3 of messages intact, summarize the rest
        keep_count = max(2, len(non_system) // 3)
        to_summarize = non_system[:-keep_count]
        to_keep = non_system[-keep_count:]

        # Build summary text
        summary_parts = []
        for msg in to_summarize:
            role = "User" if msg.get('role') == 'user' else "Assistant"
            summary_parts.append(f"{role}: {msg.get('content', '')}")

        summary_text = '\n'.join(summary_parts)

        try:
            summary = ai_summarize(
                f"Summarize this conversation concisely, keeping key facts and decisions:\n\n{summary_text}"
            )
            if summary:
                summary_msg = {
                    "role": "system",
                    "content": f"[Earlier conversation summary]\n{summary}"
                }
                result = system_msgs + [summary_msg] + to_keep
                logger.info(f"[ContextManager] Compacted {len(to_summarize)} messages into summary")
                return result
        except Exception as e:
            logger.warning(f"[ContextManager] AI summarization failed: {e}")

        return self.fit_messages(messages, model_id, reserved_output)

    def estimate_cost(self, messages: List[Dict[str, str]],
                      model_id: str, expected_output_tokens: int = 500) -> Dict[str, float]:
        """
        Estimate the cost of a request before sending it.
        """
        if not self.registry:
            return {'input_cost': 0, 'output_cost': 0, 'total_cost': 0}

        model = self.registry.get_model(model_id)
        if not model:
            return {'input_cost': 0, 'output_cost': 0, 'total_cost': 0}

        total_input = sum(self.count_tokens(m.get('content', '')) for m in messages)
        input_cost = (total_input / 1_000_000) * model.cost_input
        output_cost = (expected_output_tokens / 1_000_000) * model.cost_output

        return {
            'input_tokens': total_input,
            'expected_output_tokens': expected_output_tokens,
            'input_cost': round(input_cost, 6),
            'output_cost': round(output_cost, 6),
            'total_cost': round(input_cost + output_cost, 6),
            'model': model_id,
        }

    def get_budget_status(self, messages: List[Dict[str, str]],
                          model_id: str) -> Dict[str, Any]:
        """Get human-readable budget status for UI display"""
        budget = self.calculate_budget(messages, model_id)
        return {
            'model': model_id,
            'context_window': budget.context_window,
            'used': budget.used,
            'remaining': budget.remaining,
            'usage_percent': round(budget.usage_ratio * 100, 1),
            'needs_compaction': budget.needs_compaction,
            'critical': budget.critical,
            'status': (
                'critical' if budget.critical else
                'warning' if budget.needs_compaction else
                'ok'
            ),
        }

    def pre_compaction_flush(self, messages: List[Dict[str, str]], 
                             ai_extract=None) -> List[str]:
        """
        Pre-compaction flush: Extract critical notes before context is trimmed.
        
        This is a "silent agentic turn" where the AI is prompted to identify
        and preserve important facts before history is pruned (OpenClaw pattern).
        
        Args:
            messages: Full message list about to be compacted
            ai_extract: Optional callable(prompt) -> extracted_notes
            
        Returns:
            List of critical notes that should be preserved
        """
        if not ai_extract:
            # Fallback: Extract manually using heuristics
            return self._extract_critical_notes_heuristic(messages)
        
        # Build the conversation text for analysis
        conversation_text = []
        for msg in messages:
            role = msg.get('role', 'unknown')
            content = msg.get('content', '')
            if role != 'system':  # Skip system prompts
                conversation_text.append(f"{role.upper()}: {content}")
        
        if not conversation_text:
            return []
        
        # Silent agentic turn prompt
        extract_prompt = """Analyze this conversation and extract ONLY the critical facts that must be preserved.
Focus on:
- User preferences and explicit requests (e.g., "I prefer...", "always do X")
- Important decisions made during the conversation
- Key technical details or configurations mentioned
- Names, dates, or specific values that would be hard to re-derive
- Action items or commitments made

DO NOT include:
- General chit-chat or greetings
- Information that can be easily looked up
- Redundant or repetitive information

Output format: One fact per line, prefixed with "- ".
If no critical facts found, respond with "NO_CRITICAL_FACTS".

CONVERSATION:
{text}
""".format(text='\n'.join(conversation_text[-20:]))  # Last 20 messages

        try:
            result = ai_extract(extract_prompt)
            if not result or 'NO_CRITICAL_FACTS' in result:
                return []
            
            # Parse the bullet points
            notes = []
            for line in result.strip().split('\n'):
                line = line.strip()
                if line.startswith('- '):
                    notes.append(line[2:].strip())
                elif line and not line.startswith('#'):
                    notes.append(line)
            
            logger.info(f"[ContextManager] Pre-compaction extracted {len(notes)} critical notes")
            return notes
            
        except Exception as e:
            logger.warning(f"[ContextManager] AI extraction failed: {e}, using heuristic")
            return self._extract_critical_notes_heuristic(messages)
    
    def _extract_critical_notes_heuristic(self, messages: List[Dict[str, str]]) -> List[str]:
        """
        Heuristic-based extraction of critical notes when AI is unavailable.
        """
        notes = []
        importance_markers = [
            'remember', 'important', 'always', 'never', 'must', 'should',
            'prefer', 'my name is', 'i am', 'don\'t forget', 'note that',
            'key', 'critical', 'essential', 'deadline', 'due date'
        ]
        
        for msg in messages:
            if msg.get('role') != 'user':
                continue
            
            content = msg.get('content', '').lower()
            for marker in importance_markers:
                if marker in content:
                    # Extract the sentence containing the marker
                    original = msg.get('content', '')
                    # Simple sentence extraction
                    sentences = original.replace('!', '.').replace('?', '.').split('.')
                    for sentence in sentences:
                        if marker in sentence.lower():
                            clean = sentence.strip()
                            if clean and len(clean) > 10:
                                notes.append(clean)
                                break
                    break  # Only one note per message
        
        return notes[:10]  # Limit to 10 notes
    
    def compact_with_flush(self, messages: List[Dict[str, str]],
                           model_id: str,
                           ai_summarize=None,
                           ai_extract=None,
                           memory_stack=None,
                           reserved_output: int = 2048) -> List[Dict[str, str]]:
        """
        Smart compaction with pre-flush to markdown memory.
        
        This combines:
        1. Pre-compaction flush (extract critical notes)
        2. Write notes to markdown memory stack
        3. Summarize remaining context
        
        Args:
            messages: Full message list
            model_id: Target model
            ai_summarize: Optional callable for summarization
            ai_extract: Optional callable for note extraction
            memory_stack: Optional MarkdownMemoryStack instance
            reserved_output: Tokens reserved for output
        """
        budget = self.calculate_budget(messages, model_id, reserved_output)
        
        if not budget.needs_compaction:
            return messages
        
        logger.info(f"[ContextManager] Context {budget.usage_ratio:.0%} full, "
                    f"initiating pre-compaction flush for {model_id}")
        
        # Step 1: Extract critical notes
        critical_notes = self.pre_compaction_flush(messages, ai_extract)
        
        # Step 2: Write to markdown memory if available
        if memory_stack and critical_notes:
            try:
                memory_stack.flush_critical_notes(critical_notes)
            except Exception as e:
                logger.warning(f"[ContextManager] Failed to flush to markdown: {e}")
        
        # Step 3: Proceed with normal compaction
        return self.compact_with_summary(messages, model_id, ai_summarize, reserved_output)


# Module-level singleton
_context_manager: Optional[ContextManager] = None


def get_context_manager() -> ContextManager:
    """Get or create the global context manager"""
    global _context_manager
    if _context_manager is None:
        _context_manager = ContextManager()
    return _context_manager
