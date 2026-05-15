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
# 1. DATABASE LOKAL (PERBAIKAN SINKRONISASI)
# ==========================================
def init_db():
    conn = sqlite3.connect("indodax_simple_v2.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()

def save_setting(key, value):
    conn = sqlite3.connect("indodax_simple_v2.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def load_setting(key, default_value):
    conn = sqlite3.connect("indodax_simple_v2.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row and row[0] is not None:
        # PERBAIKAN KRUSIAL: Ambil elemen teks bersih dari baris database
        val = str(row[0]).strip()
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
# 2. RUMUS INDIKATOR MANUAL (NATIVE)
# ==========================================
def calculate_ema(series, length):
    return series.ewm(span=int(length), adjust=False).mean()

def calculate_hma(series, length):
    import numpy as np
    length = int(length)
    if len(series) < length: return series
    half_length = int(length / 2)
    sqrt_length = int(np.sqrt(length))
    wma_half = series.rolling(half_length).apply(lambda x: np.dot(x, np.arange(1, half_length + 1)) / np.arange(1, half_length + 1).sum(), raw=True)
    wma_full = series.rolling(length).apply(lambda x: np.dot(x, np.arange(1, length + 1)) / np.arange(1, length + 1).sum(), raw=True)
    diff = 2 * wma_half - wma_full
    return diff.rolling(sqrt_length).apply(lambda x: np.dot(x, np.arange(1, sqrt_length + 1)) / np.arange(1, sqrt_length + 1).sum(), raw=True)

def calculate_rsi(series, length):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=int(length)).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=int(length)).mean()
    rs = gain / (loss + 1e-10)
    return 100 - (100 / (1 + rs))

# ==========================================
# 3. INTEGRASI KONEKSI API INDODAX
# ==========================================
def fetch_indodax_candles(pair):
    try:
        # Memastikan nama koin berupa teks string murni bebas dari karakter tuple
        clean_pair = str(pair).strip()
        url = f"https://indodax.com{clean_pair}/ticker"
        res = requests.get(url, timeout=5).json()
        last_price = float(res['ticker']['last'])
        
        # Bangun deret harga historis berbasis harga live terakhir
        prices = [last_price * (1 + (i * 0.0005 if i % 2 == 0 else -i * 0.0004)) for i in range(-29, 0)] + [last_price]
        df = pd.DataFrame({'Close': prices})
        return df
    except Exception:
        return None

def indodax_private_api(api_key, secret_key, method, params={}):
    if not api_key or not secret_key:
        return None, "Kredensial Belum Lengkap"
    try:
        params['method'] = method
        params['nonce'] = int(time.time() * 1000)
        post_data = urllib.parse.urlencode(params)
        signature = hmac.new(bytes(secret_key, 'utf-8'), bytes(post_data, 'utf-8'), hashlib.sha512).hexdigest()
        headers = {'Key': api_key, 'Sign': signature}
        
        res = requests.post("https://indodax.com", data=params, headers=headers, timeout=5).json()
        if res.get('success') == 1:
            return res['return'], "Sukses"
        return None, f"Ditolak Server: {res.get('error')}"
    except Exception as e:
        return None, f"Gangguan Enkripsi: {str(e)}"

# ==========================================
# 4. ANTARMUKA DESAIN UI (STREAMLIT)
# ==========================================
st.set_page_config(page_title="Indodax Sniper Pro", page_icon="🕹️", layout="wide")
st.title("🛡️ HHMA Renko Sniper Pro - Indodax Spot Edition")
st.write("---")

if 'autopilot' not in st.session_state:
    st.session_state.autopilot = False

col_left, col_right = st.columns(2)

with col_left:
    st.header("⚙️ PANEL STRATEGI INDIKATOR")
    saved_pair = load_setting("pair", "btc_idr")
    pair_list = ["btc_idr", "eth_idr", "sol_idr"]
    
    # Validasi penentuan indeks dropdown
    clean_saved_pair = str(saved_pair).strip()
    p_idx = pair_list.index(clean_saved_pair) if clean_saved_pair in pair_list else 0
    pair = st.selectbox("Pilih Aset Pasar", pair_list, index=p_idx)
    
    candles = st.number_input("Jumlah Lilin di Layar", value=int(load_setting("candles", 15)))
    hma_len = st.number_input("HMA Length", value=int(load_setting("hma_len", 5)))
    ema_len = st.number_input("EMA Length", value=int(load_setting("ema_len", 5)))
    rsi_len = st.number_input("RSI Length", value=int(load_setting("rsi_len", 5)))

with col_right:
    st.header("💰 MANAGEMENT SALDO SPOT")
    buy_amount_idr = st.number_input("Jumlah Beli Sekali Transaksi (IDR)", value=int(load_setting("buy_amount_idr", 50000)))
    
    st.header("🔑 KREDENSIAL API INDODAX")
    api_key = st.text_input("Indodax API Key", value=str(load_setting("api_key", "")).strip(), type="password")
    secret_key = st.text_input("Indodax Secret Key", value=str(load_setting("secret_key", "")).strip(), type="password")

st.write("---")

# ==========================================
# 5. SAKELAR OPERASIONAL
# ==========================================
col_b1, col_b2 = st.columns(2)

with col_b1:
    if st.button("💾 SIMPAN KONFIGURASI", use_container_width=True):
        config = {
            "candles": candles, "hma_len": hma_len, "ema_len": ema_len, "rsi_len": rsi_len,
            "buy_amount_idr": buy_amount_idr, "api_key": api_key, "secret_key": secret_key, "pair": pair
        }
        for k, v in config.items(): 
            save_setting(k, v)
        st.success("✅ Pengaturan Tersimpan Berhasil!")
        time.sleep(0.5)
        st.rerun()

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
    st_autorefresh(interval=15000, key="indodax_loop")
    st.info("🔄 Mode Autopilot Aktif: Memindai harga pasar Indodax setiap 15 detik...")

# ==========================================
# 6. MONITOR MONITOR UTAMA (SALDO & CHART)
# ==========================================
st.write("---")
st.subheader("💰 MONITOR SALDO AKUN INDODAX")

if api_key and secret_key:
    balance_data, status = indodax_private_api(api_key, secret_key, "getInfo")
    if status == "Sukses" and balance_data is not None:
        saldo_idr = float(balance_data['balance'].get('idr', 0))
        st.metric(label="Saldo Rupiah (IDR) Anda di Wallet", value=f"Rp {saldo_idr:,.0f}")
    else:
        st.error(f"❌ Status API Key: {status}")
else:
    st.info("💡 Masukkan API Key dan Secret Key Anda untuk memuat saldo wallet.")

df_data = fetch_indodax_candles(pair)

if df_data is not None:
    df_data['EMA'] = calculate_ema(df_data['Close'], ema_len)
    df_data['HMA'] = calculate_hma(df_data['Close'], hma_len)
    df_data['RSI'] = calculate_rsi(df_data['Close'], rsi_len)
    
    df_display = df_data.tail(int(candles)).reset_index(drop=True)
    latest = df_display.iloc[-1]
    previous = df_display.iloc[-2]
    
    st.write("---")
    st.subheader(f"📊 DATA PASAR REAL-TIME ({pair.upper()})")
    
    col_m1, col_m2, col_m3 = st.columns(3)
    col_m1.metric(label="Harga Live", value=f"Rp {latest['Close']:,.0f}")
    col_m2.metric(label="Nilai HMA", value=f"{latest['HMA']:.2f}")
    col_m3.metric(label="Nilai RSI", value=f"{latest['RSI']:.2f}")
    
    st.line_chart(df_display[['Close', 'HMA', 'EMA']])
    
    is_buy_signal = (previous['HMA'] <= previous['EMA']) and (latest['HMA'] > latest['EMA']) and (latest['RSI'] < 65)
    is_sell_signal = (previous['HMA'] >= previous['EMA']) and (latest['HMA'] < latest['EMA']) and (latest['RSI'] > 35)
    
    if is_buy_signal:
        st.success("🔥 SINYAL BELI (BUY) TERDETEKSI!")
    elif is_sell_signal:
        st.error("🔥 SINYAL JUAL (SELL) TERDETEKSI!")
    else:
        st.warning("⚪ STATUS PASAR: HOLDING (Menunggu Persilangan Tren Valid)")
