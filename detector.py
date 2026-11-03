"""NODE 3 - Laptop: subscribe telemetry kedua edge, jalankan aturan, kirim alert.

Perintah dari terminal ini:  arm | disarm | quit
Perintah juga bisa dikirim lewat MQTT ke topic .../control (payload: ARM atau DISARM).
"""
import argparse
import json
import os
import sys
import threading
import time

from nodes.detector_service.rules import RuleEngine
from shared import config
from shared.mqtt_util import make_client, publish_json

engine = RuleEngine()
lock = threading.Lock()
clf = None  # EventClassifier (AI), diisi di main() bila model tersedia


def load_classifier(path: str):
    """Muat model AI bila ada. Aturan tetap berjalan walau AI tidak aktif."""
    if not os.path.exists(path):
        print(f"[AI] model {path} belum ada - jalankan: python -m ai.train (aturan tetap jalan)")
        return None
    try:
        from ai.classifier import EventClassifier

        c = EventClassifier(path)
        print(f"[AI] model dimuat: {path} (kelas: {', '.join(c.classes)})")
        return c
    except Exception as exc:  # scikit-learn belum terpasang, file rusak, dll
        print(f"[AI] gagal memuat model ({exc!r}) - lanjut tanpa AI")
        return None


def on_telemetry(topic: str, payload: bytes) -> None:
    data = json.loads(payload)
    now = time.monotonic()  # waktu terima di laptop (jam HP bisa beda-beda)
    with lock:
        if data.get("device_id") == "edge1":
            angle, rms = float(data["door_angle_deg"]), float(data["motion_rms"])
            engine.update_door(now, angle, rms)
            if clf is not None:
                clf.update_door(now, angle, rms)
        elif data.get("device_id") == "edge2":
            lux, delta = float(data["light_lux"]), float(data.get("light_delta", 0.0))
            engine.update_light(now, lux, delta)
            if clf is not None:
                clf.update_light(now, lux, delta)


def evaluate(now: float):
    """Satu putaran: aturan + AI. Kembalikan (decision, alerts, snapshot, ai)."""
    with lock:
        decision = engine.tick(now)
        alerts = engine.pop_alerts()
        snapshot = engine.snapshot()
        ai = clf.predict(now) if clf is not None else None
        snapshot["ai_enabled"] = clf is not None
        snapshot["ai_event"] = None if ai is None else ai[0]
        snapshot["ai_confidence"] = None if ai is None else round(ai[1], 3)
        if clf is not None:
            from ai.classifier import agreement

            for alert in alerts:
                ev = clf.recent_event(now)
                alert["ai_event"] = None if ev is None else ev[0]
                alert["ai_confidence"] = None if ev is None else round(ev[1], 3)
                alert["ai_agrees"] = agreement(alert["status"], alert["ai_event"])
    return decision, alerts, snapshot, ai


def apply_command(cmd: str) -> None:
    cmd = cmd.strip().upper()
    now = time.monotonic()
    with lock:
        if cmd in ("ARM", "A"):
            engine.arm(now)
            print(">> ARM diterima: kalibrasi dimulai")
        elif cmd in ("DISARM", "D"):
            engine.disarm(now)
            print(">> DISARM diterima")


def on_control(topic: str, payload: bytes) -> None:
    text = payload.decode("utf-8", errors="ignore").strip()
    if text.startswith("{"):
        text = str(json.loads(text).get("command", ""))
    apply_command(text)


def stdin_loop() -> None:
    for line in sys.stdin:
        if line.strip().lower() in ("q", "quit", "exit"):
            print("keluar...")
            import os
            os._exit(0)
        apply_command(line)


def main() -> None:
    global clf
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.join("ai", "model.joblib"))
    ap.add_argument("--no-ai", action="store_true", help="jalankan hanya dengan aturan")
    args = ap.parse_args()
    if not args.no_ai:
        clf = load_classifier(args.model)

    print("LaciGuard - NODE 3 / Detector")
    print(f"[CONFIG] PROJECT_ID: {config.PROJECT_ID}")
    print(f"[CONFIG] broker    : {config.MQTT_HOST}:{config.MQTT_PORT} (TLS={config.MQTT_TLS})")
    print("[CMD] ketik 'arm' atau 'disarm' lalu Enter\n")

    client = make_client("detector", {
        config.topic("edge/+/telemetry"): on_telemetry,
        config.topic("control"): on_control,
    })
    threading.Thread(target=stdin_loop, daemon=True).start()

    last_key, last_status_pub, last_ai = None, 0.0, None
    try:
        while True:
            now = time.monotonic()
            decision, alerts, snapshot, ai = evaluate(now)

            if ai is not None and ai[0] != last_ai:
                print(f"[{time.strftime('%H:%M:%S')}] [AI] {ai[0]} ({ai[1] * 100:.0f}%)")
                last_ai = ai[0]

            key = (decision.state, decision.status)
            if key != last_key:
                stamp = time.strftime("%H:%M:%S")
                print(f"[{stamp}] {decision.state.value:<11} {decision.status:<17} {decision.reason}")
                last_key = key

            for alert in alerts:
                alert["sent_at_ms"] = int(time.time() * 1000)
                publish_json(client, config.topic("alerts"), alert, qos=1)
                extra = ""
                if alert.get("ai_event"):
                    extra = f" | AI: {alert['ai_event']} ({alert['ai_confidence'] * 100:.0f}%), sependapat={alert['ai_agrees']}"
                print(f"[ALERT] dipublish ke {config.topic('alerts')}{extra}")

            if now - last_status_pub >= 1.0:  # status untuk dashboard
                snapshot["sent_at_ms"] = int(time.time() * 1000)
                publish_json(client, config.topic("status"), snapshot, qos=0, retain=True)
                last_status_pub = now
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\n[DETECTOR] berhenti")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
