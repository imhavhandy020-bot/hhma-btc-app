import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import sqlite3
from datetime import datetime

# Konfigurasi Tampilan Layar HP
st.set_page_config(page_title="Indodax Auto Trade Bot Persistent", layout="centered")

# =========================================================
# MENYIMPAN DATA AGAR TETAP TERKUNCI & TIDAK RESET SAAT REFRESH
# =========================================================
if "api_key" not in st.session_state: st.session_state.api_key = ""
if "secret_key" not in st.session_state: st.session_state.secret_key = ""
if "symbol" not in st.session_state: st.session_state.symbol = "BTC/IDR"
if "timeframe" not in st.session_state: st.session_state.timeframe = "1d"
if "hma_length" not in st.session_state: st.session_state.hma_length = 2
if "max_bars" not in st.session_state: st.session_state.max_bars = 100
if "tp_pct" not in st.session_state: st.session_state.tp_pct = 5.0
if "sl_pct" not in st.session_state: st.session_state.sl_pct = 2.0
if "order_idr" not in st.session_state: st.session_state.order_idr = 50000.0  
if "sim_balance" not in st.session_state: st.session_state.sim_balance = 10000000.0
if "last_signal" not in st.session_state: st.session_state.last_signal = 0
if "refresh_rate" not in st.session_state: st.session_state.refresh_rate = 5

# Fungsi Callback untuk Mengunci Perubahan Komponen Instan
def update_state(key, val_key):
    st.session_state[key] = st.session_state[val_key]

# =========================================================
# DATABASE FISIK (TETAP TERSIMPAN AMAN)
# =========================================================
def init_db():
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            signal_type TEXT,
            price REAL,
            amount REAL,
            tp_price REAL,
            sl_price REAL,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_trade_history(filter_type="Semua"):
    conn = sqlite3.connect('trading_bot.db')
    if filter_type == "Hanya Live Trading":
        query = "SELECT * FROM trades WHERE status LIKE 'LIVE%' ORDER BY id DESC"
    elif filter_type == "Hanya Simulasi":
        query = "SELECT * FROM trades WHERE status = 'SIMULASI' ORDER BY id DESC"
    else:
        query = "SELECT * FROM trades ORDER BY id DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def save_trade(signal_type, price, amount, tp, sl, status="EXECUTED"):
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (timestamp, signal_type, price, amount, tp_price, sl_price, status)
        VALUES (datetime('now'), ?, ?, ?, ?, ?, ?)
    ''', (signal_type, price, amount, tp, sl, status))
    conn.commit()
    conn.close()

def clear_db():
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM trades')
    conn.commit()
    conn.close()

init_db()

# ==========================================
# MENU INPUT PARAMETER (SIDEBAR HP)
# ==========================================
st.sidebar.title("⚙️ Kendali Otomatis Bot")

st.sidebar.subheader("🔑 Kredensial Akun Indodax")
st.session_state.api_key = st.sidebar.text_input("API Key", type="password", value=st.session_state.api_key)
st.session_state.secret_key = st.sidebar.text_input("Secret Key", type="password", value=st.session_state.secret_key)

if not st.session_state.api_key or not st.session_state.secret_key:
    st.sidebar.subheader("🎮 Pengaturan Simulasi")
    st.session_state.sim_balance = st.sidebar.number_input(
        "Modal Awal Simulasi (IDR)", min_value=10000.0, 
        value=st.session_state.sim_balance, step=500000.0,
        key="sb_sim", on_change=update_state, args=("sim_balance", "sb_sim")
    )

st.sidebar.subheader("💰 Jumlah Perdagangan")
st.session_state.order_idr = st.sidebar.number_input(
    "Jumlah Beli Per Sinyal (IDR)", min_value=10000.0, 
    value=st.session_state.order_idr, step=5000.0,
    key="sb_order", on_change=update_state, args=("order_idr", "sb_order")
)

st.sidebar.subheader("📈 Parameter Indikator")
symbol_options = ["BTC/IDR", "ETH/IDR", "USDT/IDR"]
idx_sym = symbol_options.index(st.session_state.symbol) if st.session_state.symbol in symbol_options else 0
st.session_state.symbol = st.sidebar.selectbox("Pilih Aset", symbol_options, index=idx_sym)

tf_options = ["1d", "4h", "1h", "15m"]
idx_tf = tf_options.index(st.session_state.timeframe) if st.session_state.timeframe in tf_options else 0
st.session_state.timeframe = st.sidebar.selectbox("Timeframe", tf_options, index=idx_tf)

st.session_state.hma_length = st.sidebar.number_input(
    "Panjang HMA", min_value=1, max_value=100, 
    value=st.session_state.hma_length,
    key="sb_hma", on_change=update_state, args=("hma_length", "sb_hma")
)
st.session_state.max_bars = st.sidebar.slider(
    "Pembatasan Bar", min_value=10, max_value=500, 
    value=st.session_state.max_bars,
    key="sb_bars", on_change=update_state, args=("max_bars", "sb_bars")
)

st.sidebar.subheader("🛡️ Pembatasan Profit & Rugi")
st.session_state.tp_pct = st.sidebar.number_input(
    "Pelebaran Profit / TP (%)", min_value=0.1, 
    value=st.session_state.tp_pct,
    key="sb_tp", on_change=update_state, args=("tp_pct", "sb_tp")
)
st.session_state.sl_pct = st.sidebar.number_input(
    "Stop Loss / SL (%)", min_value=0.1, 
    value=st.session_state.sl_pct,
    key="sb_sl", on_change=update_state, args=("sl_pct", "sb_sl")
)

st.sidebar.subheader("⏱️ Sinkronisasi")
st.session_state.refresh_rate = st.sidebar.slider(
    "Jeda Auto-Refresh (Detik)", min_value=1, max_value=60, 
    value=st.session_state.refresh_rate,
    key="sb_ref", on_change=update_state, args=("refresh_rate", "sb_ref")
)

if st.sidebar.button("🗑️ Hapus Semua Riwayat Tabel", type="primary", use_container_width=True):
    clear_db()
    st.session_state.last_signal = 0  
    st.sidebar.success("Database dibersihkan!")
    st.rerun()

# Inisialisasi Bursa Indodax
def init_exchange(api, secret):
    if api and secret:
        return ccxt.indodax({'apiKey': api, 'secret': secret, 'enableRateLimit': True})
    return ccxt.indodax({'enableRateLimit': True})

exchange = init_exchange(st.session_state.api_key, st.session_state.secret_key)

# ==========================================
# RUMUS MATEMATIKA HMA
# ==========================================
def wma(series, length):
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def calculate_hma(df, length):
    half_length = int(length / 2) if int(length / 2) > 0 else 1
    sqrt_length = int(np.sqrt(length)) if int(np.sqrt(length)) > 0 else 1
    wma_half = wma(df['close'], half_length)
    wma_full = wma(df['close'], length)
    raw_hma = (2 * wma_half) - wma_full
    df['hma'] = wma(raw_hma, sqrt_length)
    return df

# ==========================================
# KOMPONEN REFRESH DAN EKSEKUSI UTAMA
# ==========================================
@st.fragment(run_every=st.session_state.refresh_rate)
def market_monitor_fragment():
    waktu_sekarang = datetime.now().strftime('%H:%M:%S')
    st.caption(f"🔄 Sinkronisasi Indodax (Setiap {st.session_state.refresh_rate} Detik): {waktu_sekarang}")
    
    base_coin = st.session_state.symbol.split('/')[0]
    
    # Render Informasi Dompet
    if st.session_state.api_key and st.session_state.secret_key:
        try:
            balance = exchange.fetch_balance()
            saldo_idr = balance['free']['IDR'] if 'IDR' in balance['free'] else 0.0
            saldo_coin = balance['free'][base_coin] if base_coin in balance['free'] else 0.0
            st.info(f"尊 **Dompet Akun Real Anda:**  \n💵 Saldo Rupiah: **Rp {saldo_idr:,.0f}**  \n🪙 Sisa Koin ({base_coin}): **{saldo_coin:.6f} {base_coin}**")
        except Exception as bal_err:
            st.sidebar.error(f"Gagal Memuat Saldo API: {bal_err}")
    else:
        st.info(f"🎮 **Dompet Kustom Simulasi:**  \n💵 Saldo Rupiah: **Rp {st.session_state.sim_balance:,.0f}**  \n🪙 Sisa Koin ({base_coin}): **0.000000 {base_coin}**")

    try:
        bars = exchange.fetch_ohlcv(st.session_state.symbol, st.session_state.timeframe, limit=int(st.session_state.max_bars))
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = calculate_hma(df, int(st.session_state.hma_length))
        
        current_hma = df['hma'].iloc[-1]
        prev_hma = df['hma'].iloc[-2]
        prev_prev_hma = df['hma'].iloc[-3]
        current_close = df['close'].iloc[-1]
        
        is_green_now = current_hma >= prev_hma
        is_green_prev = prev_hma >= prev_prev_hma
        
        raw_buy = is_green_now and not is_green_prev
        raw_sell = not is_green_now and is_green_prev
        
        col1, col2 = st.columns(2)
        col1.metric(label=f"Harga Sekarang ({st.session_state.symbol})", value=f"{current_close:,.0f} IDR")
        
        if is_green_now:
            col2.metric(label="Status Tren HHMA", value="HIJAU (BUY ZONE)", delta="Naik")
        else:
            col2.metric(label="Status Tren HHMA", value="MERAH (SELL ZONE)", delta="-Turun", delta_color="inverse")
            
        # Logika Eksekusi Otomatis Sinyal Bergantian
        if raw_buy and st.session_state.last_signal != 1:
            tp = current_close * (1 + (st.session_state.tp_pct / 100))
            sl = current_close * (1 - (st.session_state.sl_pct / 100))
            amount_to_buy = st.session_state.order_idr / current_close 
            
            status_order = "SIMULASI"
            if st.session_state.api_key and st.session_state.secret_key:
                try:
                    order = exchange.create_market_buy_order(st.session_state.symbol, amount_to_buy)
                    status_order = "LIVE_BUY_SUCCESS"
                except Exception as trade_err:
                    st.error(f"Gagal Eksekusi Buy Indodax: {trade_err}")
                    status_order = f"ERROR: {str(trade_err)[:30]}"
            else:
                st.session_state.sim_balance -= st.session_state.order_idr
            
            save_trade('BUY', current_close, amount_to_buy, tp, sl, status_order)
            st.session_state.last_signal = 1
            st.toast("🟩 AUTOMATIC BUY BERHASIL!", icon="🛒")
            st.rerun() 
            
        elif raw_sell and st.session_state.last_signal != -1:
            tp = current_close * (1 - (st.session_state.tp_pct / 100))
            sl = current_close * (1 + (st.session_state.sl_pct / 100))
            amount_to_sell = st.session_state.order_idr / current_close
            
            status_order = "SIMULASI"
            if st.session_state.api_key and st.session_state.secret_key:
                try:
                    order = exchange.create_market_sell_order(st.session_state.symbol, amount_to_sell)
                    status_order = "LIVE_SELL_SUCCESS"
                except Exception as trade_err:
                    st.error(f"Gagal Eksekusi Sell Indodax: {trade_err}")
                    status_order = f"ERROR: {str(trade_err)[:30]}"
            else:
                st.session_state.sim_balance += st.session_state.order_idr
            
            save_trade('SELL', current_close, amount_to_sell, tp, sl, status_order)
            st.session_state.last_signal = -1
            st.toast("🟥 AUTOMATIC SELL BERHASIL!", icon="💰")
            st.rerun()
            
        st.line_chart(df[['close', 'hma']].tail(int(st.session_state.max_bars)))
        
    except Exception as e:
        st.error(f"Koneksi Indodax terputus, memuat ulang... ({e})")

# ==========================================
# ALUR UTAMA HALAMAN WEB
# ==========================================
st.title("🤖 Indodax Auto Trading Bot")

if st.session_state.api_key and st.session_state.secret_key:
    st.success("🤖 BOT LIVE OTOMATIS AKTIF")
else:
    st.warning("⚠️ MODE SIMULASI AKTIF")

st.subheader("Live Market Tracker")
market_monitor_fragment()

# Filter Data Riwayat Transaksi
st.subheader("📦 Buku Transaksi")
filter_pilihan = st.radio("Saring Data Tabel:", ["Semua Transaksi", "Hanya Live Trading", "Hanya Simulasi"], horizontal=True)

history_df = get_trade_history(filter_pilihan)

if not history_df.empty:
    st.dataframe(history_df.head(15), use_container_width=True)
else:
    st.info("Tabel kosong. Menunggu sinyal otomatis berjalan.")
