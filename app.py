import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import sqlite3
from datetime import datetime

# ==========================================
# 1. KONFIGURASI LAYAR CHROME HP & DATABASE
# ==========================================
st.set_page_config(layout="vertical", page_title="Indodax Pro Bot", page_icon="🤖")

DB_NAME = 'trading_bot.db'

def init_db():
    """Inisialisasi database lokal SQLite agar anti-reset di Streamlit Cloud"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    # Tabel untuk riwayat transaksi
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
    # Tabel untuk status permanen (Last Signal, Highest Price untuk TTP)
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
    return row[0] if row else default

def set_setting(key, val):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, val) VALUES (?, ?)", (key, str(val)))
    conn.commit()
    conn.close()

# Jalankan inisialisasi DB di awal
init_db()

# ==========================================
# 2. SIDEBAR UTAMA & PARAMETER DINAMIS
# ==========================================
st.sidebar.header("⚙️ KONTROL BOT V5")

# Dropdown Periode HMA (Bisa dipilih sesuka hati dari HP, default ditanam ke 20)
hma_period = st.sidebar.selectbox(
    "Periode HMA (Rekomendasi: 20)",
    options=[5, 8, 14, 20, 50],
    index=3  # Default mengarah ke angka 20
)

sl_input = st.sidebar.number_input("Stop Loss Fisik (%)", min_value=0.5, max_value=10.0, value=2.0, step=0.1)
mode_dompet = st.sidebar.radio("Mode Akun", ["Demo/Simulasi", "Live Trading Real"])

# ==========================================
# 3. ENGINE STRATEGI HMA (UNIVERSAL)
# ==========================================
def hitung_hma_dinamis(df, period):
    """Menghitung Hull Moving Average secara akurat dan menentukan arah warna"""
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
    
    # Penentuan warna tren berdasarkan arah kemiringan garis HMA
    df['hma_color'] = 'MERAH'
    df.loc[df['hma_val'] > df['hma_val'].shift(1), 'hma_color'] = 'HIJAU'
    return df

# ==========================================
# 4. DATA DUMMY GENERATOR (SIMULASI API 4H)
# ==========================================
@st.cache_data(ttl=60)
def fetch_market_data(pair):
    """Simulasi data OHLCV Timeframe 4 Jam untuk demonstrasi berjalan"""
    np.random.seed(42 if pair == 'BTC/IDR' else 24)
    dates = pd.date_range(end=datetime.now(), periods=100, freq='4h')
    close = 100000 + np.cumsum(np.random.randn(100) * 1500)
    open_p = close - (np.random.randn(100) * 800)
    high = np.maximum(open_p, close) + np.random.rand(100) * 500
    low = np.minimum(open_p, close) - np.random.rand(100) * 500
    volume = np.random.randint(10, 100, size=100)
    
    return pd.DataFrame({'open': open_p, 'high': high, 'low': low, 'close': close, 'volume': volume}, index=dates)

# ==========================================
# 5. CORE LOGIKA TRADING AGRESIF INSTAN & TTP
# ==========================================
def jalankan_engine_bot(pair, df):
    df = hitung_hma_dinamis(df, hma_period)
    
    # Ambil bar berjalan saat ini (iloc[-1]) untuk keagresifan instan
    bar_berjalan = df.iloc[-1]
    bar_sebelumnya = df.iloc[-2]
    
    harga_sekarang = bar_berjalan['close']
    warna_sekarang = bar_berjalan['hma_color']
    warna_sebelumnya = bar_sebelumnya['hma_color']
    
    # Ambil status permanen dari database lokal
    last_signal = get_setting(f"last_signal_{pair}", default="SELL")
    posisi_aktif = get_setting(f"posisi_aktif_{pair}", default="FALSE")
    harga_masuk = float(get_setting(f"harga_masuk_{pair}", default=0.0))
    highest_price = float(get_setting(f"highest_price_{pair}", default=0.0))
    
    pemicu_aksi = None
    notif_pesan = "Menunggu Sinyal Valid..."
    
    # --- LOGIKA EMERGENSI: JIKA SEDANG PUNYA POSISI AKTIF (BUY) ---
    if posisi_aktif == "TRUE":
        # 1. Update Harga Tertinggi untuk Trailing Take Profit (TTP)
        if harga_sekarang > highest_price:
            highest_price = harga_sekarang
            set_setting(f"highest_price_{pair}", highest_price)
            
        # Perhitungan Jarak Turun dari titik puncak tertinggi
        persen_turun_dari_puncak = ((highest_price - harga_sekarang) / highest_price) * 100
        # Batas target minimal TTP agar aman (misal harga sudah naik 1% dari modal awal)
        sudah_untung = harga_sekarang > (harga_masuk * 1.01)
        
        # 2. Eksekusi Trailing Take Profit (Turun 0.5% dari Puncak)
        if sudah_untung and persen_turun_dari_puncak >= 0.5:
            pemicu_aksi = "SELL"
            notif_pesan = "🎯 TRAILING TAKE PROFIT (TTP 0.5% Terkunci)"
            
        # 3. Eksekusi Stop Loss Fisik (Sidebar)
        elif harga_sekarang <= harga_masuk * (1 - (sl_input / 100)):
            pemicu_aksi = "SELL"
            notif_pesan = f"⚠️ STOP LOSS FISIK ({sl_input}%) TERJANGKAU"
            
        # 4. Eksekusi Proteksi Anti-Repaint (Panah BUY hilang / garis balik merah)
        elif warna_sekarang == "MERAH":
            pemicu_aksi = "SELL"
            notif_pesan = "🚨 ANTI-REPAINT CUT-LOSS (Sinyal Hilang Berbalik Arah)"

    # --- LOGIKA PEMICU SINYAL BARU (WAJIB BERGANTIAN VIA DB) ---
    else:
        if warna_sekarang == "HIJAU" and warna_sebelumnya == "MERAH" and last_signal == "SELL":
            pemicu_aksi = "BUY"
            notif_pesan = "🚀 SINYAL BUY AGRESIF INSTAN VALID"

    # --- EKSEKUSI DATA KE SQLITE JIKA ADA AKSI TRADING ---
    if pemicu_aksi:
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
        st.toast(f"{pair}: {notif_pesan} di harga {harga_sekarang:,.2f}", icon="📈")
        
    return df, notif_pesan, harga_sekarang

# ==========================================
# 6. TAMPILAN LAYAR UTAMA CHROME HP (WIDGETS)
# ==========================================
# Ambil data transaksi dari SQLite untuk kalkulasi widget skor performa keseluruhan
conn = sqlite3.connect(DB_NAME)
df_trades = pd.read_sql_query("SELECT * FROM trades WHERE tipe='SELL'", conn)
conn.close()

total_trades = len(df_trades)
win_trades = len(df_trades[df_trades['profit_idr'] > 0]) if total_trades > 0 else 0
win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0.0
total_net_profit = df_trades['profit_idr'].sum() if total_trades > 0 else 0.0

# Baris Widget Ringkas Hemat Ruang HP
col1, col2, col3 = st.columns(3)
col1.metric("Win Rate", f"{win_rate:.1f}%", f"{total_trades} Trades")
col2.metric("Net Profit", f"Rp {total_net_profit:,.0f}")
col3.metric("Live Wallet", "8.12345678 BTC" if mode_dompet == "Live Trading Real" else "100,000,000 IDR")

# Dropdown Pemilihan Pair Aktif
daftar_pair = ['BTC/IDR', 'ETH/IDR', 'USDT/IDR', 'SOL/IDR', 'DOGE/IDR']
selected_pair = st.selectbox("🎯 Pilih Monitor Grafik Pair:", daftar_pair)

# Jalankan mesin bot untuk pair yang dipilih
df_market = fetch_market_data(selected_pair)
df_hasil, status_bot, live_price = jalankan_engine_bot(selected_pair, df_market)

st.info(f"**Status Terkini {selected_pair}:** {status_bot} | **Harga Running:** Rp {live_price:,.2f}")

# ==========================================
# 7. INTERFAS GRAFIK CANDLESTICK PLOTLY
# ==========================================
fig = go.Figure()

# Plot Candlestick
fig.add_trace(go.Candlestick(
    x=df_hasil.index, open=df_hasil['open'], high=df_hasil['high'],
    low=df_hasil['low'], close=df_hasil['close'], name="Candle"
))

# Plot Garis HMA Dinamis Mengikuti Pilihan Sidebar
fig.add_trace(go.Scatter(
    x=df_hasil.index, y=df_hasil['hma_val'],
    line=dict(color='cyan', width=2), name=f"HMA {hma_period}"
))

fig.update_layout(
    margin=dict(l=10, r=10, t=10, b=10),
    xaxis_rangeslider_visible=False,
    height=350,  # Pas untuk ukuran vertikal layar HP Chrome
    paper_bgcolor='#111111',
    plot_bgcolor='#111111',
    font=dict(color='white')
)
st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 8. TABEL RUNNING TRADES (HISTORI LOKAL)
# ==========================================
st.subheader("📋 Catatan Log Jurnal Trading (SQLite)")
conn = sqlite3.connect(DB_NAME)
df_all_logs = pd.read_sql_query("SELECT timestamp, pair, tipe, harga, pemicu, profit_persen FROM trades ORDER BY id DESC LIMIT 5", conn)
conn.close()

if not df_all_logs.empty:
    st.dataframe(df_all_logs, use_container_width=True)
else:
    st.caption("Belum ada eksekusi trade terdeteksi di database lokal.")
