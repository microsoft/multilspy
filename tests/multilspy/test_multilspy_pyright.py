"""Pyright language-server integration, following the other adapter tests.

Use a disposable local workspace instead of cloning a remote repository.
The integration tests require an explicit, preinstalled Pyright executable;
they skip rather than download/install when it is unavailable.
"""

import asyncio
import os
from pathlib import Path

import pytest

from multilspy import LanguageServer, SyncLanguageServer
from multilspy.language_servers.jedi_language_server.jedi_server import JediServer
from multilspy.language_servers.pyright_language_server.pyright_server import (
    PyrightServer,
)
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_exceptions import MultilspyException
from multilspy.multilspy_logger import MultilspyLogger


@pytest.fixture
def python_project(tmp_path):
    root = tmp_path.resolve()
    files = {
        "lib.py": ("def greet(name: str) -> str:\n    return name.upper()\n"),
        "app.py": (
            "from lib import greet\n\nfirst = greet('Ada')\nsecond = greet('Bob')\n"
        ),
        "worker.py": (
            "class Worker:\n"
            "    def process(self) -> int:\n"
            "        return 3\n\n"
            "worker = Worker()\n"
            "result = worker.process()\n"
        ),
        "invalid.py": ("def faulty(name: str) -> str:\n    return 123\n"),
    }
    for name, contents in files.items():
        (root / name).write_text(contents)
    (root / "pyrightconfig.json").write_text(
        '{"typeCheckingMode":"standard","include":["."]}\n'
    )
    return root


@pytest.fixture
def pyright_binary():
    provided = os.environ.get("MULTILSPY_PYRIGHT_TEST_BINARY")
    if not provided:
        pytest.skip("Set MULTILSPY_PYRIGHT_TEST_BINARY to a preinstalled executable")
    binary = Path(provided)
    if not binary.is_absolute() or not binary.is_file():
        pytest.skip("The explicit Pyright executable is unavailable")
    return str(binary)


@pytest.fixture
def create_pyright(python_project, pyright_binary):
    def create():
        return LanguageServer.create(
            MultilspyConfig(
                code_language=Language.PYTHON,
                python_server="pyright",
                server_binary=pyright_binary,
            ),
            MultilspyLogger(),
            str(python_project),
        )

    return create


@pytest.mark.parametrize(
    "backend, expected",
    [
        ("jedi", JediServer),
        ("pyright", PyrightServer),
    ],
)
def test_python_backend_selection_is_explicit(tmp_path, backend, expected):
    instance = LanguageServer.create(
        MultilspyConfig(
            code_language=Language.PYTHON,
            python_server=backend,
        ),
        MultilspyLogger(),
        str(tmp_path.resolve()),
    )
    assert isinstance(instance, expected)
    assert instance.server.process is None


def test_existing_jedi_default_and_explicit_server_command(tmp_path):
    root = str(tmp_path.resolve())
    default = LanguageServer.create(
        MultilspyConfig(code_language=Language.PYTHON),
        MultilspyLogger(),
        root,
    )
    assert isinstance(default, JediServer)
    pyright = LanguageServer.create(
        MultilspyConfig(
            code_language=Language.PYTHON,
            python_server="pyright",
            server_binary="/preinstalled/pyright-langserver",
        ),
        MultilspyLogger(),
        root,
    )
    assert pyright.server.process_launch_info.cmd == [
        "/preinstalled/pyright-langserver",
        "--stdio",
    ]
    assert pyright.server.process_launch_info.cwd == root
    assert pyright.server.process is None


def test_existing_positional_config_arguments_are_unchanged():
    config = MultilspyConfig(Language.PYTHON, True, False, None, None)
    assert config.trace_lsp_communication is True
    assert config.start_independent_lsp_process is False
    assert config.server_binary is None
    assert config.server_install_dir is None
    assert config.python_server == "jedi"


def test_pyright_selection_through_from_dict_and_sync_factory(tmp_path):
    config = MultilspyConfig.from_dict(
        {
            "code_language": Language.PYTHON,
            "python_server": "pyright",
            "server_binary": "/preinstalled/pyright-langserver",
        }
    )
    sync = SyncLanguageServer.create(
        config, MultilspyLogger(), str(tmp_path.resolve()), timeout=15
    )
    assert isinstance(sync.language_server, PyrightServer)
    assert sync.language_server.server.process is None


def test_invalid_python_backend_cannot_fall_back_to_jedi(tmp_path):
    config = MultilspyConfig(
        code_language=Language.PYTHON,
        python_server="unknown",
    )
    with pytest.raises(MultilspyException, match="Unsupported Python"):
        LanguageServer.create(config, MultilspyLogger(), str(tmp_path.resolve()))


@pytest.mark.asyncio
async def test_real_pyright_definition_references_hover_and_symbols(
    python_project,
    create_pyright,
):
    server = create_pyright()

    async def exercise():
        async with server.start_server():
            definition = await asyncio.wait_for(
                server.request_definition("app.py", 2, 9), timeout=8
            )
            assert len(definition) == 1
            assert definition[0]["relativePath"] == "lib.py"
            assert definition[0]["range"]["start"] == {"line": 0, "character": 4}

            references = await asyncio.wait_for(
                server.request_references("lib.py", 0, 5), timeout=8
            )
            assert len(references) >= 2
            assert all(item["relativePath"] == "app.py" for item in references)

            hover = await asyncio.wait_for(
                server.request_hover("app.py", 2, 10), timeout=8
            )
            assert hover and "contents" in hover

            symbols, _ = await asyncio.wait_for(
                server.request_document_symbols("lib.py"), timeout=8
            )
            assert "greet" in {entry["name"] for entry in symbols}

            workspace_symbols = []
            for _ in range(15):
                workspace_symbols = await asyncio.wait_for(
                    server.request_workspace_symbol("greet"), timeout=8
                )
                if workspace_symbols:
                    break
                await asyncio.sleep(0.1)
            assert any(item["name"] == "greet" for item in workspace_symbols)

    await asyncio.wait_for(exercise(), timeout=30)
    assert server.server.process is None


@pytest.mark.asyncio
async def test_real_pyright_high_level_completions_and_signature(
    python_project,
    create_pyright,
):
    server = create_pyright()

    async def exercise():
        async with server.start_server():
            # Use the same high-level API as the existing Jedi/Rust tests.
            suggestions = await asyncio.wait_for(
                server.request_completions("worker.py", 5, len("result = worker.")),
                timeout=8,
            )
            assert "process" in {item["completionText"] for item in suggestions}

            with server.open_file("app.py"):
                signature = await asyncio.wait_for(
                    server.server.send.signature_help(
                        {
                            "textDocument": {
                                "uri": (python_project / "app.py").as_uri()
                            },
                            "position": {"line": 2, "character": len("first = greet(")},
                        }
                    ),
                    timeout=8,
                )
            assert signature and signature["signatures"]
            assert "name: str" in signature["signatures"][0]["label"]

    await asyncio.wait_for(exercise(), timeout=30)
    assert server.server.process is None


@pytest.mark.asyncio
async def test_real_pyright_publishes_type_diagnostics_without_editing(
    python_project,
    create_pyright,
):
    server = create_pyright()
    source = python_project / "invalid.py"
    before = source.read_bytes()

    async def exercise():
        async with server.start_server():
            with server.open_file("invalid.py"):
                found = set()
                # Allow delayed cold starts: a short timeout is not a failure.
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 18
                while loop.time() < deadline:
                    try:
                        notification = await server.next_diagnostics(
                            timeout=min(2, max(0.01, deadline - loop.time()))
                        )
                    except asyncio.TimeoutError:
                        continue
                    if notification.get("uri") != source.as_uri():
                        continue
                    found.update(
                        entry.get("code")
                        for entry in notification.get("diagnostics", [])
                        if isinstance(entry, dict)
                    )
                    if "reportReturnType" in found:
                        break
                assert "reportReturnType" in found

    await asyncio.wait_for(exercise(), timeout=30)
    assert source.read_bytes() == before
    assert server.server.process is None


def test_real_pyright_sync_api_works_and_closes_provider(
    python_project,
    pyright_binary,
):
    sync = SyncLanguageServer.create(
        MultilspyConfig(
            code_language=Language.PYTHON,
            python_server="pyright",
            server_binary=pyright_binary,
        ),
        MultilspyLogger(),
        str(python_project),
        timeout=15,
    )
    with sync.start_server():
        definition = sync.request_definition("app.py", 2, 9)
        assert len(definition) == 1
        assert definition[0]["relativePath"] == "lib.py"
        completion = sync.request_completions("worker.py", 5, len("result = worker."))
        assert "process" in {item["completionText"] for item in completion}
    assert sync.language_server.server.process is None
    assert sync.loop.is_closed()
    assert not sync.loop_thread.is_alive()
