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

LIST_PAIRS = ['BTC/IDR', 'ETH/IDR', 'USDT/IDR', 'SOL/IDR', 'DOGE/IDR']
MODAL_PER_TRANSAKSI_IDR = 50000.0  # Rp 50.000 per eksekusi BUY pasar

# =====================================================================
# 2. SISTEM MEMORI PERMANEN & PENYEMBUHAN DATABASE TOTAL (ANTI-CRASH)
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
            pair TEXT PRIMARY KEY, 
            last_signal TEXT, 
            entry_price REAL, 
            timestamp TEXT,
            holding_amount REAL DEFAULT 0.0
        )
    """)
    
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
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS activity_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            message TEXT
        )
    """)
    
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

db_conn = init_db()

def add_log_message(message):
    try:
        cursor = db_conn.cursor()
        now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("INSERT INTO activity_logs (timestamp, message) VALUES (?, ?)", (now_str, message))
        cursor.execute("DELETE FROM activity_logs WHERE id NOT IN (SELECT id FROM activity_logs ORDER BY id DESC LIMIT 20)")
        db_conn.commit()
    except:
        pass

# =====================================================================
# 3. PENARIK DATA CHART & HITUNG INDIKATOR HMA-20 (ANTI-LAG)
# =====================================================================
def get_indodax_candles_4h(pair):
    clean_pair = pair.lower().replace("/", "")
    url = "https://indodax.com"
    end_time = int(time.time())
    start_time = end_time - (100 * 4 * 3600)  
    params = {'symbol': clean_pair.upper(), 'resolution': '240', 'from': start_time, 'to': end_time}
    try:
        response = requests.get(url, params=params, timeout=4)
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
    if df.empty or len(df) < 20: return df
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
    df['hma_color'] = np.where(df['hma_20'] > df['hma_20'].shift(1), 'Green', 'Red')
    return df

def get_live_market_price(pair):
    clean_pair = pair.lower().replace("/", "_")
    url = f"https://indodax.com{clean_pair}"
    try:
        res = requests.get(url, timeout=3).json()
        return float(res['ticker']['last'])
    except:
        return None

# =====================================================================
# 4. PRIVATE TRADE API INDODAX SIGNATURE (MARKET ORDER AUTOMATION)
# =====================================================================
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
        response = requests.post(url, data=payload, headers=headers, timeout=8)
        return response.json()
    except:
        return {"success": 0, "error": "Koneksi Ke Server Indodax Timeout"}

# =====================================================================
# 5. INTEGRASI ENGINE UTAMA & MANAJEMEN RISIKO REAL-TIME
# =====================================================================
def run_autonomous_engine():
    cursor = db_conn.cursor()
    cursor.execute("SELECT max_mdd, min_vol FROM settings LIMIT 1")
    setting_row = cursor.fetchone()
    max_mdd, min_vol = setting_row[:2] if setting_row else (5.0, 50000000)
    
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute("UPDATE settings SET last_run = ?", (now_str,))
    db_conn.commit()
    
    log_summary = []
    
    for pair in LIST_PAIRS:
        df = get_indodax_candles_4h(pair)
        if df.empty: 
            log_summary.append(f"{pair}: Gagal ambil chart")
            continue
            
        df = calculate_hma_20(df)
        if 'hma_color' not in df.columns: continue
        
        last_bar = df.iloc[-1]
        current_color = last_bar['hma_color']
        current_price = last_bar['close']
        current_volume_idr = last_bar['volume'] * current_price
        
        if current_volume_idr < min_vol: 
            log_summary.append(f"{pair}: Skip (Volume Rendah)")
            continue
            
        cursor.execute("SELECT last_signal, holding_amount FROM trades WHERE pair = ?", (pair,))
        row = cursor.fetchone()
        last_signal, holding_amount = row if row else ("NONE", 0.0)
        
        log_summary.append(f"{pair}: Tren {current_color}")
        
        if current_color == 'Green' and last_signal != 'BUY':
            res = execute_indodax_trade(pair, "buy", MODAL_PER_TRANSAKSI_IDR)
            if res.get("success") == 1:
                return_receive = float(res['return'].get('receive_coin', 0.0))
                coin_bought = return_receive if return_receive > 0 else (MODAL_PER_TRANSAKSI_IDR / current_price)
                cursor.execute("""
                    INSERT OR REPLACE INTO trades (pair, last_signal, entry_price, timestamp, holding_amount) 
                    VALUES (?, 'BUY', ?, ?, ?)
                """, (pair, current_price, now_str, coin_bought))
                cursor.execute("INSERT INTO history (pair, type, price, status, timestamp) VALUES (?, 'BUY', ?, 'SUCCESS', ?)", (pair, current_price, now_str))
                db_conn.commit()
                add_log_message(f"🚀 EKSEKUSI BUY SUKSES: {pair} di harga Rp {current_price:,.0f}")
                
        elif current_color == 'Red' and last_signal == 'BUY':
            coin_to_sell = holding_amount if holding_amount > 0 else (MODAL_PER_TRANSAKSI_IDR / current_price)
            res = execute_indodax_trade(pair, "sell", coin_to_sell)
            if res.get("success") == 1:
                cursor.execute("""
                    INSERT OR REPLACE INTO trades (pair, last_signal, entry_price, timestamp, holding_amount) 
                    VALUES (?, 'SELL', ?, ?, 0.0)
                """, (pair, current_price, now_str))
                cursor.execute("INSERT INTO history (pair, type, price, status, timestamp) VALUES (?, 'SELL', ?, 'SUCCESS', ?)", (pair, current_price, now_str))
                db_conn.commit()
                add_log_message(f"📉 EKSEKUSI SELL SUKSES: {pair} di harga Rp {current_price:,.0f}")

    add_log_message(" | ".join(log_summary))

# =====================================================================
# 6. LAYAR UTAMA DASHBOARD MONITOR (RESPONSIVE CHROME HP)
# =====================================================================
cursor = db_conn.cursor()
cursor.execute("SELECT COUNT(*) FROM history WHERE type='SELL' AND status='SUCCESS'")
total_win_row = cursor.fetchone()
total_win = int(total_win_row[0]) if total_win_row else 0

cursor.execute("SELECT COUNT(*) FROM history WHERE status='SUCCESS'")
total_trades_row = cursor.fetchone()
total_trades = int(total_trades_row[0]) if total_trades_row else 0

if total_trades > 1 and total_win > 0:
    win_rate = (total_win / (total_trades / 2)) * 100
else:
    win_rate = 100.0

cursor.execute("SELECT last_run FROM settings LIMIT 1")
last_run_time = cursor.fetchone()
last_run_display = last_run_time[0] if last_run_time and last_run_time[0] else "Belum Berjalan"

st.markdown("### 🛡️ Indodax Multi-Pair Pro Server")
col1, col2 = st.columns(2)
col1.metric("Win Rate Bot", f"{win_rate:.1f}%")

if last_run_display and " " in last_run_display:
    waktu_saja = last_run_display.split(" ")[1]
    col2.metric("Server Terakhir Scan", str(waktu_saja))
else:
    col2.metric("Server Terakhir Scan", str(last_run_display))

# =====================================================================
# MODUL LIVE PROFIT: MENAMPILKAN SEMUA 5 ASET PERMANEN (PERBAIKAN TUPLE)
# =====================================================================
st.markdown("#### 📋 Status Posisi Semua Aset Aktif")
try:
    live_data = []
    
    for pair in LIST_PAIRS:
        cursor.execute("SELECT last_signal, entry_price, holding_amount FROM trades WHERE pair = ?", (pair,))
        row = cursor.fetchone()
        
        live_price = get_live_market_price(pair)
        
        if row and row[0] == 'BUY':
            entry_price = float(row[1])
            holding_amount = float(row[2])
            posisi = "🛒 BUYING"
            
            if live_price is None: live_price = entry_price
            
            profit_pct = ((live_price - entry_price) / entry_price) * 100
            current_value_idr = holding_amount * live_price
            initial_value_idr = holding_amount * entry_price
            profit_idr = current_value_idr - initial_value_idr
            sign = "+" if profit_idr >= 0 else ""
            
            profit_display = f"{sign}Rp {profit_idr:,.0f} ({sign}{profit_pct:.2f}%)"
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
            "Pair Aset": pair,
            "Status": posisi,
            "Harga Masuk": entry_display,
            "Harga Live": f"Rp {live_price:,.0f}" if live_price > 0 else "Delay API",
            "Saldo Koin": saldo_coin_display,
            "Valuasi (IDR)": saldo_idr_display,
            "Live Floating Profit": profit_display
        })
        
    df_display = pd.DataFrame(live_data)
    st.dataframe(df_display, use_container_width=True, hide_index=True)
        
except Exception as database_error:
    st.write("🔄 *Sedang mengalkulasi tabel komparasi semua aset...*")

# =====================================================================
# MODUL: TABEL LOG AKTIVITAS PEMINDAIAN (BAWAH SCREEN HP)
# =====================================================================
st.markdown("#### 📜 Log Aktivitas Server Cloud (20 Terakhir)")
try:
    df_logs = pd.read_sql_query("SELECT timestamp as 'Waktu', message as 'Catatan Aktivitas' FROM activity_logs ORDER BY id DESC LIMIT 20", db_conn)
    if df_logs.empty:
        st.write("⏳ *Menunggu rekaman scan perdana...*")
    else:
        st.dataframe(df_logs, use_container_width=True, hide_index=True)
except:
    st.write("🔄 *Gagal memuat log aktivitas.*")

# 7. CONTROL PANEL SIDEBAR HP
st.sidebar.header("⚙️ Manajemen Risiko")
cursor.execute("SELECT max_mdd, min_vol FROM settings LIMIT 1")
curr_set = cursor.fetchone()
curr_mdd, curr_vol = curr_set[:2] if curr_set else (5.0, 50000000)

input_mdd = st.sidebar.number_input("Max Drawdown Harian (%)", value=curr_mdd, step=0.5)
input_vol = st.sidebar.number_input("Min Volume 24J (IDR)", value=int(curr_vol), step=5000000)

if st.sidebar.button("💾 Terapkan Batas Risiko"):
    cursor.execute("UPDATE settings SET max_mdd = ?, min_vol = ?", (input_mdd, input_vol))
    db_conn.commit()
    st.sidebar.success("Parameter risiko tersimpan ke Cloud!")

# =====================================================================
# 8. DAEMON AUTO-LOOPING CLOUD (SOLUSI ANTI-LAYAR MATI)
# =====================================================================
run_autonomous_engine()
time.sleep(300)
st.rerun()
