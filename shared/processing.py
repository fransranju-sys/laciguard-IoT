"""Pengolahan data LaciGuard.

Edge 1 (pintu)  : A. RMS getaran          B. Sudut pintu (integral gyroscope)
Edge 2 (dalam)  : C. Rata-rata bergerak lux  D. Perubahan cahaya (light_delta)
Detector        : E. Kalibrasi adaptif (mean + z * std)
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass
from statistics import fmean, pstdev
from typing import Sequence

GRAVITY = 9.81


def _norm(v) -> float:
    return math.sqrt(sum(c * c for c in v))


def _dot(a, b) -> float:
    return sum(x * y for x, y in zip(a, b))


# --------------------------------------------------------------------------
# A. RMS getaran (accelerometer)
# --------------------------------------------------------------------------
def motion_rms(samples: Sequence) -> float:
    """RMS selisih antara besar percepatan dan gravitasi (m/s^2).

    HP diam -> ~0. Pintu dibuka/dihentak -> naik.
    """
    if not samples:
        return 0.0
    errors = [_norm(s.accel) - GRAVITY for s in samples]
    return math.sqrt(sum(e * e for e in errors) / len(errors))


# --------------------------------------------------------------------------
# B. Sudut pintu (gyroscope + arah gravitasi)
# --------------------------------------------------------------------------
class DoorAngleTracker:
    """Menghitung sudut buka pintu dengan mengintegrasikan gyroscope.

    Asumsi: engsel pintu VERTIKAL (pintu kamar, lemari baju), sehingga pintu
    berputar mengelilingi arah gravitasi. Arah gravitasi diambil dari rata-rata
    accelerometer, jadi HP boleh ditempel dengan orientasi apa pun.

        yaw_rate = gyro . arah_vertikal      (rad/s, bertanda)
        sudut   += yaw_rate * dt             (membuka +, menutup -)

    Pengaman drift:
      * dead-zone: laju putar kecil dianggap noise/bias, tidak diintegrasikan
      * snap-to-zero: dekat 0 derajat dan diam -> sudut direset ke 0
    """

    def __init__(self, deadzone: float = 0.04, snap_deg: float = 3.0, max_dt: float = 1.0):
        self.deadzone = deadzone
        self.snap_deg = snap_deg
        self.max_dt = max_dt
        self.angle_deg = 0.0  # bertanda

    def update(self, samples: Sequence) -> float:
        """Proses satu window sampel. Return sudut (derajat, nilai mutlak)."""
        if len(samples) < 2:
            return abs(self.angle_deg)
        n = len(samples)
        mean_acc = tuple(sum(s.accel[i] for s in samples) / n for i in range(3))
        norm = _norm(mean_acc)
        if norm < 1e-6:
            return abs(self.angle_deg)
        up = tuple(c / norm for c in mean_acc)

        moving = False
        for prev, cur in zip(samples, samples[1:]):
            dt = cur.seconds - prev.seconds
            if dt <= 0 or dt > self.max_dt:  # lewati celah data
                continue
            rate = _dot(cur.gyro, up)
            if abs(rate) < self.deadzone:
                continue
            self.angle_deg += math.degrees(rate * dt)
            moving = True

        if not moving and abs(self.angle_deg) < self.snap_deg:
            self.angle_deg = 0.0
        return abs(self.angle_deg)


# --------------------------------------------------------------------------
# C & D. Cahaya
# --------------------------------------------------------------------------
class LightProcessor:
    """C. light_lux   = rata-rata bergerak dari beberapa window terakhir
    D. light_delta = light_lux dikurangi baseline lambat (EMA) -> deteksi lonjakan
    """

    def __init__(self, history: int = 3, baseline_alpha: float = 0.02):
        self._means = deque(maxlen=history)
        self._alpha = baseline_alpha
        self._baseline = None

    def update(self, lux_values: Sequence[float]):
        """Return (light_lux, light_delta)."""
        if not lux_values:
            return (self._means[-1] if self._means else 0.0), 0.0
        self._means.append(fmean(lux_values))
        smooth = fmean(self._means)
        if self._baseline is None:
            self._baseline = smooth
        delta = smooth - self._baseline
        self._baseline += self._alpha * (smooth - self._baseline)
        return smooth, delta


# --------------------------------------------------------------------------
# E. Kalibrasi adaptif
# --------------------------------------------------------------------------
@dataclass(frozen=True)
class Baseline:
    mean: float
    std: float
    n: int


class Calibrator:
    """Mengumpulkan nilai saat kalibrasi lalu menghitung mean dan std."""

    def __init__(self):
        self._values = []

    def add(self, value: float) -> None:
        self._values.append(float(value))

    def __len__(self) -> int:
        return len(self._values)

    def fit(self) -> Baseline:
        if not self._values:
            raise ValueError("belum ada data kalibrasi")
        return Baseline(fmean(self._values), pstdev(self._values), len(self._values))


def threshold(base: Baseline, z: float, std_floor: float, margin: float) -> float:
    """Ambang adaptif: mean + max(z * max(std, std_floor), margin).

    std_floor mencegah ambang terlalu sempit saat data kalibrasi sangat stabil;
    margin adalah kenaikan minimum agar noise kecil tidak memicu deteksi.
    """
    return base.mean + max(z * max(base.std, std_floor), margin)


def z_score(value: float, base: Baseline, std_floor: float = 1e-6) -> float:
    return (value - base.mean) / max(base.std, std_floor)
