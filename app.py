import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sqlite3
import hmac
import hashlib
import requests
import time
from datetime import datetime
from urllib.parse import urlencode

# ==========================================
# 1. KONFIGURASI UTAMA LAYAR CHROME HP
# ==========================================
# Menggunakan layout "centered" agar seluruh komponen tersusun vertikal rapi di ponsel
st.set_page_config(layout="centered", page_title="Indodax Pro Bot", page_icon="🤖")

DB_NAME = 'trading_bot.db'

def init_db():
    """Inisialisasi database lokal SQLite agar anti-reset di Streamlit Cloud"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            pair TEXT,
            tipe TEXT,
            harga REAL,
            jumlah REAL,
            pemicu TEXT,
            profit_idr REAL,
            profit_persen REAL
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            val TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT val FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row if row else default

def set_setting(key, val):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, val) VALUES (?, ?)", (key, str(val)))
    conn.commit()
    conn.close()

# Jalankan inisialisasi DB di awal sistem
init_db()

# ==========================================
# 2. INTEGRASI PRIVATE TRADE API INDODAX
# ==========================================
def ambil_saldo_indodax(api_key, secret_key, pair):
    """Memanggil metode 'getInfo' untuk sinkronisasi saldo dompet riil"""
    url_tapi = "https://indodax.com"
    nonce = int(time.time() * 1000)
    payload = {'method': 'getInfo', 'nonce': nonce}
    coin_code = pair.split('/')[0].lower()
    
    try:
        query_string = urlencode(payload)
        signature = hmac.new(bytes(secret_key, 'utf-8'), msg=bytes(query_string, 'utf-8'), digestmod=hashlib.sha512).hexdigest()
        headers = {'Key': api_key, 'Sign': signature, 'Content-Type': 'application/x-www-form-urlencoded'}
        
        response = requests.post(url_tapi, data=payload, headers=headers, timeout=10)
        hasil_json = response.json()
        
        if hasil_json.get('success') == 1:
            balances = hasil_json['return']['balance']
            return {"success": True, "idr": float(balances.get('idr', 0.0)), "coin": float(balances.get(coin_code, 0.0)), "coin_symbol": coin_code.upper()}
        return {"success": False, "error": hasil_json.get('error', 'Gagal Response API')}
    except Exception as e:
        return {"success": False, "error": str(e)}

def kirim_order_indodax(api_key, secret_key, pair, tipe_aksi, nominal_idr=None, jumlah_coin=None):
    """Mengirimkan eksekusi Market Order instan (Buy IDR / Sell Coin) ke Indodax"""
    pair_id = pair.replace('/', '_').lower()
    url_tapi = "https://indodax.com"
    nonce = int(time.time() * 1000)
    payload = {'method': 'trade', 'pair': pair_id, 'nonce': nonce}
    
    if tipe_aksi.upper() == "BUY":
        payload.update({'type': 'buy', 'order_type': 'market', 'idr': int(nominal_idr if nominal_idr else 50000)})
    elif tipe_aksi.upper() == "SELL":
        payload.update({'type': 'sell', 'order_type': 'market', 'coin': float(jumlah_coin if jumlah_coin else 0.0)})
    else:
        return {"success": 0, "error": "Aksi Tidak Valid"}

    try:
        query_string = urlencode(payload)
        signature = hmac.new(bytes(secret_key, 'utf-8'), msg=bytes(query_string, 'utf-8'), digestmod=hashlib.sha512).hexdigest()
        headers = {'Key': api_key, 'Sign': signature, 'Content-Type': 'application/x-www-form-urlencoded'}
        
        response = requests.post(url_tapi, data=payload, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": 0, "error": str(e)}

# ==========================================
# 3. SIDEBAR UTAMA & INPUT PARAMETER DINAMIS
# ==========================================
st.sidebar.header("⚙️ KONTROL KUNCI BOT")

# Kolom kunci pengaman (Ketik untuk RUN, kosongkan/hapus untuk STOP)
api_key_input = st.sidebar.text_input("🔑 API Key Indodax", type="password", help="Isi teks untuk mengaktifkan bot. Kosongkan untuk STOP total.")
secret_key_input = st.sidebar.text_input("🔒 Secret Key Indodax", type="password")

bot_is_authenticated = bool(api_key_input and secret_key_input)

if bot_is_authenticated:
    st.sidebar.success("🟢 MESIN AKTIF (Kunci Terhubung)")
else:
    st.sidebar.error("🔴 MESIN MATI TOTAL (Kunci Terputus)")

st.sidebar.markdown("---")
st.sidebar.header("📊 PARAMETER TRADING")

# Fitur Baru: Pengatur Modal Belanja Dinamis langsung dari Sidebar HP
order_size_idr = st.sidebar.number_input(
    "💰 Modal Belanja per Transaksi (IDR)", 
    min_value=10000, 
    max_value=100000000, 
    value=100000, 
    step=10000,
    help="Jumlah uang Rupiah yang dipakai untuk BUY instan di market."
)

hma_period = st.sidebar.selectbox("Periode HMA (Rekomendasi: 20)", options=[5, 8, 14, 20, 50], index=3)
sl_input = st.sidebar.number_input("Stop Loss Fisik (%)", min_value=0.5, max_value=10.0, value=2.0, step=0.1)
mode_dompet = st.sidebar.radio("Mode Akun", ["Demo/Simulasi", "Live Trading Real"])

# ==========================================
# 4. ENGINE STRATEGI HMA (UNIVERSAL)
# ==========================================
def hitung_hma_dinamis(df, period):
    df = df.copy()
    half_length = int(period / 2)
    sqrt_length = int(np.sqrt(period))
    
    def wma(series, window):
        weights = np.arange(1, window + 1)
        return series.rolling(window).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    
    wma_half = wma(df['close'], half_length)
    wma_full = wma(df['close'], period)
    raw_hma = (2 * wma_half) - wma_full
    df['hma_val'] = wma(raw_hma, sqrt_length)
    
    df['hma_color'] = 'MERAH'
    df.loc[df['hma_val'] > df['hma_val'].shift(1), 'hma_color'] = 'HIJAU'
    return df

# ==========================================
# 5. DATA SIMULATOR (OHLCV TIMEFRAME 4 JAM)
# ==========================================
@st.cache_data(ttl=60)
def fetch_market_data(pair):
    """Simulasi pemanggilan data Candlestick 4h Indodax"""
    np.random.seed(42 if pair == 'BTC/IDR' else 24)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='4h')
    close = 100000 + np.cumsum(np.random.randn(100) * 1500)
    open_p = close - (np.random.randn(100) * 800)
    high = np.maximum(open_p, close) + np.random.rand(100) * 500
    low = np.minimum(open_p, close) - np.random.rand(100) * 500
    volume = np.random.randint(10, 100, size=100)
    return pd.DataFrame({'open': open_p, 'high': high, 'low': low, 'close': close, 'volume': volume}, index=dates)

# ==========================================
# 6. CORE LOGIKA TRADING AGRESIF INSTAN (df.iloc[-1])
# ==========================================
def jalankan_engine_bot(pair, df):
    df = hitung_hma_dinamis(df, hma_period)
    
    # Mempertahankan keagresifan instan membaca bar berjalan index terakhir
    bar_berjalan = df.iloc[-1]
    bar_sebelumnya = df.iloc[-2]
    
    harga_sekarang = bar_berjalan['close']
    warna_sekarang = bar_berjalan['hma_color']
    warna_sebelumnya = bar_sebelumnya['hma_color']
    
    last_signal = get_setting(f"last_signal_{pair}", default="SELL")
    posisi_aktif = get_setting(f"posisi_aktif_{pair}", default="FALSE")
    harga_masuk = float(get_setting(f"harga_masuk_{pair}", default=0.0))
    highest_price = float(get_setting(f"highest_price_{pair}", default=0.0))
    
    pemicu_aksi = None
    notif_pesan = "Kunci Pengaman Terbuka. Bot Berhenti." if not bot_is_authenticated else "Menunggu Sinyal Valid..."
    
    # Eksekusi hanya berjalan jika kunci terverifikasi (Kunci Terpasang di HP)
    if bot_is_authenticated:
        # --- LOGIKA EMERGENSI: JIKA POSISI LAGI AKTIF (BUY) ---
        if posisi_aktif == "TRUE":
            if harga_sekarang > highest_price:
                highest_price = harga_sekarang
                set_setting(f"highest_price_{pair}", highest_price)
                
            persen_turun_dari_puncak = ((highest_price - harga_sekarang) / highest_price) * 100
            sudah_untung = harga_sekarang > (harga_masuk * 1.01)
            
            # A. Trailing Take Profit (TTP 0.5% dari Puncak)
            if sudah_untung and persen_turun_dari_puncak >= 0.5:
                pemicu_aksi = "SELL"
                notif_pesan = "🎯 TRAILING TAKE PROFIT (TTP 0.5% Terkunci)"
            # B. Stop Loss Fisik Sidebar
            elif harga_sekarang <= harga_masuk * (1 - (sl_input / 100)):
                pemicu_aksi = "SELL"
                notif_pesan = f"⚠️ STOP LOSS FISIK ({sl_input}%) TERJANGKAU"
            # C. Proteksi Anti-Repaint (Warna HMA berbalik arah instan di bar berjalan)
            elif warna_sekarang == "MERAH":
                pemicu_aksi = "SELL"
                notif_pesan = "🚨 ANTI-REPAINT CUT-LOSS (CLOSED_BY_SIGNAL_DISAPPEARED)"

        # --- LOGIKA PEMICU SINYAL BARU (WAJIB BERGANTIAN VIA DB) ---
        else:
            if warna_sekarang == "HIJAU" and warna_sebelumnya == "MERAH" and last_signal == "SELL":
                pemicu_aksi = "BUY"
                notif_pesan = "🚀 SINYAL BUY AGRESIF INSTAN VALID"

        # --- EKSEKUSI TRANSAKSI LIVE & PENCATATAN SQLITE ---
        if pemicu_aksi:
            api_success = True
            
            # Eksekusi Order Riil ke Server Indodax jika Akun disetel Live
            if mode_dompet == "Live Trading Real":
                if pemicu_aksi == "BUY":
                    # Menggunakan nominal IDR dinamis dari input sidebar
                    res_api = kirim_order_indodax(api_key_input, secret_key_input, pair, "BUY", nominal_idr=order_size_idr)
                else:
                    # Mengosongkan volume koin (0.0) agar sistem melepas seluruh isi koin di dompet
                    res_api = kirim_order_indodax(api_key_input, secret_key_input, pair, "SELL", jumlah_coin=0.0)
                
                if res_api.get('success') != 1:
                    api_success = False
                    notif_pesan += f" | ❌ API Error: {res_api.get('error')}"
            
            # Jika eksekusi sukses (atau mode simulasi), kunci status permanen ke SQLite
            if api_success:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                if pemicu_aksi == "BUY":
                    cursor.execute("INSERT INTO trades (timestamp, pair, tipe, harga, jumlah, pemicu, profit_idr, profit_persen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                   (ts, pair, "BUY", harga_sekarang, 1.0, notif_pesan, 0.0, 0.0))
                    set_setting(f"last_signal_{pair}", "BUY")
                    set_setting(f"posisi_aktif_{pair}", "TRUE")
                    set_setting(f"harga_masuk_{pair}", harga_sekarang)
                    set_setting(f"highest_price_{pair}", harga_sekarang)
                elif pemicu_aksi == "SELL":
                    profit_idr = (harga_sekarang - harga_masuk) * 1.0
                    profit_persen = ((harga_sekarang - harga_masuk) / harga_masuk) * 100
                    cursor.execute("INSERT INTO trades (timestamp, pair, tipe, harga, jumlah, pemicu, profit_idr, profit_persen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                                   (ts, pair, "SELL", harga_sekarang, 1.0, notif_pesan, profit_idr, profit_persen))
                    set_setting(f"last_signal_{pair}", "SELL")
                    set_setting(f"posisi_aktif_{pair}", "FALSE")
                    set_setting(f"harga_masuk_{pair}", 0.0)
                    set_setting(f"highest_price_{pair}", 0.0)
                    
                conn.commit()
                conn.close()
                st.toast(f"{pair}: {notif_pesan}", icon="📈")
                
    return df, notif_pesan, harga_sekarang

# ==========================================
# 7. TAMPILAN LAYAR UTAMA CHROME HP (WIDGETS)
# ==========================================
conn = sqlite3.connect(DB_NAME)
df_trades = pd.read_sql_query("SELECT * FROM trades WHERE tipe='SELL'", conn)
conn.close()

total_trades = len(df_trades)
win_trades = len(df_trades[df_trades['profit_idr'] > 0]) if total_trades > 0 else 0
win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0.0
total_net_profit = df_trades['profit_idr'].sum() if total_trades > 0 else 0.0

# Dropdown Pemilihan Aset Pair Aktif
daftar_pair = ['BTC/IDR', 'ETH/IDR', 'USDT/IDR', 'SOL/IDR', 'DOGE/IDR']
selected_pair = st.selectbox("🎯 Pilih Monitor Grafik Pair:", daftar_pair)

# Sinkronisasi Dompet Riil/Demo secara Dinamis
saldo_idr_tampil = 100000000.0
saldo_coin_tampil = 8.12345678
coin_label = selected_pair.split('/')[0]

if mode_dompet == "Live Trading Real" and bot_is_authenticated:
    data_dompet = ambil_saldo_indodax(api_key_input, secret_key_input, pair=selected_pair)
    if data_dompet.get("success"):
        saldo_idr_tampil = data_dompet["idr"]
        saldo_coin_tampil = data_dompet["coin"]
        coin_label = data_dompet["coin_symbol"]

col1, col2, col3 = st.columns(3)
col1.metric("Win Rate", f"{win_rate:.1f}%", f"{total_trades} Trades")
col2.metric("Wallet IDR", f"Rp {saldo_idr_tampil:,.0f}")
col3.metric(f"Wallet {coin_label}", f"{saldo_coin_tampil:.8f}")

df_market = fetch_market_data(selected_pair)
df_hasil, status_bot, live_price = jalankan_engine_bot(selected_pair, df_market)

if bot_is_authenticated:
    st.success(f"🤖 **Status Sistem:** {status_bot} | **Harga:** Rp {live_price:,.2f}")
else:
    st.error(f"🛑 **Status Keamanan:** Kunci Terputus. Hubungkan Key di Sidebar untuk Menyalakan Mesin.")

# ==========================================
# 8. INTERFAS GRAFIK CANDLESTICK PLOTLY
# ==========================================
fig = go.Figure()
fig.add_trace(go.Candlestick(x=df_hasil.index, open=df_hasil['open'], high=df_hasil['high'], low=df_hasil['low'], close=df_hasil['close'], name="Candle"))
fig.add_trace(go.Scatter(x=df_hasil.index, y=df_hasil['hma_val'], line=dict(color='cyan', width=2), name=f"HMA {hma_period}"))
fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_rangeslider_visible=False, height=350, paper_bgcolor='#111111', plot_bgcolor='#111111', font=dict(color='white'))
st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 9. TABEL HISTORI LOG JURNAL TRADING SQLITE
# ==========================================
st.subheader("📋 Catatan Log Jurnal Trading (SQLite)")
conn = sqlite3.connect(DB_NAME)
df_all_logs = pd.read_sql_query("SELECT timestamp, pair, tipe, harga, pemicu, profit_persen FROM trades ORDER BY id DESC LIMIT 5", conn)
conn.close()

if not df_all_logs.empty:
    st.dataframe(df_all_logs, use_container_width=True)
else:
    st.caption("Belum ada eksekusi trade terdeteksi di database lokal.")
