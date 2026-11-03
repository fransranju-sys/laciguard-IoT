import json
import os
import sys
import tempfile
import types

import joblib

try:  # paho-mqtt tidak dipakai di test ini; tiruan kecil bila belum terpasang
    import paho.mqtt.client  # noqa: F401
except ImportError:
    paho = types.ModuleType("paho")
    mqtt = types.ModuleType("paho.mqtt")
    client_mod = types.ModuleType("paho.mqtt.client")
    paho.mqtt, mqtt.client = mqtt, client_mod
    sys.modules.update({"paho": paho, "paho.mqtt": mqtt, "paho.mqtt.client": client_mod})

import detector  # noqa: E402
from ai.classifier import EventClassifier
from ai.train import train
from tests.test_ai import _fake_data


def test_detector_tanpa_ai_tetap_jalan():
    detector.clf = None
    _, _, snap, ai = detector.evaluate(0.0)
    assert snap["ai_enabled"] is False and ai is None


def test_detector_dengan_ai_menambah_status():
    X, y = _fake_data()
    model, _ = train(X, y)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.joblib")
        joblib.dump({"model": model}, path)
        detector.clf = EventClassifier(path)
    try:
        import time
        t = time.monotonic()
        detector.on_telemetry("x", json.dumps({"device_id": "edge2", "light_lux": 20, "light_delta": 0}).encode())
        detector.on_telemetry("x", json.dumps({"device_id": "edge1", "door_angle_deg": 0, "motion_rms": 0.2}).encode())
        detector.on_telemetry("x", json.dumps({"device_id": "edge1", "door_angle_deg": 30, "motion_rms": 5}).encode())
        detector.on_telemetry("x", json.dumps({"device_id": "edge2", "light_lux": 70, "light_delta": 50}).encode())
        _, _, snap, ai = detector.evaluate(time.monotonic())
        assert snap["ai_enabled"] is True
        assert snap["ai_event"] == "DIPAKSA" and ai[0] == "DIPAKSA"
    finally:
        detector.clf = None
