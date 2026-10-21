"""Pyright startup timeout/cancellation against a real but nonresponsive peer.

These process-level tests mirror test_sync_startup.py: they launch only a
local disposable Python script, never install or discover Pyright.
"""

import asyncio
import os
import sys

import pytest

from multilspy.language_server import LanguageServer
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


@pytest.fixture
def hung_stdio_server(tmp_path):
    script = tmp_path / "silent_lsp.py"
    script.write_text(
        "import sys\n"
        "for line in sys.stdin.buffer:\n"
        "    pass  # Read incoming LSP frames; never answer initialize.\n"
    )
    return script


@pytest.fixture
def pyright_with_fake_transport(tmp_path, hung_stdio_server):
    server = LanguageServer.create(
        MultilspyConfig(
            code_language=Language.PYTHON,
            python_server="pyright",
        ),
        MultilspyLogger(),
        str(tmp_path.resolve()),
    )
    handler = server.server
    handler.process_launch_info.cmd = [
        sys.executable,
        "-u",
        str(hung_stdio_server),
    ]
    started = asyncio.Event()
    created = []
    native_start = handler.start

    async def capture_process():
        await native_start()
        created.append(handler.process)
        started.set()

    handler.start = capture_process
    return server, handler, created, started


@pytest.mark.asyncio
async def test_real_initialize_timeout_stops_process_and_readers(
    pyright_with_fake_transport,
):
    server, handler, created, _started = pyright_with_fake_transport
    server._initialize_timeout_seconds = 0.05

    async def exercise():
        async with server.start_server():
            pytest.fail("No response from synthetic LSP server")

    try:
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(exercise(), timeout=5)
        assert len(created) == 1
        assert created[0].returncode is not None
        assert handler.process is None
        assert handler.tasks == {}
        assert not handler._response_handlers
        assert not server.server_started
    finally:
        for process in created:
            if process.returncode is None:
                process.kill()
                await process.wait()


@pytest.mark.asyncio
async def test_real_cancelled_initialize_stops_process_and_readers(
    pyright_with_fake_transport,
):
    server, handler, created, started = pyright_with_fake_transport

    async def exercise():
        async with server.start_server():
            pytest.fail("Cancelled startup must not enter the context")

    pending = asyncio.create_task(exercise())
    try:
        await asyncio.wait_for(started.wait(), timeout=3)
        assert len(created) == 1
        pending.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(pending, timeout=5)
        assert created[0].returncode is not None
        assert handler.process is None
        assert handler.tasks == {}
        assert not handler._response_handlers
        assert not server.server_started
    finally:
        if not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        for process in created:
            if process.returncode is None:
                process.kill()
                await process.wait()


@pytest.mark.asyncio
async def test_real_pyright_restarts_after_abandoned_request(tmp_path):
    binary = os.environ.get("MULTILSPY_PYRIGHT_TEST_BINARY")
    if not binary:
        pytest.skip("Real pinned Pyright is not configured")

    (tmp_path / "sample.py").write_text(
        "value = 42\nresult = value\n", encoding="utf-8"
    )
    server = LanguageServer.create(
        MultilspyConfig(
            code_language=Language.PYTHON,
            python_server="pyright", server_binary=binary,
        ),
        MultilspyLogger(), str(tmp_path.resolve()),
    )
    seen_ids = []
    for _ in range(2):
        async with server.start_server():
            handler = server.server
            original_send = handler._send_payload

            async def unanswered(payload):
                # Pyright may concurrently send workspace/configuration
                # requests. Their client responses must keep flowing; only
                # silence this *one* outgoing definition request.
                if payload.get("method") == "textDocument/definition":
                    return None
                return await original_send(payload)

            handler._send_payload = unanswered
            try:
                with pytest.raises(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        handler.send_request("textDocument/definition", {}), 0.05
                    )
            finally:
                handler._send_payload = original_send
            assert handler._response_handlers == {}
            seen_ids.append(handler.request_id - 1)
            with server.open_file("sample.py"):
                definition = await asyncio.wait_for(
                    server.request_definition("sample.py", 1, 10), 8
                )
                assert len(definition) == 1
                assert definition[0]["relativePath"] == "sample.py"
                assert definition[0]["range"]["start"] == {
                    "line": 0, "character": 0,
                }
        assert handler._response_handlers == {}
        assert handler.process is None
        assert handler.tasks == {}
    assert seen_ids[1] > seen_ids[0]
