"""
LADA - Context Auto-Compaction System
OpenClaw-inspired context management for long-running conversations.

Monitors conversation token count and auto-triggers compaction when
approaching the model's context window limit. Before compacting, flushes
important information to a daily memory log so nothing critical is lost.

Features:
- Token-aware compaction with configurable thresholds
- Memory flush before compaction (daily log persistence)
- Session pruning of stale tool results
- Manual compaction with optional focus instructions
- tiktoken integration with word-count fallback
"""

import json
import logging
import copy
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------

_tiktoken_encoder = None
_tiktoken_available = False

try:
    import tiktoken
    _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
    _tiktoken_available = True
    logger.debug("tiktoken available - using cl100k_base encoding for token estimation")
except ImportError:
    logger.debug("tiktoken not installed - falling back to word-count heuristic")
except Exception as exc:
    logger.warning("tiktoken failed to initialise: %s - using word-count heuristic", exc)


def estimate_tokens(text: str) -> int:
    """Return an estimated token count for *text*.

    Uses tiktoken's cl100k_base encoding when available.  Otherwise falls
    back to a simple heuristic: ``ceil(len(words) * 1.35)``.  The 1.35
    multiplier accounts for sub-word tokenisation in modern BPE encoders.
    """
    if not text:
        return 0

    if _tiktoken_available and _tiktoken_encoder is not None:
        try:
            return len(_tiktoken_encoder.encode(text))
        except Exception:
            pass  # fall through to heuristic

    # Heuristic: words * 1.35 (slightly above the commonly cited 1.3 to
    # err on the side of compacting sooner rather than blowing the window).
    word_count = len(text.split())
    return max(1, int(word_count * 1.35))


def _estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate the total token cost of a list of chat messages.

    Each message incurs ~4 overhead tokens (role, delimiters).  Content is
    estimated via :func:`estimate_tokens`.  Tool-call / function-call
    content is handled as a JSON string if it is not already a string.
    """
    total = 0
    for msg in messages:
        total += 4  # per-message overhead (role, separators)
        content = msg.get("content")
        if content is None:
            content = ""
        elif not isinstance(content, str):
            content = json.dumps(content, default=str)
        total += estimate_tokens(content)

        # tool_calls / function_call fields add tokens too
        for extra_key in ("tool_calls", "function_call", "name"):
            extra = msg.get(extra_key)
            if extra:
                extra_text = json.dumps(extra, default=str) if not isinstance(extra, str) else extra
                total += estimate_tokens(extra_text)
    total += 2  # reply priming overhead
    return total


# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

# Roles / names that indicate tool-generated output
_TOOL_ROLES = {"tool", "function"}


def prune_tool_results(
    messages: List[Dict[str, Any]],
    *,
    keep_recent: int = 6,
    max_tool_content_tokens: int = 300,
    placeholder: str = "[tool output truncated]",
) -> List[Dict[str, Any]]:
    """Return a *shallow* copy of *messages* with old tool results trimmed.

    Only tool / function result messages that fall outside the most recent
    *keep_recent* messages are touched.  Their ``content`` field is replaced
    with *placeholder* if it exceeds *max_tool_content_tokens* estimated
    tokens.  This reduces context size without removing the message
    structure (so the model still sees that a tool was called and returned
    *something*).

    The original list and its message dicts are never mutated.
    """
    if not messages:
        return []

    result: List[Dict[str, Any]] = []
    cutoff = max(0, len(messages) - keep_recent)

    for idx, msg in enumerate(messages):
        role = msg.get("role", "")
        if idx < cutoff and role in _TOOL_ROLES:
            content = msg.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content, default=str)
            if estimate_tokens(content) > max_tool_content_tokens:
                pruned_msg = {**msg, "content": placeholder}
                result.append(pruned_msg)
                continue
        result.append(msg)

    pruned_count = len(result) - sum(
        1 for r in result if r.get("content") != placeholder
    )
    if pruned_count:
        logger.debug("Pruned %d oversized tool results", pruned_count)
    return result


# ---------------------------------------------------------------------------
# Memory flush
# ---------------------------------------------------------------------------

_FLUSH_EXTRACT_CATEGORIES = [
    "decisions",
    "user_preferences",
    "facts",
    "action_items",
    "key_entities",
]


def flush_to_memory(
    messages: List[Dict[str, Any]],
    memory_log: Path,
    *,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Extract and persist important context from *messages* before compaction.

    Scans the conversation for noteworthy information and appends a
    structured JSON entry to the daily *memory_log* file.  The log uses
    JSON-Lines format (one JSON object per line) so entries can be appended
    cheaply without re-serialising the whole file.

    Returns the extracted record dict.
    """
    if categories is None:
        categories = list(_FLUSH_EXTRACT_CATEGORIES)

    record: Dict[str, Any] = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "date": date.today().isoformat(),
        "message_count": len(messages),
        "estimated_tokens": _estimate_messages_tokens(messages),
        "extracted": {},
    }

    # ------------------------------------------------------------------
    # Simple heuristic extraction (no LLM call required)
    # ------------------------------------------------------------------
    user_messages: List[str] = []
    assistant_messages: List[str] = []
    tool_names: List[str] = []

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "") or ""
        if not isinstance(content, str):
            content = json.dumps(content, default=str)

        if role == "user":
            user_messages.append(content)
        elif role == "assistant":
            assistant_messages.append(content)
        elif role in _TOOL_ROLES:
            name = msg.get("name", msg.get("tool_call_id", "unknown_tool"))
            if name not in tool_names:
                tool_names.append(name)

    # Store concise representation
    if "user_preferences" in categories:
        # Look for explicit preference signals
        prefs: List[str] = []
        preference_signals = [
            "prefer", "always", "never", "don't like", "i like",
            "i want", "i need", "please always", "please never",
            "remember that", "keep in mind",
        ]
        for text in user_messages:
            lower = text.lower()
            for signal in preference_signals:
                if signal in lower:
                    # Keep the sentence containing the signal
                    for sentence in text.replace("\n", ". ").split("."):
                        if signal in sentence.lower():
                            cleaned = sentence.strip()
                            if cleaned and cleaned not in prefs:
                                prefs.append(cleaned)
        if prefs:
            record["extracted"]["user_preferences"] = prefs[:20]  # cap

    if "action_items" in categories:
        action_items: List[str] = []
        action_signals = [
            "todo", "to-do", "action item", "follow up", "need to",
            "should do", "will do", "remind me", "don't forget",
        ]
        for text in user_messages + assistant_messages:
            lower = text.lower()
            for signal in action_signals:
                if signal in lower:
                    for sentence in text.replace("\n", ". ").split("."):
                        if signal in sentence.lower():
                            cleaned = sentence.strip()
                            if cleaned and cleaned not in action_items:
                                action_items.append(cleaned)
        if action_items:
            record["extracted"]["action_items"] = action_items[:20]

    if "key_entities" in categories:
        if tool_names:
            record["extracted"]["tools_used"] = tool_names

    if "decisions" in categories:
        decisions: List[str] = []
        decision_signals = [
            "decided", "decision", "agreed", "confirmed", "we'll go with",
            "let's use", "final answer", "conclusion",
        ]
        for text in assistant_messages:
            lower = text.lower()
            for signal in decision_signals:
                if signal in lower:
                    for sentence in text.replace("\n", ". ").split("."):
                        if signal in sentence.lower():
                            cleaned = sentence.strip()
                            if cleaned and cleaned not in decisions:
                                decisions.append(cleaned)
        if decisions:
            record["extracted"]["decisions"] = decisions[:20]

    # Build a short conversation digest
    digest_lines: List[str] = []
    for text in user_messages[-5:]:
        snippet = text[:200].replace("\n", " ")
        digest_lines.append(f"  user: {snippet}")
    for text in assistant_messages[-3:]:
        snippet = text[:200].replace("\n", " ")
        digest_lines.append(f"  assistant: {snippet}")
    record["extracted"]["recent_digest"] = digest_lines

    # ------------------------------------------------------------------
    # Persist
    # ------------------------------------------------------------------
    memory_log = Path(memory_log)
    try:
        memory_log.parent.mkdir(parents=True, exist_ok=True)
        with open(memory_log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        logger.info(
            "Flushed %d messages (%d est. tokens) to memory log: %s",
            len(messages), record["estimated_tokens"], memory_log,
        )
    except OSError as exc:
        logger.error("Failed to write memory log %s: %s", memory_log, exc)

    return record


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------

def should_compact(
    messages: List[Dict[str, Any]],
    context_window: int,
    *,
    reserve_tokens_floor: int = 20_000,
    soft_threshold_tokens: int = 4_000,
) -> bool:
    """Return ``True`` when the conversation should be compacted.

    Compaction is advised when the estimated token usage of *messages*
    exceeds::

        context_window - reserve_tokens_floor - soft_threshold_tokens

    The *reserve_tokens_floor* guarantees headroom for the model's reply
    and any injected system context.  The *soft_threshold_tokens* provides
    an additional buffer so compaction is triggered *before* we slam into
    the hard ceiling.
    """
    if not messages:
        return False
    used = _estimate_messages_tokens(messages)
    ceiling = context_window - reserve_tokens_floor - soft_threshold_tokens
    above = used >= ceiling
    if above:
        logger.debug(
            "Compaction advised: %d estimated tokens >= ceiling %d "
            "(window=%d, reserve=%d, soft=%d)",
            used, ceiling, context_window, reserve_tokens_floor,
            soft_threshold_tokens,
        )
    return above


def compact_messages(
    messages: List[Dict[str, Any]],
    *,
    focus: Optional[str] = None,
    keep_recent: int = 10,
    keep_system: bool = True,
    summary_max_tokens: int = 800,
) -> List[Dict[str, Any]]:
    """Compact *messages* by summarising older entries.

    The most recent *keep_recent* messages are preserved verbatim.  All
    older non-system messages are collapsed into a single system-role
    summary message inserted at the beginning (after any retained system
    messages).

    If *focus* is provided it is prepended to the summary to steer what
    the model pays attention to going forward.

    Returns a **new** list; the original is not mutated.
    """
    if len(messages) <= keep_recent:
        logger.debug("Nothing to compact (%d msgs <= keep_recent=%d)", len(messages), keep_recent)
        return list(messages)

    # Partition
    older = messages[:-keep_recent]
    recent = messages[-keep_recent:]

    # Separate system messages that should be kept verbatim
    system_msgs: List[Dict[str, Any]] = []
    to_summarise: List[Dict[str, Any]] = []

    for msg in older:
        if keep_system and msg.get("role") == "system":
            system_msgs.append(msg)
        else:
            to_summarise.append(msg)

    if not to_summarise:
        logger.debug("No non-system messages to compact in the older window")
        return list(messages)

    # Build the summary text
    summary_lines: List[str] = []
    summary_lines.append("=== Compacted Conversation Summary ===")
    if focus:
        summary_lines.append(f"Focus: {focus}")
    summary_lines.append(
        f"({len(to_summarise)} messages compacted at "
        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
    )
    summary_lines.append("")

    # Group consecutive messages by role for readability
    current_role: Optional[str] = None
    role_buffer: List[str] = []

    def _flush_role_buffer() -> None:
        if current_role and role_buffer:
            label = current_role.upper()
            combined = " ".join(role_buffer)
            # Aggressively truncate per-role content
            max_chars = max(100, (summary_max_tokens * 4) // max(1, len(to_summarise)))
            if len(combined) > max_chars:
                combined = combined[:max_chars] + "..."
            summary_lines.append(f"[{label}]: {combined}")

    for msg in to_summarise:
        role = msg.get("role", "unknown")
        content = msg.get("content", "") or ""
        if not isinstance(content, str):
            content = json.dumps(content, default=str)

        # Strip empty content
        content = content.strip()
        if not content:
            # Still note tool calls
            if msg.get("tool_calls"):
                content = f"(called tools: {json.dumps([tc.get('function', {}).get('name', '?') for tc in msg['tool_calls']])})"
            elif role in _TOOL_ROLES:
                name = msg.get("name", "tool")
                content = f"({name} returned a result)"
            else:
                continue

        if role != current_role:
            _flush_role_buffer()
            current_role = role
            role_buffer = [content]
        else:
            role_buffer.append(content)

    _flush_role_buffer()

    summary_lines.append("")
    summary_lines.append("=== End of Summary ===")

    summary_text = "\n".join(summary_lines)

    # Trim summary itself if it ballooned
    if estimate_tokens(summary_text) > summary_max_tokens:
        # Hard-cut at roughly the right char count
        char_limit = summary_max_tokens * 4  # ~4 chars per token
        summary_text = summary_text[:char_limit] + "\n... [summary truncated]\n=== End of Summary ==="

    summary_msg: Dict[str, Any] = {
        "role": "system",
        "content": summary_text,
    }

    compacted = system_msgs + [summary_msg] + recent
    original_tokens = _estimate_messages_tokens(messages)
    new_tokens = _estimate_messages_tokens(compacted)
    logger.info(
        "Compacted conversation: %d -> %d messages, ~%d -> ~%d tokens (%.0f%% reduction)",
        len(messages), len(compacted),
        original_tokens, new_tokens,
        (1 - new_tokens / max(1, original_tokens)) * 100,
    )
    return compacted


# ---------------------------------------------------------------------------
# ContextCompactor - main orchestrator class
# ---------------------------------------------------------------------------

class ContextCompactor:
    """Monitors a conversation and auto-compacts when nearing the context limit.

    Typical integration::

        compactor = ContextCompactor(context_window=128_000)

        # Before every API call:
        messages = compactor.prepare(messages)

        # Manual compaction with focus:
        messages = compactor.compact(messages, focus="keep API design details")

    Parameters
    ----------
    context_window : int
        The model's maximum context window in tokens (e.g. 128000).
    reserve_tokens_floor : int
        Minimum tokens reserved for the model's reply. Default 20 000.
    soft_threshold_tokens : int
        Additional buffer before the hard ceiling. Default 4 000.
    keep_recent : int
        Number of recent messages to always preserve verbatim. Default 10.
    keep_system : bool
        Whether to preserve all system messages outside the summary.
    auto_flush : bool
        Automatically flush to memory log before compacting.
    memory_log_dir : Path or str
        Directory for daily memory log files.
    prune_tool_results_flag : bool
        Whether to prune oversized tool results on every prepare() call.
    """

    def __init__(
        self,
        context_window: int = 128_000,
        reserve_tokens_floor: int = 20_000,
        soft_threshold_tokens: int = 4_000,
        keep_recent: int = 10,
        keep_system: bool = True,
        auto_flush: bool = True,
        memory_log_dir: Optional[str] = None,
        prune_tool_results_flag: bool = True,
    ):
        self.context_window = context_window
        self.reserve_tokens_floor = reserve_tokens_floor
        self.soft_threshold_tokens = soft_threshold_tokens
        self.keep_recent = keep_recent
        self.keep_system = keep_system
        self.auto_flush = auto_flush
        self.prune_tool_results_flag = prune_tool_results_flag

        if memory_log_dir is None:
            self._memory_log_dir = Path("data") / "memory_logs"
        else:
            self._memory_log_dir = Path(memory_log_dir)

        # Statistics
        self._compaction_count: int = 0
        self._total_tokens_saved: int = 0
        self._last_compaction: Optional[datetime] = None

        logger.info(
            "ContextCompactor initialised (window=%d, reserve=%d, soft=%d, "
            "keep_recent=%d, auto_flush=%s)",
            self.context_window, self.reserve_tokens_floor,
            self.soft_threshold_tokens, self.keep_recent, self.auto_flush,
        )

    # -- public API --------------------------------------------------------

    def prepare(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare *messages* for an API call.

        This is the primary entry point.  It:

        1. Optionally prunes oversized tool results (in-memory, non-destructive).
        2. Checks whether compaction is needed.
        3. If yes, flushes to memory (when *auto_flush* is enabled) and then
           compacts older messages into a summary.

        Returns a new list suitable for sending to the model.
        """
        if not messages:
            return messages

        working = list(messages)

        # Step 1: session pruning of tool results
        if self.prune_tool_results_flag:
            working = prune_tool_results(working, keep_recent=self.keep_recent)

        # Step 2: check whether compaction is needed
        if should_compact(
            working,
            self.context_window,
            reserve_tokens_floor=self.reserve_tokens_floor,
            soft_threshold_tokens=self.soft_threshold_tokens,
        ):
            # Step 3: flush before compacting
            if self.auto_flush:
                self._flush(working)

            # Step 4: compact
            working = compact_messages(
                working,
                keep_recent=self.keep_recent,
                keep_system=self.keep_system,
            )
            self._record_compaction(messages, working)

        return working

    def compact(
        self,
        messages: List[Dict[str, Any]],
        *,
        focus: Optional[str] = None,
        flush: bool = True,
    ) -> List[Dict[str, Any]]:
        """Manually trigger compaction regardless of current token usage.

        Parameters
        ----------
        messages :
            The current conversation messages.
        focus :
            Optional instruction to bias the summary (e.g. "keep all SQL
            schema details").
        flush :
            Whether to flush to memory log before compacting.
        """
        if flush:
            self._flush(messages)

        compacted = compact_messages(
            messages,
            focus=focus,
            keep_recent=self.keep_recent,
            keep_system=self.keep_system,
        )
        self._record_compaction(messages, compacted)
        return compacted

    def get_stats(self) -> Dict[str, Any]:
        """Return compaction statistics for the current session."""
        return {
            "compaction_count": self._compaction_count,
            "total_tokens_saved": self._total_tokens_saved,
            "last_compaction": (
                self._last_compaction.isoformat() if self._last_compaction else None
            ),
            "context_window": self.context_window,
            "reserve_tokens_floor": self.reserve_tokens_floor,
            "soft_threshold_tokens": self.soft_threshold_tokens,
        }

    def get_usage_report(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Return a snapshot of current context utilisation."""
        used = _estimate_messages_tokens(messages)
        ceiling = self.context_window - self.reserve_tokens_floor
        return {
            "estimated_tokens_used": used,
            "context_window": self.context_window,
            "effective_ceiling": ceiling,
            "headroom": max(0, ceiling - used),
            "utilisation_pct": round(used / max(1, ceiling) * 100, 1),
            "compaction_advised": should_compact(
                messages,
                self.context_window,
                reserve_tokens_floor=self.reserve_tokens_floor,
                soft_threshold_tokens=self.soft_threshold_tokens,
            ),
            "message_count": len(messages),
        }

    # -- internals ---------------------------------------------------------

    def _memory_log_path(self) -> Path:
        """Return today's memory log file path."""
        today = date.today().isoformat()
        return self._memory_log_dir / f"memory_{today}.jsonl"

    def _flush(self, messages: List[Dict[str, Any]]) -> None:
        """Wrapper around :func:`flush_to_memory`."""
        try:
            flush_to_memory(messages, self._memory_log_path())
        except Exception as exc:
            logger.error("Memory flush failed: %s", exc, exc_info=True)

    def _record_compaction(
        self,
        original: List[Dict[str, Any]],
        compacted: List[Dict[str, Any]],
    ) -> None:
        """Update internal statistics after a compaction."""
        original_tokens = _estimate_messages_tokens(original)
        compacted_tokens = _estimate_messages_tokens(compacted)
        saved = max(0, original_tokens - compacted_tokens)

        self._compaction_count += 1
        self._total_tokens_saved += saved
        self._last_compaction = datetime.now()

        logger.info(
            "Compaction #%d complete: saved ~%d tokens (cumulative: ~%d)",
            self._compaction_count, saved, self._total_tokens_saved,
        )
