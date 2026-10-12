"""Exercise adapter callbacks without downloading or launching language servers."""

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from multilspy.language_server import LanguageServer
from multilspy.language_servers.clangd_language_server.clangd_language_server import ClangdLanguageServer
from multilspy.language_servers.rust_analyzer.rust_analyzer import RustAnalyzer
from multilspy.language_servers.solargraph.solargraph import Solargraph
from multilspy.language_servers.typescript_language_server.typescript_language_server import TypeScriptLanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


ADAPTERS = [
    (ClangdLanguageServer, Language.CPP, {
        "triggerCharacters": ['.', '<', '>', ':', '"', '/', '*'], "resolveProvider": False,
    }),
    (RustAnalyzer, Language.RUST, {
        "resolveProvider": True, "triggerCharacters": [":", ".", "'", "("],
        "completionItem": {"labelDetailsSupport": True},
    }),
    (Solargraph, Language.RUBY, {
        "resolveProvider": True, "triggerCharacters": [".", ":", "@"],
    }),
    (TypeScriptLanguageServer, Language.TYPESCRIPT, {
        "triggerCharacters": ['.', '"', "'", '/', '@', '<'], "resolveProvider": True,
    }),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("adapter, language, completion_provider, notification", [
    (*adapter, notification)
    for adapter in ADAPTERS
    for notification in ("client/registerCapability", "language/status")
    if adapter[0] is not TypeScriptLanguageServer or notification != "language/status"
])
async def test_adapter_notifications_during_initialization(
    tmp_path, adapter, language, completion_provider, notification
):
    # Initialize the shared state without triggering adapter runtime downloads.
    server = adapter.__new__(adapter)
    LanguageServer.__init__(
        server, MultilspyConfig(code_language=language), MultilspyLogger(),
        str(tmp_path), ProcessLaunchInfo(cmd=["unused"], cwd=str(tmp_path)), str(language),
    )
    server.server_ready = asyncio.Event()
    requests, notifications = {}, {}
    transport = Mock()
    transport.on_request.side_effect = lambda method, handler: requests.update({method: handler})
    transport.on_notification.side_effect = lambda method, handler: notifications.update({method: handler})
    transport.start = AsyncMock()
    transport.shutdown = AsyncMock()
    transport.stop = AsyncMock()

    async def initialize(params):
        if notification == "client/registerCapability":
            result = await requests[notification]({"registrations": [{
                "id": "commands", "method": "workspace/executeCommand",
                "registerOptions": {"commands": ["example.command"]},
            }]})
            assert result is None
        else:
            await notifications[notification]({"type": "ServiceReady", "message": "ServiceReady"})

        # Rust's actual readiness notification must still work.
        if adapter is RustAnalyzer:
            await notifications["experimental/serverStatus"]({"quiescent": False})
            assert not server.server_ready.is_set()
            await notifications["experimental/serverStatus"]({"quiescent": True})
            assert server.server_ready.is_set()
        return {"capabilities": {
            "textDocumentSync": 2 if adapter in (Solargraph, TypeScriptLanguageServer) else {"change": 2},
            "completionProvider": completion_provider,
        }}

    transport.send.initialize = AsyncMock(side_effect=initialize)
    server.server = transport
    async with server.start_server():
        assert server.server_started
        assert server.completions_available.is_set()
    assert not server.server_started
    transport.shutdown.assert_awaited_once()
    transport.stop.assert_awaited_once()
