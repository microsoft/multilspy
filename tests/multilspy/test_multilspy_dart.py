"""
This file contains tests for running the Dart Language Server.
"""

import pytest
from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

pytest_plugins = ("pytest_asyncio",)


@pytest.mark.asyncio
async def test_multilspy_dart_open_nutri_tracker():
    """
    Test the working of multilspy with a Dart repository.
    """
    code_language = Language.DART
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/simonoppowa/OpenNutriTracker/",
        "repo_commit": "2df39185bdd822dec6a0e521f4c14e3eab6b0805",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(
            context.config, context.logger, context.source_directory
        )

        async with lsp.start_server():
            result = await lsp.request_document_symbols(
                str(
                    PurePath("lib/core/presentation/widgets/copy_or_delete_dialog.dart")
                )
            )

            assert isinstance(result, tuple)
            assert len(result) == 2

            symbols = [
                {key: symbol[key] for key in ("name", "range", "selectionRange")}
                for symbol in result[0]
            ]
            assert symbols == [
                {
                    "name": "CopyOrDeleteDialog",
                    "range": {
                        "start": {"line": 3, "character": 0},
                        "end": {"line": 25, "character": 1},
                    },
                    "selectionRange": {
                        "start": {"line": 3, "character": 6},
                        "end": {"line": 3, "character": 24},
                    },
                },
                {
                    "name": "CopyOrDeleteDialog",
                    "range": {
                        "start": {"line": 4, "character": 2},
                        "end": {"line": 4, "character": 40},
                    },
                    "selectionRange": {
                        "start": {"line": 4, "character": 8},
                        "end": {"line": 4, "character": 26},
                    },
                },
                {
                    "name": "build",
                    "range": {
                        "start": {"line": 7, "character": 2},
                        "end": {"line": 24, "character": 3},
                    },
                    "selectionRange": {
                        "start": {"line": 7, "character": 9},
                        "end": {"line": 7, "character": 14},
                    },
                },
            ]
