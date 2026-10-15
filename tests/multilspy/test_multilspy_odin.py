"""
This file contains tests for running the Odin Language Server: ols
"""

import pytest
from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

pytest_plugins = ("pytest_asyncio",)


def _hover_text(hover) -> str:
    contents = hover["contents"]
    if isinstance(contents, str):
        return contents
    if isinstance(contents, dict):
        return contents.get("value", str(contents))
    if isinstance(contents, list):
        parts = []
        for item in contents:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("value", str(item)))
        return " ".join(parts)
    return str(contents)


@pytest.mark.asyncio
async def test_multilspy_odin_example():
    """
    Test the working of multilspy with odin repository - https://github.com/odin-lang/examples
    """
    code_language = Language.ODIN
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/odin-lang/examples/",
        "repo_commit": "a72abbdd1c87022188e82e8bc35c359d40cb1b28",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        async with lsp.start_server():
            await lsp.server_ready.wait()

            path = str(PurePath("absolute_beginners/5_structs.odin"))
            expected_rel = str(PurePath("absolute_beginners/5_structs.odin"))

            # Test 1: Get definition of the 'fmt' package import
            result = await lsp.request_definition(path, 2, 13)

            assert isinstance(result, list)
            assert len(result) >= 1

            item = result[0]
            assert "fmt" in item["uri"]

            # Test 2: Find references to the 'name' field
            result = await lsp.request_references(path, 12, 1)
            assert isinstance(result, list)
            assert len(result) == 3

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            expected_results = [
                {
                    "range": {
                        "start": {"line": 36, "character": 2},
                        "end": {"line": 36, "character": 6},
                    },
                    "relativePath": expected_rel,
                },
                {
                    "range": {
                        "start": {"line": 28, "character": 6},
                        "end": {"line": 28, "character": 10},
                    },
                    "relativePath": expected_rel,
                },
                {
                    "range": {
                        "start": {"line": 46, "character": 2},
                        "end": {"line": 46, "character": 6},
                    },
                    "relativePath": expected_rel,
                },
            ]

            for expected in expected_results:
                assert expected in result

            # Test 3: Get hover information for the 'age' field use
            result = await lsp.request_hover(path, 47, 2)
            assert result is not None
            assert "Cat.age: int" in _hover_text(result)

            # Test 4: Get document symbols
            result = await lsp.request_document_symbols(path)
            assert isinstance(result, tuple)

            names = [symbol["name"] for symbol in result[0]]
            assert len(names) == 4
            for name in ["Cat", "name", "age", "structs"]:
                assert name in names
