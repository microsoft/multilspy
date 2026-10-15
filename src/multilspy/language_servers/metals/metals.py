"""
Provides Scala specific instantiation of the LanguageServer class using Metals.
Contains various configurations and settings specific to Scala.
Metals is the Scala language server from https://scalameta.org/metals/
"""

import asyncio
import dataclasses
import json
import logging
import os
import stat
import pathlib
import subprocess
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_utils import FileUtils
from multilspy.multilspy_utils import PlatformUtils


@dataclasses.dataclass
class MetalsRuntimeDependencyPaths:
    """
    Stores the paths to the runtime dependencies of Metals
    """
    java_path: str
    java_home_path: str
    metals_executable_path: str


class Metals(LanguageServer):
    """
    Provides Scala specific instantiation of the LanguageServer class using Metals.
    Contains various configurations and settings specific to Scala.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a Metals instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        runtime_dependency_paths = self.setup_runtime_dependencies(logger, config)
        self.runtime_dependency_paths = runtime_dependency_paths

        # Create command to execute the Metals launcher
        cmd = self.runtime_dependency_paths.metals_executable_path

        # Set environment variables including JAVA_HOME
        proc_env = {"JAVA_HOME": self.runtime_dependency_paths.java_home_path}

        # Track active $/progress tokens to know when Metals is quiescent
        self._active_progress_tokens: set = set()
        self._indexing_complete = asyncio.Event()
        self._no_indexing_started = True

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, env=proc_env, cwd=repository_root_path),
            "scala",
        )

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> MetalsRuntimeDependencyPaths:
        """
        Setup runtime dependencies for Metals.
        Downloads Java runtime and bootstraps Metals via Coursier.
        """
        platform_id = PlatformUtils.get_platform_id()

        # Verify platform support
        assert platform_id.value.startswith("win-") or platform_id.value.startswith("linux-") or platform_id.value.startswith("osx-"), \
            "Only Windows, Linux and macOS platforms are supported for Scala in multilspy at the moment"

        # Load dependency information
        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]

        metals_config = d["metals"]
        java_dependency = d["java"][platform_id.value]

        # Setup paths for dependencies
        static_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "static"))
        os.makedirs(static_dir, exist_ok=True)

        # Setup Java paths
        java_dir = os.path.join(static_dir, "java")
        os.makedirs(java_dir, exist_ok=True)

        java_home_path = os.path.abspath(os.path.join(java_dir, java_dependency["java_home_path"]))
        java_path = os.path.abspath(os.path.join(java_dir, java_dependency["java_path"]))

        # Download and extract Java if not exists
        if not os.path.exists(java_path):
            logger.log(f"Downloading Java for {platform_id.value}...", logging.INFO)
            FileUtils.download_and_extract_archive(
                logger, java_dependency["url"], java_dir, java_dependency["archiveType"]
            )
            # Make Java executable
            if not platform_id.value.startswith("win-"):
                os.chmod(java_path, 0o755)

        assert os.path.exists(java_path), f"Java executable not found at {java_path}"

        # Setup Metals via Coursier bootstrap
        metals_dir = os.path.join(static_dir, "metals")
        os.makedirs(metals_dir, exist_ok=True)

        metals_version = metals_config["version"]
        metals_artifact = metals_config["mavenArtifact"]

        if platform_id.value.startswith("win-"):
            metals_executable_path = os.path.abspath(os.path.join(metals_dir, "metals.bat"))
        else:
            metals_executable_path = os.path.abspath(os.path.join(metals_dir, "metals"))

        if not os.path.exists(metals_executable_path):
            logger.log(f"Bootstrapping Metals {metals_version} via Coursier...", logging.INFO)
            self._bootstrap_metals(logger, java_path, metals_artifact, metals_executable_path, platform_id)

        assert os.path.exists(metals_executable_path), f"Metals executable not found at {metals_executable_path}"

        return MetalsRuntimeDependencyPaths(
            java_path=java_path,
            java_home_path=java_home_path,
            metals_executable_path=metals_executable_path,
        )

    def _bootstrap_metals(
        self,
        logger: MultilspyLogger,
        java_path: str,
        metals_artifact: str,
        metals_executable_path: str,
        platform_id,
    ) -> None:
        """
        Bootstrap Metals using Coursier.
        Downloads Coursier if necessary, then uses it to create a Metals launcher.
        """
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        coursier_dir = os.path.join(static_dir, "coursier")
        os.makedirs(coursier_dir, exist_ok=True)

        if platform_id.value.startswith("win-"):
            coursier_path = os.path.join(coursier_dir, "cs.exe")
            coursier_url = "https://github.com/coursier/launchers/raw/master/cs-x86_64-pc-win32.zip"
            coursier_archive_type = "zip"
        elif platform_id.value.startswith("osx-"):
            if platform_id.value == "osx-arm64":
                coursier_url = "https://github.com/coursier/launchers/raw/master/cs-aarch64-apple-darwin.gz"
            else:
                coursier_url = "https://github.com/coursier/launchers/raw/master/cs-x86_64-apple-darwin.gz"
            coursier_path = os.path.join(coursier_dir, "cs")
            coursier_archive_type = "gz"
        else:
            if platform_id.value == "linux-arm64":
                coursier_url = "https://github.com/coursier/launchers/raw/master/cs-aarch64-pc-linux.gz"
            else:
                coursier_url = "https://github.com/coursier/launchers/raw/master/cs-x86_64-pc-linux.gz"
            coursier_path = os.path.join(coursier_dir, "cs")
            coursier_archive_type = "gz"

        # Download Coursier if not present
        if not os.path.exists(coursier_path):
            logger.log("Downloading Coursier...", logging.INFO)
            if coursier_archive_type == "gz":
                FileUtils.download_and_extract_archive(
                    logger, coursier_url, coursier_path, coursier_archive_type
                )
            else:
                FileUtils.download_and_extract_archive(
                    logger, coursier_url, coursier_dir, coursier_archive_type
                )

            if not platform_id.value.startswith("win-"):
                os.chmod(coursier_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        assert os.path.exists(coursier_path), f"Coursier not found at {coursier_path}"

        # Use Coursier to bootstrap Metals
        logger.log(f"Running Coursier bootstrap for {metals_artifact}...", logging.INFO)
        bootstrap_cmd = [
            coursier_path,
            "bootstrap",
            "--java-opt", "-XX:+UseG1GC",
            "--java-opt", "-XX:+UseStringDeduplication",
            "--java-opt", "-Xss4m",
            "--java-opt", "-Xms100m",
            metals_artifact,
            "-o", metals_executable_path,
            "-f",
        ]

        env = os.environ.copy()
        env["JAVA_HOME"] = os.path.dirname(os.path.dirname(java_path))
        env["PATH"] = os.path.dirname(java_path) + os.pathsep + env.get("PATH", "")

        result = subprocess.run(
            bootstrap_cmd,
            env=env,
            capture_output=True,
            timeout=300,
        )

        if result.returncode != 0:
            logger.log(f"Coursier bootstrap failed: {result.stderr.decode('utf-8', errors='replace')}", logging.ERROR)
            raise RuntimeError(
                f"Failed to bootstrap Metals: {result.stderr.decode('utf-8', errors='replace')}"
            )

        if not platform_id.value.startswith("win-"):
            os.chmod(metals_executable_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        logger.log("Metals bootstrap complete.", logging.INFO)

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Metals Language Server.
        """
        with open(str(pathlib.PurePath(os.path.dirname(__file__), "initialize_params.json")), "r") as f:
            d: InitializeParams = json.load(f)

        del d["_description"]

        if not os.path.isabs(repository_absolute_path):
            repository_absolute_path = os.path.abspath(repository_absolute_path)

        assert d["processId"] == "os.getpid()"
        d["processId"] = os.getpid()

        assert d["rootPath"] == "repository_absolute_path"
        d["rootPath"] = repository_absolute_path

        assert d["rootUri"] == "pathlib.Path(repository_absolute_path).as_uri()"
        d["rootUri"] = pathlib.Path(repository_absolute_path).as_uri()

        assert d["initializationOptions"]["workspaceFolders"] == "[pathlib.Path(repository_absolute_path).as_uri()]"
        d["initializationOptions"]["workspaceFolders"] = [pathlib.Path(repository_absolute_path).as_uri()]

        assert (
                d["workspaceFolders"]
                == '[\n            {\n                "uri": pathlib.Path(repository_absolute_path).as_uri(),\n                "name": os.path.basename(repository_absolute_path),\n            }\n        ]'
        )
        d["workspaceFolders"] = [
            {
                "uri": pathlib.Path(repository_absolute_path).as_uri(),
                "name": os.path.basename(repository_absolute_path),
            }
        ]

        return d

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["Metals"]:
        """
        Starts the Metals Language Server, waits for the server to be ready and yields the LanguageServer instance.

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
        async def execute_client_command_handler(params):
            return []

        async def do_nothing(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        async def work_done_progress_create(params):
            self.logger.log(f"LSP: window/workDoneProgress/create token={params.get('token')}", logging.INFO)
            return None

        async def handle_progress(params):
            """
            Track $/progress tokens to detect when Metals finishes build import,
            compilation, and indexing. Metals sends begin/report/end for each task.
            When all progress tokens have ended, the server is quiescent.
            """
            token = params.get("token", "")
            value = params.get("value", {})
            kind = value.get("kind", "")

            if kind == "begin":
                self._no_indexing_started = False
                self._active_progress_tokens.add(token)
                self.logger.log(
                    f"LSP: $/progress begin: {value.get('title', '')} ({token})",
                    logging.INFO,
                )
            elif kind == "end":
                self._active_progress_tokens.discard(token)
                self.logger.log(
                    f"LSP: $/progress end: {value.get('message', '')} ({token})",
                    logging.INFO,
                )
                if not self._active_progress_tokens and not self._indexing_complete.is_set():
                    self._indexing_complete.set()

        async def metals_execute_client_command(params):
            """
            Handle metals/executeClientCommand notifications.
            Auto-accept build import to ensure the project is fully indexed.
            """
            command = params.get("command", "")
            self.logger.log(f"LSP: metals/executeClientCommand: {command}", logging.INFO)
            if command == "metals-build-import":
                # Auto-trigger build import so the workspace is fully compiled
                self.logger.log("Auto-triggering build import for Metals", logging.INFO)
                await self.server.send.execute_command(
                    {"command": "build-import", "arguments": []}
                )

        async def workspace_configuration_handler(params):
            items = params.get("items", []) if isinstance(params, dict) else []
            self.logger.log(f"LSP: workspace/configuration items={items}", logging.INFO)
            result = []
            for item in items:
                section = item.get("section", "")
                if section == "metals" or not section:
                    result.append({
                        "autoImportBuilds": "off",
                        "fallbackScalaVersion": "2.13.14",
                    })
                else:
                    result.append({})
            return result

        async def window_show_message_request(params):
            self.logger.log(f"LSP: window/showMessageRequest: {params}", logging.INFO)
            return None

        async def semantic_tokens_refresh_handler(params):
            return None

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_request("window/showMessageRequest", window_show_message_request)
        self.server.on_request("workspace/semanticTokens/refresh", semantic_tokens_refresh_handler)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", handle_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("metals/status", do_nothing)
        self.server.on_notification("metals/executeClientCommand", metals_execute_client_command)
        self.server.on_request("workspace/configuration", workspace_configuration_handler)

        async with super().start_server():
            self.logger.log("Starting Metals server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)

            capabilities = init_response["capabilities"]
            assert "textDocumentSync" in capabilities, "Server must support textDocumentSync"
            assert "completionProvider" in capabilities, "Server must support code completion"
            assert "definitionProvider" in capabilities, "Server must support go to definition"
            assert "referencesProvider" in capabilities, "Server must support find references"
            assert "documentSymbolProvider" in capabilities, "Server must support document symbols"

            self.server.notify.initialized({})
            self.completions_available.set()

            # NOTE ON READINESS WAIT:
            # We wait here for Metals to finish build import, compilation, and
            # indexing before yielding. This mirrors how JDTLS waits for
            # ServiceReady and Rust Analyzer waits for quiescent=true.
            #
            # Why: Metals uses "cascade compilation" for textDocument/references.
            # If downstream targets haven't been compiled yet, references returns
            # immediately with incomplete results and compiles in the background.
            # By waiting here, we ensure results are complete on the first call.
            #
            # Tradeoff: This makes start_server() slower, especially for large
            # projects with many build targets. If you only need definition,
            # hover, or document symbols (which work without full compilation),
            # you could remove this wait and yield immediately after
            # initialized() — but references may then be incomplete until
            # Metals finishes background compilation.
            self.logger.log(
                "Waiting for Metals to complete build import and indexing...",
                logging.INFO,
            )
            try:
                await asyncio.wait_for(self._indexing_complete.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                if self._no_indexing_started:
                    self.logger.log(
                        "No background indexing detected from Metals, proceeding immediately",
                        logging.INFO,
                    )
                else:
                    self.logger.log(
                        "Background indexing in progress for Metals, waiting for completion...",
                        logging.INFO,
                    )
                    try:
                        await asyncio.wait_for(self._indexing_complete.wait(), timeout=60.0)
                    except asyncio.TimeoutError:
                        self.logger.log(
                            "Metals indexing wait timed out, proceeding with available index",
                            logging.WARNING,
                        )
            self.logger.log("Metals is ready", logging.INFO)

            yield self

            try:
                await asyncio.wait_for(self.server.shutdown(), timeout=5.0)
            except Exception as e:
                self.logger.log(f"Error during Metals server shutdown: {str(e)}", logging.WARNING)
            finally:
                try:
                    await asyncio.wait_for(self.server.stop(), timeout=5.0)
                except Exception:
                    pass
