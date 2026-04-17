"""Tests for gateway daemon runtime wrapper."""

from modules.gateway_daemon import GatewayDaemonConfig, GatewayDaemon


def test_gateway_daemon_config_from_env_defaults(monkeypatch):
    monkeypatch.delenv("LADA_GATEWAY_HOST", raising=False)
    monkeypatch.delenv("LADA_GATEWAY_PORT", raising=False)
    monkeypatch.delenv("LADA_GATEWAY_LOG_LEVEL", raising=False)

    cfg = GatewayDaemonConfig.from_env()
    assert cfg.host == "0.0.0.0"
    assert cfg.port == 18790
    assert cfg.log_level == "info"


def test_gateway_daemon_config_from_env_invalid_port(monkeypatch):
    monkeypatch.setenv("LADA_GATEWAY_HOST", "127.0.0.1")
    monkeypatch.setenv("LADA_GATEWAY_PORT", "not-a-number")
    monkeypatch.setenv("LADA_GATEWAY_LOG_LEVEL", "WARNING")

    cfg = GatewayDaemonConfig.from_env()
    assert cfg.host == "127.0.0.1"
    assert cfg.port == 18790
    assert cfg.log_level == "warning"


def test_gateway_daemon_constructs():
    daemon = GatewayDaemon(GatewayDaemonConfig(host="127.0.0.1", port=18790, log_level="info"))
    assert daemon.config.host == "127.0.0.1"
    assert daemon.config.port == 18790

