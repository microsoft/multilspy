"""Pyright adapter callbacks and startup behavior without a language-server process.

Mirrors the mock-transport pattern from test_adapter_notifications.py.
"""

import asyncio
import os
from unittest.mock import AsyncMock, Mock

import pytest

from multilspy.language_server import LanguageServer
from multilspy.language_servers.pyright_language_server.pyright_server import (
    PyrightServer,
)
from multilspy.lsp_protocol_handler.lsp_types import ErrorCodes
from multilspy.lsp_protocol_handler.server import Error
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


@pytest.fixture
def pyright(tmp_path):
    server = LanguageServer.create(
        MultilspyConfig(code_language=Language.PYTHON, python_server="pyright"),
        MultilspyLogger(),
        str(tmp_path.resolve()),
    )
    assert isinstance(server, PyrightServer)
    requests, notifications = {}, {}
    transport = Mock()
    transport.on_request.side_effect = lambda method, handler: requests.update(
        {method: handler}
    )
    transport.on_notification.side_effect = lambda method, handler: (
        notifications.update({method: handler})
    )
    transport.start = AsyncMock()
    transport.shutdown = AsyncMock()
    transport.stop = AsyncMock()
    transport.send.initialize = AsyncMock(
        return_value={
            "capabilities": {
                "definitionProvider": True,
                "referencesProvider": True,
                "hoverProvider": True,
                "textDocumentSync": 2,
            }
        }
    )
    server.server = transport
    return server, transport, requests, notifications


def test_pyright_initialize_params_are_loaded_from_profile(tmp_path):
    server = LanguageServer.create(
        MultilspyConfig(code_language=Language.PYTHON, python_server="pyright"),
        MultilspyLogger(),
        str(tmp_path.resolve()),
    )
    params = server._get_initialize_params(str(tmp_path.resolve()))
    assert "_description" not in params
    assert params["processId"] == os.getpid()
    assert params["rootUri"] == tmp_path.resolve().as_uri()
    assert params["rootPath"] == str(tmp_path.resolve())
    assert params["workspaceFolders"] == [
        {"name": tmp_path.resolve().name, "uri": tmp_path.resolve().as_uri()}
    ]
    assert params["capabilities"]["general"]["positionEncodings"] == ["utf-16"]
    assert params["capabilities"]["workspace"]["applyEdit"] is False
    assert params["capabilities"]["workspace"]["configuration"] is True
    assert params["capabilities"]["textDocument"]["completion"]
    assert params["capabilities"]["textDocument"]["signatureHelp"]


@pytest.mark.asyncio
async def test_pyright_initializes_and_cleans_up_like_existing_adapters(pyright):
    server, transport, requests, notifications = pyright
    async with server.start_server():
        assert server.server_started
        assert server.completions_available.is_set()
        transport.send.initialize.assert_awaited_once()
        transport.notify.initialized.assert_called_once_with({})
        assert "workspace/configuration" in requests
        assert "workspace/applyEdit" in requests
        assert "client/registerCapability" in requests
        assert "textDocument/publishDiagnostics" in notifications
        assert "window/logMessage" in notifications
        assert "$/progress" in notifications
        assert transport.start.await_count == 1
    assert not server.server_started
    transport.shutdown.assert_awaited_once()
    transport.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_pyright_accepts_empty_capability_options(pyright):
    server, transport, _, _ = pyright
    transport.send.initialize.return_value = {
        "capabilities": {
            "definitionProvider": {},
            "referencesProvider": {},
            "hoverProvider": {},
            "positionEncoding": "utf-16",
        }
    }
    async with server.start_server():
        assert server.server_started
        assert server.completions_available.is_set()
    transport.shutdown.assert_awaited_once()
    transport.stop.assert_awaited_once()


@pytest.mark.asyncio
async def test_pyright_configuration_is_explicit_and_bounded(pyright):
    server, _, requests, _ = pyright
    async with server.start_server():
        handler = requests["workspace/configuration"]
        result = await handler(
            {
                "items": [
                    {"section": "python"},
                    {"section": "pyright"},
                    {"section": "untrusted"},
                ]
            }
        )
        assert result[0] == {"analysis": {}}
        assert result[1]["disableLanguageServices"] is False
        assert result[2] is None
        assert await handler({"items": []}) == []
        assert await handler({"items": "bad"}) == []
        assert await handler({"items": [{}] * 65}) == []
        assert await handler(None) == []


@pytest.mark.asyncio
async def test_pyright_refuses_edit_and_unadvertised_registration(pyright):
    server, _, requests, _ = pyright
    async with server.start_server():
        result = await requests["workspace/applyEdit"](
            {"edit": {"changes": {"file:///tmp/example.py": []}}}
        )
        assert result["applied"] is False
        assert "read-only" in result["failureReason"]
        with pytest.raises(Error) as caught:
            await requests["client/registerCapability"](
                {"registrations": [{"method": "workspace/executeCommand"}]}
            )
        assert caught.value.code == ErrorCodes.MethodNotFound


@pytest.mark.asyncio
async def test_pyright_diagnostics_are_queued_not_dropped_silently(pyright):
    server, _, _, notifications = pyright
    async with server.start_server():
        await notifications["textDocument/publishDiagnostics"](None)
        await notifications["textDocument/publishDiagnostics"]({"uri": 12})
        assert server.diagnostics.empty()
        for i in range(64):
            await notifications["textDocument/publishDiagnostics"](
                {
                    "uri": "file:///tmp/example.py",
                    "diagnostics": [],
                    "version": i,
                }
            )
        assert server.diagnostics.full()
        await notifications["textDocument/publishDiagnostics"](
            {
                "uri": "file:///tmp/example.py",
                "version": 65,
            }
        )
        assert server.diagnostics_dropped is True
        assert (await server.next_diagnostics(timeout=1))["version"] == 0
        assert (await server.next_diagnostics(timeout=1))["version"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capabilities, exception, error",
    [
        (None, TypeError, "Invalid Pyright"),
        ([], TypeError, "Invalid Pyright"),
        ({}, ValueError, "Pyright missing required capability"),
        (
            {
                "definitionProvider": True,
                "referencesProvider": True,
                "hoverProvider": True,
                "positionEncoding": "utf-8",
            },
            ValueError,
            "Unsupported Pyright position",
        ),
    ],
)
async def test_bad_initialize_rejected_and_process_stopped(
    pyright, capabilities, exception, error
):
    server, transport, _, _ = pyright
    transport.send.initialize.return_value = {"capabilities": capabilities}
    with pytest.raises(exception, match=error):
        async with server.start_server():
            pytest.fail("Malformed capabilities cannot enable a server")
    transport.stop.assert_awaited_once()
    transport.shutdown.assert_not_awaited()
    assert not server.server_started


@pytest.mark.asyncio
async def test_failed_initialize_request_still_stops_provider(pyright):
    server, transport, _, _ = pyright
    transport.send.initialize.side_effect = TimeoutError("synthetic")
    with pytest.raises(TimeoutError):
        async with server.start_server():
            pytest.fail("Initialize must fail")
    transport.stop.assert_awaited_once()
    transport.shutdown.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_process_start_still_enters_stop_cleanup(pyright):
    server, transport, _, _ = pyright
    transport.start.side_effect = OSError("synthetic failed spawn")
    with pytest.raises(OSError):
        async with server.start_server():
            pytest.fail("Process start must fail")
    transport.stop.assert_awaited_once()
    transport.shutdown.assert_not_awaited()


@pytest.mark.asyncio
async def test_shutdown_error_never_skips_process_stop(pyright):
    server, transport, _, _ = pyright
    transport.shutdown.side_effect = RuntimeError("synthetic shutdown failure")
    with pytest.raises(RuntimeError, match="shutdown failure"):
        async with server.start_server():
            assert server.server_started
    transport.shutdown.assert_awaited_once()
    transport.stop.assert_awaited_once()
    assert not server.server_started


@pytest.mark.asyncio
async def test_cancelled_initialize_still_stops_process(pyright):
    server, transport, _, _ = pyright
    ready = asyncio.Event()
    block = asyncio.Event()

    async def initialize(_params):
        ready.set()
        await block.wait()

    transport.send.initialize.side_effect = initialize

    async def enter_context():
        async with server.start_server():
            pytest.fail("Cancelled initialization cannot enter context")

    task = asyncio.create_task(enter_context())
    await asyncio.wait_for(ready.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    transport.stop.assert_awaited_once()
    transport.shutdown.assert_not_awaited()
    assert not server.server_started
