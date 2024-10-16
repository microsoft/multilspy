"""
This file contains tests for running the Python Language Server: jedi-language-server
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
            # path = "./test-repos/test_js_repo/src/controllers/Auth/Login.ts"
            # result = lsp.request_document_symbols(path)
            # print(result)
            assert 1 == 1