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
# 1. KONFIGURASI UTAMA LAYAR HP CHROME
# ==========================================
st.set_page_config(layout="centered", page_title="Indodax Real Bot Pro", page_icon="💰")

DB_NAME = 'trading_bot.db'

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, pair TEXT, tipe TEXT, 
            harga REAL, jumlah REAL, pemicu TEXT, profit_idr REAL, profit_persen REAL
        )
    ''')
    cursor.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, val TEXT)')
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT val FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row if row else default
    except:
        return default
    finally:
        conn.close()

def set_setting(key, val):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT OR REPLACE INTO settings (key, val) VALUES (?, ?)", (key, str(val)))
        conn.commit()
    except:
        pass
    finally:
        conn.close()

init_db()

# ==========================================
# 2. SISTEM OTOMATIS MEMBACA KUNCI SECRETS REAL
# ==========================================
try:
    api_key_input = st.secrets["INDODAX_API_KEY"]
    secret_key_input = st.secrets["INDODAX_SECRET_KEY"]
    default_modal = int(st.secrets["DEFAULT_MODAL_BELANJA"])
    default_sl = float(st.secrets["DEFAULT_STOP_LOSS"])
    bot_is_authenticated = True
except Exception:
    api_key_input = ""
    secret_key_input = ""
    default_modal = 100000
    default_sl = 2.0
    bot_is_authenticated = False

# ==========================================
# 3. DATA PASAR ASLI INDODAX TERBARU (BYPASS BY IP2)
# ==========================================
@st.cache_data(ttl=15)
def fetch_live_indodax_data(pair):
    """Mengambil data Candlestick 4 Jam ASLI langsung dari API Publik Indodax Terbaru"""
    pair_id = pair.replace('/', '_').lower()
    
    # PERBAIKAN UTAMA: Menggunakan jalur api2 resmi untuk bypass rate-limit / cloudflare server AWS
    url = f"https://indodax.com{pair_id}&tf=4h"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36',
        'Accept': 'application/json'
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()
        if not data or not isinstance(data, list):
            return pd.DataFrame()
            
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        df.dropna(subset=['close'], inplace=True)
        return df
    except:
        return pd.DataFrame()

# ==========================================
# 4. ENGINE EKSEKUSI API PRIVATE INDODAX (LIVE REAL)
# ==========================================
def ambil_saldo_indodax(api_key, secret_key, pair):
    url_tapi = "https://indodax.com"
    nonce = int(time.time() * 1000) + 2000
    payload = {'method': 'getInfo', 'nonce': nonce}
    
    parts = pair.split('/')
    coin_code = parts[0].lower() if len(parts) > 0 else "btc"
    
    try:
        query_string = urlencode(payload)
        signature = hmac.new(bytes(secret_key, 'utf-8'), msg=bytes(query_string, 'utf-8'), digestmod=hashlib.sha512).hexdigest()
        headers = {'Key': api_key, 'Sign': signature, 'Content-Type': 'application/x-www-form-urlencoded'}
        
        response = requests.post(url_tapi, data=payload, headers=headers, timeout=10)
        hasil_json = response.json()
        
        if hasil_json.get('success') == 1:
            balances = hasil_json['return']['balance']
            return {"success": True, "idr": float(balances.get('idr', 0.0)), "coin": float(balances.get(coin_code, 0.0)), "coin_symbol": coin_code.upper()}
        return {"success": False, "error": hasil_json.get('error', 'Ditolak Server')}
    except Exception as e:
        return {"success": False, "error": str(e)}

def kirim_order_indodax(api_key, secret_key, pair, tipe_aksi, nominal_idr=None, jumlah_coin=None):
    pair_id = pair.replace('/', '_').lower()
    url_tapi = "https://indodax.com"
    nonce = int(time.time() * 1000) + 2000
    payload = {'method': 'trade', 'pair': pair_id, 'nonce': nonce}
    if tipe_aksi.upper() == "BUY":
        payload.update({'type': 'buy', 'order_type': 'market', 'idr': int(nominal_idr)})
    elif tipe_aksi.upper() == "SELL":
        payload.update({'type': 'sell', 'order_type': 'market', 'coin': float(jumlah_coin if jumlah_coin else 0.0)})
    try:
        query_string = urlencode(payload)
        signature = hmac.new(bytes(secret_key, 'utf-8'), msg=bytes(query_string, 'utf-8'), digestmod=hashlib.sha512).hexdigest()
        headers = {'Key': api_key, 'Sign': signature, 'Content-Type': 'application/x-www-form-urlencoded'}
        response = requests.post(url_tapi, data=payload, headers=headers, timeout=10)
        return response.json()
    except Exception as e:
        return {"success": 0, "error": str(e)}

# ==========================================
# 5. SIDEBAR UTAMA & PARAMETER REAL
# ==========================================
st.sidebar.header("⚙️ STATUS KUNCI BURSA")

if bot_is_authenticated:
    st.sidebar.success("🟢 REAL ACCOUNT ACTIVE")
else:
    st.sidebar.error("🔴 API KEY TERPUTUS (Cek Secrets)")

st.sidebar.markdown("---")
st.sidebar.header("📊 SETTING TRANSAKSI")

order_size_idr = st.sidebar.number_input("💰 Modal Beli per Trade (IDR)", min_value=10000, value=default_modal, step=10000)
sl_input = st.sidebar.number_input("Stop Loss Fisik (%)", min_value=0.5, max_value=10.0, value=default_sl, step=0.1)

hma_period = 20

# ==========================================
# 6. ENGINE STRATEGI HMA (UNIVERSAL)
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
# 7. CORE LOGIKA TRADING REAL AGRESIF INSTAN
# ==========================================
def jalankan_engine_bot(pair, df):
    if df.empty:
        return df, "Menghubungkan Server Indodax...", 0.0
    df = hitung_hma_dinamis(df, hma_period)
    
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
    notif_pesan = "Menganalisis Pergerakan..."
    
    if bot_is_authenticated:
        if posisi_aktif == "TRUE":
            if harga_sekarang > highest_price:
                highest_price = harga_sekarang
                set_setting(f"highest_price_{pair}", highest_price)
                
            persen_turun_dari_puncak = ((highest_price - harga_sekarang) / highest_price) * 100
            sudah_untung = harga_sekarang > (harga_masuk * 1.01)
            
            if sudah_untung and persen_turun_dari_puncak >= 0.5:
                pemicu_aksi = "SELL"
                notif_pesan = "🎯 TRAILING TAKE PROFIT (TTP 0.5% Terkunci)"
            elif harga_sekarang <= harga_masuk * (1 - (sl_input / 100)):
                pemicu_aksi = "SELL"
                notif_pesan = f"⚠️ STOP LOSS FISIK ({sl_input}%) TERJANGKAU"
            elif warna_sekarang == "MERAH":
                pemicu_aksi = "SELL"
                notif_pesan = "🚨 ANTI-REPAINT CUT-LOSS (CLOSED_BY_SIGNAL_DISAPPEARED)"
        else:
            if warna_sekarang == "HIJAU" and warna_sebelumnya == "MERAH" and last_signal == "SELL":
                pemicu_aksi = "BUY"
                notif_pesan = "🚀 SINYAL BUY AGRESIF INSTAN VALID"

        if pemicu_aksi:
            api_success = True
            
            if pemicu_aksi == "BUY":
                res_api = kirim_order_indodax(api_key_input, secret_key_input, pair, "BUY", nominal_idr=order_size_idr)
            else:
                res_api = kirim_order_indodax(api_key_input, secret_key_input, pair, "SELL", jumlah_coin=0.0)
            
            if res_api.get('success') != 1:
                api_success = False
                notif_pesan += f" | ❌ API Error: {res_api.get('error')}"
            
            if api_success:
                conn = sqlite3.connect(DB_NAME)
                cursor = conn.cursor()
                ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if pemicu_aksi == "BUY":
                    cursor.execute("INSERT INTO trades (timestamp, pair, tipe, harga, jumlah, pemicu, profit_idr, profit_persen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (ts, pair, "BUY", harga_sekarang, 1.0, notif_pesan, 0.0, 0.0))
                    set_setting(f"last_signal_{pair}", "BUY")
                    set_setting(f"posisi_aktif_{pair}", "TRUE")
                    set_setting(f"harga_masuk_{pair}", harga_sekarang)
                    set_setting(f"highest_price_{pair}", harga_sekarang)
                elif pemicu_aksi == "SELL":
                    profit_idr = (harga_sekarang - harga_masuk) * 1.0
                    profit_persen = ((harga_sekarang - harga_masuk) / harga_masuk) * 100
                    cursor.execute("INSERT INTO trades (timestamp, pair, tipe, harga, jumlah, pemicu, profit_idr, profit_persen) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (ts, pair, "SELL", harga_sekarang, 1.0, notif_pesan, profit_idr, profit_persen))
                    set_setting(f"last_signal_{pair}", "SELL")
                    set_setting(f"posisi_aktif_{pair}", "FALSE")
                    set_setting(f"harga_masuk_{pair}", 0.0)
                    set_setting(f"highest_price_{pair}", 0.0)
                conn.commit()
                conn.close()
                st.toast(f"{pair}: {notif_pesan}", icon="📈")
                
    return df, notif_pesan, harga_sekarang

# ==========================================
# 8. TAMPILAN DOMPET & MONITORING NYATA HP
# ==========================================
conn = sqlite3.connect(DB_NAME)
try:
    df_trades = pd.read_sql_query("SELECT * FROM trades WHERE tipe='SELL'", conn)
except:
    df_trades = pd.DataFrame()
conn.close()

total_trades = len(df_trades)
win_rate = (len(df_trades[df_trades['profit_idr'] > 0]) / total_trades) * 100 if total_trades > 0 else 0.0
total_net_profit = df_trades['profit_idr'].sum() if total_trades > 0 else 0.0

daftar_pair = ['BTC/IDR', 'ETH/IDR', 'USDT/IDR', 'SOL/IDR', 'DOGE/IDR']
selected_pair = st.selectbox("🎯 Pilih Monitor Grafik Pair:", daftar_pair)

saldo_idr_tampil = 0.0
saldo_coin_tampil = 0.0
coin_label = selected_pair.split('/')[0]

if bot_is_authenticated:
    data_dompet = ambil_saldo_indodax(api_key_input, secret_key_input, pair=selected_pair)
    if data_dompet.get("success"):
        saldo_idr_tampil = data_dompet["idr"]
        saldo_coin_tampil = data_dompet["coin"]
        coin_label = data_dompet["coin_symbol"]

col1, col2, col3 = st.columns(3)
col1.metric("Win Rate", f"{win_rate:.1f}%", f"{total_trades} Trades")
col2.metric("Wallet IDR Asli", f"Rp {saldo_idr_tampil:,.0f}")
col3.metric(f"Wallet Real {coin_label}", f"{saldo_coin_tampil:.8f}")

df_market = fetch_live_indodax_data(selected_pair)
df_hasil, status_bot, live_price = jalankan_engine_bot(selected_pair, df_market)

if bot_is_authenticated:
    st.success(f"📈 **Harga Live {selected_pair}:** Rp {live_price:,.2f} | {status_bot}")
else:
    st.error("🛑 MASALAH KEAMANAN: Masukkan API Key dan Secret Key asli Anda di menu Secrets Streamlit Cloud.")

# ==========================================
# 9. GRAFIK PLOTLY REAL-TIME & TABEL JURNAL
# ==========================================
if not df_hasil.empty and 'hma_val' in df_hasil.columns:
    fig = go.Figure()
    fig.add_trace(go.Candlestick(x=df_hasil.index, open=df_hasil['open'], high=df_hasil['high'], low=df_hasil['low'], close=df_hasil['close'], name="Candle"))
    fig.add_trace(go.Scatter(x=df_hasil.index, y=df_hasil['hma_val'], line=dict(color='cyan', width=2), name="HMA 20"))
    fig.update_layout(margin=dict(l=10, r=10, t=10, b=10), xaxis_rangeslider_visible=False, height=350, paper_bgcolor='#111111', plot_bgcolor='#111111', font=dict(color='white'))
    st.plotly_chart(fig, use_container_width=True)

st.subheader("📋 Catatan Log Jurnal Trading Nyata (SQLite)")
conn = sqlite3.connect(DB_NAME)
try:
    df_all_logs = pd.read_sql_query("SELECT timestamp, pair, tipe, harga, pemicu, profit_persen FROM trades ORDER BY id DESC LIMIT 5", conn)
except:
    df_all_logs = pd.DataFrame()
conn.close()

if not df_all_logs.empty:
    st.dataframe(df_all_logs, use_container_width=True)
else:
    st.caption("Belum ada riwayat transaksi akun real terdeteksi di database lokal.")
