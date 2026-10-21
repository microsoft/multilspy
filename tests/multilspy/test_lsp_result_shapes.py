"""Normalize valid LSP return shapes across Python language server adapters.

Like test_completion_responses.py, inject a mocked LSP response and verify the
language-agnostic API without launching or downloading a language server.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from multilspy import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


@pytest.fixture(params=("jedi", "pyright"))
def server(tmp_path, request):
    (tmp_path / "example.py").write_text("def greet(): return 'hi'\n")
    instance = LanguageServer.create(
        MultilspyConfig(
            code_language=Language.PYTHON,
            python_server=request.param,
        ),
        MultilspyLogger(),
        str(tmp_path.resolve()),
    )

    @contextmanager
    def open_file(_relative_path):
        yield

    instance.open_file = open_file
    instance.server_started = True
    return instance, tmp_path.resolve()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response_kind",
    ("location", "link_without_origin", "link_with_origin", "null", "empty"),
)
async def test_definition_accepts_lsp_3_17_result_variants(server, response_kind):
    instance, root = server
    uri = (root / "example.py").as_uri()
    selection = {
        "start": {"line": 0, "character": 4},
        "end": {"line": 0, "character": 9},
    }
    variants = {
        "location": {"uri": uri, "range": selection},
        "link_without_origin": {
            "targetUri": uri,
            "targetRange": selection,
            "targetSelectionRange": selection,
        },
        "link_with_origin": {
            "originSelectionRange": selection,
            "targetUri": uri,
            "targetRange": selection,
            "targetSelectionRange": selection,
        },
    }
    response = (
        None
        if response_kind == "null"
        else []
        if response_kind == "empty"
        else [variants[response_kind]]
    )

    async def definition(_params):
        return response

    instance.server.send = SimpleNamespace(definition=definition)
    normalized = await instance.request_definition("example.py", 0, 5)
    if response_kind in ("null", "empty"):
        assert normalized == []
    else:
        assert len(normalized) == 1
        assert normalized[0]["relativePath"] == "example.py"
        assert normalized[0]["range"] == selection


@pytest.mark.asyncio
@pytest.mark.parametrize("response", (None, []))
async def test_references_support_null_or_empty_list(server, response):
    instance, _ = server

    async def references(_params):
        return response

    instance.server.send = SimpleNamespace(references=references)
    assert await instance.request_references("example.py", 0, 5) == []


@pytest.mark.asyncio
async def test_references_preserve_valid_locations(server):
    instance, root = server
    target = root / "example.py"
    span = {
        "start": {"line": 0, "character": 4},
        "end": {"line": 0, "character": 9},
    }

    async def references(_params):
        return [{"uri": target.as_uri(), "range": span}]

    instance.server.send = SimpleNamespace(references=references)
    normalized = await instance.request_references("example.py", 0, 5)
    assert len(normalized) == 1
    assert normalized[0]["relativePath"] == "example.py"
    assert normalized[0]["range"] == span
