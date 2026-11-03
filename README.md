# 🐟 Dashboard Monitoring Kolam Ikan Nila (Real-Time)

Aplikasi web dashboard berbasis **Streamlit** untuk memantau suhu dan kelembapan kolam ikan nila secara langsung (real-time) melalui **Firebase Realtime Database**.

---

## 🚀 Fitur Utama
* **Data Aktual Firebase**: Membaca data langsung dari node `/device/current`, `/device/power`, dan `/device/history`.
* **Metrik Sensor Terkini**: Menampilkan suhu, kelembapan, status power perangkat, dan versi firmware.
* **Prediksi Suhu**: Visualisasi prediksi suhu 30 menit ke depan beserta zona aman/ideal untuk ikan nila (28°C - 33°C).
* **Grafik Dinamis**: Grafik riwayat suhu dan kelembapan interaktif menggunakan Plotly.
* **Tabel Riwayat & Ekspor CSV**: Menampilkan seluruh titik data yang ditarik dan menyediakan tombol unduh CSV.
* **Auto-refresh**: Otomatis memperbarui data setiap 30 detik.

---

## 🛠️ Persyaratan & Instalasi
Untuk menjalankan secara lokal:

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```
