"""
Provides Swift specific instantiation of the LanguageServer class using SourceKit-LSP. Contains various configurations and settings specific to Swift.
"""

import asyncio
import json
import logging
import os
import pathlib
import stat
import subprocess
from contextlib import asynccontextmanager
from typing import AsyncIterator, Union

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_utils import FileUtils
from multilspy.multilspy_utils import PlatformUtils


class SourceKitLSP(LanguageServer):
    """
    Provides Swift specific instantiation of the LanguageServer class using SourceKit-LSP.
    Contains various configurations and settings specific to Swift.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a SourceKitLSP instance. This class is not meant to be instantiated directly. Use LanguageServer.create() instead.
        """
        sourcekit_lsp_path = self.setup_runtime_dependencies(logger, config)

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=sourcekit_lsp_path, cwd=repository_root_path),
            "swift",
        )

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> str:
        """
        Setup runtime dependencies for SourceKit-LSP.

        Strategy:
        - On macOS: Discover sourcekit-lsp from Xcode or swift.org toolchain install.
        - On Linux: Download the Swift toolchain from swift.org if not already cached.
        - On Windows: Discover sourcekit-lsp from a local Swift toolchain install.

        Returns the path to the sourcekit-lsp executable.
        """
        platform_id = PlatformUtils.get_platform_id()

        # First, try to discover a locally installed sourcekit-lsp
        local_path = self._discover_local_sourcekit_lsp(logger, platform_id)
        if local_path is not None:
            logger.log(f"Found local sourcekit-lsp at {local_path}", logging.INFO)
            return local_path

        # On macOS and Windows, we require a local install
        if platform_id.value.startswith("osx-"):
            raise RuntimeError(
                "sourcekit-lsp not found. Please install Swift via Xcode or from https://www.swift.org/install/macos/. "
                "Ensure sourcekit-lsp is available via 'xcrun --find sourcekit-lsp' or on PATH."
            )
        elif platform_id.value.startswith("win-"):
            raise RuntimeError(
                "sourcekit-lsp not found. Please install Swift from https://www.swift.org/install/windows/. "
                "Ensure sourcekit-lsp is available on PATH."
            )

        # On Linux, download the Swift toolchain
        logger.log("sourcekit-lsp not found locally, downloading Swift toolchain...", logging.INFO)
        return self._download_swift_toolchain(logger, platform_id)

    def _discover_local_sourcekit_lsp(self, logger: MultilspyLogger, platform_id) -> Union[str, None]:
        """
        Try to find a locally installed sourcekit-lsp binary.
        Returns the path if found, None otherwise.
        """
        # On macOS, try xcrun first (works with Xcode and command line tools)
        if platform_id.value.startswith("osx-"):
            try:
                result = subprocess.run(
                    ["xcrun", "--find", "sourcekit-lsp"],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    path = result.stdout.decode("utf-8").strip()
                    if os.path.exists(path):
                        return path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        # Try which/where on all platforms
        which_cmd = "where" if platform_id.value.startswith("win-") else "which"
        try:
            result = subprocess.run(
                [which_cmd, "sourcekit-lsp"],
                capture_output=True,
                timeout=10,
            )
            if result.returncode == 0:
                path = result.stdout.decode("utf-8").strip().split("\n")[0]
                if os.path.exists(path):
                    return path
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        return None

    def _download_swift_toolchain(self, logger: MultilspyLogger, platform_id) -> str:
        """
        Download the Swift toolchain for Linux and return the path to sourcekit-lsp.
        """
        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            d = json.load(f)
            del d["_description"]

        runtime_dependencies = d["runtimeDependencies"]
        runtime_dependencies = [
            dep for dep in runtime_dependencies if dep["platformId"] == platform_id.value
        ]

        if len(runtime_dependencies) == 0:
            raise RuntimeError(
                f"No Swift toolchain download available for platform {platform_id.value}. "
                "Please install Swift manually from https://www.swift.org/install/"
            )

        assert len(runtime_dependencies) == 1
        dependency = runtime_dependencies[0]

        static_dir = os.path.join(os.path.dirname(__file__), "static")
        os.makedirs(static_dir, exist_ok=True)

        toolchain_dir = os.path.join(static_dir, dependency["toolchainPath"])
        sourcekit_lsp_path = os.path.join(toolchain_dir, dependency["binaryPath"])

        if not os.path.exists(sourcekit_lsp_path):
            logger.log(f"Downloading Swift toolchain for {platform_id.value}...", logging.INFO)
            FileUtils.download_and_extract_archive(
                logger, dependency["url"], static_dir, dependency["archiveType"]
            )

        assert os.path.exists(sourcekit_lsp_path), f"sourcekit-lsp not found at {sourcekit_lsp_path}"

        if not platform_id.value.startswith("win-"):
            os.chmod(sourcekit_lsp_path, stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)

        logger.log(f"Swift toolchain ready at {toolchain_dir}", logging.INFO)
        return sourcekit_lsp_path

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for SourceKit-LSP.
        """
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r") as f:
            d = json.load(f)

        del d["_description"]

        assert d["processId"] == "os.getpid()"
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
    async def start_server(self) -> AsyncIterator["SourceKitLSP"]:
        """
        Starts the SourceKit-LSP Language Server, waits for the server to be ready and yields the LanguageServer instance.

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
        # Track $/progress tokens to detect when background indexing completes
        active_progress_tokens: set = set()
        indexing_complete = asyncio.Event()
        # Set immediately in case there is no background indexing (e.g. standalone files)
        no_indexing_started = True

        async def execute_client_command_handler(params):
            return []

        async def do_nothing(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        async def handle_progress(params):
            nonlocal no_indexing_started
            token = params.get("token", "")
            value = params.get("value", {})
            kind = value.get("kind", "")

            if kind == "begin":
                no_indexing_started = False
                active_progress_tokens.add(token)
                self.logger.log(
                    f"LSP: $/progress begin: {value.get('title', '')} ({token})",
                    logging.INFO,
                )
            elif kind == "end":
                active_progress_tokens.discard(token)
                self.logger.log(
                    f"LSP: $/progress end: {value.get('message', '')} ({token})",
                    logging.INFO,
                )
                if not active_progress_tokens and not indexing_complete.is_set():
                    indexing_complete.set()

        async def work_done_progress_create(params):
            self.logger.log(f"LSP: window/workDoneProgress/create token={params.get('token')}", logging.INFO)
            return None

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_request("window/workDoneProgress/create", work_done_progress_create)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", handle_progress)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        async with super().start_server():
            self.logger.log("Starting SourceKit-LSP server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)

            capabilities = init_response["capabilities"]
            assert "textDocumentSync" in capabilities, "Server must support textDocumentSync"
            # Note: Apple's SourceKit-LSP registers completion dynamically on open text buffers
            # rather than advertising static completionProvider in initialize response capabilities.
            assert "definitionProvider" in capabilities, "Server must support go to definition"
            assert "referencesProvider" in capabilities, "Server must support find references"
            assert "documentSymbolProvider" in capabilities, "Server must support document symbols"

            self.server.notify.initialized({})
            self.completions_available.set()

            # NOTE ON READINESS WAIT:
            # SourceKit-LSP performs background indexing (enabled by default since
            # Swift 6.1). We wait for indexing to complete via $/progress tokens
            # to ensure definition/references results are complete.
            #
            # If no $/progress begin is received within a short timeout, the
            # project may not need indexing (e.g. standalone files or already
            # indexed). In that case we proceed immediately.
            self.logger.log(
                "Waiting for SourceKit-LSP background indexing to complete...",
                logging.INFO,
            )
            try:
                await asyncio.wait_for(indexing_complete.wait(), timeout=10.0)
            except asyncio.TimeoutError:
                if no_indexing_started:
                    self.logger.log(
                        "No background indexing detected, proceeding immediately",
                        logging.INFO,
                    )
                else:
                    # Indexing started but hasn't finished in 10s, wait up to 60s
                    self.logger.log(
                        "Background indexing in progress, waiting for completion...",
                        logging.INFO,
                    )
                    try:
                        await asyncio.wait_for(indexing_complete.wait(), timeout=60.0)
                    except asyncio.TimeoutError:
                        self.logger.log(
                            "Background indexing wait timed out, proceeding with available index",
                            logging.WARNING,
                        )

            self.logger.log("SourceKit-LSP is ready", logging.INFO)

            yield self

            try:
                await self.server.shutdown()
            except Exception as e:
                self.logger.log(f"Error during SourceKit-LSP shutdown: {str(e)}", logging.WARNING)
            finally:
                await self.server.stop()
