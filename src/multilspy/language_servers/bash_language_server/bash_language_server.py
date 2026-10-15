"""
Provides Bash (bash-language-server) specific instantiation of the LanguageServer class.
"""

import asyncio
import json
import logging
import os
import pathlib
import shutil
import stat
import subprocess
from contextlib import asynccontextmanager
from typing import AsyncIterator, List

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_utils import PlatformUtils
from multilspy.multilspy_settings import MultilspySettings

# Conditionally import pwd module (Unix-only)
if not PlatformUtils.get_platform_id().value.startswith("win"):
    import pwd


class BashLanguageServer(LanguageServer):
    """
    Provides Bash specific instantiation of the LanguageServer class using bash-language-server.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a BashLanguageServer instance. This class is not meant to be instantiated directly.
        Use LanguageServer.create() instead.
        """
        cmd = self.setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "shellscript",
        )
        self.server_ready = asyncio.Event()

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> List[str]:
        """
        Setup runtime dependencies for bash-language-server.
        """
        if config.server_binary:
            assert os.path.exists(config.server_binary), f"Server binary not found: {config.server_binary}"
            return [config.server_binary, "start"]

        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]

        runtime_dependencies = d.get("runtimeDependencies", [])
        bash_ls_dir = config.server_install_dir or MultilspySettings.get_server_install_directory("bash-language-server")

        if PlatformUtils.get_platform_id().value.startswith("win"):
            bash_executable_path = os.path.join(bash_ls_dir, "node_modules", ".bin", "bash-language-server.cmd")
        else:
            bash_executable_path = os.path.join(bash_ls_dir, "node_modules", ".bin", "bash-language-server")

        if not os.path.exists(bash_executable_path):
            os.makedirs(bash_ls_dir, exist_ok=True)
            for dependency in runtime_dependencies:
                if PlatformUtils.get_platform_id().value.startswith("win"):
                    subprocess.run(
                        dependency["command"],
                        shell=True,
                        check=True,
                        cwd=bash_ls_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                else:
                    user = pwd.getpwuid(os.getuid()).pw_name
                    subprocess.run(
                        dependency["command"],
                        shell=True,
                        check=True,
                        user=user,
                        cwd=bash_ls_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

        assert os.path.exists(bash_executable_path), "bash-language-server executable not found. Please install bash-language-server and try again."

        if not PlatformUtils.get_platform_id().value.startswith("win"):
            os.chmod(
                bash_executable_path,
                os.stat(bash_executable_path).st_mode
                | stat.S_IXUSR
                | stat.S_IXGRP
                | stat.S_IXOTH,
            )

        return [bash_executable_path, "start"]

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Bash Language Server.
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
    async def start_server(self) -> AsyncIterator["BashLanguageServer"]:
        """
        Starts the Bash Language Server, waits for the server to be ready and yields the LanguageServer instance.
        """

        async def register_capability_handler(params):
            return None

        async def execute_client_command_handler(params):
            return []

        async def workspace_configuration_handler(params):
            items = params.get("items", []) if isinstance(params, dict) else []
            return [{} for _ in items]

        async def work_done_progress_create_handler(params):
            return None

        async def do_nothing(params):
            return None

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)
            if isinstance(msg, dict) and "BackgroundAnalysis: Completed" in msg.get("message", ""):
                self.server_ready.set()

        async def window_show_message(msg):
            self.logger.log(f"LSP: window/showMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create_handler)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_show_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        async with super().start_server():
            self.logger.log("Starting Bash language server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)
            self.logger.log(
                f"Received initialize response from bash-language-server: {init_response.get('serverInfo', {})}",
                logging.INFO,
            )

            self.server.notify.initialized({})
            self.completions_available.set()

            try:
                await asyncio.wait_for(self.server_ready.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                self.server_ready.set()

            try:
                yield self
            finally:
                await self.server.shutdown()
                await self.server.stop()
