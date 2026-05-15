import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests

st.set_page_config(page_title="HHMA Sniper BTC Futures Max Pro", layout="wide")
st.title("🛡️ HHMA Renko Sniper Pro - 4H Institutional System (Compound Active)")

# ==========================================
# ⚙️ PANEL SETELAN PARAMETER (SATU TEMPAT)
# ==========================================
st.sidebar.header("🕹️ PANEL KENDALI UTAMA")

# 1. Parameter Utama Pasar
tf_pilihan = st.sidebar.selectbox("Jangka Waktu (Timeframe):", options=["4 Jam (4h)", "1 Hari (Daily)", "1 Jam (1h)", "15 Menit (15m)"], index=0)
src_pilihan = st.sidebar.selectbox("Sumber Data (Source):", options=["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"], index=0)
jumlah_tampilan = st.sidebar.slider("Jumlah Lilin di Layar:", min_value=10, max_value=300, value=150, step=10)

st.sidebar.markdown("---")
st.sidebar.header("📈 Konfigurasi Akurasi Sniper")
length_hma = st.sidebar.slider("Panjang HMA (Trend Utama):", min_value=2, max_value=50, value=16, step=1)
length_ema = st.sidebar.slider("Periode EMA (Pullback Zone):", min_value=5, max_value=200, value=50, step=1)
length_rsi = st.sidebar.slider("Periode RSI (Momentum):", min_value=5, max_value=30, value=14, step=1)
length_vol_ma = st.sidebar.slider("Periode Volume MA (Saringan):", min_value=5, max_value=50, value=30, step=1)

st.sidebar.markdown("---")
st.sidebar.header("🛡️ Proteksi Volatilitas (ATR & Chandelier)")
length_atr = st.sidebar.slider("Periode ATR:", min_value=5, max_value=30, value=14, step=1)
atr_multiplier = st.sidebar.slider("Pengali ATR (Stop Loss Jauh):", min_value=1.0, max_value=4.5, value=3.5, step=0.1)
chandelier_mult = st.sidebar.slider("Chandelier Trailing Mult:", min_value=1.0, max_value=4.0, value=2.0, step=0.1)

st.sidebar.markdown("---")
st.sidebar.header("🔥 Manajemen Risiko & Target")
modal_awal = st.sidebar.number_input("Margin Awal ($ USD):", min_value=10, value=1000, step=100)
leverage = st.sidebar.slider("Leverage (Multiplier):", min_value=1, max_value=50, value=10, step=1)
risiko_per_trade_pct = st.sidebar.slider("Risiko per Transaksi (% Modal):", min_value=0.5, max_value=10.0, value=1.0, step=0.5, help="Risiko dihitung dinamis dari saldo berjalan saat itu (Compounding).")

col_tp1, col_tp2 = st.sidebar.columns(2)
with col_tp1:
    tp1_ratio = st.slider("Rasio TP 1:", min_value=0.3, max_value=2.0, value=0.5, step=0.1)
with col_tp2:
    tp2_ratio = st.slider("Rasio TP 2:", min_value=1.0, max_value=5.0, value=1.5, step=0.1)

trading_fee_pct = st.sidebar.number_input("Fee Bursa per Eksekusi (%):", min_value=0.0, max_value=1.0, value=0.04, step=0.01)

st.sidebar.markdown("---")
st.sidebar.header("🤖 Integrasi Telegram")
telegram_token = st.sidebar.text_input("Telegram Bot Token:", type="password")
telegram_chat_id = st.sidebar.text_input("Telegram Chat ID:")

# ==========================================
# 📊 PROSES PENGOLAHAN DATA & INDIKATOR
# ==========================================
src_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}
src_aktif = src_map[src_pilihan]

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
    df = get_crypto_data(period_map[tf_pilihan], interval_map[tf_pilihan])
    if df.empty:
        st.error("Gagal mengambil data dari Yahoo Finance.")
        st.stop()

    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    df['ema'] = ta.ema(df['close'], length=length_ema)
    df['rsi'] = ta.rsi(df['close'], length=length_rsi)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=length_atr)
    df['vol_ma'] = ta.sma(df['volume'], length=length_vol_ma)
    
    df['highest_high'] = df['high'].rolling(window=22).max()
    df['lowest_low'] = df['low'].rolling(window=22).min()
    df['chandelier_long'] = df['highest_high'] - (df['atr'] * chandelier_mult)
    df['chandelier_short'] = df['lowest_low'] + (df['atr'] * chandelier_mult)

    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['is_red'] = df['hma'] < df['hma'].shift(1)

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    for i in df.index:
        if i < max(length_hma, length_ema, length_atr, length_vol_ma, length_rsi, 22): continue
            
        is_pullback_long = (df.at[i, 'low'] <= df.at[i, 'ema'] * 1.002) and (df.at[i, 'close'] > df.at[i, 'ema'])
        is_pullback_short = (df.at[i, 'high'] >= df.at[i, 'ema'] * 0.998) and (df.at[i, 'close'] < df.at[i, 'ema'])
        
        rsi_safe_long = df.at[i, 'rsi'] < 55
        rsi_safe_short = df.at[i, 'rsi'] > 45
        volume_valid = df.at[i, 'volume'] > df.at[i, 'vol_ma']

        if df.at[i, 'is_green'] and is_pullback_long and rsi_safe_long and volume_valid and last_signal != 1:
            df.at[i, 'buy_signal'] = True
            last_signal = 1
        elif df.at[i, 'is_red'] and is_pullback_short and rsi_safe_short and volume_valid and last_signal != -1:
            df.at[i, 'sell_signal'] = True
            last_signal = -1

    df['display_buy'] = df['buy_signal']
    df['display_sell'] = df['sell_signal']

    # --- BANNER SINYAL REAL-TIME DI BAHAW JUDUL ---
    last_row = df.iloc[-1]
    if last_row['display_buy']:
        st.success("### 🟢 SINYAL AKTIF: LONG (BUY) SEKARANG! 🚀")
        st.info(f"**Parameter:** Entry: ${last_row['close']:,.2f} | Est. SL: ${last_row['close'] - (last_row['atr'] * atr_multiplier):,.2f}")
    elif last_row['display_sell']:
        st.error("### 🔴 SINYAL AKTIF: SHORT (SELL) SEKARANG! 📉")
        st.info(f"**Parameter:** Entry: ${last_row['close']:,.2f} | Est. SL: ${last_row['close'] + (last_row['atr'] * atr_multiplier):,.2f}")
    else:
        if last_row['is_green']: st.info("### ⚪ STATUS PASAR: WAIT / HOLD LONG (Tren Bullish Berjalan) 📈")
        else: st.warning("### ⚪ STATUS PASAR: WAIT / HOLD SHORT (Tren Bearish Berjalan) 📉")

    st.markdown("---")

    # ==========================================
    # ⚙️ SIMULATOR BACKTEST UTAMA + COMPOUNDING
    # ==========================================
    trades_list = []  
    active_trade = None
    current_equity = modal_awal
    
    equity_timestamps = [df.loc[0, 'date']]
    equity_values = [modal_awal]

    for i in df.index:
        if active_trade is not None and active_trade['Status'] == "Berjalan (Running)":
            if active_trade['Posisi'] == "🟢 LONG (Buy)":
                current_sl = max(active_trade['Harga SL ($)'], df.at[i, 'chandelier_long'])
                if df.at[i, 'low'] <= current_sl:
                    p_close = current_sl
                    ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                    profit_raw = ((p_close - active_trade['Harga Entry ($)']) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                    laba_usd = (profit_net / 100) * active_trade['Margin Kunci ($)'] * ratio_aktif
                    current_equity += laba_usd
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close ($)'] = round(p_close, 2)
                    active_trade['Status'] = "💥 Terkena Stop Loss/Trailing" if not active_trade['TP1_Hit'] else "🎯 TP1 + 💥 SL Sisa"
                    active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                    active_trade['Ekuitas Akhir ($)'] = round(current_equity, 2)
                    trades_list.append(active_trade)
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)
                    active_trade = None

                elif not active_trade['TP1_Hit'] and df.at[i, 'high'] >= active_trade['Harga TP1 ($)']:
                    p_close = active_trade['Harga TP1 ($)']
                    profit_raw = ((p_close - active_trade['Harga Entry ($)']) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                    laba_tp1 = (profit_net / 100) * active_trade['Margin Kunci ($)'] * 0.5
                    current_equity += laba_tp1
                    active_trade['TP1_Hit'] = True
                    active_trade['Laba_TP1_USD'] = laba_tp1
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)

                elif active_trade['TP1_Hit'] and df.at[i, 'high'] >= active_trade['Harga TP2 ($)']:
                    p_close = active_trade['Harga TP2 ($)']
                    profit_raw = ((p_close - active_trade['Harga Entry ($)']) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                    laba_tp2 = (profit_net / 100) * active_trade['Margin Kunci ($)'] * 0.5
                    current_equity += laba_tp2
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close ($)'] = round(p_close, 2)
                    active_trade['Status'] = "🎯 Target Tercapai Penuh (TP1+TP2)"
                    active_trade['Laba Bersih ($ USD)'] = round(active_trade['Laba_TP1_USD'] + laba_tp2, 2)
                    active_trade['Ekuitas Akhir ($)'] = round(current_equity, 2)
                    trades_list.append(active_trade)
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)
                    active_trade = None

            elif active_trade is not None and active_trade['Posisi'] == "🔴 SHORT (Sell)":
                current_sl = min(active_trade['Harga SL ($)'], df.at[i, 'chandelier_short'])
                if df.at[i, 'high'] >= current_sl:
                    p_close = current_sl
                    ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                    profit_raw = ((active_trade['Harga Entry ($)'] - p_close) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                    laba_usd = (profit_net / 100) * active_trade['Margin Kunci ($)'] * ratio_aktif
                    current_equity += laba_usd
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close ($)'] = round(p_close, 2)
                    active_trade['Status'] = "💥 Terkena Stop Loss/Trailing" if not active_trade['TP1_Hit'] else "🎯 TP1 + 💥 SL Sisa"
                    active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                    active_trade['Ekuitas Akhir ($)'] = round(current_equity, 2)
                    trades_list.append(active_trade)
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)
                    active_trade = None

                elif not active_trade['TP1_Hit'] and df.at[i, 'low'] <= active_trade['Harga TP1 ($)']:
                    p_close = active_trade['Harga TP1 ($)']
                    profit_raw = ((active_trade['Harga Entry ($)'] - p_close) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                    laba_tp1 = (profit_net / 100) * active_trade['Margin Kunci ($)'] * 0.5
                    current_equity += laba_tp1
                    active_trade['TP1_Hit'] = True
                    active_trade['Laba_TP1_USD'] = laba_tp1
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)

                elif active_trade['TP1_Hit'] and df.at[i, 'low'] <= active_trade['Harga TP2 ($)']:
                    p_close = active_trade['Harga TP2 ($)']
                    profit_raw = ((active_trade['Harga Entry ($)'] - p_close) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                    laba_tp2 = (profit_net / 100) * active_trade['Margin Kunci ($)'] * 0.5
                    current_equity += laba_tp2
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close ($)'] = round(p_close, 2)
                    active_trade['Status'] = "🎯 Target Tercapai Penuh (TP1+TP2)"
                    active_trade['Laba Bersih ($ USD)'] = round(active_trade['Laba_TP1_USD'] + laba_tp2, 2)
                    active_trade['Ekuitas Akhir ($)'] = round(current_equity, 2)
                    trades_list.append(active_trade)
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)
                    active_trade = None

        # --- EKSEKUSI POSISI BARU DENGAN MODAL BERJALAN (COMPOUNDING) ---
        if df.at[i, 'display_buy']:
            if active_trade is not None:
                ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                p_close = df.at[i, 'close']
                profit_raw = ((p_close - active_trade['Harga Entry ($)']) if active_trade['Posisi'] == "🟢 LONG (Buy)" else (active_trade['Harga Entry ($)'] - p_close)) / active_trade['Harga Entry ($)'] * 100
                profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                laba_usd = (profit_net / 100) * active_trade['Margin Kunci ($)'] * ratio_aktif
                current_equity += laba_usd
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                trades_list.append(active_trade)
                equity_timestamps.append(df.at[i, 'date'])
                equity_values.append(current_equity)
                active_trade = None

            sl_price = df.at[i, 'close'] - (df.at[i, 'atr'] * atr_multiplier)
            jarak_sl = abs(df.at[i, 'close'] - sl_price)
            tp1_price = df.at[i, 'close'] + (jarak_sl * tp1_ratio)
            tp2_price = df.at[i, 'close'] + (jarak_sl * tp2_ratio)
            
            jarak_sl_pct = jarak_sl / df.at[i, 'close']
            # KRUSIAL: Nilai usd_risk kini dihitung otomatis dari 'current_equity' bukan 'modal_awal'
            usd_risk = current_equity * (risiko_per_trade_pct / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * leverage)), current_equity * 0.95)

            active_trade = {
                'Posisi': "🟢 LONG (Buy)", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2), 'Harga SL ($)': round(sl_price, 2),
                'Harga TP1 ($)': round(tp1_price, 2), 'Harga TP2 ($)': round(tp2_price, 2),
                'Margin Kunci ($)': round(margin_final, 2), 'Status': "Berjalan (Running)", 'TP1_Hit': False, 'Laba_TP1_USD': 0
            }
            if i == df.index[-1]:
                send_telegram_alert(f"🟢 *SNIPER LONG BTC-USD*\nEntry: ${df.at[i, 'close']:.2f}\nSL: ${sl_price:.2f}")

        elif df.at[i, 'display_sell']:
            if active_trade is not None:
                ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                p_close = df.at[i, 'close']
                profit_raw = ((p_close - active_trade['Harga Entry ($)']) if active_trade['Posisi'] == "🟢 LONG (Buy)" else (active_trade['Harga Entry ($)'] - p_close)) / active_trade['Harga Entry ($)'] * 100
                profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                laba_usd = (profit_net / 100) * active_trade['Margin Kunci ($)'] * ratio_aktif
                current_equity += laba_usd
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                trades_list.append(active_trade)
                equity_timestamps.append(df.at[i, 'date'])
                equity_values.append(current_equity)
                active_trade = None

            sl_price = df.at[i, 'close'] + (df.at[i, 'atr'] * atr_multiplier)
            jarak_sl = abs(sl_price - df.at[i, 'close'])
            tp1_price = df.at[i, 'close'] - (jarak_sl * tp1_ratio)
            tp2_price = df.at[i, 'close'] - (jarak_sl * tp2_ratio)
            
            jarak_sl_pct = jarak_sl / df.at[i, 'close']
            # KRUSIAL: Nilai usd_risk kini dihitung otomatis dari 'current_equity' bukan 'modal_awal'
            usd_risk = current_equity * (risiko_per_trade_pct / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * leverage)), current_equity * 0.95)

            active_trade = {
                'Posisi': "🔴 SHORT (Sell)", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2), 'Harga SL ($)': round(sl_price, 2),
                'Harga TP1 ($)': round(tp1_price, 2), 'Harga TP2 ($)': round(tp2_price, 2),
                'Margin Kunci ($)': round(margin_final, 2), 'Status': "Berjalan (Running)", 'TP1_Hit': False, 'Laba_TP1_USD': 0
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
    m5.metric("Compound ROI (%)", f"{(total_profit_usd/modal_awal)*100:.2f}%", help="Pertumbuhan modal total menggunakan efek gulung keuntungan.")
    m6.metric("Saldo Akhir Berjalan", f"${modal_awal + total_profit_usd:,.2f}")

    # Render Subplot Utama
    df_plot = df.tail(jumlah_tampilan)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.12, 0.12, 0.12, 0.64])
    fig.add_trace(go.Candlestick(x=df_plot['date'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name="Candlestick"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['hma'], line=dict(color='yellow', width=2), name="HMA Sniper"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ema'], line=dict(color='cyan', width=1.5, dash='dash'), name="EMA Filter"), row=1, col=1)

    buys = df_plot[df_plot['display_buy']]; sells = df_plot[df_plot['display_sell']]
    fig.add_trace(go.Scatter(x=buys['date'], y=buys['close'], mode='markers', marker=dict(symbol='triangle-up', size=12, color='lime'), name="LONG"), row=1, col=1)
    fig.add_trace(go.Scatter(x=sells['date'], y=sells['close'], mode='markers', marker=dict(symbol='triangle-down', size=12, color='red'), name="SHORT"), row=1, col=1)

    fig.add_trace(go.Bar(x=df_plot['date'], y=df_plot['volume'], name="Volume", marker_color='orange'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['vol_ma'], line=dict(color='white', width=1), name="Volume MA"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['rsi'], line=dict(color='green', width=1.5), name="RSI"), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1); fig.add_hline(y=30, line_dash="dash", line_color="lime", row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['atr'], line=dict(color='magenta', width=1.5), name="ATR"), row=4, col=1)
    
    fig.update_layout(height=800, xaxis_rangeslider_visible=False, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # Render Kurva Ekuitas
    st.markdown("### 📈 Kurva Pertumbuhan Ekuitas Modal (Equity Curve)")
    if len(equity_values) > 1:
        df_equity = pd.DataFrame({"Waktu": equity_timestamps, "Modal ($ USD)": equity_values})
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=df_equity['Waktu'], y=df_equity['Modal ($ USD)'], mode='lines+markers', line=dict(color='lime', width=2.5), fill='tozeroy', fillcolor='rgba(0, 255, 0, 0.1)', name="Ekuitas"))
        fig_equity.update_layout(height=350, template="plotly_dark", xaxis_title="Waktu", yaxis_title="Saldo ($ USD)")
        st.plotly_chart(fig_equity, use_container_width=True)

    if trades_list:
        st.markdown("### 🧾 Log Resmi Eksekusi Kontrak")
        df_trades = pd.DataFrame(trades_list)
        st.dataframe(df_trades.drop(columns=['TP1_Hit', 'Laba_TP1_USD'], errors='ignore').iloc[::-1], use_container_width=True)

except Exception as e:
    st.error(f"Eror Pemrosesan Logika: {e}")
