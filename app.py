import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="HHMA Renko BTC Futures Max Pro", layout="wide")
st.title("🛡️ HHMA Renko + EMA + ATR + Volume - Algoritma Kontrak Futures Pro")

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
st.sidebar.header("⚙️ Konfigurasi Filter Indikator")
length_ema = st.sidebar.slider("Periode EMA Filter:", min_value=5, max_value=200, value=21, step=1)
length_atr = st.sidebar.slider("Periode ATR Volatilitas:", min_value=5, max_value=30, value=14, step=1)
atr_multiplier = st.sidebar.slider("Pengali ATR (Stop Loss):", min_value=1.0, max_value=3.5, value=2.0, step=0.1)
length_vol_ma = st.sidebar.slider("Periode Volume MA:", min_value=5, max_value=50, value=20, step=1)

# --- PANEL SIDEBAR KALKULATOR FUTURES ---
st.sidebar.markdown("---")
st.sidebar.header("🔥 Pengaturan Akun Futures")
modal_awal = st.sidebar.number_input("Margin Awal ($ USD):", min_value=10, value=1000, step=100)
leverage = st.sidebar.slider("Leverage (Multiplier):", min_value=1, max_value=50, value=10, step=1)

st.sidebar.markdown("---")
st.sidebar.header("🧾 Biaya Transaksi Futures")
trading_fee_pct = st.sidebar.number_input("Fee Bursa per Eksekusi (%):", min_value=0.0, max_value=1.0, value=0.05, step=0.01)

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

    # --- PERHITUNGAN INDIKATOR UTAMA & TAMBAHAN ---
    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    df['ema'] = ta.ema(df['close'], length=length_ema)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=length_atr)
    df['vol_ma'] = ta.sma(df['volume'], length=length_vol_ma) # Rata-rata Volume
    
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['is_red'] = df['hma'] < df['hma'].shift(1)
    
    # Sinyal pemicu awal perubahan warna garis HMA
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = df['is_red'] & (~df['is_red'].shift(1).fillna(False))

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    # Mengunci status agar sinyal LONG dan SHORT terfilter dengan indikator pendukung
    for i in df.index:
        if i < max(length_hma, length_ema, length_atr, length_vol_ma):
            continue
            
        # Kriteria Tambahan LONG: Harga > EMA DAN Volume > Rata-rata Volume MA
        filter_long = (df.at[i, 'close'] > df.at[i, 'ema']) and (df.at[i, 'volume'] > df.at[i, 'vol_ma'])
        # Kriteria Tambahan SHORT: Harga < EMA DAN Volume > Rata-rata Volume MA
        filter_short = (df.at[i, 'close'] < df.at[i, 'ema']) and (df.at[i, 'volume'] > df.at[i, 'vol_ma'])

        if df.at[i, 'raw_buy'] and filter_long and last_signal != 1:
            df.at[i, 'buy_signal'] = True
            last_signal = 1
        elif df.at[i, 'raw_sell'] and filter_short and last_signal != -1:
            df.at[i, 'sell_signal'] = True
            last_signal = -1

    df['display_buy'] = df['buy_signal']
    df['display_sell'] = df['sell_signal']

    # --- SIMULATOR BACKTEST MESIN FUTURES (DENGAN PROTEKSI STOP LOSS ATR) ---
    trades_list = []  
    active_trade = None

    for i in df.index:
        # Check Stop Loss untuk Posisi Berjalan Lebih Dulu
        if active_trade is not None and active_trade['Status'] == "Berjalan (Running)":
            if active_trade['Posisi'] == "🟢 LONG (Buy)":
                if df.at[i, 'low'] <= active_trade['Harga SL ($)']:
                    profit_raw = ((active_trade['Harga SL ($)'] - active_trade['Harga Entry ($)']) / active_trade['Harga Entry ($)']) * 100
                    total_fee = trading_fee_pct * 2
                    profit_net = (profit_raw * leverage) - total_fee
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close ($)'] = round(active_trade['Harga SL ($)'], 2)
                    active_trade['Status'] = "💥 Terkena Stop Loss (ATR)"
                    active_trade['Profit Net (%)'] = round(profit_net, 2)
                    active_trade['Laba Bersih ($ USD)'] = round((profit_net / 100) * modal_awal, 2)
                    trades_list.append(active_trade)
                    active_trade = None
            
            elif active_trade is not None and active_trade['Posisi'] == "🔴 SHORT (Sell)":
                if df.at[i, 'high'] >= active_trade['Harga SL ($)']:
                    profit_raw = ((active_trade['Harga Entry ($)'] - active_trade['Harga SL ($)']) / active_trade['Harga Entry ($)']) * 100
                    total_fee = trading_fee_pct * 2
                    profit_net = (profit_raw * leverage) - total_fee
                    
                    active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                    active_trade['Harga Close ($)'] = round(active_trade['Harga SL ($)'], 2)
                    active_trade['Status'] = "💥 Terkena Stop Loss (ATR)"
                    active_trade['Profit Net (%)'] = round(profit_net, 2)
                    active_trade['Laba Bersih ($ USD)'] = round((profit_net / 100) * modal_awal, 2)
                    trades_list.append(active_trade)
                    active_trade = None

        # KONDISI 1: Trigger LONG
        if df.at[i, 'display_buy']:
            if active_trade is not None and active_trade['Posisi'] == "🔴 SHORT (Sell)":
                profit_raw = ((active_trade['Harga Entry ($)'] - df.at[i, 'close']) / active_trade['Harga Entry ($)']) * 100
                total_fee = trading_fee_pct * 2
                profit_net = (profit_raw * leverage) - total_fee
                
                active_trade['Waktu Close'] = df.at[i, 'date'].strftime('%Y-%m-%d %H:%M')
                active_trade['Harga Close ($)'] = round(df.at[i, 'close'], 2)
                active_trade['Status'] = "🎯 Ditutup Sinyal Kebalikan"
                active_trade['Profit Net (%)'] = round(profit_net, 2)
                active_trade['Laba Bersih ($ USD)'] = round((profit_net / 100) * modal_awal, 2)
                trades_list.append(active_trade)
                active_trade = None

            # Jarak Pengaman SL Berbasis ATR
            sl_price = df.at[i, 'close'] - (df.at[i, 'atr'] * atr_multiplier)
            active_trade = {
                'Posisi': "🟢 LONG (Buy)",
                'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2),
                'Harga SL ($)': round(sl_price, 2),
                'Waktu Close': "-",
                'Harga Close ($)': 0.0,
                'Status': "Berjalan (Running)",
                'Profit Net (%)': 0.0,
                'Laba Bersih ($ USD)': 0.0
            }

        # KONDISI 2: Trigger SHORT
        elif df.at[i, 'display_sell']:
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

            # Jarak Pengaman SL Berbasis ATR
            sl_price = df.at[i, 'close'] + (df.at[i, 'atr'] * atr_multiplier)
            active_trade = {
                'Posisi': "🔴 SHORT (Sell)",
                'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'Harga Entry ($)': round(df.at[i, 'close'], 2),
                'Harga SL ($)': round(sl_price, 2),
                'Waktu Close': "-",
                'Harga Close ($)': 0.0,
                'Status': "Berjalan (Running)",
                'Profit Net (%)': 0.0,
                'Laba Bersih ($ USD)': 0.0
            }

    if active_trade is not None and active_trade not in trades_list:
        trades_list.append(active_trade)

    # --- REKAP DATA METRIK ATAS ---
    total_trades_done = [t for t in trades_list if t['Status'] != "Berjalan (Running)"]
    win_rate = 0
    total_profit_pct = sum([t['Profit Net (%)'] for t in total_trades_done])
    estimasi_profit_usd = (total_profit_pct / 100) * modal_awal

    if len(total_trades_done) > 0:
        wins = len([t for t in total_trades_done if t['Profit Net (%)'] > 0])
        win_rate = (wins / len(total_trades_done)) * 100

    current_price = df.iloc[-1]['close']
    
    # --- MENAMPILKAN METRIK UTAMA ---
    st.markdown("### 📊 Ringkasan Kinerja Sistem Berdasarkan Filter Kombinasi")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Harga BTC Saat Ini", f"${current_price:,.2f}")
    m2.metric("Win Rate Sinyal", f"{win_rate:.2f}%", help="Persentase trade yang menghasilkan keuntungan net positif")
    m3.metric("Akumulasi Profit Net (%)", f"{total_profit_pct:.2f}%")
    m4.metric("Estimasi Profit ($ USD)", f"${estimasi_profit_usd:,.2f}")

    # --- VISUALISASI GRAFIK SUBPLOT MULTI-INDIKATOR ---
    df_plot = df.tail(jumlah_tampilan)
    
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, 
                        vertical_spacing=0.03, 
                        row_width=[0.2, 0.2, 0.6])

    # Row 1: Candlestick + HMA + EMA
    fig.add_trace(go.Candlestick(
        x=df_plot['date'], open=df_plot['open'], high=df_plot['high'],
        low=df_plot['low'], close=df_plot['close'], name="Candlestick"
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['hma'], line=dict(color='yellow', width=2), name="HMA Trend"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['ema'], line=dict(color='cyan', width=1.5, dash='dash'), name="EMA Filter"), row=1, col=1)

    # Tambahkan Marker Sinyal Buy/Sell di chart utama
    buys = df_plot[df_plot['display_buy']]
    sells = df_plot[df_plot['display_sell']]
    
    fig.add_trace(go.Scatter(x=buys['date'], y=buys['close'], mode='markers', marker=dict(symbol='triangle-up', size=12, color='lime'), name="Sinyal LONG"), row=1, col=1)
    fig.add_trace(go.Scatter(x=sells['date'], y=sells['close'], mode='markers', marker=dict(symbol='triangle-down', size=12, color='red'), name="Sinyal SHORT"), row=1, col=1)

    # Row 2: Volume + Volume MA
    fig.add_trace(go.Bar(x=df_plot['date'], y=df_plot['volume'], name="Volume", marker_color='orange'), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['vol_ma'], line=dict(color='white', width=1), name="Volume MA"), row=2, col=1)

    # Row 3: ATR (Volatilitas)
    fig.add_trace(go.Scatter(x=df_plot['date'], y=df_plot['atr'], line=dict(color='magenta', width=1.5), name="ATR"), row=3, col=1)

    fig.update_layout(height=700, xaxis_rangeslider_visible=False, theme="dark")
    st.plotly_chart(fig, use_container_width=True)

    # --- TABEL HISTORI LOG EKSEKUSI ---
    if trades_list:
        st.markdown("### 🧾 Log Transaksi Futures Resmi")
        df_trades = pd.DataFrame(trades_list)
        st.dataframe(df_trades.iloc[::-1], use_container_width=True) # Urutan terbaru di atas

except Exception as e:
    st.error(f"Terjadi kesalahan sistem pengolahan: {e}")
