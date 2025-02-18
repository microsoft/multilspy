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
async def test_multilspy_golang_example():
    """
    Test the working of multilspy with golang repository - https://github.com/golang/example
    """
    code_language = Language.GO
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/golang/example/",
        "repo_commit": "1bcfdd08c5584d89507e37be70af63c72eb8c16f"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        async with lsp.start_server():
            # Wait for server to be fully initialized
            await lsp.server_ready.wait()
            
            path = str(PurePath("hello/hello.go"))
            
            # Test 1: Get definition of the 'reverse' package import
            result = await lsp.request_definition(path, 29, 8)
            assert isinstance(result, list)
            assert len(result) == 1

            item = result[0]
            assert "reverse" in item["relativePath"]
            assert item["range"]["start"]["line"] == 5  # Package declaration is after license header

            # Test 2: Find references to the 'name' variable
            result = await lsp.request_references(path, 61, 5)  # Position of name declaration
            assert isinstance(result, list)
            assert len(result) == 5 

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {
                    'range': {
                        'start': {'line': 59, 'character': 2},
                        'end': {'line': 59, 'character': 6}
                    },
                    'relativePath': 'hello/hello.go'
                },
                {
                    'range': {
                        'start': {'line': 61, 'character': 4},
                        'end': {'line': 61, 'character': 8}
                    },
                    'relativePath': 'hello/hello.go'
                },
                {
                    'range': {
                        'start': {'line': 62, 'character': 32},
                        'end': {'line': 62, 'character': 36}
                    },
                    'relativePath': 'hello/hello.go'
                },
                {
                    'range': {
                        'start': {'line': 67, 'character': 68},
                        'end': {'line': 67, 'character': 72}
                    },
                    'relativePath': 'hello/hello.go'
                },
                {
                    'range': {
                        'start': {'line': 70, 'character': 36},
                        'end': {'line': 70, 'character': 40}
                    },
                    'relativePath': 'hello/hello.go'
                }
            ]

            # Test 3: Get hover information for the 'name' variable
            result = await lsp.request_hover(path, 59, 5)  # Position of reverse.String call
            assert result is not None
            assert "var name string" in result["contents"]["value"]
            # Test 4: Get document symbols
            result = await lsp.request_document_symbols(path)
            assert isinstance(result, tuple)
            
            # Check if the symbols are in the result
            assert [symbol["name"] for symbol in result[0]] == ["usage", "greeting", "reverseFlag", "main"]
