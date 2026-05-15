import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="HHMA Renko BTC Futures Max Pro", layout="wide")
st.title("🛡️ HHMA Renko 400 BTC - Algoritma Mesin Kontrak Futures (2 Arah)")

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

# --- PANEL SIDEBAR KALKULATOR FUTURES ---
st.sidebar.header("🔥 Pengaturan Akun Futures")
modal_awal = st.sidebar.number_input("Margin Awal ($ USD):", min_value=10, value=1000, step=100)
leverage = st.sidebar.slider("Leverage (Multiplier):", min_value=1, max_value=50, value=10, step=1) # Default 10x untuk Futures

st.sidebar.markdown("---")
st.sidebar.header("🧾 Biaya Transaksi Futures")
trading_fee_pct = st.sidebar.number_input("Fee Bursa per Eksekusi (%):", min_value=0.0, max_value=1.0, value=0.05, step=0.01, help="Rata-rata fee Taker Futures adalah 0.05%")

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

    # --- PERHITUNGAN INDIKATOR ---
    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['is_red'] = df['hma'] < df['hma'].shift(1)
    
    # Sinyal pemicu awal perubahan warna garis
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = df['is_red'] & (~df['is_red'].shift(1).fillna(False))

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    # Mengunci status agar sinyal LONG dan SHORT selalu bergantian secara sempurna
    for i in df.index:
        if df.at[i, 'raw_buy'] and last_signal != 1:
            df.at[i, 'buy_signal'] = True
            last_signal = 1
        elif df.at[i, 'raw_sell'] and last_signal != -1:
            df.at[i, 'sell_signal'] = True
            last_signal = -1

    df['display_buy'] = df['buy_signal']
    df['display_sell'] = df['sell_signal']

    # --- SIMULATOR BACKTEST MESIN FUTURES (LONG & SHORT DUA ARAH) ---
    trades_list = []  
    active_trade = None

    for i in df.index:
        # KONDISI 1: Garis Hijau Muncul -> Pemicu Posisi LONG
        if df.at[i, 'display_buy']:
            # Jika sebelumnya sedang memegang posisi SHORT, wajib ditutup paksa (Take Profit / Stop Loss SHORT)
            if active_trade is not None and active_trade['Posisi'] == "🔴 SHORT":
                profit_raw = ((active_trade['Harga Entry ($)'] - df.at[i, 'close']) / active_trade['Harga Entry ($)']) * 100
                total_fee = trading_fee_pct * 2 # Fee saat Open + Fee saat Close
                profit_net = (profit_raw * leverage) - total_fee
                
                active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                active_trade['Harga Close ($)'] = round(df.at[i, 'close'], 2)
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Profit Net (%)'] = round(profit_net, 2)
                active_trade['Laba Bersih ($ USD)'] = round((profit_net / 100) * modal_awal, 2)
                trades_list.append(active_trade)
                active_trade = None

            # Buka posisi LONG baru
            active_trade = {
                'Posisi': "🟢 LONG (Buy)",
                'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2),
                'Waktu Close': "-",
                'Harga Close ($)': 0.0,
                'Status': "Berjalan (Running)",
                'Profit Net (%)': 0.0,
                'Laba Bersih ($ USD)': 0.0
            }

        # KONDISI 2: Garis Merah Muncul -> Pemicu Posisi SHORT
        elif df.at[i, 'display_sell']:
            # Jika sebelumnya sedang memegang posisi LONG, wajib ditutup paksa (Take Profit / Stop Loss LONG)
            if active_trade is not None and active_trade['Posisi'] == "🟢 LONG (Buy)":
                profit_raw = ((df.at[i, 'close'] - active_trade['Harga Entry ($)']) / active_trade['Harga Entry ($)']) * 100
                total_fee = trading_fee_pct * 2
                profit_net = (profit_raw * leverage) - total_fee
                
                active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                active_trade['Harga Close ($)'] = round(df.at[i, 'close'], 2)
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Profit Net (%)'] = round(profit_net, 2)
                active_trade['Laba Bersih ($ USD)'] = round((profit_net / 100) * modal_awal, 2)
                trades_list.append(active_trade)
                active_trade = None

            # Buka posisi SHORT baru
            active_trade = {
                'Posisi': "🔴 SHORT (Sell)",
                'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2),
                'Waktu Close': "-",
                'Harga Close ($)': 0.0,
                'Status': "Berjalan (Running)",
                'Profit Net (%)': 0.0,
                'Laba Bersih ($ USD)': 0.0
            }

    if active_trade is not None:
        trades_list.append(active_trade)

    # Rekap data metrik atas
    total_trades_done = [t for t in trades_list if t['Status'] != "Berjalan (Running)"]
    win_rate = 0
    total_profit_pct = sum([t['Profit Net (%)'] for t in total_trades_done])
    estimasi_profit_usd = (total_profit_pct / 100) * modal_awal

    if len(total_trades_done) > 0:
        wins = len([t for t in total_trades_done if t['Profit Net (%)'] > 0])
        win_rate = (wins / len(total_trades_done)) * 100

    current_price = df.iloc[-1]['close']
    
    df_signals = df[df['display_buy'] | df['display_sell']]
    if not df_signals.empty:
        last_row = df_signals.iloc[-1]
        status_sinyal = "🟢 GARIS HIJAU (Sinyal LONG)" if last_row['display_buy'] else "🔴 GARIS MERAH (Sinyal SHORT)"
        waktu_sinyal = last_row['date'].strftime('%Y-%m-%d %H:%M')
        harga_sinyal = f"${last_row['close']:,.2f}"
    else:
        status_sinyal, waktu_sinyal, harga_sinyal = "⚪ Belum Ada Sinyal", "-", "-"

    # --- PAPAN METRIK UTAMA ---
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(label=f"Harga BTC Live ({tf_pilihan})", value=f"${current_price:,.2f}")
    with m2:
        st.metric(label="Arah Tren Futures Aktif", value=status_sinyal, delta=f"Eksekusi: {harga_sinyal}")
    with m3:
        st.metric(label="Waktu Sinyal Terakhir", value=waktu_sinyal)
    with m4:
        st.metric(label="Win Rate & Saldo Bersih", value=f"{win_rate:.1f}%", delta=f"${estimasi_profit_usd:+,.2f} ({total_profit_pct:+.1f}%)")

    # --- VISUALISASI GRAFIK UTAMA CANDLESTICK ---
    st.subheader("📈 Grafik Analisis Pergerakan Kontrak Futures")
    df_plot = df.iloc[-jumlah_tampilan:].copy()
    fig = make_subplots(rows=1, cols=1)
    
    fig.add_trace(go.Candlestick(
        x=df_plot['date'], open=df_plot['open'], high=df_plot['high'], low=df_plot['low'], close=df_plot['close'],
        name="Bitcoin Futures", increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    ))
    
    # Render warna garis kontinu
    for i in range(1, len(df_plot)):
        p1 = df_plot.iloc[i-1]
        p2 = df_plot.iloc[i]
        line_color = '#00e676' if p2['is_green'] else '#ff1744'
        fig.add_trace(go.Scatter(x=[p1['date'], p2['date']], y=[p1['hma'], p2['hma']], mode='lines', line=dict(color=line_color, width=3), showlegend=False, hoverinfo='skip'))
    
    buy_markers = df_plot[df_plot['display_buy']]
    sell_markers = df_plot[df_plot['display_sell']]
    
    fig.add_trace(go.Scatter(x=buy_markers['date'], y=buy_markers['hma'], mode='markers', name='Sinyal LONG (Garis Hijau)', marker=dict(symbol='triangle-up', size=14, color='#00e676', line=dict(width=1, color='white'))))
    fig.add_trace(go.Scatter(x=sell_markers['date'], y=sell_markers['hma'], mode='markers', name='Sinyal SHORT (Garis Merah)', marker=dict(symbol='triangle-down', size=14, color='#ff1744', line=dict(width=1, color='white'))))
    
    fig.update_layout(height=600, xaxis_rangeslider_visible=False, template="plotly_dark", margin=dict(l=10, r=10, t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # --- TABEL JURNAL AKUN FUTURES DUA ARAH ---
    if trades_list:
        st.subheader("📜 Jurnal Transaksi Eksekusi Kontrak Futures (Terbaru di Atas)")
        df_trades_report = pd.DataFrame(trades_list)
        cols_order = ['Posisi', 'Waktu Open', 'Harga Entry ($)', 'Waktu Close', 'Harga Close ($)', 'Status', 'Profit Net (%)', 'Laba Bersih ($ USD)']
        df_trades_report = df_trades_report.reindex(columns=[c for c in cols_order if c in df_trades_report.columns])
        st.dataframe(df_trades_report.iloc[::-1], use_container_width=True, hide_index=True)

        # --- PANEL STATISTIK FUTURES WIN VS LOSS ---
        st.markdown("---")
        st.subheader("📊 Laporan Keuangan Audit Akun Futures")
        
        list_win = [t for t in total_trades_done if t['Profit Net (%)'] > 0]
        list_loss = [t for t in total_trades_done if t['Profit Net (%)'] <= 0]
        
        total_win = len(list_win)
        total_loss = len(list_loss)
        
        avg_win = sum([t['Profit Net (%)'] for t in list_win]) / total_win if total_win > 0 else 0.0
        avg_loss = sum([t['Profit Net (%)'] for t in list_loss]) / total_loss if total_loss > 0 else 0.0
        
        sum_win_usd = sum([t['Laba Bersih ($ USD)'] for t in list_win])
        sum_loss_usd = abs(sum([t['Laba Bersih ($ USD)'] for t in list_loss]))
        profit_factor = sum_win_usd / sum_loss_usd if sum_loss_usd > 0 else sum_win_usd
        
        s1, s2, s3, s4 = st.columns(4)
        with s1:
            st.metric(label="🟢 Posisi LONG/SHORT Profit (Win)", value=f"{total_win} Trade", delta=f"Rata-rata: +{avg_win:.2f}% Net")
        with s2:
            st.metric(label="🔴 Posisi LONG/SHORT Rugi (Loss)", value=f"{total_loss} Trade", delta=f"Rata-rata: {avg_loss:.2f}% Net")
        with s3:
            st.metric(label="🏆 Faktor Profitabilitas Bersih", value=f"{profit_factor:.2f}x")
        with s4:
            csv_data = df_trades_report.to_csv(index=False).encode('utf-8')
            st.download_button(label="📥 Download Jurnal Futures (CSV)", data=csv_data, file_name="Jurnal_Futures_HHMA_Renko.csv", mime="text/csv", use_container_width=True)

except Exception as e:
    st.error(f"Terjadi kesalahan teknis sistem: {e}")
