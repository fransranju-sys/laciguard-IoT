# LaciGuard

Penjaga lemari/pintu kos berbasis IoT. **2 HP sebagai edge**, **2 jenis sensor**
(gerak + cahaya), pengolahan data di edge, **sensor fusion** di detector, dan
komunikasi ke cloud lewat **MQTT**.

```
 HP A (Edge 1, di pintu)            HP B (Edge 2, di dalam lemari)
 accelerometer + gyroscope          sensor cahaya (lux) + alarm
 -> sudut pintu, RMS getaran        -> lux rata-rata, light_delta
        |  telemetry                       |  telemetry        ^ alerts
        v                                  v                   |
                 MQTT Broker (HiveMQ publik, TLS 8883)
                              |  telemetry          ^ alerts, status
                              v                     |
                 Laptop: detector.py (sensor fusion + state machine)
```

## Struktur

| File | Peran |
|---|---|
| `hp_pintu.py` | Edge 1: baca gerak, olah (A, B), kirim telemetry |
| `hp_dalam.py` | Edge 2: baca cahaya, olah (C, D), kirim telemetry, alarm saat alert |
| `detector.py` | Laptop: terima telemetry, jalankan aturan, kirim alert + status |
| `shared/sensors.py` | Pembaca sensor Termux + simulator |
| `shared/processing.py` | Semua pengolahan data (RMS, sudut pintu, cahaya, kalibrasi) |
| `nodes/detector_service/rules.py` | Sensor fusion + state machine ARM/DISARM |
| `dashboard/index.html` | Dashboard web: status, ARM/DISARM, grafik sudut dan lux, riwayat alert |
| `shared/mqtt_util.py`, `shared/alarm.py`, `shared/config.py` | MQTT, alarm, konfigurasi |
| `tests/` | Unit test (28 test) |

## Pengolahan data

| Kode | Di mana | Apa | Rumus ringkas |
|---|---|---|---|
| A | Edge 1 | RMS getaran | `sqrt(mean((|a| - 9.81)^2))` |
| B | Edge 1 | Sudut pintu | `sudut += (gyro . arah_gravitasi) * dt` |
| C | Edge 2 | Lux rata-rata bergerak | rata-rata 3 window terakhir |
| D | Edge 2 | Lonjakan cahaya | `lux - baseline_EMA` |
| E | Detector | Kalibrasi adaptif | `ambang = mean + max(3*std, margin)` |

## Algoritma keputusan (ARMED)

| Pintu terbuka (>=10 deg) | Cahaya naik | Hentakan (RMS>=3) | Hasil |
|---|---|---|---|
| tidak | - | tidak | AMAN |
| bergerak/terbuka | tidak | tidak | PINTU_DIGERAKKAN (peringatan) |
| ya | ya | tidak | MENUNGGU_DISARM 10 dtk -> ALERT_DIBUKA |
| ya / cahaya naik | - | ya | ALERT_DIPAKSA (langsung, tanpa delay) |

State: `DISARMED -> CALIBRATING (10 dtk) -> ARMED -> ENTRY_DELAY -> ALARM`.
Alarm menetap sampai DISARM.

## Cara menjalankan

```bash
# 1. Semua perangkat
git clone <repo-kamu> && cd laciguard
cp .env.example .env          # ganti PROJECT_ID dengan nama unik kelompok
pip install -r requirements.txt

# 2. Laptop
python detector.py            # ketik: arm / disarm

# 3. HP A (Termux, di pintu)
python hp_pintu.py

# 4. HP B (Termux, di dalam lemari)
python hp_dalam.py
```

Termux: `pkg install python git termux-api`, lalu `termux-wake-lock` agar proses
tidak dimatikan Android. Cek sensor dengan `termux-sensor -l`.

**Tanpa HP (latihan, tidak dihitung edge fisik):**
```bash
python detector.py
python hp_pintu.py --source simulator --scenario open --event-after 40
python hp_dalam.py --source simulator --scenario open --event-after 40
# ketik "arm" di terminal detector, tunggu ~40 dtk
```
Skenario simulator: `still`, `open`, `force`.

Kalau `termux-sensor` mode stream bermasalah, tambahkan `--mode poll`.

## Dashboard

Buka `dashboard/index.html` di browser (perlu internet untuk memuat library MQTT dan
terhubung ke broker). Isi `PROJECT_ID` yang sama dengan `.env`, klik Hubungkan, lalu
gunakan tombol ARM/DISARM. Dashboard memakai WebSocket TLS `wss://broker.hivemq.com:8884/mqtt`.

## MQTT

| Topic | Arah | Isi |
|---|---|---|
| `laciguard/<ID>/edge/edge1/telemetry` | Edge 1 -> cloud | `door_angle_deg`, `motion_rms` |
| `laciguard/<ID>/edge/edge2/telemetry` | Edge 2 -> cloud | `light_lux`, `light_delta` |
| `laciguard/<ID>/alerts` | detector -> cloud | `status`, `reason`, pembacaan sensor |
| `laciguard/<ID>/status` | detector -> cloud (retained) | state, status, ambang |
| `laciguard/<ID>/control` | siapa saja -> detector | `ARM` / `DISARM` |

Uji manual: `mosquitto_pub -h broker.hivemq.com -t "laciguard/<ID>/control" -m ARM`

## Pemasangan dan batasan

* Desain ini untuk **pintu dengan engsel vertikal** (pintu kamar, lemari baju).
  Untuk **laci geser** gyroscope tidak mendeteksi buka-tutup; gunakan accelerometer
  (hentakan/geseran) atau andalkan sensor cahaya saja.
* HP A: tempel kuat di permukaan pintu (karet/selotip), orientasi bebas.
* HP B: taruh di dalam lemari dengan sensor cahaya (dekat kamera depan) tidak tertutup.
  Kecerahan layar bisa memengaruhi bacaan, jadi kalibrasi di kondisi yang sama dengan demo.
* Jangan sentuh pintu selama 10 detik kalibrasi setelah ARM.
* Broker publik dipakai bersama: pakai `PROJECT_ID` unik dan jangan kirim data pribadi.

## Parameter yang boleh disetel (`RuleConfig` di `rules.py`)

`open_deg`, `nudge_deg`, `force_rms`, `entry_delay_s`, `calibration_s`,
`rms_margin`, `light_margin`. Catat hasil percobaan tiap nilai di dokumentasi.

## Pengujian

```bash
pip install pytest && pytest -q
```
Skenario uji manual untuk PPT/video: ARM lalu pintu diam (AMAN); pintu dibuka pelan
(ALERT_DIBUKA); buka lalu DISARM <10 dtk (tanpa alert); pintu dihentak (ALERT_DIPAKSA);
lampu kamar dinyalakan tanpa menyentuh pintu (tidak alert); DISARM lalu buka pintu (AMAN).
