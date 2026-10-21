"""
This file provides the implementation of the JSON-RPC client, that launches and 
communicates with the language server.

The initial implementation of this file was obtained from 
https://github.com/predragnikolic/OLSP under the MIT License with the following terms:

MIT License

Copyright (c) 2023 Предраг Николић

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import asyncio
import dataclasses
import json
import os
import psutil
from typing import Any, Dict, List, Optional, Union

from .lsp_requests import LspNotification, LspRequest
from .lsp_types import ErrorCodes

StringDict = Dict[str, Any]
PayloadLike = Union[List[StringDict], StringDict, None]
CONTENT_LENGTH = "Content-Length: "
ENCODING = "utf-8"


@dataclasses.dataclass
class ProcessLaunchInfo:
    """
    This class is used to store the information required to launch a process.
    """

    # The command to launch the process as a list of arguments (no shell involved)
    cmd: List[str]

    # The environment variables to set for the process
    env: Dict[str, str] = dataclasses.field(default_factory=dict)

    # The working directory for the process
    cwd: str = os.getcwd()


class Error(Exception):
    def __init__(self, code: ErrorCodes, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_lsp(self) -> StringDict:
        return {"code": self.code, "message": super().__str__()}

    @classmethod
    def from_lsp(cls, d: StringDict) -> "Error":
        return Error(d["code"], d["message"])

    def __str__(self) -> str:
        return f"{super().__str__()} ({self.code})"


def make_response(request_id: Any, params: PayloadLike) -> StringDict:
    return {"jsonrpc": "2.0", "id": request_id, "result": params}


def make_error_response(request_id: Any, err: Error) -> StringDict:
    return {"jsonrpc": "2.0", "id": request_id, "error": err.to_lsp()}


def make_notification(method: str, params: PayloadLike) -> StringDict:
    return {"jsonrpc": "2.0", "method": method, "params": params}


def make_request(method: str, request_id: Any, params: PayloadLike) -> StringDict:
    return {"jsonrpc": "2.0", "method": method, "id": request_id, "params": params}


class StopLoopException(Exception):
    pass


def create_message(payload: PayloadLike):
    body = json.dumps(payload, check_circular=False, ensure_ascii=False, separators=(",", ":")).encode(ENCODING)
    return (
        f"Content-Length: {len(body)}\r\n".encode(ENCODING),
        "Content-Type: application/vscode-jsonrpc; charset=utf-8\r\n\r\n".encode(ENCODING),
        body,
    )


class MessageType:
    error = 1
    warning = 2
    info = 3
    log = 4


class Request:
    def __init__(self) -> None:
        self.cv = asyncio.Condition()
        self.result: Optional[PayloadLike] = None
        self.error: Optional[Error] = None
        self.completed = False

    async def on_result(self, params: PayloadLike) -> None:
        async with self.cv:
            if self.completed:
                return
            self.result = params
            self.completed = True
            self.cv.notify_all()

    async def on_error(self, err: Error) -> None:
        async with self.cv:
            if self.completed:
                return
            self.error = err
            self.completed = True
            self.cv.notify_all()


def content_length(line: bytes) -> Optional[int]:
    if line.startswith(b"Content-Length: "):
        _, value = line.split(b"Content-Length: ")
        value = value.strip()
        try:
            return int(value)
        except ValueError:
            raise ValueError("Invalid Content-Length header: {}".format(value))
    return None


class LanguageServerHandler:
    """
    This class provides the implementation of Python client for the Language Server Protocol.
    A class that launches the language server and communicates with it
    using the Language Server Protocol (LSP).

    It provides methods for sending requests, responses, and notifications to the server
    and for registering handlers for requests and notifications from the server.

    Uses JSON-RPC 2.0 for communication with the server over stdin/stdout.

    Attributes:
        send: A LspRequest object that can be used to send requests to the server and
            await for the responses.
        notify: A LspNotification object that can be used to send notifications to the server.
        cmd: A string that represents the command to launch the language server process.
        process: A subprocess.Popen object that represents the language server process.
        _received_shutdown: A boolean flag that indicates whether the client has received
            a shutdown request from the server.
        request_id: An integer that represents the next available request id for the client.
        _response_handlers: A dictionary that maps request ids to Request objects that
            store the results or errors of the requests.
        on_request_handlers: A dictionary that maps method names to callback functions
            that handle requests from the server.
        on_notification_handlers: A dictionary that maps method names to callback functions
            that handle notifications from the server.
        logger: An optional function that takes two strings (source and destination) and
            a payload dictionary, and logs the communication between the client and the server.
        tasks: A dictionary that maps task ids to asyncio.Task objects that represent
            the asynchronous tasks created by the handler.
        task_counter: An integer that represents the next available task id for the handler.
        loop: An asyncio.AbstractEventLoop object that represents the event loop used by the handler.
        start_independent_lsp_process: An optional boolean flag that indicates whether to start the
        language server process in an independent process group. Default is `True`. Setting it to
        `False` means that the language server process will be in the same process group as the
        the current process, and any SIGINT and SIGTERM signals will be sent to both processes.
    """

    def __init__(
        self,
        process_launch_info: ProcessLaunchInfo,
        logger=None,
        start_independent_lsp_process=True,
    ) -> None:
        """
        Params:
            cmd: A string that represents the command to launch the language server process.
            logger: An optional function that takes two strings (source and destination) and
                a payload dictionary, and logs the communication between the client and the server.
        """
        self.send = LspRequest(self.send_request)
        self.notify = LspNotification(self.send_notification)

        self.process_launch_info = process_launch_info
        self.process = None
        self._received_shutdown = False
        self._stopping = False
        self._write_lock: Optional[asyncio.Lock] = None

        self.request_id = 1
        self._response_handlers: Dict[Any, Request] = {}
        self.on_request_handlers = {}
        self.on_notification_handlers = {}
        self.logger = logger
        self.tasks = {}
        self.task_counter = 0
        self.loop = None
        self.start_independent_lsp_process = start_independent_lsp_process

    async def start(self) -> None:
        """
        Starts the language server process and creates a task to continuously read from its stdout to handle communications
        from the server to the client
        """
        child_proc_env = os.environ.copy()
        child_proc_env.update(self.process_launch_info.env)
        self.process = await asyncio.create_subprocess_exec(
            *self.process_launch_info.cmd,
            stdout=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=child_proc_env,
            cwd=self.process_launch_info.cwd,
            start_new_session=self.start_independent_lsp_process,
        )

        self._stopping = False
        self._received_shutdown = False
        # A SyncLanguageServer can restart this handler in a new event loop.
        self._write_lock = asyncio.Lock()
        self.loop = asyncio.get_event_loop()
        self._track_task(self.run_forever())
        self._track_task(self.run_forever_stderr())

    async def stop(self) -> None:
        """
        Sends the terminate signal to the language server process and waits for it to exit, with a timeout, killing it if necessary
        """
        # Stop admitting new requests and release callers waiting on the
        # process, even when it exits without a shutdown response.
        self._stopping = True
        await self._fail_pending_requests("Language server process stopped")
        await self._cancel_pending_tasks()
    
        process = self.process
        self.process = None
    
        if not process:
            return
    
        # Clean up the process
        await self._cleanup_process(process)

    async def _fail_pending_requests(self, reason: str) -> None:
        """Wake and forget every request whose response will never arrive."""
        pending = list(self._response_handlers.values())
        self._response_handlers.clear()
        for request in pending:
            await request.on_error(Error(ErrorCodes.InternalError, reason))

    def _track_task(self, coroutine) -> None:
        """Track only running reader/notification tasks, not completed ones."""
        identifier = self.task_counter
        self.task_counter += 1
        task = asyncio.get_running_loop().create_task(coroutine)
        self.tasks[identifier] = task

        def remove_completed(finished):
            self.tasks.pop(identifier, None)
            try:
                finished.result()
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                # Avoid retaining failed tasks or echoing untrusted wire data.
                self._log(f"LSP background task failed: {type(exc).__name__}")

        task.add_done_callback(remove_completed)

    async def _cancel_pending_tasks(self):
        """Cancel all pending tasks and wait for them to complete or timeout."""
        pending_tasks = []
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
                pending_tasks.append(task)

        if pending_tasks:
            try:
                await asyncio.wait_for(asyncio.gather(*pending_tasks, return_exceptions=True), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                pass
    
        self.tasks = {}

    async def _cleanup_process(self, process):
        """Clean up a process: close stdin, terminate/kill process, close stdout/stderr."""
        # Close stdin first to prevent deadlocks
        # See: https://bugs.python.org/issue35539
        self._safely_close_pipe(process.stdin)
    
        # Terminate/kill the process if it's still running
        if process.returncode is None:
            await self._terminate_or_kill_process(process)
    
        # Close stdout and stderr pipes after process has exited
        # This is essential to prevent "I/O operation on closed pipe" errors and
        # "Event loop is closed" errors during garbage collection
        # See: https://bugs.python.org/issue41320 and https://github.com/python/cpython/issues/88050
        self._safely_close_pipe(process.stdout)
        self._safely_close_pipe(process.stderr)
    
        # Small delay to ensure OS has released file handles
        await asyncio.sleep(0.5)

    def _safely_close_pipe(self, pipe):
        """Safely close a pipe, ignoring any exceptions."""
        if pipe:
            try:
                pipe.close()
            except Exception:
                pass

    async def _terminate_or_kill_process(self, process):
        """Try to terminate the process gracefully, then forcefully if necessary."""
        # First try to terminate the process tree gracefully
        self._signal_process_tree(process, terminate=True)

        # Wait for the process to exit (with timeout)
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except (asyncio.TimeoutError, Exception):
            # If termination failed, forcefully kill the process tree
            self._signal_process_tree(process, terminate=False)
            try:
                # Give it one more chance to exit
                await asyncio.wait_for(process.wait(), timeout=2)
            except Exception:
                pass

    def _signal_process_tree(self, process, terminate=True):
        """Send signal (terminate or kill) to the process and all its children."""
        signal_method = "terminate" if terminate else "kill"
    
        # Try to get the parent process
        parent = None
        try:
            parent = psutil.Process(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
            pass
    
        # If we have the parent process and it's running, signal the entire tree
        if parent and parent.is_running():
            # Signal children first - wrap in try-except to handle race conditions
            # where children exit between getting the list and signaling them
            try:
                children = parent.children(recursive=True)
                for child in children:
                    try:
                        getattr(child, signal_method)()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                        pass
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                # Parent or children may have exited during iteration
                pass
        
            # Then signal the parent
            try:
                getattr(parent, signal_method)()
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                pass
        else:
            # Fall back to direct process signaling
            try:
                getattr(process, signal_method)()
            except Exception:
                pass


    async def shutdown(self) -> None:
        """
        Perform the shutdown sequence for the client, including sending the shutdown request to the server and notifying it of exit
        """
        try:
            await asyncio.wait_for(self.send.shutdown(), timeout=30)
        except (asyncio.TimeoutError, Exception):
            # Server didn't respond to shutdown request; proceed to exit/kill
            pass
        self._received_shutdown = True
        self.notify.exit()
        if self.process and self.process.stdout:
            self.process.stdout.set_exception(StopLoopException())
            # This yields the control to the event loop to allow the exception to be handled
            # in the run_forever and run_forever_stderr methods
            await asyncio.sleep(0)

    def _log(self, message: str) -> None:
        """
        Create a log message
        """
        if self.logger:
            self.logger("client", "logger", message)

    async def run_forever(self) -> bool:
        """
        Continuously read from the language server process stdout and handle the messages
        invoking the registered response and notification handlers
        """
        # A delayed reader from an earlier lifespan must never abort pending
        # requests belonging to a new process after restart.
        reader_process = self.process
        try:
            while self.process and self.process.stdout and not self.process.stdout.at_eof():
                line = await self.process.stdout.readline()
                if not line:
                    continue
                try:
                    num_bytes = content_length(line)
                except ValueError:
                    continue
                if num_bytes is None:
                    continue
                while line and line.strip():
                    line = await self.process.stdout.readline()
                if not line:
                    continue
                body = await self.process.stdout.readexactly(num_bytes)

                self._track_task(self._handle_body(body))
        except (BrokenPipeError, ConnectionResetError, StopLoopException,
                asyncio.IncompleteReadError):
            pass
        finally:
            if self.process is reader_process and not self._received_shutdown:
                # EOF/crash is as terminal as an explicit stop, but an old
                # reader may not close a newly started session's requests.
                self._stopping = True
                await self._fail_pending_requests("Language server connection closed")
        return self._received_shutdown

    async def run_forever_stderr(self) -> None:
        """
        Continuously read from the language server process stderr and log the messages
        """
        try:
            while self.process and self.process.stderr and not self.process.stderr.at_eof():
                line = await self.process.stderr.readline()
                if not line:
                    continue
                self._log("LSP stderr: " + line.decode(ENCODING, errors='replace'))
        except (BrokenPipeError, ConnectionResetError, StopLoopException):
            pass

    async def _handle_body(self, body: bytes) -> None:
        """
        Parse the body text received from the language server process and invoke the appropriate handler
        """
        try:
            await self._receive_payload(json.loads(body))
        except IOError as ex:
            self._log(f"malformed {ENCODING}: {ex}")
        except UnicodeDecodeError as ex:
            self._log(f"malformed {ENCODING}: {ex}")
        except json.JSONDecodeError as ex:
            self._log(f"malformed JSON: {ex}")

    async def _receive_payload(self, payload: StringDict) -> None:
        """
        Determine if the payload received from server is for a request, response, or notification and invoke the appropriate handler
        """
        if self.logger:
            self.logger("server", "client", payload)
        try:
            if "method" in payload:
                if "id" in payload:
                    await self._request_handler(payload)
                else:
                    await self._notification_handler(payload)
            elif "id" in payload:
                await self._response_handler(payload)
            else:
                self._log(f"Unknown payload type: {payload}")
        except Exception as err:
            self._log(f"Error handling server payload: {err}")

    def send_notification(self, method: str, params: Optional[dict] = None) -> None:
        """
        Send notification pertaining to the given method to the server with the given parameters
        """
        self._send_payload_sync(make_notification(method, params))

    def send_response(self, request_id: Any, params: PayloadLike) -> None:
        """Send a response to a server-initiated request."""
        self._track_task(self._send_payload(make_response(request_id, params)))

    def send_error_response(self, request_id: Any, err: Error) -> None:
        """Send an error response to a server-initiated request."""
        self._track_task(self._send_payload(make_error_response(request_id, err)))

    async def send_request(self, method: str, params: Optional[dict] = None) -> None:
        """
        Send request to the server, register the request id, and wait for the response
        """
        if self._stopping:
            raise Error(ErrorCodes.InternalError, "Language server is stopped")
        request = Request()
        request_id = self.request_id
        self.request_id += 1
        self._response_handlers[request_id] = request
        try:
            # Never hold the condition lock across stdin I/O: stop() must be
            # able to wake abandoned requests even if pipe.drain() stalls.
            await self._send_payload(make_request(method, request_id, params))
            async with request.cv:
                await request.cv.wait_for(lambda: request.completed)
            if isinstance(request.error, Error):
                raise request.error
            return request.result
        except asyncio.CancelledError:
            # Inform an active server that the request is no longer wanted;
            # always preserve cancellation even if stdin is already closed.
            if not self._stopping:
                try:
                    self.notify.cancel_request({"id": request_id})
                except (OSError, RuntimeError, ValueError):
                    pass
            raise
        finally:
            # A timed-out or cancelled request must never retain its response
            # record. A late/duplicate reply will be discarded by the handler.
            if self._response_handlers.get(request_id) is request:
                self._response_handlers.pop(request_id, None)

    def _send_payload_sync(self, payload: StringDict) -> None:
        """
        Send the payload to the server by writing to its stdin synchronously
        """
        if not self.process or not self.process.stdin:
            return
        msg = create_message(payload)
        if self.logger:
            self.logger("client", "server", payload)
        self.process.stdin.writelines(msg)

    async def _send_payload(self, payload: StringDict) -> None:
        """Write a complete LSP frame, serializing concurrent drain calls."""
        lock = self._write_lock
        if lock is None:
            raise Error(ErrorCodes.InternalError, "Language server is not running")
        async with lock:
            if self._stopping:
                raise Error(ErrorCodes.InternalError, "Language server is stopped")
            process = self.process
            if not process or not process.stdin:
                raise Error(ErrorCodes.InternalError, "Language server is not running")
            msg = create_message(payload)
            if self.logger:
                self.logger("client", "server", payload)
            process.stdin.writelines(msg)
            await process.stdin.drain()

    def on_request(self, method: str, cb) -> None:
        """
        Register the callback function to handle requests from the server to the client for the given method
        """
        self.on_request_handlers[method] = cb

    def on_notification(self, method: str, cb) -> None:
        """
        Register the callback function to handle notifications from the server to the client for the given method
        """
        self.on_notification_handlers[method] = cb

    async def _response_handler(self, response: StringDict) -> None:
        """
        Handle the response received from the server for a request, using the id to determine the request
        """
        request_id = response.get("id")
        if type(request_id) not in (int, str):
            self._log("Ignoring LSP response with unroutable id")
            return
        request = self._response_handlers.get(request_id)
        if request is None or self._stopping:
            # Timeout/cancellation and duplicate replies are legal races.
            # Never fail another reader task for a completed request id.
            self._log("Ignoring late or duplicate LSP response")
            return
        if "result" in response and "error" not in response:
            await request.on_result(response["result"])
        elif "result" not in response and "error" in response:
            try:
                raw_error = response["error"]
                if (
                    not isinstance(raw_error, dict)
                    or not isinstance(raw_error.get("code"), int)
                    or isinstance(raw_error.get("code"), bool)
                    or not isinstance(raw_error.get("message"), str)
                ):
                    raise ValueError("Invalid JSON-RPC error shape")
                error = Error.from_lsp(raw_error)
            except (KeyError, TypeError, ValueError):
                # A malformed response still completes its waiting request;
                # otherwise a corrupt peer could strand the caller forever.
                error = Error(ErrorCodes.InvalidRequest, "Malformed LSP error response")
            await request.on_error(error)
        else:
            await request.on_error(Error(ErrorCodes.InvalidRequest, "Malformed LSP response"))

    async def _request_handler(self, response: StringDict) -> None:
        """
        Handle the request received from the server: call the appropriate callback function and return the result
        """
        method = response.get("method", "")
        params = response.get("params")
        request_id = response.get("id")
        handler = self.on_request_handlers.get(method)
        if not handler:
            self.send_error_response(
                request_id,
                Error(
                    ErrorCodes.MethodNotFound,
                    "method '{}' not handled on client.".format(method),
                ),
            )
            return
        try:
            self.send_response(request_id, await handler(params))
        except Error as ex:
            self.send_error_response(request_id, ex)
        except Exception as ex:
            self.send_error_response(request_id, Error(ErrorCodes.InternalError, str(ex)))

    async def _notification_handler(self, response: StringDict) -> None:
        """
        Handle the notification received from the server: call the appropriate callback function
        """
        method = response.get("method", "")
        params = response.get("params")
        handler = self.on_notification_handlers.get(method)
        if not handler:
            self._log(f"unhandled {method}")
            return
        try:
            await handler(params)
        except asyncio.CancelledError:
            return
        except Exception as ex:
            if (not self._received_shutdown) and self.logger:
                self.logger(
                    "client",
                    "logger",
                    str(
                        {
                            "type": MessageType.error,
                            "message": str(ex),
                            "method": method,
                            "params": params,
                        }
                    ),
                )
