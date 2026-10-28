"""Uji ujung-ke-ujung tanpa MQTT: sampel mentah -> processing -> aturan keputusan."""
from nodes.detector_service.rules import RuleEngine, State
from shared.processing import DoorAngleTracker, LightProcessor, motion_rms
from tests.helpers import make_samples


def test_pintu_dibuka_di_ruang_gelap_menghasilkan_alert():
    eng, tracker, lp = RuleEngine(), DoorAngleTracker(), LightProcessor()
    eng.arm(0.0)

    def step(t, gyro_z, lux, accel=(0, 0, 9.81)):
        win = make_samples(11, 0.1, accel=accel, gyro=(0, 0, gyro_z), t0=t)
        angle = tracker.update(win)
        eng.update_door(t, angle, motion_rms(win))
        smooth, delta = lp.update([lux] * 5)
        eng.update_light(t, smooth, delta)

    for t in range(0, 12):          # kalibrasi: pintu diam, gelap
        step(float(t), 0.0, 2.0)
    assert eng.tick(12.0).state is State.ARMED

    step(12.0, 1.0, 80.0)           # pintu diayun ~57 derajat, cahaya masuk
    assert eng.state is State.ENTRY_DELAY

    for t in range(13, 23):         # pintu dibiarkan terbuka
        step(float(t), 0.0, 80.0)
    eng.tick(23.0)
    alerts = eng.pop_alerts()
    assert len(alerts) == 1 and alerts[0]["status"] == "ALERT_DIBUKA"
