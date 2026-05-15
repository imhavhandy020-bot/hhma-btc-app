import sqlite3
import pandas as pd
import streamlit as st
import requests
from binance.client import Client
from binance.enums import *
from streamlit_autorefresh import st_autorefresh

# ==========================================
# 1. DATABASE LOKAL (ANTI-LOST CONFIG)
# ==========================================
def init_db():
    conn = sqlite3.connect("bot_settings.db")
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()

def save_setting(key, value):
    conn = sqlite3.connect("bot_settings.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def load_setting(key, default_value):
    conn = sqlite3.connect("bot_settings.db")
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
# 2. SISTEM NOTIFIKASI TELEGRAM
# ==========================================
def send_telegram_alert(token, chat_id, message):
    if not token or not chat_id:
        return
    try:
        url = f"https://telegram.org{token}/sendMessage"
        payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
        requests.post(url, json=payload, timeout=5)
    except Exception:
        pass

# ==========================================
# 3. KALKULASI INDIKATOR SECARA MANUAL (NATIVE)
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

def calculate_atr(df, length):
    high_low = df['High'] - df['Low']
    high_close = (df['High'] - df['Close'].shift()).abs()
    low_close = (df['Low'] - df['Close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(length).mean()

def fetch_and_calculate_data(symbol, timeframe, limit, hma_len, ema_len, rsi_len, vol_len, atr_len):
    try:
        client = Client()
        extended_limit = int(limit) + 100
        klines = client.futures_candles(symbol=symbol, interval=timeframe, limit=extended_limit)
        
        df = pd.DataFrame(klines, columns=[
            'Timestamp', 'Open', 'High', 'Low', 'Close', 'Volume', 
            'Close_time', 'Quote_av', 'Trades', 'Tb_base_av', 'Tb_quote_av', 'Ignore'
        ])
        
        for col in ['Open', 'High', 'Low', 'Close', 'Volume']:
            df[col] = df[col].astype(float)
            
        # Hitung Indikator Menggunakan Fungsi Native Baru
        df['EMA'] = calculate_ema(df['Close'], int(ema_len))
        df['HMA'] = calculate_hma(df['Close'], int(hma_len))
        df['RSI'] = calculate_rsi(df['Close'], int(rsi_len))
        df['Vol_MA'] = df['Volume'].rolling(window=int(vol_len)).mean()
        df['ATR'] = calculate_atr(df, int(atr_len))
        
        return df.tail(int(limit)).reset_index(drop=True)
    except Exception:
        return None

def check_trading_signals(df):
    if len(df) < 2: return "WAIT"
    current = df.iloc[-1]
    previous = df.iloc[-2]
    
    # Validasi penanganan nilai kosong (NaN)
    if pd.isna(current['HMA']) or pd.isna(current['EMA']) or pd.isna(current['Vol_MA']):
        return "WAIT"
        
    is_cross_over = (previous['HMA'] <= previous['EMA']) and (current['HMA'] > current['EMA'])
    is_cross_under = (previous['HMA'] >= previous['EMA']) and (current['HMA'] < current['EMA'])
    volume_confirmed = current['Volume'] > current['Vol_MA']
    
    if is_cross_over and current['RSI'] < 65 and volume_confirmed: return "BUY"
    elif is_cross_under and current['RSI'] > 35 and volume_confirmed: return "SELL"
    return "WAIT"

def execute_futures_trade(api_key, secret_key, symbol, side, initial_margin, leverage, sl_mult, tp_ratio, current_price, atr_value, mode, tele_token, tele_id):
    try:
        testnet_mode = True if mode == "Simulasi / Testnet" else False
        client = Client(api_key, secret_key, testnet=testnet_mode)
        
        client.futures_change_leverage(symbol=symbol, leverage=int(leverage))
        total_buying_power = float(initial_margin) * int(leverage)
        quantity = round(total_buying_power / current_price, 3)
        atr_distance = atr_value * float(sl_mult)
        
        if side == "BUY":
            sl_price = round(current_price - atr_distance, 2)
            tp_price = round(current_price + (atr_distance * float(tp_ratio)), 2)
            order_side, close_side = SIDE_BUY, SIDE_SELL
        else:
            sl_price = round(current_price + atr_distance, 2)
            tp_price = round(current_price - (atr_distance * float(tp_ratio)), 2)
            order_side, close_side = SIDE_SELL, SIDE_BUY

        client.futures_create_order(symbol=symbol, side=order_side, type=FUTURE_ORDER_TYPE_MARKET, quantity=quantity)
        client.futures_create_order(symbol=symbol, side=close_side, type=FUTURE_ORDER_TYPE_STOP_MARKET, stopPrice=sl_price, closePosition=True)
        client.futures_create_order(symbol=symbol, side=close_side, type=FUTURE_ORDER_TYPE_TAKE_PROFIT_MARKET, stopPrice=tp_price, closePosition=True)
        
        msg = f"🚀 *HHMA SNIPER PRO SIGNAL DETECTED*\n\n🔹 *Pair:* {symbol}\n🔹 *Posisi:* {side}\n🔹 *Harga Entry:* ${current_price}\n🔹 *Quantity:* {quantity}\n🛑 *Stop Loss:* ${sl_price}\n🎯 *Take Profit:* ${tp_price}\n⚙️ *Mode:* {mode}"
        send_telegram_alert(tele_token, tele_id, msg)
        
        return True, f"Berhasil {side} {quantity} {symbol}. TP: {tp_price}, SL: {sl_price}"
    except Exception as e:
        return False, f"Gagal Eksekusi Order: {str(e)}"

def execute_emergency_kill(api_key, secret_key, symbol, mode, tele_token, tele_id):
    try:
        testnet_mode = True if mode == "Simulasi / Testnet" else False
        client = Client(api_key, secret_key, testnet=testnet_mode)
        client.futures_cancel_all_open_orders(symbol=symbol)
        position_info = client.futures_position_information(symbol=symbol)
        
        for pos in position_info:
            amt = float(pos['positionAmt'])
            if amt > 0:
                client.futures_create_order(symbol=symbol, side=SIDE_SELL, type=FUTURE_ORDER_TYPE_MARKET, quantity=abs(amt), reduceOnly=True)
            elif amt < 0:
                client.futures_create_order(symbol=symbol, side=SIDE_BUY, type=FUTURE_ORDER_TYPE_MARKET, quantity=abs(amt), reduceOnly=True)
        
        msg = f"🚨 *EMERGENCY KILLED!!!*\n\nBot dihentikan paksa. Seluruh antrean order pada {symbol} telah dibatalkan dan posisi aktif berhasil DITUTUP secara instan!"
        send_telegram_alert(tele_token, tele_id, msg)
        
        return True, "Semua order dibatalkan dan seluruh posisi aktif berhasil DITUTUP!"
    except Exception as e:
        return False, f"Gagal: {str(e)}"

# ==========================================
# 4. ANTARMUKA DESAIN UI (STREAMLIT)
# ==========================================
st.set_page_config(page_title="HHMA Renko Sniper Pro", page_icon="🛡️", layout="wide")
st.title("🛡️ HHMA Renko Sniper Pro - Binance Futures Trading Bot")
st.write("---")

if 'autopilot' not in st.session_state:
    st.session_state.autopilot = False

col_left, col_right = st.columns()

with col_left:
    st.header("🕹️ PANEL KENDALI UTAMA")
    symbol = st.selectbox("Asset Pair Selector", ["BTCUSDT", "ETHUSDT", "SOLUSDT"], index=0)
    timeframe = st.selectbox("Timeframe (Fokus Satu TF)", ["1m", "5m", "15m", "1h", "4h", "1d"], index=4)
    source_data = st.selectbox("Source Data", ["Close", "Open", "High", "Low"], index=0)
    
    candles = st.number_input("Jumlah Lilin di Layar", value=load_setting("candles", 10))
    hma_len = st.number_input("HMA Length", value=load_setting("hma_len", 5))
    ema_len = st.number_input("EMA Length", value=load_setting("ema_len", 5))
    rsi_len = st.number_input("RSI Length", value=load_setting("rsi_len", 5))
    vol_len = st.number_input("Volume MA Length", value=load_setting("vol_len", 5))
    atr_len = st.number_input("ATR Length", value=load_setting("atr_len", 5))
    sl_mult = st.number_input("Stop Loss ATR Mult", value=load_setting("sl_mult", 2.50), step=0.1)
    chan_mult = st.number_input("Chandelier Trailing Mult", value=load_setting("chan_mult", 1.00), step=0.1)

with col_right:
    st.header("🔥 PENGATURAN KEUANGAN AGRESIF")
    margin_type = st.radio("Margin Type", ["Isolated", "Cross"], index=0)
    initial_margin = st.number_input("Initial Margin ($)", value=load_setting("initial_margin", 100.0))
    leverage = st.slider("Leverage", min_value=1, max_value=125, value=load_setting("leverage", 25))
    max_risk = st.number_input("Max Risk per Trade (%)", value=load_setting("max_risk", 2.0))
    slippage = st.number_input("Slippage Tolerance (%)", value=load_setting("slippage", 0.1))
    tp_ratio = st.number_input("TP 1 Ratio (Risk:Reward)", value=load_setting("tp_ratio", 1.50))
    tp_size = st.number_input("TP 1 Size (% Volume Close)", value=load_setting("tp_size", 50))
    fee = st.number_input("Trading Fee (%)", value=load_setting("fee", 0.04))
    
    st.header("🟡 INTEGRASI API BINANCE FUTURES")
    api_key = st.text_input("Binance API Key", value=load_setting("api_key", ""), type="password")
    secret_key = st.text_input("Binance Secret Key", value=load_setting("secret_key", ""), type="password")
    execution_mode = st.radio("Mode Eksekusi", ["Simulasi / Testnet", "Live Real Trading"])

    st.header("📱 NOTIFIKASI TELEGRAM OLEH BOT")
    tele_token = st.text_input("Telegram Bot Token", value=load_setting("tele_token", ""), type="password")
    tele_id = st.text_input("Telegram Chat ID", value=load_setting("tele_id", ""))

st.write("---")

# ==========================================
# 5. KONTROL UTAMA & AUTOPILOT SAKELAR
# ==========================================
col_b1, col_b2, col_b3 = st.columns(3)

with col_b1:
    if st.button("💾 SIMPAN CONFIG", use_container_width=True):
        config_dict = {
            "candles": candles, "hma_len": hma_len, "ema_len": ema_len, "rsi_len": rsi_len, 
            "vol_len": vol_len, "atr_len": atr_len, "sl_mult": sl_mult, "chan_mult": chan_mult, 
            "initial_margin": initial_margin, "leverage": leverage, "max_risk": max_risk, 
            "slippage": slippage, "tp_ratio": tp_ratio, "tp_size": tp_size, "fee": fee, 
            "api_key": api_key, "secret_key": secret_key, "tele_token": tele_token, "tele_id": tele_id
        }
        for k, v in config_dict.items():
            save_setting(k, v)
        st.success("Konfigurasi dan Kredensial Telegram disimpan!")

with col_b2:
    if st.session_state.autopilot:
        if st.button("🔴 MATIKAN AUTOPILOT", type="secondary", use_container_width=True):
            st.session_state.autopilot = False
            st.rerun()
    else:
        if st.button("🟢 AKTIFKAN AUTOPILOT", type="primary", use_container_width=True):
            st.session_state.autopilot = True
            st.rerun()

with col_b3:
    if st.button("🚨 EMERGENCY KILL SWITCH", type="primary", use_container_width=True):
        st.session_state.autopilot = False
        success, msg = execute_emergency_kill(api_key, secret_key, symbol, execution_mode, tele_token, tele_id)
        st.error(f"🚨 DARURAT: {msg}")

if st.session_state.autopilot:
    st_autorefresh(interval=15000, key="bot_loop")
    st.info("🔄 Mode Autopilot Aktif: Memindai harga real-time setiap 15 detik...")

# ==========================================
# 6. PEMROSESAN DATA LIVE & SCANNING
# ==========================================
df_data = fetch_and_calculate_data(symbol, timeframe, candles, hma_len, ema_len, rsi_len, vol_len, atr_len)

if df_data is not None:
    latest = df_data.iloc[-1]
    
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric(label=f"Harga Live {symbol}", value=f"${latest['Close']:,}")
    col_m2.metric(label="HMA", value=f"{latest['HMA']:.2f}" if not pd.isna(latest['HMA']) else "Kalkulasi...")
    col_m3.metric(label="EMA", value=f"{latest['EMA']:.2f}" if not pd.isna(latest['EMA']) else "Kalkulasi...")
    col_m4.metric(label="RSI", value=f"{latest['RSI']:.2f}" if not pd.isna(latest['RSI']) else "Kalkulasi...")
    
    st.line_chart(df_data[['Close', 'HMA', 'EMA']].dropna())
    
    signal = check_trading_signals(df_data)
    if signal in ["BUY", "SELL"]:
        st.subheader(f"🔥 SINYAL {signal} TERDETEKSI!")
        if st.session_state.autopilot and api_key and secret_key:
            success, msg = execute_futures_trade(
                api_key, secret_key, symbol, signal, initial_margin, 
                leverage, sl_mult, tp_ratio, latest['Close'], latest['ATR'], 
                execution_mode, tele_token, tele_id
            )
            st.success(msg) if success else st.error(msg)
    else:
        st.warning("⚪ STATUS PASAR: WAIT / HOLDING (Menunggu Area Pantulan Valid)")
