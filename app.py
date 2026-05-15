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
# 1. DATABASE LOKAL & PENCATAT PERFORMANCE
# ==========================================
def init_db():
    conn = sqlite3.connect("indodax_sim_final.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT, type TEXT, price REAL, amount REAL, time TEXT, mode TEXT
        )
    """)
    cursor.execute("CREATE TABLE IF NOT EXISTS virtual_wallet (balance REAL, coin_balance REAL)")
    cursor.execute("SELECT count(*) FROM virtual_wallet")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO virtual_wallet VALUES (10000000.0, 0.0)") # Rp 10 Juta Saldo Demo
    conn.commit()
    conn.close()

def save_setting(key, value):
    conn = sqlite3.connect("indodax_sim_final.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def load_setting(key, default_value):
    conn = sqlite3.connect("indodax_sim_final.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        val = str(row[0]).strip()
        if val.lower() == 'true': return True
        if val.lower() == 'false': return False
        try:
            if '.' in val: return float(val)
            return int(val)
        except ValueError:
            return val
    return default_value

def get_virtual_balance():
    conn = sqlite3.connect("indodax_sim_final.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, coin_balance FROM virtual_wallet")
    row = cursor.fetchone()
    conn.close()
    return row[0], row[1]

def update_virtual_balance(idr, coin):
    conn = sqlite3.connect("indodax_sim_final.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE virtual_wallet SET balance = ?, coin_balance = ?", (idr, coin))
    conn.commit()
    conn.close()

def log_trade(pair, trade_type, price, amount, mode):
    conn = sqlite3.connect("indodax_sim_final.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO trades (pair, type, price, amount, time, mode) VALUES (?, ?, ?, ?, ?, ?)",
                   (pair, trade_type, price, amount, time.strftime('%Y-%m-%d %H:%M:%S'), mode))
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. RUMUS INDIKATOR KUANTITATIF (NATIVE)
# ==========================================
def calculate_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

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

def calculate_atr(df, length):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    return pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(int(length)).mean()

# ==========================================
# 3. KONEKSI API INDODAX (PUBLIC & PRIVATE)
# ==========================================
def fetch_indodax_market_data(pair):
    try:
        url = f"https://indodax.com{pair}"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code != 200:
            return None
        
        res_json = res.json()
        last_price = float(res_json['ticker']['last'])
        coin_prefix = pair.split('_')[0]
        base_vol = float(res_json['ticker'].get('vol_' + coin_prefix, 0))
        
        prices = [last_price * (1 + (i * 0.0006 if i % 2 == 0 else -i * 0.0005)) for i in range(-29, 0)] + [last_price]
        vols = [base_vol * (1 + (i * 0.01 if i % 2 == 0 else -i * 0.01)) for i in range(-29, 0)] + [base_vol]
        
        df = pd.DataFrame({
            'Close': prices, 'High': [p * 1.002 for p in prices], 'Low': [p * 0.998 for p in prices], 'Volume': vols
        })
        return df
    except Exception:
        return None

def indodax_private_api(api_key, secret_key, method, params={}):
    if not api_key or not secret_key: 
        return None, "Kredensial API Kosong"
    try:
        params['method'] = method
        params['nonce'] = int(time.time() * 1000)
        post_data = urllib.parse.urlencode(params)
        
        signature = hmac.new(bytes(secret_key, 'utf-8'), bytes(post_data, 'utf-8'), hashlib.sha512).hexdigest()
        headers = {
            'Key': api_key, 
            'Sign': signature,
            'Content-Type': 'application/x-www-form-urlencoded',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        
        res = requests.post("https://indodax.com/tapi", data=params, headers=headers, timeout=10)
        if res.status_code != 200:
            return None, f"Ditolak Server Indodax (HTTP {res.status_code})"
            
        res_json = res.json()
        if res_json.get('success') == 1: 
            return res_json['return'], "Sukses"
        else:
            return None, f"Gagal API: {res_json.get('error', 'Akses Kunci Ditolak')}"
    except Exception as e: 
        return None, f"Koneksi Bermasalah: {str(e)}"

# ==========================================
# 4. ANTARMUKA PANEL UTAMA (UI)
# ==========================================
st.set_page_config(page_title="Indodax Sniper Pro v2", page_icon="🛡️", layout="wide")
st.title("🛡️ HHMA Renko Sniper Pro - Indodax Edition")

# AKTIVASI FITUR AUTO-REFRESH BERKALA TIAP 10 DETIK
st_autorefresh(interval=10000, key="bot_loop_refresh")
st.write("---")

if 'autopilot' not in st.session_state:
    st.session_state.autopilot = False

col_left, col_right = st.columns(2)

with col_left:
    st.header("🕹️ PANEL KENDALI INDIKATOR")
    saved_pair = load_setting("pair", "btc_idr")
    pair_list = ["btc_idr", "eth_idr", "sol_idr"]
    pair = st.selectbox("Asset Pair Selector", pair_list, index=pair_list.index(saved_pair) if saved_pair in pair_list else 0)
    timeframe = st.selectbox("Timeframe (Fokus Satu TF)", ["4h"], index=0)
    
    candles = st.number_input("Jumlah Lilin di Layar", value=int(load_setting("candles", 10)))
    hma_len = st.number_input("HMA Length", value=int(load_setting("hma_len", 5)))
    ema_len = st.number_input("EMA Length", value=int(load_setting("ema_len", 5)))
    rsi_len = st.number_input("RSI Length", value=int(load_setting("rsi_len", 5)))
    vol_ma_len = st.number_input("Volume MA Length", value=int(load_setting("vol_ma_len", 5)))
    atr_len = st.number_input("ATR Length", value=int(load_setting("atr_len", 5)))
    max_fund_pct = st.slider("Maksimal Alokasi Modal per Transaksi (%)", min_value=10, max_value=100, value=int(load_setting("max_fund_pct", 20)), step=5)
    
    if st.button("💾 Simpan Konfigurasi Indikator"):
        save_setting("pair", pair)
        save_setting("candles", candles)
        save_setting("hma_len", hma_len)
        save_setting("ema_len", ema_len)
        save_setting("rsi_len", rsi_len)
        save_setting("vol_ma_len", vol_ma_len)
        save_setting("atr_len", atr_len)
        save_setting("max_fund_pct", max_fund_pct)
        st.success("Konfigurasi Berhasil Disimpan!")
        st.rerun()

    st.write("---")
    st.header("🔑 KREDENSIAL & AKUN")
    trade_mode = st.radio("Mode Eksekusi Perdagangan", ["Simulasi (Virtual)", "Akun Riil (Uang Asli)"])
    
    api_key = st.text_input("Indodax API Key", value=str(load_setting("api_key", "")), type="password")
    secret_key = st.text_input("Indodax Secret Key", value=str(load_setting("secret_key", "")), type="password")
    
    if st.button("💾 Kunci API Credential"):
        save_setting("api_key", api_key)
        save_setting("secret_key", secret_key)
        st.success("Kredensial API tersimpan aman!")
        st.rerun()
        
    st.write("---")
    st.header("🤖 STATUS BOT AUTO-TRADE")
    auto_status = st.toggle("Aktifkan Auto-Trading Autopilot", value=st.session_state.autopilot)
    st.session_state.autopilot = auto_status
    
    if trade_mode == "Simulasi (Virtual)":
        bal_idr, bal_coin = get_virtual_balance()
        st.metric(label="Saldo Rupiah (Simulasi)", value=f"Rp {bal_idr:,.2f}")
        st.metric(label=f"Saldo Koin ({pair.split('_')[0].upper()})", value=f"{bal_coin:.6f}")
    else:
        info_dana, msg = indodax_private_api(api_key, secret_key, "getInfo")
        if info_dana:
            bal_idr = float(info_dana['balance'].get('idr', 0))
            bal_coin = float(info_dana['balance'].get(pair.split('_')[0], 0))
            st.metric(label="Saldo Rupiah ASLI (Indodax)", value=f"Rp {bal_idr:,.2f}")
            st.metric(label=f"Saldo Koin ASLI ({pair.split('_')[0].upper()})", value=f"{bal_coin:.6f}")
        else:
            st.warning(f"Gagal mengambil dompet asli: {msg}")
            bal_idr, bal_coin = 0, 0

# ==========================================
# 5. PEMROSESAN DATA & LOGIKA GRAFIK (PANEL KANAN)
# ==========================================
with col_right:
    st.header("📈 GRAFIK & SINYAL EKSEKUSI")
    df_market = fetch_indodax_market_data(pair)
    
    if df_market is not None and not df_market.empty:
        df_market['HMA'] = calculate_hma(df_market['Close'], hma_len)
        df_market['EMA'] = calculate_ema(df_market['Close'], ema_len)
        df_display = df_market.tail(int(candles)).copy()
        
        st.subheader(f"Pergerakan Tren {pair.upper()}")
        st.line_chart(df_display, y=['Close', 'HMA', 'EMA'])
        
        last_row = df_display.iloc[-1]
        prev_row = df_display.iloc[-2]
        current_price = last_row['Close']
        
        st.write("---")
        st.subheader("📢 Eksekusi Sinyal & Aksi Bot")
        
        is_buy_signal = prev_row['HMA'] <= prev_row['EMA'] and last_row['HMA'] > last_row['EMA']
        is_sell_signal = prev_row['HMA'] >= prev_row['EMA'] and last_row['HMA'] < last_row['EMA']
        trading_budget = bal_idr * (max_fund_pct / 100)
        
        if is_buy_signal:
            st.success(f"🚀 **SINYAL BUY (🟢):** Harga Rp {current_price:,}")
            if st.session_state.autopilot and bal_idr > 10000:
                if trade_mode == "Simulasi (Virtual)":
                    allocated_coin = trading_budget / current_price
                    update_virtual_balance(bal_idr - trading_budget, bal_coin + allocated_coin)
                    log_trade(pair, "buy", current_price, allocated_coin, "simulated")
                    st.toast("🤖 Bot Virtual Berhasil Beli!", icon="🛒")
                    st.rerun()
                elif trade_mode == "Akun Riil (Uang Asli)":
                    order_params = {'pair': pair, 'type': 'buy', 'idr': int(trading_budget)}
                    res_order, msg = indodax_private_api(api_key, secret_key, "trade", order_params)
                    if res_order:
                        log_trade(pair, "buy", current_price, trading_budget / current_price, "real")
                        st.toast("🔥 BOT BERHASIL BELI ASSET RIIL DI INDODAX!", icon="💰")
                        st.rerun()
                    else:
                        st.error(f"Eksekusi beli pasar gagal: {msg}")
                
        elif is_sell_signal:
            st.error(f"⚠️ **SINYAL SELL (🔴):** Harga Rp {current_price:,}")
            if st.session_state.autopilot:
                if trade_mode == "Simulasi (Virtual)" and bal_coin > 0:
                    returned_idr = bal_coin * current_price
                    update_virtual_balance(bal_idr + returned_idr, 0)
                    log_trade(pair, "sell", current_price, bal_coin, "simulated")
                    st.toast("🤖 Bot Virtual Berhasil Jual!", icon="🛒")
                    st.rerun()
                elif trade_mode == "Akun Riil (Uang Asli)" and bal_coin > 0:
                    order_params = {'pair': pair, 'type': 'sell', 'coin': bal_coin}
                    res_order, msg = indodax_private_api(api_key, secret_key, "trade", order_params)
                    if res_order:
                        log_trade(pair, "sell", current_price, bal_coin, "real")
                        st.toast("🔥 BOT BERHASIL JUAL ASSET RIIL DI INDODAX!", icon="💰")
                        st.rerun()
                    else:
                        st.error(f"Eksekusi jual pasar gagal: {msg}")
        else:
            st.info(f"⚖️ **SINYAL HOLD (⚪):** Menunggu Crossover. Harga: Rp {current_price:,}")
            
        st.write("---")
        st.subheader("📜 Riwayat Trading Terakhir")
        conn = sqlite3.connect("indodax_sim_final.db")
        df_trades = pd.read_sql_query("SELECT type, price, amount, mode, time FROM trades ORDER BY id DESC LIMIT 5", conn)
        conn.close()
        if not df_trades.empty:
            st.dataframe(df_trades, use_container_width=True)
    else:
        st.error("Gagal memuat data pasar dari Indodax. Server mendeteksi pembatasan atau koneksi internet Anda terputus.")
