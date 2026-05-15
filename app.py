import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit.components.v1 as components  

st.set_page_config(page_title="HHMA Renko BTC Max Pro", layout="wide")
st.title("🛡️ HHMA Renko 400 BTC - Algoritma Filter Berlapis (Maksimal Akurasi)")

# --- SISTEM PENGUNCI SETELAN ANTI REFRESH ---
query_params = st.query_params
default_tf = query_params.get("tf", "1 Jam (1h)")  
default_src = query_params.get("src", "Close (Penutupan)")
try:
    default_len = int(query_params.get("len", "19"))  
except:
    default_len = 19

# Panel Menu Pengaturan Utama
col1, col2, col3, col4 = st.columns(4)
with col1:
    tf_options = ["1 Hari (Daily)", "4 Jam (4h)", "1 Jam (1h)"]
    tf_index = tf_options.index(default_tf) if default_tf in tf_options else 2
    tf_pilihan = st.selectbox("Jangka Waktu (Timeframe):", options=tf_options, index=tf_index)
with col2:
    src_options = ["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"]
    src_index = src_options.index(default_src) if default_src in src_options else 0
    src_pilihan = st.selectbox("Sumber Data (Source):", options=src_options, index=src_index)
with col3:
    length_hma = st.slider("Panjang HMA (Length):", min_value=2, max_value=50, value=default_len, step=1)
with col4:
    jumlah_tampilan = st.slider("Jumlah Lilin di Layar:", min_value=10, max_value=300, value=150, step=10)

# --- PANEL KALKULATOR MODAL & TARGET ATR (SIDEBAR) ---
st.sidebar.header("💰 Pengaturan Kalkulator Finansial")
modal_awal = st.sidebar.number_input("Modal Trading Anda ($ USD):", min_value=10, value=1000, step=100)
leverage = st.sidebar.slider("Leverage (Multiplier):", min_value=1, max_value=50, value=1, step=1)

st.sidebar.markdown("---")
st.sidebar.header("🎯 Target Risiko Dinamis (ATR)")
st.sidebar.info("Target harga otomatis mengikuti volatilitas market. Mengecil saat sepi, melebar saat ramai.")
# Pengaturan pengali (multiplier) jarak ATR untuk penentuan level TP dan SL
tp_atr_multiplier = st.sidebar.number_input("Multiplier Take Profit (TP ATR):", min_value=0.5, max_value=10.0, value=3.0, step=0.1)
sl_atr_multiplier = st.sidebar.number_input("Multiplier Stop Loss (SL ATR):", min_value=0.5, max_value=10.0, value=1.5, step=0.1)

st.query_params.update(tf=tf_pilihan, src=src_pilihan, len=str(length_hma))

src_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}
src_aktif = src_map[src_pilihan]
interval_map = {"1 Hari (Daily)": "1d", "4 Jam (4h)": "4h", "1 Jam (1h)": "1h"}
period_map = {"1 Hari (Daily)": "730d", "4 Jam (4h)": "180d", "1 Jam (1h)": "90d"}

@st.cache_data(ttl=30)
def get_crypto_data(p, i):
    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(period=p, interval=i)
    df = df.reset_index()
    df = df.rename(columns={'Date': 'date', 'Datetime': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
    return df

try:
    df = get_crypto_data(period_map[tf_pilihan], interval_map[tf_pilihan])
    
    if df.empty:
        st.error("Gagal mengambil data dari Yahoo Finance.")
        st.stop()

    # --- PENGHITUNGAN ALGORITMA FILTER BERLAPIS ---
    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    df['ema_200'] = ta.ema(df['close'], length=200)  
    df['rsi'] = ta.rsi(df['close'], length=14)        
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14) 
    df['atr_ma'] = ta.sma(df['atr'], length=20)
    df['volume_ma'] = ta.sma(df['volume'], length=20)
    
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = (~df['is_green']) & df['is_green'].shift(1).fillna(False)

    # Filter Akurasi Ultra Maksimal
    df['high_accuracy_buy'] = (df['raw_buy'] & (df['close'] > df['ema_200'] * 1.005) & (df['rsi'] > 45) & (df['rsi'] < 58) & (df['atr'] > df['atr_ma']) & (df['volume'] > df['volume_ma']))
    df['high_accuracy_sell'] = (df['raw_sell'] & (df['close'] < df['ema_200'] * 0.995) & (df['rsi'] > 42) & (df['rsi'] < 55) & (df['atr'] > df['atr_ma']) & (df['volume'] > df['volume_ma']))

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    for i in df.index:
        if df.at[i, 'high_accuracy_buy'] and last_signal != 1:
            df.at[i, 'buy_signal'] = True
            last_signal = 1
        elif df.at[i, 'high_accuracy_sell'] and last_signal != -1:
            df.at[i, 'sell_signal'] = True
            last_signal = -1

    # --- MATRIKS BACKTEST DINAMIS ATR ---
    trades_list = []  
    active_trade = None

    for i in df.index:
        if df.at[i, 'buy_signal']:
            # Logika penutupan darurat jika ada posisi gantung terdeteksi sinyal balik
            if active_trade is not None:
                loss_pct = ((df.at[i, 'close'] - active_trade['entry_price']) / active_trade['entry_price']) * 100
                active_trade['status'] = "Selesai (Cut Sinyal Kebalikan)"
                active_trade['profit_pct'] = loss_pct * leverage
                active_trade['profit_usd'] = (active_trade['profit_pct'] / 100) * modal_awal
                trades_list.append(active_trade)

            # Eksekusi kalkulasi target harga berbasis ATR saat lilin berjalan entry
            entry_price = df.at[i, 'close']
            atr_now = df.at[i, 'atr']
            
            # Formulasi target harga absolut (bukan persentase statis)
            live_tp_price = entry_price + (atr_now * tp_atr_multiplier)
            live_sl_price = entry_price - (atr_now * sl_atr_multiplier)

            active_trade = {
                'waktu_entry': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'jenis': "🟢 BUY",
                'entry_price': entry_price,
                'target_tp': live_tp_price,
                'target_sl': live_sl_price,
                'status': "Berjalan (Running)",
                'profit_pct': 0.0,
                'profit_usd': 0.0
            }

        elif active_trade is not None:
            # Pengecekan real-time apakah sumbu harga menembus batas ATR dinamis
            high_match = df.at[i, 'high'] >= active_trade['target_tp']
            low_match = df.at[i, 'low'] <= active_trade['target_sl']
            
            if high_match:
                real_profit_pct = ((active_trade['target_tp'] - active_trade['entry_price']) / active_trade['entry_price']) * 100
                active_trade['status'] = "🎯 Take Profit (ATR)"
                active_trade['profit_pct'] = real_profit_pct * leverage
                active_trade['profit_usd'] = (active_trade['profit_pct'] / 100) * modal_awal
                trades_list.append(active_trade)
                active_trade = None
            elif low_match or df.at[i, 'sell_signal']:
                exit_price = active_trade['target_sl'] if low_match else df.at[i, 'close']
                real_loss_pct = ((exit_price - active_trade['entry_price']) / active_trade['entry_price']) * 100
                active_trade['status'] = "🛑 Stop Loss / Exit"
                active_trade['profit_pct'] = real_loss_pct * leverage
                active_trade['profit_usd'] = (active_trade['profit_pct'] / 100) * modal_awal
                trades_list.append(active_trade)
                active_trade = None

    if active_trade is not None:
        trades_list.append(active_trade)

    # Rekap data metrik papan skor
    total_trades_done = [t for t in trades_list if t['status'] != "Berjalan (Running)"]
    win_rate = 0
    total_profit_pct = sum([t['profit_pct'] for t in total_trades_done])
    estimasi_profit_usd = (total_profit_pct / 100) * modal_awal

    if len(total_trades_done) > 0:
        wins = len([t for t in total_trades_done if t['profit_pct'] > 0])
        win_rate = (wins / len(total_trades_done)) * 100

    current_price = df.iloc[-1]['close']
    
    df_signals = df[df['buy_signal'] | df['sell_signal']]
    if not df_signals.empty:
        last_row = df_signals.iloc[-1]
        if last_row['buy_signal']:
            status_sinyal = "🟢 BUY (Masuk Posisi)"
            waktu_sinyal = last_row['date'].strftime('%Y-%m-%d %H:%M')
            harga_sinyal = f"${last_row['close']:,.2f}"
        else:
            status_sinyal = "🔴 EXIT / SELL (Keluar)"
            waktu_sinyal = last_row['date'].strftime('%Y-%m-%d %H:%M')
            harga_sinyal = f"${last_row['close']:,.2f}"
    else:
        status_sinyal = "⚪ Belum Ada Sinyal"
        waktu_sinyal = "-"
        harga_sinyal = "-"

    # --- PAPAN METRIK UTAMA ---
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(label=f"Harga BTC Live ({tf_pilihan})", value=f"${current_price:,.2f}")
    with m2:
        st.metric(label="Sinyal Aktif Saat Ini", value=status_sinyal, delta=f"Eksekusi: {harga_sinyal}")
    with m3:
        st.metric(label="Waktu Sinyal Terakhir", value=waktu_sinyal)
    with m4:
        st.metric(label="Win Rate & Estimasi Profit", value=f"{win_rate:.1f}%", delta=f"${estimasi_profit_usd:+,.2f} ({total_profit_pct:+.1f}%)")

    # --- VISUALISASI GRAFIK UTAMA CANDLESTICK (PLOTLY) ---
    st.subheader("📈 Grafik Analisis Multi-Indikator Live")
    
    df_plot = df.iloc[-jumlah_tampilan:].copy()
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05, row_heights=[0.7, 0.3])
    
    # Candlestick
    fig.add_trace(go.Candlestick(
        x=df_plot['date'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'],
        name="Bitcoin (BTC)", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ), row=1, col=1)
    
    # Indikator Tren
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['hma'], name=f"HHMA ({length_hma})", line=dict(color='#ffeb3b', width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ema_200'], name="EMA 200", line=dict(color='#e91e63', width=1.5, dash='dash')), row=1, col=1)
    
    # Penempatan Penanda Sinyal Grafik
    buy_markers = df_plot[df_plot['buy_signal']]
    sell_markers = df_plot[df_plot['sell_signal']]
    
    fig.add_trace(go.Scatter(
        x=buy_markers['date'], y=buy_markers['low'] * 0.99, mode='markers',
        name='Sinyal BUY', marker=dict(symbol='triangle-up', size=14, color='#00e676', line=dict(width=1, color='white'))
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=sell_markers['date'], y=sell_markers['high'] * 1.01, mode='markers',
        name='Sinyal EXIT', marker=dict(symbol='triangle-down', size=14, color='#ff1744', line=dict(width=1, color='white'))
    ), row=1, col=1)
    
    # Subplot Sub-Panel RSI
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['rsi'], name="RSI (14)", line=dict(color='#29b6f6', width=1.5)), row=2, col=1)
    
    fig.update_layout(height=650, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # Tampilkan tabel data transaksi resmi
    if trades_list:
        st.subheader("📜 Riwayat Transaksi Backtest")
        # Mengubah list dictionary menjadi dataframe untuk pelaporan audit transaksi
        df_trades_report = pd.DataFrame(trades_list)
        # Re-order kolom agar nilai target harga dinamis ATR ikut tertera jelas di tabel data
        cols_order = ['waktu_entry', 'jenis', 'entry_price', 'target_tp', 'target_sl', 'status', 'profit_pct', 'profit_usd']
        df_trades_report = df_trades_report.reindex(columns=[c for c in cols_order if c in df_trades_report.columns])
        st.dataframe(df_trades_report, use_container_width=True)

except Exception as e:
    st.error(f"Terjadi kesalahan teknis sistem: {e}")
