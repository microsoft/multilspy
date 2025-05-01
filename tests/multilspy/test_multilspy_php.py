"""
This file contains tests for running the Intelephense Language Server.
"""

import pytest
from multilspy import LanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath

pytest_plugins = ("pytest_asyncio",)


@pytest.mark.asyncio
async def test_multilspy_php():
    """
    Test the working of multilspy with a PHP repository.
    """
    code_language = Language.PHP
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/phpactor/phpactor/",
        "repo_commit": "bfc8a7040bed145a35fb9afee0ddd645297b9ed9",
    }

    with create_test_context(params) as context:
        lsp = LanguageServer.create(
            context.config, context.logger, context.source_directory
        )
        async with lsp.start_server():
            result = await lsp.request_definition(
                str(PurePath("lib/ConfigLoader/Tests/TestCase.php")),
                13,
                16,
            )

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {
                    "range": {
                        "start": {"line": 9, "character": 24},
                        "end": {"line": 9, "character": 34},
                    },
                    "relativePath": "lib/ConfigLoader/Tests/TestCase.php",
                }
            ]

            result = await lsp.request_document_symbols(
                str(
                    PurePath(
                        "lib/Extension/LanguageServerIndexer/Handler/WorkspaceSymbolHandler.php"
                    )
                ),
            )

            assert isinstance(result, tuple)
            assert len(result) == 2

            symbols = result[0]

            assert symbols == [
                {
                    "name": "Phpactor\\Extension\\LanguageServerIndexer\\Handler",
                    "kind": 3,
                    "range": {
                        "start": {"line": 2, "character": 0},
                        "end": {"line": 2, "character": 59},
                    },
                    "selectionRange": {
                        "start": {"line": 2, "character": 10},
                        "end": {"line": 2, "character": 58},
                    },
                },
                {
                    "name": "WorkspaceSymbolHandler",
                    "kind": 5,
                    "range": {
                        "start": {"line": 12, "character": 0},
                        "end": {"line": 43, "character": 1},
                    },
                    "selectionRange": {
                        "start": {"line": 12, "character": 6},
                        "end": {"line": 12, "character": 28},
                    },
                },
                {
                    "name": "$provider",
                    "kind": 7,
                    "range": {
                        "start": {"line": 14, "character": 36},
                        "end": {"line": 14, "character": 45},
                    },
                    "selectionRange": {
                        "start": {"line": 14, "character": 36},
                        "end": {"line": 14, "character": 45},
                    },
                },
                {
                    "name": "__construct",
                    "kind": 9,
                    "range": {
                        "start": {"line": 16, "character": 4},
                        "end": {"line": 19, "character": 5},
                    },
                    "selectionRange": {
                        "start": {"line": 16, "character": 20},
                        "end": {"line": 16, "character": 31},
                    },
                },
                {
                    "name": "$provider",
                    "kind": 13,
                    "range": {
                        "start": {"line": 16, "character": 32},
                        "end": {"line": 16, "character": 65},
                    },
                    "selectionRange": {
                        "start": {"line": 16, "character": 56},
                        "end": {"line": 16, "character": 65},
                    },
                },
                {
                    "name": "methods",
                    "kind": 6,
                    "range": {
                        "start": {"line": 21, "character": 4},
                        "end": {"line": 26, "character": 5},
                    },
                    "selectionRange": {
                        "start": {"line": 21, "character": 20},
                        "end": {"line": 21, "character": 27},
                    },
                },
                {
                    "name": "symbol",
                    "kind": 6,
                    "range": {
                        "start": {"line": 28, "character": 4},
                        "end": {"line": 37, "character": 5},
                    },
                    "selectionRange": {
                        "start": {"line": 31, "character": 20},
                        "end": {"line": 31, "character": 26},
                    },
                },
                {
                    "name": "$params",
                    "kind": 13,
                    "range": {
                        "start": {"line": 32, "character": 8},
                        "end": {"line": 32, "character": 37},
                    },
                    "selectionRange": {
                        "start": {"line": 32, "character": 30},
                        "end": {"line": 32, "character": 37},
                    },
                },
                {
                    "name": "Closure",
                    "kind": 12,
                    "range": {
                        "start": {"line": 34, "character": 25},
                        "end": {"line": 36, "character": 9},
                    },
                    "selectionRange": {
                        "start": {"line": 34, "character": 25},
                        "end": {"line": 36, "character": 9},
                    },
                },
                {
                    "name": "$params",
                    "kind": 13,
                    "range": {
                        "start": {"line": 34, "character": 42},
                        "end": {"line": 34, "character": 49},
                    },
                    "selectionRange": {
                        "start": {"line": 34, "character": 42},
                        "end": {"line": 34, "character": 49},
                    },
                },
                {
                    "name": "registerCapabiltiies",
                    "kind": 6,
                    "range": {
                        "start": {"line": 39, "character": 4},
                        "end": {"line": 42, "character": 5},
                    },
                    "selectionRange": {
                        "start": {"line": 39, "character": 20},
                        "end": {"line": 39, "character": 40},
                    },
                },
                {
                    "name": "$capabilities",
                    "kind": 13,
                    "range": {
                        "start": {"line": 39, "character": 41},
                        "end": {"line": 39, "character": 73},
                    },
                    "selectionRange": {
                        "start": {"line": 39, "character": 60},
                        "end": {"line": 39, "character": 73},
                    },
                },
                {
                    "name": "$capabilities",
                    "kind": 13,
                    "range": {
                        "start": {"line": 41, "character": 8},
                        "end": {"line": 41, "character": 21},
                    },
                    "selectionRange": {
                        "start": {"line": 41, "character": 8},
                        "end": {"line": 41, "character": 21},
                    },
                },
            ]


@pytest.mark.asyncio
async def test_multilspy_php_multiple_references():
    """
    Test the working of multilspy with PHP Language Server
    """
    code_language = Language.PHP
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/myclabs/DeepCopy/",
        "repo_commit": "1720ddd719e16cf0db4eb1c6eca108031636d46c",
    }
    with create_test_context(params) as context:
        lsp = LanguageServer.create(
            context.config, context.logger, context.source_directory
        )

        async with lsp.start_server():
            result = await lsp.request_references(
                file_path=str(PurePath("src/DeepCopy/DeepCopy.php")),
                line=27,
                column=8,
            )

            """
            This should be greater than 0 but the language server is not finding
            the references for some reason.
            """
            assert len(result) > 0