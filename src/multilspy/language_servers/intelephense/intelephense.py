"""
Provides PHP specific instantiation of the LanguageServer class using Intelephense.
"""

from contextlib import asynccontextmanager
import logging
import os
import pathlib
import shutil
import stat
import subprocess
from typing import AsyncIterator
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_settings import MultilspySettings
from multilspy.multilspy_utils import PlatformUtils, PlatformId
import json

# Conditionally import pwd module (Unix-only)
if not PlatformUtils.get_platform_id().value.startswith("win"):
    import pwd


class Intelephense(LanguageServer):
    """
    Provides PHP specific instantiation of the LanguageServer class using Intelephense.
    """

    def __init__(self, config, logger, repository_root_path):
        """
        Creates an Intelephense instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """

        executable_path = self.setup_runtime_dependencies(logger, config)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=executable_path, cwd=repository_root_path),
            "php",
        )

    def setup_runtime_dependencies(self, logger, config: MultilspyConfig) -> str:
        if config.server_binary:
            assert os.path.exists(config.server_binary), f"Server binary not found: {config.server_binary}"
            return [config.server_binary, "--stdio"]

        with open(
            os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r"
        ) as f:
            d = json.load(f)
            del d["_description"]

        runtime_dependencies = d.get("runtimeDependencies", [])
        php_ls_dir = config.server_install_dir or MultilspySettings.get_server_install_directory("intelephense")

        is_node_installed = shutil.which("node") is not None
        assert is_node_installed, "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert is_npm_installed, "npm is not installed or isn't in PATH. Please install npm and try again."

        intelephense_executable_path = os.path.join(
            php_ls_dir, "node_modules", ".bin", "intelephense"
        )

        if not os.path.exists(intelephense_executable_path):
            os.makedirs(php_ls_dir, exist_ok=True)
            for dependency in runtime_dependencies:
                if PlatformUtils.get_platform_id().value.startswith("win"):
                    subprocess.run(
                        dependency["command"],
                        shell=True,
                        check=True,
                        cwd=php_ls_dir,
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
                        cwd=php_ls_dir,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )

        assert os.path.exists(intelephense_executable_path), "intelephense executable not found. Please install intelephense and try again."
        os.chmod(
            intelephense_executable_path,
            os.stat(intelephense_executable_path).st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH,
        )

        return [intelephense_executable_path, "--stdio"]

    def _get_initialize_params(self, repository_absolute_path: str):
        """
        Returns the initialize params for the Intelephense PHP Language Server.
        """
        with open(
            os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r"
        ) as f:
            d = json.load(f)

        del d["_description"]

        d["processId"] = os.getpid()
        assert d["rootPath"] == "$rootPath"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "$rootUri"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["workspaceFolders"][0]["uri"] == "$uri"
        d["workspaceFolders"][0]["uri"] = pathlib.Path(
            repository_absolute_path
        ).as_uri()

        assert d["workspaceFolders"][0]["name"] == "$name"
        d["workspaceFolders"][0]["name"] = os.path.basename(repository_absolute_path)

        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["Intelephense"]:
        """
        Start the language server and yield when the server is ready.
        """

        async def execute_client_command_handler(params):
            return []

        async def do_nothing(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request(
            "workspace/executeClientCommand", execute_client_command_handler
        )
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)

        async with super().start_server():
            self.logger.log("Starting intelephense server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            init_response = await self.server.send.initialize(initialize_params)
            self.logger.log(
                f"Received initialize response from intelephense: {init_response}",
                logging.INFO,
            )

            self.server.notify.initialized({})
            self.completions_available.set()

            try:
                yield self
            finally:
                await self.server.shutdown()
                await self.server.stop()
