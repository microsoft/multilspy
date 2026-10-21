"""Pyright backend regression tests; real provider is opt-in through env.

No auto-install, project clone or network request in the default test suite.
"""

import asyncio
import os
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from multilspy.language_server import LanguageServer
from multilspy.language_servers.jedi_language_server.jedi_server import JediServer
from multilspy.language_servers.pyright_language_server.pyright_server import PyrightServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_exceptions import MultilspyException
from multilspy.multilspy_logger import MultilspyLogger


def _server(tmp_path: Path, *, backend: str = "pyright", executable=None):
    config = MultilspyConfig(
        code_language=Language.PYTHON, python_server=backend, server_binary=executable
    )
    return LanguageServer.create(config, MultilspyLogger(), str(tmp_path.resolve()))


def test_existing_python_users_still_get_jedi(tmp_path):
    lsp = LanguageServer.create(
        MultilspyConfig(code_language=Language.PYTHON),
        MultilspyLogger(),
        str(tmp_path),
    )
    assert isinstance(lsp, JediServer)


def test_explicit_pyright_factory_uses_stdio_without_downloading(tmp_path):
    executable = "/some/preinstalled/pyright-langserver"
    lsp = _server(tmp_path, executable=executable)
    assert isinstance(lsp, PyrightServer)
    assert lsp.language_id == "python"
    assert lsp.server.process_launch_info.cmd == [executable, "--stdio"]
    assert lsp.server.process_launch_info.cwd == str(tmp_path.resolve())
    assert lsp.server.process is None


def test_pyright_default_binary_is_an_existing_install_requirement(tmp_path):
    lsp = _server(tmp_path)
    assert lsp.server.process_launch_info.cmd == [
        "pyright-langserver",
        "--stdio",
    ]
    assert lsp.server.process is None


def test_unknown_python_backend_is_not_silently_jedi(tmp_path):
    with pytest.raises(MultilspyException, match="Unsupported Python"):
        _server(tmp_path, backend="invalid")


@pytest.mark.parametrize("kind", ["location", "link"])
def test_definition_accepts_location_and_optional_origin_link(tmp_path, kind):
    """LocationLink.originSelectionRange is optional in LSP 3.17."""
    lsp = _server(tmp_path)
    source = tmp_path / "example.py"
    source.write_text("def hello(): return 1\n")
    location = source.resolve().as_uri()
    span = {
        "start": {"line": 0, "character": 4},
        "end": {"line": 0, "character": 9},
    }
    response = (
        {"uri": location, "range": span}
        if kind == "location"
        else {
            "targetUri": location,
            "targetRange": span,
            "targetSelectionRange": span,
            # No originSelectionRange!
        }
    )

    @contextmanager
    def noop_open(_path: str):
        yield

    async def definition(_params):
        return [response]

    lsp.server_started = True
    lsp.open_file = noop_open
    lsp.server.send = SimpleNamespace(definition=definition)
    actual = asyncio.run(lsp.request_definition("example.py", 0, 5))
    assert len(actual) == 1
    assert actual[0]["relativePath"] == "example.py"
    assert actual[0]["range"] == span


def test_null_references_become_empty_list(tmp_path):
    lsp = _server(tmp_path)
    (tmp_path / "example.py").write_text("hello = 1\n")

    @contextmanager
    def noop_open(_path: str):
        yield

    async def references(_params):
        return None

    lsp.server_started = True
    lsp.open_file = noop_open
    lsp.server.send = SimpleNamespace(references=references)
    assert asyncio.run(lsp.request_references("example.py", 0, 2)) == []


def test_real_pyright_navigation_and_diagnostics(tmp_path):
    """Optional official Pyright LSP integration, no implicit install."""
    executable = os.environ.get("MULTILSPY_PYRIGHT_TEST_BINARY")
    if not executable:
        pytest.skip("Set MULTILSPY_PYRIGHT_TEST_BINARY to a trusted binary")
    binary = Path(executable)
    if not binary.is_absolute() or not binary.is_file():
        pytest.skip("Explicit Pyright binary not found")
    root = tmp_path.resolve()
    source = root / "sample.py"
    original = (
        "def say_hello(name: str) -> str:\n"
        "    return 123\n"
        "\n"
        "answer = say_hello('Ada')\n"
    )
    source.write_text(original)
    (root / "pyrightconfig.json").write_text('{"typeCheckingMode":"standard"}')
    lsp = _server(root, executable=str(binary))

    async def exercise():
        async with lsp.start_server():
            definition = await asyncio.wait_for(
                lsp.request_definition("sample.py", 3, 12), 8
            )
            assert len(definition) == 1
            assert definition[0]["relativePath"] == "sample.py"
            references = await asyncio.wait_for(
                lsp.request_references("sample.py", 0, 4), 8
            )
            assert isinstance(references, list)
            assert len(references) >= 1
            hover = await asyncio.wait_for(
                lsp.request_hover("sample.py", 3, 12), 8
            )
            assert hover is not None
            # A push diagnostic is asynchronous and can arrive after
            # an earlier empty didClose diagnostic for the same URI.
            while not lsp.diagnostics.empty():
                lsp.diagnostics.get_nowait()
            with lsp.open_file("sample.py"):
                observed = set()
                for _ in range(10):
                    message = await lsp.next_diagnostics(timeout=2)
                    if message.get("uri") != source.as_uri():
                        continue
                    observed.update(
                        item.get("code")
                        for item in message.get("diagnostics", [])
                        if isinstance(item, dict)
                    )
                    if "reportReturnType" in observed:
                        break
                assert "reportReturnType" in observed
    asyncio.run(asyncio.wait_for(exercise(), timeout=30))
    assert lsp.server.process is None
    assert source.read_text() == original
