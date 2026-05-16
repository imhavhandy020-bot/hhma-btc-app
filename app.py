import streamlit as st
import ccxt
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time

# --- FUNGSI UTILITAS INDIKATOR HHMA ---
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

# --- 1. DEKLARASI STATE AWAL (HANYA DIEKSEKUSI 1X SAAT FORM DIBUKA) ---
if 'api_key' not in st.session_state: st.session_state['api_key'] = ""
if 'secret_key' not in st.session_state: st.session_state['secret_key'] = ""
if 'symbol' not in st.session_state: st.session_state['symbol'] = "BTC/IDR"
if 'timeframe_label' not in st.session_state: st.session_state['timeframe_label'] = "5 Menit"
if 'fast_period' not in st.session_state: st.session_state['fast_period'] = 9
if 'slow_period' not in st.session_state: st.session_state['slow_period'] = 20
if 'trade_amount' not in st.session_state: st.session_state['trade_amount'] = 50000
if 'stop_loss_pct' not in st.session_state: st.session_state['stop_loss_pct'] = 2.0
if 'refresh_interval' not in st.session_state: st.session_state['refresh_interval'] = 30
if 'last_buy_price' not in st.session_state: st.session_state['last_buy_price'] = 0.0

# --- CONFIG APLIKASI ---
st.set_page_config(page_title="Indodax Advanced Bot", layout="wide")
st.title("🤖 Bot Trading Indodax Permanen (HHMA, Chart & Stop Loss)")

# --- 2. PANEL SIDEBAR INPUT DENGAN SISTEM KUNCI PERMANEN ('key=') ---
st.sidebar.header("🔑 Kredensial Indodax")
st.sidebar.text_input("API Key", type="password", key="api_key")
st.sidebar.text_input("Secret Key", type="password", key="secret_key")

st.sidebar.header("⚙️ Pengaturan Bot")
st.sidebar.text_input("Simbol Trading (Contoh: BTC/IDR)", key="symbol")

# FIX ERROR INVALID TIMEFRAME INDODAX
st.sidebar.selectbox(
    "Timeframe", 
    ["1 Menit", "5 Menit", "15 Menit", "1 Jam", "1 Hari"], 
    key="timeframe_label"
)

# Kamus Pemetaan khusus untuk mencocokkan kemauan API Indodax
timeframe_mapping = {
    "1 Menit": "1",
    "5 Menit": "5",
    "15 Menit": "15",
    "1 Jam": "60",
    "1 Hari": "1D"
}
# Konversi label pilihan user ke string parameter yang sah bagi server Indodax
selected_timeframe_api = timeframe_mapping[st.session_state.timeframe_label]

st.sidebar.number_input("HHMA Cepat (Fast Line)", step=1, key="fast_period")
st.sidebar.number_input("HHMA Lambat (HHMA20)", step=1, key="slow_period")
st.sidebar.number_input("Jumlah Transaksi Beli (IDR)", step=10000, key="trade_amount")

st.sidebar.header("🛡️ Manajemen Risiko")
st.sidebar.number_input("Batas Stop Loss (%)", step=0.5, key="stop_loss_pct")
st.sidebar.number_input("Harga Beli Terakhir (Isi Manual / Otomatis)", step=100.0, key="last_buy_price")

st.sidebar.header("⏱️ Durasi Penyegaran")
st.sidebar.slider("Jeda Cek Pasar (Detik)", min_value=10, max_value=300, step=10, key="refresh_interval")

# --- INISIALISASI CONECTOR KE INDODAX ---
exchange = None
if st.session_state.api_key and st.session_state.secret_key:
    exchange = ccxt.indodax({
        'apiKey': st.session_state.api_key,
        'secret': st.session_state.secret_key,
        'enableRateLimit': True,
    })
    st.sidebar.success("✅ Hubungan API Sukses Terkunci!")
else:
    st.sidebar.warning("⚠️ Masukkan kredensial API Key untuk memulai trading.")

# --- 3. PROSES UTAMA (AUTO REFRESH HARGA & SIGNAL EVALUATION) ---
@st.fragment(run_every=st.session_state.refresh_interval)
def run_trading_bot():
    if not exchange:
        st.info("Sistem standby. Menunggu input API Key & Secret Key dimasukkan pada panel kiri.")
        return
        
    try:
        # Menampilkan penanda waktu sinkronisasi data terakhir
        st.caption(f"🔄 Waktu Pembaruan Terakhir: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Tarik Data Saldo Riil Akun Indodax Anda
        balance = exchange.fetch_balance()
        symbol_split = st.session_state.symbol.split('/')
        base_asset = symbol_split[0]
        quote_asset = symbol_split[1] if len(symbol_split) > 1 else 'IDR'
        
        saldo_idr = balance['total'].get(quote_asset, 0)
        saldo_kripto = balance['total'].get(base_asset, 0)
        
        st.subheader("💰 Ringkasan Saldo Akun")
        col_bal1, col_bal2 = st.columns(2)
        col_bal1.metric(f"Saldo {quote_asset}", f"{saldo_idr:,.0f} IDR")
        col_bal2.metric(f"Saldo {base_asset}", f"{saldo_kripto:.8f} {base_asset}")

        # 2. Ambil Riwayat Candlestick Menggunakan Kode Parameter Terkonversi
        ohlcv = exchange.fetch_ohlcv(st.session_state.symbol, selected_timeframe_api, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        # Eksekusi kalkulasi indikator HHMA
        df['hhma_fast'] = calculate_hma(df['close'], int(st.session_state.fast_period))
        df['hhma_slow'] = calculate_hma(df['close'], int(st.session_state.slow_period))
        
        latest_idx = df.index[-1]
        prev_idx = df.index[-2]
        current_close = df.loc[latest_idx, 'close']
        
        # 3. MEMUNCULKAN GRAFIK CANDLESTICK LIVE INTERAKTIF
        st.subheader(f"📊 Live Candlestick & Indikator {st.session_state.symbol}")
        fig = go.Figure()
        
        # Masukkan lilin harga pasar
        fig.add_trace(go.Candlestick(
            x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
            name='Harga Candlestick'
        ))
        # Masukkan garis bantu HHMA Cepat dan Lambat
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['hhma_fast'], line=dict(color='#FFA500', width=1.5), name='HHMA Fast'))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['hhma_slow'], line=dict(color='#1E90FF', width=2), name='HHMA Slow (20)'))
        
        fig.update_layout(xaxis_rangeslider_visible=False, height=450, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # 4. LOGIKA HITUNGAN PERSILANGAN & VALIDASI STOP LOSS
        is_buy_signal = (df.loc[latest_idx, 'hhma_fast'] > df.loc[latest_idx, 'hhma_slow']) and \
                         (df.loc[prev_idx, 'hhma_fast'] <= df.loc[prev_idx, 'hhma_slow'])
                         
        is_sell_signal = (df.loc[latest_idx, 'hhma_fast'] < df.loc[latest_idx, 'hhma_slow']) and \
                          (df.loc[prev_idx, 'hhma_fast'] >= df.loc[prev_idx, 'hhma_slow'])

        # Cek kondisi darurat pemicu penjualan Stop Loss
        is_stop_loss_triggered = False
        if st.session_state.last_buy_price > 0:
            drop_ratio = ((st.session_state.last_buy_price - current_close) / st.session_state.last_buy_price) * 100
            if drop_ratio >= st.session_state.stop_loss_pct:
                is_stop_loss_triggered = True

        # Tampilkan papan metrik harga real-time di bawah grafik
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("Harga Pasar Saat Ini", f"{current_close:,.0f} IDR")
        col_p2.metric("Posisi Line Fast", f"{df.loc[latest_idx, 'hhma_fast']:,.2f}")
        col_p3.metric("Posisi Line Slow (20)", f"{df.loc[latest_idx, 'hhma_slow']:,.2f}")

        # 5. MATRIKS AUTOMATED ORDER EXECUTION SYSTEM
        st.subheader("⚡ Konsol Status Eksekusi Otomatis")
        
        # JALUR UTAMA 1: EKSEKUSI PROTEKSI LOSS DARURAT (STOP LOSS)
        if is_stop_loss_triggered:
            st.error(f"🚨 LIMIT RUGI TERLEWATI! Harga drop di bawah {st.session_state.stop_loss_pct}% dari harga beli.")
            if saldo_kripto > 0.0001:
                order = exchange.create_market_sell_order(st.session_state.symbol, saldo_kripto)
                st.success(f"💥 STOP LOSS SUKSES DIEKSEKUSI! Semua aset berhasil di-cutloss. ID Order: {order['id']}")
                st.session_state.last_buy_price = 0.0  # Reset status harga beli ke nol
            else:
                st.error("Gagal Cut-loss: Saldo koin di dompet kosong.")
        
        # JALUR UTAMA 2: EKSEKUSI ORDER BELI KARENA ADANYA GOLDEN CROSS
        elif is_buy_signal:
            st.warning("🔴 STRATEGI HHMA TERDETEKSI GOLDEN CROSS (BUY SIGNAL)!")
            if saldo_idr >= st.session_state.trade_amount:
                amount_to_buy = st.session_state.trade_amount / current_close
                order = exchange.create_market_buy_order(st.session_state.symbol, amount_to_buy)
                st.success(f"🛒 PEMBELIAN INSTAN BERHASIL! ID Transaksi: {order['id']}")
                st.session_state.last_buy_price = current_close  # Simpan harga beli ke variabel permanent state
            else:
                st.error(f"Gagal Beli: Saldo {quote_asset} Anda kurang dari setelan nominal transaksi.")
                
        # JALUR UTAMA 3: EKSEKUSI ORDER JUAL KARENA ADANYA DEATH CROSS
        elif is_sell_signal:
            st.warning("🟢 STRATEGI HHMA TERDETEKSI DEATH CROSS (SELL SIGNAL)!")
            if saldo_kripto > 0.0001:
                order = exchange.create_market_sell_order(st.session_state.symbol, saldo_kripto)
                st.success(f"💰 TAKE PROFIT / PENJUALAN BERHASIL! ID Transaksi: {order['id']}")
                st.session_state.last_buy_price = 0.0  # Bersihkan riwayat kunci harga beli
            else:
                st.error(f"Gagal Jual: Anda tidak sedang memegang saldo aset {base_asset}.")
        
        # JALUR UTAMA 4: TIDAK ADA AKSI (KONDISI PASAR AMAN/HOLD)
        else:
            st.info("⌛ Status: HOLD. Grafik harga bergerak stabil di dalam jalur indikator HHMA.")

    except Exception as e:
        st.error(f"⚠️ Gangguan Komunikasi Server / API Error: {e}")

# Memanggil Fungsi Engine Utama
run_trading_bot()
