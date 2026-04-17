"""Tests for KAIROS idle loop integration in JarvisCommandProcessor."""

from lada_jarvis_core import JarvisCommandProcessor


def test_record_activity_increments_session_and_timestamp():
    JarvisCommandProcessor._start_kairos_loop = lambda self: None  # type: ignore[assignment]
    proc = JarvisCommandProcessor(ai_router=None)
    before = proc._session_count
    before_ts = proc._last_activity_ts
    proc._record_activity()
    assert proc._session_count == before + 1
    assert proc._last_activity_ts >= before_ts


def test_kairos_consolidation_no_memory_is_noop():
    JarvisCommandProcessor._start_kairos_loop = lambda self: None  # type: ignore[assignment]
    proc = JarvisCommandProcessor(ai_router=None)
    proc.memory = None
    proc._run_kairos_consolidation()
    # no exception => pass
