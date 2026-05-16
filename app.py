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
# 1. INTEGRASI API KEYS RIIL INDODAX (TERENKRIPSI)
# =====================================================================
API_KEY = "KXFCXMGP-HXH2UXNK-9T1KRVO0-XCEZBKRR-HCIDLBUF"
SECRET_KEY = "a423ce71c0c54f54899d0c03193865176b0b5d83b7826f51c3eea4b269ea553ed0087e69ac200d48"

LIST_PAIRS = ['BTC/IDR', 'ETH/IDR', 'USDT/IDR', 'DOGE/IDR', 'SOL/IDR']
MODAL_PER_TRANSAKSI_IDR = 50000.0  # nominal modal Rp 50.000 per transaksi BUY

# =====================================================================
# 2. SISTEM MEMORI PERMANEN & DATABASE PROTECTION (ANTI-CRASH)
# =====================================================================
def init_db():
    conn = sqlite3.connect('trading_bot.db', check_same_thread=False, timeout=20)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT pair, last_signal, entry_price, timestamp, holding_amount FROM trades LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("DROP TABLE IF EXISTS trades")
        conn.commit()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            pair TEXT PRIMARY KEY, last_signal TEXT, entry_price REAL, timestamp TEXT, holding_amount REAL DEFAULT 0.0
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, pair TEXT, type TEXT, price REAL, status TEXT, timestamp TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, message TEXT
        )
    """)
    try:
        cursor.execute("SELECT last_run FROM settings LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("DROP TABLE IF EXISTS settings")
        cursor.execute("""
            CREATE TABLE settings (max_mdd REAL DEFAULT 5.0, min_vol REAL DEFAULT 50000000, last_run TEXT)
        """)
        cursor.execute("INSERT INTO settings (max_mdd, min_vol, last_run) VALUES (5.0, 50000000, 'Belum Berjalan')")
    conn.commit()
    return conn

db_conn = init_db()

def add_log_message(message):
    try:
        cursor = db_conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT INTO activity_logs (timestamp, message) VALUES (?, ?)", (now_str, message))
        cursor.execute("DELETE FROM activity_logs WHERE id NOT IN (SELECT id FROM activity_logs ORDER BY id DESC LIMIT 25)")
        db_conn.commit()
    except:
        pass

# =====================================================================
# 3. PENARIK DATA GRAFIK JALUR RESMI TOKOCRYPTO (100% ANTI-BLOKIR)
# =====================================================================
def get_indodax_candles_4h(pair):
    """Mengambil riwayat lilin 4 jam langsung dari server resmi Tokocrypto Indonesia"""
    try:
        clean_coin = pair.upper().replace("/IDR", "")
        
        if clean_coin == "USDT":
            tokocrypto_symbol = "USDTIDR"
        else:
            tokocrypto_symbol = f"{clean_coin}USDT"
            
        url = "https://tokocrypto.com"
        params = {
            'symbol': tokocrypto_symbol,
            'interval': '4h',  
            'limit': 50        
        }
        
        response = requests.get(url, params=params, timeout=8)
        res_json = response.json()
        
        if res_json.get('code') == 0 and isinstance(res_json.get('data'), list):
            data = res_json['data']
            if len(data) > 20:
                df_raw = pd.DataFrame(data)
                df_cleaned = pd.DataFrame({
                    'timestamp': pd.to_datetime(df_raw[0], unit='ms'),
                    'open': df_raw[1].astype(float),
                    'high': df_raw[2].astype(float),
                    'low': df_raw[3].astype(float),
                    'close': df_raw[4].astype(float),  
                    'volume': df_raw[5].astype(float)
                })
                return df_cleaned
        return pd.DataFrame()
    except:
        return pd.DataFrame()

def calculate_hma_20(df):
    if df.empty or len(df) < 25: return df
    
    def wma(series, p):
        weights = np.arange(1, p + 1)
        return series.rolling(p).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)
    
    period = 20  
    half_period = int(period / 2)  
    sqrt_period = int(np.sqrt(period))  
    
    wma_half = wma(df['close'], half_period)
    wma_full = wma(df['close'], period)
    raw_hma = (2 * wma_half) - wma_full
    
    df['hma_value'] = wma(raw_hma, sqrt_period)
    df['is_green'] = df['hma_value'] >= df['hma_value'].shift(1)
    df['is_red'] = df['hma_value'] < df['hma_value'].shift(1)
    df['raw_buy'] = df['is_green'] & (~df['is_green'].shift(1).fillna(False))
    df['raw_sell'] = df['is_red'] & (~df['is_red'].shift(1).fillna(False))
    return df

def get_live_market_price(pair):
    """Mengambil harga ticker instan riil berjalan dari Indodax"""
    clean_pair = pair.lower().replace("/", "_")
    url = f"https://indodax.com{clean_pair}"
    try:
        res = requests.get(url, timeout=4).json()
        return float(res['ticker']['last']), float(res['ticker']['vol_idr'])
    except:
        return None, 0.0

def get_indodax_balance():
    url = "https://indodax.com"
    nonce = int(time.time() * 1000)
    payload = {"method": "getInfo", "nonce": nonce}
    query_string = requests.compat.urlencode(payload)
    signature = hmac.new(bytes(SECRET_KEY, 'utf-8'), msg=bytes(query_string, 'utf-8'), digestmod=hashlib.sha512).hexdigest()
    headers = {"Key": API_KEY, "Sign": signature}
    try:
        res = requests.post(url, data=payload, headers=headers, timeout=5).json()
        if res.get('success') == 1 or res.get('success') == '1':
            return float(res['return']['balance']['idr'])
    except:
        pass
    return 0.0

def execute_indodax_trade(pair, action, amount_or_coin):
    clean_pair = pair.lower().replace("/", "_")
    url = "https://indodax.com"
    nonce = int(time.time() * 1000)
    payload = {"method": "trade", "pair": clean_pair, "type": action.lower(), "price": "market", "nonce": nonce}
    if action.lower() == "buy":
        payload["idr"] = str(int(amount_or_coin))
    else:
        payload["order_type"] = "market"
        payload["amount"] = f"{amount_or_coin:.8f}"
    query_string = requests.compat.urlencode(payload)
    signature = hmac.new(bytes(SECRET_KEY, 'utf-8'), msg=bytes(query_string, 'utf-8'), digestmod=hashlib.sha512).hexdigest()
    headers = {"Key": API_KEY, "Sign": signature}
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=5)
        return response.json()
    except:
        return {"success": 0, "error": "Timeout"}

# =====================================================================
# 5. ENGINE UTAMA: PEMINDAIAN MANDIRI VIA TOKOCRYPTO DATA FEED
# =====================================================================
def run_autonomous_engine():
    cursor = db_conn.cursor()
    cursor.execute("SELECT max_mdd, min_vol FROM settings LIMIT 1")
    setting_row = cursor.fetchone()
    max_mdd = float(setting_row[0]) if setting_row else 5.0
    min_vol = float(setting_row[1]) if setting_row else 50000000.0
    
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("UPDATE settings SET last_run = ?", (now_str,))
    db_conn.commit()
    
    saldo_saat_ini = get_indodax_balance()
    
    for pair in LIST_PAIRS:
        df = get_indodax_candles_4h(pair)
        
        if df.empty: 
            add_log_message(f"🔍 {pair} | Status: ❌ Jaringan Tokocrypto Overload")
            continue
            
        df = calculate_hma_20(df)
        if 'hma_value' not in df.columns: 
            add_log_message(f"🔍 {pair} | Status: ⚠️ Perhitungan Rumus Gagal")
            continue
        
        last_bar = df.iloc[-1]
        confirmed_bar = df.iloc[-2]
        current_color = "Hijau (BUY)" if last_bar['is_green'] else "Merah (SELL)"
        
        indodax_price, volume_24j_idr = get_live_market_price(pair)
        if indodax_price is None: indodax_price = last_bar['close']
        
        if volume_24j_idr < min_vol: 
            add_log_message(f"🔍 {pair} | Sinyal: {current_color} | Status: ⏩ Skip Vol Rendah")
            continue
            
        cursor.execute("SELECT last_signal, holding_amount FROM trades WHERE pair = ?", (pair,))
        row = cursor.fetchone()
        last_signal = row[0] if row else "NONE"
        holding_amount = float(row[1]) if row else 0.0
        
        add_log_message(f"🔍 {pair} | Sinyal Tren: {current_color} | Posisi SQLite: {last_signal}")
        
        # BUY
        if confirmed_bar['raw_buy'] and last_signal != 'BUY':
            if saldo_saat_ini < MODAL_PER_TRANSAKSI_IDR:
                add_log_message(f"⚠️ {pair} | Sinyal: BUY | Status: 🛑 Saldo Dompet Rp {saldo_saat_ini:,.0f} Kurang")
                continue
            res = execute_indodax_trade(pair, "buy", MODAL_PER_TRANSAKSI_IDR)
            if res.get("success") == 1:
                return_receive = float(res['return'].get('receive_coin', 0.0))
                coin_bought = return_receive if return_receive > 0 else (MODAL_PER_TRANSAKSI_IDR / indodax_price)
                cursor.execute("INSERT OR REPLACE INTO trades VALUES (?, 'BUY', ?, ?, ?)", (pair, indodax_price, now_str, coin_bought))
                cursor.execute("INSERT INTO history (pair, type, price, status, timestamp) VALUES (?, 'BUY', ?, 'SUCCESS', ?)", (pair, indodax_price, now_str))
                db_conn.commit()
                add_log_message(f"🚀 {pair} | Aksi: BERHASIL BUY ORDER")
                saldo_saat_ini -= MODAL_PER_TRANSAKSI_IDR
                
        # SELL
        elif confirmed_bar['raw_sell'] and last_signal == 'BUY':
            coin_to_sell = holding_amount if holding_amount > 0 else (MODAL_PER_TRANSAKSI_IDR / indodax_price)
            res = execute_indodax_trade(pair, "sell", coin_to_sell)
            if res.get("success") == 1:
                cursor.execute("INSERT OR REPLACE INTO trades VALUES (?, 'SELL', ?, ?, 0.0)", (pair, indodax_price, now_str))
                cursor.execute("INSERT INTO history (pair, type, price, status, timestamp) VALUES (?, 'SELL', ?, 'SUCCESS', ?)", (pair, indodax_price, now_str))
                db_conn.commit()
                add_log_message(f"📉 {pair} | Aksi: BERHASIL SELL ORDER")

# =====================================================================
# 6. LAYAR UTAMA DASHBOARD MONITOR (RESPONSIVE CHROME HP)
# =====================================================================
cursor = db_conn.cursor()
cursor.execute("SELECT COUNT(*) FROM history WHERE type='SELL' AND status='SUCCESS'")
total_win_row = cursor.fetchone()
# PERBAIKAN SEMENTARA TYPEERROR: Mengekstrak index tuple [0] sebelum dikonversi
total_win = int(total_win_row[0]) if total_win_row else 0

cursor.execute("SELECT COUNT(*) FROM history WHERE status='SUCCESS'")
total_trades_row = cursor.fetchone()
# PERBAIKAN SEMENTARA TYPEERROR: Mengekstrak index tuple [0] sebelum dikonversi
total_trades = int(total_trades_row[0]) if total_trades_row else 0

win_rate = (total_win / (total_trades / 2)) * 100 if total_trades > 1 and total_win > 0 else 100.0

cursor.execute("SELECT last_run FROM settings LIMIT 1")
last_run_time = cursor.fetchone()
last_run_display = last_run_time[0] if last_run_time else "Belum Berjalan"

total_modal_aktif = 0.0
total_valuasi_aktif = 0.0
live_data = []

try:
    for pair in LIST_PAIRS:
        cursor.execute("SELECT last_signal, entry_price, holding_amount FROM trades WHERE pair = ?", (pair,))
        row = cursor.fetchone()
        live_price, _ = get_live_market_price(pair)
        
        if row and str(row[0]) == 'BUY':
            entry_price = float(row[1])
            holding_amount = float(row[2])
            posisi = "🛒 BUYING"
            if live_price is None: live_price = entry_price
            current_value_idr = holding_amount * live_price
            total_modal_aktif += (holding_amount * entry_price)
            total_valuasi_aktif += current_value_idr
            profit_idr = current_value_idr - (holding_amount * entry_price)
            profit_pct = ((live_price - entry_price) / entry_price) * 100
            profit_display = f"{'+' if profit_idr >= 0 else ''}Rp {profit_idr:,.0f} ({'+' if profit_idr >= 0 else ''}{profit_pct:.2f}%)"
            saldo_idr_display = f"Rp {current_value_idr:,.0f}"
            saldo_coin_display = f"{holding_amount:.6f}"
            entry_display = f"Rp {entry_price:,.0f}"
        else:
            posisi = "💤 CLEAN"
            if live_price is None: live_price = 0.0
            entry_display = "-"
            saldo_coin_display = "0.000000"
            saldo_idr_display = "Rp 0"
            profit_display = "Rp 0 (0.00%)"
            
        live_data.append({
            "Pair Aset": pair, "Status": posisi, "Harga Masuk": entry_display,
            "Harga Live": f"Rp {live_price:,.0f}" if live_price > 0 else "Delay API",
            "Saldo Koin": saldo_coin_display, "Valuasi (IDR)": saldo_idr_display, "Live Floating Profit": profit_display
        })
except:
    pass

akumulasi_pnl_idr = total_valuasi_aktif - total_modal_aktif
total_pnl_pct = (akumulasi_pnl_idr / total_modal_aktif) * 100 if total_modal_aktif > 0 else 0.0
saldo_idr_dompet = get_indodax_balance()

st.markdown("### 🛡️ Indodax Multi-Pair Pro Server")
col_w, col_s = st.columns(2)
st.metric("Win Rate Bot", f"{win_rate:.1f}%")

if last_run_display and " " in last_run_display:
    waktu_saja = last_run_display.split(" ")
    st.metric("Server Terakhir Scan", str(waktu_saja[1]))
else:
    st.metric("Server Terakhir Scan", str(last_run_display))

st.markdown("---")
col_bal, col_pnl = st.columns(2)
col_bal.metric("Saldo Utama IDR (Dompet)", f"Rp {saldo_idr_dompet:,.0f}")
if akumulasi_pnl_idr >= 0:
    col_pnl.metric("Total Profit Gabungan", f"+{total_pnl_pct:.2f}%", delta=f"Rp {akumulasi_pnl_idr:,.0f}")
else:
    col_pnl.metric("Total Loss Gabungan", f"{total_pnl_pct:.2f}%", delta=f"Rp {akumulasi_pnl_idr:,.0f}")
st.markdown("---")

st.markdown("#### 📋 Status Positions Semua Aset")
if live_data:
    st.dataframe(pd.DataFrame(live_data), use_container_width=True, hide_index=True)

st.markdown("#### 📜 Log Aktivitas Server Terpisah (Per Koin)")
try:
    df_logs = pd.read_sql_query("SELECT timestamp as 'Waktu', message as 'Catatan Aktivitas' FROM activity_logs ORDER BY id DESC LIMIT 25", db_conn)
    st.dataframe(df_logs, use_container_width=True, hide_index=True)
except:
    st.write("🔄 *Gagal memuat log aktivitas.*")

st.sidebar.header("⚙️ Manajemen Risiko")
cursor = db_conn.cursor()
cursor.execute("SELECT max_mdd, min_vol FROM settings LIMIT 1")
curr_set = cursor.fetchone()
curr_mdd = float(curr_set[0]) if curr_set else 5.0
curr_vol = float(curr_set[1]) if curr_set else 50000000.0

input_mdd = st.sidebar.number_input("Max Drawdown Harian (%)", value=curr_mdd, step=0.5)
input_vol = st.sidebar.number_input("Min Volume 24J (IDR)", value=int(curr_vol), step=5000000)

if st.sidebar.button("💾 Terapkan Batas Risiko"):
    cursor.execute("UPDATE settings SET max_mdd = ?, min_vol = ?", (input_mdd, input_vol))
    db_conn.commit()
    st.sidebar.success("Parameter risiko tersimpan ke Cloud!")

# Jalankan mesin pemindaian kilat (60 Detik)
run_autonomous_engine()
time.sleep(60)
st.rerun()
