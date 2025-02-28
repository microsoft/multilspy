"""
This file contains tests for running the Python Language Server: jedi-language-server
"""

import pytest
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath
import time

def test_multilspy_timeout() -> None:
    """
    Test timeout error in multilspy
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory, timeout=1)

        # Mock the request_definition method to simulate a long running process
        async def request_definition(*args, **kwargs):
            time.sleep(5)
            return []

        lsp.language_server.request_definition = request_definition

        with lsp.start_server():
            with pytest.raises(TimeoutError):
                lsp.request_definition(str(PurePath("src/black/mode.py")), 163, 4)
