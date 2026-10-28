"""Algoritma keputusan LaciGuard: sensor fusion + state machine ARM/DISARM.

Sensor fusion lintas jenis sensor:
    Edge 1 (gerak pintu)  +  Edge 2 (cahaya di dalam)  ->  keputusan

State machine:
    DISARMED --arm--> CALIBRATING --selesai--> ARMED
    ARMED --pintu terbuka + cahaya naik--> ENTRY_DELAY --habis--> ALARM
    ARMED --hentakan keras + (terbuka/cahaya)--------------------> ALARM
    (state apa pun) --disarm--> DISARMED

Modul ini murni logika (tidak membaca jam sendiri, tidak memakai MQTT):
waktu dikirim lewat parameter `now`, sehingga mudah diuji.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from shared.processing import Calibrator, threshold


class State(str, Enum):
    DISARMED = "DISARMED"
    CALIBRATING = "CALIBRATING"
    ARMED = "ARMED"
    ENTRY_DELAY = "ENTRY_DELAY"
    ALARM = "ALARM"


@dataclass(frozen=True)
class RuleConfig:
    calibration_s: float = 10.0   # lama kalibrasi setelah ARM
    entry_delay_s: float = 10.0   # waktu pemilik untuk DISARM
    stale_s: float = 6.0          # data lebih tua dari ini dianggap tidak segar
    min_cal_samples: int = 3      # minimal data per edge agar kalibrasi sah

    nudge_deg: float = 3.0        # sudut minimal = pintu "digerakkan"
    open_deg: float = 10.0        # sudut minimal = pintu "terbuka"
    force_rms: float = 3.0        # RMS (m/s^2) = hentakan/paksa

    z_threshold: float = 3.0      # ambang = mean + z * std
    rms_std_floor: float = 0.05
    rms_margin: float = 0.4       # kenaikan RMS minimum (m/s^2)
    light_std_floor: float = 1.0
    light_margin: float = 5.0     # kenaikan cahaya minimum (lux)


@dataclass(frozen=True)
class Decision:
    status: str   # AMAN | KALIBRASI | MENUNGGU_DATA | PINTU_DIGERAKKAN |
                  # MENUNGGU_DISARM | ALERT_DIBUKA | ALERT_DIPAKSA
    state: State
    reason: str


@dataclass
class _Door:
    t: float
    angle_deg: float
    rms: float


@dataclass
class _Light:
    t: float
    lux: float
    delta: float


class RuleEngine:
    def __init__(self, config: Optional[RuleConfig] = None):
        self.cfg = config or RuleConfig()
        self.state = State.DISARMED
        self._door: Optional[_Door] = None
        self._light: Optional[_Light] = None
        self._cal_start = 0.0
        self._cal_angle = Calibrator()
        self._cal_rms = Calibrator()
        self._cal_lux = Calibrator()
        self._angle_base = 0.0
        self._rms_thr: Optional[float] = None
        self._light_thr: Optional[float] = None
        self._entry_start = 0.0
        self._pending = ("", "")
        self._alerts: list = []
        self._last = Decision("AMAN", State.DISARMED, "sistem tidak aktif (DISARM)")

    # ---------------- perintah ----------------
    def arm(self, now: float) -> Decision:
        """Mulai kalibrasi lalu aktif. Diabaikan bila sistem sudah aktif."""
        if self.state is not State.DISARMED:
            return self._last
        self._cal_angle, self._cal_rms, self._cal_lux = Calibrator(), Calibrator(), Calibrator()
        self._door = None
        self._light = None
        self._cal_start = now
        self.state = State.CALIBRATING
        self._last = Decision("KALIBRASI", self.state, "kalibrasi dimulai - jangan sentuh pintu")
        return self._last

    def disarm(self, now: float) -> Decision:
        self.state = State.DISARMED
        self._pending = ("", "")
        self._last = Decision("AMAN", self.state, "DISARM: sistem tidak aktif")
        return self._last

    # ---------------- data masuk ----------------
    def update_door(self, now: float, angle_deg: float, motion_rms: float) -> Decision:
        self._door = _Door(now, angle_deg, motion_rms)
        if self.state is State.CALIBRATING:
            self._cal_angle.add(angle_deg)
            self._cal_rms.add(motion_rms)
        return self._evaluate(now)

    def update_light(self, now: float, lux: float, delta: float = 0.0) -> Decision:
        self._light = _Light(now, lux, delta)
        if self.state is State.CALIBRATING:
            self._cal_lux.add(lux)
        return self._evaluate(now)

    def tick(self, now: float) -> Decision:
        """Panggil berkala (mis. tiap 0.25 dtk) agar timer & data basi terproses."""
        return self._evaluate(now)

    # ---------------- keluaran ----------------
    def pop_alerts(self) -> list:
        """Ambil alert baru (sekali saja per kejadian) lalu kosongkan antrean."""
        alerts, self._alerts = self._alerts, []
        return alerts

    def snapshot(self) -> dict:
        d, l = self._door, self._light
        return {
            "state": self.state.value,
            "status": self._last.status,
            "reason": self._last.reason,
            "door_angle_deg": None if d is None else round(d.angle_deg, 1),
            "motion_rms": None if d is None else round(d.rms, 3),
            "light_lux": None if l is None else round(l.lux, 1),
            "angle_baseline_deg": round(self._angle_base, 1),
            "rms_threshold": None if self._rms_thr is None else round(self._rms_thr, 3),
            "light_threshold": None if self._light_thr is None else round(self._light_thr, 1),
            "nudge_deg": self.cfg.nudge_deg,
            "open_deg": self.cfg.open_deg,
            "force_rms": self.cfg.force_rms,
        }

    # ---------------- internal ----------------
    def _evaluate(self, now: float) -> Decision:
        if self.state is State.CALIBRATING:
            self._eval_calibrating(now)
        if self.state is State.ARMED:
            self._eval_armed(now)
        elif self.state is State.ENTRY_DELAY:
            self._eval_entry(now)
        elif self.state is State.ALARM:
            status, reason = self._pending
            self._last = Decision(status, State.ALARM, reason)
        return self._last

    def _eval_calibrating(self, now: float) -> None:
        c = self.cfg
        elapsed = now - self._cal_start
        enough = (
            len(self._cal_angle) >= c.min_cal_samples
            and len(self._cal_lux) >= c.min_cal_samples
        )
        if elapsed < c.calibration_s:
            self._last = Decision(
                "KALIBRASI", self.state,
                f"kalibrasi {elapsed:.0f}/{c.calibration_s:.0f} dtk - jangan sentuh pintu",
            )
            return
        if not enough:
            self._last = Decision(
                "KALIBRASI", self.state, "menunggu data dari kedua edge untuk kalibrasi"
            )
            return
        angle = self._cal_angle.fit()
        rms = self._cal_rms.fit()
        lux = self._cal_lux.fit()
        self._angle_base = angle.mean
        self._rms_thr = threshold(rms, c.z_threshold, c.rms_std_floor, c.rms_margin)
        self._light_thr = threshold(lux, c.z_threshold, c.light_std_floor, c.light_margin)
        self.state = State.ARMED

    def _fresh(self, now: float) -> bool:
        if self._door is None or self._light is None:
            return False
        s = self.cfg.stale_s
        return (now - self._door.t) <= s and (now - self._light.t) <= s

    def _flags(self):
        c, d, l = self.cfg, self._door, self._light
        angle_delta = abs(d.angle_deg - self._angle_base)
        moved = d.rms >= self._rms_thr or angle_delta >= c.nudge_deg
        opened = angle_delta >= c.open_deg
        forced = d.rms >= c.force_rms
        light_up = l.lux >= self._light_thr
        return moved, opened, forced, light_up, angle_delta

    def _info(self, angle_delta: float) -> str:
        return (
            f"sudut {angle_delta:.0f} deg, RMS {self._door.rms:.2f} m/s2, "
            f"cahaya {self._light.lux:.1f} lux"
        )

    def _eval_armed(self, now: float) -> None:
        c = self.cfg
        if not self._fresh(now):
            self._last = Decision(
                "MENUNGGU_DATA", self.state, "data salah satu edge belum/tidak lagi masuk"
            )
            return
        moved, opened, forced, light_up, angle_delta = self._flags()
        info = self._info(angle_delta)

        if forced and (opened or light_up):
            self._raise_alarm("ALERT_DIPAKSA", "pintu dihentak/dipaksa - " + info)
        elif opened and light_up:
            self.state = State.ENTRY_DELAY
            self._entry_start = now
            self._pending = ("ALERT_DIBUKA", "pintu terbuka dan cahaya masuk - " + info)
            self._last = Decision(
                "MENUNGGU_DISARM", self.state, f"DISARM dalam {c.entry_delay_s:.0f} dtk - " + info
            )
        elif moved:
            why = "pintu terbuka tapi cahaya belum naik" if opened else "pintu bergerak"
            self._last = Decision("PINTU_DIGERAKKAN", self.state, f"{why} - {info}")
        else:
            self._last = Decision("AMAN", self.state, "ARMED: normal - " + info)

    def _eval_entry(self, now: float) -> None:
        c = self.cfg
        d = self._door
        if d is not None and (now - d.t) <= c.stale_s and d.rms >= c.force_rms:
            self._raise_alarm("ALERT_DIPAKSA", "hentakan keras saat menunggu DISARM")
            return
        remaining = c.entry_delay_s - (now - self._entry_start)
        if remaining <= 0:
            status, reason = self._pending
            self._raise_alarm(status, reason)
        else:
            self._last = Decision(
                "MENUNGGU_DISARM", self.state, f"DISARM dalam {remaining:.0f} dtk"
            )

    def _raise_alarm(self, status: str, reason: str) -> None:
        self.state = State.ALARM
        self._pending = (status, reason)
        d, l = self._door, self._light
        self._alerts.append({
            "status": status,
            "reason": reason,
            "door_angle_deg": None if d is None else round(d.angle_deg, 1),
            "motion_rms": None if d is None else round(d.rms, 3),
            "light_lux": None if l is None else round(l.lux, 1),
        })
        self._last = Decision(status, State.ALARM, reason)
