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
            path = str(PurePath("lib/csv/csv.js"))
            result = await lsp.request_definition(path, 108, 3)
            assert isinstance(result, list)
            assert len(result) == 1

            item = result[0]
            assert item["relativePath"] == path
            assert item["range"] == {
                "start": {"line": 108, "character": 2},
                "end": {"line": 108, "character": 7},
            }

            result = await lsp.request_references(path, 108, 3)
            assert isinstance(result, list)
            assert len(result) == 2

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {'range': {'start': {'line': 180, 'character': 16}, 'end': {'line': 180, 'character': 21}}, 'relativePath': path},
                {'range': {'start': {'line': 185, 'character': 15}, 'end': {'line': 185, 'character': 20}}, 'relativePath': path}
            ]
