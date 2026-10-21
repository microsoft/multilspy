"""
Provides Python specific instantiation of the LanguageServer class using Pyright.
Contains various configurations and settings specific to Pyright.
"""

import asyncio
import inspect
import json
import logging
import math
import os
import pathlib
import shutil
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_exceptions import MultilspyException
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


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
        executable = config.server_binary or "pyright-langserver"
        # npm exposes .cmd shims on Windows; resolve through PATHEXT before
        # passing the executable to subprocess (which runs without a shell).
        if os.name == "nt":
            executable = shutil.which(executable) or executable
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=[executable, "--stdio"], cwd=repository_root_path),
            "python",
        )
        self._initialize_timeout_seconds = 30
        self._shutdown_timeout_seconds = 10
        # Pyright pushes textDocument/publishDiagnostics asynchronously. Keep a
        # bounded queue so callers can read them without unbounded growth.
        self.diagnostics: asyncio.Queue = asyncio.Queue(maxsize=64)
        self.diagnostics_dropped = False
        # Applying an LSP WorkspaceEdit belongs to the embedding client. A
        # callback must be installed explicitly before starting the server.
        self._workspace_edit_handler: Callable[[dict], Awaitable[dict]] | None = None
        self._workspace_edit_timeout_seconds = 30.0

    def set_workspace_edit_handler(
        self, handler: Callable[[dict], Awaitable[dict]] | None,
        *, timeout_seconds: float = 30.0,
    ) -> None:
        """Opt in to processing server-requested workspace edits.

        The callback receives the original ApplyWorkspaceEditParams and must
        authorize and apply the proposed edit, returning an LSP response such
        as ``{"applied": True}``. No filesystem changes are made by this
        adapter. This does NOT restrict commands that write directly on the
        Pyright server side; callers must sandbox untrusted server processes.
        """
        if self.server_started:
            raise MultilspyException("Cannot change workspace edit handler while running")
        if handler is not None and not inspect.iscoroutinefunction(handler):
            raise TypeError("Workspace edit handler must be an async function or None")
        if (not isinstance(timeout_seconds, (int, float)) or
                not math.isfinite(timeout_seconds) or timeout_seconds <= 0):
            raise ValueError("Workspace edit timeout must be a positive finite number")
        self._workspace_edit_handler = handler
        self._workspace_edit_timeout_seconds = timeout_seconds

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

        # Advertise application support only when an embedding client has
        # explicitly supplied a handler that authorizes and applies edits.
        d["capabilities"]["workspace"]["applyEdit"] = self._workspace_edit_handler is not None
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
        if self.server_started:
            raise MultilspyException("Pyright language server is already started")

        async def workspace_configuration(params):
            # Pyright asks for the "python", "python.analysis" and "pyright"
            # sections. Answer with fixed, read-only settings; project settings
            # come from pyrightconfig.json / pyproject.toml in the workspace.
            if not isinstance(params, dict):
                return []
            items = params.get("items")
            if not isinstance(items, list):
                return []
            if len(items) > 64:
                # LSP requires one response per requested configuration item.
                return [None] * len(items)
            settings = {
                "python": {"analysis": {}},
                "python.analysis": {},
                "pyright": {
                    "disableLanguageServices": False,
                    "disableOrganizeImports": self._workspace_edit_handler is None,
                },
            }
            answers = []
            for item in items:
                section = item.get("section") if isinstance(item, dict) else None
                answers.append(settings.get(section) if isinstance(section, str) else None)
            return answers

        async def workspace_apply_edit(params):
            if self._workspace_edit_handler is None:
                return {"applied": False, "failureReason": "multilspy Pyright client is read-only"}
            try:
                response = await asyncio.wait_for(
                    self._workspace_edit_handler(params),
                    timeout=self._workspace_edit_timeout_seconds,
                )
                if not isinstance(response, dict) or type(response.get("applied")) is not bool:
                    raise ValueError("Invalid LSP workspace edit result")
                result = {"applied": response["applied"]}
                if not result["applied"]:
                    if "failureReason" in response:
                        reason = response["failureReason"]
                        if not isinstance(reason, str):
                            raise ValueError("Invalid workspace edit failureReason")
                        result["failureReason"] = reason[:256]
                    if "failedChange" in response:
                        number = response["failedChange"]
                        if type(number) is not int or number < 0:
                            raise ValueError("Invalid workspace edit failedChange")
                        result["failedChange"] = number
                return result
            except asyncio.TimeoutError:
                self.logger.log("LSP: workspace edit handler timed out", logging.WARNING)
                return {"applied": False, "failureReason": "Workspace edit handler timed out"}
            except Exception as exc:
                # Never report applied=true when a client edit failed, or
                # echo untrusted exception messages that contain local paths.
                self.logger.log(
                    f"LSP: workspace edit handler failed ({type(exc).__name__})", logging.WARNING
                )
                return {"applied": False, "failureReason": "Workspace edit handler failed"}

        async def publish_diagnostics(params):
            if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
                return
            if self.diagnostics.full():
                # Keep the newest diagnostic state rather than permanently
                # losing updates when the consumer falls behind.
                self.diagnostics_dropped = True
                self.diagnostics.get_nowait()
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

        # A LanguageServer instance may be started more than once. Old progress
        # and diagnostics must never be delivered to the next server session.
        self.completions_available.clear()
        self.diagnostics = asyncio.Queue(maxsize=64)
        self.diagnostics_dropped = False

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
                for required in (
                    "definitionProvider",
                    "referencesProvider",
                    "hoverProvider",
                    "completionProvider",
                    "documentSymbolProvider",
                    "workspaceSymbolProvider",
                ):
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
                        try:
                            await asyncio.wait_for(
                                self.server.shutdown(), timeout=self._shutdown_timeout_seconds
                            )
                        except asyncio.TimeoutError:
                            # A slow/blocked language server must not turn an
                            # otherwise successful operation into a failed
                            # context exit; stop() still terminates it.
                            self.logger.log("LSP: graceful Pyright shutdown timed out", logging.WARNING)
            finally:
                await self.server.stop()
