import math

from shared.processing import (
    Calibrator, DoorAngleTracker, LightProcessor, motion_rms, threshold, z_score,
)
from tests.helpers import make_samples


def test_rms_diam_mendekati_nol():
    assert motion_rms(make_samples(10, 0.1)) < 1e-9


def test_rms_offset_satu():
    s = make_samples(10, 0.1, accel=(0, 0, 10.81))  # magnitude 10.81 -> error 1.0
    assert math.isclose(motion_rms(s), 1.0, abs_tol=1e-6)


def test_sudut_pintu_satu_radian():
    # 1 rad/s selama 1 detik -> 57.3 derajat
    tracker = DoorAngleTracker()
    s = make_samples(11, 0.1, gyro=(0, 0, 1.0))
    assert math.isclose(tracker.update(s), 57.3, abs_tol=1.0)


def test_sudut_pintu_tidak_bergantung_orientasi_hp():
    # HP ditempel miring: gravitasi di sumbu x, putaran pintu juga di sumbu x
    tracker = DoorAngleTracker()
    s = make_samples(11, 0.1, accel=(9.81, 0, 0), gyro=(1.0, 0, 0))
    assert math.isclose(tracker.update(s), 57.3, abs_tol=1.0)


def test_putaran_di_sumbu_lain_tidak_dihitung_sebagai_buka_pintu():
    # HP diputar mengelilingi sumbu horizontal (bukan engsel vertikal)
    tracker = DoorAngleTracker()
    s = make_samples(11, 0.1, accel=(0, 0, 9.81), gyro=(1.0, 0, 0))
    assert tracker.update(s) < 1.0


def test_buka_lalu_tutup_kembali_ke_nol():
    tracker = DoorAngleTracker()
    tracker.update(make_samples(11, 0.1, gyro=(0, 0, 1.0)))
    angle = tracker.update(make_samples(11, 0.1, gyro=(0, 0, -1.0), t0=1.0))
    assert angle < 1.0


def test_bias_gyro_kecil_tidak_menyebabkan_drift():
    tracker = DoorAngleTracker()
    s = make_samples(300, 0.1, gyro=(0, 0, 0.02))  # 30 detik, di bawah dead-zone
    assert tracker.update(s) == 0.0


def test_celah_data_dilewati():
    tracker = DoorAngleTracker()
    s = make_samples(2, 5.0, gyro=(0, 0, 1.0))  # dt 5 detik -> dilewati
    assert tracker.update(s) == 0.0


def test_light_processor_stabil_lalu_lonjakan():
    lp = LightProcessor()
    for _ in range(5):
        lux, delta = lp.update([2.0] * 5)
    assert math.isclose(lux, 2.0) and abs(delta) < 1e-6
    lux, delta = lp.update([80.0] * 5)
    assert lux > 20 and delta > 20


def test_kalibrasi_dan_ambang():
    cal = Calibrator()
    for v in (1.0, 1.0, 1.0):
        cal.add(v)
    base = cal.fit()
    assert base.mean == 1.0 and base.std == 0.0
    # std 0 -> pakai floor: max(3*0.05, 0.4) = 0.4
    assert math.isclose(threshold(base, 3.0, 0.05, 0.4), 1.4)


def test_z_score():
    cal = Calibrator()
    for v in (0.0, 2.0):
        cal.add(v)
    base = cal.fit()  # mean 1, std 1
    assert math.isclose(z_score(4.0, base), 3.0)
