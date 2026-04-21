"""Phase 4 tests for stealth browser safety bounds and routing gates."""

from core.executors.browser_executor import BrowserExecutor, validate_navigation_url
from modules.stealth_browser import StealthBrowser, StealthConfig


class _FakeDriver:
    def __init__(self):
        self.current_url = ""
        self.title = ""
        self.page_load_timeout = None
        self.script_timeout = None

    def set_page_load_timeout(self, timeout):
        self.page_load_timeout = timeout

    def set_script_timeout(self, timeout):
        self.script_timeout = timeout

    def get(self, url):
        self.current_url = url
        self.title = "Loaded"


class _FakeCore:
    def __init__(self):
        self.comet_agent = None
        self.smart_browser = None
        self.browser_tabs = None
        self.youtube_summarizer = None
        self.page_summarizer = None
        self.multi_tab = None


def test_stealth_config_reads_rollout_and_safety_env(monkeypatch):
    monkeypatch.setenv("LADA_STEALTH_BROWSER_ENABLED", "false")
    monkeypatch.setenv("LADA_STEALTH_DOMAIN_ALLOWLIST", "example.com,*.lada.ai")
    monkeypatch.setenv("LADA_STEALTH_MAX_NAVIGATION_DEPTH", "7")
    monkeypatch.setenv("LADA_STEALTH_COMMAND_TIMEOUT_SEC", "12")

    cfg = StealthConfig.from_env()

    assert cfg.enabled is False
    assert cfg.domain_allowlist == ["example.com", "*.lada.ai"]
    assert cfg.max_navigation_depth == 7
    assert cfg.command_timeout_sec == 12.0


def test_stealth_navigate_blocks_domain_outside_allowlist():
    browser = StealthBrowser(
        config=StealthConfig(
            enabled=True,
            domain_allowlist=["allowed.com"],
            max_navigation_depth=3,
            command_timeout_sec=5,
        )
    )
    browser.driver = _FakeDriver()
    browser._initialized = True

    result = browser.navigate("https://blocked.com", wait_load=False)

    assert result["success"] is False
    assert "allowlist" in result["error"].lower()


def test_stealth_navigate_enforces_max_navigation_depth():
    browser = StealthBrowser(
        config=StealthConfig(
            enabled=True,
            max_navigation_depth=1,
            command_timeout_sec=5,
        )
    )
    browser.driver = _FakeDriver()
    browser._initialized = True

    first = browser.navigate("https://example.com", wait_load=False)
    second = browser.navigate("https://example.org", wait_load=False)

    assert first["success"] is True
    assert first["depth"] == 1
    assert second["success"] is False
    assert "max navigation depth" in second["error"].lower()


def test_validate_navigation_url_enforces_allowlist(monkeypatch):
    monkeypatch.setenv("LADA_STEALTH_DOMAIN_ALLOWLIST", "allowed.com")

    ok_allowed, _ = validate_navigation_url("https://allowed.com/page")
    ok_blocked, blocked_msg = validate_navigation_url("https://blocked.com/page")

    assert ok_allowed is True
    assert ok_blocked is False
    assert "allowlist" in blocked_msg.lower()


def test_browser_executor_rejects_stealth_when_flag_disabled(monkeypatch):
    monkeypatch.setenv("LADA_STEALTH_BROWSER_ENABLED", "false")

    executor = BrowserExecutor(_FakeCore())
    handled, response = executor.try_handle("stealth go to example.com")

    assert handled is True
    assert "disabled" in response.lower()
