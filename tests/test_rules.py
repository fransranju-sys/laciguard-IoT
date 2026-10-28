from nodes.detector_service.rules import RuleEngine, State


def armed_engine():
    """Engine yang sudah selesai kalibrasi (pintu diam, ruangan ~2 lux)."""
    eng = RuleEngine()
    eng.arm(0.0)
    for t in range(0, 11):
        eng.update_door(float(t), 0.0, 0.05)
        eng.update_light(float(t), 2.0)
    d = eng.tick(11.0)
    assert eng.state is State.ARMED, d
    return eng


def test_disarmed_selalu_aman():
    eng = RuleEngine()
    eng.update_door(1.0, 90.0, 5.0)
    d = eng.update_light(1.0, 100.0)
    assert d.status == "AMAN" and eng.state is State.DISARMED


def test_kalibrasi_selesai_jadi_armed():
    eng = armed_engine()
    assert eng.tick(11.5).status == "AMAN"


def test_kalibrasi_menunggu_jika_edge2_tidak_ada():
    eng = RuleEngine()
    eng.arm(0.0)
    for t in range(0, 11):
        eng.update_door(float(t), 0.0, 0.05)   # edge 2 tidak pernah kirim
    d = eng.tick(11.0)
    assert eng.state is State.CALIBRATING and d.status == "KALIBRASI"


def test_normal_tetap_aman():
    eng = armed_engine()
    eng.update_door(12.0, 0.0, 0.06)
    assert eng.update_light(12.0, 2.1).status == "AMAN"


def test_pintu_bergerak_tanpa_cahaya_hanya_peringatan():
    eng = armed_engine()
    d = eng.update_door(12.0, 15.0, 1.0)
    assert d.status == "PINTU_DIGERAKKAN" and eng.state is State.ARMED
    assert eng.pop_alerts() == []


def test_lampu_menyala_tanpa_pintu_bergerak_tidak_alert():
    eng = armed_engine()
    eng.update_door(12.0, 0.0, 0.05)
    d = eng.update_light(12.0, 300.0)
    assert d.status == "AMAN"


def test_buka_pintu_dan_cahaya_masuk_menunggu_disarm_lalu_alert():
    eng = armed_engine()
    eng.update_door(12.0, 40.0, 1.0)
    d = eng.update_light(12.0, 80.0)
    assert d.status == "MENUNGGU_DISARM" and eng.state is State.ENTRY_DELAY
    assert eng.pop_alerts() == []

    d = eng.tick(22.0)  # 10 dtk setelah masuk ENTRY_DELAY
    assert d.status == "ALERT_DIBUKA" and eng.state is State.ALARM
    alerts = eng.pop_alerts()
    assert len(alerts) == 1 and alerts[0]["status"] == "ALERT_DIBUKA"

    eng.tick(23.0)
    assert eng.pop_alerts() == []   # alert hanya sekali


def test_disarm_saat_entry_delay_membatalkan_alert():
    eng = armed_engine()
    eng.update_door(12.0, 40.0, 1.0)
    eng.update_light(12.0, 80.0)
    eng.disarm(15.0)
    eng.tick(30.0)
    assert eng.state is State.DISARMED and eng.pop_alerts() == []


def test_hentakan_keras_langsung_alarm_tanpa_delay():
    eng = armed_engine()
    eng.update_door(12.0, 30.0, 5.0)
    d = eng.update_light(12.0, 80.0)
    assert d.status == "ALERT_DIPAKSA" and eng.state is State.ALARM
    assert len(eng.pop_alerts()) == 1


def test_hentakan_saat_entry_delay_eskalasi_ke_alarm():
    eng = armed_engine()
    eng.update_door(12.0, 40.0, 1.0)
    eng.update_light(12.0, 80.0)
    d = eng.update_door(14.0, 45.0, 6.0)
    assert d.status == "ALERT_DIPAKSA"


def test_alarm_menetap_sampai_disarm():
    eng = armed_engine()
    eng.update_door(12.0, 30.0, 5.0)
    eng.update_light(12.0, 80.0)
    assert eng.tick(100.0).status == "ALERT_DIPAKSA"
    eng.disarm(101.0)
    assert eng.tick(102.0).status == "AMAN"


def test_data_basi_menghasilkan_menunggu_data():
    eng = armed_engine()
    assert eng.tick(30.0).status == "MENUNGGU_DATA"


def test_arm_ulang_setelah_disarm_kalibrasi_lagi():
    eng = armed_engine()
    eng.disarm(12.0)
    eng.arm(13.0)
    assert eng.state is State.CALIBRATING
