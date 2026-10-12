"""Synchronous integration coverage for OmniSharp using the pinned Json.NET solution."""

import pytest

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from tests.multilspy.csharp_test_utils import (
    csharp_project, assert_definition, assert_references, assert_completions, SERIALIZER, SETTINGS,
)


@pytest.mark.timeout(180)
def test_sync_multilspy_csharp(csharp_project):
    server = SyncLanguageServer.create(
        MultilspyConfig(code_language=Language.CSHARP), MultilspyLogger(), str(csharp_project), timeout=30
    )
    with server.start_server():
        assert_definition(server.request_definition(SERIALIZER, 562, 58))
        assert_references(server.request_references(SETTINGS, 53, 43))
        with server.open_file(SETTINGS):
            deleted = server.delete_text_between_positions(
                SETTINGS, {"line": 53, "character": 92}, {"line": 53, "character": 99}
            )
            assert deleted == "Default"
            assert_completions(server.request_completions(SETTINGS, 53, 92, allow_incomplete=True))
