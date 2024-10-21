"""
This file contains tests for running the TypeScript Language Server: typescript-language-server
"""

import pytest
from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

pytest_plugins = ("pytest_asyncio",)

@pytest.mark.asyncio
async def test_multilspy_typescript_trpc():
    """
    Test the working of multilspy with typescript repository - trpc
    """
    code_language = Language.TYPESCRIPT
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/trpc/trpc/",
        "repo_commit": "936db6dd2598337758e29c843ff66984ed54faaf"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            path = str(PurePath("packages/server/src/core/router.ts"))
            result = await lsp.request_definition(path, 194, 8)
            assert isinstance(result, list)
            assert len(result) == 1

            item = result[0]
            assert item["relativePath"] == path
            assert item["range"] == {
                "start": {"line": 194, "character": 2},
                "end": {"line": 194, "character": 8},
            }

            result = await lsp.request_references(path, 194, 8)
            assert isinstance(result, list)
            assert len(result) == 2

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {'range': {'start': {'line': 231, 'character': 15}, 'end': {'line': 231, 'character': 21}}, 'relativePath': path}, 
                {'range': {'start': {'line': 264, 'character': 12}, 'end': {'line': 264, 'character': 18}}, 'relativePath': path}
            ]