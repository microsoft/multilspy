"""Integration coverage for OmniSharp using a local C# solution."""

import asyncio

import pytest

from multilspy import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from tests.multilspy.csharp_test_utils import (
    csharp_project, assert_definition, assert_references, assert_completions,
)


@pytest.mark.asyncio
async def test_multilspy_csharp(csharp_project):
    server = LanguageServer.create(
        MultilspyConfig(code_language=Language.CSHARP), MultilspyLogger(), str(csharp_project)
    )
    async with server.start_server():
        assert_definition(await asyncio.wait_for(
            server.request_definition("Consumer.cs", 4, 46), timeout=30
        ))
        assert_references(await asyncio.wait_for(
            server.request_references("Constants.cs", 6, 25), timeout=30
        ))
        with server.open_file("Consumer.cs"):
            deleted = server.delete_text_between_positions(
                "Consumer.cs", {"line": 6, "character": 46}, {"line": 6, "character": 51}
            )
            assert deleted == "First"
            assert_completions(await asyncio.wait_for(
                server.request_completions("Consumer.cs", 6, 46, allow_incomplete=True), timeout=30
            ))
