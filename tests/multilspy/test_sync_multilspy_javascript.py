"""
This file contains tests for running the JavaScript Language Server: typescript-language-server
"""

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

def test_sync_multilspy_javascript_exceljs() -> None:
    """
    Test the working of multilspy with javascript repository - exceljs
    """
    code_language = Language.JAVASCRIPT
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/exceljs/exceljs/",
        "repo_commit": "ac96f9a61e9799c7776bd940f05c4a51d7200209"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        with lsp.start_server():
            path = str(PurePath("lib/csv/csv.js"))
            result = lsp.request_definition(path, 108, 3)
            assert isinstance(result, list)
            assert len(result) == 1

            item = result[0]
            assert item["relativePath"] == path
            assert item["range"] == {
                "start": {"line": 108, "character": 2},
                "end": {"line": 108, "character": 7},
            }

            result = lsp.request_references(path, 108, 3)
            assert isinstance(result, list)
            assert len(result) == 2

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {'range': {'start': {'line': 180, 'character': 16}, 'end': {'line': 180, 'character': 21}}, 'relativePath': path},
                {'range': {'start': {'line': 185, 'character': 15}, 'end': {'line': 185, 'character': 20}}, 'relativePath': path}
            ]

def test_sync_multilspy_javascript_violentmonkey_cross_file() -> None:
    """
    Test the working of multilspy with javascript repository - violentmonkey
    """
    code_language = Language.JAVASCRIPT
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/violentmonkey/violentmonkey/",
        "repo_commit": "e2930510b4fb5f59848ecafcd533d06fc41d4187"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        with lsp.start_server():
            result = lsp.request_definition("src/common/util.js", 335, 55)
            print("Definition", result)
            assert isinstance(result, list)
            assert len(result) == 1

            item = result[0]
            assert item["relativePath"] == "src/common/consts.js"
            assert item["range"] == {
                "start": {"line": 46, "character": 13},
                "end": {"line": 46, "character": 21},
            }

            result = lsp.request_references("src/common/consts.js", 46, 13)
            print("References", result)
            assert isinstance(result, list)
            assert len(result) == 10

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {"range": {"start": {"line": 2, "character": 9}, "end": {"line": 2, "character": 17}}, "relativePath": "src/common/util.js"},
                {"range": {"start": {"line": 335, "character": 51}, "end": {"line": 335, "character": 59}}, "relativePath": "src/common/util.js"},
                {"range": {"start": {"line": 5, "character": 16}, "end": {"line": 5, "character": 24}}, "relativePath": "src/background/sync/base.js"},
                {"range": {"start": {"line": 342, "character": 34}, "end": {"line": 342, "character": 42}}, "relativePath": "src/background/sync/base.js"},
                {"range": {"start": {"line": 4, "character": 36}, "end": {"line": 4, "character": 44}}, "relativePath": "src/background/utils/update.js"},
                {"range": {"start": {"line": 15, "character": 5}, "end": {"line": 15, "character": 13}}, "relativePath": "src/background/utils/update.js"},
                {"range": {"start": {"line": 40, "character": 11}, "end": {"line": 40, "character": 19}}, "relativePath": "src/background/utils/update.js"},
                {"range": {"start": {"line": 123, "character": 48}, "end": {"line": 123, "character": 56}}, "relativePath": "src/background/utils/update.js"},
                {"range": {"start": {"line": 1, "character": 9}, "end": {"line": 1, "character": 17}}, "relativePath": "src/background/utils/storage-fetch.js"},
                {"range": {"start": {"line": 70, "character": 26}, "end": {"line": 70, "character": 34}}, "relativePath": "src/background/utils/storage-fetch.js"}
            ]