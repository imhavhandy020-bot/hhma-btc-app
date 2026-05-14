import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go

st.set_page_config(page_title="HHMA Renko BTC", layout="wide")
st.title("📊 Aplikasi Sinyal HHMA Renko 400 BTC")

@st.cache_data(ttl=60)
def get_crypto_data():
    # Mengunduh data Bitcoin harian (1d) sebanyak 500 bar terakhir lewat pustaka resmi Yahoo Finance
    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(period="500d", interval="1d")
    
    # Merapikan struktur index tanggal menjadi kolom data biasa
    df = df.reset_index()
    df = df.rename(columns={
        'Date': 'date',
        'Open': 'open',
        'High': 'high',
        'Low': 'low',
        'Close': 'close'
    })
    return df[['date', 'open', 'high', 'low', 'close']]

try:
    df = get_crypto_data()
    length = 2
    df['hma'] = ta.hma(df['close'], length=length)
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

    # Sinyal Mundur 1 Balok (offset=-1) sesuai logika asli TradingView Anda
    df['display_buy'] = df['buy_signal'].shift(-1)
    df['display_sell'] = df['sell_signal'].shift(-1)

    latest_row = df.iloc[-2]
    current_price = df.iloc[-1]['close']
    
    st.metric(label="Harga Bitcoin Live (USD)", value=f"${current_price:,.2f}")

    if df.iloc[-1]['display_buy'] or df.iloc[-2]['buy_signal']:
        st.success(f"🟢 **SINYAL TERBARU: BUY** pada harga ${latest_row['close']:,.2f}")
    elif df.iloc[-1]['display_sell'] or df.iloc[-2]['sell_signal']:
        st.error(f"🔴 **SINYAL TERBARU: SELL** pada harga ${latest_row['close']:,.2f}")
    else:
        st.info("⚪ Status Saat Ini: Mengikuti Tren Berjalan (Hold)")

    fig = go.Figure()
    
    # Grafik Candlestick Utama
    fig.add_trace(go.Candlestick(
        x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name="BTC/USD", opacity=0.3
    ))

    # Segmentasi Garis HMA Berwarna Merah / Hijau Kontinu
    for i in range(1, len(df)):
        color = "green" if df.loc[i, 'is_green'] else "red"
        fig.add_trace(go.Scatter(
            x=df['date'].iloc[i-1:i+1], y=df['hma'].iloc[i-1:i+1],
            mode='lines', line=dict(color=color, width=3), showlegend=False
        ))

    # Plot Panah Hijau BUY Mundur 1 Balok
    buy_plots = df[df['display_buy'] == True]
    fig.add_trace(go.Scatter(
        x=buy_plots['date'], y=buy_plots['hma'],
        mode='markers', marker=dict(symbol='triangle-up', size=15, color='green'), name="Sinyal BUY"
    ))

    # Plot Panah Merah SELL Mundur 1 Balok
    sell_plots = df[df['display_sell'] == True]
    fig.add_trace(go.Scatter(
        x=sell_plots['date'], y=sell_plots['hma'],
        mode='markers', marker=dict(symbol='triangle-down', size=15, color='red'), name="Sinyal SELL"
    ))

    fig.update_layout(xaxis_rangeslider_visible=False, height=550, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

except Exception as e:
    st.error(f"Gagal memuat data. Error: {e}")
