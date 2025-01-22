"""
This file contains tests for running the Ruby Language Server: ruby-analyzer
"""

import unittest

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

def test_multilspy_ruby_rubyland() -> None:
    """
    Test the working of multilspy with ruby repository - rubyland
    """
    code_language = Language.RUBY
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/jrochkind/rubyland/",
        "repo_commit": "c243ee2533a5822f5699a2475e492927ace039c7"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)
        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        with lsp.start_server():
            result = lsp.request_definition(str(PurePath("app/controllers/feed_controller.rb")), 11, 23)

            assert isinstance(result, list)
            assert len(result) == 2
            item = result[1]
            assert item["relativePath"] == str(PurePath("app/models/feed.rb"))
            assert item["range"] == {
                "start": {"line": 0, "character": 0},
                "end": {"line": 42, "character": 3},
            }

            result = lsp.request_references(str(PurePath("app/models/feed.rb")), 0, 7)

            assert isinstance(result, list)
            assert len(result) == 8

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            case = unittest.TestCase()
            case.assertCountEqual(
                result,
                [
                    {
                        "range": {
                            "start": {"line": 11, "character": 20},
                            "end": {"line": 11, "character": 24},
                        },
                        "relativePath": "app/controllers/feed_controller.rb",
                    },
                    {
                        "range": {
                            "start": {"line": 27, "character": 46},
                            "end": {"line": 27, "character": 50},
                        },
                        "relativePath": "app/controllers/feed_controller.rb",
                    },
                    {
                        "range": {
                            "start": {"line": 0, "character": 6},
                            "end": {"line": 0, "character": 10},
                        },
                        "relativePath": "app/models/feed.rb",
                    },
                    {
                        "range": {
                            "start": {"line": 13, "character": 74},
                            "end": {"line": 13, "character": 78},
                        },
                        "relativePath": "app/updaters/feed_updater.rb",
                    },
                    {
                        "range": {
                            "start": {"line": 52, "character": 4},
                            "end": {"line": 52, "character": 8},
                        },
                        "relativePath": "app/updaters/feed_updater.rb",
                    },
                    {
                        "range": {
                            "start": {"line": 10, "character": 20},
                            "end": {"line": 10, "character": 24},
                        },
                        "relativePath": "app/updaters/updater.rb",
                    },
                    {
                        "range": {
                            "start": {"line": 14, "character": 20},
                            "end": {"line": 14, "character": 24},
                        },
                        "relativePath": "app/updaters/updater.rb",
                    },
                    {
                        "range": {
                            "start": {"line": 0, "character": 6},
                            "end": {"line": 0, "character": 10},
                        },
                        "relativePath": "db/migrate/20161029161855_feed.rb",
                    },
                ]
            )
