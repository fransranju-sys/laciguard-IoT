"""Membaca sensor HP Android lewat Termux:API (atau simulator untuk debugging).

Catatan: simulator TIDAK dihitung sebagai edge fisik. Pakai hanya untuk latihan.
"""
from __future__ import annotations

import json
import os
import random
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class MotionSample:
    seconds: float  # waktu monotonic
    accel: tuple    # (x, y, z) m/s^2
    gyro: tuple     # (x, y, z) rad/s


@dataclass(frozen=True)
class LightSample:
    seconds: float
    lux: float


# --------------------------------------------------------------------------
# Util parsing output termux-sensor
# --------------------------------------------------------------------------
def iter_json_objects(buffer: str):
    """Ambil semua objek JSON utuh dari buffer.

    termux-sensor mode stream mencetak banyak objek JSON berurutan (tanpa koma),
    jadi json.loads biasa tidak cukup. Return (list_objek, sisa_buffer).
    """
    decoder = json.JSONDecoder()
    objs, idx, n = [], 0, len(buffer)
    while True:
        while idx < n and buffer[idx].isspace():
            idx += 1
        if idx >= n:
            break
        if buffer[idx] != "{":
            nxt = buffer.find("{", idx)
            if nxt == -1:
                idx = n
                break
            idx = nxt
        try:
            obj, end = decoder.raw_decode(buffer, idx)
        except json.JSONDecodeError:
            break  # objek belum lengkap, tunggu data berikutnya
        objs.append(obj)
        idx = end
    rest = buffer[idx:]
    if len(rest) > 200_000:  # pengaman: buang sampah
        rest = ""
    return objs, rest


def list_sensors() -> list:
    out = subprocess.run(
        ["termux-sensor", "-l"], capture_output=True, text=True, timeout=12, check=True
    ).stdout
    return json.loads(out)["sensors"]


def find_sensor(names, keyword: str, exclude=("uncalibrated",)):
    """Cari nama sensor yang memuat keyword; utamakan varian 'Non-wakeup'."""
    kw = keyword.lower()
    cands = [
        n for n in names
        if kw in n.lower() and not any(e in n.lower() for e in exclude)
    ]
    cands.sort(key=lambda n: ("wakeup" in n.lower() and "non-wakeup" not in n.lower()))
    return cands[0] if cands else None


# --------------------------------------------------------------------------
# Pembaca latar belakang: simpan nilai terbaru tiap sensor
# --------------------------------------------------------------------------
class TermuxSensorReader:
    """Menjalankan termux-sensor di thread terpisah dan menyimpan nilai terbaru.

    mode "stream": satu proses termux-sensor terus berjalan (-d ms), cepat.
    mode "poll"  : memanggil `termux-sensor -n 1` berulang (lambat, tapi paling
                   aman bila stream bermasalah di HP kamu).
    """

    def __init__(self, sensor_names, mode: str = "stream", delay_ms: int = 50):
        self.names = list(sensor_names)
        self.mode = mode
        self.delay_ms = delay_ms
        self._latest = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._proc = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._proc is not None:
            try:
                self._proc.terminate()
            except OSError:
                pass

    def latest(self, name: str, max_age=None):
        """Nilai terbaru (tuple) atau None. max_age=None -> tidak dibatasi umur.

        Sensor cahaya biasanya hanya mengirim saat nilai berubah, jadi untuk
        cahaya pakai max_age=None (nilai terakhir yang diketahui).
        """
        with self._lock:
            item = self._latest.get(name)
        if item is None:
            return None
        t, values = item
        if max_age is not None and time.monotonic() - t > max_age:
            return None
        return values

    def _store(self, obj: dict):
        now = time.monotonic()
        with self._lock:
            for name, payload in obj.items():
                vals = payload.get("values") if isinstance(payload, dict) else None
                if vals:
                    self._latest[name] = (now, tuple(float(v) for v in vals))

    def _run(self):
        if self.mode == "poll":
            self._run_poll()
        else:
            self._run_stream()

    def _run_stream(self):
        cmd = ["termux-sensor", "-s", ",".join(self.names), "-d", str(self.delay_ms)]
        self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        fd = self._proc.stdout.fileno()
        buf = ""
        while not self._stop.is_set():
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            buf += chunk.decode("utf-8", errors="ignore")
            objs, buf = iter_json_objects(buf)
            for obj in objs:
                self._store(obj)

    def _run_poll(self):
        cmd = ["termux-sensor", "-s", ",".join(self.names), "-n", "1"]
        while not self._stop.is_set():
            try:
                out = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=12, check=True
                ).stdout
            except (subprocess.SubprocessError, OSError):
                time.sleep(1.0)
                continue
            objs, _ = iter_json_objects(out)
            for obj in objs:
                self._store(obj)


# --------------------------------------------------------------------------
# Sumber data: Termux (HP asli)
# --------------------------------------------------------------------------
class TermuxMotionSource:
    name = "termux"

    def __init__(self, mode: str = "stream"):
        names = list_sensors()
        self.accel_name = find_sensor(names, "accelerometer")
        self.gyro_name = find_sensor(names, "gyroscope")
        if not self.accel_name or not self.gyro_name:
            raise RuntimeError("Accelerometer/gyroscope tidak ditemukan. Cek: termux-sensor -l")
        self.reader = TermuxSensorReader([self.accel_name, self.gyro_name], mode)
        self.reader.start()

    def read(self):
        a = self.reader.latest(self.accel_name, max_age=2.0)
        g = self.reader.latest(self.gyro_name, max_age=2.0)
        if a is None or g is None:
            return None
        return MotionSample(time.monotonic(), tuple(a[:3]), tuple(g[:3]))

    def stop(self):
        self.reader.stop()


class TermuxLightSource:
    name = "termux"

    def __init__(self, mode: str = "stream"):
        names = list_sensors()
        self.light_name = find_sensor(names, "light")
        if not self.light_name:
            raise RuntimeError("Sensor cahaya tidak ditemukan. Cek: termux-sensor -l")
        self.reader = TermuxSensorReader([self.light_name], mode, delay_ms=200)
        self.reader.start()

    def read(self):
        v = self.reader.latest(self.light_name)  # nilai terakhir (on-change)
        if v is None:
            return None
        return LightSample(time.monotonic(), float(v[0]))

    def stop(self):
        self.reader.stop()


# --------------------------------------------------------------------------
# Simulator (debugging di laptop)
# --------------------------------------------------------------------------
class SimulatedMotionSource:
    """scenario: still | open | force. Kejadian dimulai event_after detik setelah start."""

    name = "simulator"

    def __init__(self, scenario: str = "open", event_after: float = 40.0):
        self.scenario, self.event_after = scenario, event_after
        self._t0 = time.monotonic()

    def read(self):
        now = time.monotonic()
        t = now - self._t0 - self.event_after
        g = random.gauss
        accel_noise, yaw = 0.03, 0.0
        if self.scenario == "open" and 0 <= t < 2.0:
            yaw, accel_noise = 0.7, 1.0      # ~80 derajat dalam 2 detik
        elif self.scenario == "force" and 0 <= t < 1.5:
            yaw, accel_noise = 1.5, 5.0      # dihentak keras
        accel = (g(0, accel_noise), g(0, accel_noise), 9.81 + g(0, accel_noise))
        gyro = (g(0, 0.005), g(0, 0.005), yaw + g(0, 0.005))
        return MotionSample(now, accel, gyro)

    def stop(self):
        pass


class SimulatedLightSource:
    name = "simulator"

    def __init__(self, scenario: str = "open", event_after: float = 40.0):
        self.scenario, self.event_after = scenario, event_after
        self._t0 = time.monotonic()

    def read(self):
        now = time.monotonic()
        t = now - self._t0 - self.event_after
        lux = 2.0 + random.gauss(0, 0.2)
        if self.scenario in ("open", "force") and t >= 0.5:
            lux = 80.0 + random.gauss(0, 2.0)
        return LightSample(now, max(0.0, lux))

    def stop(self):
        pass


def _auto(kind: str) -> str:
    if kind == "auto":
        return "termux" if shutil.which("termux-sensor") else "simulator"
    return kind


def make_motion_source(kind="auto", scenario="open", event_after=40.0, mode="stream"):
    if _auto(kind) == "termux":
        return TermuxMotionSource(mode)
    return SimulatedMotionSource(scenario, event_after)


def make_light_source(kind="auto", scenario="open", event_after=40.0, mode="stream"):
    if _auto(kind) == "termux":
        return TermuxLightSource(mode)
    return SimulatedLightSource(scenario, event_after)
