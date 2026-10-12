"""Pinned Json.NET checkout shared by the async and sync OmniSharp tests."""

from pathlib import PurePath
import subprocess

import pytest

from multilspy.multilspy_types import CompletionItemKind


# Json.NET 13.0.3. Pin the commit so source positions and expected results are stable.
REPOSITORY = "https://github.com/JamesNK/Newtonsoft.Json.git"
COMMIT = "0a2e291c0d9c0c7675d445703e51750363a549ef"
SERIALIZER = str(PurePath("Newtonsoft.Json/JsonSerializer.cs"))
SETTINGS = str(PurePath("Newtonsoft.Json/JsonSerializerSettings.cs"))


@pytest.fixture
def csharp_project(tmp_path):
    project = tmp_path / "Newtonsoft.Json"

    def run(command, cwd=None):
        result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=180)
        assert result.returncode == 0, result.stdout + result.stderr
        return result.stdout.strip()

    run(["git", "clone", "--quiet", "--no-checkout", "--depth", "1", REPOSITORY, str(project)])
    run(["git", "fetch", "--quiet", "--depth", "1", "origin", COMMIT], cwd=project)
    run(["git", "checkout", "--quiet", "--detach", COMMIT], cwd=project)
    assert run(["git", "rev-parse", "HEAD"], cwd=project) == COMMIT

    # Use the upstream solution, projects, and global.json without rewriting them.
    # OmniSharp disables automatic restore, so prepare the project assets first.
    source = project / "Src"
    run(["dotnet", "restore", "Newtonsoft.Json.sln"], cwd=source)

    return source


def assert_definition(result):
    assert len(result) == 1, result
    assert result[0]["relativePath"] == SETTINGS, result
    assert result[0]["range"] == {
        "start": {"line": 53, "character": 43},
        "end": {"line": 53, "character": 69},
    }, result


def assert_references(result):
    locations = sorted(
        ((item["relativePath"], item["range"]) for item in result), key=lambda item: item[0]
    )
    assert locations == [
        (SERIALIZER, {
            "start": {"line": 562, "character": 58},
            "end": {"line": 562, "character": 84},
        }),
        (SETTINGS, {
            "start": {"line": 225, "character": 43},
            "end": {"line": 225, "character": 69},
        }),
    ], result


def assert_completions(result):
    assert {
        item["completionText"] for item in result if item["kind"] == CompletionItemKind.EnumMember
    } == {"Default", "AllowNonPublicDefaultConstructor"}, result
