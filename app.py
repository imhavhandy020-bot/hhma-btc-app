import sqlite3
import time
import hmac
import hashlib
import urllib.parse
import pandas as pd
import streamlit as st
import requests
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. DATABASE LOKAL (ANTI-LOST CONFIG)
# ==========================================
def init_db():
    conn = sqlite3.connect("indodax_bot.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()

def save_setting(key, value):
    conn = sqlite3.connect("indodax_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def load_setting(key, default_value):
    conn = sqlite3.connect("indodax_bot.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        val = row[0]
        if val.lower() == 'true': return True
        if val.lower() == 'false': return False
        try:
            if '.' in val: return float(val)
            return int(val)
        except ValueError:
            return val
    return default_value

init_db()

# ==========================================
# 2. KALKULASI INDIKATOR NATIVE PANDAS
# ==========================================
def calculate_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def calculate_hma(series, length):
    import numpy as np
    half_length = int(length / 2)
    sqrt_length = int(np.sqrt(length))
    wma_half = series.rolling(half_length).apply(lambda x: np.dot(x, np.arange(1, half_length + 1)) / np.arange(1, half_length + 1).sum(), raw=True)
    wma_full = series.rolling(length).apply(lambda x: np.dot(x, np.arange(1, length + 1)) / np.arange(1, length + 1).sum(), raw=True)
    diff = 2 * wma_half - wma_full
    hma = diff.rolling(sqrt_length).apply(lambda x: np.dot(x, np.arange(1, sqrt_length + 1)) / np.arange(1, sqrt_length + 1).sum(), raw=True)
    return hma

def calculate_rsi(series, length):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=length).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=length).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

# ==========================================
# 3. INTEGRASI API INDODAX SPOT
# ==========================================
def fetch_indodax_candles(pair, timeframe):
    # Mapping timeframe ke format Indodax (misal: 4h -> 240)
    tf_map = {"1m": "1", "5m": "5", "15m": "15", "1h": "60", "4h": "240", "1d": "1D"}
    tf_indodax = tf_map.get(timeframe, "240")
    
    try:
        url = f"https://indodax.com{pair.upper()}&resolution={tf_indodax}&from={int(time.time())-86400*30}&to={int(time.time())}"
        res = requests.get(url, timeout=10).json()
        
        df = pd.DataFrame({
            'Open': res['o'], 'High': res['h'], 'Low': res['l'], 'Close': res['c'], 'Volume': res['v']
        })
        return df
    except Exception:
        return None

def indodax_private_api(api_key, secret_key, method, params={}):
    if not api_key or not secret_key:
        return None, "API Key kosong"
    try:
        params['method'] = method
        params['nonce'] = int(time.time() * 1000)
        post_data = urllib.parse.urlencode(params)
        
        signature = hmac.new(bytes(secret_key, 'utf-8'), bytes(post_data, 'utf-8'), hashlib.sha512).hexdigest()
        headers = {'Key': api_key, 'Sign': signature}
        
        res = requests.post("https://indodax.com", data=params, headers=headers, timeout=10).json()
        if res.get('success') == 1:
            return res['return'], "Sukses"
        else:
            return None, res.get('error', 'Terjadi kesalahan API')
    except Exception as e:
        return None, str(e)

# ==========================================
# 4. ANTARMUKA DESAIN UI (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Indodax Sniper Spot Bot", page_icon="🕹️", layout="wide")
st.title("🕹️ Indodax Sniper Pro - Spot Trading Bot")
st.write("---")

if 'autopilot' not in st.session_state:
    st.session_state.autopilot = False

col_left, col_right = st.columns(2)

with col_left:
    st.header("⚙️ PANEL STRATEGI INDIKATOR")
    # Pilihan koin utama di Indodax (Rupiah Market)
    pair = st.selectbox("Pilih Aset Pasar", ["btc_idr", "eth_idr", "sol_idr"], index=0)
    timeframe = st.selectbox("Timeframe", ["15m", "1h", "4h", "1d"], index=2)
    
    candles = st.number_input("Jumlah Lilin di Layar", value=load_setting("candles", 15))
    hma_len = st.number_input("HMA Length", value=load_setting("hma_len", 5))
    ema_len = st.number_input("EMA Length", value=load_setting("ema_len", 5))
    rsi_len = st.number_input("RSI Length", value=load_setting("rsi_len", 5))

with col_right:
    st.header("💰 MANAGEMENT SALDO SPOT")
    buy_amount_idr = st.number_input("Jumlah Beli Sekali Transaksi (IDR)", value=load_setting("buy_amount_idr", 50000))
    
    st.header("🔑 KREDENSIAL API INDODAX")
    api_key = st.text_input("Indodax API Key", value=load_setting("api_key", ""), type="password")
    secret_key = st.text_input("Indodax Secret Key", value=load_setting("secret_key", ""), type="password")

st.write("---")

# ==========================================
# 5. SAKELAR KONTROL AUTOPILOT
# ==========================================
col_b1, col_b2 = st.columns(2)

with col_b1:
    if st.button("💾 SIMPAN KONFIGURASI", use_container_width=True):
        config = {
            "candles": candles, "hma_len": hma_len, "ema_len": ema_len, "rsi_len": rsi_len,
            "buy_amount_idr": buy_amount_idr, "api_key": api_key, "secret_key": secret_key
        }
        for k, v in config.items(): save_setting(k, v)
        st.success("Pengaturan Spot Indodax berhasil disimpan!")

with col_b2:
    if st.session_state.autopilot:
        if st.button("🔴 MATIKAN AUTOPILOT", type="secondary", use_container_width=True):
            st.session_state.autopilot = False
            st.rerun()
    else:
        if st.button("🟢 AKTIFKAN AUTOPILOT", type="primary", use_container_width=True):
            st.session_state.autopilot = True
            st.rerun()

if st.session_state.autopilot:
    st_autorefresh(interval=20000, key="indodax_loop") # Refresh setiap 20 detik
    st.info("🔄 Autopilot Aktif: Memindai harga pasar Indodax secara real-time...")

# ==========================================
# 6. RUNNING PROSES & FILTER KEPUTUSAN
# ==========================================
# Tampilkan Saldo Akun Real-time jika API diisi
if api_key and secret_key:
    balance_data, status = indodax_private_api(api_key, secret_key, "getInfo")
    if status == "Sukses":
        saldo_idr = float(balance_data['balance']['idr'])
        st.metric(label="Saldo Rupiah (IDR) Anda di Indodax", value=f"Rp {saldo_idr:,.0f}")

df_data = fetch_indodax_candles(pair, timeframe)

if df_data is not None:
    # Hitung Indikator
    df_data['EMA'] = calculate_ema(df_data['Close'], int(ema_len))
    df_data['HMA'] = calculate_hma(df_data['Close'], int(hma_len))
    df_data['RSI'] = calculate_rsi(df_data['Close'], int(rsi_len))
    
    df_display = df_data.tail(int(candles)).reset_index(drop=True)
    latest = df_display.iloc[-1]
    previous = df_display.iloc[-2]
    
    # Tampilkan Data Ringkas
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric(label=f"Harga Terakhir {pair.upper()}", value=f"Rp {latest['Close']:,.0f}")
    col_m2.metric(label="Nilai HMA", value=f"{latest['HMA']:.2f}")
    col_m3.metric(label="Nilai RSI", value=f"{latest['RSI']:.2f}")
    
    st.line_chart(df_display[['Close', 'HMA', 'EMA']])
    
    # Logika Sniper Cross Over
    is_buy_signal = (previous['HMA'] <= previous['EMA']) and (latest['HMA'] > latest['EMA']) and (latest['RSI'] < 65)
    is_sell_signal = (previous['HMA'] >= previous['EMA']) and (latest['HMA'] < latest['EMA']) and (latest['RSI'] > 35)
    
    if is_buy_signal:
        st.success("🔥 SINYAL BELI (BUY) TERDETEKSI!")
        if st.session_state.autopilot:
            # Eksekusi Beli Instan menggunakan Rupiah (IDR)
            order_params = {'pair': pair, 'type': 'buy', 'idr': int(buy_amount_idr)}
            res, msg = indodax_private_api(api_key, secret_key, "trade", order_params)
            st.info(f"Eksekusi Order Beli: {msg}")
            
    elif is_sell_signal:
        st.error("🔥 SINYAL JUAL (SELL) TERDETEKSI!")
        if st.session_state.autopilot:
            # Pada mode spot, jual memerlukan info sisa saldo koin Anda
            coin_name = pair.split('_')[0]
            if balance_data:
                sisa_koin = balance_data['balance'].get(coin_name, 0)
                if float(sisa_koin) > 0:
                    order_params = {'pair': pair, 'type': 'sell', coin_name: sisa_koin}
                    res, msg = indodax_private_api(api_key, secret_key, "trade", order_params)
                    st.info(f"Eksekusi Order Jual: {msg}")
                else:
                    st.warning("Sinyal Jual muncul tapi saldo koin Anda 0.")
    else:
        st.warning("⚪ STATUS PASAR: HOLDING (Menunggu Persilangan Tren Valid)")
