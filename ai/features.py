"""Fitur untuk klasifikasi kejadian (input model AI).

Telemetry dari dua edge digabung menjadi satu 'window' waktu (3 detik terakhir),
lalu diringkas menjadi 6 angka.
"""
from collections import deque

WINDOW_S = 3.0

FEATURES = [
    "angle_change",   # |sudut akhir - sudut awal| (derajat): pintu berpindah berapa jauh
    "angle_range",    # sudut maks - sudut min (derajat): ada ayunan atau tidak
    "rms_max",        # getaran terbesar di window (m/s2)
    "rms_mean",       # rata-rata getaran di window (m/s2)
    "lux_delta_max",  # lonjakan cahaya terbesar terhadap baseline (lux)
    "lux_range",      # lux maks - lux min di window
]

LABELS = ["DIAM", "BUKA_NORMAL", "DIPAKSA", "KETUKAN", "CAHAYA_SAJA"]


class FeatureWindow:
    """Menyimpan gabungan data terbaru kedua edge dan menghitung fitur."""

    def __init__(self, window_s: float = WINDOW_S):
        self.window_s = window_s
        self._buf = deque()
        self._angle = self._rms = self._lux = self._delta = None

    def update_door(self, t: float, angle: float, rms: float) -> None:
        self._angle, self._rms = angle, rms
        self._append(t)

    def update_light(self, t: float, lux: float, delta: float) -> None:
        self._lux, self._delta = lux, delta
        self._append(t)

    def _append(self, t: float) -> None:
        if None in (self._angle, self._rms, self._lux, self._delta):
            return  # tunggu sampai kedua edge sudah mengirim data
        self._buf.append((t, self._angle, self._rms, self._lux, self._delta))

    def _trim(self, now: float) -> None:
        while self._buf and now - self._buf[0][0] > self.window_s:
            self._buf.popleft()

    def features(self, now: float):
        """List 6 fitur sesuai urutan FEATURES, atau None bila data belum cukup."""
        self._trim(now)
        if len(self._buf) < 2:
            return None
        angles = [b[1] for b in self._buf]
        rms = [b[2] for b in self._buf]
        lux = [b[3] for b in self._buf]
        delta = [b[4] for b in self._buf]
        return [
            abs(angles[-1] - angles[0]),
            max(angles) - min(angles),
            max(rms),
            sum(rms) / len(rms),
            max(delta),
            max(lux) - min(lux),
        ]
