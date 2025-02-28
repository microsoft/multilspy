"""
This file contains tests for running the Python Language Server: jedi-language-server
"""

from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath


def test_sync_multilspy_dart() -> None:
    """
    Test the working of multilspy with python repository - black
    """
    code_language = Language.DART
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/simonoppowa/OpenNutriTracker/",
        "repo_commit": "2df39185bdd822dec6a0e521f4c14e3eab6b0805",
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(
            context.config, context.logger, context.source_directory
        )

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        with lsp.start_server():
            result = lsp.request_references(
                file_path=str(
                    PurePath("lib/features/add_meal/presentation/add_meal_screen.dart")
                ),
                line=19,
                column=5,
            )

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {
                    "range": {
                        "end": {"character": 21, "line": 20},
                        "start": {"character": 8, "line": 20},
                    },
                    "relativePath": "lib/features/add_meal/presentation/add_meal_screen.dart",
                },
                {
                    "range": {
                        "end": {"character": 21, "line": 23},
                        "start": {"character": 8, "line": 23},
                    },
                    "relativePath": "lib/features/add_meal/presentation/add_meal_screen.dart",
                },
                {
                    "range": {
                        "end": {"character": 53, "line": 26},
                        "start": {"character": 40, "line": 26},
                    },
                    "relativePath": "lib/features/add_meal/presentation/add_meal_screen.dart",
                },
            ]
