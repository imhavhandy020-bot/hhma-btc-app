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
default_tf = query_params.get("tf", "4 Jam (4h)")  
default_src = query_params.get("src", "Close (Penutupan)")
try:
    default_len = int(query_params.get("len", "20"))  
except:
    default_len = 20

tf_options = ["1 Hari (Daily)", "4 Jam (4h)", "1 Jam (1h)"]
src_options = ["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"]
tf_index = tf_options.index(default_tf) if default_tf in tf_options else 1
src_index = src_options.index(default_src) if default_src in src_options else 0

# Tambahan Kolom ke-4 untuk Mengatur Jumlah Tampilan Transaksi di Layar
col1, col2, col3, col4 = st.columns(4)
with col1:
    tf_pilihan = st.selectbox("Jangka Waktu (Timeframe):", options=tf_options, index=tf_index)
with col2:
    src_pilihan = st.selectbox("Sumber Data (Source):", options=src_options, index=src_index)
with col3:
    length_hma = st.slider("Panjang HMA (Length):", min_value=2, max_value=50, value=default_len, step=1)
with col4:
    jumlah_tampilan = st.slider("Jumlah Lilin di Layar:", min_value=10, max_value=300, value=100, step=10)

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
    return df[['date', 'open', 'high', 'low', 'close', 'volume']]

def putar_alarm(jenis_sinyal):
    if jenis_sinyal == "BUY":
        audio_url = "google.com"
    else:
        audio_url = "google.com"
        
    js_code = f"""
    <script>
        var audio = new Audio('{audio_url}');
        audio.play().catch(function(error) {{
            console.log("Autoplay diblokir browser sebelum interaksi pengguna: ", error);
        }});
    </script>
    """
    components.html(js_code, height=0, width=0)

try:
    df = get_crypto_data(period_map[tf_pilihan], interval_map[tf_pilihan])
    
    # --- PENGHITUNGAN ALGORITMA FILTER BERLAPIS ---
    df['hma'] = ta.hma(df[src_aktif], length=length_hma)
    df['ema_200'] = ta.ema(df['close'], length=200)  
    df['rsi'] = ta.rsi(df['close'], length=14)        
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=14) 
    df['atr_ma'] = ta.sma(df['atr'], length=20)
    
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = (~df['is_green']) & df['is_green'].shift(1).fillna(False)

    # --- EKSEKUSI FILTER LEVEL TINGGI (ULTRA SHIELD) ---
    df['high_accuracy_buy'] = df['raw_buy'] & (df['close'] > df['ema_200']) & (df['rsi'] < 60) & (df['atr'] > df['atr_ma'])
    df['high_accuracy_sell'] = df['raw_sell'] & (df['close'] < df['ema_200']) & (df['rsi'] > 40) & (df['atr'] > df['atr_ma'])

    df['buy_signal'] = False
    df['sell_signal'] = False
    last_signal = 0

    for i in range(len(df)):
        if df.loc[i, 'high_accuracy_buy'] and last_signal != 1:
            df.loc[i, 'buy_signal'] = True
            last_signal = 1
        elif df.loc[i, 'high_accuracy_sell'] and last_signal != -1:
            df.loc[i, 'sell_signal'] = True
            last_signal = -1

    df['display_buy'] = df['buy_signal'].shift(-1)
    df['display_sell'] = df['sell_signal'].shift(-1)

    # --- MATRIKS BACKTEST PRESISI TINGGI ---
    trades = []
    active_trade_price = None
    target_tp = 1.045  
    target_sl = 0.985  

    live_tp_price = None
    live_sl_price = None
    live_entry_price = None

    for i in range(len(df)):
        if df.loc[i, 'buy_signal']:
            active_trade_price = df.loc[i, 'close']
            live_entry_price = active_trade_price
            live_tp_price = active_trade_price * target_tp
            live_sl_price = active_trade_price * target_sl
        elif active_trade_price is not None:
            high_match = df.loc[i, 'high'] >= (active_trade_price * target_tp)
            low_match = df.loc[i, 'low'] <= (active_trade_price * target_sl)
            
            if high_match:
                trades.append(4.5)
                active_trade_price = None
            elif low_match or df.loc[i, 'sell_signal']:
                loss_pct = ((df.loc[i, 'close'] - active_trade_price) / active_trade_price) * 100
                trades.append(max(loss_pct, -1.5))
                active_trade_price = None
            
    win_rate = 0
    if len(trades) > 0:
        wins = len([t for t in trades if t > 0])
        win_rate = (wins / len(trades)) * 100

    latest_row = df.iloc[-2]
    current_price = df.iloc[-1]['close']
    
    m1, m2 = st.columns(2)
    with m1:
        st.metric(label=f"Harga BTC Live ({tf_pilihan})", value=f"${current_price:,.2f}")
    with m2:
        st.metric(label="Persentase Akurasi Sistem Maksimal", value=f"{win_rate:.1f}%", delta=f"{len(trades)} Sinyal Lolos Sensor")

    is_latest_buy = df.iloc[-1]['display_buy'] or df.iloc[-2]['buy_signal']
    is_latest_sell = df.iloc[-1]['display_sell'] or df.iloc[-2]['sell_signal']

    if is_latest_buy:
        st.success(f"🟢 **SINYAL TERBARU: BUY** pada harga ${latest_row['close']:,.2f} (Konfirmasi Tren Institusional)")
        putar_alarm("BUY")  
    elif is_latest_sell:
        st.error(f"🔴 **SINYAL TERBARU: SELL** pada harga ${latest_row['close']:,.2f} (Konfirmasi Tren Institusional)")
        putar_alarm("SELL")  
    else:
        st.info("⚪ Status Saat Ini: Hold Tren (Menunggu Sinyal Berkekuatan Tinggi Luar Biasa)")

    # --- PEMOTONGAN DATA UNTUK FOKUS BEBERAPA TRANSAKSI TERAKHIR ---
    df_grafik = df.tail(jumlah_tampilan).reset_index(drop=True)

    # --- GRAFIK SEGMEN BERSIH TERPISAH ---
    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, row_heights=[0.75, 0.25], vertical_spacing=0.06)
    
    fig.add_trace(go.Candlestick(x=df_grafik['date'], open=df_grafik['open'], high=df_grafik['high'], low=df_grafik['low'], close=df_grafik['close'], name="BTC/USD", opacity=0.3), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_grafik['date'], y=df_grafik['ema_200'], mode='lines', line=dict(color='white', width=1.5, dash='dot'), name="EMA 200 (Tren Makro)"), row=1, col=1)
    
    for i in range(1, len(df_grafik)):
        color = "green" if df_grafik.loc[i, 'is_green'] else "red"
        fig.add_trace(go.Scatter(x=df_grafik['date'].iloc[i-1:i+1], y=df_grafik['hma'].iloc[i-1:i+1], mode='lines', line=dict(color=color, width=3), showlegend=False), row=1, col=1)

    buy_plots = df_grafik[df_grafik['display_buy'] == True]
    fig.add_trace(go.Scatter(x=buy_plots['date'], y=buy_plots['hma'], mode='markers', marker=dict(symbol='triangle-up', size=16, color='green'), name="Sinyal BUY Maksimal"), row=1, col=1)

    sell_plots = df_grafik[df_grafik['display_sell'] == True]
    fig.add_trace(go.Scatter(x=sell_plots['date'], y=sell_plots['hma'], mode='markers', marker=dict(symbol='triangle-down', size=16, color='red'), name="Sinyal SELL Maksimal"), row=1, col=1)

    # Menampilkan garis target TP/SL hanya jika harga entri masuk ke dalam rentang lilin yang dipotong
    if live_entry_price is not None and live_entry_price >= df_grafik['low'].min() and live_entry_price <= df_grafik['high'].max():
        fig.add_hline(y=live_entry_price, line_dash="dash", line_color="#3498db", line_width=1.5, 
                      annotation_text=f"Entry: ${live_entry_price:,.2f}", annotation_position="top right", row=1, col=1)
        fig.add_hline(y=live_tp_price, line_dash="dash", line_color="#2ecc71", line_width=2, 
                      annotation_text=f"Target TP (+4.5%): ${live_tp_price:,.2f}", annotation_position="top right", row=1, col=1)
        fig.add_hline(y=live_sl_price, line_dash="dash", line_color="#e74c3c", line_width=2, 
                      annotation_text=f"Batas SL (-1.5%): ${live_sl_price:,.2f}", annotation_position="bottom right", row=1, col=1)

    fig.add_trace(go.Scatter(x=df_grafik['date'], y=df_grafik['atr'], mode='lines', line=dict(color='magenta', width=2), name="ATR Volatilitas"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_grafik['date'], y=df_grafik['atr_ma'], mode='lines', line=dict(color='yellow', width=1), name="Rata-rata Volatilitas"), row=2, col=1)

    fig.update_layout(xaxis_rangeslider_visible=False, height=650, template="plotly_dark", margin=dict(t=10, b=10))
    st.plotly_chart(fig, use_container_width=True)

    # --- TABEL HISTORY TRANSAKSI (DIBATASI HANYA 5 TRANSAKSI TERAKHIR) ---
    st.subheader("📋 Riwayat Sinyal Khusus Level Maksimal (5 Terakhir)")
    df_signals = df[(df['buy_signal'] == True) | (df['sell_signal'] == True)].copy()
    df_signals['Jenis Sinyal'] = df_signals['buy_signal'].apply(lambda x: "🟢 BUY" if x else "🔴 SELL")
    df_signals['Waktu Sinyal'] = df_signals['date'].dt.strftime('%Y-%m-%d %H:%M')
    df_signals = df_signals.rename(columns={'close': 'Harga Eksekusi (USD)'})
    
    st.dataframe(
        df_signals[['Waktu Sinyal', 'Jenis Sinyal', 'Harga Eksekusi (USD)']].sort_index(ascending=False).head(5),
        use_container_width=True, hide_index=True
    )

except Exception as e:
    st.error(f"Gagal memuat data. Error: {e}")
