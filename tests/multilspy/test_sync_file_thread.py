"""Synchronous file operations must share the request/transport event loop."""

import asyncio
from contextlib import contextmanager
import threading
from unittest.mock import Mock

import pytest

from multilspy import SyncLanguageServer
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_exceptions import MultilspyException
from multilspy.multilspy_logger import MultilspyLogger


class BufferServer(LanguageServer):
    """Use the base lifecycle without launching an external server."""


@pytest.fixture
def server(tmp_path):
    (tmp_path / "example.py").write_text("value = 1\n")
    underlying = BufferServer(
        MultilspyConfig(code_language=Language.PYTHON), MultilspyLogger(), str(tmp_path),
        ProcessLaunchInfo(cmd=["unused"], cwd=str(tmp_path)), "python",
    )
    wrapper = SyncLanguageServer(underlying, timeout=5)
    yield wrapper
    # Main does not close the event loop; keep the regression suite leak-free.
    if wrapper.loop is not None and not wrapper.loop.is_closed():
        wrapper.loop.close()


@pytest.mark.parametrize("body_error", [False, True])
def test_file_notifications_and_reads_share_server_thread(server, monkeypatch, body_error):
    underlying = server.language_server
    events = []
    reads = []
    for name in ("did_open_text_document", "did_change_text_document", "did_close_text_document"):
        monkeypatch.setattr(underlying.server.notify, name, Mock(
            side_effect=lambda params, name=name: events.append((name, params, threading.get_ident()))
        ))
    original_read = underlying.get_open_file_text

    def read(path):
        reads.append(threading.get_ident())
        return original_read(path)

    monkeypatch.setattr(underlying, "get_open_file_text", read)
    with server.start_server():
        async def thread_id():
            return threading.get_ident()

        expected_thread = asyncio.run_coroutine_threadsafe(thread_id(), server.loop).result(5)
        assert expected_thread != threading.get_ident()
        try:
            with server.open_file("example.py"):
                with server.open_file("example.py"):
                    assert server.insert_text_at_position("example.py", 0, 9, "0") == {"line": 0, "character": 10}
                    assert server.get_open_file_text("example.py") == "value = 10\n"
                    assert server.delete_text_between_positions(
                        "example.py", {"line": 0, "character": 9}, {"line": 0, "character": 10}
                    ) == "0"
                assert server.get_open_file_text("example.py") == "value = 1\n"
                if body_error:
                    raise ValueError("caller failed")
        except ValueError as exc:
            assert body_error and str(exc) == "caller failed"
        assert not underlying.open_file_buffers
    assert [event[0] for event in events] == [
        "did_open_text_document", "did_change_text_document", "did_change_text_document", "did_close_text_document"
    ]
    assert [event[1]["textDocument"]["version"] for event in events[:-1]] == [0, 1, 2]
    assert {event[2] for event in events} == {expected_thread}
    assert set(reads) == {expected_thread}


@pytest.mark.timeout(10)
def test_file_operations_can_run_from_server_loop(server, monkeypatch):
    for name in ("did_open_text_document", "did_close_text_document"):
        monkeypatch.setattr(server.language_server.server.notify, name, Mock())
    with server.start_server():
        async def use_file():
            with server.open_file("example.py"):
                return server.get_open_file_text("example.py")

        assert asyncio.run_coroutine_threadsafe(use_file(), server.loop).result(5) == "value = 1\n"


def test_open_file_preserves_context_exception_handling(server, monkeypatch):
    received = []

    @contextmanager
    def suppress(path):
        try:
            yield
        except ValueError as exc:
            received.append(str(exc))

    monkeypatch.setattr(server.language_server, "open_file", suppress)
    with server.start_server():
        with server.open_file("example.py"):
            raise ValueError("suppressed by underlying context")
    assert received == ["suppressed by underlying context"]


@pytest.mark.parametrize("operation", ["open", "insert", "delete", "read"])
def test_file_operations_require_running_server(server, operation):
    with pytest.raises(MultilspyException, match="Language Server not started"):
        if operation == "open":
            with server.open_file("example.py"):
                pass
        elif operation == "insert":
            server.insert_text_at_position("example.py", 0, 0, "x")
        elif operation == "delete":
            server.delete_text_between_positions("example.py", {"line": 0, "character": 0}, {"line": 0, "character": 1})
        else:
            server.get_open_file_text("example.py")
