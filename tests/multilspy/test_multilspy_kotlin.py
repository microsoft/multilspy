"""
This file contains tests for running the Java Language Server: Eclipse JDT.LS
"""

import pytest
from pathlib import PurePath
from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from multilspy.multilspy_types import Position, CompletionItemKind
from tests.test_utils import create_test_context

pytest_plugins = ("pytest_asyncio",)

@pytest.mark.asyncio
async def test_multilspy_kotlin_example_repo_document_symbols() -> None:
    code_language = Language.KOTLIN
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/LakshyAAAgrawal/ExampleRepo/",
        "repo_commit": "f3762fd55a457ff9c6b0bf3b266de2b203a766ab",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        async with lsp.start_server():
            filepath = str(PurePath("Person.java"))
            result = await lsp.request_document_symbols(filepath)

            print(result)