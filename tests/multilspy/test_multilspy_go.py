"""
This file contains tests for running the Golang Language Server: gopls
"""

import pytest
from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

pytest_plugins = ("pytest_asyncio",)

@pytest.mark.asyncio
async def test_multilspy_golang_bbolt():
    """
    Test the working of multilspy with golang repository - bbolt
    """
    code_language = Language.GO
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/etcd-io/bbolt/",
        "repo_commit": "7b2d3609bf79d1810d6454b22205dfe4ab754991"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            path = str(PurePath("cmd/bbolt/main.go"))
            result = await lsp.request_definition(path, 214, 18)
            assert isinstance(result, list)
            assert len(result) == 1

            item = result[0]
            assert item["relativePath"] == str(PurePath("db.go"))
            assert item["range"] == {
                "start": {"line": 177, "character": 5},
                "end": {"line": 177, "character": 9},
            }

            result = await lsp.request_references(path, 1275, 18)
            assert isinstance(result, list)
            assert len(result) == 2

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {'range': {'start': {'line': 1128, 'character': 6}, 'end': {'line': 1128, 'character': 20}}, 'relativePath': path}, 
                {'range': {'start': {'line': 1275, 'character': 6}, 'end': {'line': 1275, 'character': 20}}, 'relativePath': path}, 
            ]