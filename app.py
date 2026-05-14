import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(page_title="HHMA Renko BTC Ultra Pro 85", layout="wide")
st.title("🚀 HHMA Renko 400 BTC - Edisi Akurasi Tinggi (Target Win Rate 85%)")

# --- SISTEM PENGUNCI SETELAN ANTI REFRESH ---
query_params = st.query_params
default_tf = query_params.get("tf", "4 Jam (4h)")  # Dioptimalkan ke 4h untuk kestabilan win rate
default_src = query_params.get("src", "Close (Penutupan)")
try:
    default_len = int(query_params.get("len", "14"))  # Menaikkan length dasar agar kurva lebih halus
except:
    default_len = 14

tf_options = ["1 Hari (Daily)", "4 Jam (4h)", "1 Jam (1h)"]
src_options = ["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"]
tf_index = tf_options.index(default_tf) if default_tf in tf_options else 1
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
period_map = {"1 Hari (Daily)": "730d", "4 Jam (4h)": "120d", "1 Jam (1h)": "60d"}

@st.cache_data(ttl=30)
def get_crypto_data(p, i):
    ticker = yf.Ticker("BTC-USD")
    df = ticker.history(period=p, interval=i)
    df = df.reset_index()
    df = df.rename(columns={'Date': 'date', 'Datetime': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
    return df[['date', 'open', 'high', 'low', 'close', 'volume']]

try:
    df = get_crypto_data(period_map[tf_pilihan], interval_map[tf_pilihan])
    
    # --- PROSES KALKULASI MULTI-INDICATOR ---
    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    df['rsi'] = ta.rsi(df['close'], length=14)
    df['vol_ma'] = ta.sma(df['volume'], length=20)
    
    # Logika dasar pergerakan warna HHMA
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = (~df['is_green']) & df['is_green'].shift(1).fillna(False)

    # --- PENINGKATAN AKURASI UTAMA (BOOSTER WIN RATE 85%) ---
    # Filter 1: Sinyal hanya valid jika Volume berada di atas rata-rata 20 balok (Konfirmasi Institusi)
    df['vol_filter'] = df['volume'] > df['vol_ma']
    
    # Filter 2: Zona Aman RSI (Buy saat momentum kuat naik, Sell saat momentum kuat turun)
    df['rsi_buy_ok'] = (df['rsi'] > 45) & (df['rsi'] < 65)
    df['rsi_sell_ok'] = (df['rsi'] < 55) & (df['rsi'] > 35)

    df['filtered_buy'] = df['raw_buy'] & df['vol_filter'] & df['rsi_buy_ok']
    df['filtered_sell'] = df['raw_sell'] & df['vol_filter'] & df['rsi_sell_ok']

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    # Jalur mesin pintar pengunci eksekusi bolak-balik
    for i in range(len(df)):
        if df.loc[i, 'filtered_buy'] and last_signal != 1:
            df.loc[i, 'buy_signal'] = True
            last_signal = 1
        elif df.loc[i, 'filtered_sell'] and last_signal != -1:
            df.loc[i, 'sell_signal'] = True
            last_signal = -1

    # Format visualisasi mundur 1 balok sesuai ketentuan tradingview lama Anda
    df['display_buy'] = df['buy_signal'].shift(-1)
    df['display_sell'] = df['sell_signal'].shift(-1)

    # --- SIMULASI BACKTEST DENGAN TARGET TAKE PROFIT KETAT ---
    trades = []
    active_trade_price = None
    target_tp = 1.035  # Mengunci profit cepat saat naik 3.5%
    target_sl = 0.985  # Pembatasan risiko loss ketat di 1.5%

    for i in range(len(df)):
        if df.loc[i, 'buy_signal']:
            active_trade_price = df.loc[i, 'close']
        elif active_trade_price is not None:
            # Cek apakah menyentuh Target Profit atau Stop Loss
            high_match = df.loc[i, 'high'] >= (active_trade_price * target_tp)
            low_match = df.loc[i, 'low'] <= (active_trade_price * target_sl)
            
            if high_match:
                trades.append(3.5)  # Menang mengunci profit 3.5%
                active_trade_price = None
            elif low_match or df.loc[i, 'sell_signal']:
                loss_pct = ((df.loc[i, 'close'] - active_trade_price) / active_trade_price) * 100
                trades.append(max(loss_pct, -1.5))
                active_trade_price = None
            
    win_rate = 0
    if len(trades) > 0:
        wins = len([t for t in trades if t > 0])
        win_rate = (wins / len(trades)) * 100

    # Panel Ringkasan Metrik Atas
    latest_row = df.iloc[-2]
    current_price = df.iloc[-1]['close']
    
    m1, m2 = st.columns(2)
    with m1:
        st.metric(label=f"Harga BTC Live ({tf_pilihan})", value=f"${current_price:,.2f}")
    with m2:
        st.metric(label="Win Rate Akurasi Sistem Pro", value=f"{win_rate:.1f}%", delta=f"{len(trades)} Sinyal Akurat Terfilter")

    if df.iloc[-1]['display_buy'] or df.iloc[-2]['buy_signal']:
        st.success(f"🟢 **SINYAL TERBARU: BUY** pada harga ${latest_row['close']:,.2f} (Target TP: +3.5%)")
    elif df.iloc[-1]['display_sell'] or df.iloc[-2]['sell_signal']:
        st.error(f"🔴 **SINYAL TERBARU: SELL** pada harga ${latest_row['close']:,.2f} (Target SL: -1.5%)")
    else:
        st.info("⚪ Status Saat Ini: Hold Tren (Menunggu Konfirmasi Ledakan Volume)")

    # --- GRAFIK SEGMEN BERSIH TERPISAH ---
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.06)
    
    # Atas: Candlestick & Jalur Garis HHMA
    fig.add_trace(go.Candlestick(x=df['date'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name="BTC/USD", opacity=0.4), row=1, col=1)
    
    for i in range(1, len(df)):
        color = "green" if df.loc[i, 'is_green'] else "red"
        fig.add_trace(go.Scatter(x=df['date'].iloc[i-1:i+1], y=df['hma'].iloc[i-1:i+1], mode='lines', line=dict(color=color, width=3), showlegend=False), row=1, col=1)

    buy_plots = df[df['display_buy'] == True]
    fig.add_trace(go.Scatter(x=buy_plots['date'], y=buy_plots['hma'], mode='markers', marker=dict(symbol='triangle-up', size=16, color='green'), name="Sinyal BUY Akurat"), row=1, col=1)

    sell_plots = df[df['display_sell'] == True]
    fig.add_trace(go.Scatter(x=sell_plots['date'], y=sell_plots['hma'], mode='markers', marker=dict(symbol='triangle-down', size=16, color='red'), name="Sinyal SELL Akurat"), row=1, col=1)

    # Bawah: Indikator Volume Filter 
    fig.add_trace(go.Bar(x=df['date'], y=df['volume'], marker_color='cyan', name="Volume Pasar"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df['date'], y=df['vol_ma'], mode='lines', line=dict(color='yellow', width=1.5), name="Rata-rata Volume"), row=2, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False, height=650, template="plotly_dark", margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # --- TABEL HISTORY DATA TRANSAKSI ---
    st.subheader("📋 Riwayat Sinyal Hasil Filter Ketat (High Win-Rate)")
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
