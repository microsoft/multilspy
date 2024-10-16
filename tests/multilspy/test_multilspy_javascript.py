"""
This file contains tests for running the Python Language Server: jedi-language-server
"""

import pytest
from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

pytest_plugins = ("pytest_asyncio",)

@pytest.mark.asyncio
async def test_multilspy_javascript_exceljs():
    """
    Test the working of multilspy with javascript repository - exceljs
    """
    code_language = Language.JAVASCRIPT
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/exceljs/exceljs/",
        "repo_commit": "ac96f9a61e9799c7776bd940f05c4a51d7200209"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            result = await lsp.request_definition(str(PurePath("src/black/mode.py")), 163, 4)

            assert isinstance(result, list)
            assert len(result) == 1
            item = result[0]
            assert item["relativePath"] == str(PurePath("src/black/mode.py"))
            assert item["range"] == {
                "start": {"line": 163, "character": 4},
                "end": {"line": 163, "character": 20},
            }

            result = await lsp.request_references(str(PurePath("src/black/mode.py")), 163, 4)

            assert isinstance(result, list)
            assert len(result) == 8

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {
                    "relativePath": str(PurePath("src/black/__init__.py")),
                    "range": {
                        "start": {"line": 71, "character": 4},
                        "end": {"line": 71, "character": 20},
                    },
                },
                {
                    "relativePath": str(PurePath("src/black/__init__.py")),
                    "range": {
                        "start": {"line": 1105, "character": 11},
                        "end": {"line": 1105, "character": 27},
                    },
                },
                {
                    "relativePath": str(PurePath("src/black/__init__.py")),
                    "range": {
                        "start": {"line": 1113, "character": 11},
                        "end": {"line": 1113, "character": 27},
                    },
                },
                {
                    "relativePath": str(PurePath("src/black/mode.py")),
                    "range": {
                        "start": {"line": 163, "character": 4},
                        "end": {"line": 163, "character": 20},
                    },
                },
                {
                    "relativePath": str(PurePath("src/black/parsing.py")),
                    "range": {
                        "start": {"line": 7, "character": 68},
                        "end": {"line": 7, "character": 84},
                    },
                },
                {
                    "relativePath": str(PurePath("src/black/parsing.py")),
                    "range": {
                        "start": {"line": 37, "character": 11},
                        "end": {"line": 37, "character": 27},
                    },
                },
                {
                    "relativePath": str(PurePath("src/black/parsing.py")),
                    "range": {
                        "start": {"line": 39, "character": 14},
                        "end": {"line": 39, "character": 30},
                    },
                },
                {
                    "relativePath": str(PurePath("src/black/parsing.py")),
                    "range": {
                        "start": {"line": 44, "character": 11},
                        "end": {"line": 44, "character": 27},
                    },
                },
            ]