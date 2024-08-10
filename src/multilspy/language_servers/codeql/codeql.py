"""
Provides CodeQL specific instantiation of the LanguageServer class. Contains various configurations and settings specific to CodeQL.
"""

import asyncio
import json
import logging
import os
import time
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig


class CodeQL(LanguageServer):
    """
    Provides CodeQL specific instantiation of the LanguageServer class. Contains various configurations and settings specific to CodeQL.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a CodeQL instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        codeql_executable_path = "codeql execute language-server --check-errors ON_CHANGE -v --log-to-stderr" # FIXME
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=codeql_executable_path, cwd=repository_root_path),
            "ql",
        )
        self.server_ready = asyncio.Event()

    def get_syntax_errors(self, relative_file_path: str, timeout: int = 2):
        """
        Request syntax errors from the CodeQL Language Server for the given URI.
        """
        absolute_file_path = str(pathlib.PurePath(self.repository_root_path, relative_file_path))
        uri = pathlib.Path(absolute_file_path).as_uri()

        # Define and register a custom handler for the syntax error notification.
        syntax_errors = []
        async def syntax_error_handler(params):
            syntax_errors
            if params["uri"] == uri:
                syntax_errors.append(params)

        self.server.on_notification("textDocument/publishDiagnostics", syntax_error_handler)

        # Trigger the syntax error check by opening the file and performing a dummy operation.
        with self.open_file(relative_file_path):
            self.insert_text_at_position(relative_file_path, line=0, column=0, text_to_be_inserted="")
            # Wait for the syntax error notification handler to be called.
            # NOTE: we may want to `break` after seeing the first syntax_error. However, there
            # may be multiple. Not sure how to handle this.
            time_start = time.time()
            while time.time() - time_start < timeout:
                time.sleep(0.1)

        # Unregister the custom handler.
        self.server.on_notification("textDocument/publishDiagnostics", lambda _: None)

        return syntax_errors

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> str:
        raise NotImplementedError

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the CodeQL Language Server.
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
    async def start_server(self) -> AsyncIterator["CodeQL"]:
        """
        Starts the CodeQL Language Server, waits for the server to be ready and yields the LanguageServer instance.

        Usage:
        ```
        async with lsp.start_server():
            # LanguageServer has been initialized and ready to serve requests
            await lsp.request_definition(...)
            await lsp.request_references(...)
            # Shutdown the LanguageServer on exit from scope
        # LanguageServer has been shutdown
        """

        async def register_capability_handler(params):
            assert "registrations" in params
            for registration in params["registrations"]:
                if registration["method"] == "workspace/executeCommand":
                    self.initialize_searcher_command_available.set()
                    self.resolve_main_method_available.set()
            return

        async def lang_status_handler(params):
            # TODO: Should we wait for
            # server -> client: {'jsonrpc': '2.0', 'method': 'language/status', 'params': {'type': 'ProjectStatus', 'message': 'OK'}}
            # Before proceeding?
            if params["type"] == "ServiceReady" and params["message"] == "ServiceReady":
                self.service_ready_event.set()

        async def execute_client_command_handler(params):
            return []

        async def do_nothing(params):
            return

        async def check_experimental_status(params):
            print(params, "checking")
            if params["quiescent"] == True:
                self.server_ready.set()

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        async with super().start_server():
            self.logger.log("Starting CodeQL server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )

            init_response = await self.server.send.initialize(initialize_params)
            assert init_response["capabilities"]["textDocumentSync"] == 1
            assert "completionProvider" in init_response["capabilities"]
            self.server.notify.initialized({})
            self.completions_available.set()

            yield self

            await self.server.shutdown()
            await self.server.stop()
