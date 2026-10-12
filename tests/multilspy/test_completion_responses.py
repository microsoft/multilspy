"""Completion response handling without a language-server subprocess."""

from unittest.mock import AsyncMock, Mock

import pytest

from multilspy import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


ITEM = {"label": "example", "insertText": "example", "kind": 6}
EXPECTED = [{"completionText": "example", "kind": 6}]


@pytest.fixture
def server(tmp_path):
    (tmp_path / "example.py").write_text("example\n")
    server = LanguageServer.create(
        MultilspyConfig(code_language=Language.PYTHON), MultilspyLogger(), str(tmp_path)
    )
    server.server = Mock()
    server.server_started = True
    server.completions_available.set()
    return server


@pytest.mark.asyncio
@pytest.mark.parametrize("responses, expected", [
    ([None], []),
    ([[]], []),
    ([[ITEM]], EXPECTED),
    ([{"isIncomplete": False, "items": [ITEM]}], EXPECTED),
    ([{"isIncomplete": True, "items": []}, None], []),
    ([{"isIncomplete": True, "items": []}, {"isIncomplete": False, "items": [ITEM]}], EXPECTED),
])
async def test_completion_responses(server, responses, expected):
    # Fail immediately on an unexpected retry instead of letting a regression hang.
    server.server.send.completion = AsyncMock(side_effect=responses + [AssertionError("Unexpected retry")])
    result = await server.request_completions("example.py", 0, 0)
    assert result == expected
    assert server.server.send.completion.await_count == len(responses)
    assert not server.open_file_buffers
    server.server.notify.did_close_text_document.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("allow_incomplete", [False, True])
async def test_incomplete_completion_retries_are_bounded(server, allow_incomplete):
    server.server.send.completion = AsyncMock(return_value={"isIncomplete": True, "items": [ITEM]})
    result = await server.request_completions("example.py", 0, 0, allow_incomplete=allow_incomplete)
    assert result == (EXPECTED if allow_incomplete else [])
    assert server.server.send.completion.await_count == 30
    assert not server.open_file_buffers
