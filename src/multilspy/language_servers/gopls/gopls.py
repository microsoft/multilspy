"""
Provides Go specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Go.
"""

import asyncio
import json
import logging
import os
import pwd
import shutil
import stat
import pathlib
from contextlib import asynccontextmanager
import subprocess
from typing import AsyncIterator

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_utils import PlatformId
from multilspy.multilspy_utils import PlatformUtils


class Gopls(LanguageServer):
    """
    Provides Go specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Go.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a gopls instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        gopls_executable_path = self.setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=gopls_executable_path, cwd=repository_root_path),
            "go",
        )
        self.server_ready = asyncio.Event()

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> str:
        """
        Setup runtime dependencies for gopls.
        """
        platform_id = PlatformUtils.get_platform_id()

        valid_platforms = [
            PlatformId.LINUX_x64, 
            PlatformId.LINUX_arm64,
            PlatformId.OSX, 
            PlatformId.OSX_x64,
            PlatformId.OSX_arm64,
            PlatformId.WIN_x64, 
            PlatformId.WIN_arm64, 
        ] 
        assert platform_id in valid_platforms, f"Platform {platform_id} is not supported for multilspy gopls at the moment"

        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]

        runtime_dependencies = d["runtimeDependencies"]
        runtime_dependencies = d.get("runtimeDependencies", [])
        assert len(runtime_dependencies) == 1
        dependency = runtime_dependencies[0]

        # Require Go sdk to be installed 
        assert shutil.which('go') is not None, "go is not installed or isn't in PATH. Please install go and try again."
        
        # Install gopls
        gopls_dir = os.path.join(os.path.dirname(__file__), "static", "go", "bin")
        gopls_path = os.path.join(gopls_dir, dependency["binaryName"])
        if not os.path.exists(gopls_path):
            os.makedirs(gopls_dir, exist_ok=True)
            user = pwd.getpwuid(os.getuid()).pw_name
            new_env = os.environ.copy()
            new_env["GOBIN"] = gopls_dir
            subprocess.run(
                dependency["command"], 
                shell=True, 
                check=True, 
                user=user, 
                cwd=gopls_dir,
                env=new_env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        gopls_path = os.path.join(gopls_dir, dependency["binaryName"])

        return gopls_path

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Go Language Server.
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
        """
        Starts gopls, waits for the server to be ready and yields the LanguageServer instance.

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

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("language/status", lang_status_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_request("window/workDoneProgress/create", do_nothing)
        self.server.on_request("workspace/configuration", do_nothing)

        async with super().start_server():
            self.logger.log("Starting gopls process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)
            assert init_response["capabilities"]["textDocumentSync"]["change"] == 2
            assert "completionProvider" in init_response["capabilities"]
            assert init_response["capabilities"]["completionProvider"] == {
                "triggerCharacters": ['.'],
            }
            self.server.notify.initialized({})
            self.completions_available.set()

            self.server_ready.set()
            await self.server_ready.wait()

            yield self

            await self.server.shutdown()
            await self.server.stop()
