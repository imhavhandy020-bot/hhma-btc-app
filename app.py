import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="HHMA Renko BTC", layout="wide")
st.title("📊 Aplikasi Sinyal HHMA Renko 400 BTC")

# MEMBUAT KOLOM INPUT DI LAYAR UTAMA
col1, col2, col3 = st.columns(3)

with col1:
    tf_pilihan = st.selectbox(
        "Pilih Jangka Waktu (Timeframe):",
        options=["1 Hari (Daily)", "4 Jam (4h)", "1 Jam (1h)"],
        index=0
    )

with col2:
    src_pilihan = st.selectbox(
        "Sumber Data Indikator (Source):",
        options=["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"],
        index=0
    )

with col3:
    # --- FITUR BARU: TOMBOL GESER UNTUK MENGUBAH PANJANG HMA ---
    length_hma = st.slider(
        "Panjang HMA (Length):",
        min_value=2,
        max_value=50,
        value=2,  # Angka bawaan tetap 2 sesuai skrip asli Anda
        step=1
    )

src_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}
src_aktif = src_map[src_pilihan]

interval_map = {"1 Hari (Daily)": "1d", "4 Jam (4h)": "4h", "1 Jam (1h)": "1h"}
period_map = {"1 Hari (Daily)": "500d", "4 Jam (4h)": "60d", "1 Jam (1h)": "30d"}
interval_aktif = interval_map[tf_pilihan]
period_aktif = period_map[tf_pilihan]

@st.cache_data(ttl=60)
def get_crypto_data(p, i):
    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(period=p, interval=i)
    df = df.reset_index()
    df = df.rename(columns={'Date': 'date', 'Datetime': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close'})
    return df[['date', 'open', 'high', 'low', 'close']]

try:
    df = get_crypto_data(period_aktif, interval_aktif)
    
    # Menghitung HMA menggunakan nilai variabel dari Slider (length_hma)
    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = (~df['is_green']) & df['is_green'].shift(1).fillna(False)

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    for i in range(len(df)):
        if df.loc[i, 'raw_buy'] and last_signal != 1:
            df.loc[i, 'buy_signal'] = True
            last_signal = 1
        elif df.loc[i, 'raw_sell'] and last_signal != -1:
            df.loc[i, 'sell_signal'] = True
            last_signal = -1

    df['display_buy'] = df['buy_signal'].shift(-1)
    df['display_sell'] = df['sell_signal'].shift(-1)

    latest_row = df.iloc[-2]
    current_price = df.iloc[-1]['close']
    
    st.metric(label=f"Harga Bitcoin Live ({tf_pilihan})", value=f"${current_price:,.2f}")

    if df.iloc[-1]['display_buy'] or df.iloc[-2]['buy_signal']:
        st.success(f"🟢 **SINYAL TERBARU: BUY** pada harga ${latest_row['close']:,.2f} (HMA Length: {length_hma})")
    elif df.iloc[-1]['display_sell'] or df.iloc[-2]['sell_signal']:
        st.error(f"🔴 **SINYAL TERBARU: SELL** pada harga ${latest_row['close']:,.2f} (HMA Length: {length_hma})")
    else:
        st.info(f"⚪ Status Saat Ini: Mengikuti Tren Berjalan (Hold HMA Length: {length_hma})")

    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="BTC/USD", opacity=0.3))

    for i in range(1, len(df)):
        color = "green" if df.loc[i, 'is_green'] else "red"
        fig.add_trace(go.Scatter(x=df['date'].iloc[i-1:i+1], y=df['hma'].iloc[i-1:i+1], mode='lines', line=dict(color=color, width=3), showlegend=False))

    buy_plots = df[df['display_buy'] == True]
    fig.add_trace(go.Scatter(x=buy_plots['date'], y=buy_plots['hma'], mode='markers', marker=dict(symbol='triangle-up', size=15, color='green'), name="Sinyal BUY"))

    sell_plots = df[df['display_sell'] == True]
    fig.add_trace(go.Scatter(x=sell_plots['date'], y=sell_plots['hma'], mode='markers', marker=dict(symbol='triangle-down', size=15, color='red'), name="Sinyal SELL"))

    fig.update_layout(xaxis_rangeslider_visible=False, height=550, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Gagal memuat data. Error: {e}")
