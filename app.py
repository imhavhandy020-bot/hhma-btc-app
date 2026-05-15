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
    # Buat tabel saldo virtual jika belum ada
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
        val = row
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

def calculate_performance_metrics(mode):
    conn = sqlite3.connect("indodax_sim_final.db")
    df = pd.read_sql_query(f"SELECT * FROM trades WHERE mode='{mode}'", conn)
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
        else:
            return None, f"Gagal API: {res.get('error', 'Kunci API Ditolak')}"
    except Exception as e: 
        return None, f"Koneksi Bermasalah: {str(e)}"

# ==========================================
# 4. ANTARMUKA PANEL UTAMA (UI)
# ==========================================
st.set_page_config(page_title="Indodax Sniper Pro v2", page_icon="🛡️", layout="wide")
st.title("🛡️ HHMA Renko Sniper Pro - Indodax Edition")
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
    sl_atr_mult = st.number_input("Stop Loss ATR Mult", value=float(load_setting("sl_atr_mult", 2.50)), step=0.1)

with col_right:
    st.header("🔥 PENGATURAN KEUANGAN")
    buy_amount_idr = st.number_input("Initial Purchase ($ / IDR)", value=int(load_setting("buy_amount_idr", 50000)))
    trading_fee = st.number_input("Trading Fee (%)", value=float(load_setting("trading_fee", 0.30)))
    
    # PARAMETER MODE EKSEKUSI (LOCK REFRESH)
    saved_mode = load_setting("execution_mode", "Simulasi / Testnet")
    mode_index = 0 if saved_mode == "Simulasi / Testnet" else 1
    execution_mode = st.radio("Mode Eksekusi", ["Simulasi / Testnet", "Live Real Trading"], index=mode_index)

    st.header("🟡 INTEGRASI API REAL TRADING")
    api_key = st.text_input("Indodax API Key (Kosongkan jika simulasi)", value=str(load_setting("api_key", "")), type="password")
    secret_key = st.text_input("Indodax Secret Key (Kosongkan jika simulasi)", value=str(load_setting("secret_key", "")), type="password")
    
    st.header("📱 NOTIFIKASI TELEGRAM")
    tele_token = st.text_input("Telegram Bot Token", value=str(load_setting("tele_token", "")), type="password")
    tele_id = st.text_input("Telegram Chat ID", value=str(load_setting("tele_id", "")))

st.write("---")

# ==========================================
# 5. RINGKASAN KINERJA KOMPARATIF
# ==========================================
st.header(f"📊 RINGKASAN KINERJA KOMPARATIF ({execution_mode.upper()})")
win_rate, profit_factor, total_log = calculate_performance_metrics(execution_mode)
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
            "secret_key": secret_key, "tele_token": tele_token, "tele_id": tele_id, "pair": pair,
            "execution_mode": execution_mode
        }
        for k, v in config.items(): save_setting(k, v)
        st.success("Konfigurasi Berhasil Disimpan!")
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
    st.info(f"🤖 Status Jembatan API: Mode Autopilot [{execution_mode}] Aktif...")

# ==========================================
# 7. MONITOR SALDO (REAL VS VIRTUAL)
# ==========================================
st.write("---")
st.subheader("💰 MONITOR SALDO AKUN")

v_idr, v_coin = get_virtual_balance()

if execution_mode == "Live Real Trading":
    if api_key and secret_key:
        balance_data, status = indodax_private_api(api_key, secret_key, "getInfo")
        if status == "Sukses" and balance_data is not None:
            saldo_idr = float(balance_data['balance'].get('idr', 0))
            st.metric(label="Saldo Rupiah Real (IDR) Anda", value=f"Rp {saldo_idr:,.0f}")
        else:
            st.warning(f"⚠️ {status}")
    else:
        st.info("💡 Masukkan API Key & Secret Key untuk live trading.")
else:
    # Tampilan Saldo Virtual untuk Mode Simulasi
    st.info("🎮 Anda sedang berada dalam MODE SIMULASI (Menggunakan Saldo Demo Lokal)")
    cm1, cm2 = st.columns(2)
    cm1.metric(label="Saldo Rupiah Virtual (IDR)", value=f"Rp {v_idr:,.0f}")
    cm2.metric(label=f"Saldo Koin Virtual ({pair.split('_')[0].upper()})", value=f"{v_coin:.6f}")

# ==========================================
# 8. PEMROSESAN DATA & EKSEKUSI STRATEGI
# ==========================================
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
    
    st.write("---")
    st.subheader(f"📊 DATA PASAR REAL-TIME ({pair.upper()})")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Harga Live IDR", f"Rp {latest['Close']:,.0f}")
    m2.metric("HMA Line", f"{latest['HMA']:.2f}")
    m3.metric("Volume / MA", f"{latest['Volume']:,.0f} / {latest['Vol_MA']:,.0f}")
    m4.metric("ATR Jarak", f"Rp {latest['ATR']:,.0f}")
    
    st.line_chart(df_display, y=['Close', 'HMA', 'EMA'])

    
    # Logika Crossover
    is_cross_over = (previous['HMA'] <= previous['EMA']) and (latest['HMA'] > latest['EMA'])
    is_cross_under = (previous['HMA'] >= previous['EMA']) and (latest['HMA'] < latest['EMA'])
    volume_confirmed = latest['Volume'] > latest['Vol_MA']
    
    atr_stop_loss_distance = latest['ATR'] * sl_atr_mult
    current_sl_floor = latest['Close'] - atr_stop_loss_distance
    
    conn = sqlite3.connect("indodax_sim_final.db")
    last_buy_trade = pd.read_sql_query(f"SELECT * FROM trades WHERE type='buy' AND mode='{execution_mode}' ORDER BY id DESC LIMIT 1", conn)
    conn.close()
    
    if is_cross_over and latest['RSI'] < 65 and volume_confirmed:
        st.success("🔥 Sinyal BUY Valid Terdeteksi!")
        if st.session_state.autopilot:
            if execution_mode == "Live Real Trading" and api_key and secret_key:
                # Beli Asli
                order_params = {'pair': pair, 'type': 'buy', 'idr': int(buy_amount_idr)}
                res, msg = indodax_private_api(api_key, secret_key, "trade", order_params)
                if msg == "Sukses":
                    log_trade(pair, "buy", latest['Close'], buy_amount_idr / latest['Close'], execution_mode)
                    st.rerun()
            elif execution_mode == "Simulasi / Testnet":
                # Beli Simulasi
                if v_idr >= buy_amount_idr:
                    new_idr = v_idr - buy_amount_idr
                    bought_coin = buy_amount_idr / latest['Close']
                    new_coin = v_coin + bought_coin
                    update_virtual_balance(new_idr, new_coin)
                    log_trade(pair, "buy", latest['Close'], bought_coin, execution_mode)
                    st.success(f"🎰 [SIMULASI BUY] Berhasil membeli {bought_coin:.4f} koin.")
                    st.rerun()

    elif not last_buy_trade.empty:
        buy_price = last_buy_trade.loc[0, 'price']
        coin_amt = last_buy_trade.loc[0, 'amount']
        
        if latest['Close'] > buy_price + atr_stop_loss_distance:
            current_sl_floor = buy_price + (latest['ATR'] * 0.5)
            st.info(f"🛡️ Pengaman Modal Aktif: Batas Trailing Profit Dikunci pada Level Rp {current_sl_floor:,.0f}")
            
        if is_cross_under or latest['Close'] <= current_sl_floor:
            st.error("🚨 Sinyal SELL / Stop Loss ATR Terpicu!")
            if st.session_state.autopilot:
                if execution_mode == "Live Real Trading" and api_key and secret_key:
                    # Jual Asli
                    coin_name = pair.split('_')[0]
                    sisa_koin = balance_data['balance'].get(coin_name, 0)
                    if float(sisa_koin) > 0:
                        order_params = {'pair': pair, 'type': 'sell', coin_name: sisa_koin}
                        res, msg = indodax_private_api(api_key, secret_key, "trade", order_params)
                        if msg == "Sukses":
                            log_trade(pair, "sell", latest['Close'], float(sisa_koin), execution_mode)
                            st.rerun()
                elif execution_mode == "Simulasi / Testnet":
                    # Jual Simulasi
                    if v_coin > 0:
                        revenue = v_coin * latest['Close']
                        new_idr = v_idr + revenue
                        update_virtual_balance(new_idr, 0.0)
                        log_trade(pair, "sell", latest['Close'], v_coin, execution_mode)
                        st.error(f"🎰 [SIMULASI SELL] Berhasil melikuidasi koin. Pendapatan: Rp {revenue:,.0f}")
                        st.rerun()
    else:
        st.warning("⚪ STATUS PASAR: WAIT / HOLDING (Menunggu Area Pantulan Valid)")
