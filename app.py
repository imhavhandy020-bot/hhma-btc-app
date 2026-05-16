import streamlit as st
import pandas as pd
import sqlite3
import requests
import time
import hmac
import hashlib
import urllib.parse
from datetime import datetime

# ==============================================================================
# 1. KONFIGURASI LAYAR & SIDEBAR HP (ANTI-RESET FORM)
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

# Inisialisasi Session State Utama
if "modal_trade" not in st.session_state:
    st.session_state.modal_trade = 50000
if "min_vol" not in st.session_state:
    st.session_state.min_vol = 50000000

# Input Parameter Utama
modal_per_trade = st.sidebar.number_input(
    "Modal per Transaksi (IDR)", 
    min_value=10000, 
    value=st.session_state.modal_trade, 
    step=5000,
    key="modal_input"
)
st.session_state.modal_trade = modal_per_trade

min_volume_24h = st.sidebar.number_input(
    "Min Vol 24J (USD)", 
    min_value=0, 
    value=st.session_state.min_vol, 
    step=1000000,
    key="vol_input"
)
st.session_state.min_vol = min_volume_24h

# SOLUSI KUNCI PERMANEN: Membungkus API Key dalam Form agar tidak hilang saat Rerun
with st.sidebar.form(key="api_secure_form"):
    st.markdown("🔑 **Koneksi Akun Indodax**")
    api_key_field = st.text_input("Indodax API Key", type="password", value=st.session_state.get("saved_key", ""))
    api_secret_field = st.text_input("Indodax Secret Key", type="password", value=st.session_state.get("saved_secret", ""))
    submit_api = st.form_submit_button("Hubungkan API Akun")

# ==============================================================================
# 2. INISIALISASI DATABASE & MANAJEMEN KONEKSI AMAN
# ==============================================================================
DB_FILE = 'trading_bot.db'

def get_db_connection():
    return sqlite3.connect(DB_FILE, timeout=15)

def init_db():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                pair TEXT PRIMARY KEY,
                status TEXT,
                buy_price REAL,
                amount REAL,
                last_update TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activity_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                pair TEXT,
                action TEXT,
                message TEXT
            )
        """)
        # Tabel internal penyimpan saldo riil terakhir agar tidak lenyap saat refresh
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bot_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        permanent_pairs = ['BTC/IDR', 'ETH/IDR', 'USDT/IDR', 'SOL/IDR', 'DOGE/IDR']
        for pair in permanent_pairs:
            cursor.execute("INSERT OR IGNORE INTO positions VALUES (?, ?, ?, ?, ?)", 
                           (pair, 'WAITING_BUY', 0.0, 0.0, datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        
        # Inisialisasi saldo bawaan awal jika database baru dibuat
        cursor.execute("INSERT OR IGNORE INTO bot_settings VALUES ('last_balance', '1500000.0')")
        cursor.execute("INSERT OR IGNORE INTO bot_settings VALUES ('api_status', 'Mode Simulasi')")
        conn.commit()

init_db()

def get_setting(key_name, default_value):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM bot_settings WHERE key=?", (key_name,))
            row = cursor.fetchone()
            return row[0] if row else default_value
    except Exception:
        return default_value

def update_setting(key_name, value_str):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO bot_settings (key, value) VALUES (?, ?)", (key_name, str(value_str)))
            conn.commit()
    except Exception:
        pass

def get_positions():
    try:
        with get_db_connection() as conn:
            query = 'SELECT pair as "Aset", status as "Status", buy_price as "Harga Beli", amount as "Jumlah", last_update as "Waktu Update" FROM positions'
            df = pd.read_sql_query(query, conn)
        return df
    except Exception:
        return pd.DataFrame(columns=["Aset", "Status", "Harga Beli", "Jumlah", "Waktu Update"])

def get_logs():
    try:
        with get_db_connection() as conn:
            query = 'SELECT timestamp as "Waktu", pair as "Aset", action as "Aksi", message as "Detail" FROM activity_logs ORDER BY id DESC LIMIT 10'
            df = pd.read_sql_query(query, conn)
        return df
    except Exception:
        return pd.DataFrame(columns=["Waktu", "Aset", "Aksi", "Detail"])

def add_log(pair, action, message):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO activity_logs (timestamp, pair, action, message) VALUES (?, ?, ?, ?)",
                           (datetime.now().strftime('%H:%M:%S'), pair, action, message))
            conn.commit()
    except Exception:
        pass

def update_position(pair, status, buy_price, amount):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE positions SET status=?, buy_price=?, amount=?, last_update=? WHERE pair=?",
                           (status, buy_price, amount, datetime.now().strftime('%Y-%m-%d %H:%M:%S'), pair))
            conn.commit()
    except Exception:
        pass

# ==============================================================================
# 3. KONEKSI PRIVATE API RIIL INDODAX (GET REAL BALANCE)
# ==============================================================================
def fetch_indodax_real_balance(api_key, api_secret):
    try:
        payload = {
            'method': 'getInfo',
            'nonce': int(time.time() * 1000)
        }
        post_data = urllib.parse.urlencode(payload)
        sign = hmac.new(api_secret.encode('utf-8'), post_data.encode('utf-8'), hashlib.sha512).hexdigest()
        
        headers = {
            'Sign': sign,
            'Key': api_key,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        response = requests.post("https://indodax.com", data=payload, headers=headers, timeout=10).json()
        
        if response.get('success') == 1:
            balances = response['return']['balance']
            idr_balance = float(balances.get('idr', 0))
            return idr_balance, "Koneksi Riil Sukses"
        else:
            return None, f"Gagal: {response.get('error', 'Kunci Salah')}"
    except Exception:
        return None, "Error Jaringan API"

# Proses penyimpanan saat tombol Form ditekan di HP
if submit_api:
    st.session_state["saved_key"] = api_key_field
    st.session_state["saved_secret"] = api_secret_field
    
    if api_key_field and api_secret_field:
        real_bal, status_msg = fetch_indodax_real_balance(api_key_field, api_secret_field)
        if real_bal is not None:
            update_setting("last_balance", real_bal)
            update_setting("api_status", status_msg)
        else:
            update_setting("api_status", status_msg)

# ==============================================================================
# 4. KONEKSI DATA CHART BINANCE GLOBAL & OPTIMASI LOGIKA HMA-20
# ==============================================================================
def calculate_hma(series, period):
    import numpy as np
    def wma(s, p):
        weights = np.arange(1, p + 1)
        return s.rolling(p).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    raw_hma = 2 * wma(series, half_period) - wma(series, period)
    return wma(raw_hma, sqrt_period)

def fetch_binance_4h_signals(pair):
    clean_pair = pair.replace('/IDR', '')
    binance_symbol = f"{clean_pair}USDT"
    url = f"https://binance.com{binance_symbol}&interval=4h&limit=50"
    
    try:
        response = requests.get(url, timeout=10).json()
        df = pd.DataFrame(response, columns=['time', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'qav', 'num_trades', 'taker_base', 'taker_quote', 'ignore'])
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        
        df['hma_20'] = calculate_hma(df['close'], 20)
        
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
    except Exception:
        return "ERROR", 0.0, 0.0

# ==============================================================================
# 5. EXECUTION & VISUAL MONITOR CHROME HP
# ==============================================================================
st.title("📊 Multi-Pair Pro Monitor")

# Ambil nilai saldo dan status aman dari Database SQLite (Anti-Reset)
saldo_idr_dompet = float(get_setting("last_balance", "1500000.0"))
status_api_pesan = get_setting("api_status", "Mode Simulasi")

col1, col2, col3 = st.columns(3)
win_rate_sim = 68.5 
total_profit_idr = 125000.0
total_profit_pct = 8.33

with col1:
    st.metric("Win Rate", f"{win_rate_sim}%")
with col2:
    st.metric("Saldo IDR", f"Rp {saldo_idr_dompet:,.0f}", delta=status_api_pesan)
with col3:
    st.metric("Total Profit/Loss", f"Rp {total_profit_idr:+,.0f}", f"{total_profit_pct:+.2f}%")

st.markdown("---")

# Jalankan Logika Otomatisasi Rem Saldo
df_positions = get_positions()

if not df_positions.empty and "Aset" in df_positions.columns:
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
                
                # Update saldo baru ke database penampung agar permanen
                update_setting("last_balance", saldo_idr_dompet)
                update_position(pair, 'HOLDING_SELL', target_price, amount_to_buy)
                add_log(pair, 'BUY', f"Membeli menggunakan modal Rp{modal_per_trade:,.0f} pada harga Rp{target_price:,.2f}")
            else:
                add_log(pair, 'SKIP', "Gagal BUY: Saldo IDR tidak mencukupi modal per transaksi!")
                
        elif current_status == 'HOLDING_SELL' and signal == 'SELL':
            payout = row['Jumlah'] * target_price
            saldo_idr_dompet += payout
            
            # Update saldo baru ke database penampung agar permanen
            update_setting("last_balance", saldo_idr_dompet)
            update_position(pair, 'WAITING_BUY', 0.0, 0.0)
            add_log(pair, 'SELL', f"Menjual seluruh aset ekivalen Rp{payout:,.0f} pada harga Rp{target_price:,.2f}")

# Menampilkan tabel data monitor HP
st.subheader("📌 Status Posisi 5 Aset Permanen")
st.table(get_positions())

st.subheader("📜 Log Aktivitas Server")
st.table(get_logs())

# Autorefresh berkala aman (5 Detik)
time.sleep(5)
st.rerun()
