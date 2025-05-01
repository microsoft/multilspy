from contextlib import asynccontextmanager
import logging
import os
import pathlib
import pwd
import shutil
import stat
import subprocess
from typing import AsyncIterator
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
import json
from multilspy.multilspy_utils import FileUtils, PlatformUtils


class Intelephense(LanguageServer):
    """
    Provides Php specific instantiation of the LanguageServer class.
    """

    def __init__(self, config, logger, repository_root_path):
        """
        Creates an Intelephense instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """

        executable_path = self.setup_runtime_dependencies(logger)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=executable_path, cwd=repository_root_path),
            "php",
        )

    def setup_runtime_dependencies(self, logger: "MultilspyLogger") -> str:
        with open(
            os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r"
        ) as f:
            d = json.load(f)
            del d["_description"]

        runtime_dependencies = d.get("runtimeDependencies", [])
        php_ls_dir = os.path.join(os.path.dirname(__file__), "static", "intelephense")

        is_node_installed = shutil.which("node") is not None
        assert (
            is_node_installed
        ), "node is not installed or isn't in PATH. Please install NodeJS and try again."
        is_npm_installed = shutil.which("npm") is not None
        assert (
            is_npm_installed
        ), "npm is not installed or isn't in PATH. Please install npm and try again."

        if not os.path.exists(php_ls_dir):
            os.makedirs(php_ls_dir, exist_ok=True)
            for dependency in runtime_dependencies:
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
        intelephense_executable_path = os.path.join(
            php_ls_dir, "node_modules", ".bin", "intelephense"
        )

        assert os.path.exists(intelephense_executable_path)
        os.chmod(
            intelephense_executable_path,
            os.stat(intelephense_executable_path).st_mode
            | stat.S_IXUSR
            | stat.S_IXGRP
            | stat.S_IXOTH,
        )

        return f"{intelephense_executable_path} --stdio"

    def _get_initialize_params(self, repository_absolute_path: str):
        """
        Returns the initialize params for the Php Language Server.
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

        async def check_experimental_status(params):
            pass

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
        self.server.on_notification(
            "experimental/serverStatus", check_experimental_status
        )

        async with super().start_server():
            self.logger.log("Starting intelephense server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)
            self.logger.log(
                "Sending initialize request to php-language-server",
                logging.DEBUG,
            )
            init_response = await self.server.send.initialize(initialize_params)
            self.logger.log(
                f"Received initialize response from intelephense: {init_response}",
                logging.INFO,
            )

            self.logger.log(
                "Sending initialized notification to intelephense",
                logging.INFO,
            )

            self.server.notify.initialized({})

            yield self

            await self.server.shutdown()
            await self.server.stop()
