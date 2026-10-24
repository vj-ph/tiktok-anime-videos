import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from benchmark_workers import benchmark, check_limits, recommendation, select_frames, summarize_trial
from resource_metrics import ResourceSampler, _WindowsGpu


class BenchmarkTests(unittest.TestCase):
    def test_memory_and_time_limits_fail_before_more_work_is_started(self):
        with patch("benchmark_workers.time.monotonic", return_value=100):
            with self.assertRaisesRegex(RuntimeError, "time limit"):
                check_limits(0, 10, 4)
        with patch("benchmark_workers.time.monotonic", return_value=1), \
                patch("psutil.virtual_memory", return_value=MagicMock(available=3 * 2**30)):
            with self.assertRaisesRegex(RuntimeError, "Free RAM"):
                check_limits(0, 10, 4)

    def test_gpu_counters_only_combine_owned_pids_on_the_same_engine(self):
        gpu = _WindowsGpu.__new__(_WindowsGpu)
        gpu.api = MagicMock()
        gpu.query = 1
        gpu.counters = {"engines": "usage", "dedicated_bytes": "memory"}
        values = {
            "usage": [("pid_11_luid_adapter_eng_0", 36), ("pid_22_luid_adapter_eng_0", 34),
                      ("pid_33_luid_adapter_eng_0", 90), ("pid_11_luid_adapter_eng_1", 2)],
            "memory": [("pid_11_luid_adapter", 100), ("pid_22_luid_adapter", 200),
                       ("pid_33_luid_adapter", 900)],
        }
        gpu._values = lambda counter: values[counter]
        result = gpu.sample({11, 22})
        self.assertEqual(result["engines"], {"luid_adapter_eng_0": 70, "luid_adapter_eng_1": 2})
        self.assertEqual(result["dedicated_bytes"], 300)

    def test_frames_are_unique_evenly_spaced_and_on_the_native_clock(self):
        frames = select_frames(4555, 2, 48)
        self.assertEqual((frames[0], frames[-1]), (1, 4555))
        self.assertEqual(len(set(frames)), 48)
        self.assertTrue(all(frame % 2 == 1 for frame in frames))
        with self.assertRaises(ValueError):
            select_frames(3, 2, 3)

    def test_windows_process_activity_is_not_reported_as_physical_gpu_utilization(self):
        processes = [MagicMock(pid=11), MagicMock(pid=22)]
        for process in processes:
            process.memory_info.return_value = MagicMock(rss=100)
        gpu = MagicMock()
        with patch("resource_metrics.sys.platform", "win32"), \
                patch("resource_metrics.psutil.Process", side_effect=processes), \
                patch("resource_metrics.psutil.cpu_percent", return_value=1), \
                patch("resource_metrics.psutil.virtual_memory", return_value=MagicMock(available=16 * 2**30)), \
                patch("resource_metrics._WindowsGpu", return_value=gpu):
            sampler = ResourceSampler([11, 22])
            for activity in (70, 180):
                gpu.sample.return_value = {"engines": {"engine0": activity, "engine1": 2},
                                           "dedicated_bytes": 300, "shared_bytes": 400}
                result = sampler.sample()
                self.assertIsNone(result["gpu_busiest_engine_percent"])
                self.assertEqual(result["gpu_owned_engine_activity_index"], activity)
                self.assertEqual(result["gpu_dedicated_bytes"], 300)
                self.assertEqual(result["worker_resident_bytes"], 200)
                gpu.sample.assert_called_with({11, 22})
            sampler.close()
        gpu.close.assert_called_once()

    def test_aggregate_warm_rate_is_not_sum_of_per_worker_rates(self):
        records = [
            {"frames": [{"started": 1, "finished": 5}, {"started": 5, "finished": 7},
                        {"started": 7, "finished": 9}]},
            {"frames": [{"started": 2, "finished": 6}, {"started": 6, "finished": 8},
                        {"started": 8, "finished": 10}]},
        ]
        samples = [{"at": 7, "cpu_percent": 50, "worker_resident_bytes": 100,
                    "gpu_busiest_engine_percent": 70, "gpu_owned_engine_activity_index": 180}]
        report = summarize_trial(records, 0, 11, samples)
        self.assertEqual(report["warm_frames"], 4)
        self.assertEqual(report["warm_elapsed_seconds"], 5)
        self.assertEqual(report["warm_frames_per_minute"], 48)
        self.assertEqual(report["cold_start_seconds_until_all_first_frames"], 6)
        self.assertEqual(report["warm_metrics"]["gpu_busiest_engine_percent"]["mean"], 70)
        self.assertEqual(report["warm_metrics"]["gpu_owned_engine_activity_index"]["mean"], 180)
        self.assertIsNone(report["warm_metrics"]["gpu_shared_bytes"])

    def test_recommendation_requires_all_verified_trials_and_uses_median(self):
        trials = [
            {"jobs": 1, "verified": True, "summary": {"warm_frames_per_minute": 60}},
            {"jobs": 1, "verified": True, "summary": {"warm_frames_per_minute": 62}},
            {"jobs": 2, "verified": True, "summary": {"warm_frames_per_minute": 70}},
            {"jobs": 2, "verified": True, "summary": {"warm_frames_per_minute": 72}},
            {"jobs": 4, "verified": True, "summary": {"warm_frames_per_minute": 100}},
            {"jobs": 4, "verified": False, "summary": {"warm_frames_per_minute": 101}},
        ]
        result = recommendation(trials, [1, 2, 4], 2)
        self.assertEqual(result["jobs"], 2)
        self.assertEqual(result["candidates"][0]["median_warm_frames_per_minute"], 71)

    def test_isolated_outputs_preserve_source_and_reverse_repeat_order(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            timeline = {"total_frames": 48}
            (source / "studio.blend").write_bytes(b"synthetic scene")
            (source / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            (source / "scene_manifest.json").write_text(
                json.dumps({"timeline": timeline, "motion_step": 2}), encoding="utf-8")
            original = {path.name: path.read_bytes() for path in source.iterdir()}
            output = Path(directory) / "benchmark"

            def trial(source, output, frames, jobs, threads, backend, **limits):
                self.assertEqual(frames, select_frames(48, 2, 12))
                return {"jobs": jobs, "verified": True, "scene_settings": {"samples": 2},
                        "summary": {"warm_frames_per_minute": 100 / jobs}}

            with patch("benchmark_workers.run_trial", side_effect=trial) as run:
                report = benchmark(source, output, frame_count=12)
            self.assertEqual([call.args[3] for call in run.call_args_list], [1, 2, 4, 4, 2, 1])
            self.assertEqual(report["recommendation"]["jobs"], 1)
            self.assertTrue(report["complete"])
            self.assertEqual({path.name: path.read_bytes() for path in source.iterdir()}, original)
            self.assertTrue((output / "benchmark.json").is_file())
            with self.assertRaises(ValueError):
                benchmark(source, source / "nested", frame_count=12)
            with self.assertRaises(ValueError):
                benchmark(source, output, frame_count=12)

    def test_eight_worker_guard_failure_is_not_recommended_and_other_trials_continue(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            timeline = {"total_frames": 48}
            (source / "studio.blend").write_bytes(b"synthetic production scene")
            (source / "timeline.json").write_text(json.dumps(timeline), encoding="utf-8")
            (source / "scene_manifest.json").write_text(
                json.dumps({"timeline": timeline, "motion_step": 1, "width": 720,
                            "height": 1280, "samples": 16, "quality": "production"}), encoding="utf-8")
            output = Path(directory) / "benchmark"

            def trial(source, output, frames, jobs, threads, backend, **limits):
                if jobs == 8:
                    raise RuntimeError("Free RAM safety reserve")
                return {"jobs": jobs, "verified": True, "scene_settings": {"samples": 16},
                        "summary": {"warm_frames_per_minute": jobs * 10}}

            with patch("benchmark_workers.run_trial", side_effect=trial) as run:
                with self.assertRaisesRegex(RuntimeError, "could not be verified"):
                    benchmark(source, output, jobs=[2, 4, 8], frame_count=24,
                              expected_profile="production")
            report = json.loads((output / "benchmark.json").read_text(encoding="utf-8"))
            self.assertTrue(report["complete"])
            self.assertFalse(report["all_trials_verified"])
            self.assertEqual(report["recommendation"]["jobs"], 4)
            self.assertEqual([call.args[3] for call in run.call_args_list], [2, 4, 8, 8, 4, 2])
            self.assertTrue(all(not trial["verified"] for trial in report["trials"] if trial["jobs"] == 8))
            with self.assertRaisesRegex(ValueError, "quality profile"):
                benchmark(source, Path(directory) / "bad-profile", jobs=[2], frame_count=6,
                          expected_profile="preview")


if __name__ == "__main__":
    unittest.main()
