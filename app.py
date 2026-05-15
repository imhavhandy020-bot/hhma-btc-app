import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime

st.set_page_config(page_title="HHMA Sniper BTC Futures Max Pro", layout="wide")
st.title("🛡️ HHMA Renko Sniper Pro - 4H Institutional System")

# ==========================================
# 💾 SISTEM PENYIMPANAN PARSING & RESET STATE
# ==========================================
DEFAULTS = {
    "tf_pilihan": "4 Jam (4h)",
    "src_pilihan": "Close (Penutupan)",
    "jumlah_tampilan": 150,
    "length_hma": 16,
    "length_ema": 50,
    "length_rsi": 14,
    "length_vol_ma": 30,
    "length_atr": 14,
    "atr_multiplier": 3.5,
    "chandelier_mult": 2.0,
    "modal_awal": 1000.0,
    "leverage": 10,
    "risiko_per_trade_pct": 1.0,
    "tp1_ratio": 0.5,
    "tp2_ratio": 1.5,
    "trading_fee_pct": 0.04,
    "session_filter_active": False,
    "start_hour": 14,
    "end_hour": 23
}

for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val

def reset_to_defaults():
    for key, val in DEFAULTS.items():
        st.session_state[key] = val
    st.success("🔄 Pengaturan berhasil dikembalikan ke standar awal pabrik!")

# ==========================================
# ⚙️ PANEL SETELAN PARAMETER (SIDEBAR)
# ==========================================
st.sidebar.header("🕹️ PANEL KENDALI UTAMA")

col_action1, col_action2 = st.sidebar.columns(2)
with col_action1:
    btn_simpan = st.button("💾 Simpan Setelan", help="Mengunci parameter kustom Anda.")
with col_action2:
    st.button("🔄 Reset Standar", on_click=reset_to_defaults, help="Kembali ke rumus presisi awal.")

st.sidebar.markdown("---")
st.sidebar.subheader("📦 1. Parameter Utama Pasar")
tf_options = ["4 Jam (4h)", "1 Hari (Daily)", "1 Jam (1h)", "15 Menit (15m)"]
src_options = ["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"]

tf_pilihan = st.sidebar.selectbox("Jangka Waktu (Timeframe):", options=tf_options, index=tf_options.index(st.session_state.tf_pilihan))
src_pilihan = st.sidebar.selectbox("Sumber Data (Source):", options=src_options, index=src_options.index(st.session_state.src_pilihan))
jumlah_tampilan = st.sidebar.number_input("Jumlah Lilin di Layar:", min_value=10, max_value=300, value=int(st.session_state.jumlah_tampilan), step=10)

st.sidebar.markdown("---")
st.sidebar.subheader("📈 2. Konfigurasi Sinyal Sniper")
length_hma = st.sidebar.number_input("Panjang HMA (Trend Utama):", min_value=2, max_value=50, value=int(st.session_state.length_hma), step=1)
length_ema = st.sidebar.number_input("Periode EMA (Pullback Zone):", min_value=5, max_value=200, value=int(st.session_state.length_ema), step=1)
length_rsi = st.sidebar.number_input("Periode RSI (Momentum):", min_value=5, max_value=30, value=int(st.session_state.length_rsi), step=1)
length_vol_ma = st.sidebar.number_input("Periode Volume MA (Saringan):", min_value=5, max_value=50, value=int(st.session_state.length_vol_ma), step=1)

st.sidebar.markdown("---")
st.sidebar.subheader("🛡️ 3. Proteksi Volatilitas (ATR & Trailing)")
length_atr = st.sidebar.number_input("Periode ATR:", min_value=5, max_value=30, value=int(st.session_state.length_atr), step=1)
atr_multiplier = st.sidebar.number_input("Pengali ATR (Stop Loss Jauh):", min_value=1.0, max_value=4.5, value=float(st.session_state.atr_multiplier), step=0.1)
chandelier_mult = st.sidebar.number_input("Chandelier Trailing Mult:", min_value=1.0, max_value=4.0, value=float(st.session_state.chandelier_mult), step=0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("⏱️ 4. Saringan Jam Sesi Pasar")
session_filter_active = st.sidebar.checkbox("Aktifkan Filter Jam Trading", value=st.session_state.session_filter_active)
col_h1, col_h2 = st.sidebar.columns(2)
with col_h1:
    start_hour = st.number_input("Jam Mulai (WIB):", min_value=0, max_value=23, value=int(st.session_state.start_hour), step=1)
with col_h2:
    end_hour = st.number_input("Jam Selesai (WIB):", min_value=0, max_value=23, value=int(st.session_state.end_hour), step=1)

st.sidebar.markdown("---")
st.sidebar.subheader("🔥 5. Manajemen Risiko & Keuangan")
modal_awal = st.sidebar.number_input("Margin Awal (\$ USD):", min_value=10.0, value=float(st.session_state.modal_awal), step=100.0)
leverage = st.sidebar.number_input("Leverage (Multiplier):", min_value=1, max_value=50, value=int(st.session_state.leverage), step=1)
risiko_per_trade_pct = st.sidebar.number_input("Risiko per Transaksi (%):", min_value=0.5, max_value=10.0, value=float(st.session_state.risiko_per_trade_pct), step=0.5)

col_tp1, col_tp2 = st.sidebar.columns(2)
with col_tp1:
    tp1_ratio = st.number_input("Rasio TP 1:", min_value=0.3, max_value=2.0, value=float(st.session_state.tp1_ratio), step=0.1)
with col_tp2:
    tp2_ratio = st.number_input("Rasio TP 2:", min_value=1.0, max_value=5.0, value=float(st.session_state.tp2_ratio), step=0.1)

trading_fee_pct = st.sidebar.number_input("Fee Bursa per Eksekusi (%):", min_value=0.0, max_value=1.0, value=float(st.session_state.trading_fee_pct), step=0.01)

st.sidebar.markdown("---")
st.sidebar.subheader("🤖 6. Integrasi Telegram")
telegram_token = st.sidebar.text_input("Telegram Bot Token:", type="password")
telegram_chat_id = st.sidebar.text_input("Telegram Chat ID:")

if btn_simpan:
    st.session_state.tf_pilihan = tf_pilihan
    st.session_state.src_pilihan = src_pilihan
    st.session_state.jumlah_tampilan = jumlah_tampilan
    st.session_state.length_hma = length_hma
    st.session_state.length_ema = length_ema
    st.session_state.length_rsi = length_rsi
    st.session_state.length_vol_ma = length_vol_ma
    st.session_state.length_atr = length_atr
    st.session_state.atr_multiplier = atr_multiplier
    st.session_state.chandelier_mult = chandelier_mult
    st.session_state.modal_awal = modal_awal
    st.session_state.leverage = leverage
    st.session_state.risiko_per_trade_pct = risiko_per_trade_pct
    st.session_state.tp1_ratio = tp1_ratio
    st.session_state.tp2_ratio = tp2_ratio
    st.session_state.trading_fee_pct = trading_fee_pct
    st.session_state.session_filter_active = session_filter_active
    st.session_state.start_hour = start_hour
    st.session_state.end_hour = end_hour
    st.success("💾 Seluruh konfigurasi kustom Anda berhasil dikunci secara permanen!")

# ==========================================
# 📊 PROSES PENGOLAHAN DATA & INDIKATOR
# ==========================================
src_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}
src_aktif = src_map[st.session_state.src_pilihan]

interval_map = {"4 Jam (4h)": "4h", "1 Hari (Daily)": "1d", "1 Jam (1h)": "1h", "15 Menit (15m)": "15m"}
period_map = {"4 Jam (4h)": "180d", "1 Hari (Daily)": "730d", "1 Jam (1h)": "90d", "15 Menit (15m)": "30d"}

def send_telegram_alert(message):
    if telegram_token and telegram_chat_id:
        url = f"https://telegram.org{telegram_token}/sendMessage"
        payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "Markdown"}
        try: requests.post(url, json=payload, timeout=5)
        except: pass

@st.cache_data(ttl=30)
def get_crypto_data(p, i):
    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(period=p, interval=i)
    df = df.reset_index()
    if 'Date' in df.columns: df = df.rename(columns={'Date': 'date'})
    elif 'Datetime' in df.columns: df = df.rename(columns={'Datetime': 'date'})
    df['date'] = pd.to_datetime(df['date']).dt.tz_convert(None)
    df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
    return df

try:
    df = get_crypto_data(period_map[st.session_state.tf_pilihan], interval_map[st.session_state.tf_pilihan])
    if df.empty:
        st.error("Gagal mengambil data dari Yahoo Finance.")
        st.stop()

    df['hma'] = ta.hma(df[src_aktif], length=st.session_state.length_hma)
    df['ema'] = ta.ema(df['close'], length=st.session_state.length_ema)
    df['rsi'] = ta.rsi(df['close'], length=st.session_state.length_rsi)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=st.session_state.length_atr)
    df['vol_ma'] = ta.sma(df['volume'], length=st.session_state.length_vol_ma)
    
    df['highest_high'] = df['high'].rolling(window=22).max()
    df['lowest_low'] = df['low'].rolling(window=22).min()
    df['chandelier_long'] = df['highest_high'] - (df['atr'] * st.session_state.chandelier_mult)
    df['chandelier_short'] = df['lowest_low'] + (df['atr'] * st.session_state.chandelier_mult)

    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['is_red'] = df['hma'] < df['hma'].shift(1)

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    for i in df.index:
        if i < max(st.session_state.length_hma, st.session_state.length_ema, st.session_state.length_atr, st.session_state.length_vol_ma, st.session_state.length_rsi, 22): continue
            
        is_pullback_long = (df.at[i, 'low'] <= df.at[i, 'ema'] * 1.002) and (df.at[i, 'close'] > df.at[i, 'ema'])
        is_pullback_short = (df.at[i, 'high'] >= df.at[i, 'ema'] * 0.998) and (df.at[i, 'close'] < df.at[i, 'ema'])
        
        rsi_safe_long = df.at[i, 'rsi'] < 55
        rsi_safe_short = df.at[i, 'rsi'] > 45
        volume_valid = df.at[i, 'volume'] > df.at[i, 'vol_ma']

        # Saringan Jam Sesi Pasar Dinamis
        time_valid = True
        if st.session_state.session_filter_active:
            current_hour = df.at[i, 'date'].hour
            if st.session_state.start_hour <= st.session_state.end_hour:
                time_valid = st.session_state.start_hour <= current_hour <= st.session_state.end_hour
            else:
                time_valid = current_hour >= st.session_state.start_hour or current_hour <= st.session_state.end_hour

        if df.at[i, 'is_green'] and is_pullback_long and rsi_safe_long and volume_valid and time_valid and last_signal != 1:
            df.at[i, 'buy_signal'] = True
            last_signal = 1
        elif df.at[i, 'is_red'] and is_pullback_short and rsi_safe_short and volume_valid and time_valid and last_signal != -1:
            df.at[i, 'sell_signal'] = True
            last_signal = -1

    df['display_buy'] = df['buy_signal']
    df['display_sell'] = df['sell_signal']

    # --- BANNER SINYAL REAL-TIME ---
    last_row = df.iloc[-1]
    if last_row['display_buy']:
        st.success("### 🟢 SINYAL AKTIF: LONG (BUY) SEKARANG! 🚀")
        st.info(f"**Parameter:** Entry: ${last_row['close']:,.2f} | Est. SL: ${last_row['close'] - (last_row['atr'] * st.session_state.atr_multiplier):,.2f}")
    elif last_row['display_sell']:
        st.error("### 🔴 SINYAL AKTIF: SHORT (SELL) SEKARANG! 📉")
        st.info(f"**Parameter:** Entry: ${last_row['close']:,.2f} | Est. SL: ${last_row['close'] + (last_row['atr'] * st.session_state.atr_multiplier):,.2f}")
    else:
        if last_row['is_green']: st.info("### ⚪ STATUS PASAR: WAIT / HOLD LONG (Tren Bullish Berjalan) 📈")
        else: st.warning("### ⚪ STATUS PASAR: WAIT / HOLD SHORT (Tren Bearish Berjalan) 📉")

    st.markdown("---")

    # ==========================================
    # ⚙️ SIMULATOR BACKTEST UTAMA + COMPOUNDING
    # ==========================================
    trades_list = []  
    active_trade = None
    current_equity = st.session_state.modal_awal
    
    equity_timestamps = [df.loc[0, 'date']]
    equity_values = [st.session_state.modal_awal]

    for i in df.index:
        if active_trade is not None and active_trade['Status'] == "Berjalan (Running)":
            if active_trade['Posisi'] == "🟢 LONG (Buy)":
                current_sl = max(active_trade['Harga SL (\$)'], df.at[i, 'chandelier_long'])
                if df.at[i, 'low'] <= current_sl:
                    p_close = current_sl
                    ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                    profit_raw = ((p_close - active_trade['Harga Entry (\$)']) / active_trade['Harga Entry (\$)']) * 100
                    profit_net = (profit_raw * st.session_state.leverage) - (st.session_state.trading_fee_pct * 2)
                    laba_usd = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * ratio_aktif
                    current_equity += laba_usd
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close (\$)'] = round(p_close, 2)
                    active_trade['Status'] = "💥 Terkena Stop Loss/Trailing" if not active_trade['TP1_Hit'] else "🎯 TP1 + 💥 SL Sisa"
                    active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                    active_trade['Ekuitas Akhir (\$)'] = round(current_equity, 2)
                    trades_list.append(active_trade)
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)
                    active_trade = None

                elif not active_trade['TP1_Hit'] and df.at[i, 'high'] >= active_trade['Harga TP1 (\$)']:
                    p_close = active_trade['Harga TP1 (\$)']
                    profit_raw = ((p_close - active_trade['Harga Entry (\$)']) / active_trade['Harga Entry (\$)']) * 100
                    profit_net = (profit_raw * st.session_state.leverage) - (st.session_state.trading_fee_pct * 2)
                    laba_tp1 = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * 0.5
                    current_equity += laba_tp1
                    active_trade['TP1_Hit'] = True
                    active_trade['Laba_TP1_USD'] = laba_tp1
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)

                elif active_trade['TP1_Hit'] and df.at[i, 'high'] >= active_trade['Harga TP2 (\$)']:
                    p_close = active_trade['Harga TP2 (\$)']
                    profit_raw = ((p_close - active_trade['Harga Entry (\$)']) / active_trade['Harga Entry (\$)']) * 100
                    profit_net = (profit_raw * st.session_state.leverage) - (st.session_state.trading_fee_pct * 2)
                    laba_tp2 = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * 0.5
                    current_equity += laba_tp2
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close (\$)'] = round(p_close, 2)
                    active_trade['Status'] = "🎯 Target Tercapai Penuh (TP1+TP2)"
                    active_trade['Laba Bersih ($ USD)'] = round(active_trade['Laba_TP1_USD'] + laba_tp2, 2)
                    active_trade['Ekuitas Akhir (\$)'] = round(current_equity, 2)
                    trades_list.append(active_trade)
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)
                    active_trade = None

            elif active_trade is not None and active_trade['Posisi'] == "🔴 SHORT (Sell)":
                current_sl = min(active_trade['Harga SL (\$)'], df.at[i, 'chandelier_short'])
                if df.at[i, 'high'] >= current_sl:
                    p_close = current_sl
                    ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                    profit_raw = ((active_trade['Harga Entry (\$)'] - p_close) / active_trade['Harga Entry (\$)']) * 100
                    profit_net = (profit_raw * st.session_state.leverage) - (st.session_state.trading_fee_pct * 2)
                    laba_usd = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * ratio_aktif
                    current_equity += laba_usd
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close (\$)'] = round(p_close, 2)
                    active_trade['Status'] = "💥 Terkena Stop Loss/Trailing" if not active_trade['TP1_Hit'] else "🎯 TP1 + 💥 SL Sisa"
                    active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                    active_trade['Ekuitas Akhir (\$)'] = round(current_equity, 2)
                    trades_list.append(active_trade)
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)
                    active_trade = None

                elif not active_trade['TP1_Hit'] and df.at[i, 'low'] <= active_trade['Harga TP1 (\$)']:
                    p_close = active_trade['Harga TP1 (\$)']
                    profit_raw = ((active_trade['Harga Entry (\$)'] - p_close) / active_trade['Harga Entry (\$)']) * 100
                    profit_net = (profit_raw * st.session_state.leverage) - (st.session_state.trading_fee_pct * 2)
                    laba_tp1 = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * 0.5
                    current_equity += laba_tp1
                    active_trade['TP1_Hit'] = True
                    active_trade['Laba_TP1_USD'] = laba_tp1
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)

                elif active_trade['TP1_Hit'] and df.at[i, 'low'] <= active_trade['Harga TP2 (\$)']:
                    p_close = active_trade['Harga TP2 (\$)']
                    profit_raw = ((active_trade['Harga Entry (\$)'] - p_close) / active_trade['Harga Entry (\$)']) * 100
                    profit_net = (profit_raw * st.session_state.leverage) - (st.session_state.trading_fee_pct * 2)
                    laba_tp2 = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * 0.5
                    current_equity += laba_tp2
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close (\$)'] = round(p_close, 2)
                    active_trade['Status'] = "🎯 Target Tercapai Penuh (TP1+TP2)"
                    active_trade['Laba Bersih ($ USD)'] = round(active_trade['Laba_TP1_USD'] + laba_tp2, 2)
                    active_trade['Ekuitas Akhir (\$)'] = round(current_equity, 2)
                    trades_list.append(active_trade)
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)
                    active_trade = None

        if df.at[i, 'display_buy']:
            if active_trade is not None:
                ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                p_close = df.at[i, 'close']
                profit_raw = ((p_close - active_trade['Harga Entry (\$)']) if active_trade['Posisi'] == "🟢 LONG (Buy)" else (active_trade['Harga Entry (\$)'] - p_close)) / active_trade['Harga Entry (\$)'] * 100
                profit_net = (profit_raw * st.session_state.leverage) - (st.session_state.trading_fee_pct * 2)
                laba_usd = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * ratio_aktif
                current_equity += laba_usd
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                trades_list.append(active_trade)
                equity_timestamps.append(df.at[i, 'date'])
                equity_values.append(current_equity)
                active_trade = None

            sl_price = df.at[i, 'close'] - (df.at[i, 'atr'] * st.session_state.atr_multiplier)
            jarak_sl = abs(df.at[i, 'close'] - sl_price)
            tp1_price = df.at[i, 'close'] + (jarak_sl * st.session_state.tp1_ratio)
            tp2_price = df.at[i, 'close'] + (jarak_sl * st.session_state.tp2_ratio)
            
            jarak_sl_pct = jarak_sl / df.at[i, 'close']
            usd_risk = current_equity * (st.session_state.risiko_per_trade_pct / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * st.session_state.leverage)), current_equity * 0.95)

            active_trade = {
                'Posisi': "🟢 LONG (Buy)", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry (\$)': round(df.at[i, 'close'], 2), 'Harga SL (\$)': round(sl_price, 2),
                'Harga TP1 (\$)': round(tp1_price, 2), 'Harga TP2 (\$)': round(tp2_price, 2),
                'Margin Kunci (\$)': round(margin_final, 2), 'Status': "Berjalan (Running)", 'TP1_Hit': False, 'Laba_TP1_USD': 0
            }
            if i == df.index[-1]:
                send_telegram_alert(f"🟢 *SNIPER LONG BTC-USD*\nEntry: ${df.at[i, 'close']:.2f}\nSL: ${sl_price:.2f}")

        elif df.at[i, 'display_sell']:
            if active_trade is not None:
                ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                p_close = df.at[i, 'close']
                profit_raw = ((p_close - active_trade['Harga Entry (\$)']) if active_trade['Posisi'] == "🟢 LONG (Buy)" else (active_trade['Harga Entry (\$)'] - p_close)) / active_trade['Harga Entry (\$)'] * 100
                profit_net = (profit_raw * st.session_state.leverage) - (st.session_state.trading_fee_pct * 2)
                laba_usd = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * ratio_aktif
                current_equity += laba_usd
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                trades_list.append(active_trade)
                equity_timestamps.append(df.at[i, 'date'])
                equity_values.append(current_equity)
                active_trade = None

            sl_price = df.at[i, 'close'] + (df.at[i, 'atr'] * st.session_state.atr_multiplier)
            jarak_sl = abs(sl_price - df.at[i, 'close'])
            tp1_price = df.at[i, 'close'] - (jarak_sl * st.session_state.tp1_ratio)
            tp2_price = df.at[i, 'close'] - (jarak_sl * st.session_state.tp2_ratio)
            
            jarak_sl_pct = jarak_sl / df.at[i, 'close']
            usd_risk = current_equity * (st.session_state.risiko_per_trade_pct / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * st.session_state.leverage)), current_equity * 0.95)

            active_trade = {
                'Posisi': "🔴 SHORT (Sell)", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry (\$)': round(df.at[i, 'close'], 2), 'Harga SL (\$)': round(sl_price, 2),
                'Harga TP1 (\$)': round(tp1_price, 2), 'Harga TP2 (\$)': round(tp2_price, 2),
                'Margin Kunci (\$)': round(margin_final, 2), 'Status': "Berjalan (Running)", 'TP1_Hit': False, 'Laba_TP1_USD': 0
            }
            if i == df.index[-1]:
                send_telegram_alert(f"🔴 *SNIPER SHORT BTC-USD*\nEntry: \({df.at[i, 'close']:.2f}\nSL:\){sl_price:.2f}")

    if active_trade is not None and active_trade not in trades_list:
        trades_list.append(active_trade)

    # ==========================================
    # 📉 KALKULASI METRIK & RENDERING DASHBOARD
    # ==========================================
    total_trades_done = [t for t in trades_list if t['Status'] != "Berjalan (Running)"]
    win_rate = 0.0; profit_factor = 0.0; total_profit_usd = 0.0; max_dd_pct = 0.0

    if len(total_trades_done) > 0:
        wins = [t for t in total_trades_done if t['Laba Bersih (\$ USD)'] > 0]
        losses = [t for t in total_trades_done if t['Laba Bersih (\$ USD)'] < 0]
        win_rate = (len(wins) / len(total_trades_done)) * 100
        total_profit_usd = sum([t['Laba Bersih (\$ USD)'] for t in total_trades_done])
        
        gross_profit = sum([t['Laba Bersih (\$ USD)'] for t in wins])
        gross_loss = abs(sum([t['Laba Bersih (\$ USD)'] for t in losses]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

        equity_series = pd.Series(equity_values)
        cum_max = equity_series.cummax()
        max_dd_pct = abs(((equity_series - cum_max) / cum_max).min()) * 100

    current_price = df.iloc[-1]['close']
    
    st.markdown("### 📊 Hasil Evaluasi
