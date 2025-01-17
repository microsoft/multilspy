"""
This file contains tests for running the Ruby Language Server: ruby-analyzer
"""

import unittest

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

def test_multilspy_ruby_rails_rails() -> None:
    """
    Test the working of multilspy with ruby repository - carbonyl
    """
    code_language = Language.RUBY
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/rails/rails/",
        "repo_commit": "abb7035e08c07bb4e2941c1c27003609ce81e77b"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)
        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        with lsp.start_server():
            result = lsp.request_definition(str(PurePath("activemodel/lib/active_model.rb")), 32, 5)

            assert isinstance(result, list)
            assert len(result) == 1
            item = result[0]
            assert item["relativePath"] == str(PurePath("actionview/lib/action_view.rb"))
            assert item["range"] == {
                "start": {"line": 43, "character": 11},
                "end": {"line": 43, "character": 19},
            }

            result = lsp.request_references(str(PurePath("actionview/lib/action_view.rb")), 43, 15)

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
