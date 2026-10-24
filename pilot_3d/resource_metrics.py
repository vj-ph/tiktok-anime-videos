"""Best-effort local resource samples; unavailable GPU counters remain null."""

import ctypes
from ctypes import wintypes
from pathlib import Path
import re
import sys

import psutil


class _WindowsGpu:
    def __init__(self):
        class Number(ctypes.Union):
            _fields_ = [("double", ctypes.c_double), ("integer", ctypes.c_longlong),
                        ("text", ctypes.c_void_p)]

        class Value(ctypes.Structure):
            _fields_ = [("status", wintypes.DWORD), ("number", Number)]

        class Item(ctypes.Structure):
            _fields_ = [("name", wintypes.LPWSTR), ("value", Value)]

        self.item = Item
        self.api = ctypes.WinDLL("pdh")
        self.api.PdhOpenQueryW.argtypes = [wintypes.LPCWSTR, ctypes.c_size_t,
                                          ctypes.POINTER(wintypes.HANDLE)]
        self.api.PdhAddEnglishCounterW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, ctypes.c_size_t,
                                                 ctypes.POINTER(wintypes.HANDLE)]
        self.api.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
        self.api.PdhGetFormattedCounterArrayW.argtypes = [
            wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD),
            ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        self.api.PdhCloseQuery.argtypes = [wintypes.HANDLE]
        self.query = wintypes.HANDLE()
        if self.api.PdhOpenQueryW(None, 0, ctypes.byref(self.query)):
            raise OSError("GPU performance query unavailable")
        self.counters = {}
        try:
            for name, path in {
                "engines": r"\GPU Engine(*)\Utilization Percentage",
                "dedicated_bytes": r"\GPU Process Memory(*)\Dedicated Usage",
                "shared_bytes": r"\GPU Process Memory(*)\Shared Usage",
            }.items():
                counter = wintypes.HANDLE()
                if not self.api.PdhAddEnglishCounterW(self.query, path, 0, ctypes.byref(counter)):
                    self.counters[name] = counter
            self.api.PdhCollectQueryData(self.query)
        except BaseException:
            self.close()
            raise

    def _values(self, counter):
        size, count = wintypes.DWORD(), wintypes.DWORD()
        result = self.api.PdhGetFormattedCounterArrayW(
            counter, 0x200, ctypes.byref(size), ctypes.byref(count), None)
        if (result & 0xFFFFFFFF) != 0x800007D2 or not size.value:
            return []
        buffer = ctypes.create_string_buffer(size.value)
        if self.api.PdhGetFormattedCounterArrayW(
                counter, 0x200, ctypes.byref(size), ctypes.byref(count), buffer):
            return []
        items = ctypes.cast(buffer, ctypes.POINTER(self.item))
        return [(items[i].name, items[i].value.number.double) for i in range(count.value)
                if items[i].value.status in (0, 1)]

    def sample(self, pids):
        result = {"engines": {}, "dedicated_bytes": None, "shared_bytes": None}
        self.api.PdhCollectQueryData(self.query)
        for key, counter in self.counters.items():
            values = []
            for name, value in self._values(counter):
                match = re.match(r"pid_(\d+)_(.+)", name)
                if match and int(match[1]) in pids:
                    values.append(value)
                    if key == "engines":
                        engine = match[2]
                        result["engines"][engine] = result["engines"].get(engine, 0) + value
            if key != "engines" and values:
                result[key] = sum(values)
        return result

    def close(self):
        if self.query:
            self.api.PdhCloseQuery(self.query)
            self.query = None


class ResourceSampler:
    def __init__(self, pids):
        self.processes = [psutil.Process(pid) for pid in pids]
        self.gpu = None
        if sys.platform == "win32":
            try:
                self.gpu = _WindowsGpu()
            except (OSError, AttributeError):
                pass
        self.amd = list(Path("/sys/class/drm").glob("card[0-9]*/device/gpu_busy_percent")) \
            if sys.platform.startswith("linux") else []
        psutil.cpu_percent()

    def sample(self):
        memory = 0
        for process in self.processes:
            try:
                memory += process.memory_info().rss
            except psutil.Error:
                pass
        result = {"cpu_percent": psutil.cpu_percent(),
                  "system_available_bytes": psutil.virtual_memory().available,
                  "worker_resident_bytes": memory, "gpu_busiest_engine_percent": None,
                  "gpu_owned_engine_activity_index": None,
                  "gpu_dedicated_bytes": None, "gpu_shared_bytes": None}
        if self.gpu is not None:
            gpu = self.gpu.sample({process.pid for process in self.processes})
            # Process counters can overlap, so their sum is not physical GPU utilization.
            result.update(gpu_owned_engine_activity_index=max(gpu["engines"].values(), default=None),
                          gpu_engines=gpu["engines"], gpu_dedicated_bytes=gpu["dedicated_bytes"],
                          gpu_shared_bytes=gpu["shared_bytes"])
        elif self.amd:
            try:
                devices = [{"busy": float(path.read_text(encoding="utf-8")),
                            "vram": float((path.parent / "mem_info_vram_used").read_text(encoding="utf-8")),
                            "gtt": float((path.parent / "mem_info_gtt_used").read_text(encoding="utf-8"))}
                           for path in self.amd]
                result.update(gpu_busiest_engine_percent=max(d["busy"] for d in devices),
                              gpu_dedicated_bytes=sum(d["vram"] for d in devices),
                              gpu_shared_bytes=sum(d["gtt"] for d in devices))
            except (OSError, ValueError):
                pass
        return result

    def close(self):
        if self.gpu is not None:
            self.gpu.close()
