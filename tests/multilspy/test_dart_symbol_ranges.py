"""Full symbol ranges from the pinned Dart language server."""

import asyncio

import pytest

from multilspy import LanguageServer, SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


@pytest.fixture
def dart_project(tmp_path):
    (tmp_path / "example.dart").write_text(
        "class Greeter {\n"
        "  String greet() {\n"
        "    return 'hello';\n"
        "  }\n"
        "}\n"
        "\n"
        "void main() {\n"
        "  Greeter().greet();\n"
        "}\n"
    )
    return tmp_path


def assert_symbol_ranges(result):
    symbols, _ = result
    by_name = {symbol["name"]: symbol for symbol in symbols}
    assert set(by_name) == {"Greeter", "greet", "main"}
    expected = {
        "Greeter": ((0, 0), (4, 1), (0, 6), (0, 13)),
        "greet": ((1, 2), (3, 3), (1, 9), (1, 14)),
        "main": ((6, 0), (8, 1), (6, 5), (6, 9)),
    }
    for name, (start, end, name_start, name_end) in expected.items():
        symbol = by_name[name]
        assert symbol["range"] == {
            "start": {"line": start[0], "character": start[1]},
            "end": {"line": end[0], "character": end[1]},
        }
        assert symbol["selectionRange"] == {
            "start": {"line": name_start[0], "character": name_start[1]},
            "end": {"line": name_end[0], "character": name_end[1]},
        }


@pytest.mark.asyncio
async def test_dart_full_symbol_ranges(dart_project):
    server = LanguageServer.create(
        MultilspyConfig(code_language=Language.DART), MultilspyLogger(), str(dart_project)
    )
    async with server.start_server():
        result = await asyncio.wait_for(server.request_document_symbols("example.dart"), timeout=30)
        assert_symbol_ranges(result)


def test_sync_dart_full_symbol_ranges(dart_project):
    server = SyncLanguageServer.create(
        MultilspyConfig(code_language=Language.DART), MultilspyLogger(), str(dart_project), timeout=30
    )
    with server.start_server():
        assert_symbol_ranges(server.request_document_symbols("example.dart"))
