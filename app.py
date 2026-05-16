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

# --- DEKLARASI STATE AWAL PERMANEN ---
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
if 'fake_signal_filter' not in st.session_state: st.session_state['fake_signal_filter'] = 0.05
if 'min_volume_idr' not in st.session_state: st.session_state['min_volume_idr'] = 50000000.0
if 'refresh_interval' not in st.session_state: st.session_state['refresh_interval'] = 30
if 'last_buy_price' not in st.session_state: st.session_state['last_buy_price'] = 0.0
if 'highest_price_since_buy' not in st.session_state: st.session_state['highest_price_since_buy'] = 0.0

# --- CONFIG APLIKASI ---
st.set_page_config(page_title="Indodax Ultra-Pro Bot", layout="wide")
st.title("🛡️ Indodax Pro Bot (Anti-Fake Signal, Trailing Profit & Volume Guard)")

# --- PANEL SIDEBAR PENGATURAN PERMANEN ---
st.sidebar.header("🔑 Kredensial Indodax")
st.sidebar.text_input("API Key", type="password", key="api_key")
st.sidebar.text_input("Secret Key", type="password", key="secret_key")

st.sidebar.header("⚙️ Parameter Strategi")
st.sidebar.text_input("Simbol Trading", key="symbol")
st.sidebar.selectbox("Timeframe", ["1 Menit", "5 Menit", "15 Menit", "1 Jam", "1 Hari"], key="timeframe_label")
st.sidebar.number_input("HHMA Cepat", step=1, key="fast_period")
st.sidebar.number_input("HHMA Lambat (HHMA20)", step=1, key="slow_period")
st.sidebar.number_input("Jumlah Beli (IDR)", step=10000, key="trade_amount")

st.sidebar.header("🛡️ Proteksi Risiko & Sinyal Palsu")
st.sidebar.number_input("Filter Sinyal Palsu (%)", key="fake_signal_filter", format="%.3f")
st.sidebar.number_input("Minimal Volume Harian (IDR)", step=5000000.0, key="min_volume_idr", format="%.1f")
st.sidebar.number_input("Batas Hard Stop Loss (%)", step=0.5, key="stop_loss_pct")
st.sidebar.number_input("Target Mulai Trailing Profit (%)", step=0.5, key="target_profit_pct")
st.sidebar.number_input("Jarak Trailing Koridor (%)", step=0.5, key="trailing_step_pct")
st.sidebar.number_input("Harga Beli Terakhir (IDR)", step=100.0, key="last_buy_price")

st.sidebar.header("⏱️ Sistem")
st.sidebar.slider("Jeda Cek Pasar (Detik)", min_value=10, max_value=300, step=10, key="refresh_interval")

# --- CONVERTER TIMEFRAME FOR INDODAX ---
timeframe_mapping = {"1 Menit": "1", "5 Menit": "5", "15 Menit": "15", "1 Jam": "60", "1 Hari": "1D"}
selected_timeframe_api = timeframe_mapping[st.session_state.timeframe_label]

exchange = None
if st.session_state.api_key and st.session_state.secret_key:
    exchange = ccxt.indodax({'apiKey': st.session_state.api_key, 'secret': st.session_state.secret_key, 'enableRateLimit': True})
    st.sidebar.success("✅ Koneksi API Aman & Terkunci!")
else:
    st.sidebar.warning("⚠️ Masukkan API Key untuk mengaktifkan fitur live trading.")

# --- ENGINE MONITORING UTAMA ---
@st.fragment(run_every=st.session_state.refresh_interval)
def run_trading_bot():
    if not exchange:
        st.info("Standby. Menunggu kredensial API Indodax.")
        return
        
    try:
        st.caption(f"🔄 Sinkronisasi Terakhir: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        
        # 1. Ambil Saldo & Data Ticker Volume
        balance = exchange.fetch_balance()
        ticker = exchange.fetch_ticker(st.session_state.symbol)
        volume_24h_idr = ticker['quoteVolume'] # Total perputaran nominal rupiah koin terkait
        
        symbol_split = st.session_state.symbol.split('/')
        base_asset = symbol_split[0]
        quote_asset = symbol_split[1] if len(symbol_split) > 1 else 'IDR'
        saldo_idr = balance['total'].get(quote_asset, 0)
        saldo_kripto = balance['total'].get(base_asset, 0)
        
        st.subheader("💰 Informasi Saldo & Volume Pasar")
        col_bal1, col_bal2, col_bal3 = st.columns(3)
        col_bal1.metric(f"Saldo {quote_asset}", f"{saldo_idr:,.0f} IDR")
        col_bal2.metric(f"Saldo {base_asset}", f"{saldo_kripto:.8f}")
        col_bal3.metric("Volume Pasar 24H", f"{volume_24h_idr:,.0f} IDR")

        # 2. Ambil Candlestick & Hitung Indikator
        ohlcv = exchange.fetch_ohlcv(st.session_state.symbol, selected_timeframe_api, limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        
        df['hhma_fast'] = calculate_hma(df['close'], int(st.session_state.fast_period))
        df['hhma_slow'] = calculate_hma(df['close'], int(st.session_state.slow_period))
        
        latest_idx = df.index[-1]
        prev_idx = df.index[-2]
        current_close = df.loc[latest_idx, 'close']
        
        # 3. VISUALISASI LIVE CHART
        st.subheader(f"📊 Live Chart: {st.session_state.symbol}")
        fig = go.Figure()
        fig.add_trace(go.Candlestick(x=df['timestamp'], open=df['open'], high=df['high'], low=df['low'], close=df['close'], name='Harga'))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['hhma_fast'], line=dict(color='#FFA500', width=1.5), name='HHMA Fast'))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['hhma_slow'], line=dict(color='#1E90FF', width=2), name='HHMA Slow'))
        fig.update_layout(xaxis_rangeslider_visible=False, height=400, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

        # 4. LOGIKA EVALUASI RISIKO & SELEKSI VOLUME
        hhma_gap_pct = abs(df.loc[latest_idx, 'hhma_fast'] - df.loc[latest_idx, 'hhma_slow']) / df.loc[latest_idx, 'hhma_slow'] * 100
        
        base_buy_signal = (df.loc[latest_idx, 'hhma_fast'] > df.loc[latest_idx, 'hhma_slow']) and (df.loc[prev_idx, 'hhma_fast'] <= df.loc[prev_idx, 'hhma_slow'])
        base_sell_signal = (df.loc[latest_idx, 'hhma_fast'] < df.loc[latest_idx, 'hhma_slow']) and (df.loc[prev_idx, 'hhma_fast'] >= df.loc[prev_idx, 'hhma_slow'])

        # FILTER INTEGRASI VOLUME 50 JUTA RUPIAH
        is_volume_liquid = volume_24h_idr >= st.session_state.min_volume_idr
        is_buy_signal = base_buy_signal and (hhma_gap_pct >= st.session_state.fake_signal_filter) and is_volume_liquid
        is_sell_signal = base_sell_signal

        execute_emergency_sell = False
        emergency_reason = ""
        
        if st.session_state.last_buy_price > 0:
            if current_close > st.session_state.highest_price_since_buy:
                st.session_state.highest_price_since_buy = current_close
            
            drop_from_buy = ((st.session_state.last_buy_price - current_close) / st.session_state.last_buy_price) * 100
            highest_profit_reached = ((st.session_state.highest_price_since_buy - st.session_state.last_buy_price) / st.session_state.last_buy_price) * 100
            is_signal_invalidated = df.loc[latest_idx, 'hhma_fast'] < df.loc[latest_idx, 'hhma_slow']

            if drop_from_buy >= st.session_state.stop_loss_pct:
                execute_emergency_sell = True
                emergency_reason = f"Hard Stop Loss {st.session_state.stop_loss_pct}% Terlewati!"
            elif highest_profit_reached >= st.session_state.target_profit_pct:
                trailing_stop_level = st.session_state.highest_price_since_buy * (1 - (st.session_state.trailing_step_pct / 100))
                if current_close <= trailing_stop_level:
                    execute_emergency_sell = True
                    emergency_reason = f"Trailing Stop Mengunci Profit Dipicu!"
            elif is_signal_invalidated:
                execute_emergency_sell = True
                emergency_reason = "Sinyal Beli Hilang Darurat (HHMA berpotongan balik!). Sistem keluar pasar."

        # Tampilkan Informasi Metrik Pasarnya
        col_p1, col_p2, col_p3 = st.columns(3)
        col_p1.metric("Harga Saat Ini", f"{current_close:,.0f} IDR")
        col_p2.metric("Gap Jarak HHMA", f"{hhma_gap_pct:.3f}%")
        if st.session_state.last_buy_price > 0:
            current_gain = ((current_close - st.session_state.last_buy_price) / st.session_state.last_buy_price) * 100
            col_p3.metric("Performa Posisi Anda", f"{current_gain:+.2f}%")
        else:
            col_p3.metric("Performa Posisi Anda", "0.00% (Tidak Ada Koin)")

        # 5. EXECUTION ENGINE
        st.subheader("⚡ Konsol Status Eksekusi")
        
        if execute_emergency_sell:
            st.error(f"🚨 TINDAKAN DARURAT: {emergency_reason}")
            if saldo_kripto > 0.0001:
                order = exchange.create_market_sell_order(st.session_state.symbol, saldo_kripto)
                st.success(f"💥 Sukses Keluar Pasar! ID Order: {order['id']}")
                st.session_state.last_buy_price = 0.0
                st.session_state.highest_price_since_buy = 0.0
            else:
                st.error("Gagal melakukan aksi jual darurat: Saldo koin kosong.")
                st.session_state.last_buy_price = 0.0
        
        elif is_buy_signal and st.session_state.last_buy_price == 0:
            st.warning("🔴 SINYAL BUY VALIDE & LIKUID! Membuka posisi...")
            if saldo_idr >= st.session_state.trade_amount:
                amount_to_buy = st.session_state.trade_amount / current_close
                order = exchange.create_market_buy_order(st.session_state.symbol, amount_to_buy)
                st.success(f"🛒 Pembelian Berhasil! ID Order: {order['id']}")
                st.session_state.last_buy_price = current_close
                st.session_state.highest_price_since_buy = current_close
            else:
                st.error("Gagal Beli: Saldo rupiah tidak mencukupi.")
                
        elif is_sell_signal and st.session_state.last_buy_price > 0:
            st.warning("🟢 SINYAL JUAL REGULER DETEKSI! Menutup posisi...")
            if saldo_kripto > 0.0001:
                order = exchange.create_market_sell_order(st.session_state.symbol, saldo_kripto)
                st.success(f"✅ Penjualan Berhasil! ID Order: {order['id']}")
                st.session_state.last_buy_price = 0.0
                st.session_state.highest_price_since_buy = 0.0
            else:
                st.error("Gagal Jual: Koin tidak ditemukan di portofolio.")
        else:
            if base_buy_signal and not is_volume_liquid:
                st.error(f"❌ BUY DITOLAK! Sinyal HHMA valid, tetapi volume 24 jam koin ini ({volume_24h_idr:,.0f} IDR) berada di bawah batas minimum Rp 50.000.000.")
            elif base_buy_signal and not is_buy_signal:
                st.warning("⚠️ Sinyal BUY ditolak karena jarak gap terlalu tipis (Potensi Sinyal Palsu).")
            else:
                st.info("Log: Kondisi pasar terpantau aman. Bot dalam mode monitor pasif.")

    except Exception as e:
        st.error(f"⚠️ Kendala API / Koneksi Terputus: {e}")

# Jalankan Engine Utama
run_trading_bot()
