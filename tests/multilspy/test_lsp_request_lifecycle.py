"""JSON-RPC pending request lifecycle across all language server adapters.

This is shared multilspy behavior, not Pyright-specific. No external LSP
binary or network required for the unit cases; real subprocess EOF is tested.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, Mock

import pytest

from multilspy.lsp_protocol_handler.lsp_types import ErrorCodes
from multilspy.lsp_protocol_handler.server import Error, LanguageServerHandler, ProcessLaunchInfo


@pytest.fixture
def handler(tmp_path):
    client = LanguageServerHandler(ProcessLaunchInfo(cmd=[sys.executable], cwd=str(tmp_path)))
    client._send_payload = AsyncMock()
    client._send_payload_sync = Mock()
    return client


async def wait_for_pending(handler, n):
    async def wait_for_count():
        while len(handler._response_handlers) != n:
            await asyncio.sleep(0)
        return list(handler._response_handlers)

    return await asyncio.wait_for(wait_for_count(), 2)


@pytest.mark.asyncio
async def test_response_race_before_wait_starts(handler):
    async def fast_peer(payload):
        # A response may be scheduled while request bytes are still draining.
        asyncio.create_task(handler._response_handler({"id": payload["id"], "result": "ready"}))
        await asyncio.sleep(0)

    handler._send_payload.side_effect = fast_peer
    assert await asyncio.wait_for(handler.send_request("example", {"x": 1}), 2) == "ready"
    assert handler._response_handlers == {}


@pytest.mark.asyncio
async def test_null_result_unblocks_waiter(handler):
    task = asyncio.create_task(handler.send_request("textDocument/references", {}))
    (identifier,) = await wait_for_pending(handler, 1)
    await handler._response_handler({"id": identifier, "result": None})
    assert await asyncio.wait_for(task, 2) is None
    assert not handler._response_handlers


@pytest.mark.asyncio
async def test_lsp_error_unblocks_waiter_and_cleans_map(handler):
    task = asyncio.create_task(handler.send_request("bad", {}))
    (identifier,) = await wait_for_pending(handler, 1)
    await handler._response_handler({"id": identifier, "error": {
        "code": ErrorCodes.MethodNotFound, "message": "not here"
    }})
    with pytest.raises(Error) as exc:
        await asyncio.wait_for(task, 2)
    assert exc.value.code == ErrorCodes.MethodNotFound
    assert not handler._response_handlers


@pytest.mark.asyncio
async def test_transport_send_exception_cleans_map(handler):
    handler._send_payload.side_effect = OSError("pipe unavailable")
    with pytest.raises(OSError, match="pipe unavailable"):
        await handler.send_request("x", {})
    assert not handler._response_handlers


@pytest.mark.asyncio
async def test_cancellation_cleans_map_and_sends_cancel_request(handler):
    task = asyncio.create_task(handler.send_request("long", {}))
    (identifier,) = await wait_for_pending(handler, 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert handler._response_handlers == {}
    handler._send_payload_sync.assert_called_once()
    payload = handler._send_payload_sync.call_args.args[0]
    assert payload == {
        "jsonrpc": "2.0", "method": "$/cancelRequest", "params": {"id": identifier}
    }
    await handler._response_handler({"id": identifier, "result": "late"})
    await handler._response_handler({"id": identifier, "result": "duplicate"})
    assert handler._response_handlers == {}


@pytest.mark.asyncio
async def test_concurrent_requests_resolve_out_of_order_without_leak(handler):
    tasks = [asyncio.create_task(handler.send_request("request", {"ordinal": i})) for i in range(20)]
    identifiers = await wait_for_pending(handler, 20)
    assert len(set(identifiers)) == len(tasks)
    for identifier in reversed(identifiers):
        await handler._response_handler({"id": identifier, "result": identifier})
    assert await asyncio.wait_for(asyncio.gather(*tasks), 3) == identifiers
    for identifier in identifiers:
        await handler._response_handler({"id": identifier, "result": "duplicate"})
    assert not handler._response_handlers


@pytest.mark.asyncio
async def test_stop_wakes_all_waiters_and_rejects_new_requests(handler):
    tasks = [asyncio.create_task(handler.send_request("stalled", {})) for _ in range(10)]
    old_ids = await wait_for_pending(handler, len(tasks))
    await asyncio.wait_for(handler.stop(), 3)
    results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 3)
    assert len(results) == len(tasks)
    assert all(isinstance(item, Error) and "stopped" in str(item) for item in results)
    assert not handler._response_handlers
    for identifier in old_ids:
        await handler._response_handler({"id": identifier, "result": "late"})
    with pytest.raises(Error, match="stopped"):
        await asyncio.wait_for(handler.send_request("new", {}), 1)


@pytest.mark.asyncio
async def test_stop_does_not_wait_for_stalled_stdin_drain(handler):
    sending = asyncio.Event()
    still_draining = asyncio.Event()

    async def blocked_send(_payload):
        sending.set()
        await still_draining.wait()

    handler._send_payload.side_effect = blocked_send
    task = asyncio.create_task(handler.send_request("blocked", {}))
    await asyncio.wait_for(sending.wait(), 2)
    assert len(handler._response_handlers) == 1
    await asyncio.wait_for(handler.stop(), 1)
    assert not handler._response_handlers
    still_draining.set()
    with pytest.raises(Error, match="stopped"):
        await asyncio.wait_for(task, 2)


@pytest.mark.asyncio
async def test_restarted_session_never_reuses_old_request_id(handler):
    task = asyncio.create_task(handler.send_request("old", {}))
    (old_id,) = await wait_for_pending(handler, 1)
    await handler.stop()
    with pytest.raises(Error):
        await task
    # start() resets stopped state when a new child is successfully spawned;
    # simulate only that lifecycle transition without launching a provider.
    handler._stopping = False
    next_request = asyncio.create_task(handler.send_request("new", {}))
    (next_id,) = await wait_for_pending(handler, 1)
    assert old_id != next_id
    await handler._response_handler({"id": old_id, "result": "obsolete"})
    assert not next_request.done()
    await handler._response_handler({"id": next_id, "result": "fresh"})
    assert await asyncio.wait_for(next_request, 2) == "fresh"
    assert not handler._response_handlers


@pytest.mark.asyncio
async def test_server_crash_and_eof_wake_outstanding_request(tmp_path):
    script = tmp_path / "exit_on_input.py"
    script.write_text("import sys\nsys.stdin.buffer.read(1)\n", encoding="utf-8")
    handler = LanguageServerHandler(ProcessLaunchInfo(cmd=[sys.executable, "-u", str(script)], cwd=str(tmp_path)))
    await handler.start()
    try:
        with pytest.raises(Error, match="connection closed"):
            await asyncio.wait_for(handler.send_request("never-answered", {}), 5)
        assert not handler._response_handlers
        with pytest.raises(Error, match="stopped"):
            await handler.send_request("after-eof", {})
    finally:
        await handler.stop()
    assert handler.process is None
    assert handler.tasks == {}


@pytest.mark.asyncio
async def test_duplicate_response_before_waiter_finishes_is_ignored(handler):
    task = asyncio.create_task(handler.send_request("repeat", {}))
    (identifier,) = await wait_for_pending(handler, 1)
    await handler._response_handler({"id": identifier, "result": "first"})
    await handler._response_handler({"id": identifier, "result": "second"})
    assert await asyncio.wait_for(task, 2) == "first"
    assert handler._response_handlers == {}


@pytest.mark.asyncio
async def test_repeated_cancels_never_accumulate_pending_requests(handler):
    for _ in range(100):
        task = asyncio.create_task(handler.send_request("repeated", {}))
        (identifier,) = await wait_for_pending(handler, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await handler._response_handler({"id": identifier, "result": "obsolete"})
        assert not handler._response_handlers
    assert handler.request_id == 101
    assert handler._send_payload_sync.call_count == 100


@pytest.mark.asyncio
@pytest.mark.parametrize("response", [
    {"error": None},
    {"error": {}},
    {"error": {"code": "wrong"}},
    {"error": {"code": "wrong", "message": "not an integer"}},
    {"error": {"code": True, "message": "boolean is not an error code"}},
    {"error": {"code": -32601, "message": 99}},
    {"result": 1, "error": {"code": -32000, "message": "bad"}},
])
async def test_malformed_reply_unblocks_and_fails_request(handler, response):
    task = asyncio.create_task(handler.send_request("malformed", {}))
    (identifier,) = await wait_for_pending(handler, 1)
    await handler._response_handler({"id": identifier, **response})
    with pytest.raises(Error) as exc:
        await asyncio.wait_for(task, 2)
    assert exc.value.code == ErrorCodes.InvalidRequest
    assert handler._response_handlers == {}


@pytest.mark.asyncio
async def test_partial_response_frame_then_eof_wakes_request(tmp_path):
    script = tmp_path / "truncated_frame.py"
    script.write_text(
        "import sys\n"
        "sys.stdin.buffer.read(1)\n"
        "sys.stdout.buffer.write(b'Content-Length: 20\\r\\n\\r\\nshort')\n"
        "sys.stdout.buffer.flush()\n",
        encoding="utf-8",
    )
    handler = LanguageServerHandler(
        ProcessLaunchInfo(cmd=[sys.executable, "-u", str(script)], cwd=str(tmp_path))
    )
    await handler.start()
    try:
        with pytest.raises(Error, match="connection closed"):
            await asyncio.wait_for(handler.send_request("partial", {}), 5)
        assert handler._response_handlers == {}
    finally:
        await handler.stop()
    assert handler.process is None
    assert handler.tasks == {}


@pytest.mark.asyncio
async def test_concurrent_stdin_drain_is_serialized_even_on_stop(handler):
    """Python 3.10/3.11 StreamWriter supports only one pending drain waiter."""
    from types import SimpleNamespace

    first_drain = asyncio.Event()
    release = asyncio.Event()

    class Writer:
        drain_calls = 0

        def writelines(self, _segments):
            pass

        async def drain(self):
            self.drain_calls += 1
            if self.drain_calls == 1:
                first_drain.set()
                await release.wait()

    writer = Writer()
    handler.process = SimpleNamespace(stdin=writer)
    handler._write_lock = asyncio.Lock()
    handler._cleanup_process = AsyncMock()
    # Restore the real method; the basic fixture uses a mocked sender.
    handler._send_payload = LanguageServerHandler._send_payload.__get__(handler)
    tasks = [asyncio.create_task(handler.send_request("stress", {})) for _ in range(2)]
    await asyncio.wait_for(first_drain.wait(), 2)
    await asyncio.sleep(0)
    assert writer.drain_calls == 1
    await asyncio.wait_for(handler.stop(), 2)
    release.set()
    outcomes = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), 2)
    assert all(isinstance(item, Error) for item in outcomes)
    assert not handler._response_handlers
    assert writer.drain_calls == 1  # queued write is never sent after stop


@pytest.mark.asyncio
async def test_old_reader_cannot_fail_requests_in_new_process(handler):
    from types import SimpleNamespace
    from multilspy.lsp_protocol_handler.server import Request

    entered = asyncio.Event()
    hold = asyncio.Event()

    class Reader:
        def at_eof(self):
            return False

        async def readline(self):
            entered.set()
            await hold.wait()
            return b""

    old_process = SimpleNamespace(stdout=Reader())
    handler.process = old_process
    old_reader = asyncio.create_task(handler.run_forever())
    await asyncio.wait_for(entered.wait(), 2)
    handler.process = SimpleNamespace(stdout=None)
    pending = Request()
    handler._response_handlers[42] = pending
    old_reader.cancel()
    with pytest.raises(asyncio.CancelledError):
        await old_reader
    assert not handler._stopping
    assert handler._response_handlers[42] is pending
    await pending.on_error(Error(ErrorCodes.InternalError, "test done"))
    handler._response_handlers.clear()


@pytest.mark.asyncio
async def test_background_task_tracking_reaps_completed_tasks(handler):
    for _ in range(300):
        handler._track_task(asyncio.sleep(0))
    # The loop schedules task completion callbacks one turn after the tasks
    # themselves finish; wait for the bound rather than assuming tick count.
    async def drained():
        while handler.tasks:
            await asyncio.sleep(0)

    await asyncio.wait_for(drained(), 2)
    assert handler.tasks == {}


@pytest.mark.asyncio
async def test_request_before_server_start_fails_instead_of_hanging(tmp_path):
    handler = LanguageServerHandler(ProcessLaunchInfo(cmd=[sys.executable], cwd=str(tmp_path)))
    with pytest.raises(Error, match="not running"):
        await asyncio.wait_for(handler.send_request("premature", {}), 1)
    assert not handler._response_handlers


@pytest.mark.asyncio
async def test_unroutable_and_duplicate_responses_leave_a_generic_log(tmp_path):
    callback = Mock()
    handler = LanguageServerHandler(
        ProcessLaunchInfo(cmd=[sys.executable], cwd=str(tmp_path)), logger=callback
    )
    await handler._response_handler({"id": None, "error": {"code": -32700, "message": "bad"}})
    await handler._response_handler({"id": 70000, "result": "late"})
    assert not handler._response_handlers
    assert callback.call_count == 2
    logs = [call.args[2] for call in callback.call_args_list]
    assert "unroutable" in logs[0]
    assert "duplicate" in logs[1]
    assert "70000" not in logs[1]  # no echo of untrusted response content
