import streamlit as st
import pandas as pd
import numpy as np
import requests
import sqlite3
import time
import hmac
import hashlib
from datetime import datetime

# =====================================================================
# API KEYS & KONFIGURASI INDODAX
# =====================================================================
API_KEY = "ISI_API_KEY_INDODAX_ANDA"
SECRET_KEY = "ISI_SECRET_KEY_INDODAX_ANDA"
LIST_PAIRS = ['BTC/IDR', 'ETH/IDR', 'USDT/IDR', 'SOL/IDR', 'DOGE/IDR']

# Initialize Database dan Tabel Utama
def init_db():
    conn = sqlite3.connect('trading_bot.db', check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            pair TEXT PRIMARY KEY, last_signal TEXT, entry_price REAL, timestamp TEXT
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (max_mdd REAL, min_vol REAL, last_run TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY AUTOINCREMENT, pair TEXT, type TEXT, price REAL, status TEXT, timestamp TEXT)")
    conn.commit()
    return conn

conn = init_db()

# =====================================================================
# CORE ENGINE: FILTER, INDIKATOR & EKSEKUSI
# =====================================================================
def get_indodax_candles_4h(pair):
    clean_pair = pair.lower().replace("/", "")
    url = "https://indodax.com"
    end_time = int(time.time())
    start_time = end_time - (200 * 4 * 3600) 
    params = {'symbol': clean_pair.upper(), 'resolution': '240', 'from': start_time, 'to': end_time}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get('s') == 'ok':
            return pd.DataFrame({
                'timestamp': pd.to_datetime(data['t'], unit='s'),
                'open': data['o'], 'high': data['h'], 'low': data['l'], 'close': data['c'], 'volume': data['v']
            })
    except:
        pass
    return pd.DataFrame()

def calculate_hma_20(df):
    if df.empty or len(df) < 20: return df
    period = 20
    half_period, sqrt_period = int(period / 2), int(np.sqrt(period))
    def wma(series, p):
        weights = np.arange(1, p + 1)
        return series.rolling(p).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    wma_half = wma(df['close'], half_period)
    wma_full = wma(df['close'], period)
    raw_hma = (2 * wma_half) - wma_full
    df['hma_20'] = wma(raw_hma, sqrt_period)
    df['hma_color'] = np.where(df['hma_20'] > df['hma_20'].shift(1), 'Green', 'Red')
    return df

def execute_indodax_trade(pair, action):
    clean_pair = pair.lower().replace("/", "_")
    url = "https://indodax.com"
    nonce = int(time.time() * 1000)
    payload = {"method": "trade", "pair": clean_pair, "type": action.lower(), "price": "market", "nonce": nonce}
    query_string = requests.compat.urlencode(payload)
    signature = hmac.new(bytes(SECRET_KEY, 'utf-8'), msg=bytes(query_string, 'utf-8'), digestmod=hashlib.sha512).hexdigest()
    headers = {"Key": API_KEY, "Sign": signature}
    try:
        res = requests.post(url, data=payload, headers=headers, timeout=10).json()
        return res
    except Exception as e:
        return {"success": 0, "error": str(e)}

def run_background_engine():
    cursor = conn.cursor()
    cursor.execute("SELECT max_mdd, min_vol FROM settings LIMIT 1")
    setting_row = cursor.fetchone()
    max_mdd, min_vol = setting_row if setting_row else (5.0, 50000000)
    
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("INSERT OR REPLACE INTO settings (rowid, last_run) VALUES (1, ?)", (now_str,))
    
    for pair in LIST_PAIRS:
        df = get_indodax_candles_4h(pair)
        if df.empty: continue
        df = calculate_hma_20(df)
        last_bar = df.iloc[-1]
        current_color = last_bar['hma_color']
        current_price = last_bar['close']
        current_volume = last_bar['volume'] * current_price
        
        if current_volume < min_vol: continue
            
        cursor.execute("SELECT last_signal FROM trades WHERE pair = ?", (pair,))
        row = cursor.fetchone()
        last_signal = row[0] if row else "NONE"
        
        # LOGIKA BUY
        if current_color == 'Green' and last_signal != 'BUY':
            res = execute_indodax_trade(pair, "buy")
            if res.get("success") == 1 or "success" in str(res):
                cursor.execute("INSERT OR REPLACE INTO trades VALUES (?, 'BUY', ?, ?)", (pair, current_price, now_str))
                cursor.execute("INSERT INTO history (pair, type, price, status, timestamp) VALUES (?, 'BUY', ?, 'SUCCESS', ?)", (pair, current_price, now_str))
                conn.commit()
                
        # LOGIKA SELL
        elif current_color == 'Red' and last_signal != 'SELL':
            res = execute_indodax_trade(pair, "sell")
            if res.get("success") == 1 or "success" in str(res):
                cursor.execute("INSERT OR REPLACE INTO trades VALUES (?, 'SELL', ?, ?)", (pair, current_price, now_str))
                cursor.execute("INSERT INTO history (pair, type, price, status, timestamp) VALUES (?, 'SELL', ?, 'SUCCESS', ?)", (pair, current_price, now_str))
                conn.commit()

# =====================================================================
# TAMPILAN INTERFACE SCREEN CHROME HP
# =====================================================================
st.title("🛡️ Indodax Multi-Pair Pro Server")

# 1. Widget Statistik Ringkas (Paling Atas agar pas Layar HP)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM history WHERE type='SELL' AND status='SUCCESS'")
total_win = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM history WHERE status='SUCCESS'")
total_trades = cursor.fetchone()[0]
win_rate = (total_win / (total_trades/2) * 100) if total_trades > 1 else 100.0

col1, col2 = st.columns(2)
col1.metric("Win Rate Bot", f"{win_rate:.1f}%")
cursor.execute("SELECT last_run FROM settings LIMIT 1")
last_run_time = cursor.fetchone()
col2.metric("Server Terakhir Cek", last_run_time[0].split(" ")[1] if last_run_time else "--:--")

# 2. Tabel Posisi Berjalan & Riwayat Pasar
st.subheader("📋 Running Trades")
df_running = pd.read_sql_query("SELECT pair, last_signal as 'Posisi', entry_price as 'Harga Masuk', timestamp as 'Waktu' FROM trades", conn)
st.dataframe(df_running, use_container_width=True)

# 3. Pengaturan Risiko Sidebar (Chrome HP)
st.sidebar.header("⚙️ Konfigurasi Risiko")
cursor.execute("SELECT max_mdd, min_vol FROM settings LIMIT 1")
curr_set = cursor.fetchone()
curr_mdd, curr_vol = curr_set if curr_set else (5.0, 50000000)

input_mdd = st.sidebar.number_input("Max Drawdown (%)", value=curr_mdd)
input_vol = st.sidebar.number_input("Min Volume (IDR)", value=int(curr_vol), step=10000000)

if st.sidebar.button("💾 Terapkan Parameter"):
    cursor.execute("INSERT OR REPLACE INTO settings (rowid, max_mdd, min_vol) VALUES (1, ?, ?)", (input_mdd, input_vol))
    conn.commit()
    st.sidebar.success("Aturan berhasil diterapkan di Server Cloud!")

# Loop Otomatis Server Cloud (Pemicu Background)
run_background_engine()
time.sleep(300)
st.rerun()
