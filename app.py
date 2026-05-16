import streamlit as st
import ccxt
import pandas as pd
import numpy as np
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

# --- CONFIG APLIKASI ---
st.set_page_config(page_title="Indodax Auto-Trading Bot", layout="wide")
st.title("🤖 Indodax Auto-Trading Bot (HHMA)")

# --- SIDEBAR: Kredensial & Parameter ---
st.sidebar.header("🔑 Kredensial Indodax")
api_key = st.sidebar.text_input("API Key", type="password", help="Dapatkan dari menu API di Indodax")
secret_key = st.sidebar.text_input("Secret Key", type="password")

st.sidebar.header("⚙️ Pengaturan Bot")
symbol = st.sidebar.text_input("Simbol Trading", value="BTC/IDR")
timeframe = st.sidebar.selectbox("Timeframe", ["1m", "5m", "15m", "1h", "1d"], index=0)
fast_period = st.sidebar.number_input("HHMA Cepat", value=9)
slow_period = st.sidebar.number_input("HHMA Lambat (HHMA20)", value=20)
trade_amount = st.sidebar.number_input("Jumlah Beli (IDR)", value=50000, step=10000)

st.sidebar.header("⏱️ Interval Auto-Refresh")
refresh_interval = st.sidebar.slider("Interval Cek (Detik)", min_value=10, max_value=300, value=30, step=10)

# --- INISIALISASI API ---
exchange = None
if api_key and secret_key:
    exchange = ccxt.indodax({
        'apiKey': api_key,
        'secret': secret_key,
        'enableRateLimit': True,
    })
    st.sidebar.success("API Terhubung!")
else:
    st.sidebar.warning("Silakan masukkan API & Secret Key untuk memulai.")

# --- FUNGSI UTAMA BOT (DENGAN REFRESH OTOMATIS) ---
# Menggunakan st.fragment agar area monitoring memperbarui dirinya sendiri secara berkala
@st.fragment(run_every=refresh_interval)
def run_trading_bot():
    if not exchange:
        st.info("Menunggu kredensial API Indodax yang valid...")
        return
        
    try:
        # Menampilkan penanda waktu pembaruan terakhir
        st.caption(f"🔄 Pembaruan Terakhir: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Cek Saldo Akun (Real Data)
        balance = exchange.fetch_balance()
        base_asset = symbol.split('/')[0]   # Contoh: BTC
        quote_asset = symbol.split('/')[1]  # Contoh: IDR
        
        saldo_idr = balance['total'].get(quote_asset, 0)
        saldo_kripto = balance['total'].get(base_asset, 0)
        
        st.subheader("💰 Saldo Akun")
        col_bal1, col_bal2 = st.columns(2)
        col_bal1.metric(f"Saldo {quote_asset}", f"{saldo_idr:,.0f} IDR")
        col_bal2.metric(f"Saldo {base_asset}", f"{saldo_kripto:.8f}")

        # 2. Ambil Data Harga & Hitung Sinyal
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        df['hhma_fast'] = calculate_hma(df['close'], fast_period)
        df['hhma_slow'] = calculate_hma(df['close'], slow_period)
        
        # Deteksi Persilangan (Crossover)
        latest_idx = df.index[-1]
        prev_idx = df.index[-2]
        current_close = df.loc[latest_idx, 'close']
        
        is_buy_signal = (df.loc[latest_idx, 'hhma_fast'] > df.loc[latest_idx, 'hhma_slow']) and \
                         (df.loc[prev_idx, 'hhma_fast'] <= df.loc[prev_idx, 'hhma_slow'])
                         
        is_sell_signal = (df.loc[latest_idx, 'hhma_fast'] < df.loc[latest_idx, 'hhma_slow']) and \
                          (df.loc[prev_idx, 'hhma_fast'] >= df.loc[prev_idx, 'hhma_slow'])

        # Tampilkan Status Harga Saat Ini
        st.subheader(f"📊 Analisis Pasar {symbol}")
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("Harga Terkini", f"{current_close:,.0f} IDR")
        col_p2.metric("HHMA Fast", f"{df.loc[latest_idx, 'hhma_fast']:,.2f}")
        col_p3.metric("HHMA Slow (20)", f"{df.loc[latest_idx, 'hhma_slow']:,.2f}")

        # 3. Eksekusi Order Otomatis (REAL TRADING)
        st.subheader("⚡ Status Eksekusi")
        
        if is_buy_signal:
            st.warning("🔴 SINYAL BUY TERDETEKSI! Memproses order...")
            if saldo_idr >= trade_amount:
                amount_to_buy = trade_amount / current_close
                order = exchange.create_market_buy_order(symbol, amount_to_buy)
                st.success(f"Berhasil BELI {symbol}! ID Order: {order['id']}")
            else:
                st.error(f"Gagal Beli: Saldo {quote_asset} tidak cukup. Butuh {trade_amount:,.0f} IDR.")
                
        elif is_sell_signal:
            st.warning("🟢 SINYAL SELL TERDETEKSI! Memproses order...")
            if saldo_kripto > 0.0001: 
                order = exchange.create_market_sell_order(symbol, saldo_kripto)
                st.success(f"Berhasil JUAL {symbol}! ID Order: {order['id']}")
            else:
                st.error(f"Gagal Jual: Anda tidak memiliki saldo {base_asset} untuk dijual.")
        else:
            st.info("⌛ Market dalam kondisi HOLD. Belum ada perpotongan garis HHMA baru.")

    except Exception as e:
        st.error(f"Terjadi Kesalahan API / Trading: {e}")

# Memanggil fungsi bot di halaman utama
run_trading_bot()
