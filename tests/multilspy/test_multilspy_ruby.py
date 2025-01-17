"""
This file contains tests for running the Ruby Language Server: Ruby-analyzer
"""

import unittest
import pytest

from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from multilspy.multilspy_types import Position, CompletionItemKind
from tests.test_utils import create_test_context
from pathlib import PurePath


async def test_multilspy_ruby_carbonyl():
    """
    Test the working of multilspy with ruby repository - rails/rails
    """
    code_language = Language.RUBY
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/rails/rails/",
        "repo_commit": "abb7035e08c07bb4e2941c1c27003609ce81e77b"
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        # The context manager is an asynchronous context manager, so it must be used with async with.
        async with lsp.start_server():
            result = await lsp.request_definition(str(PurePath("activemodel/lib/active_model.rb")), 132, 18)

            assert isinstance(result, list)
            assert len(result) == 1
            item = result[0]
            assert item["relativePath"] == str(PurePath("actionview/lib/action_view.rb"))
            assert item["range"] == {
                "start": {"line": 43, "character": 11},
                "end": {"line": 43, "character": 19},
            }

            result = await lsp.request_references(str(PurePath("activemodel/lib/active_model.rb")), 43, 15)

            assert isinstance(result, list)
            assert len(result) == 2

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            case = unittest.TestCase()
            case.assertCountEqual(
                result,
                [
                    {
                        "relativePath": str(PurePath("activemodel/lib/active_model.rb")),
                        "range": {
                            "start": {"line": 132, "character": 13},
                            "end": {"line": 132, "character": 21},
                        },
                    },
                    {
                        "relativePath": str(PurePath("actionview/lib/action_view.rb")),
                        "range": {
                            "start": {"line": 16, "character": 13},
                            "end": {"line": 16, "character": 21},
                        },
                    },
                ],
            )

# @pytest.mark.asyncio
# async def test_multilspy_rust_completions_mediaplayer() -> None:
#     """
#     Test the working of multilspy with Rust repository - mediaplayer
#     """
#     code_language = Language.RUST
#     params = {
#         "code_language": code_language,
#         "repo_url": "https://github.com/LakshyAAAgrawal/MediaPlayer_example/",
#         "repo_commit": "ba27bb16c7ba1d88808300364af65eb69b1d84a8",
#     }

#     with create_test_context(params) as context:
#         lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
#         filepath = "src/playlist.rs"
#         # All the communication with the language server must be performed inside the context manager
#         # The server process is started when the context manager is entered and is terminated when the context manager is exited.
#         async with lsp.start_server():
#             with lsp.open_file(filepath):
#                 deleted_text = lsp.delete_text_between_positions(
#                     filepath, Position(line=10, character=40), Position(line=12, character=4)
#                 )
#                 assert (
#                     deleted_text
#                     == """reset();
#         media_player1 = media_player;
#     """
#                 )

#                 response = await lsp.request_completions(filepath, 10, 40, allow_incomplete=True)

#                 response = [item for item in response if item['kind'] != CompletionItemKind.Snippet]

#                 for item in response:
#                     item['completionText'] = item['completionText'][:item['completionText'].find('(')]
                
#                 assert set([item['completionText'] for item in response]) == {'reset', 'into', 'try_into', 'prepare'}
