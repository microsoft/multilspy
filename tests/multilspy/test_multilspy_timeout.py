"""
Tests for per-request timeout protection and graceful fallback in multilspy LanguageServer.
"""

import asyncio
import logging
import pytest
import time
from pathlib import PurePath
from unittest.mock import AsyncMock, MagicMock

from multilspy import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from tests.test_utils import create_test_context

pytest_plugins = ("pytest_asyncio",)


@pytest.mark.asyncio
async def test_multilspy_request_definition_timeout_fallback(caplog) -> None:
    """
    Test that request_definition times out fast and falls back to [] when server stalls,
    logging a structured warning and checking process health.
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        async with lsp.start_server():
            # First verify normal definition works
            res_normal = await lsp.request_definition(str(PurePath("src/black/mode.py")), 163, 4)
            assert isinstance(res_normal, list)
            assert len(res_normal) >= 1

            # Simulate a stalled language server by wrapping definition RPC
            real_send_def = lsp.server.send.definition

            async def stalled_definition(*args, **kwargs):
                await asyncio.sleep(10.0)
                return await real_send_def(*args, **kwargs)

            lsp.server.send.definition = stalled_definition

            # Verify that request times out fast and returns empty list []
            start_time = time.time()
            with caplog.at_level(logging.WARNING):
                result = await lsp.request_definition(
                    str(PurePath("src/black/mode.py")), 163, 4, timeout=0.2
                )
            elapsed = time.time() - start_time

            assert elapsed < 2.0, f"Expected fast failure under 2.0s, took {elapsed}s"
            assert result == [], "Expected empty list fallback on timeout"
            assert lsp.is_process_alive() is True, "Expected process to still be alive"
            assert lsp.check_process_health() is True

            # Verify structured warning was logged
            warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert any(
                "LSP request timed out" in r.message and "textDocument/definition" in r.message
                for r in warning_logs
            )


@pytest.mark.asyncio
async def test_multilspy_request_references_timeout_fallback(caplog) -> None:
    """
    Test that request_references times out fast and falls back to [] when server stalls.
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        async with lsp.start_server():
            async def stalled_references(*args, **kwargs):
                await asyncio.sleep(10.0)
                return []

            lsp.server.send.references = stalled_references

            start_time = time.time()
            with caplog.at_level(logging.WARNING):
                result = await lsp.request_references(
                    str(PurePath("src/black/mode.py")), 163, 4, timeout=0.2
                )
            elapsed = time.time() - start_time

            assert elapsed < 2.0
            assert result == []
            assert lsp.is_process_alive() is True
            warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert any(
                "LSP request timed out" in r.message and "textDocument/references" in r.message
                for r in warning_logs
            )


@pytest.mark.asyncio
async def test_multilspy_request_completions_timeout_fallback(caplog) -> None:
    """
    Test that request_completions times out fast and falls back to [].
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        async with lsp.start_server():
            async def stalled_completion(*args, **kwargs):
                await asyncio.sleep(10.0)
                return []

            lsp.server.send.completion = stalled_completion

            start_time = time.time()
            with caplog.at_level(logging.WARNING):
                result = await lsp.request_completions(
                    str(PurePath("src/black/mode.py")), 163, 4, timeout=0.2
                )
            elapsed = time.time() - start_time

            assert elapsed < 2.0
            assert result == []
            assert lsp.is_process_alive() is True
            warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert any(
                "LSP request timed out" in r.message and "textDocument/completion" in r.message
                for r in warning_logs
            )


@pytest.mark.asyncio
async def test_multilspy_request_document_symbols_timeout_fallback(caplog) -> None:
    """
    Test that request_document_symbols times out fast and falls back to ([], None).
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        async with lsp.start_server():
            async def stalled_document_symbol(*args, **kwargs):
                await asyncio.sleep(10.0)
                return []

            lsp.server.send.document_symbol = stalled_document_symbol

            start_time = time.time()
            with caplog.at_level(logging.WARNING):
                result, tree = await lsp.request_document_symbols(
                    str(PurePath("src/black/mode.py")), timeout=0.2
                )
            elapsed = time.time() - start_time

            assert elapsed < 2.0
            assert result == []
            assert tree is None
            assert lsp.is_process_alive() is True
            warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert any(
                "LSP request timed out" in r.message and "textDocument/documentSymbol" in r.message
                for r in warning_logs
            )


@pytest.mark.asyncio
async def test_multilspy_request_hover_timeout_fallback(caplog) -> None:
    """
    Test that request_hover times out fast and falls back to None.
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        async with lsp.start_server():
            async def stalled_hover(*args, **kwargs):
                await asyncio.sleep(10.0)
                return None

            lsp.server.send.hover = stalled_hover

            start_time = time.time()
            with caplog.at_level(logging.WARNING):
                result = await lsp.request_hover(
                    str(PurePath("src/black/mode.py")), 163, 4, timeout=0.2
                )
            elapsed = time.time() - start_time

            assert elapsed < 2.0
            assert result is None
            assert lsp.is_process_alive() is True
            warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
            assert any(
                "LSP request timed out" in r.message and "textDocument/hover" in r.message
                for r in warning_logs
            )


@pytest.mark.asyncio
async def test_multilspy_config_default_timeout() -> None:
    """
    Test that MultilspyConfig.request_timeout is respected as the default timeout.
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23",
    }
    with create_test_context(params) as context:
        context.config.request_timeout = 0.2
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        assert lsp.request_timeout == 0.2

        async with lsp.start_server():
            async def stalled_definition(*args, **kwargs):
                await asyncio.sleep(10.0)
                return []

            lsp.server.send.definition = stalled_definition

            start_time = time.time()
            result = await lsp.request_definition(str(PurePath("src/black/mode.py")), 163, 4)
            elapsed = time.time() - start_time

            assert elapsed < 2.0
            assert result == []


def test_process_health_check_dead_process(caplog) -> None:
    """
    Test that check_process_health correctly detects a dead process and logs a warning.
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # Simulate dead process
        mock_process = MagicMock()
        mock_process.returncode = 137
        lsp.server.process = mock_process

        assert lsp.is_process_alive() is False
        with caplog.at_level(logging.WARNING):
            healthy = lsp.check_process_health()

        assert healthy is False
        warning_logs = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert any(
            "Language server process is not alive (returncode: 137)" in r.message
            for r in warning_logs
        )


@pytest.mark.asyncio
async def test_request_timeout_sends_cancel_request() -> None:
    """
    Test that when an RPC request times out, LanguageServerHandler sends $/cancelRequest
    with the timed-out request id to the LSP server.
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        async with lsp.start_server():
            # Spy on cancel_request notification
            cancel_calls = []
            real_cancel = lsp.server.notify.cancel_request

            def cancel_spy(params):
                cancel_calls.append(params)
                return real_cancel(params)

            lsp.server.notify.cancel_request = cancel_spy

            # Mock _send_payload to ONLY drop textDocument/definition so the server never responds to it,
            # while allowing initialize and shutdown to proceed normally
            real_send_payload = lsp.server._send_payload

            async def drop_definition_payload(payload):
                if payload.get("method") == "textDocument/definition":
                    return
                return await real_send_payload(payload)

            lsp.server._send_payload = drop_definition_payload

            result = await lsp.request_definition(
                str(PurePath("src/black/mode.py")), 163, 4, timeout=0.2
            )

            assert result == []
            # Verify $/cancelRequest was sent with the request id
            assert len(cancel_calls) == 1
            assert "id" in cancel_calls[0]
            assert isinstance(cancel_calls[0]["id"], int)

            # Restore original _send_payload for clean shutdown
            lsp.server._send_payload = real_send_payload

