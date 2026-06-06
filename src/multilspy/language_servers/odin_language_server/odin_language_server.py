import asyncio
import json
import logging
import os
import pathlib
import subprocess
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams

class Ols(LanguageServer):
    """
    Provides Odin-specific instantiation of the LanguageServer class using ols.
    """

    @staticmethod
    def _get_odin_version():
        """Get the installed Odin version or None if not found."""
        try:
            result = subprocess.run(['odin', 'version'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @staticmethod
    def _get_ols_version():
        """Get the installed ols version or None if not found."""
        try:
            result = subprocess.run(['ols', 'version'], capture_output=True, text=True)
            if result.returncode == 0:
                return result.stdout.strip()
        except FileNotFoundError:
            return None
        return None

    @classmethod
    def setup_runtime_dependency(cls):
        """
        Check if required Odin runtime dependencies are available.
        Raises RuntimeError with helpful message if dependencies are missing.
        """
        missing_deps = []
        
        # Check for Odin installation
        odin_version = cls._get_odin_version()
        if not odin_version:
            missing_deps.append(("Odin", "https://odin-lang.org/docs/install/"))
        
        # Check for ols
        ols_version = cls._get_ols_version()
        if not ols_version:
            missing_deps.append(("ols", "https://github.com/DanielGavin/ols#installation"))
        
        if missing_deps:
            error_msg = "Missing required dependencies:\n"
            for dep, install_url in missing_deps:
                error_msg += f"- {dep}: Please install from {install_url}\n"
            raise RuntimeError(error_msg)
        
        return True


    def __init__(self, config, logger, repository_root_path):
        if config.server_binary:
            assert os.path.exists(config.server_binary), f"Server binary not found: {config.server_binary}"
            cmd = [config.server_binary]
        else:
            # Check runtime dependencies before initializing
            self.setup_runtime_dependency()
            cmd = ["ols"]

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
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
            
            # Verify server capabilities
            assert "textDocumentSync" in init_response["capabilities"]
            assert "completionProvider" in init_response["capabilities"]
            assert "definitionProvider" in init_response["capabilities"]

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
