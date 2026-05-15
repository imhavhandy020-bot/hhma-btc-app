import sqlite3
import time
import hmac
import hashlib
import urllib.parse
import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh
import requests

# ==========================================
# 1. DATABASE LOKAL & PENCATAT PERFORMACE
# ==========================================
def init_db():
    conn = sqlite3.connect("indodax_pro_bot.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pair TEXT, type TEXT, price REAL, amount REAL, time TEXT, status TEXT
        )
    """)
    conn.commit()
    conn.close()

def save_setting(key, value):
    conn = sqlite3.connect("indodax_pro_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def load_setting(key, default_value):
    conn = sqlite3.connect("indodax_pro_bot.db")
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

def log_trade(pair, trade_type, price, amount, status="PROCESSED"):
    conn = sqlite3.connect("indodax_pro_bot.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO trades (pair, type, price, amount, time, status) VALUES (?, ?, ?, ?, ?, ?)",
                   (pair, trade_type, price, amount, time.strftime('%Y-%m-%d %H:%M:%S'), status))
    conn.commit()
    conn.close()

def calculate_performance_metrics():
    conn = sqlite3.connect("indodax_pro_bot.db")
    df = pd.read_sql_query("SELECT * FROM trades", conn)
    conn.close()
    
    if df.empty or len(df[df['type'] == 'sell']) == 0:
        return 0, 0, 0
    
    buys = df[df['type'] == 'buy'].reset_index(drop=True)
    sells = df[df['type'] == 'sell'].reset_index(drop=True)
    
    wins, losses, total_profit, total_loss = 0, 0, 0, 0
    min_len = min(len(buys), len(sells))
    
    for i in range(min_len):
        profit_loss = (sells.loc[i, 'price'] - buys.loc[i, 'price']) * buys.loc[i, 'amount']
        if profit_loss > 0:
            wins += 1
            total_profit += profit_loss
        else:
            losses += 1
            total_loss += abs(profit_loss)
            
    total_trades = wins + losses
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    profit_factor = total_profit / total_loss if total_loss > 0 else total_profit
    
    return round(win_rate, 2), round(profit_factor, 2), len(df)

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
# 3. KONEKSI API INDODAX
# ==========================================
def fetch_indodax_market_data(pair):
    try:
        url = f"https://indodax.com{pair}/ticker"
        res = requests.get(url, timeout=5).json()
        last_price = float(res['ticker']['last'])
        base_vol = float(res['ticker']['vol_' + pair.split('_')[0]])
        
        # Membuat deret data historis buatan berbasis real-time ticker
        prices = [last_price * (1 + (i * 0.0006 if i % 2 == 0 else -i * 0.0005)) for i in range(-29, 0)] + [last_price]
        vols = [base_vol * (1 + (i * 0.01 if i % 2 == 0 else -i * 0.01)) for i in range(-29, 0)] + [base_vol]
        
        df = pd.DataFrame({
            'Close': prices, 'High': [p * 1.002 for p in prices], 'Low': [p * 0.998 for p in prices], 'Volume': vols
        })
        return df
    except Exception:
        return None

def indodax_private_api(api_key, secret_key, method, params={}):
    if not api_key or not secret_key: return None, "Kredensial Belum Lengkap"
    try:
        params['method'] = method
        params['nonce'] = int(time.time() * 1000)
        post_data = urllib.parse.urlencode(params)
        signature = hmac.new(bytes(secret_key, 'utf-8'), bytes(post_data, 'utf-8'), hashlib.sha512).hexdigest()
        headers = {'Key': api_key, 'Sign': signature}
        res = requests.post("https://indodax.com", data=params, headers=headers, timeout=5).json()
        if res.get('success') == 1: return res['return'], "Sukses"
        return None, res.get('error', 'API Teritolak')
    except Exception: return None, "Koneksi Bermasalah"

# ==========================================
# 4. ANTARMUKA PANEL UTAMA (UI)
# ==========================================
st.set_page_config(page_title="Indodax Sniper Pro v2", page_icon="🛡️", layout="wide")
st.title("🛡️ HHMA Renko Sniper Pro - Indodax Spot Edition")
st.write("---")

if 'autopilot' not in st.session_state: st.session_state.autopilot = False

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
    sl_atr_mult = st.number_input("Stop Loss ATR Mult", value=float(load_setting("sl_atr_mult", 2.50)), step=0.1)

with col_right:
    st.header("🔥 PENGATURAN KEUANGAN AGRESIF")
    buy_amount_idr = st.number_input("Initial Purchase ($ / IDR)", value=int(load_setting("buy_amount_idr", 50000)))
    trading_fee = st.number_input("Trading Fee (%)", value=float(load_setting("trading_fee", 0.30)))
    
    st.header("🟡 INTEGRASI API INDODAX")
    api_key = st.text_input("Indodax API Key", value=str(load_setting("api_key", "")), type="password")
    secret_key = st.text_input("Indodax Secret Key", value=str(load_setting("secret_key", "")), type="password")
    
    st.header("📱 NOTIFIKASI TELEGRAM")
    tele_token = st.text_input("Telegram Bot Token", value=str(load_setting("tele_token", "")), type="password")
    tele_id = st.text_input("Telegram Chat ID", value=str(load_setting("tele_id", "")))

st.write("---")

# ==========================================
# 5. RINGKASAN KINERJA KOMPARATIF
# ==========================================
st.header("📊 RINGKASAN KINERJA KOMPARATIF")
win_rate, profit_factor, total_log = calculate_performance_metrics()
c1, c2, c3 = st.columns(3)
c1.metric(label="Win Rate Bot", value=f"{win_rate} %")
c2.metric(label="Profit Factor", value=f"x {profit_factor}")
c3.metric(label="Total Log Transaksi", value=f"{total_log} Kali")
st.write("---")

# ==========================================
# 6. SAKELAR OPERASIONAL
# ==========================================
col_b1, col_b2 = st.columns(2)
with col_b1:
    if st.button("💾 SIMPAN CONFIG", use_container_width=True):
        config = {
            "candles": candles, "hma_len": hma_len, "ema_len": ema_len, "rsi_len": rsi_len,
            "vol_ma_len": vol_ma_len, "atr_len": atr_len, "sl_atr_mult": sl_atr_mult,
            "buy_amount_idr": buy_amount_idr, "trading_fee": trading_fee, "api_key": api_key,
            "secret_key": secret_key, "tele_token": tele_token, "tele_id": tele_id, "pair": pair
        }
        for k, v in config.items(): save_setting(k, v)
        st.success("Konfigurasi Mutakhir Disimpan Permanen!")
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
    st_autorefresh(interval=15000, key="pro_loop")
    st.info("🤖 Status Jembatan API Indodax: Mode Autopilot Real-Time Aktif...")

# ==========================================
# 7. METRIK UTAMA & PEMINDAIAN PASAR
# ==========================================
balance_data, _ = indodax_private_api(api_key, secret_key, "getInfo") if api_key and secret_key else (None, "")
df_data = fetch_indodax_market_data(pair)

if df_data is not None:
    df_data['EMA'] = calculate_ema(df_data['Close'], ema_len)
    df_data['HMA'] = calculate_hma(df_data['Close'], hma_len)
    df_data['RSI'] = calculate_rsi(df_data['Close'], rsi_len)
    df_data['Vol_MA'] = df_data['Volume'].rolling(int(vol_ma_len)).mean()
    df_data['ATR'] = calculate_atr(df_data, atr_len)
    
    df_display = df_data.tail(int(candles)).reset_index(drop=True)
    latest = df_display.iloc[-1]
    previous = df_display.iloc[-2]
    
    st.subheader("⚪ STATUS PASAR: LIVE MONITORING")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Harga Live IDR", f"Rp {latest['Close']:,.0f}")
    m2.metric("HMA Line", f"{latest['HMA']:.2f}")
    m3.metric("Volume / MA", f"{latest['Volume']:,.0f} / {latest['Vol_MA']:,.0f}")
    m4.metric("ATR Jarak", f"Rp {latest['ATR']:,.0f}")
    
    st.line_chart(df_display[['Close', 'HMA', 'EMA']])

    
    # --- LOGIKA MELEBARKAN PROFIT & SNIPER CROSSOVER ---
    is_cross_over = (previous['HMA'] <= previous['EMA']) and (latest['HMA'] > latest['EMA'])
    is_cross_under = (previous['HMA'] >= previous['EMA']) and (latest['HMA'] < latest['EMA'])
    volume_confirmed = latest['Volume'] > latest['Vol_MA']
    
    # Hitung Jarak Aman Stop Loss Dinamis berbasis ATR
    atr_stop_loss_distance = latest['ATR'] * sl_atr_mult
    current_sl_floor = latest['Close'] - atr_stop_loss_distance
    
    # Deteksi Riwayat Beli Terakhir untuk Fitur Melebarkan Profit (Trailing Stop)
    conn = sqlite3.connect("indodax_pro_bot.db")
    last_buy_trade = pd.read_sql_query("SELECT * FROM trades WHERE type='buy' ORDER BY id DESC LIMIT 1", conn)
    conn.close()
    
    if is_cross_over and latest['RSI'] < 65 and volume_confirmed:
        st.success("🔥 Sinyal BUY Valid Terdeteksi!")
        if st.session_state.autopilot and balance_data:
            saldo_idr = float(balance_data['balance'].get('idr', 0))
            if saldo_idr >= buy_amount_idr:
                order_params = {'pair': pair, 'type': 'buy', 'idr': int(buy_amount_idr)}
                res, msg = indodax_private_api(api_key, secret_key, "trade", order_params)
                if msg == "Sukses":
                    log_trade(pair, "buy", latest['Close'], buy_amount_idr / latest['Close'])
                    st.rerun()

    elif not last_buy_trade.empty:
        buy_price = last_buy_trade.loc[0, 'price']
        coin_amt = last_buy_trade.loc[0, 'amount']
        
        # Logika Amankan Modal: Naikkan batas rugi jika harga melesat jauh di atas harga beli (Trailing)
        if latest['Close'] > buy_price + atr_stop_loss_distance:
            current_sl_floor = buy_price + (latest['ATR'] * 0.5) # Break Even / Secure Capital
            st.info(f"🛡️ Pengaman Modal Aktif: Batas Jual Minimum Bergeser ke Atas Harga Beli (Rp {current_sl_floor:,.0f})")
            
        # Sinyal Keluar: Cross Under ATAU Harga Menembus Batas Stop Loss ATR Lapisan Bawah
        if is_cross_under or latest['Close'] <= current_sl_floor:
            st.error("🚨 Sinyal SELL / Stop Loss ATR Terpicu!")
            if st.session_state.autopilot and balance_data:
                coin_name = pair.split('_')[0]
                sisa_koin = balance_data['balance'].get(coin_name, 0)
                if float(sisa_koin) > 0:
                    order_params = {'pair': pair, 'type': 'sell', coin_name: sisa_koin}
                    res, msg = indodax_private_api(api_key, secret_key, "trade", order_params)
                    if msg == "Sukses":
                        log_trade(pair, "sell", latest['Close'], float(sisa_koin))
                        st.rerun()
    else:
        st.warning("⚪ STATUS PASAR: WAIT / HOLDING (Menunggu Area Pantulan Valid)")
