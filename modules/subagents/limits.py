"""
LADA Subagent Limits

Defines limit types and exceptions for subagent control.

Features:
- Depth limits
- Concurrency limits
- Timeout limits
- Resource limits
"""

import os
import logging
from datetime import timedelta
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ============================================================================
# Exceptions
# ============================================================================

class LimitExceeded(Exception):
    """Base exception for limit violations."""
    
    def __init__(self, message: str, limit_type: str = "unknown", current: int = 0, limit: int = 0):
        super().__init__(message)
        self.limit_type = limit_type
        self.current = current
        self.limit = limit


class DepthLimitExceeded(LimitExceeded):
    """Raised when nesting depth limit is exceeded."""
    
    def __init__(self, message: str, current: int = 0, limit: int = 0):
        super().__init__(message, "depth", current, limit)


class ConcurrencyLimitExceeded(LimitExceeded):
    """Raised when concurrent subagent limit is exceeded."""
    
    def __init__(self, message: str, current: int = 0, limit: int = 0):
        super().__init__(message, "concurrency", current, limit)


class TimeoutLimitExceeded(LimitExceeded):
    """Raised when timeout limit is exceeded."""
    
    def __init__(self, message: str, current: int = 0, limit: int = 0):
        super().__init__(message, "timeout", current, limit)


class TokenLimitExceeded(LimitExceeded):
    """Raised when token limit is exceeded."""
    
    def __init__(self, message: str, current: int = 0, limit: int = 0):
        super().__init__(message, "tokens", current, limit)


class CostLimitExceeded(LimitExceeded):
    """Raised when cost limit is exceeded."""
    
    def __init__(self, message: str, current: float = 0.0, limit: float = 0.0):
        super().__init__(message, "cost", int(current * 100), int(limit * 100))
        self.current_cost = current
        self.limit_cost = limit


# ============================================================================
# Data Classes
# ============================================================================

@dataclass
class SubagentLimits:
    """
    Configuration for subagent limits.
    """
    # Nesting
    max_depth: int = 5                    # Maximum nesting depth
    
    # Concurrency
    max_concurrent: int = 10              # Max concurrent subagents
    max_total_per_session: int = 50       # Max total per session
    max_total_per_parent: int = 10        # Max children per parent
    
    # Time
    default_timeout_seconds: int = 300    # Default timeout (5 min)
    max_timeout_seconds: int = 3600       # Maximum allowed timeout (1 hr)
    min_timeout_seconds: int = 10         # Minimum timeout
    
    # Resources
    max_tokens_per_subagent: int = 8192   # Max tokens per subagent
    max_total_tokens_per_session: int = 100000  # Max total tokens
    
    # Cost (optional)
    max_cost_per_session: Optional[float] = None  # Max cost in USD
    
    @classmethod
    def from_env(cls) -> "SubagentLimits":
        """Create limits from environment variables."""
        return cls(
            max_depth=int(os.getenv("LADA_SUBAGENT_MAX_DEPTH", "5")),
            max_concurrent=int(os.getenv("LADA_SUBAGENT_MAX_CONCURRENT", "10")),
            max_total_per_session=int(os.getenv("LADA_SUBAGENT_MAX_TOTAL", "50")),
            max_total_per_parent=int(os.getenv("LADA_SUBAGENT_MAX_CHILDREN", "10")),
            default_timeout_seconds=int(os.getenv("LADA_SUBAGENT_DEFAULT_TIMEOUT", "300")),
            max_timeout_seconds=int(os.getenv("LADA_SUBAGENT_MAX_TIMEOUT", "3600")),
            max_tokens_per_subagent=int(os.getenv("LADA_SUBAGENT_MAX_TOKENS", "8192")),
            max_total_tokens_per_session=int(os.getenv("LADA_SUBAGENT_MAX_SESSION_TOKENS", "100000")),
            max_cost_per_session=float(os.getenv("LADA_SUBAGENT_MAX_COST", "0")) or None,
        )
    
    def validate_depth(self, depth: int) -> None:
        """Validate depth limit."""
        if depth >= self.max_depth:
            raise DepthLimitExceeded(
                f"Depth {depth} exceeds limit {self.max_depth}",
                current=depth,
                limit=self.max_depth,
            )
    
    def validate_concurrency(self, current: int) -> None:
        """Validate concurrency limit."""
        if current >= self.max_concurrent:
            raise ConcurrencyLimitExceeded(
                f"Concurrent subagents {current} exceeds limit {self.max_concurrent}",
                current=current,
                limit=self.max_concurrent,
            )
    
    def validate_timeout(self, timeout: int) -> int:
        """
        Validate and clamp timeout.
        
        Returns:
            Clamped timeout value
        """
        if timeout < self.min_timeout_seconds:
            return self.min_timeout_seconds
        if timeout > self.max_timeout_seconds:
            return self.max_timeout_seconds
        return timeout
    
    def validate_tokens(self, tokens: int, session_total: int = 0) -> None:
        """Validate token limits."""
        if tokens > self.max_tokens_per_subagent:
            raise TokenLimitExceeded(
                f"Tokens {tokens} exceeds limit {self.max_tokens_per_subagent}",
                current=tokens,
                limit=self.max_tokens_per_subagent,
            )
        
        if session_total + tokens > self.max_total_tokens_per_session:
            raise TokenLimitExceeded(
                f"Session tokens would exceed {self.max_total_tokens_per_session}",
                current=session_total + tokens,
                limit=self.max_total_tokens_per_session,
            )
    
    def validate_cost(self, current_cost: float, additional: float = 0) -> None:
        """Validate cost limit."""
        if self.max_cost_per_session is None:
            return
        
        total = current_cost + additional
        if total > self.max_cost_per_session:
            raise CostLimitExceeded(
                f"Cost ${total:.2f} exceeds limit ${self.max_cost_per_session:.2f}",
                current=total,
                limit=self.max_cost_per_session,
            )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "max_depth": self.max_depth,
            "max_concurrent": self.max_concurrent,
            "max_total_per_session": self.max_total_per_session,
            "max_total_per_parent": self.max_total_per_parent,
            "default_timeout_seconds": self.default_timeout_seconds,
            "max_timeout_seconds": self.max_timeout_seconds,
            "min_timeout_seconds": self.min_timeout_seconds,
            "max_tokens_per_subagent": self.max_tokens_per_subagent,
            "max_total_tokens_per_session": self.max_total_tokens_per_session,
            "max_cost_per_session": self.max_cost_per_session,
        }


# ============================================================================
# Limit Tracker
# ============================================================================

class LimitTracker:
    """
    Tracks resource usage against limits.
    """
    
    def __init__(self, limits: SubagentLimits):
        self.limits = limits
        
        # Current usage
        self.current_depth: int = 0
        self.current_concurrent: int = 0
        self.session_totals: Dict[str, int] = {}  # session_id -> count
        self.session_tokens: Dict[str, int] = {}  # session_id -> tokens
        self.session_costs: Dict[str, float] = {}  # session_id -> cost
    
    def check_can_spawn(
        self,
        session_id: str,
        depth: int,
        tokens: int = 0,
        cost: float = 0.0,
    ) -> bool:
        """
        Check if a new subagent can be spawned.
        
        Returns:
            True if allowed, raises exception otherwise
        """
        self.limits.validate_depth(depth)
        self.limits.validate_concurrency(self.current_concurrent)
        
        session_total = self.session_totals.get(session_id, 0)
        if session_total >= self.limits.max_total_per_session:
            raise ConcurrencyLimitExceeded(
                f"Session total {session_total} exceeds limit {self.limits.max_total_per_session}",
                current=session_total,
                limit=self.limits.max_total_per_session,
            )
        
        session_tokens = self.session_tokens.get(session_id, 0)
        self.limits.validate_tokens(tokens, session_tokens)
        
        session_cost = self.session_costs.get(session_id, 0.0)
        self.limits.validate_cost(session_cost, cost)
        
        return True
    
    def record_spawn(self, session_id: str, depth: int) -> None:
        """Record a subagent spawn."""
        self.current_concurrent += 1
        self.current_depth = max(self.current_depth, depth)
        self.session_totals[session_id] = self.session_totals.get(session_id, 0) + 1
    
    def record_complete(self, session_id: str, tokens: int = 0, cost: float = 0.0) -> None:
        """Record subagent completion."""
        self.current_concurrent = max(0, self.current_concurrent - 1)
        self.session_tokens[session_id] = self.session_tokens.get(session_id, 0) + tokens
        self.session_costs[session_id] = self.session_costs.get(session_id, 0.0) + cost
    
    def reset_session(self, session_id: str) -> None:
        """Reset tracking for a session."""
        self.session_totals.pop(session_id, None)
        self.session_tokens.pop(session_id, None)
        self.session_costs.pop(session_id, None)
    
    def get_usage(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Get current usage stats."""
        result = {
            "current_depth": self.current_depth,
            "current_concurrent": self.current_concurrent,
        }
        
        if session_id:
            result["session"] = {
                "total": self.session_totals.get(session_id, 0),
                "tokens": self.session_tokens.get(session_id, 0),
                "cost": self.session_costs.get(session_id, 0.0),
            }
        
        return result
