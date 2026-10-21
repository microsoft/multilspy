"""Pyright LSP backend for multilspy's existing Python language API.

Pyright must already be installed. This backend doesn't download binaries,
edit project files, or require a VS Code extension process.
"""

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


class PyrightServer(LanguageServer):
    """Use pyright-langserver --stdio instead of the default Jedi backend."""

    def __init__(
        self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str
    ):
        root = str(Path(repository_root_path).resolve())
        super().__init__(
            config,
            logger,
            root,
            ProcessLaunchInfo(
                cmd=[config.server_binary or "pyright-langserver", "--stdio"],
                cwd=root,
            ),
            "python",
        )
        self.diagnostics: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)
        self.diagnostics_dropped = False

    async def next_diagnostics(self, timeout: float = 5.0) -> dict:
        """Read an asynchronous publishDiagnostics notification."""
        return await asyncio.wait_for(self.diagnostics.get(), timeout)

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["PyrightServer"]:
        async def configuration(params: Any) -> list:
            if not isinstance(params, dict):
                return []
            items = params.get("items")
            if not isinstance(items, list) or len(items) > 64:
                return []
            defaults = {
                "python": {"analysis": {}},
                "pyright": {
                    "disableLanguageServices": False,
                    "disableOrganizeImports": True,
                },
            }
            return [
                defaults.get(item.get("section"))
                if isinstance(item, dict) and isinstance(item.get("section"), str)
                else None
                for item in items
            ]

        async def refuse_edit(_params: Any) -> dict:
            return {
                "applied": False,
                "failureReason": "multilspy Pyright client is read-only",
            }

        async def diagnostics(params: Any) -> None:
            if not isinstance(params, dict) or not isinstance(params.get("uri"), str):
                return
            if self.diagnostics.full():
                self.diagnostics_dropped = True
                return
            self.diagnostics.put_nowait(params)

        async def ignore_notification(_params: Any) -> None:
            return None

        self.server.on_request("workspace/configuration", configuration)
        self.server.on_request("workspace/applyEdit", refuse_edit)
        self.server.on_notification("textDocument/publishDiagnostics", diagnostics)
        self.server.on_notification("window/logMessage", ignore_notification)
        self.server.on_notification("$/progress", ignore_notification)

        async with super().start_server():
            initialized = False
            try:
                await self.server.start()
                root = Path(self.repository_root_path)
                init = await asyncio.wait_for(
                    self.server.send.initialize(
                        {
                            "processId": None,
                            "rootUri": root.as_uri(),
                            "rootPath": str(root),
                            "workspaceFolders": [
                                {"uri": root.as_uri(), "name": root.name}
                            ],
                            "clientInfo": {"name": "multilspy"},
                            "capabilities": {
                                "general": {"positionEncodings": ["utf-16"]},
                                "workspace": {
                                    "applyEdit": False,
                                    "configuration": True,
                                    "workspaceFolders": False,
                                    "symbol": {},
                                },
                                "textDocument": {
                                    "definition": {"linkSupport": True},
                                    "typeDefinition": {"linkSupport": True},
                                    "references": {},
                                    "hover": {
                                        "contentFormat": ["markdown", "plaintext"]
                                    },
                                    "completion": {
                                        "completionItem": {
                                            "snippetSupport": False,
                                            "documentationFormat": ["plaintext"],
                                        }
                                    },
                                    "signatureHelp": {
                                        "signatureInformation": {
                                            "documentationFormat": ["plaintext"],
                                        }
                                    },
                                    "documentSymbol": {
                                        "hierarchicalDocumentSymbolSupport": True
                                    },
                                    "publishDiagnostics": {
                                        "relatedInformation": True
                                    },
                                },
                            },
                        }
                    ),
                    timeout=30,
                )
                capabilities = init.get("capabilities") if isinstance(init, dict) else None
                if not isinstance(capabilities, dict):
                    raise ValueError("Invalid Pyright initialization capabilities")
                if capabilities.get("positionEncoding", "utf-16") != "utf-16":
                    raise ValueError("Unsupported Pyright position encoding")
                self.server.notify.initialized({})
                self.completions_available.set()
                initialized = True
                yield self
            finally:
                try:
                    if initialized:
                        await asyncio.wait_for(self.server.shutdown(), timeout=8)
                finally:
                    await self.server.stop()
