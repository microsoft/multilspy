"""OmniSharp must honor the SDK selected for the solution."""

import os
from pathlib import Path
import subprocess
from unittest.mock import Mock

import pytest

from multilspy.language_servers.omnisharp.omnisharp import OmniSharp
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_exceptions import MultilspyException
from multilspy.multilspy_logger import MultilspyLogger


@pytest.fixture
def create_server(tmp_path, monkeypatch):
    solution_dir = tmp_path / "Src"
    solution_dir.mkdir()
    (solution_dir / "Example.sln").touch()
    for key in list(os.environ):
        if key.lower() == "omnisharp_sdk__path":
            monkeypatch.delenv(key)
    monkeypatch.setattr(OmniSharp, "setupRuntimeDependencies", lambda *args: ("OmniSharp", "plugin.dll"))

    def create(custom=False):
        return OmniSharp(
            MultilspyConfig(code_language=Language.CSHARP, server_binary="custom" if custom else None),
            MultilspyLogger(), str(tmp_path),
        )
    return create, solution_dir


@pytest.mark.parametrize("version", ["6.0.428", "8.0.425"])
def test_project_sdk_is_passed_to_child_only(create_server, monkeypatch, version):
    create, solution_dir = create_server
    run = Mock(side_effect=[
        subprocess.CompletedProcess([], 0, version + "\n", ""),
        subprocess.CompletedProcess([], 0, f"{version} [/sdk root]\n10.0.401 [/sdk root]\n", ""),
    ])
    monkeypatch.setattr(subprocess, "run", run)
    server = create()
    assert server.server.process_launch_info.env == {
        "OMNISHARP_Sdk__Path": str(Path("/sdk root") / version)
    }
    assert "OMNISHARP_Sdk__Path" not in os.environ
    assert all(call.kwargs["cwd"] == str(solution_dir) for call in run.call_args_list)


@pytest.mark.parametrize("custom", [False, True])
def test_explicit_sdk_or_custom_server_is_respected(create_server, monkeypatch, custom):
    create, _ = create_server
    if not custom:
        monkeypatch.setenv("OMNISHARP_Sdk__Path", "/explicit/sdk")
    run = Mock(side_effect=AssertionError("Must not override explicit configuration"))
    monkeypatch.setattr(subprocess, "run", run)
    assert create(custom).server.process_launch_info.env == {}
    run.assert_not_called()


@pytest.mark.parametrize("failure", [
    FileNotFoundError("dotnet"),
    subprocess.CalledProcessError(1, ["dotnet", "--version"], stderr="SDK not found"),
    subprocess.TimeoutExpired(["dotnet", "--version"], 30),
])
def test_sdk_resolution_errors_are_actionable(create_server, monkeypatch, failure):
    create, _ = create_server
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=failure))
    with pytest.raises(MultilspyException, match="SDK"):
        create()


def test_missing_selected_sdk_fails_early(create_server, monkeypatch):
    create, _ = create_server
    monkeypatch.setattr(subprocess, "run", Mock(side_effect=[
        subprocess.CompletedProcess([], 0, "6.0.428\n", ""),
        subprocess.CompletedProcess([], 0, "8.0.425 [/sdk]\n", ""),
    ]))
    with pytest.raises(MultilspyException, match="6.0.428"):
        create()


def test_incompatible_sdk_fails_before_server_launch(create_server, monkeypatch):
    create, _ = create_server
    monkeypatch.setattr(subprocess, "run", Mock(return_value=
        subprocess.CompletedProcess([], 0, "10.0.401\n", "")))
    with pytest.raises(MultilspyException, match="global.json"):
        create()
