"""
================================================================
DASHBOARD MONITORING IKAN NILA — FIREBASE REALTIME
================================================================
Khusus menampilkan data aktual yang diambil langsung dari Firebase:
- /device/current   : Data sensor terkini (temp, humi, ts, firmware)
- /device/power     : Status daya perangkat (True / False)
- /device/history   : Riwayat data sensor & prediksi aktual
================================================================
"""

import os
import base64
import requests
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from dotenv import load_dotenv

# ── Konfigurasi Kredensial Firebase ──────────────────────────
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

_DEFAULT_URL = "https://amonia-projet-ta-default-rtdb.asia-southeast1.firebasedatabase.app"
_DEFAULT_KEY = base64.b64decode("dXVkRHd6Smk1bGxJVDI3NVBreTdPcVSTRjNqTlk0aHNrMGpQSVAyUA==").decode("utf-8")

def get_firebase_credentials():
    # 1. Dari Streamlit Secrets jika diisi
    try:
        if "FIREBASE_URL" in st.secrets and "FIREBASE_API_KEY" in st.secrets:
            return st.secrets["FIREBASE_URL"], st.secrets["FIREBASE_API_KEY"]
    except Exception:
        pass

    # 2. Dari Environment Variable / .env jika ada
    url = os.getenv("FIREBASE_URL", "")
    key = os.getenv("FIREBASE_API_KEY", "")
    if url and key:
        return url, key

    # 3. Default bawaan proyek
    return _DEFAULT_URL, _DEFAULT_KEY

FIREBASE_URL, FIREBASE_KEY = get_firebase_credentials()
if FIREBASE_URL and not FIREBASE_URL.startswith("https://"):
    FIREBASE_URL = f"https://{FIREBASE_URL}"

# ── Konfigurasi Halaman Streamlit ────────────────────────────
st.set_page_config(
    page_title="Monitoring Ikan Nila 🐟",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling Dark Ocean Theme
st.markdown("""
<style>
    .stApp { background-color: #0b132b; color: #e0e6ed; }
    div[data-testid="metric-container"] {
        background-color: #1c2541;
        border: 1px solid #3a506b;
        border-radius: 10px;
        padding: 14px 18px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.2);
    }
    div[data-testid="metric-container"] label {
        color: #6fffe9 !important;
        font-weight: 600 !important;
        font-size: 13px !important;
    }
    div[data-testid="metric-container"] div[data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 30px !important;
        font-weight: 700 !important;
    }
    .header-panel {
        background: linear-gradient(135deg, #1c2541, #0b132b);
        border: 1px solid #48cae4;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)


# ── Fungsi Pengambilan Data dari Firebase ───────────────────
def konversi_waktu(ts_raw):
    """Konversi timestamp ms / ISO string ke format waktu lokal (WIB)."""
    if pd.isna(ts_raw):
        return None
    try:
        if isinstance(ts_raw, (int, float)) or (isinstance(ts_raw, str) and ts_raw.isdigit()):
            ts_int = int(ts_raw)
            unit = "ms" if ts_int > 1e11 else "s"
            return pd.to_datetime(ts_int, unit=unit, utc=True).tz_convert("Asia/Jakarta")
        dt = pd.to_datetime(ts_raw, errors="coerce")
        if dt.tzinfo is None:
            return dt.tz_localize("UTC").tz_convert("Asia/Jakarta")
        return dt.tz_convert("Asia/Jakarta")
    except Exception:
        return pd.to_datetime(ts_raw, errors="coerce")


@st.cache_data(ttl=15)
def ambil_data_firebase(limit_history=100):
    """
    Mengambil data murni dari Firebase:
    1. /device/current.json (Data sekarang)
    2. /device/power.json   (Status daya)
    3. /device/history.json (Riwayat data)
    """
    if not FIREBASE_URL or not FIREBASE_KEY:
        return None, None, None, "Kredensial Firebase belum terkonfigurasi."

    current_data = None
    power_data   = None
    df_history   = pd.DataFrame()

    try:
        # 1. Ambil data current
        url_current = f"{FIREBASE_URL}/device/current.json"
        res_curr = requests.get(url_current, params={"auth": FIREBASE_KEY}, timeout=10)
        if res_curr.status_code == 200:
            current_data = res_curr.json()

        # 2. Ambil status power
        url_power = f"{FIREBASE_URL}/device/power.json"
        res_pow = requests.get(url_power, params={"auth": FIREBASE_KEY}, timeout=8)
        if res_pow.status_code == 200:
            power_data = res_pow.json()

        # 3. Ambil data history
        url_hist = f"{FIREBASE_URL}/device/history.json"
        params_hist = {"auth": FIREBASE_KEY}
        if limit_history and limit_history > 0:
            params_hist["orderBy"] = '"$key"'
            params_hist["limitToLast"] = limit_history

        res_hist = requests.get(url_hist, params=params_hist, timeout=15)
        if res_hist.status_code == 200:
            raw_hist = res_hist.json()
            if raw_hist and isinstance(raw_hist, dict):
                rows = []
                for key_id, item in raw_hist.items():
                    if isinstance(item, dict):
                        row = item.copy()
                        row["firebase_key"] = key_id
                        rows.append(row)
                if rows:
                    df_history = pd.DataFrame(rows)
                    if "ts" in df_history.columns:
                        df_history["waktu_wib"] = df_history["ts"].apply(konversi_waktu)
                        df_history = df_history.sort_values("waktu_wib").reset_index(drop=True)

        return current_data, power_data, df_history, None

    except requests.exceptions.RequestException as e:
        return None, None, None, f"Koneksi ke Firebase gagal: {str(e)}"
    except Exception as e:
        return None, None, None, f"Terjadi kesalahan: {str(e)}"


# ── Sidebar Pengaturan ───────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Pengaturan Data")
    st.write("Dashboard ini hanya menampilkan data yang tersimpan di Firebase.")
    
    limit_opsi = st.selectbox(
        "Jumlah Baris Riwayat:",
        options=[50, 100, 200, 500, 1000, 2500],
        index=1,
        help="Berapa banyak data terakhir dari /device/history yang ingin ditarik."
    )
    
    st.markdown("---")
    st.subheader("🌐 Info Koneksi")
    st.code(f"Database: {FIREBASE_URL.replace('https://', '') if FIREBASE_URL else 'Tidak ada'}", language="text")
    st.caption("Node aktif: `/device/current`, `/device/history`, `/device/power`")

    st.markdown("---")
    if st.button("🔄 Segarkan Data Sekarang", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── Mengambil Data ───────────────────────────────────────────
current, power, history_df, error_msg = ambil_data_firebase(limit_history=limit_opsi)

# ── Header Dashboard ─────────────────────────────────────────
st.markdown("""
<div class="header-panel">
    <h2 style="color: #6fffe9; margin: 0; font-size: 26px;">🐟 Dashboard Monitoring Kolam Ikan Nila</h2>
    <p style="color: #8da9c4; margin: 4px 0 0 0; font-size: 14px;">
        Penyajian data murni real-time dari Firebase Database (ESP32 &amp; Model Prediksi)
    </p>
</div>
""", unsafe_allow_html=True)

# ── Penanganan Error / Kosong ────────────────────────────────
if error_msg:
    st.error(f"❌ {error_msg}")
    st.stop()

if not current and history_df.empty:
    st.warning("⚠️ Belum ada data di node `/device` pada Firebase Anda.")
    st.stop()


# ── Persiapan Data Terkini ───────────────────────────────────
latest_temp = None
latest_humi = None
latest_firmware = "-"
latest_ts_str = "-"
latest_pred = None
latest_status = None

if current:
    latest_temp = current.get("temp")
    latest_humi = current.get("humi")
    latest_firmware = current.get("firmware", "-")
    ts_val = current.get("ts")
    if ts_val:
        dt_curr = konversi_waktu(ts_val)
        latest_ts_str = dt_curr.strftime("%d %b %Y, %H:%M:%S WIB") if pd.notna(dt_curr) else str(ts_val)

if not history_df.empty:
    last_row = history_df.iloc[-1]
    if latest_temp is None:
        latest_temp = last_row.get("temp")
    if latest_humi is None:
        latest_humi = last_row.get("humi")
    if latest_firmware == "-" and "firmware" in last_row:
        latest_firmware = last_row.get("firmware", "-")
    if latest_ts_str == "-" and "waktu_wib" in last_row:
        dt_last = last_row["waktu_wib"]
        latest_ts_str = dt_last.strftime("%d %b %Y, %H:%M:%S WIB") if pd.notna(dt_last) else "-"
    
    df_with_pred = history_df.dropna(subset=["predicted_val"]) if "predicted_val" in history_df.columns else pd.DataFrame()
    if not df_with_pred.empty:
        latest_pred = df_with_pred.iloc[-1]["predicted_val"]
        latest_status = df_with_pred.iloc[-1].get("status", "-")

# Hitung selisih dari data sebelumnya jika riwayat tersedia
delta_temp = None
delta_humi = None
if len(history_df) >= 2 and "temp" in history_df.columns:
    try:
        t_now = float(history_df.iloc[-1]["temp"])
        t_prev = float(history_df.iloc[-2]["temp"])
        delta_temp = round(t_now - t_prev, 2)
    except Exception:
        pass

if len(history_df) >= 2 and "humi" in history_df.columns:
    try:
        h_now = float(history_df.iloc[-1]["humi"])
        h_prev = float(history_df.iloc[-2]["humi"])
        delta_humi = round(h_now - h_prev, 2)
    except Exception:
        pass


# ── Baris Metrik Utama ───────────────────────────────────────
st.subheader("📊 Data Sensor Terkini")

m1, m2, m3, m4, m5 = st.columns(5)

with m1:
    st.metric(
        label="🌡️ Suhu Terkini",
        value=f"{float(latest_temp):.1f} °C" if latest_temp is not None else "-",
        delta=f"{delta_temp:+.1f} °C" if delta_temp is not None else None,
        delta_color="inverse"
    )

with m2:
    st.metric(
        label="💧 Kelembapan Terkini",
        value=f"{float(latest_humi):.1f} %" if latest_humi is not None else "-",
        delta=f"{delta_humi:+.1f} %" if delta_humi is not None else None
    )

with m3:
    st.metric(
        label="🔮 Prediksi Suhu",
        value=f"{float(latest_pred):.2f} °C" if latest_pred is not None else "Belum Ada",
        delta=f"{float(latest_pred) - float(latest_temp):+.2f} °C" if (latest_pred is not None and latest_temp is not None) else None,
        delta_color="inverse"
    )

with m4:
    status_label = latest_status if latest_status else ("Normal" if latest_temp and 28 <= float(latest_temp) <= 33 else "Waspada")
    st.metric(
        label="⚡ Status Model / Kondisi",
        value=str(status_label)
    )

with m5:
    power_label = "AKTIF (ON)" if power is True else ("MATI (OFF)" if power is False else "-")
    st.metric(
        label="🔌 Power Perangkat",
        value=power_label
    )

# Info Waktu dan Firmware
col_info1, col_info2, col_info3 = st.columns([2, 1, 1])
with col_info1:
    st.caption(f"🕒 Waktu Update: **{latest_ts_str}**")
with col_info2:
    st.caption(f"📦 Versi Firmware: **{latest_firmware}**")
with col_info3:
    st.caption(f"📈 Total Data Terambil: **{len(history_df)} Baris**")

st.markdown("---")


# ── Grafik Data Riwayat ──────────────────────────────────────
if not history_df.empty:
    st.subheader(f"📈 Grafik Riwayat ({len(history_df)} Titik Terakhir)")

    x_axis = history_df["waktu_wib"] if "waktu_wib" in history_df.columns else history_df.index

    # 1. Grafik Suhu (Aktual vs Prediksi)
    fig_temp = go.Figure()
    
    if "temp" in history_df.columns:
        fig_temp.add_trace(go.Scatter(
            x=x_axis,
            y=history_df["temp"],
            mode="lines+markers",
            name="Suhu Aktual (°C)",
            line=dict(color="#48cae4", width=2),
            marker=dict(size=4),
            hovertemplate="<b>%{x|%d/%m/%Y %H:%M}</b><br>Suhu: %{y:.2f} °C<extra></extra>"
        ))
    
    if "predicted_val" in history_df.columns and history_df["predicted_val"].notna().any():
        df_pred_plot = history_df.dropna(subset=["predicted_val"])
        x_pred = df_pred_plot["waktu_wib"] if "waktu_wib" in df_pred_plot.columns else df_pred_plot.index
        fig_temp.add_trace(go.Scatter(
            x=x_pred,
            y=df_pred_plot["predicted_val"],
            mode="lines",
            name="Prediksi Nilai (°C)",
            line=dict(color="#f77f00", width=2, dash="dash"),
            hovertemplate="<b>%{x|%d/%m/%Y %H:%M}</b><br>Prediksi: %{y:.2f} °C<extra></extra>"
        ))

    # Rentang Suhu Ideal Ikan Nila (28°C - 33°C)
    fig_temp.add_hrect(
        y0=28.0, y1=33.0,
        fillcolor="rgba(46, 196, 182, 0.08)",
        line_width=0,
        annotation_text="Rentang Suhu Ideal Ikan Nila (28°C - 33°C)",
        annotation_position="top left",
        annotation_font_color="#2ec4b6",
        annotation_font_size=11
    )

    fig_temp.update_layout(
        title="Dinamika Suhu Kolam & Hasil Prediksi",
        paper_bgcolor="#0b132b",
        plot_bgcolor="#1c2541",
        height=360,
        font=dict(color="#8da9c4"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="#3a506b", title="Waktu (WIB)"),
        yaxis=dict(gridcolor="#3a506b", title="Suhu (°C)"),
        hovermode="x unified"
    )
    st.plotly_chart(fig_temp, use_container_width=True)


    # 2. Grafik Kelembapan
    if "humi" in history_df.columns:
        fig_humi = go.Figure()
        fig_humi.add_trace(go.Scatter(
            x=x_axis,
            y=history_df["humi"],
            mode="lines",
            name="Kelembapan (%RH)",
            line=dict(color="#06d6a0", width=2),
            fill="tozeroy",
            fillcolor="rgba(6, 214, 160, 0.08)",
            hovertemplate="<b>%{x|%d/%m/%Y %H:%M}</b><br>Kelembapan: %{y:.1f} %<extra></extra>"
        ))
        fig_humi.update_layout(
            title="Tingkat Kelembapan Lingkungan (%RH)",
            paper_bgcolor="#0b132b",
            plot_bgcolor="#1c2541",
            height=280,
            font=dict(color="#8da9c4"),
            xaxis=dict(gridcolor="#3a506b", title="Waktu (WIB)"),
            yaxis=dict(gridcolor="#3a506b", title="Kelembapan (%)", range=[0, 100]),
            hovermode="x unified"
        )
        st.plotly_chart(fig_humi, use_container_width=True)

    st.markdown("---")

    # ── Tabel Data Murni dari Firebase ───────────────────────────
    st.subheader("📋 Tabel Data yang Diambil dari Firebase")
    
    tabel_df = history_df.copy()
    if "waktu_wib" in tabel_df.columns:
        tabel_df["Waktu (WIB)"] = tabel_df["waktu_wib"].dt.strftime("%Y-%m-%d %H:%M:%S")
    
    kolom_urut = []
    if "Waktu (WIB)" in tabel_df.columns: kolom_urut.append("Waktu (WIB)")
    if "temp" in tabel_df.columns:        kolom_urut.append("temp")
    if "humi" in tabel_df.columns:        kolom_urut.append("humi")
    if "predicted_val" in tabel_df.columns: kolom_urut.append("predicted_val")
    if "status" in tabel_df.columns:      kolom_urut.append("status")
    if "firmware" in tabel_df.columns:    kolom_urut.append("firmware")
    if "firebase_key" in tabel_df.columns: kolom_urut.append("firebase_key")

    sisa_kolom = [c for c in tabel_df.columns if c not in kolom_urut and c not in ["waktu_wib", "ts"]]
    kolom_tampil = kolom_urut + sisa_kolom

    tabel_display = tabel_df[kolom_tampil].sort_values("Waktu (WIB)", ascending=False) if "Waktu (WIB)" in tabel_df.columns else tabel_df.iloc[::-1]

    rename_map = {
        "temp": "Suhu (°C)",
        "humi": "Kelembapan (%RH)",
        "predicted_val": "Prediksi Suhu (°C)",
        "status": "Status",
        "firmware": "Firmware",
        "firebase_key": "ID Data"
    }
    tabel_display = tabel_display.rename(columns=rename_map)

    st.dataframe(
        tabel_display,
        use_container_width=True,
        hide_index=True
    )

    # Tombol Unduh CSV
    csv_bytes = tabel_display.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Unduh Data Ini (CSV)",
        data=csv_bytes,
        file_name=f"data_monitoring_ikan_nila_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )

else:
    st.info("ℹ️ Tidak ada data riwayat yang dapat dimuat.")

# ── Footer Otomatis ──────────────────────────────────────────
st.markdown("---")
st.markdown(
    f"<div style='text-align: center; color: #5c6b73; font-size: 12px;'>"
    f"Dashboard Monitoring Kolam Ikan Nila &bull; Data sumber langsung dari Firebase Realtime Database &bull; Diperbarui {datetime.now().strftime('%H:%M:%S WIB')}"
    f"</div>",
    unsafe_allow_html=True
)

try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=30_000, key="auto_refresh_loop")
except Exception:
    pass
