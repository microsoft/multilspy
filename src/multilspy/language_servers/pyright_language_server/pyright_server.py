"""Pyright Python language server adapter for multilspy.

Uses the existing language server protocol handler and a preinstalled
pyright-langserver executable. No automatic provider install is performed.
"""

import asyncio
import json
import logging
import os
import pathlib
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.lsp_types import ErrorCodes, InitializeParams
from multilspy.lsp_protocol_handler.server import Error, ProcessLaunchInfo
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


class PyrightServer(LanguageServer):
    """Python semantic requests using pyright-langserver --stdio."""

    def __init__(
        self,
        config: MultilspyConfig,
        logger: MultilspyLogger,
        repository_root_path: str,
    ):
        root = str(pathlib.Path(repository_root_path).resolve())
        super().__init__(
            config,
            logger,
            root,
            ProcessLaunchInfo(
                cmd=[config.server_binary or "pyright-langserver", "--stdio"],
                cwd=root,
            ),
            "python",
        )
        self._initialize_timeout_seconds = 30
        self.diagnostics: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)
        self.diagnostics_dropped = False

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """Load Pyright's read-only client capabilities, like other adapters."""
        config_file = pathlib.Path(__file__).with_name("initialize_params.json")
        with config_file.open(encoding="utf-8") as reader:
            params = json.load(reader)
        del params["_description"]
        root = pathlib.Path(repository_absolute_path).resolve()
        params["processId"] = os.getpid()
        params["rootPath"] = str(root)
        params["rootUri"] = root.as_uri()
        params["workspaceFolders"][0]["name"] = root.name
        params["workspaceFolders"][0]["uri"] = root.as_uri()
        return params

    async def next_diagnostics(self, timeout: float = 5.0) -> dict:
        """Read one asynchronous publishDiagnostics notification."""
        return await asyncio.wait_for(self.diagnostics.get(), timeout)

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["PyrightServer"]:
        async def configuration(params: Any) -> list:
            if not isinstance(params, dict):
                return []
            items = params.get("items")
            if not isinstance(items, list) or len(items) > 64:
                return []
            defaults = {
                "python": {"analysis": {}},
                "pyright": {
                    "disableLanguageServices": False,
                    "disableOrganizeImports": True,
                },
            }
            return [
                defaults.get(item.get("section"))
                if isinstance(item, dict) and isinstance(item.get("section"), str)
                else None
                for item in items
            ]

        async def refuse_edit(_params: Any) -> dict:
            return {
                "applied": False,
                "failureReason": "multilspy Pyright client is read-only",
            }

        async def refuse_registration(_params: Any) -> None:
            raise Error(ErrorCodes.MethodNotFound, "Dynamic registration disabled")

        async def diagnostics(params: Any) -> None:
            if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
                return
            if self.diagnostics.full():
                self.diagnostics_dropped = True
                return
            self.diagnostics.put_nowait(params)

        async def ignore_notification(_params: Any) -> None:
            return None

        self.server.on_request("workspace/configuration", configuration)
        self.server.on_request("workspace/applyEdit", refuse_edit)
        self.server.on_request("client/registerCapability", refuse_registration)
        self.server.on_notification("textDocument/publishDiagnostics", diagnostics)
        self.server.on_notification("window/logMessage", ignore_notification)
        self.server.on_notification("$/progress", ignore_notification)

        async with super().start_server():
            self.logger.log("Starting Pyright language server process", logging.INFO)
            initialized = False
            try:
                await self.server.start()
                self.logger.log("Initializing Pyright language server", logging.INFO)
                result = await asyncio.wait_for(
                    self.server.send.initialize(
                        self._get_initialize_params(self.repository_root_path)
                    ),
                    timeout=self._initialize_timeout_seconds,
                )
                capabilities = (
                    result.get("capabilities") if isinstance(result, dict) else None
                )
                if not isinstance(capabilities, dict):
                    raise TypeError("Invalid Pyright initialization capabilities")
                if capabilities.get("positionEncoding", "utf-16") != "utf-16":
                    raise ValueError("Unsupported Pyright position encoding")
                for required in (
                    "definitionProvider",
                    "referencesProvider",
                    "hoverProvider",
                ):
                    capability = capabilities.get(required)
                    if capability is not True and not isinstance(capability, dict):
                        raise ValueError(
                            f"Pyright missing required capability: {required}"
                        )

                self.server.notify.initialized({})
                self.completions_available.set()
                initialized = True
                try:
                    yield self
                finally:
                    if initialized:
                        await asyncio.wait_for(self.server.shutdown(), timeout=8)
            finally:
                await self.server.stop()
