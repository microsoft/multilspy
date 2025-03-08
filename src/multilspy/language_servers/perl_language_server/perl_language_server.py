"""
Provides Perl specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Perl.
"""

import json
import logging
import os
import pathlib
from contextlib import asynccontextmanager
from typing import AsyncIterator

from multilspy.multilspy_logger import MultilspyLogger
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.lsp_protocol_handler.lsp_types import InitializeParams
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_exceptions import MultilspyException


class PerlLanguageServer(LanguageServer):
    """
    Provides Perl specific instantiation of the LanguageServer class. Contains various configurations and settings specific to Perl.
    """

    def __init__(self, config: MultilspyConfig, logger: MultilspyLogger, repository_root_path: str):
        """
        Creates a PerlLanguageServer instance. This class is not meant to be instantiated directly. 
        Use LanguageServer.create() instead.
        """
        try:
            import subprocess
            cmd = None

            # Perl::LanguageServer
            if not cmd:
                perl_cmd = "perl -e 'eval \"use Coro; use AnyEvent; use AnyEvent::AIO; use Perl::LanguageServer;\"; print $@ ? 0 : 1'"
                result = subprocess.run(perl_cmd, shell=True, capture_output=True, text=True)
                if result.stdout.strip() == "1":
                    logger.log("Using Perl::LanguageServer", logging.INFO)
                    cmd = "perl -MPerl::LanguageServer -e 'Perl::LanguageServer::run(0, 1, 1, 1, 1, 1)'"
                
            if not cmd:
                logger.log("No Perl Language Server found. Please install:", logging.ERROR)
                logger.log("Perl::LanguageServer: cpanm Coro AnyEvent AnyEvent::AIO Perl::LanguageServer", logging.ERROR)
                raise MultilspyException("No Perl Language Server installed")

        except Exception as e:
            logger.log(f"Error checking Perl Language Servers: {str(e)}", logging.ERROR)
            raise MultilspyException(f"Error checking Perl Language Servers: {str(e)}")
        
        super().__init__(
            config,
            logger,
            repository_root_path,
            ProcessLaunchInfo(cmd=cmd, cwd=repository_root_path),
            "perl",
        )

    def _get_initialize_params(self, repository_absolute_path: str) -> InitializeParams:
        """
        Returns the initialize params for the Perl Language Server.
        """
        # Create a basic initialize params structure
        # This can be expanded with more specific settings if needed
        params = {
            "processId": os.getpid(),
            "rootPath": repository_absolute_path,
            "rootUri": pathlib.Path(repository_absolute_path).as_uri(),
            "capabilities": {
                "workspace": {
                    "applyEdit": True,
                    "workspaceEdit": {
                        "documentChanges": True
                    },
                    "didChangeConfiguration": {
                        "dynamicRegistration": True
                    },
                    "didChangeWatchedFiles": {
                        "dynamicRegistration": True
                    },
                    "symbol": {
                        "dynamicRegistration": True
                    },
                    "executeCommand": {
                        "dynamicRegistration": True
                    }
                },
                "textDocument": {
                    "synchronization": {
                        "dynamicRegistration": True,
                        "willSave": True,
                        "willSaveWaitUntil": True,
                        "didSave": True
                    },
                    "completion": {
                        "dynamicRegistration": True,
                        "completionItem": {
                            "snippetSupport": True,
                            "commitCharactersSupport": True,
                            "documentationFormat": ["markdown", "plaintext"],
                            "deprecatedSupport": True,
                            "preselectSupport": True
                        },
                        "contextSupport": True
                    },
                    "hover": {
                        "dynamicRegistration": True,
                        "contentFormat": ["markdown", "plaintext"]
                    },
                    "signatureHelp": {
                        "dynamicRegistration": True,
                        "signatureInformation": {
                            "documentationFormat": ["markdown", "plaintext"],
                            "parameterInformation": {
                                "labelOffsetSupport": True
                            }
                        }
                    },
                    "definition": {
                        "dynamicRegistration": True
                    },
                    "references": {
                        "dynamicRegistration": True
                    },
                    "documentHighlight": {
                        "dynamicRegistration": True
                    },
                    "documentSymbol": {
                        "dynamicRegistration": True,
                        "symbolKind": {
                            "valueSet": [
                                1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26
                            ]
                        },
                        "hierarchicalDocumentSymbolSupport": True
                    },
                    "codeAction": {
                        "dynamicRegistration": True,
                        "codeActionLiteralSupport": {
                            "codeActionKind": {
                                "valueSet": [
                                    "", "quickfix", "refactor", "refactor.extract", "refactor.inline", "refactor.rewrite",
                                    "source", "source.organizeImports"
                                ]
                            }
                        }
                    },
                    "codeLens": {
                        "dynamicRegistration": True
                    },
                    "formatting": {
                        "dynamicRegistration": True
                    },
                    "rangeFormatting": {
                        "dynamicRegistration": True
                    },
                    "onTypeFormatting": {
                        "dynamicRegistration": True
                    },
                    "rename": {
                        "dynamicRegistration": True
                    },
                    "publishDiagnostics": {
                        "relatedInformation": True,
                        "tagSupport": {
                            "valueSet": [1, 2]
                        }
                    }
                }
            },
            "workspaceFolders": [
                {
                    "uri": pathlib.Path(repository_absolute_path).as_uri(),
                    "name": os.path.basename(repository_absolute_path)
                }
            ]
        }

        return params

    @asynccontextmanager
    async def start_server(self) -> AsyncIterator["PerlLanguageServer"]:
        """
        Starts the Perl Language Server, waits for the server to be ready and yields the LanguageServer instance.

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

        async def check_experimental_status(params):
            if params.get("quiescent", False) == True:
                self.completions_available.set()

        async def window_log_message(msg):
            self.logger.log(f"LSP: window/logMessage: {msg}", logging.INFO)

        self.server.on_request("client/registerCapability", do_nothing)
        self.server.on_notification("language/status", do_nothing)
        self.server.on_notification("window/logMessage", window_log_message)
        self.server.on_request("workspace/executeClientCommand", execute_client_command_handler)
        self.server.on_notification("$/progress", do_nothing)
        self.server.on_notification("textDocument/publishDiagnostics", do_nothing)
        self.server.on_notification("language/actionableNotification", do_nothing)
        self.server.on_notification("experimental/serverStatus", check_experimental_status)

        async with super().start_server():
            self.logger.log("Starting Perl Language Server process", logging.INFO)
            await self.server.start()
            initialize_params = self._get_initialize_params(self.repository_root_path)

            self.logger.log(
                "Sending initialize request from LSP client to LSP server and awaiting response",
                logging.INFO,
            )
            init_response = await self.server.send.initialize(initialize_params)
            
            # Check for expected capabilities
            # These may need to be adjusted based on the actual capabilities of the Perl Language Server
            if "textDocumentSync" in init_response["capabilities"]:
                self.logger.log(f"textDocumentSync: {init_response['capabilities']['textDocumentSync']}", logging.INFO)
            
            if "completionProvider" in init_response["capabilities"]:
                self.logger.log(f"completionProvider: {init_response['capabilities']['completionProvider']}", logging.INFO)

            self.server.notify.initialized({})

            yield self

            await self.server.shutdown()
            await self.server.stop()
