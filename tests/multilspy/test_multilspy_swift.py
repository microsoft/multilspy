"""
This file contains tests for running the SourceKit-LSP Swift Language Server.
"""

import pytest
from pathlib import PurePath

from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context

pytest_plugins = ("pytest_asyncio",)

@pytest.mark.asyncio
async def test_multilspy_swift_document_symbols() -> None:
    params = {
        "code_language": Language.SWIFT,
        "repo_url": "https://github.com/SwiftyJSON/SwiftyJSON/",
        "repo_commit": "8805b547079d605f61f9c7964296384ff6fe853e"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        test_file = str(PurePath("Source/SwiftyJSON/SwiftyJSON.swift"))

        async with lsp.start_server():
            result = await lsp.request_document_symbols(test_file)

            symbols = result[0]
            assert len(symbols) > 0, "Should find document symbols"

            # Verify the SwiftyJSONError enum symbol
            error_symbol = next((s for s in symbols if s["name"] == "SwiftyJSONError"), None)
            assert error_symbol is not None, "SwiftyJSONError enum should be present"

@pytest.mark.asyncio
async def test_multilspy_swift_definition() -> None:
    params = {
        "code_language": Language.SWIFT,
        "repo_url": "https://github.com/SwiftyJSON/SwiftyJSON/",
        "repo_commit": "8805b547079d605f61f9c7964296384ff6fe853e"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # SwiftyJSON.swift is a single large file, test go-to-definition within it
        test_file = str(PurePath("Source/SwiftyJSON/SwiftyJSON.swift"))

        async with lsp.start_server():
            # Line 35 col 15 is SwiftyJSONError in "extension SwiftyJSONError: CustomNSError"
            definition_result = await lsp.request_definition(test_file, 35, 15)

            assert definition_result is not None, "Definition result should not be None"
            assert len(definition_result) >= 1, "Should find at least one definition"

@pytest.mark.asyncio
async def test_multilspy_swift_references() -> None:
    params = {
        "code_language": Language.SWIFT,
        "repo_url": "https://github.com/SwiftyJSON/SwiftyJSON/",
        "repo_commit": "8805b547079d605f61f9c7964296384ff6fe853e"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        # Find references to SwiftyJSONError enum (used throughout the file)
        test_file = str(PurePath("Source/SwiftyJSON/SwiftyJSON.swift"))

        async with lsp.start_server():
            references = await lsp.request_references(test_file, 35, 15)

            assert references is not None, "References should not be None"
            assert len(references) >= 1, "Should find at least one reference to SwiftyJSONError"

@pytest.mark.asyncio
async def test_multilspy_swift_completions() -> None:
    params = {
        "code_language": Language.SWIFT,
        "repo_url": "https://github.com/SwiftyJSON/SwiftyJSON/",
        "repo_commit": "8805b547079d605f61f9c7964296384ff6fe853e"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        test_file = str(PurePath("Source/SwiftyJSON/SwiftyJSON.swift"))

        async with lsp.start_server():
            completions = await lsp.request_completions(test_file, 35, 15, allow_incomplete=True)

            assert completions is not None, "Completions result should not be None"
            assert len(completions) > 0, "Should find at least one completion item"

            # Verify completion items have required properties
            for item in completions:
                assert "completionText" in item, "Completion item should have completionText"
                assert "kind" in item, "Completion item should have kind"

@pytest.mark.asyncio
async def test_multilspy_swift_hover() -> None:
    params = {
        "code_language": Language.SWIFT,
        "repo_url": "https://github.com/SwiftyJSON/SwiftyJSON/",
        "repo_commit": "8805b547079d605f61f9c7964296384ff6fe853e"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        test_file = str(PurePath("Source/SwiftyJSON/SwiftyJSON.swift"))

        async with lsp.start_server():
            # Hover over SwiftyJSONError enum
            hover_result = await lsp.request_hover(test_file, 35, 15)

            assert hover_result is not None, "Hover result should not be None"
            assert "contents" in hover_result, "Hover result should contain contents"

