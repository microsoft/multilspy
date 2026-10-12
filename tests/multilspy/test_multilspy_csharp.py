"""Integration coverage for OmniSharp using the pinned Json.NET solution."""

import asyncio

import pytest

from multilspy import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from tests.multilspy.csharp_test_utils import (
    csharp_project, assert_definition, assert_references, assert_completions, SERIALIZER, SETTINGS,
)


@pytest.mark.asyncio
@pytest.mark.timeout(180)
async def test_multilspy_csharp(csharp_project):
    server = LanguageServer.create(
        MultilspyConfig(code_language=Language.CSHARP), MultilspyLogger(), str(csharp_project)
    )
    async with server.start_server():
        assert_definition(await asyncio.wait_for(
            server.request_definition(SERIALIZER, 562, 58), timeout=30
        ))
        assert_references(await asyncio.wait_for(
            server.request_references(SETTINGS, 53, 43), timeout=30
        ))
        with server.open_file(SETTINGS):
            deleted = server.delete_text_between_positions(
                SETTINGS, {"line": 53, "character": 92}, {"line": 53, "character": 99}
            )
            assert deleted == "Default"
            assert_completions(await asyncio.wait_for(
                server.request_completions(SETTINGS, 53, 92, allow_incomplete=True), timeout=30
            ))
