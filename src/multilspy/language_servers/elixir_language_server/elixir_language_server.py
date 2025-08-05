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
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_utils import FileUtils, PlatformUtils

class ElixirLanguageServer(LanguageServer):
    """
    Provides Elixir-specific instantiation of the LanguageServer class.
    """

    def __init__(self, config, logger, repository_root_path):
        executable_path = self.setup_runtime_dependencies(logger)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=executable_path, cwd=repository_root_path),
            "elixir",
        )

    def setup_runtime_dependencies(self, logger: MultilspyLogger) -> str:
        # First try to find elixir-ls in PATH
        path = shutil.which("elixir-ls")
        if path:
            logger.log(f"Found elixir-ls in PATH: {path}", logging.INFO)
            return path

        # Try language_server.sh directly (if user has ElixirLS installed)
        language_server_path = shutil.which("language_server.sh")
        if language_server_path:
            logger.log(f"Found language_server.sh in PATH: {language_server_path}", logging.INFO)
            return language_server_path

        # Fall back to downloading and setting up ElixirLS
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
        elixir_ls_dir = os.path.join(os.path.dirname(__file__), "static", "elixir-ls")
        elixir_executable_path = os.path.join(elixir_ls_dir, dependency["binaryName"])

        if not os.path.exists(elixir_ls_dir):
            os.makedirs(elixir_ls_dir)
            logger.log(f"Downloading ElixirLS from {dependency['url']}", logging.INFO)
            FileUtils.download_and_extract_archive(
                logger, dependency["url"], elixir_ls_dir, dependency["archiveType"]
            )

        if not os.path.exists(elixir_executable_path):
            raise RuntimeError(f"ElixirLS executable not found at {elixir_executable_path}")

        # Make executable (important for Unix-like systems)
        if not dependency["binaryName"].endswith(".bat"):
            os.chmod(elixir_executable_path, stat.S_IEXEC | stat.S_IREAD | stat.S_IWRITE)

        logger.log(f"Using ElixirLS executable: {elixir_executable_path}", logging.INFO)
        return elixir_executable_path



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
        # Set up ElixirLS-specific message handlers
        async def execute_client_command_handler(params):
            self.logger.log(f"executeClientCommand: {params}", logging.DEBUG)
            return []

        async def do_nothing(params):
            self.logger.log(f"Received notification: {params}", logging.DEBUG)
            return

        async def check_experimental_status(params):
            self.logger.log(f"experimental/serverStatus: {params}", logging.DEBUG)
            pass

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        async def window_show_message(msg):
            self.logger.log(f"LSP: window/showMessage: {msg}", logging.INFO)

        # Register handlers for ElixirLS-specific notifications and requests
        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("window/showMessage", window_show_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        async with super().start_server():
            self.logger.log("Starting ElixirLS server process", logging.INFO)
            await self.server.start()

            initialize_params = self._get_initialize_params(self.repository_root_path)
            self.logger.log(f"Sending initialize request to ElixirLS: {json.dumps(initialize_params, indent=2)}", logging.DEBUG)

            try:
                init_response = await asyncio.wait_for(
                    self.server.send_request("initialize", initialize_params),
                    timeout=60,
                )
                self.logger.log(f"Received initialize response: {init_response}", logging.INFO)

                # Verify that ElixirLS supports the capabilities we need
                capabilities = init_response.get("capabilities", {})
                if not capabilities.get("hoverProvider"):
                    self.logger.log("Warning: ElixirLS does not support hover", logging.WARNING)
                if not capabilities.get("definitionProvider"):
                    self.logger.log("Warning: ElixirLS does not support go-to-definition", logging.WARNING)
                if not capabilities.get("completionProvider"):
                    self.logger.log("Warning: ElixirLS does not support completions", logging.WARNING)

            except asyncio.TimeoutError:
                self.logger.log("Timed out waiting for initialize response from ElixirLS", logging.ERROR)
                raise

            self.server.notify.initialized({})
            self.completions_available.set()

            yield self

            # Proper shutdown sequence
            self.logger.log("Shutting down ElixirLS server", logging.INFO)
            await self.server.shutdown()
            await self.server.stop()