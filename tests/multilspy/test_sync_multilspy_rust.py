"""
This file contains tests for running the Rust Language Server: rust-analyzer
"""

import unittest

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

def test_multilspy_rust_carbonyl() -> None:
    """
    Test the working of multilspy with rust repository - carbonyl
    """
    code_language = Language.RUST
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/fathyb/carbonyl/",
        "repo_commit": "ab80a276b1bd1c2c8dcefc8f248415dfc61dc2bf"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        with lsp.start_server():
            result = lsp.request_definition(str(PurePath("src/browser/bridge.rs")), 132, 18)

            assert isinstance(result, list)
            assert len(result) == 1
            item = result[0]
            assert item["relativePath"] == str(PurePath("src/input/tty.rs"))
            assert item["range"] == {
                "start": {"line": 43, "character": 11},
                "end": {"line": 43, "character": 19},
            }

            result = lsp.request_references(str(PurePath("src/input/tty.rs")), 43, 15)

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
                        "relativePath": str(PurePath("src/browser/bridge.rs")),
                        "range": {
                            "start": {"line": 132, "character": 13},
                            "end": {"line": 132, "character": 21},
                        },
                    },
                    {
                        "relativePath": str(PurePath("src/input/tty.rs")),
                        "range": {
                            "start": {"line": 16, "character": 13},
                            "end": {"line": 16, "character": 21},
                        },
                    },
                ],
            )
