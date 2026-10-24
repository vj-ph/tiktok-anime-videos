import ctypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import os
import signal
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import psutil

import generation_runtime as runtime


class FakePower:
    def __init__(self, ac=True):
        self.ac = ac
        self.requests = []

    def on_ac(self):
        return self.ac

    def set_required(self, required):
        self.requests.append(required)


class PowerTests(unittest.TestCase):
    def test_ac_battery_transitions_and_idempotent_refresh(self):
        api = FakePower()
        with runtime.SleepGuard(api, interval=60) as guard:
            self.assertTrue(guard.required)
            guard.refresh()
            api.ac = False
            guard.refresh()
            self.assertFalse(guard.required)
            api.ac = True
            guard.refresh()
        self.assertEqual(api.requests, [True, False, True, False])

    def test_battery_never_acquires_request(self):
        api = FakePower(False)
        with runtime.SleepGuard(api, interval=60) as guard:
            self.assertFalse(guard.required)
        self.assertNotIn(True, api.requests)

    def test_success_failure_and_cancellation_release(self):
        for error in (None, ValueError("test"), KeyboardInterrupt()):
            api = FakePower()
            try:
                with runtime.SleepGuard(api, interval=60):
                    if error is not None:
                        raise error
            except (ValueError, KeyboardInterrupt):
                pass
            self.assertEqual(api.requests, [True, False])

    def test_power_api_never_requests_display_or_away_mode(self):
        dll = MagicMock()
        dll.PowerCreateRequest.return_value = 1234
        dll.PowerSetRequest.return_value = True
        with patch.object(ctypes, "WinDLL", return_value=dll, create=True):
            api = runtime._WindowsPower()
            api.set_required(True)
            api.set_required(False)
        self.assertEqual([call.args[1] for call in dll.PowerSetRequest.call_args_list], [1, 3])
        self.assertEqual([call.args[1] for call in dll.PowerClearRequest.call_args_list], [3, 1])
        dll.CloseHandle.assert_called_once_with(1234)

    def test_query_failure_does_not_interrupt_generation(self):
        api = FakePower()
        api.on_ac = MagicMock(side_effect=OSError("power query unavailable"))
        with patch("sys.stderr", new_callable=io.StringIO):
            with runtime.SleepGuard(api):
                pass
        self.assertNotIn(True, api.requests)

    def test_monitor_start_failure_releases_request(self):
        api = FakePower()
        with patch("generation_runtime.threading.Thread.start", side_effect=RuntimeError("test")), \
                patch("sys.stderr", new_callable=io.StringIO):
            with runtime.SleepGuard(api) as guard:
                self.assertFalse(guard.required)
        self.assertEqual(api.requests, [True, False, False])

    def test_partial_native_acquisition_is_rolled_back(self):
        dll = MagicMock()
        dll.PowerCreateRequest.return_value = 1234
        dll.PowerSetRequest.side_effect = [True, False]
        with patch.object(ctypes, "WinDLL", return_value=dll, create=True), \
                patch.object(ctypes, "get_last_error", return_value=5, create=True), \
                patch.object(ctypes, "WinError", return_value=OSError("test"), create=True):
            api = runtime._WindowsPower()
            with self.assertRaises(OSError):
                api.set_required(True)
        self.assertIsNone(api.handle)
        dll.PowerClearRequest.assert_called_once_with(1234, 1)
        dll.CloseHandle.assert_called_once_with(1234)

    @unittest.skipUnless(sys.platform == "win32", "Native Windows API")
    def test_native_request_handle_is_closed(self):
        api = runtime._WindowsPower()
        with runtime.SleepGuard(api, interval=60) as guard:
            self.assertEqual(guard.required, api.on_ac())
            handle = api.handle
        self.assertIsNone(api.handle)
        if handle is not None:
            api.api.GetHandleInformation.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
            self.assertFalse(api.api.GetHandleInformation(handle, ctypes.byref(ctypes.c_ulong())))

    @unittest.skipUnless(sys.platform == "win32", "Native Windows execution-state query")
    def test_native_sleep_request_does_not_require_display(self):
        power = ctypes.WinDLL("powrprof")
        power.CallNtPowerInformation.argtypes = [
            ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p, ctypes.c_ulong]
        power.CallNtPowerInformation.restype = ctypes.c_ulong

        def state():
            value = ctypes.c_ulong()
            self.assertEqual(power.CallNtPowerInformation(
                16, None, 0, ctypes.byref(value), ctypes.sizeof(value)), 0)
            return value.value

        before = state()
        with runtime.SleepGuard() as guard:
            active = state()
            self.assertEqual(active & 2, before & 2)
            if guard.required:
                self.assertTrue(active & 1)
        self.assertEqual(state(), before)


class NotificationTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch("generation_runtime.build_opener") as opener:
            client = runtime.Notifier()
            client.event("started")
            client.close()
        self.assertIsNone(client.thread)
        opener.assert_not_called()

    def test_invalid_configuration_is_nonfatal_and_generic(self):
        for server, topic in (("http://[", "test"), ("https://user:password@example.org", "test"),
                              ("https://example.org", "bad/topic"), (None, "test")):
            with patch("sys.stderr", new_callable=io.StringIO) as output:
                client = runtime.Notifier(server, topic)
            self.assertIsNone(client.url)
            self.assertNotIn("password", output.getvalue())

    def test_sender_start_failure_does_not_interrupt_generation(self):
        with patch("generation_runtime.threading.Thread.start", side_effect=RuntimeError("test")), \
                patch("sys.stderr", new_callable=io.StringIO):
            client = runtime.Notifier("http://localhost", "test")
            client.event("started")
            client.close()
        self.assertIsNone(client.thread)
        self.assertIsNone(client.url)

    def test_milestones_are_deduplicated_and_time_throttled(self):
        client = runtime.Notifier()
        with patch.object(client, "_enqueue") as enqueue, \
                patch("generation_runtime.time.monotonic", side_effect=[0, 1, 31, 31, 32, 33, 70]):
            for value in (24, 25, 49, 50, 75, 100, 100):
                client.progress(value, 100)
        self.assertEqual([call.args[0] for call in enqueue.call_args_list], [
            "Video generation: frame rendering reached 25%.",
            "Video generation: frame rendering reached 50%.",
            "Video generation: frame rendering reached 100%.",
        ])

    def test_resume_reports_only_current_milestone(self):
        client = runtime.Notifier()
        with patch.object(client, "_enqueue") as enqueue:
            client.progress(56, 100)
        enqueue.assert_called_once_with("Video generation: frame rendering reached 50%.")

    def test_unknown_events_and_stages_cannot_send_arbitrary_content(self):
        client = runtime.Notifier()
        with patch.object(client, "_enqueue") as enqueue:
            client.event("private-script")
            client.stage(r"C:\private\video.mp4")
        enqueue.assert_not_called()

    def test_queue_is_bounded_and_keeps_terminal_status(self):
        client = runtime.Notifier()
        client.url = "http://unused"
        with patch("sys.stderr", new_callable=io.StringIO):
            for _ in range(40):
                client.stage("audio")
            client.event("cancelled")
        self.assertEqual(client.messages.qsize(), 32)
        self.assertIn("Video generation run cancelled.", list(client.messages.queue))

    def test_unresponsive_delivery_has_bounded_shutdown(self):
        entered, release = threading.Event(), threading.Event()

        def blocked(*args, **kwargs):
            entered.set()
            release.wait(5)
            raise OSError("private diagnostic must not be forwarded")

        opener = MagicMock()
        opener.open.side_effect = blocked
        with patch("generation_runtime.build_opener", return_value=opener), \
                patch("sys.stderr", new_callable=io.StringIO) as output:
            client = runtime.Notifier("http://localhost", "test", close_timeout=0.03)
            client.event("started")
            self.assertTrue(entered.wait(1))
            started = time.monotonic()
            client.close()
            self.assertLess(time.monotonic() - started, 0.5)
            release.set()
            client.thread.join(timeout=2)
        self.assertNotIn("private diagnostic", output.getvalue())
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 2.0)

    def test_local_http_delivery_and_error_do_not_leak_details(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append((self.path, self.rfile.read(int(self.headers["Content-Length"])),
                                 self.headers.get("Authorization")))
                self.send_response(500 if len(received) == 2 else 200)
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch("sys.stderr", new_callable=io.StringIO):
                client = runtime.Notifier(f"http://127.0.0.1:{server.server_port}", "runtime-test",
                                          token="synthetic-token")
                client.event("started")
                client.stage("audio")
                client.event("completed")
                client.close()
            self.assertEqual(len(received), 3)
            self.assertTrue(all(path == "/runtime-test" for path, _, _ in received))
            self.assertEqual(received[0][1], b"Video generation run started.")
            self.assertEqual(received[-1][1], b"Video generation run completed.")
            self.assertTrue(all(auth == "Bearer synthetic-token" for _, _, auth in received))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_redirect_is_not_followed(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                received.append(self.path)
                self.send_response(302)
                self.send_header("Location", "/unexpected-target")
                self.end_headers()

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with patch("sys.stderr", new_callable=io.StringIO):
                client = runtime.Notifier(f"http://127.0.0.1:{server.server_port}", "original")
                client.event("started")
                client.close()
            self.assertEqual(received, ["/original"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {}, clear=True)
        self.env.start()
        self.client = MagicMock()
        self.client_patch = patch("generation_runtime.Notifier.from_environment", return_value=self.client)
        self.client_patch.start()
        self.guard = MagicMock()
        self.guard_patch = patch("generation_runtime.SleepGuard", return_value=self.guard)
        self.guard_patch.start()

    def tearDown(self):
        self.guard_patch.stop()
        self.client_patch.stop()
        self.env.stop()
        runtime._CANCELLING.clear()

    def test_nested_runs_have_one_owner_and_one_terminal_event(self):
        original = signal.getsignal(signal.SIGTERM)
        with runtime.GenerationRun():
            self.assertIn(runtime._PARENT, os.environ)
            with runtime.GenerationRun():
                runtime.stage_completed("audio")
            runtime.stage_completed("review")
        self.assertEqual([call.args[0] for call in self.client.event.call_args_list], ["started", "completed"])
        self.client.stage.assert_called_once_with("review", False)
        self.guard.__enter__.assert_called_once()
        self.guard.__exit__.assert_called_once()
        self.assertNotIn(runtime._PARENT, os.environ)
        self.assertEqual(signal.getsignal(signal.SIGTERM), original)

    def test_failure_and_cancellation_are_distinct(self):
        for error, expected in ((ValueError("private detail"), "failed"),
                                (KeyboardInterrupt(), "cancelled"), (SystemExit(130), "cancelled")):
            self.client.reset_mock()
            try:
                with runtime.GenerationRun():
                    raise error
            except (ValueError, KeyboardInterrupt, SystemExit):
                pass
            self.assertEqual([call.args[0] for call in self.client.event.call_args_list], ["started", expected])
            self.guard.__exit__.assert_called()

    def test_child_process_context_has_no_duplicate_lifecycle(self):
        os.environ[runtime._PARENT] = "synthetic-parent"
        with runtime.GenerationRun():
            runtime.render_progress(75, 100)
        self.client.event.assert_not_called()
        self.guard.__enter__.assert_not_called()
        self.client.progress.assert_called_once_with(75, 100)
        self.client.close.assert_called_once()

    def test_child_context_forwards_pipeline_stages_and_handles_cancellation(self):
        os.environ[runtime._PARENT] = "synthetic-parent"
        original = signal.getsignal(signal.SIGTERM)
        with runtime.GenerationRun():
            self.assertEqual(signal.getsignal(signal.SIGTERM), runtime.GenerationRun._cancel)
            runtime.stage_completed("audio", force=True)
        self.client.stage.assert_called_once_with("audio", False)
        self.client.event.assert_not_called()
        self.assertEqual(signal.getsignal(signal.SIGTERM), original)

    def test_bootstrap_cleanup_uses_selected_python_without_local_psutil(self):
        process = None
        real_import = __import__

        def bootstrap_import(name, *args, **kwargs):
            if name == "psutil":
                raise ImportError("simulated bootstrap interpreter")
            return real_import(name, *args, **kwargs)

        try:
            with runtime.GenerationRun(cleanup_python=sys.executable):
                process = runtime.start_process([
                    sys.executable, "-u", "-c",
                    "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c',"
                    "'import time; time.sleep(30)']); print(p.pid,flush=True); time.sleep(30)"
                ], stdout=subprocess.PIPE, text=True)
                child_pid = int(process.stdout.readline())
                with patch("builtins.__import__", side_effect=bootstrap_import), \
                        patch("generation_runtime.subprocess.run", wraps=subprocess.run) as helper:
                    runtime.stop_processes([process])
                self.assertEqual(helper.call_args.args[0][0], sys.executable)
                self.assertIsNotNone(process.poll())
                try:
                    self.assertEqual(psutil.Process(child_pid).status(), psutil.STATUS_ZOMBIE)
                except psutil.NoSuchProcess:
                    pass
        finally:
            if process is not None:
                runtime.forget_process(process)
                process.wait(timeout=3)
                process.stdout.close()

    def test_cancellation_reaps_only_owned_subprocess_tree(self):
        unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        process = None
        try:
            with self.assertRaises(KeyboardInterrupt):
                with runtime.GenerationRun():
                    process = runtime.start_process([
                        sys.executable, "-u", "-c",
                        "import subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c',"
                        "'import time; time.sleep(30)']); print(p.pid,flush=True); time.sleep(30)"
                    ], stdout=subprocess.PIPE, text=True)
                    child_pid = int(process.stdout.readline())
                    raise KeyboardInterrupt
            self.assertIsNone(unrelated.poll())
            for pid in (process.pid, child_pid):
                try:
                    self.assertEqual(psutil.Process(pid).status(), psutil.STATUS_ZOMBIE)
                except psutil.NoSuchProcess:
                    pass
        finally:
            if process is not None:
                runtime.forget_process(process)
                process.wait(timeout=3)
                process.stdout.close()
            unrelated.terminate()
            unrelated.wait(timeout=3)

    def test_run_process_preserves_capture_check_and_timeout(self):
        with runtime.GenerationRun():
            result = runtime.run_process([sys.executable, "-c", "print('ok')"], capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), "ok")
            with self.assertRaises(subprocess.CalledProcessError):
                runtime.run_process([sys.executable, "-c", "raise SystemExit(2)"], check=True)
            with self.assertRaises(subprocess.TimeoutExpired):
                runtime.run_process([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.1)


if __name__ == "__main__":
    unittest.main()
