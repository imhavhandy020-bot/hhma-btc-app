import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
from datetime import datetime, time

st.set_page_config(page_title="HHMA Sniper BTC Futures Max Pro", layout="wide")
st.title("🛡️ HHMA Renko Sniper Pro - 4H Institutional System (Ultimate Version)")

# ==========================================
# 💾 SISTEM MANAJEMEN ATURAN STANDAR (ANTI-RESET)
# ==========================================
# Definisikan pengaturan cetakan pabrik (Standard Defaults)
ATURAN_STANDAR = {
    "tf": "4 Jam (4h)", "src": "Close (Penutupan)", "lilin": 150,
    "hma": 16, "ema": 50, "rsi": 14, "vol": 30,
    "atr_l": 14, "atr_m": 3.5, "chand": 2.0,
    "modal": 1000.0, "lev": 10, "risk": 1.0,
    "tp1": 0.5, "tp2": 1.5, "fee": 0.04,
    "sesi": "Semua Sesi", "tg_token": "", "tg_id": ""
}

# Inisialisasi session state jika belum ada
if "config" not in st.session_state:
    st.session_state.config = ATURAN_STANDAR.copy()

# Tombol Reset ke Pengaturan Awal (Paling Atas Sidebar)
st.sidebar.header("🕹️ PANEL KENDALI UTAMA")
if st.sidebar.button("🔄 Kembali ke Pengaturan Jauh (Reset)"):
    st.session_state.config = ATURAN_STANDAR.copy()
    st.rerun()

# ==========================================
# ⚙️ FORM INPUT SIDEBAR (MENGGUNAKAN FORM AGAR TIDAK REFRESH OTOMATIS)
# ==========================================
with st.sidebar.form("form_pengaturan"):
    st.subheader("📊 Setelan Dasar Pasar")
    tf_pilihan = st.selectbox("Jangka Waktu (Timeframe):", options=["4 Jam (4h)", "1 Hari (Daily)", "1 Jam (1h)", "15 Menit (15m)"], index=["4 Jam (4h)", "1 Hari (Daily)", "1 Jam (1h)", "15 Menit (15m)"].index(st.session_state.config["tf"]))
    src_pilihan = st.selectbox("Sumber Data (Source):", options=["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"], index=["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"].index(st.session_state.config["src"]))
    jumlah_tampilan = st.number_input("Jumlah Lilin di Layar:", min_value=10, max_value=300, value=int(st.session_state.config["lilin"]), step=10)

    st.markdown("---")
    st.subheader("📈 Konfigurasi Akurasi Sniper")
    length_hma = st.number_input("Panjang HMA (Trend Utama):", min_value=2, max_value=50, value=int(st.session_state.config["hma"]), step=1)
    length_ema = st.number_input("Periode EMA (Pullback Zone):", min_value=5, max_value=200, value=int(st.session_state.config["ema"]), step=1)
    length_rsi = st.number_input("Periode RSI (Momentum):", min_value=5, max_value=30, value=int(st.session_state.config["rsi"]), step=1)
    length_vol_ma = st.number_input("Periode Volume MA (Saringan):", min_value=5, max_value=50, value=int(st.session_state.config["vol"]), step=1)

    st.markdown("---")
    st.subheader("🛡️ Proteksi Volatilitas (ATR & Chandelier)")
    length_atr = st.number_input("Periode ATR:", min_value=5, max_value=30, value=int(st.session_state.config["atr_l"]), step=1)
    atr_multiplier = st.number_input("Pengali ATR (Stop Loss Jauh):", min_value=1.0, max_value=4.5, value=float(st.session_state.config["atr_m"]), step=0.1)
    chandelier_mult = st.number_input("Chandelier Trailing Mult:", min_value=1.0, max_value=4.0, value=float(st.session_state.config["chand"]), step=0.1)

    st.markdown("---")
    st.subheader("⏱️ Filter Sesi Waktu Transaksi")
    sesi_pilihan = st.selectbox("Sesi Perdagangan Aktif:", options=["Semua Sesi", "Hanya London & NY (14:00 - 04:00 WIB)"], index=["Semua Sesi", "Hanya London & NY (14:00 - 04:00 WIB)"].index(st.session_state.config["sesi"]))

    st.markdown("---")
    st.subheader("🔥 Manajemen Risiko & Target")
    modal_awal = st.number_input("Margin Awal (\$ USD):", min_value=10.0, value=float(st.session_state.config["modal"]), step=100.0)
    leverage = st.number_input("Leverage (Multiplier):", min_value=1, max_value=50, value=int(st.session_state.config["lev"]), step=1)
    risiko_per_trade_pct = st.number_input("Risiko per Transaksi (% Modal):", min_value=0.5, max_value=10.0, value=float(st.session_state.config["risk"]), step=0.5)

    col_tp1, col_tp2 = st.columns(2)
    with col_tp1:
        tp1_ratio = st.number_input("Rasio TP 1:", min_value=0.3, max_value=2.0, value=float(st.session_state.config["tp1"]), step=0.1)
    with col_tp2:
        tp2_ratio = st.number_input("Rasio TP 2:", min_value=1.0, max_value=5.0, value=float(st.session_state.config["tp2"]), step=0.1)

    trading_fee_pct = st.number_input("Fee Bursa per Eksekusi (%):", min_value=0.0, max_value=1.0, value=float(st.session_state.config["fee"]), step=0.01)

    st.markdown("---")
    st.subheader("🤖 Integrasi Telegram")
    telegram_token = st.text_input("Telegram Bot Token:", value=st.session_state.config["tg_token"], type="password")
    telegram_chat_id = st.text_input("Telegram Chat ID:", value=st.session_state.config["tg_id"])

    # Tombol Simpan Manual agar Aturan Tidak Rusak / Senggol Berubah
    tombol_simpan = st.form_submit_button("💾 SIMPAN KONFIGURASI BARU")
    if tombol_simpan:
        st.session_state.config.update({
            "tf": tf_pilihan, "src": src_pilihan, "lilin": jumlah_tampilan,
            "hma": length_hma, "ema": length_ema, "rsi": length_rsi, "vol": length_vol_ma,
            "atr_l": length_atr, "atr_m": atr_multiplier, "chand": chandelier_mult,
            "modal": modal_awal, "lev": leverage, "risk": risiko_per_trade_pct,
            "tp1": tp1_ratio, "tp2": tp2_ratio, "fee": trading_fee_pct,
            "sesi": sesi_pilihan, "tg_token": telegram_token, "tg_id": telegram_chat_id
        })
        st.success("Konfigurasi disimpan! Memproses data...")
        st.rerun()

# ==========================================
# 📊 PROSES PENGOLAHAN DATA & INDIKATOR (MENGGUNAKAN AKURASI AMAN)
# ==========================================
c = st.session_state.config
src_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}
src_aktif = src_map[c["src"]]

interval_map = {"4 Jam (4h)": "4h", "1 Hari (Daily)": "1d", "1 Jam (1h)": "1h", "15 Menit (15m)": "15m"}
period_map = {"4 Jam (4h)": "180d", "1 Hari (Daily)": "730d", "1 Jam (1h)": "90d", "15 Menit (15m)": "30d"}

def send_telegram_alert(message):
    if c["tg_token"] and c["tg_id"]:
        url = f"https://telegram.org{c['tg_token']}/sendMessage"
        payload = {"chat_id": c["tg_id"], "text": message, "parse_mode": "Markdown"}
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
    df = get_crypto_data(period_map[c["tf"]], interval_map[c["tf"]])
    if df.empty:
        st.error("Gagal mengambil data dari Yahoo Finance.")
        st.stop()

    # Perhitungan Indikator Utama Berdasarkan Konfigurasi Tersimpan
    df['hma'] = ta.hma(df[src_aktif], length=c["hma"])
    df['ema'] = ta.ema(df['close'], length=c["ema"])
    df['rsi'] = ta.rsi(df['close'], length=c["rsi"])
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=c["atr_l"])
    df['vol_ma'] = ta.sma(df['volume'], length=c["vol"])
    
    df['highest_high'] = df['high'].rolling(window=22).max()
    df['lowest_low'] = df['low'].rolling(window=22).min()
    df['chandelier_long'] = df['highest_high'] - (df['atr'] * c["chand"])
    df['chandelier_short'] = df['lowest_low'] + (df['atr'] * c["chand"])

    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['is_red'] = df['hma'] < df['hma'].shift(1)

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    # Logika Filter Sinyal Ketat + Filter Sesi Jam Bursa
    for i in df.index:
        if i < max(c["hma"], c["ema"], c["atr_l"], c["vol"], c["rsi"], 22): continue
            
        # Pengecekan Filter Sesi Waktu (Jika diaktifkan)
        waktu_valid = True
        if c["sesi"] == "Hanya London & NY (14:00 - 04:00 WIB)":
            jam_bar = df.at[i, 'date'].time()
            # Sesi volatil tinggi London/NY berada di antara 07:00 UTC - 21:00 UTC (14:00 - 04:00 WIB)
            waktu_valid = (jam_bar >= time(7, 0) or jam_bar <= time(21, 0))

        is_pullback_long = (df.at[i, 'low'] <= df.at[i, 'ema'] * 1.002) and (df.at[i, 'close'] > df.at[i, 'ema'])
        is_pullback_short = (df.at[i, 'high'] >= df.at[i, 'ema'] * 0.998) and (df.at[i, 'close'] < df.at[i, 'ema'])
        
        rsi_safe_long = df.at[i, 'rsi'] < 55
        rsi_safe_short = df.at[i, 'rsi'] > 45
        volume_valid = df.at[i, 'volume'] > df.at[i, 'vol_ma']

        if df.at[i, 'is_green'] and is_pullback_long and rsi_safe_long and volume_valid and waktu_valid and last_signal != 1:
            df.at[i, 'buy_signal'] = True
            last_signal = 1
        elif df.at[i, 'is_red'] and is_pullback_short and rsi_safe_short and volume_valid and waktu_valid and last_signal != -1:
            df.at[i, 'sell_signal'] = True
            last_signal = -1

    df['display_buy'] = df['buy_signal']
    df['display_sell'] = df['sell_signal']

    # --- BANNER SINYAL REAL-TIME DI BAWAH JUDUL ---
    last_row = df.iloc[-1]
    if last_row['display_buy']:
        st.success("### 🟢 SINYAL AKTIF: LONG (BUY) SEKARANG! 🚀")
        st.info(f"**Parameter:** Entry: ${last_row['close']:,.2f} | Est. SL: ${last_row['close'] - (last_row['atr'] * c['atr_m']):,.2f}")
    elif last_row['display_sell']:
        st.error("### 🔴 SINYAL AKTIF: SHORT (SELL) SEKARANG! 📉")
        st.info(f"**Parameter:** Entry: ${last_row['close']:,.2f} | Est. SL: ${last_row['close'] + (last_row['atr'] * c['atr_m']):,.2f}")
    else:
        if last_row['is_green']: st.info("### ⚪ STATUS PASAR: WAIT / HOLD LONG (Tren Bullish Berjalan) 📈")
        else: st.warning("### ⚪ STATUS PASAR: WAIT / HOLD SHORT (Tren Bearish Berjalan) 📉")

    st.markdown("---")

    # ==========================================
    # ⚙️ SIMULATOR BACKTEST UTAMA + COMPOUNDING
    # ==========================================
    trades_list = []  
    active_trade = None
    current_equity = c["modal"]
    
    equity_timestamps = [df.loc[0, 'date']]
    equity_values = [c["modal"]]

    for i in df.index:
        if active_trade is not None and active_trade['Status'] == "Berjalan (Running)":
            if active_trade['Posisi'] == "🟢 LONG (Buy)":
                current_sl = max(active_trade['Harga SL (\$)'], df.at[i, 'chandelier_long'])
                if df.at[i, 'low'] <= current_sl:
                    p_close = current_sl
                    ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                    profit_raw = ((p_close - active_trade['Harga Entry (\$)']) / active_trade['Harga Entry (\$)']) * 100
                    profit_net = (profit_raw * c["lev"]) - (c["fee"] * 2)
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
                    profit_net = (profit_raw * c["lev"]) - (c["fee"] * 2)
                    laba_tp1 = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * 0.5
                    current_equity += laba_tp1
                    active_trade['TP1_Hit'] = True
                    active_trade['Laba_TP1_USD'] = laba_tp1
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)

                elif active_trade['TP1_Hit'] and df.at[i, 'high'] >= active_trade['Harga TP2 (\$)']:
                    p_close = active_trade['Harga TP2 (\$)']
                    profit_raw = ((p_close - active_trade['Harga Entry (\$)']) / active_trade['Harga Entry (\$)']) * 100
                    profit_net = (profit_raw * c["lev"]) - (c["fee"] * 2)
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
                    profit_net = (profit_raw * c["lev"]) - (c["fee"] * 2)
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
                    profit_net = (profit_raw * c["lev"]) - (c["fee"] * 2)
                    laba_tp1 = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * 0.5
                    current_equity += laba_tp1
                    active_trade['TP1_Hit'] = True
                    active_trade['Laba_TP1_USD'] = laba_tp1
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)

                elif active_trade['TP1_Hit'] and df.at[i, 'low'] <= active_trade['Harga TP2 (\$)']:
                    p_close = active_trade['Harga TP2 (\$)']
                    profit_raw = ((active_trade['Harga Entry (\$)'] - p_close) / active_trade['Harga Entry (\$)']) * 100
                    profit_net = (profit_raw * c["lev"]) - (c["fee"] * 2)
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

        # --- EKSEKUSI POSISI BARU DENGAN MODAL BERJALAN ---
        if df.at[i, 'display_buy']:
            if active_trade is not None:
                ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                p_close = df.at[i, 'close']
                profit_raw = ((p_close - active_trade['Harga Entry (\$)']) if active_trade['Posisi'] == "🟢 LONG (Buy)" else (active_trade['Harga Entry (\$)'] - p_close)) / active_trade['Harga Entry (\$)'] * 100
                profit_net = (profit_raw * c["lev"]) - (c["fee"] * 2)
                laba_usd = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * ratio_aktif
                current_equity += laba_usd
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                trades_list.append(active_trade)
                equity_timestamps.append(df.at[i, 'date'])
                equity_values.append(current_equity)
                active_trade = None

            sl_price = df.at[i, 'close'] - (df.at[i, 'atr'] * c["atr_m"])
            jarak_sl = abs(df.at[i, 'close'] - sl_price)
            tp1_price = df.at[i, 'close'] + (jarak_sl * c["tp1"])
            tp2_price = df.at[i, 'close'] + (jarak_sl * c["tp2"])
            
            jarak_sl_pct = jarak_sl / df.at[i, 'close']
            usd_risk = current_equity * (c["risk"] / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * c["lev"])), current_equity * 0.95)

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
                profit_net = (profit_raw * c["lev"]) - (c["fee"] * 2)
                laba_usd = (profit_net / 100) * active_trade['Margin Kunci (\$)'] * ratio_aktif
                current_equity += laba_usd
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                trades_list.append(active_trade)
                equity_timestamps.append(df.at[i, 'date'])
                equity_values.append(current_equity)
                active_trade = None

            sl_price = df.at[i, 'close'] + (df.at[i, 'atr'] * c["atr_m"])
            jarak_sl = abs(sl_price - df.at[i, 'close'])
            tp1_price = df.at[i, 'close'] - (jarak_sl * c["tp1"])
            tp2_price = df.at[i, 'close'] - (jarak_sl * c["tp2"])
            
            jarak_sl_pct = jarak_sl / df.at[i, 'close']
            usd_risk = current_equity * (c["risk"] / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * c["lev"])), current_equity * 0.95)

            active_trade = {
                'Posisi': "🔴 SHORT (Sell)", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry (\$)': round(df.at[i, 'close'], 2), 'Harga SL (\$)': round(sl_price, 2),
                'Harga TP1 (\$)': round(tp1_price, 2), 'Harga TP2 (\$)': round(tp2_price, 2),
                'Margin Kunci (\$)': round(margin_final, 2), 'Status': "Berjalan (Running)", 'TP1_Hit': False, 'Laba_TP1_USD': 0
            }
            if i == df.index[-1]:
                send_telegram_alert(f"🔴 *SNIPER SHORT BTC-USD*\nEntry: ${df.at[i, 'close']:.2f}\nSL: ${sl_price:.2f}")

    if active_trade is not None and active_trade not in trades_list:
        trades_list.append(active_trade)

    # ==========================================
    # 📉 KALKULASI METRIK & RENDERING DASHBOARD
    # ==========================================
    total_trades_done = [t for t in trades_list if t['Status'] != "Berjalan (Running)"]
    win_rate = 0.0; profit_factor = 0.0; total_profit_usd = 0.0; max_dd_pct = 0.0

    if len(total_trades_done) > 0:
        wins = [t for t in total_trades_done if t['Laba Bersih ($ USD)'] > 0]
        losses = [t for t in total_trades_done if t['Laba Bersih ($ USD)'] < 0]
        win_rate = (len(wins) / len(total_trades_done)) * 100
        total_profit_usd = sum([t['Laba Bersih ($ USD)'] for t in total_trades_done])
        
        gross_profit = sum([t['Laba Bersih ($ USD)'] for t in wins])
        gross_loss = abs(sum([t['Laba Bersih ($ USD)'] for t in losses]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0.0)

        equity_series = pd.Series(equity_values)
        cum_max = equity_series.cummax()
        max_dd_pct = abs(((equity_series - cum_max) / cum_max).min()) * 100

    current_price = df.iloc[-1]['close']
    
    st.markdown("### 📊 Hasil Evaluasi Kinerja Kuantitatif (Compound Growth)")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Harga Pasaran BTC", f"${current_price:,.2f}")
    m2.metric("Target Win Rate", f"{win_rate:.2f}%")
    m3.metric("Profit Factor", f"{profit_factor:.2f}" if profit_factor > 0 else "N/A")
    m4.metric("Max Drawdown (MDD)", f"{max_dd_pct:.2f}%")
    m5.metric("Compound ROI (%)", f"{(total_profit_usd/c['modal'])*100:.2f}%")
    m6.metric("Saldo Akhir Berjalan", f"${c['modal'] + total_profit_usd:,.2f}")

    # Render Subplot Utama
    df_plot = df.tail(int(c["lilin"]))
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.12, 0.12, 0.12, 0.64])
    fig.add_trace(go.Candlestick(x=df_plot['date'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name="Candlestick"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['hma'], line=dict(color='yellow', width=2), name="HMA Sniper"), row=1, col=1)
    fig.add_trace(
