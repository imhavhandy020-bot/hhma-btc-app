import streamlit as st
import pandas as pd
import numpy as np
import ccxt
import sqlite3
from datetime import datetime
import plotly.graph_objects as go

# Konfigurasi Tampilan Layar HP
st.set_page_config(page_title="Indodax Multi-Pair Pro Bot", layout="centered")

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
            pair TEXT,
            signal_type TEXT,
            price REAL,
            amount REAL,
            tp_price REAL,
            sl_price REAL,
            highest_price REAL,
            status TEXT
        )
    ''')
    try: cursor.execute("ALTER TABLE trades ADD COLUMN pair TEXT"); conn.commit()
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE trades ADD COLUMN amount REAL"); conn.commit()
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE trades ADD COLUMN highest_price REAL"); conn.commit()
    except sqlite3.OperationalError: pass 

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
        if default_text is not None: return row if row is not None else default_text
        if default_num is not None: return row if row is not None else default_num
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

def save_trade(pair, signal_type, price, amount, tp, sl, highest, status="OPEN"):
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (timestamp, pair, signal_type, price, amount, tp_price, sl_price, highest_price, status)
        VALUES (datetime('now'), ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (pair, signal_type, price, amount, tp, sl, highest, status))
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

# Parameter Kunci Mati
TIMEFRAME = "4h"   
HMA_LENGTH = 8     

db_api = get_setting("api_key", default_text="")
db_secret = get_setting("secret_key", default_text="")
db_max_bars = int(get_setting("max_bars", default_num=100.0))
db_tp_pct = get_setting("tp_pct", default_num=5.0)
db_sl_pct = get_setting("sl_pct", default_num=2.0)
db_order_idr = get_setting("order_idr", default_num=50000.0)
db_sim_balance = get_setting("sim_balance", default_num=10000000.0)
db_refresh_rate = int(get_setting("refresh_rate", default_num=5.0))
db_mode = get_setting("bot_mode", default_text="Demo (Simulasi)")

# ==========================================
# MENU INPUT PARAMETER (SIDEBAR HP)
# ==========================================
st.sidebar.title("⚙️ Kendali Multi-Pair Bot")

st.sidebar.subheader("🔌 Mode Operasional Bot")
mode_input = st.sidebar.radio("Pilih Sistem:", ["Demo (Simulasi)", "Live Trading Real"], index=0 if db_mode == "Demo (Simulasi)" else 1)
if mode_input != db_mode: save_setting("bot_mode", text_val=mode_input)

st.sidebar.subheader("🔑 Kredensial Akun Indodax")
api_input = st.sidebar.text_input("API Key", type="password", value=db_api)
secret_input = st.sidebar.text_input("Secret Key", type="password", value=db_secret)
if api_input != db_api: save_setting("api_key", text_val=api_input)
if secret_input != db_secret: save_setting("secret_key", text_val=secret_input)

if mode_input == "Demo (Simulasi)":
    sim_balance_input = st.sidebar.number_input("Modal Awal Demo (IDR)", min_value=10000.0, value=db_sim_balance, step=500000.0)
    if sim_balance_input != db_sim_balance: save_setting("sim_balance", num_val=sim_balance_input)
else: sim_balance_input = db_sim_balance

order_idr_input = st.sidebar.number_input("Jumlah Beli Per Sinyal (IDR)", min_value=10000.0, value=db_order_idr, step=5000.0)
if order_idr_input != db_order_idr: save_setting("order_idr", num_val=order_idr_input)

LIST_PAIRS = ["BTC/IDR", "ETH/IDR", "USDT/IDR", "SOL/IDR", "DOGE/IDR"]
st.sidebar.info(f"📋 **Aset Dipantau Serentak:** {', '.join(LIST_PAIRS)}")

max_bars_input = st.sidebar.slider("Pembatasan Bar Tampilan", min_value=10, max_value=500, value=db_max_bars)
if max_bars_input != db_max_bars: save_setting("max_bars", num_val=float(max_bars_input))

tp_pct_input = st.sidebar.number_input("Pelebaran Profit / TP (%)", min_value=0.1, value=db_tp_pct)
if tp_pct_input != db_tp_pct: save_setting("tp_pct", num_val=tp_pct_input)

sl_pct_input = st.sidebar.number_input("Stop Loss / SL (%)", min_value=0.1, value=db_sl_pct)
if sl_pct_input != db_sl_pct: save_setting("sl_pct", num_val=sl_pct_input)

refresh_rate_input = st.sidebar.slider("Jeda Auto-Refresh (Detik)", min_value=1, max_value=60, value=db_refresh_rate)
if refresh_rate_input != db_refresh_rate: save_setting("refresh_rate", num_val=float(refresh_rate_input))

if st.sidebar.button("🗑️ Hapus Semua Riwayat Tabel", type="primary", use_container_width=True):
    clear_db()
    for p in LIST_PAIRS:
        save_setting(f"last_signal_{p}", num_val=0.0)
        save_setting(f"sim_coin_{p}", num_val=0.0)
    st.sidebar.success("Database dibersihkan!")
    st.rerun()

exchange = ccxt.indodax({'apiKey': api_input, 'secret': secret_input, 'enableRateLimit': True}) if api_input and secret_input else ccxt.indodax({'enableRateLimit': True})

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
# KOMPONEN REFRESH DAN EKSEKUSI MULTI-PAIR
# ==========================================
@st.fragment(run_every=refresh_rate_input)
def market_monitor_fragment():
    waktu_sekarang = datetime.now().strftime('%H:%M:%S')
    st.caption(f"🔄 Sinkronisasi Multi-Pair Indodax (Setiap {refresh_rate_input} Detik): {waktu_sekarang}")
    
    current_sim_balance = get_setting("sim_balance", default_num=10000000.0)
    saldo_idr_tersedia = 0.0

    if mode_input == "Live Trading Real" and api_input and secret_input:
        try:
            balance = exchange.fetch_balance()
            saldo_idr_tersedia = balance['free']['IDR'] if 'IDR' in balance['free'] else 0.0
            st.info(f"💼 **Dompet Live IDR Anda:** **Rp {saldo_idr_tersedia:,.0f}**")
        except:
            st.error("⚠️ Hubungan API Gagal Dimuat")
            saldo_idr_tersedia = 0.0
    else:
        st.info(f"🎮 **Dompet Demo IDR Anda:** **Rp {current_sim_balance:,.0f}**")
        saldo_idr_tersedia = current_sim_balance

    # Pilihan koin untuk digambar grafiknya di layar HP agar tidak bertumpuk
    st.write("---")
    pair_grafik = st.selectbox("🎯 Pilih Grafik Candlestick Aset yang Mau Dilihat:", LIST_PAIRS, index=0)

    for pair in LIST_PAIRS:
        coin_name = pair.split('/')[0]
        last_sig_key = f"last_signal_{pair}"
        sim_coin_key = f"sim_coin_{pair}"
        
        last_signal_pair = int(get_setting(last_sig_key, default_num=0.0))
        current_sim_coin = get_setting(sim_coin_key, default_num=0.0)
        
        try:
            bars = exchange.fetch_ohlcv(pair, TIMEFRAME, limit=int(max_bars_input))
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = calculate_hma(df, HMA_LENGTH)
            
            current_hma = df['hma'].iloc[-1]
            prev_hma = df['hma'].iloc[-2]
            prev_prev_hma = df['hma'].iloc[-3]
            current_close = df['close'].iloc[-1]
            
            is_green = current_hma >= prev_hma
            is_green_prev = prev_hma >= prev_prev_hma
            
            raw_buy = is_green and not is_green_prev
            raw_sell = not is_green and is_green_prev
            
            # AMBIL DATA RUNNING TRADES KHUSUS PAIR INI
            history_conn = sqlite3.connect('trading_bot.db')
            target_status = 'LIVE_OPEN' if mode_input == "Live Trading Real" else 'DEMO_OPEN'
            active_trades = pd.read_sql_query(f"SELECT * FROM trades WHERE status='{target_status}' AND pair='{pair}'", history_conn)
            history_conn.close()

            # ─── PENGUNCI PROFIT & PELINDUNG SINYAL PALSU (ANTI REPAINT) ───
            if not active_trades.empty:
                for idx, row in active_trades.iterrows():
                    trade_id = row['id']
                    buy_price = row['price']
                    highest_so_far = max(row['highest_price'], current_close)
                    profit_pct = ((highest_so_far - buy_price) / buy_price) * 100
                    
                    if not is_green:
                        if mode_input == "Live Trading Real" and api_input and secret_input:
                            try: exchange.create_market_sell_order(pair, row['amount'])
                            except: pass
                        else:
                            save_setting("sim_balance", num_val=float(current_sim_balance + (current_close * row['amount'])))
                            save_setting(sim_coin_key, num_val=0.0)
                        update_active_trade(trade_id, highest_so_far, "CLOSED_BY_SIGNAL_DISAPPEARED")
                        save_setting(last_sig_key, num_val=-1.0)
                        st.toast(f"🟥 {pair} Sinyal Palsu Lenyap! Auto Cut-Loss.", icon="🚨")
                        st.rerun()
                    
                    if profit_pct >= tp_pct_input:
                        if current_close <= (highest_so_far * 0.995):
                            if mode_input == "Live Trading Real" and api_input and secret_input:
                                try: exchange.create_market_sell_order(pair, row['amount'])
                                except: pass
                            else:
                                save_setting("sim_balance", num_val=float(current_sim_balance + (current_close * row['amount'])))
                                save_setting(sim_coin_key, num_val=0.0)
                            update_active_trade(trade_id, highest_so_far, "CLOSED_BY_LOCK_PROFIT")
                            save_setting(last_sig_key, num_val=-1.0)
                            st.toast(f"💰 {pair} Keuntungan Berhasil Dikunci!", icon="🔒")
                            st.rerun()
                    
                    sl_price = buy_price * (1 - (sl_pct_input / 100))
                    if current_close <= sl_price:
                        if mode_input == "Live Trading Real" and api_input and secret_input:
                            try: exchange.create_market_sell_order(pair, row['amount'])
                            except: pass
                        else:
                            save_setting("sim_balance", num_val=float(current_sim_balance + (current_close * row['amount'])))
                            save_setting(sim_coin_key, num_val=0.0)
                        update_active_trade(trade_id, highest_so_far, "CLOSED_BY_STOP_LOSS")
                        save_setting(last_sig_key, num_val=-1.0)
                        st.toast(f"🟥 {pair} Batasan Rugi Terpenuhi (Cut Loss)", icon="🛑")
                        st.rerun()
                        
                    if highest_so_far > row['highest_price']:
                        update_active_trade(trade_id, highest_so_far, row['status'])

            # ─── SAKELAR EKSEKUSI UTAMA (ANTI BELI BERUNTUN SEJENIS) ───
            if raw_buy and last_signal_pair != 1:
                nominal_belanja = min(order_idr_input, saldo_idr_tersedia)
                if nominal_belanja >= 10000:
                    tp = current_close * (1 + (tp_pct_input / 100))
                    sl = current_close * (1 - (sl_pct_input / 100))
                    amount_to_buy = nominal_belanja / current_close
                    
                    if mode_input == "Live Trading Real" and api_input and secret_input:
                        try:
                            exchange.create_market_buy_order(pair, amount_to_buy)
                            status_order = "LIVE_OPEN"
                        except: status_order = "ERROR_BUY"
                    else:
                        status_order = "DEMO_OPEN"
                        save_setting("sim_balance", num_val=float(current_sim_balance - nominal_belanja))
                        save_setting(sim_coin_key, num_val=float(current_sim_coin + amount_to_buy))
                    
                    save_trade(pair, 'BUY', current_close, amount_to_buy, tp, sl, current_close, status_order)
                    save_setting(last_sig_key, num_val=1.0)
                    st.toast(f"🟩 {pair} INSTAN BUY BERHASIL!", icon="🛒")
                    st.rerun()

            # ─── BARU: LOGIKA GAMBAR VISUAL CANDLESTICK KHUSUS PAIR YANG DIPILIH ───
            if pair == pair_grafik:
                st.write(f"📈 **Harga {pair} Sekarang:** Rp {current_close:,.0f}")
                
                # Buat kerangka grafik candlestick interaktif
                fig = go.Figure()
                fig.add_trace(go.Candlestick(
                    x=df['datetime'], open=df['open'], high=df['high'], low=df['low'], close=df['close'],
                    name="Candlestick", increasing_line_color='green', decreasing_line_color='red'
                ))
                # Tambahkan garis HHMA dinamis berwarna
                line_color = 'green' if is_green else 'red'
                fig.add_trace(go.Scatter(x=df['datetime'], y=df['hma'], line=dict(color=line_color, width=2.5), name="Garis HHMA"))
                
                # BARU: Tempelkan Tanda Panah Panah BUY / SELL pas melekat di titik harga balok berjalan
                if raw_buy:
                    fig.add_annotation(x=df['datetime'].iloc[-1], y=df['low'].iloc[-1], text="▲ BUY", showarrow=False, yshift=-15, font=dict(color="green", size=14))
                elif raw_sell:
                    fig.add_annotation(x=df['datetime'].iloc[-1], y=df['high'].iloc[-1], text="▼ SELL", showarrow=False, yshift=15, font=dict(color="red", size=14))
                
                fig.update_layout(xaxis_rangeslider_visible=False, height=350, margin=dict(l=10, r=10, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
                    
        except Exception as e:
            pass

    # 3. MENAMPILKAN TABEL RUNNING MULTI-PAIR TERPADU
    st.subheader("📊 Tabel Running (Multi-Pair Terbuka)")
    h_conn = sqlite3.connect('trading_bot.db')
    t_status = 'LIVE_OPEN' if mode_input == "Live Trading Real" else 'DEMO_OPEN'
    all_active = pd.read_sql_query(f"SELECT timestamp, pair, signal_type, price, amount, highest_price FROM trades WHERE status='{t_status}'", h_conn)
    h_conn.close()
    
    if not all_active.empty:
        st.dataframe(all_active, use_container_width=True)
    else:
        st.info("Tidak ada posisi koin berjalan saat ini.")

# ==========================================
# ALUR UTAMA HALAMAN WEB SCREEN
# ==========================================
st.title("🤖 Indodax Auto Trading Bot Multi-Pair")

# KALKULASI STATISTIK WIN RATE GLOBAL & PROFIT BERSIH UTAMA
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
        match_buy = all_buys[(all_buys['id'] > row_closed['id']) & (all_buys['pair'] == row_closed['pair'])].head(1)
        if not match_buy.empty:
            harga_beli = match_buy['price'].values
            harga_jual = row_closed['price']
            banyak_koin = row_closed['amount']
            
            profit_idr = (harga_jual - harga_beli) * banyak_koin
            profit_pct = ((harga_jual - harga_beli) / harga_beli) * 100
            
            total_profit_idr += profit_idr
            total_profit_pct += profit_pct

col_p1, col_p2, col_p3 = st.columns(3)
col_p1.metric(label="🎯 Global Win Rate", value=f"{win_rate:.1f} %")
col_p2.metric(label="💰 Total Profit Bersih", value=f"Rp {total_profit_idr:,.0f}", delta=f"{total_profit_pct:.2f}%" if total_closed > 0 else "0.00%")
col_p3.metric(label="📦 Total Trade Selesai", value=f"{total_closed} Kali")

if mode_input == "Live Trading Real":
    st.success("💼 AKUN LIVE TRADING REAL AKTIF (Menggunakan Saldo Asli Indodax)")
else:
    st.warning("⚠️ AKUN DEMO / SIMULASI AKTIF (Aman Untuk Uji Coba Sinyal)")

st.subheader("Live Multi-Pair Market Tracker (4H - HMA 8)")
market_monitor_fragment()

st.subheader("📦 Buku Transaksi Historis Global")
filter_pilihan = st.radio("Saring Data Tabel:", ["Semua Transaksi", "Hanya Live Trading", "Hanya Demo (Simulasi)"], horizontal=True)
st.dataframe(get_trade_history(filter_pilihan).head(15), use_container_width=True)
