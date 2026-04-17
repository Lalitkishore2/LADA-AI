"""
LADA Subagent Module

Provides subagent spawn, lifecycle, and orchestration.

Features:
- Subagent spawn and termination
- Depth and concurrency limits
- Timeout handling
- Resource isolation
"""

from modules.subagents.runtime import (
    SubagentConfig,
    SubagentState,
    SubagentStatus,
    SubagentResult,
    SubagentRuntime,
    get_subagent_runtime,
)

from modules.subagents.limits import (
    SubagentLimits,
    LimitExceeded,
    DepthLimitExceeded,
    ConcurrencyLimitExceeded,
    TimeoutLimitExceeded,
)

__all__ = [
    # Runtime
    'SubagentConfig',
    'SubagentState',
    'SubagentStatus',
    'SubagentResult',
    'SubagentRuntime',
    'get_subagent_runtime',
    # Limits
    'SubagentLimits',
    'LimitExceeded',
    'DepthLimitExceeded',
    'ConcurrencyLimitExceeded',
    'TimeoutLimitExceeded',
]
