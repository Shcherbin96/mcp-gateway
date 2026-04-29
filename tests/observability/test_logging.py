"""Verify structlog emits JSON with required fields."""

import json
import logging

import pytest

from gateway.observability.logging import configure_logging, get_logger

pytestmark = pytest.mark.unit


def test_log_emits_json(capsys):
    configure_logging()
    log = get_logger("test")
    log.info("hello", foo="bar")
    captured = capsys.readouterr().out
    line = captured.strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "hello"
    assert payload["foo"] == "bar"
    assert payload["level"] == "info"
    assert "timestamp" in payload


def test_log_respects_level(capsys, monkeypatch):
    monkeypatch.setenv("MCP_LOG_LEVEL", "WARNING")
    from gateway.config import get_settings

    get_settings.cache_clear()
    configure_logging()
    log = get_logger("test")
    log.debug("nope")
    log.warning("yes")
    out = capsys.readouterr().out
    assert "yes" in out
    assert "nope" not in out
    # restore
    logging.getLogger().setLevel(logging.INFO)
    monkeypatch.delenv("MCP_LOG_LEVEL")
    get_settings.cache_clear()
