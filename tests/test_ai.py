import os
import tempfile

import joblib
import numpy as np

from ai.classifier import EventClassifier, agreement
from ai.features import FEATURES, LABELS, FeatureWindow
from ai.train import train

# rata-rata fitur tiap kelas (data tiruan HANYA untuk menguji kode, bukan hasil penelitian)
_MEANS = {
    "DIAM":        [0.2, 0.3, 0.2, 0.15, 1.0, 1.0],
    "BUKA_NORMAL": [40, 40, 1.0, 0.6, 60, 60],
    "DIPAKSA":     [30, 40, 5.0, 3.0, 50, 50],
    "KETUKAN":     [1.0, 2.0, 2.5, 1.2, 1.0, 1.0],
    "CAHAYA_SAJA": [0.2, 0.3, 0.2, 0.15, 80, 80],
}


def _fake_data(n=40, seed=0):
    rng = np.random.default_rng(seed)
    X, y = [], []
    for label, mean in _MEANS.items():
        for _ in range(n):
            X.append(np.abs(rng.normal(mean, np.array(mean) * 0.1 + 0.05)))
            y.append(label)
    return np.array(X), np.array(y)


def test_fitur_jumlah_dan_label():
    assert len(FEATURES) == 6
    assert set(_MEANS) == set(LABELS)


def test_window_butuh_kedua_edge():
    fw = FeatureWindow()
    fw.update_door(0.0, 10.0, 0.2)
    fw.update_door(1.0, 12.0, 0.2)
    assert fw.features(1.0) is None  # belum ada data cahaya


def test_window_hitung_fitur():
    fw = FeatureWindow()
    fw.update_light(0.0, 20.0, 0.0)
    fw.update_door(0.0, 0.0, 0.2)
    fw.update_door(1.0, 30.0, 4.0)
    fw.update_light(1.0, 100.0, 80.0)
    f = dict(zip(FEATURES, fw.features(1.0)))
    assert f["angle_change"] == 30.0 and f["angle_range"] == 30.0
    assert f["rms_max"] == 4.0
    assert f["lux_delta_max"] == 80.0 and f["lux_range"] == 80.0


def test_window_membuang_data_lama():
    fw = FeatureWindow(window_s=3.0)
    fw.update_light(0.0, 20.0, 0.0)
    fw.update_door(0.0, 0.0, 0.2)
    fw.update_door(1.0, 5.0, 0.2)
    assert fw.features(10.0) is None


def test_latih_dan_akurasi_data_tiruan():
    X, y = _fake_data()
    model, report = train(X, y)
    assert (model.predict(X) == y).mean() > 0.95
    assert "Akurasi data uji" in report and "Aturan pohon" in report


def test_classifier_memprediksi_dipaksa():
    X, y = _fake_data()
    model, _ = train(X, y)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "m.joblib")
        joblib.dump({"model": model}, path)
        clf = EventClassifier(path)
    assert clf.predict(0.0) is None  # data belum ada
    clf.update_light(0.0, 20.0, 0.0)
    clf.update_door(0.0, 0.0, 0.2)
    clf.update_door(1.0, 30.0, 5.0)
    clf.update_light(1.0, 70.0, 50.0)
    label, conf = clf.predict(1.0)
    assert label == "DIPAKSA" and conf > 0.5
    # kejadian tetap diingat meski window berikutnya sudah tenang
    assert clf.recent_event(8.0)[0] == "DIPAKSA"


def test_agreement():
    assert agreement("ALERT_DIBUKA", "BUKA_NORMAL") is True
    assert agreement("ALERT_DIPAKSA", "BUKA_NORMAL") is False
    assert agreement("AMAN", "DIAM") is None
    assert agreement("ALERT_DIBUKA", None) is None
