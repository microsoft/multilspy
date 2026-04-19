"""
Provides BSL-specific instantiation of the LanguageServer class.

BSL (Business Scripting Language) is the programming language of the
1C:Enterprise platform and OneScript. This adapter wraps the bsl-language-server
JAR from https://github.com/1c-syntax/bsl-language-server.

Prerequisites:
  - Java 17+ must be available in PATH.
  - The BSL Language Server JAR is downloaded on first use from GitHub releases.
"""

import asyncio
import json
import logging
import os
import pathlib
import shutil
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_utils import FileUtils


class BSLLanguageServer(LanguageServer):
    """
    Provides BSL-specific instantiation of the LanguageServer class.
    """

    def __init__(
        self,
        config: MultilspyConfig,
        logger: MultilspyLogger,
        repository_root_path: str,
    ):
        """
        Creates a BSL Language Server instance. Do not instantiate directly;
        use `LanguageServer.create` with `Language.BSL`.
        """
        jar_path = self._ensure_jar(logger)
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(
                cmd=["java", "-jar", str(jar_path), "--lsp"],
                cwd=repository_root_path,
            ),
            "bsl",
        )

    def _ensure_jar(self, logger: MultilspyLogger) -> str:
        """Verify Java and the BSL LS JAR are available; download JAR if missing."""
        if shutil.which("java") is None:
            raise RuntimeError(
                "Java 17+ is required to run BSL Language Server, "
                "but `java` was not found in PATH. "
                "Install a JDK 17+ from https://adoptium.net/ "
                "and ensure `java` is on PATH."
            )

        with open(
            os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"),
            "r",
            encoding="utf-8",
        ) as f:
            deps = json.load(f)
        dep = deps["runtimeDependency"]

        server_dir = os.path.join(os.path.dirname(__file__), "static", dep["version"])
        os.makedirs(server_dir, exist_ok=True)
        jar_path = os.path.join(server_dir, dep["binaryName"])

        if not os.path.exists(jar_path):
            logger.log(
                f"Downloading BSL Language Server {dep['version']} "
                f"from {dep['url']}",
                logging.INFO,
            )
            FileUtils.download_file(logger, dep["url"], jar_path)

        return jar_path

    def _get_initialize_params(self, repository_absolute_path: str) -> dict:
        with open(
            os.path.join(os.path.dirname(__file__), "initialize_params.json"),
            "r",
            encoding="utf-8",
        ) as f:
            d = json.load(f)

        del d["_description"]

        root = pathlib.Path(repository_absolute_path)
        d["processId"] = os.getpid()
        d["rootPath"] = repository_absolute_path
        d["rootUri"] = root.as_uri()
        d["workspaceFolders"][0]["uri"] = root.as_uri()
        d["workspaceFolders"][0]["name"] = root.name or "workspace"
        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["BSLLanguageServer"]:
        async def do_nothing(params):  # noqa: ARG001
            return

        async def log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", log_message)
        self.server.on_notification("window/showMessage", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("$/progress", do_nothing)

        async with super().start_server():
            self.logger.log(
                f"Starting BSL Language Server: {self.server.process_launch_info.cmd}",
                logging.INFO,
            )
            await self.server.start()

            if self.server.process.returncode is not None:
                raise RuntimeError(
                    f"BSL Language Server failed to start "
                    f"(exit code {self.server.process.returncode}). "
                    f"Check Java version (17+ required)."
                )

            initialize_params = self._get_initialize_params(self.repository_root_path)

            init_response = await asyncio.wait_for(
                self.server.send.initialize(initialize_params),
                timeout=120,
            )
            self.logger.log(
                f"BSL LS capabilities: "
                f"{list(init_response.get('capabilities', {}).keys())}",
                logging.INFO,
            )

            self.server.notify.initialized({})
            self.completions_available.set()

            try:
                yield self
            finally:
                try:
                    await self.server.shutdown()
                except Exception:
                    pass
                try:
                    await self.server.stop()
                except Exception:
                    pass
