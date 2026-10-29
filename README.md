[readme (1).md](https://github.com/user-attachments/files/34113899/readme.1.md)
# LaciGuard

Sistem pemantau keamanan pintu lemari dan kamar kos berbasis IoT. Proyek ini menggunakan **2 HP Android sebagai edge device**, **3 sensor** (*accelerometer*, *gyroscope*, dan sensor cahaya), pengolahan data di sisi edge, algoritma **sensor fusion + state machine** di laptop, serta komunikasi dua arah lewat **MQTT**.

**Tugas Mata Kuliah Internet of Things — S1 Informatika, Universitas Diponegoro**  
**Kelompok 15**

| Nama | NIM |
| :--- | :--- |
| Frans Ranju Christian Pardede | 24060125140130 |
| Nathanael Tonyus Wilbert Sianipar | 24060125140166 |
| Randradinata Faiq Prayogo | 24060125120028 |

Repositori: https://www.google.com/search?q=https://github.com/fransranju-sys/laciguard-IoT

## Masalah dan Ide

Lemari atau kamar kos sering ditinggal dalam keadaan terkunci, tetapi penghuni tidak tahu kalau pintunya dibuka paksa atau dibobol. Jika hanya memakai satu sensor di pintu, sistem mudah mengalami salah deteksi:
- **Hanya sensor gerak di pintu:** pintu yang tersenggol atau getaran langkah kaki bisa dianggap pembobolan.
- **Hanya sensor cahaya di dalam lemari:** lampu kamar yang menyala dan masuk lewat celah lemari bisa memicu alarm palsu.

**LaciGuard** menggabungkan pembacaan dari dua HP di posisi berbeda:
1. **HP A (Edge 1, ditempel di pintu):** membaca *accelerometer* dan *gyroscope* untuk menghitung sudut bukaan pintu serta kuat getaran (RMS).
2. **HP B (Edge 2, ditaruh di dalam lemari):** membaca sensor cahaya (lux) untuk memastikan apakah pintu benar-benar terbuka hingga cahaya luar masuk, sekaligus membunyikan alarm dan getar saat ada peringatan dari server.
3. **Laptop (`detector.py` dan Dashboard):** menerima data dari kedua HP lewat broker MQTT HiveMQ, melakukan kalibrasi ambang otomatis selama 10 detik saat diaktifkan (`ARM`), lalu menentukan apakah kondisi aman, hanya tersenggol, dibuka normal (ada jeda 10 detik untuk `DISARM`), atau dibuka paksa.

## Arsitektur Sistem

```text
 HP A (Edge 1 - di pintu)           HP B (Edge 2 - di dalam lemari)
 accelerometer + gyroscope          sensor cahaya (lux) + alarm
 -> sudut pintu, RMS getaran        -> lux rata-rata, light_delta
        |  telemetry                       |  telemetry        ^ alerts
        v                                  v                   |
                 MQTT Broker (HiveMQ publik, TLS 8883)
                              |  telemetry          ^ alerts, status
                              v                     |
                 Laptop: detector.py (sensor fusion + state machine)
                 Dashboard: dashboard/index.html (WSS 8884)
```

## Struktur File

| File / Folder | Fungsi |
| :--- | :--- |
| `hp_pintu.py` | Script Edge 1: baca sensor gerak, hitung sudut pintu & RMS getaran, kirim telemetry |
| `hp_dalam.py` | Script Edge 2: baca sensor cahaya, hitung rata-rata & lonjakan lux, kirim telemetry, nyalakan alarm saat alert |
| `detector.py` | Server di laptop: terima telemetry dari kedua HP, jalankan aturan deteksi, kirim status & alert |
| `nodes/detector_service/rules.py` | Logika sensor fusion, kalibrasi, dan perpindahan state (`ARM` / `DISARM`) |
| `shared/sensors.py` | Pembaca sensor Android lewat `termux-sensor` dan generator data simulator |
| `shared/processing.py` | Fungsi hitungan pengolahan data (RMS getaran, sudut pintu, rata-rata cahaya, kalibrasi) |
| `shared/mqtt_util.py` | Pengaturan koneksi MQTT TLS dan pembuatan nama topic |
| `shared/alarm.py` | Pemicu getar (`termux-vibrate`) dan notifikasi (`termux-notification`) di HP B |
| `shared/config.py` | Pembaca pengaturan dari file `.env` |
| `dashboard/index.html` | Halaman web pemantau status, grafik sudut & cahaya, riwayat alert, dan tombol `ARM`/`DISARM` |
| `tests/` | Unit test otomatis (28 test dengan `pytest`) |

## Pengolahan Data

Pengolahan data dilakukan di kedua HP sebelum dikirim ke broker, ditambah kalibrasi awal di laptop:

| Kode | Lokasi | Pengolahan | Rumus / Cara Hitung |
| :--- | :--- | :--- | :--- |
| **A** | Edge 1 (`hp_pintu.py`) | RMS getaran | `sqrt(mean((|a| - 9.81)^2))` — mengurangi gravitasi dari total percepatan 3 sumbu |
| **B** | Edge 1 (`hp_pintu.py`) | Sudut bukaan pintu | `sudut += (gyro . arah_gravitasi) * dt` — proyeksi kecepatan putar ke sumbu gravitasi agar posisi tempel HP bebas |
| **C** | Edge 2 (`hp_dalam.py`) | Rata-rata cahaya | Rata-rata bergerak (*moving average*) dari 3 window pembacaan lux terakhir |
| **D** | Edge 2 (`hp_dalam.py`) | Lonjakan cahaya (`light_delta`) | `lux_rata_rata - baseline_EMA` — selisih cahaya saat ini terhadap baseline normal |
| **E** | Laptop (`detector.py`) | Kalibrasi adaptif | `ambang = mean + max(3 * std, margin)` — dihitung otomatis selama 10 detik pertama setelah `ARM` |

## Algoritma Keputusan (Saat Status `ARMED`)

Urutan perpindahan *state* sistem:  
`DISARMED` $\rightarrow$ `CALIBRATING` (10 detik) $\rightarrow$ `ARMED` $\rightarrow$ `ENTRY_DELAY` (10 detik) $\rightarrow$ `ALARM`.

Saat sudah `ARMED`, keputusan diambil dengan menggabungkan data HP A dan HP B:

| Pintu Terbuka ($\ge 10^\circ$) | Cahaya Naik | Hentakan Keras ($\text{RMS} \ge 3$) | Status Keputusan | Keterangan |
| :--- | :--- | :--- | :--- | :--- |
| Tidak | Tidak / Ya | Tidak | `AMAN` | Pintu diam tertutup (cahaya luar dari celah pintu diabaikan) |
| Bergerak / Terbuka | Tidak | Tidak | `PINTU_DIGERAKKAN` | Peringatan: pintu bergeser sedikit atau dibuka saat ruangan gelap |
| Ya | Ya | Tidak | `MENUNGGU_DISARM` $\rightarrow$ `ALERT_DIBUKA` | Masuk waktu tunggu 10 detik. Jika tidak di-`DISARM`, alarm berbunyi |
| Ya *(atau cahaya naik)* | — | Ya | `ALERT_DIPAKSA` | Pintu dibuka kasar/dihentak, alarm langsung berbunyi tanpa jeda |

Jika sudah masuk status `ALARM`, bunyi peringatan akan bertahan sampai pengguna mengirim perintah `DISARM`.

## Topik Komunikasi MQTT

Menggunakan broker publik `broker.hivemq.com` (port `8883` TLS untuk Python dan port `8884` WebSocket TLS untuk browser).

| Topic | Arah | Isi Pesan |
| :--- | :--- | :--- |
| `laciguard/<ID>/edge/edge1/telemetry` | Edge 1 $\rightarrow$ Broker | `door_angle_deg`, `motion_rms`, nomor urut paket |
| `laciguard/<ID>/edge/edge2/telemetry` | Edge 2 $\rightarrow$ Broker | `light_lux`, `light_delta`, nomor urut paket |
| `laciguard/<ID>/alerts` | Detector $\rightarrow$ Broker | `status`, `reason`, nilai sensor saat kejadian |
| `laciguard/<ID>/status` | Detector $\rightarrow$ Broker (*retained*) | State aktif, status keputusan, nilai ambang hasil kalibrasi |
| `laciguard/<ID>/control` | Dashboard / CLI $\rightarrow$ Detector | Perintah `ARM` atau `DISARM` |

Contoh tes kirim perintah manual dari terminal:
```bash
mosquitto_pub -h broker.hivemq.com -t "laciguard/<ID>/control" -m ARM
```

## Cara Menjalankan

### 1. Persiapan di Semua Perangkat (Laptop, HP A, dan HP B)
Untuk kedua HP Android, pasang **Termux** dan **Termux:API** dari F-Droid, lalu jalankan perintah ini di Termux:
```bash
pkg install python git termux-api
termux-wake-lock
termux-sensor -l
```

Setelah itu, clone repo dan pasang library Python di laptop maupun kedua HP:
```bash
git clone https://github.com/fransranju-sys/laciguard-IoT.git
cd laciguard-IoT
cp .env.example .env
pip install -r requirements.txt
```
Edit file `.env` dan samakan isi `PROJECT_ID` di semua perangkat.

### 2. Menjalankan Sistem dengan 2 HP + Laptop
1. **Laptop (Server Detector):**
   ```bash
   python detector.py
   ```
   Ketik `arm` atau `disarm` di terminal untuk mengubah mode.
2. **HP A (Ditempel di pintu):**
   ```bash
   python hp_pintu.py
   ```
3. **HP B (Di dalam lemari):**
   ```bash
   python hp_dalam.py
   ```
   *(Jika pembacaan `termux-sensor` mode stream macet di HP tertentu, tambahkan argumen `--mode poll`).*
4. **Dashboard Web:**
   Buka file `dashboard/index.html` di browser laptop/HP, isi `PROJECT_ID` yang sama dengan `.env`, lalu klik **Hubungkan**.

### 3. Menjalankan Mode Simulator (Tanpa HP, untuk Tes di Laptop)
```bash
# Terminal 1
python detector.py

# Terminal 2 (simulasi HP pintu)
python hp_pintu.py --source simulator --scenario open --event-after 40

# Terminal 3 (simulasi HP dalam lemari)
python hp_dalam.py --source simulator --scenario open --event-after 40
```
Ketik `arm` di terminal `detector.py`, lalu tunggu sekitar 40 detik untuk melihat simulasi pintu dibuka. Pilihan skenario simulator: `still`, `open`, dan `force`.

## Catatan Pemasangan dan Pengaturan

- **Jenis pintu:** Perhitungan sudut dari *gyroscope* dirancang untuk pintu berengsel vertikal (lemari pakaian atau pintu kamar). Pada laci tarik/geser lurus, *gyroscope* tidak berputar sehingga deteksi hanya mengandalkan hentakan *accelerometer* (RMS) dan perubahan cahaya.
- **Posisi HP A:** Tempelkan rapat di daun pintu dengan selotip dua sisi atau karet. Posisi miring tidak masalah karena sumbu putar dihitung mengikuti arah gravitasi.
- **Posisi HP B:** Letakkan di dalam lemari dengan bagian atas layar (sensor cahaya) tidak tertutup barang. Jangan mengubah kecerahan layar setelah kalibrasi selesai.
- **Waktu kalibrasi:** Selama 10 detik pertama setelah tombol `ARM` ditekan, biarkan pintu tertutup dan jangan disentuh.
- **Parameter aturan:** Nilai ambang seperti `open_deg`, `nudge_deg`, `force_rms`, `entry_delay_s`, `calibration_s`, `rms_margin`, dan `light_margin` bisa disesuaikan di dalam `nodes/detector_service/rules.py` pada bagian `RuleConfig`.

## Pengujian

Untuk menjalankan unit test otomatis:
```bash
pip install pytest
pytest -q
```

Daftar skenario pengujian fisik untuk demo dan dokumentasi:
1. **Kondisi diam (`AMAN`):** aktifkan `ARM`, tunggu kalibrasi 10 detik selesai, pintu dibiarkan tertutup.
2. **Dibuka pelan tanpa izin (`ALERT_DIBUKA`):** buka pintu saat `ARMED` dan biarkan lebih dari 10 detik tanpa menekan `DISARM`.
3. **Dibuka pemilik (`MENUNGGU_DISARM` $\rightarrow$ `DISARMED`):** buka pintu lalu tekan `DISARM` sebelum 10 detik habis (alarm tidak jadi berbunyi).
4. **Dibuka paksa (`ALERT_DIPAKSA`):** tarik atau hentakkan pintu dengan keras saat `ARMED` (alarm langsung bunyi tanpa jeda).
5. **Uji gangguan cahaya luar:** nyalakan atau matikan lampu kamar saat pintu lemari tertutup (status tetap `AMAN`).
6. **Mode nonaktif (`DISARMED`):** tekan `DISARM` lalu buka pintu (status tetap `AMAN`).

## Referensi

Struktur dasar komunikasi MQTT, pembacaan sensor, dan dashboard mengadaptasi pola dari repositori contoh kuliah [PocketGuard (contoh-project-iot1)](https://www.google.com/search?q=https://github.com/myudak/contoh-project-iot1) (lisensi MIT). Kasus penggunaan, gabungan sensor gerak dan cahaya, perhitungan sudut pintu, serta aturan state machine pada LaciGuard dibuat sendiri oleh Kelompok 15.
