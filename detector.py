"""NODE 3 - Laptop: subscribe telemetry kedua edge, jalankan aturan, kirim alert.

Perintah dari terminal ini:  arm | disarm | quit
Perintah juga bisa dikirim lewat MQTT ke topic .../control (payload: ARM atau DISARM).
"""
import json
import sys
import threading
import time

from nodes.detector_service.rules import RuleEngine
from shared import config
from shared.mqtt_util import make_client, publish_json

engine = RuleEngine()
lock = threading.Lock()


def on_telemetry(topic: str, payload: bytes) -> None:
    data = json.loads(payload)
    now = time.monotonic()  # waktu terima di laptop (jam HP bisa beda-beda)
    with lock:
        if data.get("device_id") == "edge1":
            engine.update_door(now, float(data["door_angle_deg"]), float(data["motion_rms"]))
        elif data.get("device_id") == "edge2":
            engine.update_light(now, float(data["light_lux"]), float(data.get("light_delta", 0.0)))


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
    print("LaciGuard - NODE 3 / Detector")
    print(f"[CONFIG] PROJECT_ID: {config.PROJECT_ID}")
    print(f"[CONFIG] broker    : {config.MQTT_HOST}:{config.MQTT_PORT} (TLS={config.MQTT_TLS})")
    print("[CMD] ketik 'arm' atau 'disarm' lalu Enter\n")

    client = make_client("detector", {
        config.topic("edge/+/telemetry"): on_telemetry,
        config.topic("control"): on_control,
    })
    threading.Thread(target=stdin_loop, daemon=True).start()

    last_key, last_status_pub = None, 0.0
    try:
        while True:
            now = time.monotonic()
            with lock:
                decision = engine.tick(now)
                alerts = engine.pop_alerts()
                snapshot = engine.snapshot()

            key = (decision.state, decision.status)
            if key != last_key:
                stamp = time.strftime("%H:%M:%S")
                print(f"[{stamp}] {decision.state.value:<11} {decision.status:<17} {decision.reason}")
                last_key = key

            for alert in alerts:
                alert["sent_at_ms"] = int(time.time() * 1000)
                publish_json(client, config.topic("alerts"), alert, qos=1)
                print(f"[ALERT] dipublish ke {config.topic('alerts')}")

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
