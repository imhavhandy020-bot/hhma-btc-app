import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time

# --- FUNGSI INDIKATOR HHMA ---
def calculate_wma(series, period):
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def calculate_hma(series, period):
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    wma_half = calculate_wma(series, half_period)
    wma_full = calculate_wma(series, period)
    raw_hma = (2 * wma_half) - wma_full
    return calculate_wma(raw_hma, sqrt_period)

# --- 1. DEKLARASI NILAI AWAL (HANYA BERJALAN 1x SAAT BOT DIBUKA) ---
if 'api_key' not in st.session_state: st.session_state['api_key'] = ""
if 'secret_key' not in st.session_state: st.session_state['secret_key'] = ""
if 'symbol' not in st.session_state: st.session_state['symbol'] = "BTC/IDR"
if 'timeframe' not in st.session_state: st.session_state['timeframe'] = "5m"
if 'fast_period' not in st.session_state: st.session_state['fast_period'] = 9
if 'slow_period' not in st.session_state: st.session_state['slow_period'] = 20
if 'trade_amount' not in st.session_state: st.session_state['trade_amount'] = 50000
if 'stop_loss_pct' not in st.session_state: st.session_state['stop_loss_pct'] = 2.0
if 'refresh_interval' not in st.session_state: st.session_state['refresh_interval'] = 30
if 'last_buy_price' not in st.session_state: st.session_state['last_buy_price'] = 0.0

# --- CONFIG APLIKASI ---
st.set_page_config(page_title="Indodax Advanced Bot", layout="wide")
st.title("📈 Indodax Permanent Settings Bot (HHMA, Chart & Stop Loss)")

# --- 2. PANEL SIDEBAR MENGGUNAKAN MODAL KUNCI 'key=' AGAR DATA PERMANEN ---
st.sidebar.header("🔑 Kredensial Indodax")
st.sidebar.text_input("API Key", type="password", key="api_key")
st.sidebar.text_input("Secret Key", type="password", key="secret_key")

st.sidebar.header("⚙️ Pengaturan Bot")
st.sidebar.text_input("Simbol Trading", key="symbol")
st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "1d"], index=1, key="timeframe")
st.sidebar.number_input("HHMA Cepat", step=1, key="fast_period")
st.sidebar.number_input("HHMA Lambat (HHMA20)", step=1, key="slow_period")
st.sidebar.number_input("Jumlah Beli (IDR)", step=10000, key="trade_amount")

st.sidebar.header("🛡️ Manajemen Risiko")
st.sidebar.number_input("Stop Loss (%)", step=0.5, key="stop_loss_pct")
st.sidebar.number_input("Harga Beli Terakhir (IDR)", step=100.0, key="last_buy_price")

st.sidebar.header("⏱️ Interval Pembaruan")
st.sidebar.slider("Interval Cek (Detik)", min_value=10, max_value=300, step=10, key="refresh_interval")

# --- INISIALISASI API INDODAX ---
exchange = None
if st.session_state.api_key and st.session_state.secret_key:
    exchange = ccxt.indodax({
        'apiKey': st.session_state.api_key,
        'secret': st.session_state.secret_key,
        'enableRateLimit': True,
    })
    st.sidebar.success("✅ API Kunci Terkunci & Aktif!")
else:
    st.sidebar.warning("⚠️ Masukkan API & Secret Key untuk memulai.")

# --- 3. AREA MONITORING PASAR & TRADING BOT (AUTO REFRESH) ---
# Menggunakan variabel session_state langsung agar interval update sinkron secara permanen
@st.fragment(run_every=st.session_state.refresh_interval)
def run_trading_bot():
    if not exchange:
        st.info("Menunggu input API Key dan Secret Key yang valid di panel samping kiri...")
        return
        
    try:
        # Menampilkan indikator waktu penyegaran data saat ini
        st.caption(f"🔄 Sinkronisasi Data Terakhir: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Mengambil data saldo akun
        balance = exchange.fetch_balance()
        symbol_split = st.session_state.symbol.split('/')
        base_asset = symbol_split[0]
        quote_asset = symbol_split[1] if len(symbol_split) > 1 else 'IDR'
        
        saldo_idr = balance['total'].get(quote_asset, 0)
        saldo_kripto = balance['total'].get(base_asset, 0)
        
        st.subheader("💰 Informasi Saldo Terkini")
        col_bal1, col_bal2 = st.columns(2)
        col_bal1.metric(f"Saldo {quote_asset}", f"{saldo_idr:,.0f} IDR")
        col_bal2.metric(f"Saldo {base_asset}", f"{saldo_kripto:.8f}")

        # 2. Mengambil data Candlestick pasar
        ohlcv = exchange.fetch_ohlcv(st.session_state.symbol, st.session_state.timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Kalkulasi pergerakan indikator HHMA
        df['hhma_fast'] = calculate_hma(df['close'], int(st.session_state.fast_period))
        df['hhma_slow'] = calculate_hma(df['close'], int(st.session_state.slow_period))
        
        latest_idx = df.index[-1]
        prev_idx = df.index[-2]
        current_close = df.loc[latest_idx, 'close']
        
        # 3. GRAFIK LIVE CHART INTERAKTIF (PLOTLY)
        st.subheader(f"📊 Live Chart: {st.session_state.symbol} ({st.session_state.timeframe})")
        fig = go.Figure()
        
        # Menambahkan data candlestick
        fig.add_trace(go.Candlestick(
            x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            name='Harga Pasar'
        ))
        # Menambahkan plot garis indikator HHMA Fast dan Slow
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['hhma_fast'], line=dict(color='#FFA500', width=1.5), name='HHMA Cepat'))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['hhma_slow'], line=dict(color='#1E90FF', width=2), name='HHMA Lambat (20)'))
        
        fig.update_layout(xaxis_rangeslider_visible=False, height=450, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # 4. LOGIKA ANALISIS SINYAL & STOP LOSS
        is_buy_signal = (df.loc[latest_idx, 'hhma_fast'] > df.loc[latest_idx, 'hhma_slow']) and \
                         (df.loc[prev_idx, 'hhma_fast'] <= df.loc[prev_idx, 'hhma_slow'])
                         
        is_sell_signal = (df.loc[latest_idx, 'hhma_fast'] < df.loc[latest_idx, 'hhma_slow']) and \
                          (df.loc[prev_idx, 'hhma_fast'] >= df.loc[prev_idx, 'hhma_slow'])

        # Deteksi otomatis pemicu Stop Loss
        is_stop_loss_triggered = False
        if st.session_state.last_buy_price > 0:
            persentase_turun = ((st.session_state.last_buy_price - current_close) / st.session_state.last_buy_price) * 100
            if persentase_turun >= st.session_state.stop_loss_pct:
                is_stop_loss_triggered = True

        # Tampilkan parameter metrik harga saat ini
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("Harga Terkini", f"{current_close:,.0f} IDR")
        col_p2.metric("Nilai HHMA Fast", f"{df.loc[latest_idx, 'hhma_fast']:,.2f}")
        col_p3.metric("Nilai HHMA Slow", f"{df.loc[latest_idx, 'hhma_slow']:,.2f}")

        # 5. MATRIKS EKSEKUSI TRADING OTOMATIS
        st.subheader("⚡ Status Eksekusi Sistem")
        
        if is_stop_loss_triggered:
            st.error(f"🚨 KRITIS: Batas Stop Loss {st.session_state.stop_loss_pct}% terlewati! Menjual aset...")
            if saldo_kripto > 0.0001:
                order = exchange.create_market_sell_order(st.session_state.symbol, saldo_kripto)
                st.success(f"💥 STOP LOSS DIEKSEKUSI! ID Order: {order['id']}")
                st.session_state.last_buy_price = 0.0  # Mengosongkan data riwayat harga beli
            else:
                st.error("Gagal melakukan stop loss: Tidak ada saldo koin yang tersedia.")
        
        elif is_buy_signal:
            st.warning("🔴 Sinyal Golden Cross (BUY) Terdeteksi! Membuka posisi...")
            if saldo_idr >= st.session_state.trade_amount:
                amount_to_buy = st.session_state.trade_amount / current_close
                order = exchange.create_market_buy_order(st.session_state.symbol, amount_to_buy)
                st.success(f"✅ Pembelian Berhasil! ID Order: {order['id']}")
                st.session_state.last_buy_price = current_close  # Mengunci harga beli terbaru secara permanen
            else:
                st.error("Pembelian gagal: Saldo rupiah tidak mencukupi.")
                
        elif is_sell_signal:
            st.warning("🟢 Sinyal Death Cross (SELL) Terdeteksi! Menutup posisi...")
            if saldo_kripto > 0.0001:
                order = exchange.create_market_sell_order(st.session_state.symbol, saldo_kripto)
                st.success(f"✅ Penjualan Berhasil! ID Order: {order['id']}")
                st.session_state.last_buy_price = 0.0
            else:
                st.error("Penjualan gagal: Anda tidak memegang koin ini.")
        else:
            st.info("⌛ Kondisi Pasar: HOLD (Menunggu konfirmasi sinyal indikator atau pergerakan Stop Loss).")

    except Exception as e:
        st.error(f"Koneksi/API Error: {e}")

# Eksekusi fungsi monitoring
run_trading_bot()
