import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests
import numpy as np

st.set_page_config(page_title="HHMA Renko BTC Futures Max Pro", layout="wide")
st.title("🛡️ HHMA Renko + EMA Pullback + RSI + Auto Position Sizing + Partial TP & MDD")

# --- SISTEM PENGUNCI SETELAN ANTI REFRESH ---
query_params = st.query_params
default_tf = query_params.get("tf", "5 Menit (5m)")  
default_src = query_params.get("src", "Close (Penutupan)")
try:
    default_len = int(query_params.get("len", "5"))  
except:
    default_len = 5

# Panel Menu Pengaturan Utama
col1, col2, col3, col4 = st.columns(4)
with col1:
    tf_options = ["1 Hari (Daily)", "4 Jam (4h)", "1 Jam (1h)", "15 Menit (15m)", "5 Menit (5m)", "1 Menit (1m)"]
    tf_index = tf_options.index(default_tf) if default_tf in tf_options else 4
    tf_pilihan = st.selectbox("Jangka Waktu (Timeframe):", options=tf_options, index=tf_index)
with col2:
    src_options = ["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"]
    src_index = src_options.index(default_src) if default_src in src_options else 0
    src_pilihan = st.selectbox("Sumber Data (Source):", options=src_options, index=src_index)
with col3:
    length_hma = st.slider("Panjang HMA (Length):", min_value=2, max_value=50, value=default_len, step=1)
with col4:
    jumlah_tampilan = st.slider("Jumlah Lilin di Layar:", min_value=10, max_value=300, value=150, step=10)

# --- PANEL SIDEBAR CONFIG INDIKATOR TAMBAHAN ---
st.sidebar.header("⚙️ Konfigurasi Filter Akurasi")
length_ema = st.sidebar.slider("Periode EMA Pullback:", min_value=5, max_value=200, value=21, step=1)
length_rsi = st.sidebar.slider("Periode RSI Momentum:", min_value=5, max_value=30, value=14, step=1)
length_atr = st.sidebar.slider("Periode ATR Volatilitas:", min_value=5, max_value=30, value=14, step=1)
atr_multiplier = st.sidebar.slider("Pengali ATR (Stop Loss):", min_value=1.0, max_value=3.5, value=2.0, step=0.1)
length_vol_ma = st.sidebar.slider("Periode Volume MA:", min_value=5, max_value=50, value=20, step=1)

# --- PANEL SIDEBAR MANAJEMEN RISIKO & INTEGRASI ---
st.sidebar.markdown("---")
st.sidebar.header("🔥 Manajemen Risiko & Modal")
modal_awal = st.sidebar.number_input("Margin Awal ($ USD):", min_value=10, value=1000, step=100)
leverage = st.sidebar.slider("Leverage (Multiplier):", min_value=1, max_value=50, value=10, step=1)
risiko_per_trade_pct = st.sidebar.slider("Risiko per Transaksi (% Modal):", min_value=0.5, max_value=10.0, value=2.0, step=0.5)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Target Profit Parsial (Risk:Reward)")
tp1_ratio = st.sidebar.slider("Rasio TP 1 (Tutup 50% Posisi):", min_value=0.5, max_value=3.0, value=1.0, step=0.1)
tp2_ratio = st.sidebar.slider("Rasio TP 2 (Tutup Sisa Posisi):", min_value=1.0, max_value=5.0, value=2.0, step=0.1)

st.sidebar.markdown("---")
st.sidebar.header("🧾 Biaya Transaksi Futures")
trading_fee_pct = st.sidebar.number_input("Fee Bursa per Eksekusi (%):", min_value=0.0, max_value=1.0, value=0.05, step=0.01)

st.sidebar.markdown("---")
st.sidebar.header("🤖 Integrasi Bot Telegram")
telegram_token = st.sidebar.text_input("Telegram Bot Token:", type="password")
telegram_chat_id = st.sidebar.text_input("Telegram Chat ID:")

def send_telegram_alert(message):
    if telegram_token and telegram_chat_id:
        url = f"https://telegram.org{telegram_token}/sendMessage"
        payload = {"chat_id": telegram_chat_id, "text": message, "parse_mode": "Markdown"}
        try: requests.post(url, json=payload, timeout=5)
        except: pass

st.query_params.update(tf=tf_pilihan, src=src_pilihan, len=str(length_hma))

src_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}
src_aktif = src_map[src_pilihan]

interval_map = {"1 Hari (Daily)": "1d", "4 Jam (4h)": "4h", "1 Jam (1h)": "1h", "15 Menit (15m)": "15m", "5 Menit (5m)": "5m", "1 Menit (1m)": "1m"}
period_map = {"1 Hari (Daily)": "730d", "4 Jam (4h)": "180d", "1 Jam (1h)": "90d", "15 Menit (15m)": "30d", "5 Menit (5m)": "30d", "1 Menit (1m)": "7d"}

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
        st.error("Gagal mengambil data.")
        st.stop()

    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    df['ema'] = ta.ema(df['close'], length=length_ema)
    df['rsi'] = ta.rsi(df['close'], length=length_rsi)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=length_atr)
    df['vol_ma'] = ta.sma(df['volume'], length=length_vol_ma)
    
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['is_red'] = df['hma'] < df['hma'].shift(1)

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    for i in df.index:
        if i < max(length_hma, length_ema, length_atr, length_vol_ma, length_rsi): continue
            
        is_pullback_long = (df.at[i, 'low'] <= df.at[i, 'ema'] * 1.002) and (df.at[i, 'close'] > df.at[i, 'ema'])
        is_pullback_short = (df.at[i, 'high'] >= df.at[i, 'ema'] * 0.998) and (df.at[i, 'close'] < df.at[i, 'ema'])
        rsi_safe_long = df.at[i, 'rsi'] < 65
        rsi_safe_short = df.at[i, 'rsi'] > 35
        volume_valid = df.at[i, 'volume'] > df.at[i, 'vol_ma']

        if df.at[i, 'is_green'] and is_pullback_long and rsi_safe_long and volume_valid and last_signal != 1:
            df.at[i, 'buy_signal'] = True
            last_signal = 1
        elif df.at[i, 'is_red'] and is_pullback_short and rsi_safe_short and volume_valid and last_signal != -1:
            df.at[i, 'sell_signal'] = True
            last_signal = -1

    df['display_buy'] = df['buy_signal']
    df['display_sell'] = df['sell_signal']

    # --- SIMULATOR BACKTEST MESIN FUTURES + PARTIAL TAKE PROFIT ---
    trades_list = []  
    active_trade = None
    current_equity = modal_awal
    
    equity_timestamps = [df.iloc[0]['date']]
    equity_values = [modal_awal]

    for i in df.index:
        if active_trade is not None and active_trade['Status'] == "Berjalan (Running)":
            if active_trade['Posisi'] == "🟢 LONG (Buy)":
                if df.at[i, 'low'] <= active_trade['Harga SL ($)']:
                    p_close = active_trade['Harga SL ($)']
                    ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                    profit_raw = ((p_close - active_trade['Harga Entry ($)']) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                    laba_usd = (profit_net / 100) * active_trade['Margin Kunci ($)'] * ratio_aktif
                    current_equity += laba_usd
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close ($)'] = round(p_close, 2)
                    active_trade['Status'] = "💥 Terkena Stop Loss" if not active_trade['TP1_Hit'] else "🎯 TP1 + 💥 SL Sisa"
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
                if df.at[i, 'high'] >= active_trade['Harga SL ($)']:
                    p_close = active_trade['Harga SL ($)']
                    ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                    profit_raw = ((active_trade['Harga Entry ($)'] - p_close) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * leverage) - (trading_fee_pct * 2)
                    laba_usd = (profit_net / 100) * active_trade['Margin Kunci ($)'] * ratio_aktif
                    current_equity += laba_usd
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close ($)'] = round(p_close, 2)
                    active_trade['Status'] = "💥 Terkena Stop Loss" if not active_trade['TP1_Hit'] else "🎯 TP1 + 💥 SL Sisa"
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
            usd_risk = current_equity * (risiko_per_trade_pct / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * leverage)), current_equity * 0.95)

            active_trade = {
                'Posisi': "🟢 LONG (Buy)", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2), 'Harga SL ($)': round(sl_price, 2),
                'Harga TP1 ($)': round(tp1_price, 2), 'Harga TP2 ($)': round(tp2_price, 2),
                'Margin Kunci ($)': round(margin_final, 2), 'Status': "Berjalan (Running)", 'TP1_Hit': False, 'Laba_TP1_USD': 0
            }
            if i == df.index[-1]:
                send_telegram_alert(f"🟢 *SINYAL LONG BTC-USD*\nEntry: ${df.at[i, 'close']:.2f}\nSL: ${sl_price:.2f}\nTP1: ${tp1_price:.2f}\nTP2: ${tp2_price:.2f}")

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
            usd_risk = current_equity * (risiko_per_trade_pct / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * leverage)), current_equity * 0.95)

            active_trade = {
                'Posisi': "🔴 SHORT (Sell)", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2), 'Harga SL ($)': round(sl_price, 2),
                'Harga TP1 ($)': round(tp1_price, 2), 'Harga TP2 ($)': round(tp2_price, 2),
                'Margin Kunci ($)': round(margin_final, 2), 'Status': "Berjalan (Running)", 'TP1_Hit': False, 'Laba_TP1_USD': 0
            }
            if i == df.index[-1]:
                send_telegram_alert(f"🔴 *SINYAL SHORT BTC-USD*\nEntry: ${df.at[i, 'close']:.2f}\nSL: ${sl_price:.2f}\nTP1: ${tp1_price:.2f}\nTP2: ${tp2_price:.2f}")

    if active_trade is not None and active_trade not in trades_list:
        trades_list.append(active_trade)

    # --- REKAP METRIK KINERJA + FORMULA DRAWDOWN ---
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

        # --- HITUNG MAXIMUM DRAWDOWN ---
        equity_series = pd.Series(equity_values)
        cum_max = equity_series.cummax()
        drawdowns = (equity_series - cum_max) / cum_max
        max_dd_pct = abs(drawdowns.min()) * 100

    current_price = df.iloc[-1]['close']
    
    # --- DASHBOARD METRIK + NEW SUBPLOT MDD ---
    st.markdown("### 📊 Ringkasan Kinerja Sistem Pro (Kombinasi 4 Indikator + MDD)")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Harga BTC", f"${current_price:,.2f}")
    m2.metric("Win Rate", f"{win_rate:.2f}%")
    m3.metric("Profit Factor", f"{profit_factor:.2f}" if profit_factor > 0 else "N/A")
    m4.metric("Max Drawdown (MDD)", f"{max_dd_pct:.2f}%", help="Penurunan modal terbesar hulu ke hilir. Amannya di bawah < 15-20%")
    m5.metric("Akumulasi ROI", f"{(total_profit_usd/modal_awal)*100:.2f}%")
    m6.metric("Saldo Akhir", f"${modal_awal + total_profit_usd:,.2f}")

    # --- GRAFIK CHART UTAMA ---
    df_plot = df.tail(jumlah_tampilan)
    fig = make_subplots(rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.03, row_width=[0.12, 0.12, 0.12, 0.64])
    fig.add_trace(go.Candlestick(x=df_plot['date'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name="Candlestick"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['hma'], line=dict(color='yellow', width=2), name="HMA Trend"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ema'], line=dict(color='cyan', width=1.5, dash='dash'), name="EMA Pullback"), row=1, col=1)

    buys = df_plot[df_plot['display_buy']]; sells = df_plot[df_plot['display_sell']]
    fig.add_trace(go.Scatter(x=buys['date'], y=buys['close'], mode='markers', marker=dict(symbol='triangle-up', size=12, color='lime'), name="Sinyal LONG"), row=1, col=1)
    fig.add_trace(go.Scatter(x=sells['date'], y=sells['close'], mode='markers', marker=dict(symbol='triangle-down', size=12, color='red'), name="Sinyal SHORT"), row=1, col=1)

    fig.add_trace(go.Bar(x=df_plot['date'], y=df_plot['volume'], name="Volume", marker_color='orange'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['vol_ma'], line=dict(color='white', width=1), name="Volume MA"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['rsi'], line=dict(color='green', width=1.5), name="RSI"), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1); fig.add_hline(y=30, line_dash="dash", line_color="lime", row=3, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['atr'], line=dict(color='magenta', width=1.5), name="ATR"), row=4, col=1)
    fig.update_layout(height=800, xaxis_rangeslider_visible=False, theme="dark")
    st.plotly_chart(fig, use_container_width=True)

    # --- GRAFIK KURVA EKUITAS MODAL ---
    st.markdown("### 📈 Kurva Pertumbuhan Ekuitas Modal (Equity Curve)")
    if len(equity_values) > 1:
        df_equity = pd.DataFrame({"Waktu": equity_timestamps, "Modal ($ USD)": equity_values})
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=df_equity['Waktu'], y=df_equity['Modal ($ USD)'], mode='lines+markers', line=dict(color='lime', width=2.5), fill='tozeroy', fillcolor='rgba(0, 255, 0, 0.1)', name="Ekuitas"))
        fig_equity.update_layout(height=350, theme="dark", xaxis_title="Waktu", yaxis_title="Saldo ($ USD)")
        st.plotly_chart(fig_equity, use_container_width=True)

    # --- TABEL HISTORI LOG EKSEKUSI ---
    if trades_list:
        st.markdown("### 🧾 Log Transaksi Futures Resmi (Dengan Riwayat TP Parsial)")
        df_trades = pd.DataFrame(trades_list)
        df_trades_clean = df_trades.drop(columns=['TP1_Hit', 'Laba_TP1_USD'], errors='ignore')
        st.dataframe(df_trades_clean.iloc[::-1], use_container_width=True)

except Exception as e:
    st.error(f"Terjadi kesalahan sistem pengolahan: {e}")
