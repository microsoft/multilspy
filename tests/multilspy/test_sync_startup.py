"""Startup deadlines and cleanup, including real subprocess resources."""

import asyncio
import concurrent.futures
from contextlib import asynccontextmanager
import sys
import threading

import pytest

from multilspy import SyncLanguageServer
from multilspy.language_server import LanguageServer
from multilspy.lsp_protocol_handler.server import ProcessLaunchInfo
from multilspy.multilspy_config import Language, MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


class StartupServer(LanguageServer):
    def __init__(self, path, fail=False, delay=0):
        super().__init__(
            MultilspyConfig(code_language=Language.PYTHON), MultilspyLogger(), str(path),
            ProcessLaunchInfo(cmd=[sys.executable, "-c", "import time; time.sleep(60)"], cwd=str(path)),
            "python",
        )
        self.fail = fail
        self.delay = delay
        self.process = None
        self.cancelled = False

    @asynccontextmanager
    async def start_server(self):
        async with super().start_server():
            await self.server.start()
            self.process = self.server.process
            try:
                if self.fail:
                    raise ValueError("initialization failed")
                await asyncio.sleep(self.delay)
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            try:
                yield self
            finally:
                await self.server.stop()


@pytest.fixture
def servers(tmp_path):
    created = []
    threads_before = set(threading.enumerate())

    def create(**kwargs):
        underlying = StartupServer(tmp_path, **kwargs)
        server = SyncLanguageServer(underlying, timeout=1)
        created.append(server)
        return server

    yield create
    # Also clean up resources when running these regressions against unfixed code.
    for server in created:
        if server.loop and server.loop.is_running():
            asyncio.run_coroutine_threadsafe(server.language_server.server.stop(), server.loop).result(5)
            server.loop.call_soon_threadsafe(server.loop.stop)
    for thread in set(threading.enumerate()) - threads_before:
        thread.join(5)
    for server in created:
        if server.loop and not server.loop.is_closed():
            server.loop.close()


def assert_stopped(server):
    assert server.language_server.process.returncode is not None
    assert server.language_server.server.process is None
    assert not server.language_server.server_started
    assert server.loop.is_closed()
    assert not server.loop_thread.is_alive()


def test_startup_timeout_cancels_initialization_and_cleans_up(servers):
    server = servers(delay=2)
    with pytest.raises((TimeoutError, concurrent.futures.TimeoutError)):
        with server.start_server():
            pytest.fail("Startup should have timed out")
    assert server.language_server.cancelled
    assert_stopped(server)


def test_startup_error_cleans_up_and_preserves_exception(servers):
    server = servers(fail=True)
    with pytest.raises(ValueError, match="initialization failed"):
        with server.start_server():
            pytest.fail("Failed startup must not enter the body")
    assert_stopped(server)


@pytest.mark.parametrize("body_error", [False, True])
def test_successful_startup_always_closes_loop(servers, body_error):
    server = servers()
    try:
        with server.start_server():
            assert server.language_server.server_started
            if body_error:
                raise ValueError("body failed")
    except ValueError as exc:
        assert body_error and str(exc) == "body failed"
    assert_stopped(server)
