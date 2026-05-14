import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="HHMA Renko BTC Ultra", layout="wide")
st.title("🚀 Aplikasi Trading Ultra - HHMA Renko + Filter RSI")

# --- SISTEM PENGUNCI SETELAN ANTI REFRESH ---
query_params = st.query_params
default_tf = query_params.get("tf", "1 Hari (Daily)")
default_src = query_params.get("src", "Close (Penutupan)")
try:
    default_len = int(query_params.get("len", "2"))
except:
    default_len = 2

tf_options = ["1 Hari (Daily)", "4 Jam (4h)", "1 Jam (1h)"]
src_options = ["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"]
tf_index = tf_options.index(default_tf) if default_tf in tf_options else 0
src_index = src_options.index(default_src) if default_src in src_options else 0

# Tampilan Menu Pengaturan Utama
col1, col2, col3 = st.columns(3)
with col1:
    tf_pilihan = st.selectbox("Jangka Waktu (Timeframe):", options=tf_options, index=tf_index)
with col2:
    src_pilihan = st.selectbox("Sumber Data (Source):", options=src_options, index=src_index)
with col3:
    length_hma = st.slider("Panjang HMA (Length):", min_value=2, max_value=50, value=default_len, step=1)

st.query_params.update(tf=tf_pilihan, src=src_pilihan, len=str(length_hma))

src_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}
src_aktif = src_map[src_pilihan]
interval_map = {"1 Hari (Daily)": "1d", "4 Jam (4h)": "4h", "1 Jam (1h)": "1h"}
period_map = {"1 Hari (Daily)": "500d", "4 Jam (4h)": "60d", "1 Jam (1h)": "30d"}

@st.cache_data(ttl=30)
def get_crypto_data(p, i):
    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(period=p, interval=i)
    df = df.reset_index()
    df = df.rename(columns={'Date': 'date', 'Datetime': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'})
    return df[['date', 'open', 'high', 'low', 'close']]

try:
    df = get_crypto_data(period_map[tf_pilihan], interval_map[tf_pilihan])
    
    # --- HITUNG INDIKATOR ---
    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    df['rsi'] = ta.rsi(df['close'], length=14)
    
    # Logika dasar perubahan arah HHMA
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = (~df['is_green']) & df['is_green'].shift(1).fillna(False)

    # --- PENINGKATAN AKURASI: FILTER KONFIRMASI TREND DENGAN RSI ---
    df['filtered_buy'] = df['raw_buy'] & (df['rsi'] < 65)
    df['filtered_sell'] = df['raw_sell'] & (df['rsi'] > 35)

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    # Sistem pengunci status agar sinyal bergantian secara akurat
    for i in range(len(df)):
        if df.loc[i, 'filtered_buy'] and last_signal != 1:
            df.loc[i, 'buy_signal'] = True
            last_signal = 1
        elif df.loc[i, 'filtered_sell'] and last_signal != -1:
            df.loc[i, 'sell_signal'] = True
            last_signal = -1

    # Sinyal Mundur 1 Balok (offset=-1) untuk visualisasi di grafik
    df['display_buy'] = df['buy_signal'].shift(-1)
    df['display_sell'] = df['sell_signal'].shift(-1)

    # --- HITUNG STATISTIK AKURASI WIN RATE BARU ---
    trades = []
    active_trade = None
    for i in range(len(df)):
        if df.loc[i, 'buy_signal']:
            active_trade = df.loc[i, 'close']
        elif df.loc[i, 'sell_signal'] and active_trade is not None:
            profit = ((df.loc[i, 'close'] - active_trade) / active_trade) * 100
            trades.append(profit)
            active_trade = None
            
    win_rate = 0
    if len(trades) > 0:
        wins = len([t for t in trades if t > 0])
        win_rate = (wins / len(trades)) * 100

    # Tampilan Papan Informasi Atas
    latest_row = df.iloc[-2]
    current_price = df.iloc[-1]['close']
    
    m1, m2 = st.columns(2)
    with m1:
        st.metric(label=f"Harga BTC Live ({tf_pilihan})", value=f"${current_price:,.2f}")
    with m2:
        st.metric(label="Win Rate Akurasi Setelah Difilter", value=f"{win_rate:.1f}%", delta=f"{len(trades)} Sinyal Valid")

    if df.iloc[-1]['display_buy'] or df.iloc[-2]['buy_signal']:
        st.success(f"🟢 **SINYAL TERBARU: BUY** pada harga ${latest_row['close']:,.2f} (Tren Akurat)")
    elif df.iloc[-1]['display_sell'] or df.iloc[-2]['sell_signal']:
        st.error(f"🔴 **SINYAL TERBARU: SELL** pada harga ${latest_row['close']:,.2f} (Tren Akurat)")
    else:
        st.info("⚪ Status Saat Ini: Mengikuti Tren Berjalan (Hold / Menunggu Konfirmasi)")

    # --- GRAFIK PANDUAN BERSIH (TERPISAH / TIDAK BERTUMPUK) ---
    # Membuat 2 baris grafik terpisah: Atas untuk Candlestick, Bawah untuk RSI
    fig = make_subplots(
        rows=2, cols=1, 
        shared_xaxes=True, 
        row_heights=[0.7, 0.3], 
        vertical_spacing=0.08
    )
    
    # Panel Atas: Candlestick Utama & Garis HHMA
    fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="BTC/USD", opacity=0.4), row=1, col=1)
    
    for i in range(1, len(df)):
        color = "green" if df.loc[i, 'is_green'] else "red"
        fig.add_trace(go.Scatter(x=df['date'].iloc[i-1:i+1], y=df['hma'].iloc[i-1:i+1], mode='lines', line=dict(color=color, width=3), showlegend=False), row=1, col=1)

    # Plot Panah Sinyal Akurat di Panel Atas
    buy_plots = df[df['display_buy'] == True]
    fig.add_trace(go.Scatter(x=buy_plots['date'], y=buy_plots['hma'], mode='markers', marker=dict(symbol='triangle-up', size=16, color='green'), name="Sinyal BUY Valid"), row=1, col=1)

    sell_plots = df[df['display_sell'] == True]
    fig.add_trace(go.Scatter(x=sell_plots['date'], y=sell_plots['hma'], mode='markers', marker=dict(symbol='triangle-down', size=16, color='red'), name="Sinyal SELL Valid"), row=1, col=1)

    # Panel Bawah: Garis Indikator RSI Terpisah
    fig.add_trace(go.Scatter(x=df['date'], y=df['rsi'], mode='lines', line=dict(color='orange', width=2), name="RSI (Filter)"), row=2, col=1)
    fig.add_hline(y=65, line_dash="dash", line_color="red", row=2, col=1)
    fig.add_hline(y=35, line_dash="dash", line_color="green", row=2, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False, height=650, template="plotly_dark", margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # --- TABEL RIWAYAT TRANSAKSI AKTUAL ---
    st.subheader("📋 Riwayat Sinyal Trading Hasil Filter")
    df_signals = df[(df['buy_signal'] == True) | (df['sell_signal'] == True)].copy()
    df_signals['Jenis Sinyal'] = df_signals['buy_signal'].apply(lambda x: "🟢 BUY" if x else "🔴 SELL")
    df_signals['Waktu Sinyal'] = df_signals['date'].dt.strftime('%Y-%m-%d %H:%M')
    df_signals = df_signals.rename(columns={'close': 'Harga Eksekusi (USD)'})
    
    st.dataframe(
        df_signals[['Waktu Sinyal', 'Jenis Sinyal', 'Harga Eksekusi (USD)']].sort_index(ascending=False).head(10),
        use_container_width=True, hide_index=True
    )

except Exception as e:
    st.error(f"Gagal memuat data. Error: {e}")
