"""
This file contains tests for running the C# Language Server: OmniSharp
"""


from multilspy import SyncLanguageServer
from multilspy.multilspy_config import Language
from tests.test_utils import create_test_context
from pathlib import PurePath


def test_multilspy_csharp_ryujinx() -> None:
    """
    Test the working of multilspy with C# repository - Ryujinx
    """
    code_language = Language.CSHARP
    params = {
        "code_language": code_language,
        "repo_url": "https://github.com/LakshyAAAgrawal/Ryujinx/",
        "repo_commit": "e768a54f17b390c3ac10904c7909e3bef020edbd"
    }
    with create_test_context(params) as context:
        lsp = SyncLanguageServer.create(context.config, context.logger, context.source_directory)

        # All the communication with the language server must be performed inside the context manager
        # The server process is started when the context manager is entered and is terminated when the context manager is exited.
        with lsp.start_server():
            result = lsp.request_definition(str(PurePath("src/Ryujinx.Audio/Input/AudioInputManager.cs")), 176, 44)

            assert isinstance(result, list)
            assert len(result) == 1
            item = result[0]
            assert item["relativePath"] == str(PurePath("src/Ryujinx.Audio/Constants.cs"))
            assert item["range"] == {
                "start": {"line": 15, "character": 28},
                "end": {"line": 15, "character": 50},
            }

            result = lsp.request_references(str(PurePath("src/Ryujinx.Audio/Constants.cs")), 15, 40)

            assert isinstance(result, list)
            assert len(result) == 2

            for item in result:
                del item["uri"]
                del item["absolutePath"]

            assert result == [
                {
                    "relativePath": str(PurePath("src/Ryujinx.Audio/Input/AudioInputManager.cs")),
                    "range": {
                        "start": {"line": 176, "character": 37},
                        "end": {"line": 176, "character": 59},
                    },
                },
                {
                    "relativePath": str(PurePath("src/Ryujinx.Audio/Input/AudioInputSystem.cs")),
                    "range": {
                        "start": {"line": 77, "character": 29},
                        "end": {"line": 77, "character": 51},
                    },
                },
            ]
