"""Rekam data berlabel untuk melatih model AI.

Jalankan di laptop saat kedua HP (atau simulator) sudah mengirim telemetry:

    python -m ai.collect --label DIPAKSA --duration 60

Selama waktu berjalan, ulangi kejadian sesuai label (misalnya hentak pintu
beberapa kali). Satu baris data direkam tiap detik ke ai/data/dataset.csv.

Label: DIAM, BUKA_NORMAL, DIPAKSA, KETUKAN, CAHAYA_SAJA
"""
import argparse
import csv
import json
import os
import threading
import time

from ai.features import FEATURES, LABELS, FeatureWindow
from shared import config
from shared.mqtt_util import make_client

DEFAULT_CSV = os.path.join("ai", "data", "dataset.csv")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True, choices=LABELS)
    ap.add_argument("--duration", type=float, default=60.0, help="lama rekam (detik)")
    ap.add_argument("--out", default=DEFAULT_CSV)
    args = ap.parse_args()

    fw = FeatureWindow()
    lock = threading.Lock()

    def on_telemetry(topic: str, payload: bytes) -> None:
        d = json.loads(payload)
        now = time.monotonic()
        with lock:
            if d.get("device_id") == "edge1":
                fw.update_door(now, float(d["door_angle_deg"]), float(d["motion_rms"]))
            elif d.get("device_id") == "edge2":
                fw.update_light(now, float(d["light_lux"]), float(d.get("light_delta", 0.0)))

    client = make_client("collect", {config.topic("edge/+/telemetry"): on_telemetry})
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    new_file = not os.path.exists(args.out)

    print(f"Label: {args.label}. Siap-siap, mulai dalam 3 detik...")
    time.sleep(3)
    print(">>> REKAM. Lakukan kejadian sesuai label, ulangi beberapa kali.")
    rows, end = 0, time.monotonic() + args.duration
    try:
        with open(args.out, "a", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(FEATURES + ["label"])
            while time.monotonic() < end:
                time.sleep(1.0)
                with lock:
                    feats = fw.features(time.monotonic())
                if feats is None:
                    print("  (menunggu data kedua edge...)")
                    continue
                w.writerow([round(x, 4) for x in feats] + [args.label])
                f.flush()
                rows += 1
                print(f"  baris {rows}: " + ", ".join(f"{n}={v:.2f}" for n, v in zip(FEATURES, feats)))
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()
    print(f"Selesai: {rows} baris untuk label {args.label} -> {args.out}")


if __name__ == "__main__":
    main()
