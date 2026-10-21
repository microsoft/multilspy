"""Pyright language-server integration, following the other adapter tests.

Use a disposable local workspace instead of cloning a remote repository.
The integration tests require an explicit, preinstalled Pyright executable;
they skip rather than download/install when it is unavailable.

Every expected payload below is the exact response of pyright-langserver
1.1.413 for the temporary project. Rename, code actions and commands are
proposals only: the workspace files are compared byte for byte afterwards.
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

# The adapter, the capability matrix and every exact payload in this module
# were captured against this Pyright release.
TESTED_PYRIGHT_VERSION = (1, 1, 413)

# Server capabilities that pyright-langserver 1.1.413 advertises to multilspy's
# read-only client. Everything else (implementationProvider, diagnosticProvider
# for pull diagnostics, semantic tokens, inlay hints, folding, formatting, ...)
# is not advertised and such requests fail with MethodNotFound.
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

SHAPES_SOURCE = (
    "from dataclasses import dataclass\n"
    "\n"
    "\n"
    "@dataclass\n"
    "class Point:\n"
    "    x: float\n"
    "    y: float\n"
    "\n"
    "\n"
    "class Shape:\n"
    "    def area(self) -> float:\n"
    "        raise NotImplementedError\n"
    "\n"
    "    def describe(self) -> str:\n"
    "        return f\"{type(self).__name__}: {self.area():.1f}\"\n"
    "\n"
    "\n"
    "class Square(Shape):\n"
    "    def __init__(self, side: float) -> None:\n"
    "        self.side = side\n"
    "\n"
    "    def area(self) -> float:\n"
    "        return self.side * self.side\n"
    "\n"
    "\n"
    "def total_area(shapes: list[Shape]) -> float:\n"
    "    return sum(shape.area() for shape in shapes)\n"
)

REPORT_SOURCE = (
    "import sys\n"
    "import os\n"
    "from shapes import Point, Square, total_area\n"
    "\n"
    "origin = Point(0.0, 0.0)\n"
    "squares = [Square(2.0), Square(side=3.0)]\n"
    "summary = total_area(squares)\n"
    "label = squares[0].describe()\n"
)


def _range(start_line, start_character, end_line, end_character):
    return {
        "start": {"line": start_line, "character": start_character},
        "end": {"line": end_line, "character": end_character},
    }


def _pyright_version(language_server_binary):
    """Return the Pyright version tuple for a pyright-langserver executable.

    pyright-langserver has no --version flag. The npm and PyPI packages install
    a sibling `pyright` CLI that reports the shared version; the npm package
    also carries the version in its package.json next to the resolved script.
    """
    binary = Path(language_server_binary)
    for name in ("pyright", "pyright.cmd", "pyright.exe"):
        sibling = binary.with_name(name)
        if sibling.is_file():
            completed = subprocess.run(
                [str(sibling), "--version"], capture_output=True, text=True, timeout=60, check=False
            )
            match = re.search(r"pyright (\d+)\.(\d+)\.(\d+)", completed.stdout + completed.stderr)
            if completed.returncode == 0 and match:
                return tuple(int(part) for part in match.groups())
    package_json = binary.resolve().parent / "package.json"
    if package_json.is_file():
        version = json.loads(package_json.read_text(encoding="utf-8")).get("version", "")
        match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
        if match:
            return tuple(int(part) for part in match.groups())
    return None


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
        "shapes.py": SHAPES_SOURCE,
        "report.py": REPORT_SOURCE,
    }
    for name, contents in files.items():
        (root / name).write_text(contents, encoding="utf-8")
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
        pytest.fail("MULTILSPY_PYRIGHT_TEST_BINARY must be an existing absolute file")
    if os.name != "nt" and not os.access(binary, os.X_OK):
        pytest.fail("MULTILSPY_PYRIGHT_TEST_BINARY must be executable")
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


def test_real_pyright_binary_is_the_tested_version(pyright_binary):
    version = _pyright_version(pyright_binary)
    assert version is not None, "Cannot determine the Pyright version next to the language server"
    # The exact payloads in this module belong to one release. To validate a
    # newer Pyright, re-capture the expectations and bump TESTED_PYRIGHT_VERSION.
    assert version == TESTED_PYRIGHT_VERSION


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
    assert set(capabilities) == ADVERTISED_CAPABILITIES
    assert capabilities["textDocumentSync"] == 2
    assert capabilities["completionProvider"] == {
        "triggerCharacters": [".", "[", '"', "'"],
        "resolveProvider": True,
        "completionItem": {"labelDetailsSupport": True},
        "workDoneProgress": True,
    }
    assert capabilities["signatureHelpProvider"]["triggerCharacters"] == ["(", ",", ")"]
    assert capabilities["renameProvider"]["prepareProvider"] is True
    assert capabilities["codeActionProvider"]["codeActionKinds"] == [
        "quickfix",
        "source.organizeImports",
    ]
    # Pyright registers no server commands for this client; its commands still
    # execute by name (see test_real_pyright_commands_cannot_edit_the_workspace).
    assert capabilities["executeCommandProvider"]["commands"] == []
    assert capabilities["callHierarchyProvider"] is True
    assert capabilities["workspace"] == {
        "workspaceFolders": {"supported": True, "changeNotifications": True}
    }


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
            assert definition[0]["range"] == _range(0, 4, 0, 9)

            # Keep the import and definition open to avoid relying on when
            # background workspace indexing completes on a cold runner.
            with server.open_file("app.py"), server.open_file("lib.py"):
                references = await asyncio.wait_for(
                    server.request_references("lib.py", 0, 5), timeout=8
                )
            assert [(item["relativePath"], item["range"]) for item in references] == [
                ("app.py", _range(0, 16, 0, 21)),
                ("app.py", _range(2, 8, 2, 13)),
                ("app.py", _range(3, 9, 3, 14)),
            ]

            hover = await asyncio.wait_for(
                server.request_hover("app.py", 2, 10), timeout=8
            )
            assert hover == {
                "contents": {
                    "kind": "markdown",
                    "value": "```python\n(function) def greet(name: str) -> str\n```",
                },
                "range": _range(2, 8, 2, 13),
            }

            symbols, tree = await asyncio.wait_for(
                server.request_document_symbols("lib.py"), timeout=8
            )
            assert tree is None
            assert [(entry["name"], entry["kind"]) for entry in symbols] == [
                ("greet", 12),
                ("name", 13),
            ]

            workspace_symbols = []
            for _ in range(15):
                workspace_symbols = await asyncio.wait_for(
                    server.request_workspace_symbol("greet"), timeout=8
                )
                if workspace_symbols:
                    break
                await asyncio.sleep(0.1)
            assert workspace_symbols == [
                {
                    "name": "greet",
                    "kind": 12,
                    "location": {
                        "uri": (python_project / "lib.py").as_uri(),
                        "range": _range(0, 4, 0, 9),
                    },
                }
            ]

    await asyncio.wait_for(exercise(), timeout=30)
    assert server.server.process is None


@pytest.mark.asyncio
async def test_real_pyright_high_level_api_on_classes_across_files(
    python_project,
    create_pyright,
):
    """Inheritance, overrides, keyword arguments and cross-file references."""
    server = create_pyright()

    async def exercise():
        async with server.start_server():
            # shape.area() inside total_area resolves to the base method.
            definition = await asyncio.wait_for(
                server.request_definition("shapes.py", 26, 22), timeout=8
            )
            assert [(item["relativePath"], item["range"]) for item in definition] == [
                ("shapes.py", _range(10, 8, 10, 12))
            ]

            # Square used through a keyword-argument constructor call.
            definition = await asyncio.wait_for(
                server.request_definition("report.py", 5, 26), timeout=8
            )
            assert [(item["relativePath"], item["range"]) for item in definition] == [
                ("shapes.py", _range(17, 6, 17, 12))
            ]

            # References exclude the declaration (multilspy sends includeDeclaration=false).
            with server.open_file("shapes.py"), server.open_file("report.py"):
                references = await asyncio.wait_for(
                    server.request_references("shapes.py", 17, 6), timeout=8
                )
            assert [(item["relativePath"], item["range"]) for item in references] == [
                ("report.py", _range(2, 26, 2, 32)),
                ("report.py", _range(5, 11, 5, 17)),
                ("report.py", _range(5, 24, 5, 30)),
            ]
            # References to the base method do not include the override.
            references = await asyncio.wait_for(
                server.request_references("shapes.py", 10, 8), timeout=8
            )
            assert [(item["relativePath"], item["range"]) for item in references] == [
                ("shapes.py", _range(14, 46, 14, 50)),
                ("shapes.py", _range(26, 21, 26, 25)),
            ]

            hover = await asyncio.wait_for(
                server.request_hover("report.py", 6, 10), timeout=8
            )
            assert hover == {
                "contents": {
                    "kind": "markdown",
                    "value": "```python\n(function) def total_area(shapes: list[Shape]) -> float\n```",
                },
                "range": _range(6, 10, 6, 20),
            }
            hover = await asyncio.wait_for(
                server.request_hover("report.py", 5, 12), timeout=8
            )
            assert hover["contents"]["value"] == "```python\nclass Square(side: float)\n```"

            symbols, _ = await asyncio.wait_for(
                server.request_document_symbols("shapes.py"), timeout=8
            )
            assert [(entry["name"], entry["kind"]) for entry in symbols] == [
                ("Point", 5),
                ("x", 13),
                ("y", 13),
                ("Shape", 5),
                ("area", 6),
                ("describe", 6),
                ("Square", 5),
                ("__init__", 6),
                ("side", 13),
                ("area", 6),
                ("side", 13),
                ("total_area", 12),
                ("shapes", 13),
            ]

            workspace_symbols = await asyncio.wait_for(
                server.request_workspace_symbol("Square"), timeout=8
            )
            assert {
                "name": "Square",
                "kind": 5,
                "location": {
                    "uri": (python_project / "shapes.py").as_uri(),
                    "range": _range(17, 6, 17, 12),
                },
            } in workspace_symbols

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

            # Pyright answers member completions with isIncomplete=true first;
            # the high-level API retries with TriggerForIncompleteCompletions.
            suggestions = await asyncio.wait_for(
                server.request_completions("report.py", 7, len("label = squares[0].")),
                timeout=8,
            )
            by_name = {item["completionText"]: item["kind"] for item in suggestions}
            assert by_name["describe"] == 2
            assert by_name["area"] == 2
            assert by_name["side"] == 6

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
            assert signature == {
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
            }

    await asyncio.wait_for(exercise(), timeout=30)
    assert server.server.process is None


@pytest.mark.asyncio
async def test_real_pyright_read_only_requests_return_exact_shapes(
    python_project,
    create_pyright,
):
    """One server session covers the advertised requests without a high-level API."""
    server = create_pyright()
    before = {path: path.read_bytes() for path in python_project.glob("*.py")}

    def uri(name):
        return (python_project / name).as_uri()

    def at(name, line, character):
        return {
            "textDocument": {"uri": uri(name)},
            "position": {"line": line, "character": character},
        }

    square_uses = [_range(2, 26, 2, 32), _range(5, 11, 5, 17), _range(5, 24, 5, 30)]
    corpus = [
        ("declaration", at("report.py", 2, 26), [{"uri": uri("shapes.py"), "range": _range(17, 6, 17, 12)}]),
        ("type_definition", at("report.py", 4, 0), [{"uri": uri("shapes.py"), "range": _range(4, 6, 4, 11)}]),
        (
            "document_highlight",
            at("shapes.py", 19, 13),
            [
                {"kind": 3, "range": _range(19, 13, 19, 17)},
                {"kind": 2, "range": _range(22, 20, 22, 24)},
                {"kind": 2, "range": _range(22, 32, 22, 36)},
            ],
        ),
        ("prepare_rename", at("shapes.py", 17, 6), _range(17, 6, 17, 12)),
        (
            "signature_help",
            at("report.py", 5, len("squares = [Square(2.0), Square(")),
            {
                "activeParameter": 0,
                "activeSignature": 0,
                "signatures": [
                    {
                        "activeParameter": 0,
                        "label": "(side: float) -> Square",
                        "parameters": [
                            {"documentation": {"kind": "plaintext", "value": ""}, "label": [1, 12]}
                        ],
                    }
                ],
            },
        ),
        (
            "prepare_call_hierarchy",
            at("shapes.py", 25, 4),
            [
                {
                    "kind": 12,
                    "name": "total_area",
                    "uri": uri("shapes.py"),
                    "range": _range(25, 4, 25, 14),
                    "selectionRange": _range(25, 4, 25, 14),
                }
            ],
        ),
        # UTF-16 column 14 is the second `x`; a code-point column would miss it.
        ("definition", at("emoji.py", 0, 14), [{"uri": uri("emoji.py"), "range": _range(0, 0, 0, 1)}]),
        ("hover", at("emoji.py", 0, 10), {
            "contents": {"kind": "markdown", "value": "```python\n(variable) y: Literal['\U0001F600']\n```"},
            "range": _range(0, 10, 0, 11),
        }),
        # Blank line and unknown file: Pyright answers null, never an error.
        ("hover", at("app.py", 1, 0), None),
        ("definition", at("app.py", 1, 0), None),
        ("references", {**at("app.py", 1, 0), "context": {"includeDeclaration": True}}, None),
        ("hover", at("missing.py", 0, 0), None),
        ("definition", at("missing.py", 0, 0), None),
        (
            "code_action",
            {
                "textDocument": {"uri": uri("report.py")},
                "range": _range(0, 0, 2, 44),
                "context": {"diagnostics": []},
            },
            [],
        ),
        (
            "code_action",
            {
                "textDocument": {"uri": uri("report.py")},
                "range": _range(0, 0, 2, 44),
                "context": {"diagnostics": [], "only": ["source.organizeImports"]},
            },
            [],
        ),
    ]

    async def exercise():
        async with server.start_server():
            send = server.server.send
            with server.open_file("app.py"), server.open_file("emoji.py"), server.open_file(
                "shapes.py"
            ), server.open_file("report.py"):
                for method, params, expected in corpus:
                    result = await asyncio.wait_for(getattr(send, method)(params), timeout=8)
                    assert result == expected, (method, params.get("position", params))

                # The high-level API passes UTF-16 columns through unchanged.
                definition = await asyncio.wait_for(
                    server.request_definition("emoji.py", 0, 14), timeout=8
                )
                assert [(item["relativePath"], item["range"]) for item in definition] == [
                    ("emoji.py", _range(0, 0, 0, 1))
                ]
                assert await asyncio.wait_for(server.request_hover("app.py", 1, 0), timeout=8) is None
                assert await asyncio.wait_for(server.request_references("app.py", 1, 0), timeout=8) == []

                # Call hierarchy: incoming from the report module, outgoing to
                # Shape.area in the workspace and to typeshed's sum overloads.
                item = (await asyncio.wait_for(send.prepare_call_hierarchy(at("shapes.py", 25, 4)), timeout=8))[0]
                incoming = await asyncio.wait_for(send.incoming_calls({"item": item}), timeout=8)
                assert incoming == [
                    {
                        "from": {
                            "kind": 2,
                            "name": "(module) report.py",
                            "uri": uri("report.py"),
                            "range": _range(0, 0, 0, 0),
                            "selectionRange": _range(0, 0, 0, 0),
                        },
                        "fromRanges": [_range(6, 10, 6, 20)],
                    }
                ]
                outgoing = await asyncio.wait_for(send.outgoing_calls({"item": item}), timeout=8)
                workspace_calls = [call for call in outgoing if call["to"]["uri"] == uri("shapes.py")]
                assert workspace_calls == [
                    {
                        "to": {
                            "kind": 6,
                            "name": "area",
                            "uri": uri("shapes.py"),
                            "range": _range(10, 8, 10, 12),
                            "selectionRange": _range(10, 8, 10, 12),
                        },
                        "fromRanges": [_range(26, 21, 26, 25)],
                    }
                ]
                builtin_calls = [call for call in outgoing if call not in workspace_calls]
                assert builtin_calls
                for call in builtin_calls:
                    assert call["to"]["name"] == "sum"
                    assert call["to"]["uri"].endswith("/stdlib/builtins.pyi")
                    assert call["fromRanges"] == [_range(26, 11, 26, 14)]

                # Rename is a WorkspaceEdit proposal; nothing is applied.
                proposal = await asyncio.wait_for(
                    send.rename({**at("shapes.py", 17, 6), "newName": "Box"}), timeout=8
                )
                changes = sorted(proposal["documentChanges"], key=lambda change: change["textDocument"]["uri"])
                assert changes == [
                    {
                        "textDocument": {"uri": uri("report.py"), "version": None},
                        "edits": [{"range": span, "newText": "Box"} for span in square_uses],
                    },
                    {
                        "textDocument": {"uri": uri("shapes.py"), "version": None},
                        "edits": [{"range": _range(17, 6, 17, 12), "newText": "Box"}],
                    },
                ]

                # completionItem/resolve adds documentation to a raw item.
                completion = await asyncio.wait_for(
                    send.completion({**at("report.py", 7, len("label = squares[0].")), "context": {"triggerKind": 1}}),
                    timeout=8,
                )
                raw = next(entry for entry in completion["items"] if entry["label"] == "describe")
                resolved = await asyncio.wait_for(send.resolve_completion_item(raw), timeout=8)
                assert resolved["documentation"] == {"kind": "plaintext", "value": "def describe() -> str"}
                assert resolved["kind"] == 2
                assert resolved["label"] == "describe"

                # Unadvertised requests fail with MethodNotFound instead of hanging.
                with pytest.raises(Error) as unsupported:
                    await asyncio.wait_for(send.implementation(at("shapes.py", 10, 8)), timeout=8)
                assert unsupported.value.code == ErrorCodes.MethodNotFound

    await asyncio.wait_for(exercise(), timeout=60)
    assert server.server.process is None
    assert {path: path.read_bytes() for path in python_project.glob("*.py")} == before


@pytest.mark.asyncio
async def test_real_pyright_commands_cannot_edit_the_workspace(
    python_project,
    create_pyright,
):
    """workspace/executeCommand is reachable but never changes files.

    Pyright's organize-imports command is disabled by the adapter configuration
    and returns an empty result. When a client enables it, Pyright answers with
    a WorkspaceEdit proposal and asks the client to apply it; the adapter
    refuses that reverse request, so the workspace stays unchanged.
    """
    server = create_pyright()
    report = python_project / "report.py"
    before = report.read_bytes()
    apply_requests = []

    async def exercise():
        async with server.start_server():
            send = server.server.send
            handlers = server.server.on_request_handlers
            refuse_edit = handlers["workspace/applyEdit"]

            async def record_apply_edit(params):
                result = await refuse_edit(params)
                apply_requests.append((params, result))
                return result

            handlers["workspace/applyEdit"] = record_apply_edit
            command = {"command": "pyright.organizeimports", "arguments": [report.as_uri()]}

            with server.open_file("report.py"):
                assert await asyncio.wait_for(send.execute_command(command), timeout=8) == []
                with pytest.raises(Error):
                    await asyncio.wait_for(
                        send.execute_command({"command": "pyright.doesNotExist", "arguments": []}),
                        timeout=8,
                    )

                # Opt in to organize imports and let Pyright re-read its settings.
                adapter_configuration = handlers["workspace/configuration"]

                async def permissive_configuration(params):
                    answers = await adapter_configuration(params)
                    for item, answer in zip(params["items"], answers):
                        if item.get("section") == "pyright":
                            answer["disableOrganizeImports"] = False
                    return answers

                handlers["workspace/configuration"] = permissive_configuration
                server.server.notify.workspace_did_change_configuration({"settings": {}})
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 10
                proposal = []
                while not proposal and loop.time() < deadline:
                    await asyncio.sleep(0.1)
                    proposal = await asyncio.wait_for(send.execute_command(command), timeout=8)
                assert proposal == {
                    "changes": {
                        report.as_uri(): [
                            {
                                "range": _range(0, 0, 2, 44),
                                "newText": "import os\nimport sys\n\nfrom shapes import Point, Square, total_area",
                            }
                        ]
                    }
                }
                for _ in range(50):
                    if apply_requests:
                        break
                    await asyncio.sleep(0.1)
            assert [result for _, result in apply_requests] == [
                {"applied": False, "failureReason": "multilspy Pyright client is read-only"}
            ]
            assert apply_requests[0][0]["edit"] == proposal

    await asyncio.wait_for(exercise(), timeout=60)
    assert server.server.process is None
    assert report.read_bytes() == before


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
                # Pyright can publish an initial empty snapshot and then a
                # complete analysis. Observe until the expected diagnostic
                # state appears, with an explicit finite deadline.
                loop = asyncio.get_running_loop()
                deadline = loop.time() + 18
                observed = None
                while loop.time() < deadline:
                    try:
                        notification = await server.next_diagnostics(
                            timeout=min(2, max(0.01, deadline - loop.time()))
                        )
                    except asyncio.TimeoutError:
                        continue
                    if notification.get("uri") != source.as_uri():
                        continue
                    observed = notification.get("diagnostics", [])
                    if {item.get("code") for item in observed} == expected_codes:
                        return observed
                pytest.fail(f"Expected diagnostics {expected_codes!r}; last received: {observed!r}")

    diagnostics = await asyncio.wait_for(exercise(), timeout=30)
    assert {entry["code"] for entry in diagnostics} == expected_codes
    assert all(entry["severity"] == 1 for entry in diagnostics)
    assert all(entry["range"] == _range(1, 11, 1, 14) for entry in diagnostics)
    assert server.server.process is None
    assert not server.diagnostics_dropped


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
        # Cross-file references require the target module to be indexed.
        # Keep both files open instead of relying on OS-dependent background
        # workspace discovery timing.
        with sync.open_file("shapes.py"), sync.open_file("report.py"):
            references = sync.request_references("shapes.py", 17, 6)
            assert [item["relativePath"] for item in references] == ["report.py"] * 3
        hover = sync.request_hover("report.py", 6, 10)
        assert hover["range"] == _range(6, 10, 6, 20)
        symbols, _ = sync.request_document_symbols("shapes.py")
        assert "total_area" in {entry["name"] for entry in symbols}
        assert sync.request_hover("app.py", 1, 0) is None
    assert sync.language_server.server.process is None
    assert sync.loop.is_closed()
    assert not sync.loop_thread.is_alive()


def test_invalid_explicit_pyright_binary_fails_instead_of_skipping(
    request, monkeypatch, tmp_path
):
    # A broken CI installation or an incorrectly set env var must fail visibly,
    # not turn all real Pyright tests green by skipping them.
    monkeypatch.setenv("MULTILSPY_PYRIGHT_TEST_BINARY", str(tmp_path / "not-installed"))
    with pytest.raises(pytest.fail.Exception, match="existing absolute file"):
        request.getfixturevalue("pyright_binary")


@pytest.mark.asyncio
async def test_real_pyright_unicode_workspace_and_restart(tmp_path, pyright_binary):
    # Spaces, non-ASCII names and non-BMP characters must survive URI encoding
    # and reuse of a LanguageServer instance must not replay old notifications.
    root = tmp_path / "Python project 中文 🐍"
    root.mkdir()
    (root / "functions.py").write_text(
        "def greet(name: str) -> str:\n    return name.upper()\n", encoding="utf-8"
    )
    (root / "caller.py").write_text(
        "from functions import greet\nresult = greet('Ada')\n", encoding="utf-8"
    )
    server = LanguageServer.create(
        MultilspyConfig(
            code_language=Language.PYTHON,
            python_server="pyright",
            server_binary=pyright_binary,
        ),
        MultilspyLogger(),
        str(root),
    )
    params = server._get_initialize_params(str(root))
    assert params["rootUri"] == root.as_uri()
    assert params["workspaceFolders"][0]["uri"] == root.as_uri()

    for attempt in range(2):
        previous_queue = server.diagnostics
        if attempt:
            previous_queue.put_nowait({"uri": "file:///old-session.py"})
            server.diagnostics_dropped = True
        async with server.start_server():
            assert server.diagnostics is not previous_queue
            assert not server.diagnostics_dropped
            definition = await asyncio.wait_for(
                server.request_definition("caller.py", 1, 10), timeout=8
            )
            assert [(item["relativePath"], item["range"]) for item in definition] == [
                ("functions.py", _range(0, 4, 0, 9))
            ]
        assert server.server.process is None
        assert not server.server_started


@pytest.mark.asyncio
async def test_real_pyright_incremental_edits_use_utf16_columns(
    python_project, create_pyright
):
    """Local buffer and Pyright must agree on didChange after an astral symbol."""
    source = python_project / "emoji.py"
    original = source.read_bytes()
    server = create_pyright()
    async with server.start_server():
        with server.open_file("emoji.py"):
            before = await asyncio.wait_for(server.request_definition("emoji.py", 0, 14), 8)
            assert [(item["relativePath"], item["range"]) for item in before] == [
                ("emoji.py", _range(0, 0, 0, 1))
            ]
            # `x` after the emoji starts at UTF-16 column 14, not codepoint 13.
            cursor = server.insert_text_at_position("emoji.py", 0, 14, "missing_")
            assert cursor == {"line": 0, "character": 22}
            assert server.get_open_file_text("emoji.py") == "x = '😀'; y = missing_x\n"
            for _ in range(20):
                changed = await asyncio.wait_for(
                    server.request_definition("emoji.py", 0, 18), timeout=8
                )
                if not changed:
                    break
                await asyncio.sleep(0.1)
            assert changed == []

            assert server.delete_text_between_positions(
                "emoji.py", {"line": 0, "character": 14},
                {"line": 0, "character": 22},
            ) == "missing_"
            assert server.get_open_file_text("emoji.py").encode("utf-8") == original
            for _ in range(20):
                restored = await asyncio.wait_for(
                    server.request_definition("emoji.py", 0, 14), timeout=8
                )
                if restored:
                    break
                await asyncio.sleep(0.1)
            assert [(item["relativePath"], item["range"]) for item in restored] == [
                ("emoji.py", _range(0, 0, 0, 1))
            ]
    assert source.read_bytes() == original
    assert server.server.process is None


@pytest.mark.parametrize("extension", ["", ".cmd", ".exe"])
def test_pyright_version_resolves_platform_specific_cli_wrappers(
    tmp_path, monkeypatch, extension
):
    binary = tmp_path / "pyright-langserver"
    binary.write_text("fake", encoding="utf-8")
    sibling = tmp_path / ("pyright" + extension)
    sibling.write_text("fake", encoding="utf-8")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(argv, 0, stdout="pyright 1.1.413\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert _pyright_version(binary) == TESTED_PYRIGHT_VERSION
    assert calls[0][0] == [str(sibling), "--version"]
    assert calls[0][1]["timeout"] == 60
