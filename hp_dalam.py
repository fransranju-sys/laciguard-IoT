"""EDGE 2 - HP di DALAM lemari (sensor cahaya) + alarm.

Processing di edge:
  C. light_lux   : rata-rata bergerak lux
  D. light_delta : selisih terhadap baseline lambat
Saat detector mengirim alert, HP ini bergetar, menampilkan notifikasi, dan bersuara.

Contoh:
  python hp_dalam.py
  python hp_dalam.py --source simulator --scenario open --event-after 40
"""
import argparse
import json
import time

from shared import config
from shared.alarm import trigger_alarm
from shared.mqtt_util import make_client, publish_json
from shared.processing import LightProcessor
from shared.sensors import make_light_source


def on_alert(topic: str, payload: bytes) -> None:
    data = json.loads(payload)
    status = data.get("status", "ALERT")
    trigger_alarm("LaciGuard: " + status, data.get("reason", ""), speak="Peringatan! Lemari dibuka!")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["auto", "termux", "simulator"], default="auto")
    ap.add_argument("--mode", choices=["stream", "poll"], default="stream")
    ap.add_argument("--scenario", choices=["still", "open", "force"], default="open")
    ap.add_argument("--event-after", type=float, default=40.0)
    args = ap.parse_args()

    source = make_light_source(args.source, args.scenario, args.event_after, args.mode)
    topic = config.topic("edge/edge2/telemetry")
    print(f"[EDGE2] sumber sensor: {source.name}")
    print(f"[EDGE2] publish ke: {topic}")
    print(f"[EDGE2] subscribe : {config.topic('alerts')}")
    if source.name == "simulator":
        print("[EDGE2] PERINGATAN: simulator tidak dihitung sebagai edge fisik")

    client = make_client("edge2", {config.topic("alerts"): on_alert})
    lp = LightProcessor()
    values, sequence, last_ok = [], 0, time.monotonic()
    try:
        while True:
            sample = source.read()
            if sample is not None:
                values.append(sample.lux)
                last_ok = time.monotonic()
            elif time.monotonic() - last_ok > 5:
                print("[EDGE2] sensor cahaya belum memberi data")
                last_ok = time.monotonic()

            if len(values) >= config.WINDOW_SIZE:
                lux, delta = lp.update(values)
                sequence += 1
                publish_json(client, topic, {
                    "device_id": "edge2",
                    "sequence": sequence,
                    "light_lux": round(lux, 2),
                    "light_delta": round(delta, 2),
                    "sent_at_ms": int(time.time() * 1000),
                })
                print(f"[EDGE2] #{sequence} lux={lux:.1f}  delta={delta:+.1f}")
                values = []
            time.sleep(config.SAMPLE_INTERVAL)
    except KeyboardInterrupt:
        print("\n[EDGE2] berhenti")
    finally:
        source.stop()
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
