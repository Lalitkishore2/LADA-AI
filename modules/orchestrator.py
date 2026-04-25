"""
LADA v12.0 — System Orchestrator
Master integration layer that wires all Phase 1–7 subsystems together.

This module provides:
- Unified initialization of all subsystems
- Health monitoring and diagnostics
- Configuration-driven subsystem enable/disable
- Event bus for inter-module communication
- API surface for the main LADA application

Subsystems managed:
1. CrossTabSynthesizer   — multi-tab browser context
2. DLPFilter             — screen data loss prevention
3. VoicePipelineRouter   — sub-second voice I/O
4. VisualGrounder         — SoM-based visual grounding (enhanced)
5. Mem0Adapter            — semantic memory
6. YOLOPermissionClassifier — AI permission gate
7. MCPInterceptor         — MCP tool middleware
"""

from __future__ import annotations

import logging
import time
import asyncio
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List, Callable

logger = logging.getLogger(__name__)


@dataclass
class OrchestratorConfig:
    """Top-level configuration for the LADA orchestrator."""
    enable_cross_tab: bool = True
    enable_dlp: bool = True
    enable_voice: bool = True
    enable_visual_grounding: bool = True
    enable_mem0: bool = True
    enable_yolo_permissions: bool = True
    enable_mcp_interceptor: bool = True
    user_id: str = "default"
    agent_id: str = "lada"


@dataclass
class SubsystemStatus:
    name: str
    enabled: bool
    initialized: bool = False
    healthy: bool = False
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class LADAOrchestrator:
    """
    Master orchestrator for all LADA v12.0 subsystems.

    Usage::

        orch = LADAOrchestrator()
        status = await orch.initialize()
        # ... use individual subsystems via orch.cross_tab, orch.dlp, etc.
        diagnostics = orch.health_check()
    """

    def __init__(
        self,
        config: Optional[OrchestratorConfig] = None,
        ai_router: Optional[Any] = None,
        mcp_client: Optional[Any] = None,
    ) -> None:
        self.config = config or OrchestratorConfig()
        self.ai_router = ai_router
        self.mcp_client = mcp_client

        # Subsystem instances (initialized lazily)
        self.cross_tab = None
        self.dlp = None
        self.voice = None
        self.visual_grounder = None
        self.mem0 = None
        self.yolo_classifier = None
        self.mcp_interceptor = None

        # Event bus (simple callback registry)
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._init_time: Optional[float] = None
        self._statuses: Dict[str, SubsystemStatus] = {}

    async def initialize(self) -> Dict[str, SubsystemStatus]:
        """
        Initialize all enabled subsystems.

        Returns a dict of subsystem statuses.
        """
        self._init_time = time.time()
        logger.info("[Orchestrator] Initializing LADA v12.0 subsystems...")

        # 1. Cross-Tab Synthesizer
        if self.config.enable_cross_tab:
            self._statuses["cross_tab"] = self._init_cross_tab()

        # 2. DLP Filter
        if self.config.enable_dlp:
            self._statuses["dlp"] = self._init_dlp()

        # 3. Voice Pipeline
        if self.config.enable_voice:
            self._statuses["voice"] = await self._init_voice()

        # 4. Visual Grounding
        if self.config.enable_visual_grounding:
            self._statuses["visual_grounding"] = self._init_visual_grounding()

        # 5. Mem0 Memory
        if self.config.enable_mem0:
            self._statuses["mem0"] = self._init_mem0()

        # 6. YOLO Permissions
        if self.config.enable_yolo_permissions:
            self._statuses["yolo_permissions"] = self._init_yolo_classifier()

        # 7. MCP Interceptor
        if self.config.enable_mcp_interceptor:
            self._statuses["mcp_interceptor"] = self._init_mcp_interceptor()

        elapsed = (time.time() - self._init_time) * 1000
        ok_count = sum(1 for s in self._statuses.values() if s.healthy)
        total = len(self._statuses)
        logger.info(
            f"[Orchestrator] Initialized {ok_count}/{total} subsystems in {elapsed:.0f}ms"
        )
        return self._statuses

    # -- Individual subsystem initializers --

    def _init_cross_tab(self) -> SubsystemStatus:
        status = SubsystemStatus(name="CrossTabSynthesizer", enabled=True)
        try:
            from modules.cross_tab_synthesizer import CrossTabSynthesizer
            self.cross_tab = CrossTabSynthesizer()
            status.initialized = True
            status.healthy = True
            logger.info("[Orchestrator] ✓ CrossTabSynthesizer ready")
        except Exception as e:
            status.error = str(e)
            logger.warning(f"[Orchestrator] ✗ CrossTabSynthesizer: {e}")
        return status

    def _init_dlp(self) -> SubsystemStatus:
        status = SubsystemStatus(name="DLPFilter", enabled=True)
        try:
            from modules.dlp_filter import DLPFilter
            self.dlp = DLPFilter()
            status.initialized = True
            status.healthy = True
            logger.info("[Orchestrator] ✓ DLPFilter ready")
        except Exception as e:
            status.error = str(e)
            logger.warning(f"[Orchestrator] ✗ DLPFilter: {e}")
        return status

    async def _init_voice(self) -> SubsystemStatus:
        status = SubsystemStatus(name="VoicePipeline", enabled=True)
        try:
            from modules.voice_pipeline import VoicePipelineRouter
            self.voice = VoicePipelineRouter(
                intent_handler=(
                    self.ai_router.query if self.ai_router else None
                ),
            )
            voice_status = await self.voice.initialize()
            status.initialized = True
            status.healthy = True
            status.metadata = voice_status
            logger.info(f"[Orchestrator] ✓ VoicePipeline ready: {voice_status}")
        except Exception as e:
            status.error = str(e)
            logger.warning(f"[Orchestrator] ✗ VoicePipeline: {e}")
        return status

    def _init_visual_grounding(self) -> SubsystemStatus:
        status = SubsystemStatus(name="VisualGrounder", enabled=True)
        try:
            from modules.visual_grounding import VisualGrounder
            self.visual_grounder = VisualGrounder()
            status.initialized = True
            status.healthy = True
            logger.info("[Orchestrator] ✓ VisualGrounder ready")
        except Exception as e:
            status.error = str(e)
            logger.warning(f"[Orchestrator] ✗ VisualGrounder: {e}")
        return status

    def _init_mem0(self) -> SubsystemStatus:
        status = SubsystemStatus(name="Mem0Adapter", enabled=True)
        try:
            from modules.mem0_adapter import Mem0Adapter
            self.mem0 = Mem0Adapter(
                user_id=self.config.user_id,
                agent_id=self.config.agent_id,
            )
            stats = self.mem0.get_stats()
            status.initialized = True
            status.healthy = True
            status.metadata = stats
            logger.info(f"[Orchestrator] ✓ Mem0Adapter ready (backend={stats['backend']})")
        except Exception as e:
            status.error = str(e)
            logger.warning(f"[Orchestrator] ✗ Mem0Adapter: {e}")
        return status

    def _init_yolo_classifier(self) -> SubsystemStatus:
        status = SubsystemStatus(name="YOLOPermissions", enabled=True)
        try:
            from modules.yolo_permission_classifier import YOLOPermissionClassifier
            self.yolo_classifier = YOLOPermissionClassifier(
                ai_router=self.ai_router,
            )
            status.initialized = True
            status.healthy = True
            logger.info("[Orchestrator] ✓ YOLOPermissionClassifier ready")
        except Exception as e:
            status.error = str(e)
            logger.warning(f"[Orchestrator] ✗ YOLOPermissionClassifier: {e}")
        return status

    def _init_mcp_interceptor(self) -> SubsystemStatus:
        status = SubsystemStatus(name="MCPInterceptor", enabled=True)
        try:
            from modules.mcp_interceptor import MCPInterceptor
            self.mcp_interceptor = MCPInterceptor(mcp_client=self.mcp_client)
            status.initialized = True
            status.healthy = True
            logger.info("[Orchestrator] ✓ MCPInterceptor ready")
        except Exception as e:
            status.error = str(e)
            logger.warning(f"[Orchestrator] ✗ MCPInterceptor: {e}")
        return status

    # -- Health & Diagnostics --

    def health_check(self) -> Dict[str, Any]:
        """Run health checks on all subsystems."""
        results: Dict[str, Any] = {}

        if self.cross_tab:
            results["cross_tab"] = self.cross_tab.get_stats()
        if self.dlp:
            results["dlp"] = {"audit_entries": len(self.dlp._audit)}
        if self.voice:
            results["voice"] = self.voice.get_stats()
        if self.mem0:
            results["mem0"] = self.mem0.get_stats()
        if self.yolo_classifier:
            results["yolo_permissions"] = self.yolo_classifier.get_stats()
        if self.mcp_interceptor:
            results["mcp_interceptor"] = self.mcp_interceptor.get_stats()

        results["uptime_seconds"] = (
            time.time() - self._init_time if self._init_time else 0
        )
        return results

    def get_subsystem_statuses(self) -> Dict[str, Dict[str, Any]]:
        """Return initialization statuses for all subsystems."""
        return {
            name: {
                "enabled": s.enabled,
                "initialized": s.initialized,
                "healthy": s.healthy,
                "error": s.error,
                "metadata": s.metadata,
            }
            for name, s in self._statuses.items()
        }

    # -- Event Bus --

    def on(self, event: str, handler: Callable) -> None:
        """Register an event handler."""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def emit(self, event: str, **kwargs) -> None:
        """Emit an event to all registered handlers."""
        for handler in self._event_handlers.get(event, []):
            try:
                handler(**kwargs)
            except Exception as e:
                logger.error(f"[Orchestrator] Event handler error ({event}): {e}")

    # -- Convenience methods --

    def check_permission(self, command: str) -> Dict[str, Any]:
        """Check if a command is safe using YOLO classifier + DLP."""
        result: Dict[str, Any] = {"command": command, "safe": True, "tier": "safe"}

        if self.yolo_classifier:
            classification = self.yolo_classifier.classify(command)
            result["tier"] = classification.tier.value
            result["confidence"] = classification.confidence
            result["reason"] = classification.reason
            result["safe"] = classification.tier.value == "safe"

        if self.dlp:
            has_pii = self.dlp.contains_sensitive(command)
            if has_pii:
                result["dlp_warning"] = True
                result["safe"] = False

        return result

    def add_memory(self, content: str, metadata: Optional[Dict] = None) -> str:
        """Convenience: add a memory via Mem0."""
        if self.mem0:
            return self.mem0.add(content, metadata)
        return ""

    def search_memory(self, query: str, limit: int = 5) -> List[Dict]:
        """Convenience: search memories via Mem0."""
        if self.mem0:
            entries = self.mem0.search(query, limit)
            return [
                {"content": e.content, "score": e.score, "source": e.source}
                for e in entries
            ]
        return []

    async def shutdown(self) -> None:
        """Gracefully shut down all subsystems."""
        logger.info("[Orchestrator] Shutting down...")
        if self.voice:
            await self.voice.shutdown()
        if self.cross_tab:
            self.cross_tab.clear()
        logger.info("[Orchestrator] Shutdown complete")


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_instance: Optional[LADAOrchestrator] = None


def get_orchestrator(
    config: Optional[OrchestratorConfig] = None,
    ai_router: Optional[Any] = None,
    mcp_client: Optional[Any] = None,
) -> LADAOrchestrator:
    """Get or create the global LADAOrchestrator."""
    global _instance
    if _instance is None:
        _instance = LADAOrchestrator(
            config=config,
            ai_router=ai_router,
            mcp_client=mcp_client,
        )
    return _instance
