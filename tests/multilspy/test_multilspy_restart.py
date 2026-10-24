"""
This file contains a test for starting the same language server twice (typescript-language-server)
"""

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath


def test_sync_multilspy_typescript_start_server_twice() -> None:
    """
    Test that start_server can be entered repeatedly on the same SyncLanguageServer
    """
    code_language = Language.TYPESCRIPT
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/trpc/trpc/",
        "repo_commit": "936db6dd2598337758e29c843ff66984ed54faaf"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)
        path = str(PurePath("packages/server/src/core/router.ts"))

        with lsp.start_server():
            first_result = lsp.request_definition(path, 194, 8)
            first_server_ready = lsp.language_server.server_ready
            first_completions_available = lsp.language_server.completions_available

        # The readiness events are the root cause of the bug: they must not stay set after the session ends
        assert not lsp.language_server.server_ready.is_set()
        assert not lsp.language_server.completions_available.is_set()
        assert lsp.language_server.server_ready is not first_server_ready
        assert lsp.language_server.completions_available is not first_completions_available

        with lsp.start_server():
            second_result = lsp.request_definition(path, 194, 8)

        assert isinstance(first_result, list)
        assert len(first_result) == 1
        assert second_result == first_result
