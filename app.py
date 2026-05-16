import streamlit as tf
import pandas as pd
import numpy as np
import sqlite3
import time
from datetime import datetime, timedelta

# --- CONFIGURASI UTAMA ---
PAIR_UTAMA = "BTC/IDR"
TIMEFRAME = "4h"
INTERVAL_DETIK = 5
DB_NAME = "trading_bot.db"

# Target Manajemen Risiko (Persentase)
TP_PERSEN = 5.0  # Take Profit 5%
SL_PERSEN = 2.0  # Stop Loss 2%

tf.set_page_config(page_title="Indodax Multi-Pair Pro", layout="wide")
tf.title("🤖 Bot Trading Indodax Multi-Pair Pro (Fixed KeyError)")

# --- INITIALISASI & MIGRASI DATABASE PERMANEN ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # 1. Buat tabel dasar jika belum ada
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS posisi (
            pair TEXT PRIMARY KEY,
            status TEXT,
            harga_beli REAL,
            waktu_eksekusi TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS riwayat (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT,
            tipe TEXT,
            harga REAL,
            keterangan TEXT,
            waktu TEXT
        )
    ''')
    
    # 2. AUTO-MIGRASI: Tambah kolom baru jika database lama masih memakai struktur lama
    cursor.execute("PRAGMA table_info(posisi)")
    kolom_ada = [info[1] for info in cursor.fetchall()]
    
    if "harga_tp" not in kolom_ada:
        cursor.execute("ALTER TABLE posisi ADD COLUMN harga_tp REAL DEFAULT 0.0")
    if "harga_sl" not in kolom_ada:
        cursor.execute("ALTER TABLE posisi ADD COLUMN harga_sl REAL DEFAULT 0.0")
        
    # 3. Isi data awal jika baris pair belum terdaftar
    cursor.execute("SELECT COUNT(*) FROM posisi WHERE pair = ?", (PAIR_UTAMA,))
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO posisi VALUES (?, ?, ?, ?, ?, ?)", (PAIR_UTAMA, "CARI_BUY", 0.0, "-", 0.0, 0.0))
        
    conn.commit()
    conn.close()

# Jalankan inisialisasi dan migrasi database sebelum membaca data
init_db()

# --- STANDALONE MOCK ENGINE (Anti-Blokir & Delay) ---
def ambil_data_feed(pair):
    np.random.seed(int(time.time()) // 1000) 
    harga_dasar = 1_000_000_000 # ~1 Milyar IDR
    waktu_sekarang = datetime.now()
    list_waktu = [waktu_sekarang - timedelta(hours=4*i) for i in range(50, -1, -1)]
    
    close_prices = harga_dasar + np.cumsum(np.random.normal(0, 15000000, len(list_waktu)))
    open_prices = close_prices - np.random.normal(0, 5000000, len(list_waktu))
    high_prices = np.maximum(open_prices, close_prices) + np.abs(np.random.normal(0, 3000000, len(list_waktu)))
    low_prices = np.minimum(open_prices, close_prices) - np.abs(np.random.normal(0, 3000000, len(list_waktu)))
    
    df = pd.DataFrame({
        'waktu': list_waktu,
        'open': open_prices,
        'high': high_prices,
        'low': low_prices,
        'close': close_prices
    })
    return df

# --- PERHITUNGAN FORMULA HMA-20 (OFFSET = -1) ---
def hitung_wma(series, period):
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def hitung_hma(df, period=20):
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    wma_half = hitung_wma(df['close'], half_period)
    wma_full = hitung_wma(df['close'], period)
    raw_hma = (2 * wma_half) - wma_full
    df['hma'] = hitung_wma(raw_hma, sqrt_period)
    df['hma_signal'] = df['hma'].shift(1)
    return df

# --- FUNGSI UTILITAS DATABASE ---
def dapatkan_status():
    conn = sqlite3.connect(DB_NAME)
    df = pd.read_sql(f"SELECT * FROM posisi WHERE pair='{PAIR_UTAMA}'", conn)
    conn.close()
    return df.iloc[0] if not df.empty else None

def eksekusi_buy(harga):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    waktu_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    tp_harga = harga * (1 + (TP_PERSEN / 100))
    sl_harga = harga * (1 - (SL_PERSEN / 100))
    
    cursor.execute(
        "UPDATE posisi SET status=?, harga_beli=?, harga_tp=?, harga_sl=?, waktu_eksekusi=? WHERE pair=?",
        ("BUY_SUCCESS", harga, tp_harga, sl_harga, waktu_str, PAIR_UTAMA)
    )
    cursor.execute(
        "INSERT INTO riwayat (pair, tipe, harga, keterangan, waktu) VALUES (?, ?, ?, ?, ?)",
        (PAIR_UTAMA, "BUY", harga, f"Target TP: {tp_harga:,.0f} | SL: {sl_harga:,.0f}", waktu_str)
    )
    conn.commit()
    conn.close()

def eksekusi_sell(harga, alasan):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    waktu_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute(
        "UPDATE posisi SET status=?, harga_beli=?, harga_tp=?, harga_sl=?, waktu_eksekusi=? WHERE pair=?",
        ("CARI_BUY", 0.0, 0.0, 0.0, waktu_str, PAIR_UTAMA)
    )
    cursor.execute(
        "INSERT INTO riwayat (pair, tipe, harga, keterangan, waktu) VALUES (?, ?, ?, ?, ?)",
        (PAIR_UTAMA, "SELL", harga, f"Sinyal Keluar: {alasan}", waktu_str)
    )
    conn.commit()
    conn.close()

# --- ENGINE LOGIKA UTAMA (HMA + TP/SL PROTECTION) ---
df_Clean = ambil_data_feed(PAIR_UTAMA)
df_Indikator = hitung_hma(df_Clean, period=20)

bar_terakhir = df_Indikator.iloc[-1]
harga_live = bar_terakhir['close']
hma_aktif = bar_terakhir['hma_signal']

status_sekarang = dapatkan_status()

if status_sekarang is not None:
    if status_sekarang['status'] == "CARI_BUY":
        if harga_live > hma_aktif:
            eksekusi_buy(harga_live)

    elif status_sekarang['status'] == "BUY_SUCCESS":
        # Proteksi Berbasis Nilai Numerik Aman
        batasi_tp = float(status_sekarang['harga_tp'])
        batasi_sl = float(status_sekarang['harga_sl'])
        
        if harga_live >= batasi_tp and batasi_tp > 0:
            eksekusi_sell(harga_live, f"TAKE PROFIT HIT ({TP_PERSEN}%)")
        elif harga_live <= batasi_sl and batasi_sl > 0:
            eksekusi_sell(harga_live, f"STOP LOSS HIT (-{SL_PERSEN}%)")
        elif harga_live < hma_aktif:
            eksekusi_sell(harga_live, "HMA CROSS DOWN")

# --- ANTARMUKA STREAMLIT UI ---
status_terbaru = dapatkan_status()

col1, col2, col3, col4 = tf.columns(4)
col1.metric("Pair Pantauan", PAIR_UTAMA)
col2.metric("Harga Live", f"Rp {harga_live:,.0f}")
col3.metric(f"HMA-20 (4h Offset -1)", f"Rp {hma_aktif:,.0f}")
col4.metric("Status Bot", status_terbaru['status'] if status_terbaru is not None else "-")

tf.markdown(f"**🛡️ Pengaman Aktif:** Take Profit: `{TP_PERSEN}%` | Stop Loss: `{SL_PERSEN}%`")

tf.subheader("📊 Analisis Data Real-Time")
tf.line_chart(df_Indikator.set_index('waktu')[['close', 'hma_signal']])

col_status, col_log = tf.columns(2)

with col_status:
    tf.markdown("### 📌 Posisi & Batas Pengaman")
    if status_terbaru is not None:
        tf.json({
            "Pair": status_terbaru['pair'],
            "Status Order": status_terbaru['status'],
            "Harga Beli": f"Rp {status_terbaru['harga_beli']:,.0f}",
            "Batas Target TP": f"Rp {status_terbaru['harga_tp']:,.0f}",
            "Batas Resiko SL": f"Rp {status_terbaru['harga_sl']:,.0f}",
            "Waktu Sinyal": status_terbaru['waktu_eksekusi']
        })

with col_log:
    tf.markdown("### 📜 Riwayat Transaksi (Database)")
    conn = sqlite3.connect(DB_NAME)
    try:
        df_riwayat = pd.read_sql("SELECT * FROM riwayat ORDER BY id DESC LIMIT 5", conn)
    except Exception:
        df_riwayat = pd.DataFrame()
    conn.close()
    
    if not df_riwayat.empty:
        tf.dataframe(df_riwayat, use_container_width=True)
    else:
        tf.info("Belum ada transaksi TP/SL atau HMA yang terekam.")

# Fitur Auto Refresh Berkecepatan Tinggi (5 Detik)
time.sleep(INTERVAL_DETIK)
tf.rerun()
