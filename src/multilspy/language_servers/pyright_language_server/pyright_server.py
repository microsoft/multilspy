"""
Provides Python specific instantiation of the LanguageServer class using Pyright.
Contains various configurations and settings specific to Pyright.
"""

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


class PyrightServer(LanguageServer):
    """
    Provides Python specific instantiation of the LanguageServer class using pyright-langserver.
    Pyright is opt-in: select it with MultilspyConfig(python_server="pyright").
    The executable must be preinstalled; multilspy does not download it.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a PyrightServer instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=[config.server_binary or "pyright-langserver", "--stdio"], cwd=repository_root_path),
            "python",
        )
        self._initialize_timeout_seconds = 30
        # Pyright pushes textDocument/publishDiagnostics asynchronously. Keep a
        # bounded queue so callers can read them without unbounded growth.
        self.diagnostics: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.diagnostics_dropped = False

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Pyright Language Server.
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

    async def next_diagnostics(self, timeout: float = 5.0) -> dict:
        """
        Returns the next queued textDocument/publishDiagnostics notification, waiting at most `timeout` seconds.
        """
        return await asyncio.wait_for(self.diagnostics.get(), timeout)

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["PyrightServer"]:
        """
        Starts the Pyright Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        ```
        """

        async def workspace_configuration(params):
            # Pyright asks for the "python", "python.analysis" and "pyright"
            # sections. Answer with fixed, read-only settings; project settings
            # come from pyrightconfig.json / pyproject.toml in the workspace.
            if not isinstance(params, dict):
                return []
            items = params.get("items")
            if not isinstance(items, list) or len(items) > 64:
                return []
            settings = {
                "python": {"analysis": {}},
                "pyright": {
                    "disableLanguageServices": False,
                    "disableOrganizeImports": True,
                },
            }
            answers = []
            for item in items:
                section = item.get("section") if isinstance(item, dict) else None
                answers.append(settings.get(section) if isinstance(section, str) else None)
            return answers

        async def workspace_apply_edit(params):
            # multilspy never applies server-initiated edits.
            return {"applied": False, "failureReason": "multilspy Pyright client is read-only"}

        async def publish_diagnostics(params):
            if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
                return
            if self.diagnostics.full():
                self.diagnostics_dropped = True
                return
            self.diagnostics.put_nowait(params)

        async def do_nothing(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_request("workspace/configuration", workspace_configuration)
        self.server.on_request("workspace/applyEdit", workspace_apply_edit)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", publish_diagnostics)

        async with super().start_server():
            self.logger.log("Starting pyright-langserver server process", logging.INFO)
            initialized = False
            try:
                await self.server.start()
                initialize_params = self._get_initialize_params(self.repository_root_path)

                self.logger.log(
                    "Sending initialize request from LSP client to LSP server and awaiting response",
                    logging.INFO,
                )
                init_response = await asyncio.wait_for(
                    self.server.send.initialize(initialize_params),
                    timeout=self._initialize_timeout_seconds,
                )
                capabilities = init_response.get("capabilities") if isinstance(init_response, dict) else None
                if not isinstance(capabilities, dict):
                    raise TypeError("Invalid Pyright initialization capabilities")
                # multilspy sends UTF-16 positions, the LSP default.
                if capabilities.get("positionEncoding", "utf-16") != "utf-16":
                    raise ValueError("Unsupported Pyright position encoding")
                for required in ("definitionProvider", "referencesProvider", "hoverProvider"):
                    capability = capabilities.get(required)
                    if capability is not True and not isinstance(capability, dict):
                        raise ValueError(f"Pyright missing required capability: {required}")

                self.server.notify.initialized({})
                self.completions_available.set()
                initialized = True
                try:
                    yield self
                finally:
                    if initialized:
                        await self.server.shutdown()
            finally:
                await self.server.stop()
