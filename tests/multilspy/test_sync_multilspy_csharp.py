"""Synchronous integration coverage for OmniSharp using a local C# solution."""

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger
from tests.multilspy.csharp_test_utils import (
    csharp_project, assert_definition, assert_references, assert_completions,
)


def test_sync_multilspy_csharp(csharp_project):
    server = SyncLanguageServer.create(
        MultilspyConfig(code_language=Language.CSHARP), MultilspyLogger(), str(csharp_project), timeout=30
    )
    with server.start_server():
        assert_definition(server.request_definition("Consumer.cs", 4, 46))
        assert_references(server.request_references("Constants.cs", 6, 25))
        with server.open_file("Consumer.cs"):
            deleted = server.delete_text_between_positions(
                "Consumer.cs", {"line": 6, "character": 46}, {"line": 6, "character": 51}
            )
            assert deleted == "First"
            assert_completions(server.request_completions("Consumer.cs", 6, 46, allow_incomplete=True))
