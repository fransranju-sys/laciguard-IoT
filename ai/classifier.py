"""Klasifikasi kejadian pintu memakai model Decision Tree (scikit-learn)."""
from collections import deque

from ai.features import FeatureWindow

# alert aturan -> kelas AI yang dianggap sependapat
AGREE = {
    "ALERT_DIBUKA": {"BUKA_NORMAL"},
    "ALERT_DIPAKSA": {"DIPAKSA"},
}


def agreement(status: str, ai_event):
    """True/False bila AI sependapat dengan alert aturan, None bila tidak bisa dinilai."""
    if ai_event is None or status not in AGREE:
        return None
    return ai_event in AGREE[status]


class EventClassifier:
    def __init__(self, path: str):
        import joblib

        bundle = joblib.load(path)
        self.model = bundle["model"]
        self.classes = list(self.model.classes_)
        self.fw = FeatureWindow()
        self.history = deque()  # (waktu, label, keyakinan)
        self.last = None

    def update_door(self, t, angle, rms):
        self.fw.update_door(t, angle, rms)

    def update_light(self, t, lux, delta):
        self.fw.update_light(t, lux, delta)

    def predict(self, now: float):
        """(label, keyakinan) untuk window terbaru, atau None bila data belum cukup."""
        feats = self.fw.features(now)
        if feats is None:
            self.last = None
            return None
        proba = self.model.predict_proba([feats])[0]
        i = int(proba.argmax())
        self.last = (str(self.classes[i]), float(proba[i]))
        self.history.append((now, *self.last))
        while self.history and now - self.history[0][0] > 30.0:
            self.history.popleft()
        return self.last

    def recent_event(self, now: float, horizon: float = 15.0):
        """Kejadian bukan-DIAM paling meyakinkan dalam `horizon` detik terakhir.

        Alert dibuka baru keluar ~10 detik setelah pintu dibuka (entry delay), jadi
        AI dinilai dari kejadian beberapa detik sebelumnya, bukan saat alert keluar.
        """
        cands = [h for h in self.history if now - h[0] <= horizon and h[1] != "DIAM"]
        if cands:
            _, label, conf = max(cands, key=lambda h: h[2])
            return label, conf
        return self.last
