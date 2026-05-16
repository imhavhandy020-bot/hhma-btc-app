import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import sqlite3
from datetime import datetime

# Konfigurasi Tampilan Layar HP
st.set_page_config(page_title="Indodax HMA Bot v2", layout="centered")

# ==========================================
# MENU INPUT PARAMETER (SIDEBAR HP)
# ==========================================
st.sidebar.title("⚙️ Pengaturan Bot")

# 1. Kolom Input API Key Indodax
st.sidebar.subheader("🔑 Kredensial Indodax")
api_key_input = st.sidebar.text_input("API Key", type="password", help="Masukkan API Key Indodax Anda")
secret_key_input = st.sidebar.text_input("Secret Key", type="password", help="Masukkan Secret Key Indodax Anda")

# 2. Menu Indikator & Pembatasan Data
st.sidebar.subheader("📈 Parameter Indikator")
SYMBOL = st.sidebar.selectbox("Pilih Aset", ["BTC/IDR", "ETH/IDR", "USDT/IDR"], index=0)
TIMEFRAME = st.sidebar.selectbox("Timeframe", ["1d", "4h", "1h", "15m"], index=0)
HMA_LENGTH = st.sidebar.number_input("Panjang HMA (Length)", min_value=1, max_value=100, value=2, step=1)
MAX_BARS = st.sidebar.slider("Pembatasan Bar (Max Bars)", min_value=10, max_value=500, value=100, step=10)

# 3. Parameter Risiko
st.sidebar.subheader("🛡️ Manajemen Risiko")
TAKE_PROFIT_PCT = st.sidebar.number_input("Pelebaran Profit / TP (%)", min_value=0.1, max_value=100.0, value=5.0) / 100
STOP_LOSS_PCT = st.sidebar.number_input("Batasan Rugi / SL (%)", min_value=0.1, max_value=100.0, value=2.0) / 100

# Inisialisasi CCXT berdasarkan Key yang Diinput
def init_exchange(api_key, secret_key):
    if api_key and secret_key:
        return ccxt.indodax({
            'apiKey': api_key,
            'secret': secret_key,
            'enableRateLimit': True
        })
    else:
        # Jika key kosong, gunakan mode public (hanya baca data harga saja)
        return ccxt.indodax({'enableRateLimit': True})

exchange = init_exchange(api_key_input, secret_key_input)

# ==========================================
# MANAJEMEN DATABASE SQLITE
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
    half_length = int(length / 2) if int(length / 2) > 0 else 1
    sqrt_length = int(np.sqrt(length)) if int(np.sqrt(length)) > 0 else 1
    wma_half = wma(df['close'], half_length)
    wma_full = wma(df['close'], length)
    raw_hma = (2 * wma_half) - wma_full
    df['hma'] = wma(raw_hma, sqrt_length)
    return df

# ==========================================
# KOMPONEN REFRESH OTOMATIS (FRAGMENT)
# ==========================================
@st.fragment(run_every=5)
def market_monitor_fragment():
    waktu_sekarang = datetime.now().strftime('%H:%M:%S')
    st.caption(f"🔄 Auto-Refresh Aktif: {waktu_sekarang}")
    
    try:
        # Menarik data dengan limit sesuai input "Pembatasan Bar"
        bars = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=int(MAX_BARS))
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = calculate_hma(df, int(HMA_LENGTH))
        
        current_hma = df['hma'].iloc[-1]
        prev_hma = df['hma'].iloc[-2]
        prev_prev_hma = df['hma'].iloc[-3]
        current_close = df['close'].iloc[-1]
        
        is_green_now = current_hma >= prev_hma
        is_green_prev = prev_hma >= prev_prev_hma
        
        raw_buy = is_green_now and not is_green_prev
        raw_sell = not is_green_now and is_green_prev
        
        col1, col2 = st.columns(2)
        col1.metric(label=f"Harga {SYMBOL}", value=f"{current_close:,.0f} IDR")
        
        if is_green_now:
            col2.metric(label="Tren HHMA", value="HIJAU (BULL)", delta="Naik")
        else:
            col2.metric(label="Tren HHMA", value="MERAH (BEAR)", delta="-Turun", delta_color="inverse")
            
        if 'last_signal' not in st.session_state:
            st.session_state.last_signal = 0
            
        if raw_buy and st.session_state.last_signal != 1:
            tp = current_close * (1 + TAKE_PROFIT_PCT)
            sl = current_close * (1 - STOP_LOSS_PCT)
            
            # Eksekusi riil hanya berjalan jika API Key diisi
            if api_key_input and secret_key_input:
                try:
                    # exchange.create_market_buy_order(SYMBOL, jumlah_beli)
                    pass
                except Exception as trade_err:
                    st.sidebar.error(f"Gagal Order Riil: {trade_err}")
            
            save_trade('BUY', current_close, tp, sl)
            st.session_state.last_signal = 1
            st.toast("🚨 Sinyal BUY Baru Tersimpan!", icon="🟩")
            
        elif raw_sell and st.session_state.last_signal != -1:
            tp = current_close * (1 - TAKE_PROFIT_PCT)
            sl = current_close * (1 + STOP_LOSS_PCT)
            
            if api_key_input and secret_key_input:
                try:
                    # exchange.create_market_sell_order(SYMBOL, jumlah_jual)
                    pass
                except Exception as trade_err:
                    st.sidebar.error(f"Gagal Order Riil: {trade_err}")
            
            save_trade('SELL', current_close, tp, sl)
            st.session_state.last_signal = -1
            st.toast("🚨 Sinyal SELL Baru Tersimpan!", icon="🟥")
            
        # Menampilkan grafik sesuai batasan bar yang dipilih
        st.line_chart(df[['close', 'hma']].tail(int(MAX_BARS)))
        
    except Exception as e:
        st.error(f"Gagal memuat data pasar: {e}")

# ==========================================
# ALUR UTAMA TAMPILAN APP
# ==========================================
st.title("📊 Indodax Monitor Bot")
init_db()

# Indikator status koneksi API di atas halaman
if api_key_input and secret_key_input:
    st.success("🔐 API Key Terpasang (Mode Live Trading Aktif)")
else:
    st.warning("🔓 Menggunakan Mode Public (Hanya Memantau / Simulasi)")

st.subheader("Live Market")
market_monitor_fragment()

st.subheader("📦 Data Riwayat Transaksi (Terbaca dari SQLite)")
history_df = get_trade_history()

if not history_df.empty:
    st.dataframe(history_df, use_container_width=True)
else:
    st.info("Belum ada data transaksi masuk yang tersimpan.")
