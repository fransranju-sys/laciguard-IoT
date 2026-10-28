"""EDGE 1 - HP yang ditempel di PINTU (accelerometer + gyroscope).

Processing di edge:
  A. motion_rms     : RMS getaran
  B. door_angle_deg : sudut buka pintu (integral gyroscope)
Yang dikirim ke MQTT hanya hasil olahan, bukan data mentah.

Contoh:
  python hp_pintu.py                                   # HP asli (Termux)
  python hp_pintu.py --source simulator --scenario open --event-after 40
"""
import argparse
import time

from shared import config
from shared.mqtt_util import make_client, publish_json
from shared.processing import DoorAngleTracker, motion_rms
from shared.sensors import make_motion_source


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", choices=["auto", "termux", "simulator"], default="auto")
    ap.add_argument("--mode", choices=["stream", "poll"], default="stream",
                    help="cara baca termux-sensor; pakai poll jika stream bermasalah")
    ap.add_argument("--scenario", choices=["still", "open", "force"], default="open",
                    help="hanya untuk simulator")
    ap.add_argument("--event-after", type=float, default=40.0,
                    help="simulator: detik sampai pintu 'dibuka'")
    args = ap.parse_args()

    source = make_motion_source(args.source, args.scenario, args.event_after, args.mode)
    topic = config.topic("edge/edge1/telemetry")
    print(f"[EDGE1] sumber sensor: {source.name}")
    print(f"[EDGE1] publish ke: {topic}")
    if source.name == "simulator":
        print("[EDGE1] PERINGATAN: simulator tidak dihitung sebagai edge fisik")

    client = make_client("edge1")
    tracker = DoorAngleTracker()
    window, sequence, last_ok = [], 0, time.monotonic()
    try:
        while True:
            sample = source.read()
            if sample is not None:
                window.append(sample)
                last_ok = time.monotonic()
            elif time.monotonic() - last_ok > 5:
                print("[EDGE1] sensor tidak mengirim data - cek izin Termux:API")
                last_ok = time.monotonic()

            if len(window) >= config.WINDOW_SIZE:
                rms = motion_rms(window)
                angle = tracker.update(window)
                sequence += 1
                publish_json(client, topic, {
                    "device_id": "edge1",
                    "sequence": sequence,
                    "door_angle_deg": round(angle, 1),
                    "motion_rms": round(rms, 3),
                    "sent_at_ms": int(time.time() * 1000),
                })
                print(f"[EDGE1] #{sequence} sudut={angle:.1f} deg  rms={rms:.3f}")
                window = window[-1:]  # sisakan 1 sampel agar integrasi tidak terputus
            time.sleep(config.SAMPLE_INTERVAL)
    except KeyboardInterrupt:
        print("\n[EDGE1] berhenti")
    finally:
        source.stop()
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
