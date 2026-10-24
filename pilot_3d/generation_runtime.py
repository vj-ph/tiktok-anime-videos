"""Scoped power management, generic notifications, and owned subprocess cleanup."""

import contextvars
import ctypes
from ctypes import wintypes
import functools
import os
from pathlib import Path
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

_ACTIVE = contextvars.ContextVar("generation_runtime", default=None)
_PARENT = "_VIDEO_GENERATION_PARENT"
_PROCESSES = set()
_PROCESS_LOCK = threading.Lock()
_CANCELLING = threading.Event()
STAGES = {
    "audio": "speech", "alignment": "subtitle alignment", "scene": "scene preparation",
    "scene_checks": "scene checks", "frames": "frame rendering", "export": "encoding",
    "review": "delivery review", "promo": "derived video", "benchmark": "worker benchmark",
}


def _warn(message):
    print(message, file=sys.stderr, flush=True)


class _WindowsPower:
    def __init__(self):
        class DetailedReason(ctypes.Structure):
            _fields_ = [("module", wintypes.HMODULE), ("id", wintypes.ULONG),
                        ("count", wintypes.ULONG), ("strings", ctypes.POINTER(wintypes.LPWSTR))]

        class Reason(ctypes.Union):
            _fields_ = [("simple", wintypes.LPWSTR), ("detailed", DetailedReason)]

        class Context(ctypes.Structure):
            _fields_ = [("version", wintypes.ULONG), ("flags", wintypes.DWORD), ("reason", Reason)]

        class PowerStatus(ctypes.Structure):
            _fields_ = [("ac", wintypes.BYTE), ("battery_flag", wintypes.BYTE),
                        ("battery_percent", wintypes.BYTE), ("reserved", wintypes.BYTE),
                        ("battery_seconds", wintypes.DWORD), ("full_seconds", wintypes.DWORD)]

        self.context_type = Context
        self.status_type = PowerStatus
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.GetSystemPowerStatus.argtypes = [ctypes.POINTER(PowerStatus)]
        self.api.GetSystemPowerStatus.restype = wintypes.BOOL
        self.api.PowerCreateRequest.argtypes = [ctypes.POINTER(Context)]
        self.api.PowerCreateRequest.restype = wintypes.HANDLE
        for name in ("PowerSetRequest", "PowerClearRequest"):
            function = getattr(self.api, name)
            function.argtypes = [wintypes.HANDLE, ctypes.c_int]
            function.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = None

    def on_ac(self):
        status = self.status_type()
        if not self.api.GetSystemPowerStatus(ctypes.byref(status)):
            raise ctypes.WinError(ctypes.get_last_error())
        return status.ac == 1

    def set_required(self, required):
        if not required:
            handle, self.handle = self.handle, None
            if handle is not None:
                try:
                    for request in (3, 1):
                        self.api.PowerClearRequest(handle, request)
                finally:
                    self.api.CloseHandle(handle)
            return
        if self.handle is not None:
            return
        context = self.context_type(0, 1)
        context.reason.simple = "Video generation in progress on AC power"
        handle = self.api.PowerCreateRequest(ctypes.byref(context))
        if handle in (None, ctypes.c_void_p(-1).value):
            raise ctypes.WinError(ctypes.get_last_error())
        acquired = []
        try:
            # System and execution requests allow display idle; never request display or away mode.
            for request in (1, 3):
                if not self.api.PowerSetRequest(handle, request):
                    raise ctypes.WinError(ctypes.get_last_error())
                acquired.append(request)
        except BaseException:
            for request in reversed(acquired):
                self.api.PowerClearRequest(handle, request)
            self.api.CloseHandle(handle)
            raise
        self.handle = handle


class SleepGuard:
    def __init__(self, api=None, interval=1.0):
        self.api = api
        self.interval = interval
        self.stop = threading.Event()
        self.thread = None
        self.required = False

    def refresh(self):
        required = self.api.on_ac()
        if required != self.required:
            self.api.set_required(required)
            self.required = required

    def _monitor(self):
        try:
            while not self.stop.wait(self.interval):
                self.refresh()
        except Exception:
            self._release()
            _warn("Sleep prevention unavailable; generation continues.")

    def _release(self):
        try:
            if self.api is not None:
                self.api.set_required(False)
        except Exception:
            _warn("Sleep request cleanup failed; Windows also releases requests when this process exits.")
        self.required = False

    def __enter__(self):
        if sys.platform != "win32" and self.api is None:
            return self
        try:
            if self.api is None:
                self.api = _WindowsPower()
            self.refresh()
            self.thread = threading.Thread(target=self._monitor, daemon=True)
            self.thread.start()
        except Exception:
            self.thread = None
            self._release()
            _warn("Sleep prevention unavailable; generation continues.")
        return self

    def __exit__(self, *unused):
        self.stop.set()
        if self.thread is not None:
            self.thread.join()
        self._release()


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Notifier:
    def __init__(self, server=None, topic=None, token=None, timeout=2.0, close_timeout=1.0):
        self.url = None
        self.token = token
        self.timeout = timeout
        self.close_timeout = close_timeout
        self.messages = queue.Queue(maxsize=32)
        self.thread = None
        self.closed = threading.Event()
        self.finish_by = float("inf")
        self.warned = False
        self.last_milestone = 0
        self.last_progress_time = -float("inf")
        if server is None and topic is None:
            return
        try:
            parsed = urlsplit(server or "")
        except ValueError:
            _warn("Invalid video notification configuration; notifications disabled.")
            return
        if (parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.username
                or parsed.password or parsed.query or parsed.fragment
                or not re.fullmatch(r"[-_A-Za-z0-9]{1,64}", topic or "")
                or any(c in (token or "") for c in "\r\n")):
            _warn("Invalid video notification configuration; notifications disabled.")
            return
        self.url = server.rstrip("/") + "/" + topic
        self.thread = threading.Thread(target=self._deliver, daemon=True)
        try:
            self.thread.start()
        except RuntimeError:
            self.thread = None
            self.url = None
            self._warning()

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("VIDEO_NTFY_SERVER"), os.environ.get("VIDEO_NTFY_TOPIC"),
                   os.environ.get("VIDEO_NTFY_TOKEN"))

    def _warning(self):
        if not self.warned:
            self.warned = True
            _warn("Video notification delivery unavailable; generation continues.")

    def _enqueue(self, message, terminal=False):
        if self.url is None or self.closed.is_set():
            return
        try:
            self.messages.put_nowait(message)
        except queue.Full:
            if terminal:
                try:
                    self.messages.get_nowait()
                    self.messages.task_done()
                    self.messages.put_nowait(message)
                    return
                except (queue.Empty, queue.Full):
                    pass
            self._warning()

    def event(self, event):
        messages = {
            "started": "Video generation run started.",
            "completed": "Video generation run completed.",
            "failed": "Video generation run failed. Check local logs.",
            "cancelled": "Video generation run cancelled.",
        }
        if event in messages:
            self._enqueue(messages[event], terminal=event != "started")

    def stage(self, name, reused=False):
        if name in STAGES:
            suffix = " (verified checkpoint)" if reused else ""
            self._enqueue(f"Video generation: {STAGES[name]} completed{suffix}.")

    def progress(self, completed, total):
        if total <= 0:
            return
        milestone = min(100, max(0, completed * 100 // total)) // 25 * 25
        now = time.monotonic()
        if milestone <= self.last_milestone:
            return
        if milestone < 100 and now - self.last_progress_time < 30:
            return
        self.last_milestone = milestone
        self.last_progress_time = now
        self._enqueue(f"Video generation: frame rendering reached {milestone}%.")

    def _deliver(self):
        try:
            opener = build_opener(_NoRedirect())
        except Exception:
            self._warning()
            return
        while time.monotonic() < self.finish_by and (not self.closed.is_set() or not self.messages.empty()):
            try:
                message = self.messages.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                headers = {"Title": "Video generation", "Content-Type": "text/plain; charset=utf-8"}
                if self.token:
                    headers["Authorization"] = "Bearer " + self.token
                request = Request(self.url, data=message.encode("utf-8"), headers=headers, method="POST")
                with opener.open(request, timeout=self.timeout):
                    pass
            except Exception:
                self._warning()
            finally:
                self.messages.task_done()

    def close(self):
        self.finish_by = time.monotonic() + self.close_timeout
        self.closed.set()
        if self.thread is not None:
            self.thread.join(timeout=self.close_timeout)


def start_process(command, **kwargs):
    with _PROCESS_LOCK:
        if _CANCELLING.is_set():
            raise KeyboardInterrupt
        if sys.platform == "win32":
            kwargs.setdefault("creationflags", subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            kwargs.setdefault("start_new_session", True)
        process = subprocess.Popen(list(map(str, command)), **kwargs)
        _PROCESSES.add(process)
        return process


def forget_process(process):
    with _PROCESS_LOCK:
        _PROCESSES.discard(process)


def stop_processes(processes):
    if not processes:
        return
    try:
        import psutil
    except ImportError:
        active = _ACTIVE.get()
        if active is not None and active.cleanup_python is not None:
            pids = [str(process.pid) for process in processes if process.poll() is None]
            try:
                result = subprocess.run(
                    [str(active.cleanup_python), str(Path(__file__).resolve()), "--stop-owned", *pids],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=8)
                if result.returncode == 0 and all(process.poll() is not None for process in processes):
                    return
            except (OSError, subprocess.TimeoutExpired):
                pass
        for process in processes:
            if process.poll() is not None:
                continue
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT if sys.platform == "win32" else signal.SIGTERM)
                process.wait(timeout=8)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait()
        return
    targets = {}
    for process in processes:
        if process.poll() is not None:
            continue
        try:
            root = psutil.Process(process.pid)
            for target in [*root.children(recursive=True), root]:
                targets[target.pid] = target
        except psutil.Error:
            continue
    for target in targets.values():
        try:
            target.terminate()
        except psutil.Error:
            pass
    _, alive = psutil.wait_procs(list(targets.values()), timeout=3)
    for target in alive:
        try:
            target.kill()
        except psutil.Error:
            pass
    psutil.wait_procs(alive, timeout=2)


def cancel_processes():
    _CANCELLING.set()
    with _PROCESS_LOCK:
        processes = list(_PROCESSES)
    stop_processes(processes)


def run_process(command, *, check=False, capture_output=False, input=None, timeout=None, **kwargs):
    if capture_output:
        if "stdout" in kwargs or "stderr" in kwargs:
            raise ValueError("capture_output cannot be combined with stdout/stderr")
        kwargs.update(stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if input is not None:
        kwargs["stdin"] = subprocess.PIPE
    process = start_process(command, **kwargs)
    try:
        stdout, stderr = process.communicate(input, timeout=timeout)
        result = subprocess.CompletedProcess(list(map(str, command)), process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result
    except BaseException:
        stop_processes([process])
        try:
            process.communicate(timeout=1)
        except (OSError, subprocess.TimeoutExpired):
            pass
        raise
    finally:
        forget_process(process)


class GenerationRun:
    def __init__(self, cleanup_python=None):
        self.cleanup_python = cleanup_python

    def __enter__(self):
        self.parent = _ACTIVE.get()
        if self.parent is not None and self.cleanup_python is None:
            self.cleanup_python = self.parent.cleanup_python
        self.owner = self.parent is None and not os.environ.get(_PARENT)
        self.notifier = self.parent.notifier if self.parent else Notifier.from_environment()
        self.token = _ACTIVE.set(self)
        self.handlers = {}
        self.guard = None
        if self.parent is None and threading.current_thread() is threading.main_thread():
            for name in ("SIGTERM", "SIGBREAK"):
                sig = getattr(signal, name, None)
                if sig is not None:
                    self.handlers[sig] = signal.signal(sig, self._cancel)
        if self.owner:
            _CANCELLING.clear()
            os.environ[_PARENT] = str(os.getpid())
            self.guard = SleepGuard()
            self.guard.__enter__()
            self.notifier.event("started")
        return self

    @staticmethod
    def _cancel(signum, frame):
        raise KeyboardInterrupt

    def __exit__(self, kind, value, traceback):
        try:
            if self.parent is None and kind is not None:
                cancel_processes()
            if self.owner:
                self.guard.__exit__(kind, value, traceback)
                cancelled = (kind is not None and issubclass(kind, KeyboardInterrupt)
                             or isinstance(value, SystemExit) and value.code in (130, 143))
                success = kind is None or isinstance(value, SystemExit) and value.code in (None, 0)
                self.notifier.event("cancelled" if cancelled else "completed" if success else "failed")
        finally:
            if self.parent is None:
                self.notifier.close()
            if self.owner:
                os.environ.pop(_PARENT, None)
            if self.parent is None:
                for sig, handler in self.handlers.items():
                    signal.signal(sig, handler)
                _CANCELLING.clear()
            _ACTIVE.reset(self.token)


def generation_job(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        with GenerationRun():
            return function(*args, **kwargs)
    return wrapped


def stage_completed(name, reused=False, *, force=False):
    active = _ACTIVE.get()
    if active is not None and (active.owner or force):
        active.notifier.stage(name, reused)


def render_progress(completed, total):
    active = _ACTIVE.get()
    if active is not None:
        active.notifier.progress(completed, total)


if __name__ == "__main__":
    from types import SimpleNamespace

    if sys.argv[1:2] != ["--stop-owned"]:
        raise SystemExit("Internal owned-process cleanup helper.")
    stop_processes([SimpleNamespace(pid=int(pid), poll=lambda: None) for pid in sys.argv[2:]])
