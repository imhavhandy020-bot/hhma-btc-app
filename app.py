import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="HHMA Renko BTC Max Pro", layout="wide")
st.title("🛡️ HHMA Renko 400 BTC - Siklus Sinyal Bergantian (BUY ↔ SELL)")

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

# --- PANEL KALKULATOR MODAL (SIDEBAR) ---
st.sidebar.header("💰 Pengaturan Kalkulator Finansial")
modal_awal = st.sidebar.number_input("Modal Trading Anda ($ USD):", min_value=10, value=1000, step=100)
leverage = st.sidebar.slider("Leverage (Multiplier):", min_value=1, max_value=50, value=1, step=1)

st.query_params.update(tf=tf_pilihan, src=src_pilihan, len=str(length_hma))

src_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}
src_aktif = src_map[src_pilihan]

interval_map = {
    "1 Hari (Daily)": "1d", "4 Jam (4h)": "4h", "1 Jam (1h)": "1h",
    "15 Menit (15m)": "15m", "5 Menit (5m)": "5m", "1 Menit (1m)": "1m"
}
period_map = {
    "1 Hari (Daily)": "730d", "4 Jam (4h)": "180d", "1 Jam (1h)": "90d",
    "15 Menit (15m)": "30d", "5 Menit (5m)": "30d", "1 Menit (1m)": "7d"
}

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

    # --- PERHITUNGAN INDIKATOR SESUAI PINE SCRIPT ANDA ---
    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = (~df['is_green']) & df['is_green'].shift(1).fillna(False)

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    # Sistem pengunci status agar sinyal selalu bergantian BUY -> SELL -> BUY -> SELL
    for i in df.index:
        if df.at[i, 'raw_buy'] and last_signal != 1:
            df.at[i, 'buy_signal'] = True
            last_signal = 1
        elif df.at[i, 'raw_sell'] and last_signal != -1:
            df.at[i, 'sell_signal'] = True
            last_signal = -1

    # Emulasi offset=-1 dari TradingView (geser maju 1 bar untuk sinkronisasi grafik)
    df['display_buy'] = df['buy_signal'].shift(1).fillna(False)
    df['display_sell'] = df['sell_signal'].shift(1).fillna(False)

    # --- MATRIKS BACKTEST PARADIGMA BERGANTIAN (SELALU BUY -> SELL) ---
    trades_list = []  
    active_trade = None

    for i in df.index:
        # PERBAIKAN: Transaksi masuk hanya dieksekusi jika ada sinyal display_buy
        if df.at[i, 'display_buy']:
            # Jika sebelumnya ada trade menggantung, tutup paksa tepat saat BUY baru ini aktif
            if active_trade is not None:
                profit_pct = ((df.at[i, 'close'] - active_trade['entry_price']) / active_trade['entry_price']) * 100
                active_trade['status'] = "🛑 Ditutup Sinyal Kebalikan"
                active_trade['profit_pct'] = profit_pct * leverage
                active_trade['profit_usd'] = (active_trade['profit_pct'] / 100) * modal_awal
                trades_list.append(active_trade)

            # Buka posisi BUY baru
            active_trade = {
                'waktu_entry': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'jenis': "🟢 BUY",
                'entry_price': df.at[i, 'close'],
                'waktu_exit': "-",
                'exit_price': 0.0,
                'status': "Berjalan (Running)",
                'profit_pct': 0.0,
                'profit_usd': 0.0
            }

        # PERBAIKAN MUTLAK: Posisi BUY hanya bisa ditutup jika mendeteksi sinyal display_sell murni
        elif df.at[i, 'display_sell'] and active_trade is not None:
            profit_pct = ((df.at[i, 'close'] - active_trade['entry_price']) / active_trade['entry_price']) * 100
            
            # Buat record penutupan posisi SELL pasangannya
            active_trade['waktu_exit'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
            # Jika datanya bertipe tuple, ekstrak nilai string pertamanya agar rapi di tabel
            if isinstance(active_trade['waktu_exit'], tuple):
                active_trade['waktu_exit'] = active_trade['waktu_exit'][0]
                
            active_trade['exit_price'] = df.at[i, 'close']
            active_trade['status'] = "🔴 SELL (Exit Sinyal)"
            active_trade['profit_pct'] = profit_pct * leverage
            active_trade['profit_usd'] = (active_trade['profit_pct'] / 100) * modal_awal
            
            trades_list.append(active_trade)
            active_trade = None

    # Jika trade paling akhir saat ini statusnya masih running, masukkan juga ke list tabel
    if active_trade is not None:
        trades_list.append(active_trade)

    # Rekap data papan skor metrik atas
    total_trades_done = [t for t in trades_list if t['status'] != "Berjalan (Running)"]
    win_rate = 0
    total_profit_pct = sum([t['profit_pct'] for t in total_trades_done])
    estimasi_profit_usd = (total_profit_pct / 100) * modal_awal

    if len(total_trades_done) > 0:
        wins = len([t for t in total_trades_done if t['profit_pct'] > 0])
        win_rate = (wins / len(total_trades_done)) * 100

    current_price = df.iloc[-1]['close']
    
    df_signals = df[df['display_buy'] | df['display_sell']]
    if not df_signals.empty:
        last_row = df_signals.iloc[-1]
        if last_row['display_buy']:
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
    fig = make_subplots(rows=1, cols=1)
    
    fig.add_trace(go.Candlestick(
        x=df_plot['date'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'],
        name="Bitcoin (BTC)", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ))
    
    # Garis HHMA Dinamis Berubah Warna per Segmen Lilin
    for i in range(1, len(df_plot)):
        p1 = df_plot.iloc[i-1]
        p2 = df_plot.iloc[i]
        line_color = '#00e676' if p2['is_green'] else '#ff1744'
        fig.add_trace(go.Scatter(
            x=[p1['date'], p2['date']], y=[p1['hma'], p2['hma']],
            mode='lines', line=dict(color=line_color, width=3), showlegend=False, hoverinfo='skip'
        ))
    
    # Penempatan Penanda Sinyal Grafik (Mengikuti nilai hma persis seperti lekukan Pine Script)
    buy_markers = df_plot[df_plot['display_buy']]
    sell_markers = df_plot[df_plot['display_sell']]
    
    fig.add_trace(go.Scatter(
        x=buy_markers['date'], y=buy_markers['hma'].shift(1), mode='markers',
        name='Sinyal BUY', marker=dict(symbol='triangle-up', size=14, color='#00e676', line=dict(width=1, color='white'))
    ))
    
    fig.add_trace(go.Scatter(
        x=sell_markers['date'], y=sell_markers['hma'].shift(1), mode='markers',
        name='Sinyal EXIT', marker=dict(symbol='triangle-down', size=14, color='#ff1744', line=dict(width=1, color='white'))
    ))
    
    fig.update_layout(height=600, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # --- TABEL RIWAYAT TRANSAKSI RESMI (TERBARU DI ATAS) ---
    if trades_list:
        st.subheader("📜 Riwayat Transaksi Backtest")
        df_trades_report = pd.DataFrame(trades_list)
        cols_order = ['waktu_entry', 'jenis', 'entry_price', 'waktu_exit', 'exit_price', 'status', 'profit_pct', 'profit_usd']
        df_trades_report = df_trades_report.reindex(columns=[c for c in cols_order if c in df_trades_report.columns])
        st.dataframe(df_trades_report.iloc[::-1], use_container_width=True)

except Exception as e:
    st.error(f"Terjadi kesalahan teknis sistem: {e}")
