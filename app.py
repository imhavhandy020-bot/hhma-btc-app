import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import sqlite3
from datetime import datetime

# Konfigurasi Halaman Dasar agar Ramah Tampilan Layar HP
st.set_page_config(page_title="Indodax HMA Bot", layout="centered")

# ==========================================
# KONFIGURASI API INDODAX & STRATEGI
# ==========================================
SYMBOL = 'BTC/IDR'       
TIMEFRAME = '1d'         
HMA_LENGTH = 2           
TAKE_PROFIT_PCT = 0.05   
STOP_LOSS_PCT = 0.02     

# Inisialisasi API Publik Indodax (Simulasi / Baca Data)
@st.cache_resource
def init_exchange():
    return ccxt.indodax({'enableRateLimit': True})

exchange = init_exchange()

# ==========================================
# MANAJEMEN DATABASE SQLITE LOCAL
# ==========================================
def init_db():
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            signal_type TEXT,
            price REAL,
            tp_price REAL,
            sl_price REAL,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_trade_history():
    conn = sqlite3.connect('trading_bot.db')
    df = pd.read_sql_query("SELECT * FROM trades ORDER BY id DESC LIMIT 10", conn)
    conn.close()
    return df

def save_trade(signal_type, price, tp, sl):
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (timestamp, signal_type, price, tp_price, sl_price, status)
        VALUES (datetime('now'), ?, ?, ?, ?, 'OPEN')
    ''', (signal_type, price, tp, sl))
    conn.commit()
    conn.close()

# ==========================================
# RUMUS MATEMATIKA HMA
# ==========================================
def wma(series, length):
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def calculate_hma(df, length):
    half_length = int(length / 2)
    sqrt_length = int(np.sqrt(length))
    wma_half = wma(df['close'], half_length)
    wma_full = wma(df['close'], length)
    raw_hma = (2 * wma_half) - wma_full
    df['hma'] = wma(raw_hma, sqrt_length)
    return df

# ==========================================
# KOMPONEN REFRESH OTOMATIS (FRAGMENT)
# ==========================================
@st.fragment(run_every=5) # Paksa segarkan bagian ini setiap 5 detik
def market_monitor_fragment():
    waktu_sekarang = datetime.now().strftime('%H:%M:%S')
    st.caption(f"🔄 Auto-Refresh Aktif: {waktu_sekarang}")
    
    try:
        # Tarik data market terbaru
        bars = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=50)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = calculate_hma(df, HMA_LENGTH)
        
        current_hma = df['hma'].iloc[-1]
        prev_hma = df['hma'].iloc[-2]
        prev_prev_hma = df['hma'].iloc[-3]
        current_close = df['close'].iloc[-1]
        
        is_green_now = current_hma >= prev_hma
        is_green_prev = prev_hma >= prev_prev_hma
        
        raw_buy = is_green_now and not is_green_prev
        raw_sell = not is_green_now and is_green_prev
        
        # Kartu Informasi Utama di Layar HP
        col1, col2 = st.columns(2)
        col1.metric(label=f"Harga {SYMBOL}", value=f"{current_close:,.0f} IDR")
        
        if is_green_now:
            col2.metric(label="Tren HHMA", value="HIJAU (BULL)", delta="Naik")
        else:
            col2.metric(label="Tren HHMA", value="MERAH (BEAR)", delta="-Turun", delta_color="inverse")
            
        # Logika Sinyal dan Penyimpanan Otomatis
        if 'last_signal' not in st.session_state:
            st.session_state.last_signal = 0
            
        if raw_buy and st.session_state.last_signal != 1:
            tp = current_close * (1 + TAKE_PROFIT_PCT)
            sl = current_close * (1 - STOP_LOSS_PCT)
            save_trade('BUY', current_close, tp, sl)
            st.session_state.last_signal = 1
            st.toast("🚨 Sinyal BUY Baru Terdeteksi & Tersimpan!", icon="🟩")
            
        elif raw_sell and st.session_state.last_signal != -1:
            tp = current_close * (1 - TAKE_PROFIT_PCT)
            sl = current_close * (1 + STOP_LOSS_PCT)
            save_trade('SELL', current_close, tp, sl)
            st.session_state.last_signal = -1
            st.toast("🚨 Sinyal SELL Baru Terdeteksi & Tersimpan!", icon="🟥")
            
        # Grafik Garis Sederhana untuk HP
        st.line_chart(df[['close', 'hma']].tail(20))
        
    except Exception as e:
        st.error(f"Gagal memuat data pasar: {e}")

# ==========================================
# ALUR UTAMA TAMPILAN APP
# ==========================================
st.title("📊 Indodax Monitor Bot")
init_db()

# Jalankan pemantau harga real-time
st.subheader("Live Market")
market_monitor_fragment()

# Tampilkan data transaksi yang tersimpan permanen
st.subheader("📦 Data Riwayat Transaksi (Terbaca dari SQLite)")
history_df = get_trade_history()

if not history_df.empty:
    st.dataframe(history_df, use_container_width=True)
else:
    st.info("Belum ada data transaksi masuk yang tersimpan.")
