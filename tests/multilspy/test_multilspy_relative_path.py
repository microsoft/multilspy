"""
This file contains tests for running the Python Language Server: jedi-language-server
"""

import pytest
from multilspy import LanguageServer
from multilspy.language_servers.jedi_language_server.jedi_server import JediServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath
from unittest.mock import patch

pytest_plugins = ("pytest_asyncio",)


@pytest.mark.asyncio
async def test_multilspy_relative_path():
    """
    Test the relative path not breaking in case if the repository
    and returned paths are using different drive letters.
    """
    code_language = Language.PYTHON
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/psf/black/",
        "repo_commit": "f3b50e466969f9142393ec32a4b2a383ffbe5f23",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(context.config, context.logger, context.source_directory)
        assert isinstance(lsp, JediServer)

        async with lsp.start_server():
            drive_letter = "X:" if PurePath(context.source_directory).drive == "C:" else "C:"
            response_path = f"file:///{drive_letter}/test.py"
            definition_response = [
                {
                    "uri": response_path,
                    "range": {"start": {"line": 856, "character": 6}, "end": {"line": 856, "character": 10}},
                }
            ]

            @patch(
                "multilspy.lsp_protocol_handler.lsp_requests.LspRequest.definition", return_value=definition_response
            )
            async def run_request_definition_test(_):
                result = await lsp.request_definition(str(PurePath("src/black/mode.py")), 163, 4)
                assert isinstance(result, list)
                assert len(result) == 1
                item = result[0]
                del item["absolutePath"]
                assert item["uri"] == definition_response[0]["uri"]
                assert item["range"] == definition_response[0]["range"]
                assert item["relativePath"] is None

            await run_request_definition_test()

            references_response = definition_response.copy()

            @patch(
                "multilspy.lsp_protocol_handler.lsp_requests.LspRequest.references", return_value=references_response
            )
            async def run_request_references_test(_):
                result = await lsp.request_references(str(PurePath("src/black/mode.py")), 163, 4)
                assert isinstance(result, list)
                assert len(result) == 1
                item = result[0]
                del item["absolutePath"]
                assert item["uri"] == definition_response[0]["uri"]
                assert item["range"] == definition_response[0]["range"]
                assert item["relativePath"] is None

            await run_request_references_test()
