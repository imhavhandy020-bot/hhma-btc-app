import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import sqlite3
from datetime import datetime

# Konfigurasi Tampilan Layar HP
st.set_page_config(page_title="Indodax Bot Pro Fix Balance", layout="centered")

# =========================================================
# MANAJEMEN DATABASE FISIK (PARAM & TRANSAKSI) - ANTI RESET
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
            highest_price REAL,
            status TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            val_text TEXT,
            val_num REAL
        )
    ''')
    conn.commit()
    conn.close()

def save_setting(key, text_val="", num_val=0.0):
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO settings (key, val_text, val_num)
        VALUES (?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET val_text=excluded.val_text, val_num=excluded.val_num
    ''', (key, text_val, num_val))
    conn.commit()
    conn.close()

def get_setting(key, default_text=None, default_num=None):
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute("SELECT val_text, val_num FROM settings WHERE key=?", (key,))
    row = cursor.fetchone()
    conn.close()
    if row:
        if default_text is not None: return row[0] if row[0] is not None else default_text
        if default_num is not None: return row[1] if row[1] is not None else default_num
    return default_text if default_text is not None else default_num

def get_trade_history(filter_type="Semua"):
    conn = sqlite3.connect('trading_bot.db')
    if filter_type == "Hanya Live Trading":
        query = "SELECT * FROM trades WHERE status NOT LIKE 'DEMO%' AND status NOT LIKE 'SIMULASI%' ORDER BY id DESC"
    elif filter_type == "Hanya Demo (Simulasi)":
        query = "SELECT * FROM trades WHERE status LIKE 'DEMO%' OR status LIKE 'SIMULASI%' ORDER BY id DESC"
    else:
        query = "SELECT * FROM trades ORDER BY id DESC"
    df = pd.read_sql_query(query, conn)
    conn.close()
    return df

def save_trade(signal_type, price, amount, tp, sl, highest, status="OPEN"):
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (timestamp, signal_type, price, amount, tp_price, sl_price, highest_price, status)
        VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?)
    ''', (signal_type, price, amount, tp, sl, highest, status))
    conn.commit()
    conn.close()

def update_active_trade(trade_id, highest, status):
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE trades SET highest_price=?, status=? WHERE id=?", (highest, status, trade_id))
    conn.commit()
    conn.close()

def clear_db():
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM trades')
    conn.commit()
    conn.close()

init_db()

# =========================================================
# PARAMETER DIKUNCI MATI (4H & HMA 8)
# =========================================================
TIMEFRAME = "4h"   
HMA_LENGTH = 8     

db_api = get_setting("api_key", default_text="")
db_secret = get_setting("secret_key", default_text="")
db_symbol = get_setting("symbol", default_text="BTC/IDR")
db_max_bars = int(get_setting("max_bars", default_num=100.0))
db_tp_pct = get_setting("tp_pct", default_num=5.0)
db_sl_pct = get_setting("sl_pct", default_num=2.0)
db_order_idr = get_setting("order_idr", default_num=50000.0)
db_sim_balance = get_setting("sim_balance", default_num=10000000.0)
db_sim_coin = get_setting("sim_coin", default_num=0.0) # BARU: Pengingat koin simulasi
db_refresh_rate = int(get_setting("refresh_rate", default_num=5.0))
db_mode = get_setting("bot_mode", default_text="Demo (Simulasi)")

if "last_signal" not in st.session_state: 
    st.session_state.last_signal = int(get_setting("last_signal", default_num=0.0))

# ==========================================
# MENU INPUT PARAMETER (SIDEBAR HP)
# ==========================================
st.sidebar.title("⚙️ Kendali Otomatis Bot")

st.sidebar.subheader("🔌 Mode Operasional Bot")
mode_input = st.sidebar.radio("Pilih Sistem:", ["Demo (Simulasi)", "Live Trading Real"], index=0 if db_mode == "Demo (Simulasi)" else 1)
if mode_input != db_mode: save_setting("bot_mode", text_val=mode_input)

st.sidebar.subheader("🔑 Kredensial Akun Indodax")
api_input = st.sidebar.text_input("API Key", type="password", value=db_api)
secret_input = st.sidebar.text_input("Secret Key", type="password", value=db_secret)

if api_input != db_api: save_setting("api_key", text_val=api_input)
if secret_input != db_secret: save_setting("secret_key", text_val=secret_input)

if mode_input == "Demo (Simulasi)":
    st.sidebar.subheader("🎮 Akun Uji Coba")
    sim_balance_input = st.sidebar.number_input("Modal Awal Demo (IDR)", min_value=10000.0, value=db_sim_balance, step=500000.0)
    if sim_balance_input != db_sim_balance: save_setting("sim_balance", num_val=sim_balance_input)
else: sim_balance_input = db_sim_balance

st.sidebar.subheader("💰 Jumlah Perdagangan")
order_idr_input = st.sidebar.number_input("Jumlah Beli Per Sinyal (IDR)", min_value=10000.0, value=db_order_idr, step=5000.0)
if order_idr_input != db_order_idr: save_setting("order_idr", num_val=order_idr_input)

st.sidebar.subheader("📈 Parameter Indikator")
symbol_options = ["BTC/IDR", "ETH/IDR", "USDT/IDR"]
idx_sym = symbol_options.index(db_symbol) if db_symbol in symbol_options else 0
symbol_input = st.sidebar.selectbox("Pilih Aset", symbol_options, index=idx_sym)
if symbol_input != db_symbol: save_setting("symbol", text_val=symbol_input)

st.sidebar.text(f"⏱️ Timeframe Terkunci: {TIMEFRAME.upper()}")
st.sidebar.text(f"📊 Panjang Periode HMA: {HMA_LENGTH}")

max_bars_input = st.sidebar.slider("Pembatasan Bar Tampilan", min_value=10, max_value=500, value=db_max_bars)
if max_bars_input != db_max_bars: save_setting("max_bars", num_val=float(max_bars_input))

st.sidebar.subheader("🛡️ Pembatasan Profit & Rugi")
tp_pct_input = st.sidebar.number_input("Pelebaran Profit / TP (%)", min_value=0.1, value=db_tp_pct)
if tp_pct_input != db_tp_pct: save_setting("tp_pct", num_val=tp_pct_input)

sl_pct_input = st.sidebar.number_input("Stop Loss / SL (%)", min_value=0.1, value=db_sl_pct)
if sl_pct_input != db_sl_pct: save_setting("sl_pct", num_val=sl_pct_input)

st.sidebar.subheader("⏱️ Sinkronisasi & Pembersihan")
refresh_rate_input = st.sidebar.slider("Jeda Auto-Refresh (Detik)", min_value=1, max_value=60, value=db_refresh_rate)
if refresh_rate_input != db_refresh_rate: save_setting("refresh_rate", num_val=float(refresh_rate_input))

if st.sidebar.button("🗑️ Hapus Semua Riwayat Tabel", type="primary", use_container_width=True):
    clear_db()
    save_setting("last_signal", num_val=0.0)
    save_setting("sim_coin", num_val=0.0)
    st.session_state.last_signal = 0  
    st.sidebar.success("Database dibersihkan!")
    st.rerun()

exchange = ccxt.indodax({'apiKey': api_input, 'secret': secret_input, 'enableRateLimit': True}) if api_input and secret_input else ccxt.indodax({'enableRateLimit': True})

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
@st.fragment(run_every=refresh_rate_input)
def market_monitor_fragment():
    waktu_sekarang = datetime.now().strftime('%H:%M:%S')
    st.caption(f"🔄 Sinkronisasi Indodax (Setiap {refresh_rate_input} Detik): {waktu_sekarang}")
    
    base_coin = symbol_input.split('/')
    coin_name = str(base_coin[0])
    saldo_idr_tersedia = 0.0

    # Pemuatan Ulang Saldo Terkunci Database Fisik
    current_sim_balance = get_setting("sim_balance", default_num=10000000.0)
    current_sim_coin = get_setting("sim_coin", default_num=0.0)

    if mode_input == "Live Trading Real" and api_input and secret_input:
        try:
            balance = exchange.fetch_balance()
            saldo_idr_tersedia = balance['free']['IDR'] if 'IDR' in balance['free'] else 0.0
            saldo_coin = balance['free'][coin_name] if coin_name in balance['free'] else 0.0
            # PERBAIKAN: Format koin diubah ke :.8f agar pecahan kecil BTC langsung kelihatan dan tidak nol
            st.info(f"💼 **Dompet Akun Real Anda:**  \n💵 Saldo Rupiah: **Rp {saldo_idr_tersedia:,.0f}**  \n🪙 Sisa Koin ({coin_name}): **{saldo_coin:.8f} {coin_name}**")
        except Exception as bal_err:
            st.error(f"⚠️ Hubungan API Gagal: {bal_err}")
    else:
        saldo_idr_tersedia = current_sim_balance
        # PERBAIKAN: Format tampilan sisa koin simulasi didukung sistem presisi 8 desimal
        st.info(f"🎮 **Dompet Kustom Simulasi (Demo):**  \n💵 Saldo Rupiah: **Rp {saldo_idr_tersedia:,.0f}**  \n🪙 Sisa Koin ({coin_name}): **{current_sim_coin:.8f} {coin_name}**")

    try:
        bars = exchange.fetch_ohlcv(symbol_input, TIMEFRAME, limit=int(max_bars_input))
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = calculate_hma(df, HMA_LENGTH)
        
        current_hma = df['hma'].iloc[-1]
        prev_hma = df['hma'].iloc[-2]
        prev_prev_hma = df['hma'].iloc[-3]
        current_close = df['close'].iloc[-1]
        
        is_green_now = current_hma >= prev_hma
        is_green_prev = prev_hma >= prev_prev_hma
        
        raw_buy = is_green_now and not is_green_prev  
        raw_sell = not is_green_now and is_green_prev 
        
        col1, col2 = st.columns(2)
        col1.metric(label=f"Harga Sekarang ({symbol_input})", value=f"{current_close:,.0f} IDR")
        
        if is_green_now:
            col2.metric(label="Status Tren HHMA", value="HIJAU (BUY ZONE)", delta="Naik")
        else:
            col2.metric(label="Status Tren HHMA", value="MERAH (SELL ZONE)", delta="-Turun", delta_color="inverse")
            
        # AMBIL DATA POSISI AKTIF
        history_conn = sqlite3.connect('trading_bot.db')
        target_status = 'LIVE_OPEN' if mode_input == "Live Trading Real" else 'DEMO_OPEN'
        active_trades = pd.read_sql_query(f"SELECT * FROM trades WHERE status='{target_status}'", history_conn)
        history_conn.close()
        
        st.subheader("📊 Tabel Running (Posisi Terbuka Saat Ini)")
        if not active_trades.empty:
            display_running = active_trades.copy()
            display_running['Current Price'] = current_close
            display_running['Floating P&L (%)'] = ((current_close - display_running['price']) / display_running['price']) * 100
            st.dataframe(display_running[['timestamp', 'signal_type', 'price', 'Current Price', 'amount', 'Floating P&L (%)']], use_container_width=True)
            
            for idx, row in active_trades.iterrows():
                trade_id = row['id']
                buy_price = row['price']
                highest_so_far = max(row['highest_price'], current_close)
                profit_pct = ((highest_so_far - buy_price) / buy_price) * 100
                
                # A. Auto-Cut Loss Instan jika sinyal lenyap
                if not is_green_now:
                    if mode_input == "Live Trading Real" and api_input and secret_input:
                        try: exchange.create_market_sell_order(symbol_input, row['amount'])
                        except: pass
                    else:
                        save_setting("sim_balance", num_val=float(current_sim_balance + (current_close * row['amount'])))
                        save_setting("sim_coin", num_val=0.0)
                    update_active_trade(trade_id, highest_so_far, "CLOSED_BY_SIGNAL_DISAPPEARED")
                    save_setting("last_signal", num_val=-1.0)
                    st.session_state.last_signal = -1
                    st.toast("🟥 Sinyal Palsu Menghilang! Bot Langsung Cut Loss Otomatis.", icon="🚨")
                    st.rerun()

                # B. Pengunci Profit Otomatis (Trailing Take Profit)
                if profit_pct >= tp_pct_input:
                    lock_price = highest_so_far * 0.995 
                    if current_close <= lock_price:
                        if mode_input == "Live Trading Real" and api_input and secret_input:
                            try: exchange.create_market_sell_order(symbol_input, row['amount'])
                            except: pass
                        else:
                            save_setting("sim_balance", num_val=float(current_sim_balance + (current_close * row['amount'])))
                            save_setting("sim_coin", num_val=0.0)
                        update_active_trade(trade_id, highest_so_far, "CLOSED_BY_LOCK_PROFIT")
                        save_setting("last_signal", num_val=-1.0)
                        st.session_state.last_signal = -1
                        st.toast("💰 Keuntungan Berhasil Dikunci Otomatis!", icon="🔒")
                        st.rerun()
                
                # C. Stop Loss Fisik (Batas Cut Loss Persentase)
                sl_price = buy_price * (1 - (sl_pct_input / 100))
                if current_close <= sl_price:
                    if mode_input == "Live Trading Real" and api_input and secret_input:
                        try: exchange.create_market_sell_order(symbol_input, row['amount'])
                        except: pass
                    else:
                        save_setting("sim_balance", num_val=float(current_sim_balance + (current_close * row['amount'])))
                        save_setting("sim_coin", num_val=0.0)
                    update_active_trade(trade_id, highest_so_far, "CLOSED_BY_STOP_LOSS")
                    save_setting("last_signal", num_val=-1.0)
                    st.session_state.last_signal = -1
                    st.toast("🟥 Batasan Rugi Terpenuhi (Cut Loss)", icon="🛑")
                    st.rerun()
                    
                if highest_so_far > row['highest_price']:
                    update_active_trade(trade_id, highest_so_far, row['status'])
        else:
            st.info("Tidak ada posisi yang sedang berjalan.")

        # SAKELAR EKSEKUSI UTAMA (ANTI-REPAINT & ANTI BELI BERUNTUN)
        if raw_buy and st.session_state.last_signal != 1:
            nominal_belanja = min(order_idr_input, saldo_idr_tersedia)
            
            if nominal_belanja < 10000:
                st.error("❌ Saldo Rupiah (IDR) tidak cukup untuk eksekusi instan!")
            else:
                tp = current_close * (1 + (tp_pct_input / 100))
                sl = current_close * (1 - (sl_pct_input / 100))
                amount_to_buy = nominal_belanja / current_close 
                
                if mode_input == "Live Trading Real" and api_input and secret_input:
                    try:
                        order = exchange.create_market_buy_order(symbol_input, amount_to_buy)
                        status_order = "LIVE_OPEN"
                    except Exception as trade_err:
                        st.error(f"Gagal Eksekusi Live Buy: {trade_err}")
                        status_order = f"ERROR_BUY: {str(trade_err)[:30]}"
                else:
                    status_order = "DEMO_OPEN"
                    # PERBAIKAN: Mengunci pengurangan saldo dan penambahan koin simulasi agar tidak terus terkuras saat refresh
                    save_setting("sim_balance", num_val=float(current_sim_balance - nominal_belanja))
                    save_setting("sim_coin", num_val=float(current_sim_coin + amount_to_buy))
                
                save_trade('BUY', current_close, amount_to_buy, tp, sl, current_close, status_order)
                save_setting("last_signal", num_val=1.0)
                st.session_state.last_signal = 1  
                st.toast("🟩 INSTAN BUY BERHASIL!", icon="🛒")
                st.rerun() 
            
        elif raw_sell and st.session_state.last_signal == 1:
            for idx, row in active_trades.iterrows():
                if mode_input == "Live Trading Real" and api_input and secret_input:
                    try: exchange.create_market_sell_order(symbol_input, row['amount'])
                    except: pass
                else:
                    save_setting("sim_balance", num_val=float(current_sim_balance + (current_close * row['amount'])))
                    save_setting("sim_coin", num_val=0.0)
                update_active_trade(row['id'], max(row['highest_price'], current_close), "CLOSED_BY_INDICATOR_SELL")
            
            tp = current_close * (1 - (tp_pct_input / 100))
            sl = current_close * (1 + (sl_pct_input / 100))
            amount_to_sell = order_idr_input / current_close
            
            status_order = "LIVE_CLOSED" if mode_input == "Live Trading Real" else "DEMO_CLOSED"
            save_trade('SELL', current_close, amount_to_sell, tp, sl, current_close, status_order)
            save_setting("last_signal", num_val=-1.0)
            st.session_state.last_signal = -1  
            st.toast("🟥 AUTOMATIC SELL BERHASIL!", icon="💰")
            st.rerun()
            
        st.line_chart(df[['close', 'hma']].tail(int(max_bars_input)))
        
    except Exception as e:
        st.error(f"Koneksi Indodax terputus, memuat ulang... ({e})")

# ==========================================
# ALUR UTAMA HALAMAN WEB
# ==========================================
st.title("🤖 Indodax Auto Trading Bot Pro")

# HITUNG TOTAL PROFIT, LOSS, DAN WIN RATE AKURASI SINYAL 
target_filter = "Hanya Live Trading" if mode_input == "Live Trading Real" else "Hanya Demo (Simulasi)"
history_df = get_trade_history(target_filter)

closed_trades = history_df[history_df['status'].str.contains('CLOSED|LOCK|LOSS', na=False)].copy()
total_closed = len(closed_trades)

total_profit_idr = 0.0
total_profit_pct = 0.0
win_rate = 0.0

if total_closed > 0:
    win_trades = len(closed_trades[closed_trades['status'].str.contains('LOCK', na=False)])
    win_rate = (win_trades / total_closed) * 100
    all_buys = history_df[history_df['signal_type'] == 'BUY']
    
    for idx, row_closed in closed_trades.iterrows():
        match_buy = all_buys[all_buys['id'] > row_closed['id']].head(1)
        if not match_buy.empty:
            harga_beli = match_buy['price'].values[0]
            harga_jual = row_closed['price']
            banyak_koin = row_closed['amount']
            
            profit_idr = (harga_jual - harga_beli) * banyak_koin
            profit_pct = ((harga_jual - harga_beli) / harga_beli) * 100
            
            total_profit_idr += profit_idr
            total_profit_pct += profit_pct

col_p1, col_p2, col_p3 = st.columns(3)
col_p1.metric(label="🎯 Akurasi Sinyal (Win Rate)", value=f"{win_rate:.1f} %")
col_p2.metric(label="💰 Profit Bersih (IDR)", value=f"Rp {total_profit_idr:,.0f}", delta=f"{total_profit_pct:.2f}%" if total_profit_idr >= 0 else f"{total_profit_pct:.2f}%")
col_p3.metric(label="📦 Total Trade Selesai", value=f"{total_closed} Kali")

if mode_input == "Live Trading Real":
    st.success("💼 AKUN LIVE TRADING REAL AKTIF (Menggunakan Saldo Asli Indodax)")
else:
    st.warning("⚠️ AKUN DEMO / SIMULASI AKTIF (Aman Untuk Uji Coba Sinyal)")

st.subheader("Live Market Tracker (4H - HMA 8)")
market_monitor_fragment()

st.subheader("📦 Buku Transaksi Historis")
filter_pilihan = st.radio("Saring Data Tabel:", ["Semua Transaksi", "Hanya Live Trading", "Hanya Demo (Simulasi)"], horizontal=True)
history_table = get_trade_history(filter_pilihan)

if not history_table.empty:
    st.dataframe(history_table.head(15), use_container_width=True)
else:
    st.info("Tabel kosong. Menunggu sinyal otomatis berjalan.")
