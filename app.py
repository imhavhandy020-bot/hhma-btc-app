import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import requests

st.set_page_config(page_title="HHMA Renko BTC Futures Max Pro", layout="wide")
st.title("🛡️ HHMA Renko + EMA Pullback + RSI + Auto Position Sizing + CKS Filter")

# ==============================================================================
# === PUSAT SETELAN PARAMETER (UBAH ANGKA DI SINI UNTUK OPTIMALISASI AKURASI) ===
# ==============================================================================
SETELAN_TIMEFRAME = "4 Jam (4h)"       # Pilihan: "1 Hari (Daily)", "4 Jam (4h)", "1 Jam (1h)", "15 Menit (15m)", "5 Menit (5m)", "1 Menit (1m)"
SETELAN_SOURCE = "Close (Penutupan)"   # Pilihan: "Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"
JUMLAH_LILIN_LAYAR = 150               # Jumlah bar lilin yang ditampilkan di grafik

# 1. Parameter Indikator Utama & Pendukung
P_HMA_LENGTH = 16                      # Periode tren utama HMA
P_EMA_PULLBACK = 50                    # Periode filter pantulan harga EMA
P_RSI_MOMENTUM = 14                    # Periode RSI untuk mengukur kejenuhan pasar
P_ATR_VOLATILITAS = 14                 # Periode ATR untuk mengukur jarak fluktuasi
P_ATR_MULTIPLIER = 3.5                 # Pengali jarak Stop Loss ATR (Gunakan 3.0 - 3.5 untuk akurasi tinggi)
P_VOLUME_MA = 30                       # Periode Moving Average Volume untuk menyaring likuiditas

# 2. Tambahan Indikator Premium: Chande Kroll Stop (CKS) Filter
P_CKS_P = 10                           # Periode pelacakan harga tertinggi/terendah CKS
P_CKS_X = 3                            # Pengali ATR untuk garis batas CKS
P_CKS_Q = 9                            # Periode pemulusan (smoothing) garis CKS

# 3. Manajemen Risiko & Target Profit Parsial
MODAL_AWAL = 1000                      # Margin awal akun ($ USD)
LEVERAGE = 10                          # Pengali daya beli kontrak Futures (Multiplier)
RISIKO_PER_TRADE_PCT = 1.0             # Batas toleransi kerugian nominal (% dari modal akun)
RASIO_TP1 = 0.5                        # Target profit 1 (Tutup cepat 50% posisi untuk amankan modal)
RASIO_TP2 = 2.0                        # Target profit 2 (Membiarkan sisa posisi mengejar tren besar)

# 4. Biaya Transaksi & Integrasi Notifikasi
TRADING_FEE_PCT = 0.05                 # Estimasi fee bursa per eksekusi (%)
TELEGRAM_TOKEN = ""                    # Masukkan token bot Telegram Anda di sini
TELEGRAM_CHAT_ID = ""                  # Masukkan chat ID Telegram Anda di sini
# ==============================================================================

# --- LOGIKA SYSTEM INTEGRASI ---
def send_telegram_alert(message):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://telegram.org{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
        try: requests.post(url, json=payload, timeout=5)
        except: pass

src_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}
src_aktif = src_map[SETELAN_SOURCE]

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
    df = get_crypto_data(period_map[SETELAN_TIMEFRAME], interval_map[SETELAN_TIMEFRAME])
    if df.empty:
        st.error("Gagal mengambil data dari Yahoo Finance.")
        st.stop()

    # --- KALKULATOR INDIKATOR ---
    df['hma'] = ta.hma(df[src_aktif], length=P_HMA_LENGTH)
    df['ema'] = ta.ema(df['close'], length=P_EMA_PULLBACK)
    df['rsi'] = ta.rsi(df['close'], length=P_ROM_MOMENTUM if 'P_ROM_MOMENTUM' in locals() else P_RSI_MOMENTUM)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=P_ATR_VOLATILITAS)
    df['vol_ma'] = ta.sma(df['volume'], length=P_VOLUME_MA)
    
    # Perhitungan Chande Kroll Stop (CKS) Manual sebagai filter konfirmasi volatilitas
    df['atr_cks'] = ta.atr(df['high'], df['low'], df['close'], length=P_CKS_P)
    df['highest_p'] = df['high'].rolling(window=P_CKS_P).max()
    df['lowest_p'] = df['low'].rolling(window=P_CKS_P).min()
    
    df['cks_stop_long_raw'] = df['highest_p'] - (P_CKS_X * df['atr_cks'])
    df['cks_stop_short_raw'] = df['lowest_p'] + (P_CKS_X * df['atr_cks'])
    
    df['cks_long'] = df['cks_stop_long_raw'].rolling(window=P_CKS_Q).max()
    df['cks_short'] = df['cks_stop_short_raw'].rolling(window=P_CKS_Q).min()

    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['is_red'] = df['hma'] < df['hma'].shift(1)

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    # --- LOGIKA ALGORITMA FILTER AKURASI TINGGI ---
    for i in df.index:
        limit_idx = max(P_HMA_LENGTH, P_EMA_PULLBACK, P_ATR_VOLATILITAS, P_VOLUME_MA, P_CKS_P + P_CKS_Q)
        if i < limit_idx: continue
            
        is_pullback_long = (df.at[i, 'low'] <= df.at[i, 'ema'] * 1.002) and (df.at[i, 'close'] > df.at[i, 'ema'])
        is_pullback_short = (df.at[i, 'high'] >= df.at[i, 'ema'] * 0.998) and (df.at[i, 'close'] < df.at[i, 'ema'])
        rsi_safe_long = df.at[i, 'rsi'] < 55
        rsi_safe_short = df.at[i, 'rsi'] > 45
        volume_valid = df.at[i, 'volume'] > df.at[i, 'vol_ma']
        
        # Filter Tambahan CKS: Harga wajib menembus batas jenuh volatilitas
        cks_filter_long = df.at[i, 'close'] > df.at[i, 'cks_long']
        cks_filter_short = df.at[i, 'close'] < df.at[i, 'cks_short']

        if df.at[i, 'is_green'] and is_pullback_long and rsi_safe_long and volume_valid and cks_filter_long and last_signal != 1:
            df.at[i, 'buy_signal'] = True
            last_signal = 1
        elif df.at[i, 'is_red'] and is_pullback_short and rsi_safe_short and volume_valid and cks_filter_short and last_signal != -1:
            df.at[i, 'sell_signal'] = True
            last_signal = -1

    df['display_buy'] = df['buy_signal']
    df['display_sell'] = df['sell_signal']

    # --- SIMULATOR BACKTEST MESIN FUTURES ---
    trades_list = []  
    active_trade = None
    current_equity = MODAL_AWAL
    equity_timestamps = [df.iloc['date']]
    equity_values = [MODAL_AWAL]

    for i in df.index:
        if active_trade is not None and active_trade['Status'] == "Berjalan (Running)":
            if active_trade['Posisi'] == "🟢 LONG (Buy)":
                if df.at[i, 'low'] <= active_trade['Harga SL ($)']:
                    p_close = active_trade['Harga SL ($)']
                    ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                    profit_raw = ((p_close - active_trade['Harga Entry ($)']) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * LEVERAGE) - (TRADING_FEE_PCT * 2)
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
                    profit_net = (profit_raw * LEVERAGE) - (TRADING_FEE_PCT * 2)
                    laba_tp1 = (profit_net / 100) * active_trade['Margin Kunci ($)'] * 0.5
                    current_equity += laba_tp1
                    active_trade['TP1_Hit'] = True
                    active_trade['Laba_TP1_USD'] = laba_tp1
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)

                elif active_trade['TP1_Hit'] and df.at[i, 'high'] >= active_trade['Harga TP2 ($)']:
                    p_close = active_trade['Harga TP2 ($)']
                    profit_raw = ((p_close - active_trade['Harga Entry ($)']) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * LEVERAGE) - (TRADING_FEE_PCT * 2)
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
                    profit_net = (profit_raw * LEVERAGE) - (TRADING_FEE_PCT * 2)
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
                    profit_net = (profit_raw * LEVERAGE) - (TRADING_FEE_PCT * 2)
                    laba_tp1 = (profit_net / 100) * active_trade['Margin Kunci ($)'] * 0.5
                    current_equity += laba_tp1
                    active_trade['TP1_Hit'] = True
                    active_trade['Laba_TP1_USD'] = laba_tp1
                    equity_timestamps.append(df.at[i, 'date'])
                    equity_values.append(current_equity)

                elif active_trade['TP1_Hit'] and df.at[i, 'low'] <= active_trade['Harga TP2 ($)']:
                    p_close = active_trade['Harga TP2 ($)']
                    profit_raw = ((active_trade['Harga Entry ($)'] - p_close) / active_trade['Harga Entry ($)']) * 100
                    profit_net = (profit_raw * LEVERAGE) - (TRADING_FEE_PCT * 2)
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
                profit_net = (profit_raw * LEVERAGE) - (TRADING_FEE_PCT * 2)
                laba_usd = (profit_net / 100) * active_trade['Margin Kunci ($)'] * ratio_aktif
                current_equity += laba_usd
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                trades_list.append(active_trade)
                equity_timestamps.append(df.at[i, 'date'])
                equity_values.append(current_equity)
                active_trade = None

            sl_price = df.at[i, 'close'] - (df.at[i, 'atr'] * P_ATR_MULTIPLIER)
            jarak_sl = abs(df.at[i, 'close'] - sl_price)
            tp1_price = df.at[i, 'close'] + (jarak_sl * RASIO_TP1)
            tp2_price = df.at[i, 'close'] + (jarak_sl * RASIO_TP2)
            
            jarak_sl_pct = jarak_sl / df.at[i, 'close']
            usd_risk = current_equity * (RISIKO_PER_TRADE_PCT / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * LEVERAGE)), current_equity * 0.95)

            active_trade = {
                'Posisi': "🟢 LONG (Buy)", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2), 'Harga SL ($)': round(sl_price, 2),
                'Harga TP1 ($)': round(tp1_price, 2), 'Harga TP2 ($)': round(tp2_price, 2),
                'Margin Kunci ($)': round(margin_final, 2), 'Status': "Berjalan (Running)", 'TP1_Hit': False, 'Laba_TP1_USD': 0
            }
            if i == df.index[-1]:
                send_telegram_alert(f"🟢 *SINYAL SNIPER LONG BTC-USD*\nEntry: ${df.at[i, 'close']:.2f}\nSL: ${sl_price:.2f}\nTP1: ${tp1_price:.2f}\nTP2: ${tp2_price:.2f}")

        elif df.at[i, 'display_sell']:
            if active_trade is not None:
                ratio_aktif = 1.0 if not active_trade['TP1_Hit'] else 0.5
                p_close = df.at[i, 'close']
                profit_raw = ((p_close - active_trade['Harga Entry ($)']) if active_trade['Posisi'] == "🟢 LONG (Buy)" else (active_trade['Harga Entry ($)'] - p_close)) / active_trade['Harga Entry ($)'] * 100
                profit_net = (profit_raw * LEVERAGE) - (TRADING_FEE_PCT * 2)
                laba_usd = (profit_net / 100) * active_trade['Margin Kunci ($)'] * ratio_aktif
                current_equity += laba_usd
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Laba Bersih ($ USD)'] = round(active_trade.get('Laba_TP1_USD', 0) + laba_usd, 2)
                trades_list.append(active_trade)
                equity_timestamps.append(df.at[i, 'date'])
                equity_values.append(current_equity)
                active_trade = None

            sl_price = df.at[i, 'close'] + (df.at[i, 'atr'] * P_ATR_MULTIPLIER)
            jarak_sl = abs(sl_price - df.at[i, 'close'])
            tp1_price = df.at[i, 'close'] - (jarak_sl * RASIO_TP1)
            tp2_price = df.at[i, 'close'] - (jarak_sl * RASIO_TP2)
            
            jarak_sl_pct = jarak_sl / df.at[i, 'close']
            usd_risk = current_equity * (RISIKO_PER_TRADE_PCT / 100)
            margin_final = min((usd_risk / (jarak_sl_pct * LEVERAGE)), current_equity * 0.95)

            active_trade = {
                'Posisi': "🔴 SHORT (Sell)", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2), 'Harga SL ($)': round(sl_price, 2),
                'Harga TP1 ($)': round(tp1_price, 2), 'Harga TP2 ($)': round(tp2_price, 2),
                'Margin Kunci ($)': round(margin_final, 2), 'Status': "Berjalan (Running)", 'TP1_Hit': False, 'Laba_TP1_USD': 0
            }
            if i == df.index[-1]:
                send_telegram_alert(f"🔴 *SINYAL SNIPER SHORT BTC-USD*\nEntry: ${df.at[i, 'close']:.2f}\nSL: ${sl_price:.2f}\nTP1: ${tp1_price:.2f}\nTP2: ${tp2_price:.2f}")

    if active_trade is not None and active_trade not in trades_list:
        trades_list.append(active_trade)

    # --- REKAP DATA METRIK ---
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
        drawdowns = (equity_series - cum_max) / cum_max
        max_dd_pct = abs(drawdowns.min()) * 100

    current_price = df.iloc[-1]['close']
    
    # --- RENDERING DASHBOARD METRIK ---
    st.markdown("### 📊 Hasil Analisis Kuantitatif Terpusat (Sniper 4h Mode)")
    m1, m2, m3, m4, m5, m6 = st.columns(6)
    m1.metric("Harga BTC", f"${current_price:,.2f}")
    m2.metric("Win Rate Sinyal", f"{win_rate:.2f}%")
    m3.metric("Profit Factor", f"{profit_factor:.2f}" if profit_factor > 0 else "N/A")
    m4.metric("Max Drawdown (MDD)", f"{max_dd_pct:.2f}%")
    m5.metric("Akumulasi ROI", f"{(total_profit_usd/MODAL_AWAL)*100:.2f}%")
    m6.metric("Saldo Akhir Akun", f"${MODAL_AWAL + total_profit_usd:,.2f}")

    # --- GRAFIK MULTI-INDIKATOR SUBPLOT ---
    df_plot = df.tail(JUMLAH_LILIN_LAYAR)
    fig = make_subplots(rows=5, cols=1, shared_xaxes=True, vertical_spacing=0.02, row_width=[0.1, 0.1, 0.1, 0.1, 0.6])
    
    # Row 1: Candlestick + HMA + EMA + CKS
    fig.add_trace(go.Candlestick(x=df_plot['date'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'], name="Candlestick"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['hma'], line=dict(color='yellow', width=2), name="HMA Trend"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ema'], line=dict(color='cyan', width=1.5, dash='dash'), name="EMA Pullback"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['cks_long'], line=dict(color='orange', width=1, dash='dot'), name="CKS Long Bound"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['cks_short'], line=dict(color='purple', width=1, dash='dot'), name="CKS Short Bound"), row=1, col=1)

    buys = df_plot[df_plot['display_buy']]; sells = df_plot[df_plot['display_sell']]
    fig.add_trace(go.Scatter(x=buys['date'], y=buys['close'], mode='markers', marker=dict(symbol='triangle-up', size=12, color='lime'), name="Sinyal LONG"), row=1, col=1)
    fig.add_trace(go.Scatter(x=sells['date'], y=sells['close'], mode='markers', marker=dict(symbol='triangle-down', size=12, color='red'), name="Sinyal SHORT"), row=1, col=1)

    # Row 2: Volume
    fig.add_trace(go.Bar(x=df_plot['date'], y=df_plot['volume'], name="Volume", marker_color='orange'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['vol_ma'], line=dict(color='white', width=1), name="Volume MA"), row=2, col=1)
    
    # Row 3: RSI
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['rsi'], line=dict(color='green', width=1.5), name="RSI"), row=3, col=1)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=3, col=1); fig.add_hline(y=30, line_dash="dash", line_color="lime", row=3, col=1)
    
    # Row 4: ATR
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['atr'], line=dict(color='magenta', width=1.5), name="ATR"), row=4, col=1)

    fig.update_layout(height=850, xaxis_rangeslider_visible=False, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    # --- GRAFIK KURVA EKUITAS MODAL ---
    st.markdown("### 📈 Kurva Pertumbuhan Ekuitas Modal (Equity Curve)")
    if len(equity_values) > 1:
        df_equity = pd.DataFrame({"Waktu": equity_timestamps, "Modal ($ USD)": equity_values})
        fig_equity = go.Figure()
        fig_equity.add_trace(go.Scatter(x=df_equity['Waktu'], y=df_equity['Modal ($ USD)'], mode='lines+markers', line=dict(color='lime', width=2.5), fill='tozeroy', fillcolor='rgba(0, 255, 0, 0.1)', name="Ekuitas"))
        fig_equity.update_layout(height=350, template="plotly_dark", xaxis_title="Waktu", yaxis_title="Saldo ($ USD)")
        st.plotly_chart(fig_equity, use_container_width=True)

    # --- TABEL HISTORI LOG EKSEKUSI ---
    if trades_list:
        st.markdown("### 🧾 Log Transaksi Futures Resmi")
        df_trades = pd.DataFrame(trades_list)
        df_trades_clean = df_trades.drop(columns=['TP1_Hit', 'Laba_TP1_USD'], errors='ignore')
        st.dataframe(df_trades_clean.iloc[::-1], use_container_width=True)

except Exception as e:
    st.error(f"Terjadi kesalahan sistem pengolahan: {e}")
