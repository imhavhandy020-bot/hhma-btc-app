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

# Panel Menu Pengaturan
col1, col2, col3, col4 = st.columns(4)
with col1:
    tf_options = ["1 Hari (Daily)", "4 Jam (4h)", "1 Jam (1h)"]
    tf_index = tf_options.index(default_tf) if default_tf in tf_options else 1
    tf_pilihan = st.selectbox("Jangka Waktu (Timeframe):", options=tf_options, index=tf_index)
with col2:
    src_options = ["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"]
    src_index = src_options.index(default_src) if default_src in src_options else 0
    src_pilihan = st.selectbox("Sumber Data (Source):", options=src_options, index=src_index)
with col3:
    length_hma = st.slider("Panjang HMA (Length):", min_value=2, max_value=50, value=default_len, step=1)
with col4:
    jumlah_tampilan = st.slider("Jumlah Lilin di Layar:", min_value=10, max_value=300, value=100, step=10)

# --- PANEL KALKULATOR MODAL (SIDEBAR) ---
st.sidebar.header("💰 Pengaturan Kalkulator Finansial")
modal_awal = st.sidebar.number_input("Modal Trading Anda ($ USD):", min_value=10, value=1000, step=100)
leverage = st.sidebar.slider("Leverage (Multiplier):", min_value=1, max_value=50, value=1, step=1)

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
    
    df['is_green'] = df['hma'] >= df['hma'].shift(1)
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = (~df['is_green']) & df['is_green'].shift(1).fillna(False)

    # --- EKSEKUSI FILTER LEVEL TINGGI (ULTRA SHIELD) ---
    df['high_accuracy_buy'] = df['raw_buy'] & (df['close'] > df['ema_200']) & (df['rsi'] < 60) & (df['atr'] > df['atr_ma'])
    df['high_accuracy_sell'] = df['raw_sell'] & (df['close'] < df['ema_200']) & (df['rsi'] > 40) & (df['atr'] > df['atr_ma'])

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

    # PERBAIKAN: Menghapus .shift(-1) agar status sinyal real-time sinkron
    df['display_buy'] = df['buy_signal']
    df['display_sell'] = df['sell_signal']

    # --- MATRIKS BACKTEST PRESISI UTAMA ---
    trades_list = []  
    active_trade = None
    target_tp = 1.045  
    target_sl = 0.985  

    for i in df.index:
        if df.at[i, 'buy_signal']:
            if active_trade is not None:
                loss_pct = ((df.at[i, 'close'] - active_trade['entry_price']) / active_trade['entry_price']) * 100
                final_pct = max(loss_pct, -1.5) * leverage
                active_trade['status'] = "Selesai (Cut Sinyal Kebalikan)"
                active_trade['profit_pct'] = final_pct
                active_trade['profit_usd'] = (final_pct / 100) * modal_awal
                trades_list.append(active_trade)

            active_trade = {
                'waktu_entry': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'),
                'jenis': "🟢 BUY",
                'entry_price': df.at[i, 'close'],
                'status': "Berjalan (Running)",
                'profit_pct': 0.0,
                'profit_usd': 0.0
            }

        elif active_trade is not None:
            high_match = df.at[i, 'high'] >= (active_trade['entry_price'] * target_tp)
            low_match = df.at[i, 'low'] <= (active_trade['entry_price'] * target_sl)
            
            if high_match:
                final_pct = 4.5 * leverage
                active_trade['status'] = "🎯 Take Profit"
                active_trade['profit_pct'] = final_pct
                active_trade['profit_usd'] = (final_pct / 100) * modal_awal
                trades_list.append(active_trade)
                active_trade = None
            elif low_match or df.at[i, 'sell_signal']:
                loss_pct = ((df.at[i, 'close'] - active_trade['entry_price']) / active_trade['entry_price']) * 100
                final_pct = max(loss_pct, -1.5) * leverage
                active_trade['status'] = "🛑 Stop Loss / Exit"
                active_trade['profit_pct'] = final_pct
                active_trade['profit_usd'] = (final_pct / 100) * modal_awal
                trades_list.append(active_trade)
                active_trade = None

    if active_trade is not None:
        trades_list.append(active_trade)

    # Rekap data metrik
    total_trades_done = [t for t in trades_list if t['status'] != "Berjalan (Running)"]
    win_rate = 0
    total_profit_pct = sum([t['profit_pct'] for t in total_trades_done])
    estimasi_profit_usd = (total_profit_pct / 100) * modal_awal

    if len(total_trades_done) > 0:
        wins = len([t for t in total_trades_done if t['profit_pct'] > 0])
        win_rate = (wins / len(total_trades_done)) * 100

    current_price = df.iloc[-1]['close']
    
    # PERBAIKAN: Deteksi otomatis sinyal terakhir untuk ditaruh di papan metrik
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

    # --- PAPAN METRIK UTAMA (DIURUTKAN ULANG) ---
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.metric(label=f"Harga BTC Live ({tf_pilihan})", value=f"${current_price:,.2f}")
    with m2:
        # Menampilkan status sinyal aktif paling baru hasil filter algoritma
        st.metric(label="Sinyal Aktif Saat Ini", value=status_sinyal, delta=f"Eksekusi: {harga_sinyal}")
    with m3:
        st.metric(label="Waktu Sinyal Terakhir", value=waktu_sinyal)
    with m4:
        st.metric(label="Win Rate & Estimasi Profit", value=f"{win_rate:.1f}%", delta=f"${estimasi_profit_usd:+,.2f} ({total_profit_pct:+.1f}%)")

    # Tampilkan tabel data transaksi
    if trades_list:
        st.subheader("📜 Riwayat Transaksi Backtest")
        st.dataframe(pd.DataFrame(trades_list), use_container_width=True)

except Exception as e:
    st.error(f"Terjadi kesalahan teknis sistem: {e}")
