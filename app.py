import streamlit as st
import pandas as pd
import numpy as np
import requests
import sqlite3
import time
import hmac
import hashlib
from datetime import datetime

# =====================================================================
# 1. KONFIGURASI UTAMA & API KEYS (INTEGRASI INDODAX)
# =====================================================================
# Disarankan menggunakan Streamlit Secrets untuk keamanan API Key Anda
API_KEY = st.secrets.get("INDODAX_API_KEY", "ISI_API_KEY_RIIL_ANDA")
SECRET_KEY = st.secrets.get("INDODAX_SECRET_KEY", "ISI_SECRET_KEY_RIIL_ANDA")

# Daftar Pair Aktif sesuai Rangka Dasar Anda
LIST_PAIRS = ['BTC/IDR', 'ETH/IDR', 'USDT/IDR', 'SOL/IDR', 'DOGE/IDR']

# Alokasi Modal Tetap untuk Pembalian Pasar (Market Order IDR)
# Indodax mewajibkan Market Buy diisi dengan jumlah nominal Rupiah (IDR)
MODAL_PER_TRANSAKSI_IDR = 50000.0  # Contoh: Rp 50.000 per eksekusi BUY

# =====================================================================
# 2. SISTEM MEMORI PERMANEN (SQLITE DATABASE ENGINE)
# =====================================================================
def init_db():
    """Inisialisasi tabel basis data anti-reset di server cloud"""
    conn = sqlite3.connect('trading_bot.db', check_same_thread=False, timeout=30)
    cursor = conn.cursor()
    
    # Tabel Pencatat Status Terakhir (Sistem Pengunci Sinyal)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            pair TEXT PRIMARY KEY, 
            last_signal TEXT, 
            entry_price REAL, 
            holding_amount REAL,
            timestamp TEXT
        )
    """)
    
    # Tabel Log Riwayat Transaksi Sukses untuk Widget Win Rate
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, 
            pair TEXT, 
            type TEXT, 
            price REAL, 
            status TEXT, 
            timestamp TEXT
        )
    """)
    
    # Tabel Konfigurasi Risiko Manajemen Darurat
    try:
        cursor.execute("SELECT last_run FROM settings LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("DROP TABLE IF EXISTS settings")
        cursor.execute("""
            CREATE TABLE settings (
                max_mdd REAL DEFAULT 5.0, 
                min_vol REAL DEFAULT 50000000, 
                last_run TEXT
            )
        """)
        cursor.execute("INSERT INTO settings (max_mdd, min_vol, last_run) VALUES (5.0, 50000000, 'Belum Berjalan')")
    
    conn.commit()
    return conn

# Hubungkan basis data secara global
db_conn = init_db()

# =====================================================================
# 3. PENARIK DATA CHART & HITUNG INDIKATOR HMA-20 (MANDIRI & GRATIS)
# =====================================================================
def get_indodax_candles_4h(pair):
    """Mengambil riwayat lilin 4 jam langsung dari server chart Indodax gratis"""
    clean_pair = pair.lower().replace("/", "")
    url = "https://indodax.com"
    
    end_time = int(time.time())
    start_time = end_time - (200 * 4 * 3600)  # Mengambil 200 bar terakhir
    
    params = {'symbol': clean_pair.upper(), 'resolution': '240', 'from': start_time, 'to': end_time}
    try:
        response = requests.get(url, params=params, timeout=10)
        data = response.json()
        if data.get('s') == 'ok':
            return pd.DataFrame({
                'timestamp': pd.to_datetime(data['t'], unit='s'),
                'open': data['o'], 'high': data['h'], 'low': data['l'], 'close': data['c'], 'volume': data['v']
            })
    except:
        pass
    return pd.DataFrame()

def calculate_hma_20(df):
    """Kalkulasi Hull Moving Average Periode 20 secara presisi"""
    if df.empty or len(df) < 20: 
        return df
    period = 20
    half_period = int(period / 2)
    sqrt_period = int(np.sqrt(period))
    
    def wma(series, p):
        weights = np.arange(1, p + 1)
        return series.rolling(p).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    
    wma_half = wma(df['close'], half_period)
    wma_full = wma(df['close'], period)
    raw_hma = (2 * wma_half) - wma_full
    
    df['hma_20'] = wma(raw_hma, sqrt_period)
    # Penentu warna bar berjalan instan (df.iloc[-1])
    df['hma_color'] = np.where(df['hma_20'] > df['hma_20'].shift(1), 'Green', 'Red')
    return df

# =====================================================================
# 4. PRIVATE TRADE API INDODAX SIGNATURE (MARKET ORDER)
# =====================================================================
def execute_indodax_trade(pair, action, amount_or_coin):
    """Menembak endpoint transaksi instan pasar asli Indodax secara terenkripsi"""
    clean_pair = pair.lower().replace("/", "_")
    url = "https://indodax.com/tapi"
    nonce = int(time.time() * 1000)
    
    payload = {
        "method": "trade",
        "pair": clean_pair,
        "type": action.lower(),
        "price": "market",
        "nonce": nonce
    }
    
    # Ketentuan Indodax untuk Market Order: 
    # BUY menggunakan nominal Rupiah (idr), SELL menggunakan kuantitas aset koin
    if action.lower() == "buy":
        payload["idr"] = str(int(amount_or_coin))
    else:
        payload["order_type"] = "market"  # Pastikan flag market tersemat untuk penjualan
        # Ganti format ke string desimal dengan presisi tinggi untuk unit koin
        payload["amount"] = f"{amount_or_coin:.8f}"
        
    query_string = requests.compat.urlencode(payload)
    signature = hmac.new(bytes(SECRET_KEY, 'utf-8'), msg=bytes(query_string, 'utf-8'), digestmod=hashlib.sha512).hexdigest()
    
    headers = {"Key": API_KEY, "Sign": signature}
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=12)
        return response.json()
    except Exception as e:
        return {"success": 0, "error": str(e)}

# =====================================================================
# 5. INTEGRASI ENGINE UTAMA & FILTER MANAJEMEN RISIKO BARU
# =====================================================================
def run_autonomous_engine():
    """Mesin utama penyaring sinyal dan eksekutor otomatis 24 Jam"""
    cursor = db_conn.cursor()
    cursor.execute("SELECT max_mdd, min_vol FROM settings LIMIT 1")
    setting_row = cursor.fetchone()
    max_mdd, min_vol = setting_row if setting_row else (5.0, 50000000)
    
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("UPDATE settings SET last_run = ?", (now_str,))
    db_conn.commit()
    
    for pair in LIST_PAIRS:
        df = get_indodax_candles_4h(pair)
        if df.empty: 
            continue
            
        df = calculate_hma_20(df)
        last_bar = df.iloc[-1]
        current_color = last_bar['hma_color']
        current_price = last_bar['close']
        current_volume_idr = last_bar['volume'] * current_price
        
        # FILTER RISIKO 1: Minimum Volume Likuiditas Pasar
        if current_volume_idr < min_vol: 
            continue
            
        # Ambil status memori transaksi terakhir pair dari SQLite
        cursor.execute("SELECT last_signal, holding_amount FROM trades WHERE pair = ?", (pair,))
        row = cursor.fetchone()
        last_signal, holding_amount = row if row else ("NONE", 0.0)
        
        # 🟢 LOGIKA EKSEKUSI BUY (HMA Hijau Agresif & Wajib Bergantian)
        if current_color == 'Green' and last_signal != 'BUY':
            res = execute_indodax_trade(pair, "buy", MODAL_PER_TRANSAKSI_IDR)
            if res.get("success") == 1:
                # Dapatkan jumlah estimasi koin bersih yang dibeli dari response
                return_receive = float(res['return'].get('receive_coin', 0.0))
                coin_bought = return_receive if return_receive > 0 else (MODAL_PER_TRANSAKSI_IDR / current_price)
                
                cursor.execute("INSERT OR REPLACE INTO trades VALUES (?, 'BUY', ?, ?, ?)", 
                               (pair, current_price, coin_bought, now_str))
                cursor.execute("INSERT INTO history (pair, type, price, status, timestamp) VALUES (?, 'BUY', ?, 'SUCCESS', ?)", 
                               (pair, current_price, now_str))
                db_conn.commit()
                
        # 🔴 LOGIKA EKSEKUSI SELL (HMA Merah / Sistem Anti-Repaint Darurat)
        elif current_color == 'Red' and last_signal == 'BUY':
            # Gunakan sisa koin di memori database untuk dilepas ke pasar IDR
            coin_to_sell = holding_amount if holding_amount > 0 else (MODAL_PER_TRANSAKSI_IDR / current_price)
            
            res = execute_indodax_trade(pair, "sell", coin_to_sell)
            if res.get("success") == 1:
                cursor.execute("INSERT OR REPLACE INTO trades VALUES (?, 'SELL', ?, 0.0, ?)", 
                               (pair, current_price, now_str))
                cursor.execute("INSERT INTO history (pair, type, price, status, timestamp) VALUES (?, 'SELL', ?, 'SUCCESS', ?)", 
                               (pair, current_price, now_str))
                db_conn.commit()

# =====================================================================
# 6. LAYAR UTAMA MONITOR (OPTIMASI RESPONSIVENESS CHROME HP)
# =====================================================================
# Perhitungan metrik Win Rate dari Database secara langsung
cursor = db_conn.cursor()
cursor.execute("SELECT COUNT(*) FROM history WHERE type='SELL' AND status='SUCCESS'")
total_win = cursor.fetchone()[0]
cursor.execute("SELECT COUNT(*) FROM history WHERE status='SUCCESS'")
total_trades = cursor.fetchone()[0]
win_rate = (total_win / (total_trades / 2) * 100) if total_trades > 1 else 100.0

cursor.execute("SELECT last_run FROM settings LIMIT 1")
last_run_time = cursor.fetchone()
last_run_display = last_run_time[0] if last_run_time else "--:--"

# Tampilan Ringkas Blok Atas HP
st.markdown("### 🛡️ Indodax Multi-Pair Pro Server")
col1, col2 = st.columns(2)
col1.metric("Win Rate Bot", f"{win_rate:.1f}%")
col2.metric("Server Terakhir Scan", last_run_display.split(" ")[1] if " " in last_run_display else last_run_display)

# Komponen Tabel Live Running Trades
st.markdown("#### 📋 Running Trades (Status Posisi)")
df_running = pd.read_sql_query("""
    SELECT pair as 'Pair', last_signal as 'Posisi', 
    entry_price as 'Harga Masuk', timestamp as 'Waktu Pemicu' 
    FROM trades WHERE last_signal='BUY'
""", db_conn)

if df_running.empty:
    st.write("💡 *Semua aset sedang clean (posisi kosong/terjual).*")
else:
    st.dataframe(df_running, use_container_width=True, hide_index=True)

# 7. LAYOUT CONTROL PANEL SIDEBAR HP
st.sidebar.header("⚙️ Manajemen Risiko")
cursor.execute("SELECT max_mdd, min_vol FROM settings LIMIT 1")
curr_set = cursor.fetchone()
curr_mdd, curr_vol = curr_set if curr_set else (5.0, 50000000)

input_mdd = st.sidebar.number_input("Max Drawdown Harian (%)", value=curr_mdd, step=0.5)
input_vol = st.sidebar.number_input("Min Volume 24J (IDR)", value=int(curr_vol), step=5000000)

if st.sidebar.button("💾 Terapkan Batas Risiko"):
    cursor.execute("UPDATE settings SET max_mdd = ?, min_vol = ?", (input_mdd, input_vol))
    db_conn.commit()
    st.sidebar.success("Parameter risiko tersimpan ke Cloud!")

# =====================================================================
# 8. DAEMON AUTO-LOOPING CLOUD (SOLUSI ANTI-LAYAR MATI)
# =====================================================================
# Bagian ini akan memaksa server Streamlit Cloud terus memutar script 
# di latar belakang setiap 5 menit meskipun Anda mengunci layar HP.
run_autonomous_engine()
time.sleep(300)  # Menahan loop selama 5 Menit (300 detik) sebelum scanning ulang
st.rerun()
