"""
Provides Elixir specific instantiation of the LanguageServer class using ElixirLS.
"""

import asyncio
from contextlib import asynccontextmanager
import logging
import os
import pathlib
import shutil
import stat
import json
from typing import AsyncIterator

from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_settings import MultilspySettings
from multilspy.multilspy_utils import FileUtils, PlatformUtils


class ElixirLanguageServer(LanguageServer):
    """
    Provides Elixir-specific instantiation of the LanguageServer class using ElixirLS.
    """

    def __init__(self, config, logger, repository_root_path):
        executable_path = self.setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=executable_path, cwd=repository_root_path),
            "elixir",
        )

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> str:
        import subprocess

        # Verify Elixir is installed
        if not shutil.which("elixir"):
            raise RuntimeError(
                "Elixir is not installed. ElixirLS requires Elixir and Erlang/OTP.\n"
                "Install from https://elixir-lang.org/install.html\n"
                "Then run: mix local.hex --force"
            )

        # Ensure hex is installed non-interactively (ElixirLS needs it to build on first launch)
        subprocess.run(["mix", "local.hex", "--force"], capture_output=True)

        if config.server_binary:
            assert os.path.exists(config.server_binary), f"Server binary not found: {config.server_binary}"
            return [config.server_binary]

        # Try to find elixir-ls or language_server.sh in PATH
        for name in ("elixir-ls", "language_server.sh"):
            path = shutil.which(name)
            if path:
                logger.log(f"Found {name} in PATH: {path}", logging.INFO)
                return [path]

        logger.log(
            "NOTE: ElixirLS builds itself from source on first launch. "
            "This may take several minutes while it downloads dependencies and compiles.",
            logging.WARNING,
        )

        # Fall back to downloading ElixirLS
        platform_id = PlatformUtils.get_platform_id()
        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]

        runtime_dependencies = [
            dep for dep in d["runtimeDependencies"] if dep["platformId"] == platform_id.value
        ]

        if not runtime_dependencies:
            raise RuntimeError(f"No runtime dependency found for platform {platform_id.value}")

        dependency = runtime_dependencies[0]
        elixir_ls_dir = config.server_install_dir or MultilspySettings.get_server_install_directory("elixir-ls")
        elixir_executable_path = os.path.join(elixir_ls_dir, dependency["binaryName"])

        if not os.path.exists(elixir_executable_path):
            os.makedirs(elixir_ls_dir, exist_ok=True)
            logger.log(f"Downloading ElixirLS from {dependency['url']}", logging.INFO)
            FileUtils.download_and_extract_archive(
                logger, dependency["url"], elixir_ls_dir, dependency["archiveType"]
            )

        assert os.path.exists(elixir_executable_path), f"ElixirLS executable not found at {elixir_executable_path}"

        if not dependency["binaryName"].endswith(".bat"):
            os.chmod(elixir_executable_path, stat.S_IEXEC | stat.S_IREAD | stat.S_IWRITE)

        return [elixir_executable_path]

    def _get_initialize_params(self, repository_absolute_path: str):
        with open(
            os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r"
        ) as f:
            d = json.load(f)

        del d["_description"]

        d["processId"] = os.getpid()
        d["rootPath"] = repository_absolute_path
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()
        d["workspaceFolders"][0]["uri"] = pathlib.Path(repository_absolute_path).as_uri()
        d["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["ElixirLanguageServer"]:
        async def execute_client_command_handler(params):
            return []

        async def do_nothing(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        async with super().start_server():
            self.logger.log(f"Starting ElixirLS server process with cmd: {self.server.process_launch_info.cmd}", logging.INFO)
            await self.server.start()

            # Check if the process started successfully
            if self.server.process.returncode is not None:
                self.logger.log(f"ElixirLS process exited immediately with code {self.server.process.returncode}", logging.ERROR)
                raise RuntimeError(f"ElixirLS failed to start (exit code {self.server.process.returncode})")

            self.logger.log(f"ElixirLS process started with PID {self.server.process.pid}", logging.INFO)
            initialize_params = self._get_initialize_params(self.repository_root_path)

            # ElixirLS builds itself from source on first launch (downloads deps,
            # compiles). This can take several minutes. 600s timeout accommodates this.
            init_response = await asyncio.wait_for(
                self.server.send.initialize(initialize_params),
                timeout=600,
            )
            self.logger.log(f"Received initialize response from ElixirLS: {init_response}", logging.INFO)

            self.server.notify.initialized({})
            self.completions_available.set()

            try:
                yield self
            finally:
                await self.server.shutdown()
                await self.server.stop()
