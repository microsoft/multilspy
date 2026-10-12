"""A self-contained C# workspace shared by the async and sync integration tests."""

from pathlib import Path
import shutil
import subprocess

import pytest


@pytest.fixture
def csharp_project(tmp_path):
    source = Path(__file__).parents[1] / "fixtures" / "csharp"
    project = tmp_path / "csharp"
    shutil.copytree(source, project)
    # OmniSharp disables automatic restore; produce the assets file explicitly.
    subprocess.run(
        ["dotnet", "restore", str(project / "Example.sln"), "--ignore-failed-sources"],
        check=True, capture_output=True, text=True, timeout=120,
    )
    return project


def assert_definition(result):
    assert len(result) == 1, result
    assert result[0]["relativePath"] == "Constants.cs"
    assert result[0]["range"] == {
        "start": {"line": 6, "character": 25},
        "end": {"line": 6, "character": 31},
    }


def assert_references(result):
    assert sorted(
        (item["relativePath"], item["range"]["start"]["line"],
         item["range"]["start"]["character"], item["range"]["end"]["character"])
        for item in result
    ) == [("Consumer.cs", 4, 46, 52), ("Consumer.cs", 5, 51, 57)]


def assert_completions(result):
    assert {item["completionText"] for item in result} == {"First", "Second"}
