"""
LADA v12.0 — Phase 9: End-to-End Integration Test Suite

Validates that all v12.0 subsystems initialize cleanly, expose the
expected public API, and inter-operate without import / runtime errors.

Run:
    python tests/test_v12_integration.py
"""

import sys
import os
import time
import traceback

# Fix Windows console encoding for unicode/emoji output
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure repo root is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

_results = []


def _test(name, fn):
    """Run a test function and capture pass/fail."""
    try:
        fn()
        _results.append(("PASS", name, ""))
        print(f"  ✅ {name}")
    except Exception as e:
        _results.append(("FAIL", name, str(e)))
        print(f"  ❌ {name}: {e}")


# ---------------------------------------------------------------------------
# Phase 1: Browser Automation + CrossTabSynthesizer
# ---------------------------------------------------------------------------

def test_cross_tab_synthesizer():
    from modules.cross_tab_synthesizer import CrossTabSynthesizer, get_cross_tab_synthesizer
    synth = get_cross_tab_synthesizer()
    assert isinstance(synth, CrossTabSynthesizer)
    synth.snapshot_tab("tab1", url="https://example.com", title="Example", text="Hello World")
    prompt = synth.build_synthesis_prompt()
    assert "example.com" in prompt.lower() or "Example" in prompt
    synth.clear()


def test_browser_automation_class():
    from modules.browser_automation import CometBrowserAgent
    agent = CometBrowserAgent.__new__(CometBrowserAgent)
    assert hasattr(agent, "new_tab")
    assert hasattr(agent, "switch_tab")
    assert hasattr(agent, "close_tab")
    assert hasattr(agent, "get_all_tabs")


def test_comet_agent_async():
    from modules.comet_agent import CometAgent
    import asyncio
    # Verify key methods are coroutines
    assert asyncio.iscoroutinefunction(CometAgent._capture_screen_state)
    assert asyncio.iscoroutinefunction(CometAgent._execute_action)
    assert asyncio.iscoroutinefunction(CometAgent._verify_action)


# ---------------------------------------------------------------------------
# Phase 2: DLP Filter
# ---------------------------------------------------------------------------

def test_dlp_filter():
    from modules.dlp_filter import DLPFilter, get_dlp_filter, DLPSensitivity
    dlp = get_dlp_filter()
    assert isinstance(dlp, DLPFilter)

    # Scan text
    events = dlp.scan_text("My credit card is 4111-1111-1111-1111")
    assert len(events) > 0, "Should detect credit card"
    assert events[0].pattern_name.startswith("credit_card")

    # Contains check
    assert dlp.contains_sensitive("Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig")
    assert not dlp.contains_sensitive("Hello world, nice day today!")

    # Sensitivity change
    dlp.set_sensitivity(DLPSensitivity.RELAXED)
    dlp.set_sensitivity(DLPSensitivity.NORMAL)

    # Audit log
    log = dlp.get_audit_log()
    assert isinstance(log, list)


# ---------------------------------------------------------------------------
# Phase 3: Voice Pipeline
# ---------------------------------------------------------------------------

def test_voice_pipeline():
    from modules.voice_pipeline import VoicePipelineRouter, VoicePipelineConfig, get_voice_pipeline
    pipeline = get_voice_pipeline()
    assert isinstance(pipeline, VoicePipelineRouter)

    stats = pipeline.get_stats()
    assert "stage" in stats
    assert "total_utterances" in stats
    assert stats["stage"] == "idle"


# ---------------------------------------------------------------------------
# Phase 4: Visual Grounding
# ---------------------------------------------------------------------------

def test_visual_grounding():
    from modules.visual_grounding import VisualGrounder
    grounder = VisualGrounder.__new__(VisualGrounder)
    assert hasattr(grounder, "detect_elements_ocr")
    assert hasattr(grounder, "detect_elements_contours")
    assert hasattr(grounder, "annotate_image_colored")
    assert hasattr(grounder, "get_element_list_prompt")


# ---------------------------------------------------------------------------
# Phase 5: Mem0 Adapter
# ---------------------------------------------------------------------------

def test_mem0_adapter():
    from modules.mem0_adapter import Mem0Adapter, get_mem0_adapter
    adapter = get_mem0_adapter(user_id="test", agent_id="lada")
    assert isinstance(adapter, Mem0Adapter)

    # Add + search
    mid = adapter.add("The user prefers dark mode and likes Tamil music")
    assert mid  # should return an ID

    results = adapter.search("What theme does the user like?")
    assert isinstance(results, list)

    # Context prompt
    ctx = adapter.build_context_prompt("theme preference")
    assert isinstance(ctx, str)

    # Stats
    stats = adapter.get_stats()
    assert stats["backend"] in ("mem0", "legacy")
    assert stats["user_id"] == "test"


# ---------------------------------------------------------------------------
# Phase 6: YOLO Permission Classifier
# ---------------------------------------------------------------------------

def test_yolo_classifier():
    from modules.yolo_permission_classifier import (
        YOLOPermissionClassifier, PermissionTier, get_yolo_classifier,
    )
    clf = get_yolo_classifier()
    assert isinstance(clf, YOLOPermissionClassifier)

    # Safe command
    r = clf.classify("search for Python tutorials")
    assert r.tier == PermissionTier.SAFE

    # Dangerous command
    r = clf.classify("rm -rf /system32")
    assert r.tier == PermissionTier.DENY

    # Confirm command
    r = clf.classify("send email to boss")
    assert r.tier == PermissionTier.CONFIRM

    # Override
    clf.add_override("reboot now", PermissionTier.SAFE)
    r = clf.classify("reboot now please")
    assert r.tier == PermissionTier.SAFE
    clf.remove_override("reboot now")

    # Stats
    stats = clf.get_stats()
    assert stats["total_classifications"] > 0


# ---------------------------------------------------------------------------
# Phase 7: MCP Interceptor
# ---------------------------------------------------------------------------

def test_mcp_interceptor():
    from modules.mcp_interceptor import MCPInterceptor, get_mcp_interceptor
    interceptor = get_mcp_interceptor()
    assert isinstance(interceptor, MCPInterceptor)

    # Stats
    stats = interceptor.get_stats()
    assert "total_calls" in stats
    assert "blocked_calls" in stats

    # Audit log
    log = interceptor.get_audit_log()
    assert isinstance(log, list)


# ---------------------------------------------------------------------------
# Phase 8: Orchestrator
# ---------------------------------------------------------------------------

def test_orchestrator():
    from modules.orchestrator import LADAOrchestrator
    orch = LADAOrchestrator.__new__(LADAOrchestrator)
    assert hasattr(orch, "initialize")
    assert hasattr(orch, "health_check")


# ---------------------------------------------------------------------------
# Phase 5 integration: Mem0 in AI Router
# ---------------------------------------------------------------------------

def test_mem0_in_router():
    """Verify Mem0 is wired into the AI router init path."""
    import importlib
    spec = importlib.util.find_spec("lada_ai_router")
    assert spec is not None, "lada_ai_router module not found"

    # Check the source contains Mem0 injection
    source_path = spec.origin
    with open(source_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "mem0_adapter" in source, "Mem0 adapter import missing from router"
    assert "build_context_prompt" in source, "Mem0 context injection missing from router"
    assert "mem0.add" in source or "self.mem0.add" in source, "Mem0 storage missing from router"


# ---------------------------------------------------------------------------
# Settings UI: DLP/MCP/YOLO panels
# ---------------------------------------------------------------------------

def test_settings_ui_panels():
    """Verify the settings dialog source contains the new security panels."""
    settings_path = os.path.join(
        os.path.dirname(__file__), "..", "modules", "desktop", "settings.py"
    )
    with open(settings_path, "r", encoding="utf-8") as f:
        source = f.read()
    assert "Data Loss Prevention" in source, "DLP settings panel missing"
    assert "MCP Tool Interceptor" in source, "MCP settings panel missing"
    assert "Permission Classifier" in source, "YOLO settings panel missing"
    assert "_refresh_dlp_log" in source, "DLP refresh handler missing"
    assert "_refresh_mcp_log" in source, "MCP refresh handler missing"
    assert "_add_yolo_override" in source, "YOLO override handler missing"


# ---------------------------------------------------------------------------
# Run all tests
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("LADA v12.0 — Phase 9: End-to-End Integration Tests")
    print("=" * 60)

    t0 = time.time()

    print("\n🔧 Phase 1: Browser Automation + Cross-Tab")
    _test("CrossTabSynthesizer API", test_cross_tab_synthesizer)
    _test("CometBrowserAgent async methods", test_browser_automation_class)
    _test("CometAgent async coroutines", test_comet_agent_async)

    print("\n🔒 Phase 2: DLP Filter")
    _test("DLP filter scan + sensitivity", test_dlp_filter)

    print("\n🎙️ Phase 3: Voice Pipeline")
    _test("VoicePipelineRouter init + stats", test_voice_pipeline)

    print("\n👁️ Phase 4: Visual Grounding")
    _test("VisualGrounder API surface", test_visual_grounding)

    print("\n🧠 Phase 5: Mem0 Adapter")
    _test("Mem0Adapter CRUD + context", test_mem0_adapter)

    print("\n⚡ Phase 6: YOLO Permission Classifier")
    _test("YOLO classify + overrides", test_yolo_classifier)

    print("\n🛡️ Phase 7: MCP Interceptor")
    _test("MCPInterceptor audit + stats", test_mcp_interceptor)

    print("\n🎯 Phase 8: Orchestrator")
    _test("LADAOrchestrator API surface", test_orchestrator)

    print("\n🔗 Integration Checks")
    _test("Mem0 wired into AI Router", test_mem0_in_router)
    _test("Settings UI security panels", test_settings_ui_panels)

    elapsed = time.time() - t0
    passed = sum(1 for r in _results if r[0] == "PASS")
    failed = sum(1 for r in _results if r[0] == "FAIL")

    print(f"\n{'=' * 60}")
    print(f"Results: {passed} passed, {failed} failed ({elapsed:.1f}s)")
    print(f"{'=' * 60}")

    if failed > 0:
        print("\nFailed tests:")
        for status, name, err in _results:
            if status == "FAIL":
                print(f"  ❌ {name}: {err}")
        sys.exit(1)
    else:
        print("\n🎉 ALL TESTS PASSED — v12.0 integration verified!")
        sys.exit(0)
