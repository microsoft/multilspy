"""Pyright language-server integration, following the other adapter tests.

Use a disposable local workspace instead of cloning a remote repository.
The integration tests require an explicit, preinstalled Pyright executable;
they skip rather than download/install when it is unavailable.
"""

import asyncio
import json
import os
import re
import subprocess
from pathlib import Path

import pytest

from multilspy import LanguageServer, SyncLanguageServer
from multilspy.language_servers.jedi_language_server.jedi_server import JediServer
from multilspy.language_servers.pyright_language_server.pyright_server import (
    PyrightServer,
)
from multilspy.lsp_protocol_handler.lsp_types import ErrorCodes
from multilspy.lsp_protocol_handler.server import Error
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_exceptions import MultilspyException
from multilspy.multilspy_logger import MultilspyLogger

# The adapter and the expectations below were validated against this release.
TESTED_PYRIGHT_VERSION = (1, 1, 413)

# Server capabilities that pyright-langserver 1.1.413 advertises to this
# read-only client, and well-known ones it does not advertise.
ADVERTISED_CAPABILITIES = {
    "callHierarchyProvider",
    "codeActionProvider",
    "completionProvider",
    "declarationProvider",
    "definitionProvider",
    "documentHighlightProvider",
    "documentSymbolProvider",
    "executeCommandProvider",
    "hoverProvider",
    "referencesProvider",
    "renameProvider",
    "signatureHelpProvider",
    "textDocumentSync",
    "typeDefinitionProvider",
    "workspace",
    "workspaceSymbolProvider",
}
UNADVERTISED_CAPABILITIES = {
    "codeLensProvider",
    "diagnosticProvider",
    "documentFormattingProvider",
    "documentLinkProvider",
    "foldingRangeProvider",
    "implementationProvider",
    "inlayHintProvider",
    "selectionRangeProvider",
    "semanticTokensProvider",
}


def _range(start_line, start_character, end_line, end_character):
    return {
        "start": {"line": start_line, "character": start_character},
        "end": {"line": end_line, "character": end_character},
    }


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
        # The emoji is one code point but two UTF-16 code units; the second
        # `x` is at UTF-16 column 14 (code-point column 13).
        "emoji.py": ("x = '\U0001F600'; y = x\n"),
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


def test_real_pyright_binary_reports_tested_version(pyright_binary):
    # pyright-langserver has no --version flag; the sibling pyright CLI
    # installed by the same package reports the shared version.
    reported = []
    for candidate in (pyright_binary, str(Path(pyright_binary).with_name("pyright"))):
        if not Path(candidate).is_file():
            continue
        completed = subprocess.run(
            [candidate, "--version"], capture_output=True, text=True, timeout=30
        )
        match = re.search(r"pyright (\d+)\.(\d+)\.(\d+)", completed.stdout + completed.stderr)
        if completed.returncode == 0 and match:
            reported.append(tuple(int(part) for part in match.groups()))
    assert reported, "No executable next to the language server reports a Pyright version"
    assert all(version >= TESTED_PYRIGHT_VERSION for version in reported)


@pytest.mark.asyncio
async def test_real_pyright_advertised_capabilities_match_matrix(create_pyright):
    server = create_pyright()
    native_initialize = server.server.send.initialize
    captured = {}

    async def initialize(params):
        captured["result"] = await native_initialize(params)
        return captured["result"]

    server.server.send.initialize = initialize

    async def exercise():
        async with server.start_server():
            pass

    await asyncio.wait_for(exercise(), timeout=30)
    assert server.server.process is None
    capabilities = captured["result"]["capabilities"]
    assert ADVERTISED_CAPABILITIES <= set(capabilities)
    assert UNADVERTISED_CAPABILITIES.isdisjoint(capabilities)
    assert capabilities["textDocumentSync"] == 2
    assert capabilities["completionProvider"]["resolveProvider"] is True
    assert capabilities["completionProvider"]["triggerCharacters"] == [".", "[", '"', "'"]
    assert capabilities["signatureHelpProvider"]["triggerCharacters"] == ["(", ",", ")"]
    assert capabilities["renameProvider"]["prepareProvider"] is True
    assert capabilities["codeActionProvider"]["codeActionKinds"] == [
        "quickfix",
        "source.organizeImports",
    ]
    # Pyright registers no server commands for a client without applyEdit.
    assert capabilities["executeCommandProvider"]["commands"] == []


@pytest.mark.asyncio
async def test_real_pyright_read_only_requests_return_exact_shapes(
    python_project,
    create_pyright,
):
    """One server session covers the advertised read-only requests.

    Every expectation is the exact payload returned by Pyright 1.1.413 for the
    temporary project. Rename and code actions are proposals only: the files
    on disk are compared byte for byte afterwards.
    """
    server = create_pyright()
    before = {path: path.read_bytes() for path in python_project.glob("*.py")}

    def uri(name):
        return (python_project / name).as_uri()

    def at(name, line, character):
        return {
            "textDocument": {"uri": uri(name)},
            "position": {"line": line, "character": character},
        }

    greet_call_sites = [_range(2, 8, 2, 13), _range(3, 9, 3, 14)]
    corpus = [
        ("declaration", at("app.py", 2, 9), [{"uri": uri("lib.py"), "range": _range(0, 4, 0, 9)}]),
        ("type_definition", at("worker.py", 4, 0), [{"uri": uri("worker.py"), "range": _range(0, 6, 0, 12)}]),
        (
            "document_highlight",
            at("app.py", 2, 9),
            [
                {"kind": 3, "range": _range(0, 16, 0, 21)},
                {"kind": 2, "range": greet_call_sites[0]},
                {"kind": 2, "range": greet_call_sites[1]},
            ],
        ),
        ("prepare_rename", at("lib.py", 0, 5), _range(0, 4, 0, 9)),
        (
            "signature_help",
            at("app.py", 2, len("first = greet(")),
            {
                "activeParameter": 0,
                "activeSignature": 0,
                "signatures": [
                    {
                        "activeParameter": 0,
                        "label": "(name: str) -> str",
                        "parameters": [
                            {"documentation": {"kind": "plaintext", "value": ""}, "label": [1, 10]}
                        ],
                    }
                ],
            },
        ),
        (
            "prepare_call_hierarchy",
            at("lib.py", 0, 5),
            [
                {
                    "kind": 12,
                    "name": "greet",
                    "uri": uri("lib.py"),
                    "range": _range(0, 4, 0, 9),
                    "selectionRange": _range(0, 4, 0, 9),
                }
            ],
        ),
        # UTF-16 column 14 is the second `x`; a code-point column would miss it.
        ("definition", at("emoji.py", 0, 14), [{"uri": uri("emoji.py"), "range": _range(0, 0, 0, 1)}]),
        # Blank line: Pyright answers null, never an error.
        ("hover", at("app.py", 1, 0), None),
        ("definition", at("app.py", 1, 0), None),
        ("references", {**at("app.py", 1, 0), "context": {"includeDeclaration": True}}, None),
        (
            "code_action",
            {
                "textDocument": {"uri": uri("app.py")},
                "range": _range(0, 0, 0, 20),
                "context": {"diagnostics": []},
            },
            [],
        ),
    ]

    async def exercise():
        async with server.start_server():
            send = server.server.send
            with server.open_file("app.py"), server.open_file("lib.py"), server.open_file(
                "worker.py"
            ), server.open_file("emoji.py"):
                for method, params, expected in corpus:
                    result = await asyncio.wait_for(getattr(send, method)(params), timeout=8)
                    assert result == expected, method

                # The high-level API passes UTF-16 columns through unchanged.
                definition = await asyncio.wait_for(
                    server.request_definition("emoji.py", 0, 14), timeout=8
                )
                assert [(item["relativePath"], item["range"]) for item in definition] == [
                    ("emoji.py", _range(0, 0, 0, 1))
                ]
                assert await asyncio.wait_for(
                    server.request_hover("app.py", 1, 0), timeout=8
                ) is None
                assert await asyncio.wait_for(
                    server.request_references("app.py", 1, 0), timeout=8
                ) == []

                calls = await asyncio.wait_for(
                    send.incoming_calls(
                        {"item": (await send.prepare_call_hierarchy(at("lib.py", 0, 5)))[0]}
                    ),
                    timeout=8,
                )
                assert [(call["from"]["name"], call["from"]["uri"], call["fromRanges"]) for call in calls] == [
                    ("(module) app.py", uri("app.py"), greet_call_sites)
                ]

                # Rename is a WorkspaceEdit proposal; nothing is applied.
                proposal = await asyncio.wait_for(
                    send.rename({**at("lib.py", 0, 5), "newName": "salute"}), timeout=8
                )
                changes = sorted(proposal["documentChanges"], key=lambda change: change["textDocument"]["uri"])
                assert changes == [
                    {
                        "textDocument": {"uri": uri("app.py"), "version": None},
                        "edits": [
                            {"range": _range(0, 16, 0, 21), "newText": "salute"},
                            {"range": greet_call_sites[0], "newText": "salute"},
                            {"range": greet_call_sites[1], "newText": "salute"},
                        ],
                    },
                    {
                        "textDocument": {"uri": uri("lib.py"), "version": None},
                        "edits": [{"range": _range(0, 4, 0, 9), "newText": "salute"}],
                    },
                ]

                # completionItem/resolve adds documentation to a raw item.
                completion = await asyncio.wait_for(
                    send.completion({**at("worker.py", 5, len("result = worker.")), "context": {"triggerKind": 1}}),
                    timeout=8,
                )
                item = next(entry for entry in completion["items"] if entry["label"] == "process")
                resolved = await asyncio.wait_for(send.resolve_completion_item(item), timeout=8)
                assert resolved["documentation"] == {"kind": "plaintext", "value": "def process() -> int"}
                assert resolved["kind"] == 2

                # Unadvertised requests fail with MethodNotFound instead of hanging.
                with pytest.raises(Error) as unsupported:
                    await asyncio.wait_for(send.implementation(at("lib.py", 0, 5)), timeout=8)
                assert unsupported.value.code == ErrorCodes.MethodNotFound
                with pytest.raises(Error):
                    await asyncio.wait_for(
                        send.execute_command({"command": "pyright.doesNotExist", "arguments": []}),
                        timeout=8,
                    )

    await asyncio.wait_for(exercise(), timeout=60)
    assert server.server.process is None
    assert {path: path.read_bytes() for path in python_project.glob("*.py")} == before


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode, expected_codes",
    [
        ("off", set()),
        ("basic", {"reportReturnType"}),
        ("standard", {"reportReturnType"}),
        ("strict", {"reportReturnType"}),
    ],
)
async def test_real_pyright_type_checking_mode_controls_push_diagnostics(
    python_project,
    create_pyright,
    mode,
    expected_codes,
):
    (python_project / "pyrightconfig.json").write_text(
        json.dumps({"typeCheckingMode": mode, "include": ["."]})
    )
    server = create_pyright()
    source = python_project / "invalid.py"

    async def exercise():
        async with server.start_server():
            with server.open_file("invalid.py"):
                # Pyright publishes once per open file, also when the list is empty.
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 18
                while True:
                    notification = await server.next_diagnostics(
                        timeout=max(0.01, deadline - loop.time())
                    )
                    if notification["uri"] == source.as_uri():
                        return notification["diagnostics"]

    diagnostics = await asyncio.wait_for(exercise(), timeout=30)
    assert {entry["code"] for entry in diagnostics} == expected_codes
    assert all(entry["severity"] == 1 for entry in diagnostics)
    assert server.server.process is None
    assert not server.diagnostics_dropped
