"""Completion readiness regression tests using the real Jedi language server."""

import asyncio

import pytest

from multilspy import LanguageServer, SyncLanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


@pytest.fixture
def completion_project(tmp_path):
    (tmp_path / "example.py").write_text('message = "hello"\nmessage.\n')
    return tmp_path


@pytest.mark.asyncio
async def test_python_completions_after_initialization(completion_project):
    server = LanguageServer.create(
        MultilspyConfig(code_language=Language.PYTHON),
        MultilspyLogger(),
        str(completion_project),
    )
    async with server.start_server():
        completions = await asyncio.wait_for(
            server.request_completions("example.py", 1, 8), timeout=10
        )
        assert "upper" in {item["completionText"] for item in completions}


def test_sync_python_completions_after_initialization(completion_project):
    server = SyncLanguageServer.create(
        MultilspyConfig(code_language=Language.PYTHON),
        MultilspyLogger(),
        str(completion_project),
        timeout=10,
    )
    with server.start_server():
        completions = server.request_completions("example.py", 1, 8)
        assert "upper" in {item["completionText"] for item in completions}
