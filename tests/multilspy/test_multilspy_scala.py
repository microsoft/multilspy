"""
This file contains tests for running the Metals Scala Language Server.
"""

import pytest
from pathlib import PurePath

from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context

pytest_plugins = ("pytest_asyncio",)

@pytest.mark.asyncio
async def test_multilspy_scala_document_symbols() -> None:
    params = {
        "code_language": Language.SCALA,
        "repo_url": "https://github.com/lhartikk/ArnoldC/",
        "repo_commit": "3dd905be59525f0b9a04e0baa6fd6acab09db8ea"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        test_file = str(PurePath("src/main/scala/org/arnoldc/ArnoldC.scala"))

        async with lsp.start_server():
            result = await lsp.request_document_symbols(test_file)

            symbols = result[0]
            assert len(symbols) > 0, "Should find document symbols"

            # Verify the ArnoldC object symbol
            arnoldc_symbol = next((s for s in symbols if s["name"] == "ArnoldC"), None)
            assert arnoldc_symbol is not None, "ArnoldC object should be present"

@pytest.mark.asyncio
async def test_multilspy_scala_definition() -> None:
    params = {
        "code_language": Language.SCALA,
        "repo_url": "https://github.com/lhartikk/ArnoldC/",
        "repo_commit": "3dd905be59525f0b9a04e0baa6fd6acab09db8ea"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # In ArnoldC.scala, line 11 (0-indexed): "val filename = getFilNameFromArgs(args)"
        # "getFilNameFromArgs" starts at column 19
        test_file = str(PurePath("src/main/scala/org/arnoldc/ArnoldC.scala"))

        async with lsp.start_server():
            definition_result = await lsp.request_definition(test_file, 11, 25)

            assert definition_result is not None, "Definition result should not be None"
            assert len(definition_result) >= 1, "Should find at least one definition"

            definition = definition_result[0]
            assert "ArnoldC.scala" in definition["relativePath"]

@pytest.mark.asyncio
async def test_multilspy_scala_completions() -> None:
    params = {
        "code_language": Language.SCALA,
        "repo_url": "https://github.com/lhartikk/ArnoldC/",
        "repo_commit": "3dd905be59525f0b9a04e0baa6fd6acab09db8ea"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # In ArnoldC.scala, line 7 (0-indexed): "println(\"Usage: ArnoldC [-run|-declaim] [FileToSourceCode]\")"
        test_file = str(PurePath("src/main/scala/org/arnoldc/ArnoldC.scala"))

        async with lsp.start_server():
            completions = await lsp.request_completions(test_file, 7, 12)

            assert completions is not None, "Completions result should not be None"
            assert len(completions) > 0, "Should find at least one completion item"

            # Verify completion items have required properties
            for item in completions:
                assert "completionText" in item, "Completion item should have completionText"
                assert "kind" in item, "Completion item should have kind"

@pytest.mark.asyncio
async def test_multilspy_scala_hover() -> None:
    params = {
        "code_language": Language.SCALA,
        "repo_url": "https://github.com/lhartikk/ArnoldC/",
        "repo_commit": "3dd905be59525f0b9a04e0baa6fd6acab09db8ea"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # Hover over "getFilNameFromArgs" in ArnoldC.scala, line 11 (0-indexed)
        test_file = str(PurePath("src/main/scala/org/arnoldc/ArnoldC.scala"))

        async with lsp.start_server():
            hover_result = await lsp.request_hover(test_file, 11, 25)

            assert hover_result is not None, "Hover result should not be None"
            assert "contents" in hover_result, "Hover result should contain contents"
