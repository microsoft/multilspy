import asyncio
import json
import logging
import os
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig


class Gopls(LanguageServer):
    """
    Provides Go specific instantiation of the LanguageServer class using gopls.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd="gopls", cwd=repository_root_path),
            "go",
        )
        self.server_ready = asyncio.Event()
        self.request_id = 0

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the TypeScript Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r") as f:
            d = json.load(f)

        del d["_description"]

        d["processId"] = os.getpid()
        assert d["rootPath"] == "$rootPath"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "$rootUri"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["uri"] == "$uri"
        d["workspaceFolders"][0]["uri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["name"] == "$name"
        d["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["Gopls"]:
        """Start gopls server process"""
        async def register_capability_handler(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        async def do_nothing(params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        async with super().start_server():
            self.logger.log("Starting gopls server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)
            
            # Verify server capabilities
            assert "textDocumentSync" in init_response["capabilities"]
            assert "completionProvider" in init_response["capabilities"]
            assert "definitionProvider" in init_response["capabilities"]

            self.server.notify.initialized({})
            self.completions_available.set()

            # gopls server is typically ready immediately after initialization
            self.server_ready.set()
            await self.server_ready.wait()

            yield self

            await self.server.shutdown()
            await self.server.stop()
