import asyncio
import json
import logging
import os
import pathlib
import stat
import subprocess
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_utils import PlatformUtils, FileUtils, PlatformId
from multilspy.multilspy_settings import MultilspySettings

class Ols(LanguageServer):
    """
    Provides Odin-specific instantiation of the LanguageServer class using ols.
    """

    odin_root_path : str

    @staticmethod
    def _get_dependency_version(dependency: str):
        """Get the installed ols or odin version or None if not found."""
        try:
            result = subprocess.run([dependency, 'version'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None
    
    
    @staticmethod
    def _setup_runtime_dependency(dependency: str, platform_id: PlatformId, logger: MultilspyLogger, config: MultilspyConfig):
        """Setup odin or ols runtime dependency for Odin Language Server."""

        assert dependency in ["odin", "ols"]

        dependency_version = Ols._get_dependency_version(dependency)
        if dependency_version:
            return dependency
        else:
            with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
                d = json.load(f)
                del d["_description"]

            dependencies = d[dependency]
            dependencies = [
                dependency for dependency in dependencies if dependency["platformId"] == platform_id.value
            ]
            assert len(dependencies) == 1

            # Select dependency matching the current platform
            dependency = next((dep for dep in dependencies if dep["platformId"] == platform_id.value), None)
            if dependency is None:
                raise RuntimeError(f"No runtime dependency found for platform {platform_id.value}")

            ls_dir = config.server_install_dir or MultilspySettings.get_server_install_directory("ols")
            executable_path = pathlib.PurePath(ls_dir, dependency["binaryName"])
            if not os.path.exists(executable_path):
                os.makedirs(ls_dir, exist_ok=True)
                FileUtils.download_and_extract_archive(
                    logger, dependency["url"], ls_dir, dependency["archiveType"]
                )
                if not os.path.exists(executable_path):
                    raise FileNotFoundError(f"ols executable was not found at {executable_path} after extraction")
            os.chmod(executable_path, stat.S_IEXEC)

            return str(executable_path)


    @classmethod
    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> str:
        """
        Setup runtime dependencies for Odin Language Server.
        """

        platform_id = PlatformUtils.get_platform_id()
        assert platform_id.value in [
            "linux-x64",
            "win-x64",
            "osx-x64",
            "osx-arm64",
        ], "Unsupported platform: " + platform_id.value

        self.odin_root_path = os.path.dirname(Ols._setup_runtime_dependency("odin", platform_id, logger, config))

        if config.server_binary:
            assert os.path.exists(config.server_binary), f"Server binary not found: {config.server_binary}"
            return config.server_binary

        ols_executable_path = Ols._setup_runtime_dependency("ols", platform_id, logger, config)

        return ols_executable_path


    def __init__(self, config, logger, repository_root_path):
        if config.server_binary:
            assert os.path.exists(config.server_binary), f"Server binary not found: {config.server_binary}"
            cmd = [config.server_binary]
        else:
            # Check runtime dependencies before initializing
            cmd = [self.setup_runtime_dependencies(logger, config)]

        proc_env = {"ODIN_ROOT": self.odin_root_path}

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, env = proc_env, cwd=repository_root_path),
            "odin",
        )
        self.server_ready = asyncio.Event()
        self.request_id = 0


    def _get_initialize_params(self) -> InitializeParams:
        """
        Returns the initialize params for the Odin Language Server.
        """
        with open(os.path.join(os.path.dirname(__file__), "initialize_params.json"), "r") as f:
            d = json.load(f)

        del d["_description"]
        return d


    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["Ols"]:
        """Start ols server process"""
        async def register_capability_handler(params):
            return

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        async def do_nothing(params):
            return

        self.server.on_request("client/registerCapability", register_capability_handler)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)

        async with super().start_server():
            self.logger.log("Starting ols server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params()

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)
            
            capabilities = init_response["capabilities"]
            # Verify server capabilities
            assert "completionProvider"     in capabilities
            assert "textDocumentSync"       in capabilities and capabilities["textDocumentSync"]["openClose"] is True
            assert "definitionProvider"     in capabilities and capabilities["definitionProvider"] is True
            assert "hoverProvider"          in capabilities and capabilities["hoverProvider"] is True
            assert "documentSymbolProvider" in capabilities and capabilities["documentSymbolProvider"] is True

            self.server.notify.initialized({})
            self.completions_available.set()

            # ols server is typically ready immediately after initialization
            self.server_ready.set()
            await self.server_ready.wait()
            try:
                yield self
            finally:
                await self.server.shutdown()
                await self.server.stop()
