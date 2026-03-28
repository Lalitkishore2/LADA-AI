"""
LADA Token Counter & Cost Tracker

Provides:
- Token counting per request/response (estimation without tiktoken)
- Cumulative cost tracking per session
- Context window budget enforcement
- Cost alerts when approaching limits
- Session cost summary for display in status bar

Uses character-based estimation (4 chars ≈ 1 token for English).
"""

import os
import json
import logging
import threading
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from modules.singleton_utils import thread_safe_singleton

logger = logging.getLogger(__name__)

# Approximate characters per token (varies by model/language)
CHARS_PER_TOKEN = 4


@dataclass
class TokenUsage:
    """Token usage for a single request"""
    input_tokens: int
    output_tokens: int
    model_id: str
    provider: str
    cost_usd: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    query_preview: str = ""  # first 50 chars of query for debugging


class TokenCounter:
    """
    Estimates token count from text.
    Uses character-based estimation (fast, no external dependencies).
    """

    @staticmethod
    def count(text: str) -> int:
        """Estimate token count for a text string"""
        if not text:
            return 0
        return max(1, len(text) // CHARS_PER_TOKEN)

    @staticmethod
    def count_messages(messages: List[Dict[str, str]]) -> int:
        """Estimate token count for a list of messages"""
        total = 0
        for msg in messages:
            content = msg.get('content', '')
            role = msg.get('role', '')
            # Each message has ~4 token overhead (role, delimiters)
            total += TokenCounter.count(content) + 4
        return total

    @staticmethod
    def fits_context(text: str, context_window: int, reserved: int = 1000) -> bool:
        """Check if text fits within a context window (with reserve for response)"""
        tokens = TokenCounter.count(text)
        return tokens < (context_window - reserved)

    @staticmethod
    def trim_to_fit(text: str, max_tokens: int) -> str:
        """Trim text to fit within token budget"""
        max_chars = max_tokens * CHARS_PER_TOKEN
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "\n...[trimmed]"


class CostTracker:
    """
    Tracks cumulative costs per session.

    Features:
    - Per-request cost recording
    - Session totals by provider
    - Budget alerts
    - Persistent cost history (optional)
    """

    def __init__(self, budget_usd: float = 0, persist_path: str = None):
        self.budget_usd = budget_usd or float(os.getenv('AI_BUDGET_USD', '0'))
        self.persist_path = Path(persist_path) if persist_path else None

        self.session_start = datetime.now().isoformat()
        self.usage_history: List[TokenUsage] = []
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost_usd = 0.0
        self.provider_costs: Dict[str, float] = {}

        self._lock = threading.Lock()
        logger.info(f"[CostTracker] Initialized (budget: ${self.budget_usd:.2f})")

    def record(self, input_tokens: int, output_tokens: int,
               model_id: str, provider: str,
               cost_input_per_m: float = 0, cost_output_per_m: float = 0,
               query_preview: str = "") -> TokenUsage:
        """Record token usage for a single request"""
        cost = (input_tokens / 1_000_000) * cost_input_per_m + \
               (output_tokens / 1_000_000) * cost_output_per_m

        usage = TokenUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_id=model_id,
            provider=provider,
            cost_usd=cost,
            query_preview=query_preview[:50],
        )

        with self._lock:
            self.usage_history.append(usage)
            self.total_input_tokens += input_tokens
            self.total_output_tokens += output_tokens
            self.total_cost_usd += cost
            self.provider_costs[provider] = self.provider_costs.get(provider, 0) + cost

        logger.debug(
            f"[CostTracker] {model_id}: {input_tokens}+{output_tokens} tokens, "
            f"${cost:.6f} (total: ${self.total_cost_usd:.4f})"
        )

        # Budget alert
        if self.budget_usd > 0 and self.total_cost_usd >= self.budget_usd * 0.8:
            pct = (self.total_cost_usd / self.budget_usd) * 100
            logger.warning(f"[CostTracker] Budget alert: {pct:.0f}% used (${self.total_cost_usd:.4f}/${self.budget_usd:.2f})")

        return usage

    def record_from_text(self, input_text: str, output_text: str,
                         model_id: str, provider: str,
                         cost_input_per_m: float = 0,
                         cost_output_per_m: float = 0) -> TokenUsage:
        """Record usage by estimating tokens from text"""
        input_tokens = TokenCounter.count(input_text)
        output_tokens = TokenCounter.count(output_text)
        return self.record(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            model_id=model_id,
            provider=provider,
            cost_input_per_m=cost_input_per_m,
            cost_output_per_m=cost_output_per_m,
            query_preview=input_text[:50],
        )

    def is_over_budget(self) -> bool:
        """Check if spending exceeds budget"""
        if self.budget_usd <= 0:
            return False
        return self.total_cost_usd >= self.budget_usd

    def get_summary(self) -> Dict[str, Any]:
        """Get session cost summary"""
        return {
            'session_start': self.session_start,
            'total_requests': len(self.usage_history),
            'total_input_tokens': self.total_input_tokens,
            'total_output_tokens': self.total_output_tokens,
            'total_tokens': self.total_input_tokens + self.total_output_tokens,
            'total_cost_usd': round(self.total_cost_usd, 6),
            'budget_usd': self.budget_usd,
            'budget_remaining': round(max(0, self.budget_usd - self.total_cost_usd), 6) if self.budget_usd > 0 else None,
            'costs_by_provider': {k: round(v, 6) for k, v in self.provider_costs.items()},
        }

    def get_status_text(self) -> str:
        """Get short status text for display in status bar"""
        total = self.total_input_tokens + self.total_output_tokens
        if total == 0:
            return ""

        parts = [f"{total:,} tokens"]
        if self.total_cost_usd > 0:
            parts.append(f"${self.total_cost_usd:.4f}")
        if self.budget_usd > 0:
            pct = (self.total_cost_usd / self.budget_usd) * 100
            parts.append(f"({pct:.0f}% of budget)")

        return " | ".join(parts)

    def save(self, path: str = None) -> None:
        """Save cost history to file"""
        save_path = Path(path) if path else self.persist_path
        if not save_path:
            return

        save_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            'summary': self.get_summary(),
            'history': [
                {
                    'input_tokens': u.input_tokens,
                    'output_tokens': u.output_tokens,
                    'model_id': u.model_id,
                    'provider': u.provider,
                    'cost_usd': u.cost_usd,
                    'timestamp': u.timestamp,
                    'query_preview': u.query_preview,
                }
                for u in self.usage_history
            ],
        }

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

        logger.info(f"[CostTracker] Saved to {save_path}")


# Module-level singletons
_counter: Optional[TokenCounter] = None
_tracker: Optional[CostTracker] = None


def get_token_counter() -> TokenCounter:
    """Get the global token counter"""
    global _counter
    if _counter is None:
        _counter = TokenCounter()
    return _counter


def get_cost_tracker() -> CostTracker:
    """Get or create the global cost tracker"""
    global _tracker
    if _tracker is None:
        _tracker = CostTracker(
            persist_path=os.getenv('COST_LOG_PATH', 'data/cost_history.json')
        )
    return _tracker
