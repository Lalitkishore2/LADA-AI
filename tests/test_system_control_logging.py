import logging
import threading
from unittest.mock import patch

from modules import system_control as sc


def _make_missing_module_error(name: str) -> ModuleNotFoundError:
    err = ModuleNotFoundError(f"No module named '{name}'")
    err.name = name
    return err


def test_optional_dependency_warning_logged_once(caplog):
    controller = object.__new__(sc.SystemController)
    controller._optional_dep_warnings = set()

    with caplog.at_level(logging.DEBUG, logger=sc.logger.name):
        controller._log_operation_error(
            "getting volume",
            _make_missing_module_error("pycaw"),
            optional_modules=("pycaw",),
        )
        controller._log_operation_error(
            "getting volume",
            _make_missing_module_error("pycaw"),
            optional_modules=("pycaw",),
        )

    warning_messages = [r.message for r in caplog.records if r.levelno == logging.WARNING]
    error_messages = [r.message for r in caplog.records if r.levelno == logging.ERROR]
    debug_messages = [r.message for r in caplog.records if r.levelno == logging.DEBUG]

    assert len(warning_messages) == 1
    assert "optional dependency 'pycaw'" in warning_messages[0]
    assert not error_messages
    assert any("still unavailable" in msg for msg in debug_messages)


def test_non_optional_failure_logs_error(caplog):
    controller = object.__new__(sc.SystemController)
    controller._optional_dep_warnings = set()

    with caplog.at_level(logging.ERROR, logger=sc.logger.name):
        controller._log_operation_error(
            "getting volume",
            RuntimeError("device query failed"),
            optional_modules=("pycaw",),
        )

    error_messages = [r.message for r in caplog.records if r.levelno == logging.ERROR]
    assert error_messages
    assert "Error getting volume: device query failed" in error_messages[0]


def test_optional_library_logger_noise_suppressed_once():
    controller = object.__new__(sc.SystemController)
    configured_levels = []

    class _DummyLogger:
        def __init__(self, name):
            self.name = name

        def setLevel(self, level):
            configured_levels.append((self.name, level))

    original_flag = sc._NOISY_OPTIONAL_LOGGERS_CONFIGURED
    sc._NOISY_OPTIONAL_LOGGERS_CONFIGURED = False
    try:
        with patch("modules.system_control.logging.getLogger", side_effect=lambda name=None: _DummyLogger(name)):
            controller._configure_optional_library_loggers()
            controller._configure_optional_library_loggers()
    finally:
        sc._NOISY_OPTIONAL_LOGGERS_CONFIGURED = original_flag

    assert configured_levels == [("screen_brightness_control.windows", logging.ERROR)]


def test_optional_library_logger_noise_suppressed_once_concurrent():
    controller = object.__new__(sc.SystemController)
    configured_levels = []
    configured_lock = threading.Lock()

    class _DummyLogger:
        def __init__(self, name):
            self.name = name

        def setLevel(self, level):
            with configured_lock:
                configured_levels.append((self.name, level))

    original_flag = sc._NOISY_OPTIONAL_LOGGERS_CONFIGURED
    sc._NOISY_OPTIONAL_LOGGERS_CONFIGURED = False
    barrier = threading.Barrier(8)

    def _worker():
        barrier.wait()
        controller._configure_optional_library_loggers()

    try:
        with patch("modules.system_control.logging.getLogger", side_effect=lambda name=None: _DummyLogger(name)):
            threads = [threading.Thread(target=_worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
    finally:
        sc._NOISY_OPTIONAL_LOGGERS_CONFIGURED = original_flag

    assert configured_levels == [("screen_brightness_control.windows", logging.ERROR)]
