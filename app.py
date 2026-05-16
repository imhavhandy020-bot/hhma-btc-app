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
    period = int(period) if int(period) > 1 else 9
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    wma_half = calculate_wma(series, half_period)
    wma_full = calculate_wma(series, period)
    raw_hma = (2 * wma_half) - wma_full
    return calculate_wma(raw_hma, sqrt_period)

# --- 1. INISIALISASI SESSION STATE (AMANKAN NILAI AWAL) ---
if 'api_key' not in st.session_state: st.session_state['api_key'] = ""
if 'secret_key' not in st.session_state: st.session_state['secret_key'] = ""
if 'symbol' not in st.session_state: st.session_state['symbol'] = "BTC/IDR"
if 'timeframe_label' not in st.session_state: st.session_state['timeframe_label'] = "5 Menit"
if 'fast_period' not in st.session_state: st.session_state['fast_period'] = 9
if 'slow_period' not in st.session_state: st.session_state['slow_period'] = 20
if 'trade_amount' not in st.session_state: st.session_state['trade_amount'] = 50000
if 'stop_loss_pct' not in st.session_state: st.session_state['stop_loss_pct'] = 2.0
if 'target_profit_pct' not in st.session_state: st.session_state['target_profit_pct'] = 4.0
if 'trailing_step_pct' not in st.session_state: st.session_state['trailing_step_pct'] = 1.0
if 'fake_signal_filter' not in st.session_state: st.session_state['fake_signal_filter'] = 0.050
if 'min_volume_idr' not in st.session_state: st.session_state['min_volume_idr'] = 50000000
if 'refresh_interval' not in st.session_state: st.session_state['refresh_interval'] = 30
if 'last_buy_price' not in st.session_state: st.session_state['last_buy_price'] = "0"
if 'highest_price_since_buy' not in st.session_state: st.session_state['highest_price_since_buy'] = 0.0

# --- CONFIG APLIKASI ---
st.set_page_config(page_title="Indodax Ultra-Pro Bot", layout="wide")
st.title("🛡️ Indodax Pro Bot (Anti-Fake Signal, Trailing Profit & Volume Guard)")

# --- 2. PANEL SIDEBAR ANTI-CRASH (MENGGUNAKAN SLIDER & AMAN INPUT) ---
st.sidebar.header("🔑 Kredensial Indodax")
st.sidebar.text_input("API Key", type="password", key="api_key")
st.sidebar.text_input("Secret Key", type="password", key="secret_key")

st.sidebar.header("⚙️ Parameter Strategi")
st.sidebar.text_input("Simbol Trading", key="symbol")
st.sidebar.selectbox("Timeframe", ["1 Menit", "5 Menit", "15 Menit", "1 Jam", "1 Hari"], key="timeframe_label")

# Menggunakan Slider agar input angka TIDAK BISA KOSONG (Bebas Eror Teks Kosong '')
st.sidebar.slider("HHMA Cepat", min_value=2, max_value=50, step=1, key="fast_period")
st.sidebar.slider("HHMA Lambat (HHMA20)", min_value=3, max_value=100, step=10, key="slow_period")
st.sidebar.slider("Jumlah Beli (IDR)", min_value=10000, max_value=5000000, step=10000, key="trade_amount")

st.sidebar.header("🛡️ Proteksi Risiko & Sinyal Palsu")
st.sidebar.slider("Filter Sinyal Palsu (%)", min_value=0.000, max_value=1.000, step=0.005, format="%.3f", key="fake_signal_filter")
st.sidebar.slider("Batas Hard Stop Loss (%)", min_value=0.5, max_value=20.0, step=0.5, key="stop_loss_pct")
st.sidebar.slider("Target Mulai Trailing Profit (%)", min_value=1.0, max_value=50.0, step=0.5, key="target_profit_pct")
st.sidebar.slider("Jarak Trailing Koridor (%)", min_value=0.2, max_value=10.0, step=0.2, key="trailing_step_pct")

# Untuk input manual teks harga beli terakhir, dikonversi dengan failsafe aman
st.sidebar.text_input("Harga Beli Terakhir (IDR)", key="last_buy_price", help="Gunakan angka tanpa koma/titik. Isi 0 jika belum beli.")

st.sidebar.header("⏱️ Sistem")
st.sidebar.slider("Jeda Cek Pasar (Detik)", min_value=10, max_value=300, step=10, key="refresh_interval")

# --- CONVERTER TIMEFRAME RESMI INDODAX ---
timeframe_mapping = {"1 Menit": "1", "5 Menit": "5", "15 Menit": "15", "1 Jam": "60", "1 Hari": "1D"}
selected_timeframe_api = timeframe_mapping.get(st.session_state.timeframe_label, "5")

# --- KONEKSI CCXT API INDODAX ---
exchange = None
if st.session_state.api_key.strip() and st.session_state.secret_key.strip():
    try:
        exchange = ccxt.indodax({
            'apiKey': str(st.session_state.api_key).strip(),
            'secret': str(st.session_state.secret_key).strip(),
            'enableRateLimit': True
        })
        st.sidebar.success("✅ Koneksi API Aman & Terkunci!")
    except:
        st.sidebar.error("Gagal menghubungkan API. Cek koneksi internet.")
else:
    st.sidebar.warning("⚠️ Masukkan API Key untuk memulai live trading.")

# --- ENGINE MONITORING UTAMA ---
# Pastikan waktu refresh aman dari nilai kosong
current_refresh = int(st.session_state.refresh_interval) if st.session_state.refresh_interval else 30

@st.fragment(run_every=current_refresh)
def run_trading_bot():
    if not exchange:
        st.info("Standby. Menunggu kredensial API Indodax dimasukkan.")
        return
        
    try:
        st.caption(f"🔄 Sinkronisasi Terakhir: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        current_symbol = str(st.session_state.symbol).strip() if st.session_state.symbol else "BTC/IDR"
        
        # 1. Ambil Saldo & Data Ticker Volume Pasaran
        balance = exchange.fetch_balance()
        ticker = exchange.fetch_ticker(current_symbol)
        volume_24h_idr = float(ticker.get('quoteVolume', 0)) if ticker else 0.0
        
        symbol_split = current_symbol.split('/')
        base_asset = symbol_split[0] if len(symbol_split) > 0 else 'BTC'
        quote_asset = symbol_split[1] if len(symbol_split) > 1 else 'IDR'
        saldo_idr = balance['total'].get(quote_asset, 0)
        saldo_kripto = balance['total'].get(base_asset, 0)
        
        st.subheader("💰 Informasi Saldo & Volume Pasar")
        col_bal1, col_bal2, col_bal3 = st.columns(3)
        col_bal1.metric(f"Saldo {quote_asset}", f"{saldo_idr:,.0f} IDR")
        col_bal2.metric(f"Saldo {base_asset}", f"{saldo_kripto:.8f}")
        col_bal3.metric("Volume Pasar 24H", f"{volume_24h_idr:,.0f} IDR")

        # 2. Ambil Candlestick & Hitung Indikator (FAILSAFE KETAT)
        ohlcv = exchange.fetch_ohlcv(current_symbol, selected_timeframe_api, limit=100)
        if not ohlcv:
            st.error("Data pasar kosong. Cek keselarasan Simbol Trading Anda.")
            return
            
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        fast_p = int(st.session_state.fast_period)
        slow_p = int(st.session_state.slow_period)
        
        df['hhma_fast'] = calculate_hma(df['close'], fast_p)
        df['hhma_slow'] = calculate_hma(df['close'], slow_p)
        
        latest_idx = df.index[-1]
        prev_idx = df.index[-2]
        current_close = df.loc[latest_idx, 'close']
        
        # 3. VISUALISASI LIVE CHART
        st.subheader(f"📊 Live Chart: {current_symbol}")
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Harga'))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['hhma_fast'], line=dict(color='#FFA500', width=1.5), name='HHMA Fast'))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['hhma_slow'], line=dict(color='#1E90FF', width=2), name='HHMA Slow'))
        fig.update_layout(xaxis_rangeslider_visible=False, height=400, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # 4. LOGIKA EVALUASI RISIKO & SELEKSI FILTER
        hhma_slow_val = df.loc[latest_idx, 'hhma_slow']
        hhma_gap_pct = abs(df.loc[latest_idx, 'hhma_fast'] - hhma_slow_val) / hhma_slow_val * 100 if hhma_slow_val != 0 else 0
        
        base_buy_signal = (df.loc[latest_idx, 'hhma_fast'] > hhma_slow_val) and (df.loc[prev_idx, 'hhma_fast'] <= df.loc[prev_idx, 'hhma_slow'])
        base_sell_signal = (df.loc[latest_idx, 'hhma_fast'] < hhma_slow_val) and (df.loc[prev_idx, 'hhma_fast'] >= df.loc[prev_idx, 'hhma_slow'])

        # Proteksi Konversi String ke Float untuk Harga Beli Terakhir
        try:
            cleaned_buy_price = str(st.session_state.last_buy_price).replace(",", "").replace(" ", "")
            last_buy = float(cleaned_buy_price) if cleaned_buy_price != '' else 0.0
        except:
            last_buy = 0.0

        # Ambil nilai kontrol risiko aman dari slider
        fake_filter = float(st.session_state.fake_signal_filter)
        sl_pct = float(st.session_state.stop_loss_pct)
        tp_pct = float(st.session_state.target_profit_pct)
        trail_pct = float(st.session_state.trailing_step_pct)
        
        # Validasi Keras: Minimal Volume Harian Harus > 50 Juta IDR
        is_volume_liquid = volume_24h_idr >= 50000000.0
        is_buy_signal = base_buy_signal and (hhma_gap_pct >= fake_filter) and is_volume_liquid
        is_sell_signal = base_sell_signal

        execute_emergency_sell = False
        emergency_reason = ""
        
        if last_buy > 0:
            if 'highest_price_since_buy' not in st.session_state or st.session_state.highest_price_since_buy == 0:
                st.session_state.highest_price_since_buy = current_close
                
            if current_close > st.session_state.highest_price_since_buy:
                st.session_state.highest_price_since_buy = current_close
            
            drop_from_buy = ((last_buy - current_close) / last_buy) * 100
            highest_profit_reached = ((st.session_state.highest_price_since_buy - last_buy) / last_buy) * 100
            is_signal_invalidated = df.loc[latest_idx, 'hhma_fast'] < df.loc[latest_idx, 'hhma_slow']

            if drop_from_buy >= sl_pct:
                execute_emergency_sell = True
                emergency_reason = f"Hard Stop Loss {sl_pct}% Terlewati!"
            elif highest_profit_reached >= tp_pct:
                trailing_stop_level = st.session_state.highest_price_since_buy * (1 - (trail_pct / 100))
                if current_close <= trailing_stop_level:
                    execute_emergency_sell = True
                    emergency_reason = "Trailing Stop Mengunci Profit Dipicu!"
            elif is_signal_invalidated:
                execute_emergency_sell = True
                emergency_reason = "Sinyal Beli Hilang Darurat (HHMA berpotongan balik!). Sistem keluar pasar."

        # Tampilkan Informasi Papan Metrik Pasar
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("Harga Saat Ini", f"{current_close:,.0f} IDR")
        col_p2.metric("Gap Jarak HHMA", f"{hhma_gap_pct:.3f}%")
        if last_buy > 0:
            current_gain = ((current_close - last_buy) / last_buy) * 100
            col_p3.metric("Performa Posisi Anda", f"{current_gain:+.2f}%")
        else:
            col_p3.metric("Performa Posisi Anda", "0.00% (Tidak Ada Koin)")

        # 5. EXECUTION ENGINE (SISTEM EKSEKUSI MARKET ORDER)
        st.subheader("⚡ Konsol Status Eksekusi")
        
        if execute_emergency_sell:
            st.error(f"🚨 TINDAKAN DARURAT: {emergency_reason}")
            if saldo_kripto > 0.0001:
                order = exchange.create_market_sell_order(current_symbol, saldo_kripto)
                st.success(f"💥 Sukses Keluar Pasar! ID Order: {order['id']}")
                st.session_state.last_buy_price = "0"
                st.session_state.highest_price_since_buy = 0.0
            else:
                st.error("Gagal melakukan aksi jual darurat: Saldo koin di portofolio kosong.")
                st.session_state.last_buy_price = "0"
        
        elif is_buy_signal and last_buy == 0:
            st.warning("🔴 SINYAL BUY VALID & LIKUID! Membuka posisi...")
            trade_amt = float(st.session_state.trade_amount)
            if saldo_idr >= trade_amt:
                amount_to_buy = trade_amt / current_close
                order = exchange.create_market_buy_order(current_symbol, amount_to_buy)
                st.success(f"🛒 Pembelian Berhasil! ID Order: {order['id']}")
                st.session_state.last_buy_price = str(int(current_close))
                st.session_state.highest_price_since_buy = current_close
            else:
                st.error("Gagal Beli: Saldo rupiah di akun Indodax tidak mencukupi.")
                
        elif is_sell_signal and last_buy > 0:
            st.warning("🟢 SINYAL JUAL REGULER (DEATH CROSS)! Menutup posisi...")
            if saldo_kripto > 0.0001:
                order = exchange.create_market_sell_order(current_symbol, saldo_kripto)
                st.success(f"✅ Penjualan Berhasil! ID Order: {order['id']}")
                st.session_state.last_buy_price = "0"
                st.session_state.highest_price_since_buy = 0.0
            else:
                st.error("Gagal Jual: Koin tidak ditemukan di portofolio.")
        else:
            if base_buy_signal and not is_volume_liquid:
                st.error(f"❌ BUY DITOLAK! Sinyal HHMA valid, tetapi volume harian ({volume_24h_idr:,.0f} IDR) di bawah syarat minimal Rp 50.000.000.")
            elif base_buy_signal and not is_buy_signal:
                st.warning("⚠️ Sinyal BUY ditolak oleh filter jarak gap (Potensi Sinyal Palsu).")
            else:
                st.info("Log: Kondisi pasar terpantau aman. Bot dalam mode monitor pasif.")

    except Exception as e:
        st.error(f"⚠️ Kendala API / Koneksi Terputus: {e}")

# Jalankan Engine Utama
run_trading_bot()
