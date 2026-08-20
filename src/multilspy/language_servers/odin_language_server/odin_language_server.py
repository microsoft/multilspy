"""
Provides Odin-specific instantiation of the LanguageServer class using ols.
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
from typing import AsyncIterator, Dict, List, Optional, Tuple

from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from multilspy.multilspy_settings import MultilspySettings
from multilspy.multilspy_utils import FileUtils, PlatformId, PlatformUtils

_SUPPORTED_PLATFORMS = {
    "linux-x64",
    "linux-arm64",
    "win-x64",
    "osx-x64",
    "osx-arm64",
}

_EXECUTABLE_MODE = stat.S_IEXEC | stat.S_IREAD | stat.S_IWRITE


class Ols(LanguageServer):
    """
    Provides Odin-specific instantiation of the LanguageServer class using ols.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        ols_path, odin_path, odin_root = self.setup_runtime_dependencies(logger, config)
        self.odin_executable_path = odin_path
        self.odin_root_path = odin_root

        odin_dir = os.path.dirname(os.path.abspath(odin_path))
        proc_env = {
            "ODIN_ROOT": odin_root,
            "PATH": odin_dir + os.pathsep + os.environ.get("PATH", ""),
        }

        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=[ols_path], env=proc_env, cwd=repository_root_path),
            "odin",
        )
        self.server_ready = asyncio.Event()

    def setup_runtime_dependencies(self, logger: MultilspyLogger, config: MultilspyConfig) -> Tuple[str, str, str]:
        """
        Resolve ols and the Odin compiler.

        Always sets up Odin (needed for collections / ODIN_ROOT), including when
        config.server_binary points at a custom ols executable.

        :return: (ols_executable, odin_executable, odin_root)
        """
        platform_id = PlatformUtils.get_platform_id()
        if platform_id.value not in _SUPPORTED_PLATFORMS:
            raise RuntimeError("Unsupported platform: " + platform_id.value)

        runtime_dependencies = self._load_runtime_dependencies()
        odin_path, odin_root = self._setup_odin(logger, config, platform_id, runtime_dependencies)

        if config.server_binary:
            if not os.path.exists(config.server_binary):
                raise FileNotFoundError(f"Server binary not found: {config.server_binary}")
            ols_path = config.server_binary
        else:
            ols_path = self._setup_ols(logger, config, platform_id, runtime_dependencies)

        return ols_path, odin_path, odin_root

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for ols, with workspace root and Odin paths filled in.
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

        init_opts = d.setdefault("initializationOptions", {})
        init_opts["odin_command"] = self.odin_executable_path
        init_opts["odin_root_override"] = self.odin_root_path

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
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)

            capabilities = init_response["capabilities"]
            assert "completionProvider" in capabilities
            assert "definitionProvider" in capabilities
            assert "hoverProvider" in capabilities
            assert "documentSymbolProvider" in capabilities
            text_sync = capabilities.get("textDocumentSync")
            if isinstance(text_sync, dict):
                assert text_sync.get("openClose") is True

            self.server.notify.initialized({})
            self.completions_available.set()
            self.server_ready.set()
            await self.server_ready.wait()
            try:
                yield self
            finally:
                await self.server.shutdown()
                await self.server.stop()

    @staticmethod
    def _load_runtime_dependencies() -> Dict:
        with open(os.path.join(os.path.dirname(__file__), "runtime_dependencies.json"), "r") as f:
            data = json.load(f)
        data.pop("_description", None)
        return data

    @staticmethod
    def _select_dependency(dependencies: List[Dict], platform_id: PlatformId, kind: str) -> Dict:
        matches = [dep for dep in dependencies if dep["platformId"] == platform_id.value]
        if not matches:
            raise RuntimeError(f"No {kind} runtime dependency found for platform {platform_id.value}")
        return matches[0]

    def _setup_odin(
        self,
        logger: MultilspyLogger,
        config: MultilspyConfig,
        platform_id: PlatformId,
        runtime_dependencies: Dict,
    ) -> Tuple[str, str]:
        existing = shutil.which("odin")
        if existing:
            odin_root = self._odin_root_from_binary(existing)
            if odin_root:
                logger.log(f"Using Odin from PATH: {existing} (ODIN_ROOT={odin_root})", logging.INFO)
                return existing, odin_root

        dependency = self._select_dependency(runtime_dependencies["odin"], platform_id, "odin")
        install_dir = self._install_dir(config, "odin")
        odin_path = self._ensure_downloaded_executable(
            logger, dependency, install_dir, kind="odin", require_sibling_dir="core"
        )
        odin_root = self._odin_root_from_binary(odin_path)
        if not odin_root:
            raise RuntimeError(f"Could not determine ODIN_ROOT for downloaded Odin at {odin_path}")
        return odin_path, odin_root

    def _setup_ols(
        self,
        logger: MultilspyLogger,
        config: MultilspyConfig,
        platform_id: PlatformId,
        runtime_dependencies: Dict,
    ) -> str:
        existing = shutil.which("ols")
        if existing:
            logger.log(f"Using ols from PATH: {existing}", logging.INFO)
            return existing

        dependency = self._select_dependency(runtime_dependencies["ols"], platform_id, "ols")
        install_dir = self._install_dir(config, "ols")
        return self._ensure_downloaded_executable(logger, dependency, install_dir, kind="ols")

    @staticmethod
    def _install_dir(config: MultilspyConfig, name: str) -> str:
        if config.server_install_dir:
            path = os.path.join(config.server_install_dir, name)
            os.makedirs(path, exist_ok=True)
            return path
        return MultilspySettings.get_server_install_directory(name)

    def _ensure_downloaded_executable(
        self,
        logger: MultilspyLogger,
        dependency: Dict,
        install_dir: str,
        kind: str,
        require_sibling_dir: Optional[str] = None,
    ) -> str:
        binary_name = dependency["binaryName"]
        executable_path = self._find_executable(install_dir, binary_name, require_sibling_dir)
        if executable_path:
            self._ensure_executable(executable_path)
            return executable_path

        os.makedirs(install_dir, exist_ok=True)
        logger.log(f"Downloading {kind} from {dependency['url']}", logging.INFO)
        FileUtils.download_and_extract_archive(
            logger, dependency["url"], install_dir, dependency["archiveType"]
        )
        self._unpack_nested_archives(install_dir)

        executable_path = self._find_executable(install_dir, binary_name, require_sibling_dir)
        if not executable_path:
            raise FileNotFoundError(
                f"{kind} executable {binary_name!r} was not found under {install_dir} after extraction"
            )
        self._ensure_executable(executable_path)
        return executable_path

    @staticmethod
    def _unpack_nested_archives(directory: str) -> None:
        """Odin Windows GitHub zips have historically nested another dist.zip."""
        for name in os.listdir(directory):
            path = os.path.join(directory, name)
            if not os.path.isfile(path):
                continue
            lower = name.lower()
            try:
                if lower.endswith(".zip"):
                    shutil.unpack_archive(path, directory, "zip")
                elif lower.endswith(".tar.gz") or lower.endswith(".tgz"):
                    shutil.unpack_archive(path, directory, "gztar")
            except shutil.ReadError:
                continue

    @staticmethod
    def _find_executable(
        root_dir: str, binary_name: str, require_sibling_dir: Optional[str] = None
    ) -> Optional[str]:
        if not os.path.isdir(root_dir):
            return None

        wanted = os.path.basename(binary_name)
        direct = os.path.join(root_dir, binary_name)
        candidates: List[str] = []
        if os.path.isfile(direct):
            candidates.append(direct)

        for dirpath, _dirnames, filenames in os.walk(root_dir):
            if wanted in filenames:
                candidates.append(os.path.join(dirpath, wanted))

        # Preserve order while dropping duplicates from the direct + walk overlap
        seen = set()
        unique: List[str] = []
        for path in candidates:
            if path not in seen:
                seen.add(path)
                unique.append(path)

        if require_sibling_dir:
            for path in unique:
                if os.path.isdir(os.path.join(os.path.dirname(path), require_sibling_dir)):
                    return path
            return None

        return unique[0] if unique else None

    @staticmethod
    def _ensure_executable(path: str) -> None:
        if os.name == "nt":
            return
        mode = os.stat(path).st_mode
        os.chmod(path, mode | _EXECUTABLE_MODE)

    @staticmethod
    def _odin_root_from_binary(odin_bin: str) -> Optional[str]:
        try:
            result = subprocess.run(
                [odin_bin, "root"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                output = (result.stdout or result.stderr).strip()
                if output:
                    root = output.splitlines()[0].strip()
                    if root and os.path.isdir(os.path.join(root, "core")):
                        return os.path.abspath(root)
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            pass

        parent = os.path.dirname(os.path.abspath(odin_bin))
        if os.path.isdir(os.path.join(parent, "core")):
            return parent
        return None
