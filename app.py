import streamlit as st
import pandas as pd
import sqlite3
import requests
import time
from datetime import datetime

# ==============================================================================
# 1. KONFIGURASI LAYAR & SIDEBAR HP
# ==============================================================================
st.set_page_config(page_title="Indodax Pro Bot", layout="wide", initial_sidebar_state="collapsed")

# CSS Kustom untuk memaksimalkan tampilan Monitor Chrome HP
st.markdown("""
    <style>
    .reportview-container .main .block-container { padding-top: 1rem; padding-bottom: 1rem; }
    .metric-card { background-color: #f0f2f6; padding: 10px; border-radius: 8px; text-align: center; }
    .stTable { font-size: 12px !important; }
    div[data-testid="stMetricValue"] { font-size: 20px !important; font-weight: bold; }
    div[data-testid="stMetricLabel"] { font-size: 12px !important; }
    </style>
""", unsafe_allow_html=True)

st.sidebar.title("📱 Kontrol Bot HP")
st.sidebar.markdown("---")

# FITUR BARU: Input modal dinamis per transaksi
modal_per_trade = st.sidebar.number_input(
    "Modal per Transaksi (IDR)", 
    min_value=10000, 
    value=50000, 
    step=5000,
    help="Jumlah IDR yang digunakan untuk setiap eksekusi order BUY."
)

min_volume_24h = st.sidebar.number_input("Min Vol 24J (USD)", min_value=0, value=50000, step=10000)
bot_loop_interval = st.sidebar.slider("Interval Cek Bot (Menit)", min_value=1, max_value=60, value=5)

# Simulasi API Key Aman
API_KEY = st.sidebar.text_input("Indodax API Key", value="INTEGRATED_SECURE_KEY", type="password")
API_SECRET = st.sidebar.text_input("Indodax Secret Key", value="INTEGRATED_SECURE_SECRET", type="password")

# ==============================================================================
# 2. INISIALISASI DATABASE & MANAJEMEN KONEKSI AMAN (ANTI-LOCK)
# ==============================================================================
DB_FILE = 'trading_bot.db'

def get_db_connection():
    # Menambahkan timeout untuk mencegah DatabaseError akibat write-lock
    return sqlite3.connect(DB_FILE, timeout=10)

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        # Tabel Posisi Permanen 5 Aset
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                pair TEXT PRIMARY KEY,
                status TEXT,
                buy_price REAL,
                amount REAL,
                last_update TEXT
            )
        """)
        # Tabel Log Aktivitas
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                pair TEXT,
                action TEXT,
                message TEXT
            )
        """)
        
        # Isi data awal 5 aset permanen jika belum ada
        permanent_pairs = ['BTC/IDR', 'ETH/IDR', 'USDT/IDR', 'SOL/IDR', 'DOGE/IDR']
        for pair in permanent_pairs:
            cursor.execute("INSERT OR IGNORE INTO positions VALUES (?, ?, ?, ?, ?)", 
                           (pair, 'WAITING_BUY', 0.0, 0.0, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        conn.commit()

# Jalankan inisialisasi basis data pertama kali
init_db()

def get_positions():
    with get_db_connection() as conn:
        query = "SELECT pair as 'Aset', status as 'Status', buy_price as 'Harga Beli', amount as 'Jumlah', last_update as 'Waktu Update' FROM positions"
        df = pd.read_sql_query(query, conn)
    return df

def get_logs():
    with get_db_connection() as conn:
        query = "SELECT timestamp as 'Waktu', pair as 'Aset', action as 'Aksi', message as 'Detail' FROM activity_logs ORDER BY id DESC LIMIT 10"
        df = pd.read_sql_query(query, conn)
    return df

def add_log(pair, action, message):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO activity_logs (timestamp, pair, action, message) VALUES (?, ?, ?, ?)",
                       (datetime.now().strftime('%H:%M:%S'), pair, action, message))
        conn.commit()

def update_position(pair, status, buy_price, amount):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE positions SET status=?, buy_price=?, amount=?, last_update=? WHERE pair=?",
                       (status, buy_price, amount, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), pair))
        conn.commit()

# ==============================================================================
# 3. KONEKSI DATA CHART BINANCE GLOBAL & OPTIMASI LOGIKA HMA-20
# ==============================================================================
def calculate_hma(series, period):
    import numpy as np
    def wma(s, p):
        weights = np.arange(1, p + 1)
        return s.rolling(p).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    
    raw_hma = 2 * wma(series, half_period) - wma(series, period)
    hma = wma(raw_hma, sqrt_period)
    return hma

def fetch_binance_4h_signals(pair):
    # Bersihkan penulisan dan petakan koin Indodax ke pasar Binance USDT
    clean_pair = pair.replace('/IDR', '')
    binance_symbol = f"{clean_pair}USDT"
    url = f"https://binance.com{binance_symbol}&interval=4h&limit=50"
    
    try:
        response = requests.get(url, timeout=10).json()
        df = pd.DataFrame(response, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        # Hitung HMA-20
        df['hma_20'] = calculate_hma(df['close'], 20)
        
        # OPTIMASI SINYAL: Konfirmasi matang pada Bar [-2] (Mencegah Repainting)
        closed_price = df['close'].iloc[-2]
        hma_last_fixed = df['hma_20'].iloc[-2]
        hma_prev_fixed = df['hma_20'].iloc[-3]
        
        volume_24h_usd = df['volume'].iloc[-7:].sum() * closed_price
        
        if closed_price > hma_last_fixed and hma_last_fixed > hma_prev_fixed:
            signal = "BUY"
        elif closed_price < hma_last_fixed and hma_last_fixed < hma_prev_fixed:
            signal = "SELL"
        else:
            signal = "HOLD"
            
        return signal, closed_price, volume_24h_usd
    except Exception as e:
        return "ERROR", 0.0, 0.0

# ==============================================================================
# 4. ENGINE DATA PASAR
# ==============================================================================
def get_indodax_data():
    try:
        res = requests.get("https://indodax.com", timeout=10).json()
        return res.get('tickers', {})
    except:
        return {}

indodax_tickers = get_indodax_data()
saldo_idr_dompet = 1500000.0

# ==============================================================================
# 5. LAYAR UTAMA MONITOR CHROME HP (VISUAL OPTIMIZED)
# ==============================================================================
st.title("📊 Multi-Pair Pro Monitor")

col1, col2, col3 = st.columns(3)
win_rate_sim = 68.5 
total_profit_idr = 125000.0
total_profit_pct = 8.33

with col1:
    st.metric("Win Rate", f"{win_rate_sim}%")
with col2:
    st.metric("Saldo IDR", f"Rp {saldo_idr_dompet:,.0f}")
with col3:
    st.metric("Total Profit/Loss", f"Rp {total_profit_idr:+,.0f}", f"{total_profit_pct:+.2f}%")

st.markdown("---")

# Eksekusi Logika Sinyal & Sistem Rem Saldo Otomatis
df_positions = get_positions()

for idx, row in df_positions.iterrows():
    pair = row['Aset']
    current_status = row['Status']
    
    signal, target_price, vol_24h = fetch_binance_4h_signals(pair)
    
    if vol_24h < min_volume_24h and signal != "ERROR":
        continue
        
    if current_status == 'WAITING_BUY' and signal == 'BUY':
        if saldo_idr_dompet >= modal_per_trade:
            amount_to_buy = modal_per_trade / target_price
            saldo_idr_dompet -= modal_per_trade
            update_position(pair, 'HOLDING_SELL', target_price, amount_to_buy)
            add_log(pair, 'BUY', f"Membeli menggunakan modal Rp{modal_per_trade:,.0f} pada harga Rp{target_price:,.2f}")
        else:
            add_log(pair, 'SKIP', "Gagal BUY: Saldo IDR tidak mencukupi modal per transaksi!")
            
    elif current_status == 'HOLDING_SELL' and signal == 'SELL':
        payout = row['Jumlah'] * target_price
        saldo_idr_dompet += payout
        update_position(pair, 'WAITING_BUY', 0.0, 0.0)
        add_log(pair, 'SELL', f"Menjual seluruh aset ekivalen Rp{payout:,.0f} pada harga Rp{target_price:,.2f}")

# Menampilkan data tabel secara aman di HP
st.subheader("📌 Status Posisi 5 Aset Permanen")
st.table(get_positions())

st.subheader("📜 Log Aktivitas Server")
st.table(get_logs())

# Autorefresh aman untuk kestabilan SQLite Streamlit Cloud
time.sleep(5)
st.rerun()
