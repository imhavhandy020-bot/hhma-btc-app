import time
import sqlite3
import pandas as pd
import numpy as np
import ccxt
from datetime import datetime
import sys

# ==========================================
# 1. KONFIGURASI API INDODAX & PARAMETER
# ==========================================
API_KEY = 'ISI_API_KEY_ANDA_DISINI'
SECRET_KEY = 'ISI_SECRET_KEY_ANDA_DISINI'
SYMBOL = 'BTC/IDR'       
TIMEFRAME = '1d'         
HMA_LENGTH = 2           
REFRESH_INTERVAL = 5     # Dibuat 5 detik agar cepat terlihat di HP

TAKE_PROFIT_PCT = 0.05   
STOP_LOSS_PCT = 0.02     

# Inisialisasi API Indodax
exchange = ccxt.indodax({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True
})

# ==========================================
# 2. MANAJEMEN DATABASE
# ==========================================
def init_db():
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT,
            signal_type TEXT,
            price REAL,
            tp_price REAL,
            sl_price REAL,
            status TEXT
        )
    ''')
    conn.commit()
    conn.close()

def save_trade(signal_type, price, tp_price, sl_price):
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (timestamp, signal_type, price, tp_price, sl_price, status)
        VALUES (datetime('now'), ?, ?, ?, ?, 'OPEN')
    ''', (signal_type, price, tp_price, sl_price))
    conn.commit()
    conn.close()
    print(f"[{datetime.now().strftime('%H:%M:%S')}] ---> DATA TERSIMPAN DI DATABASE!", flush=True)

# ==========================================
# 3. RUMUS INDIKATOR HMA
# ==========================================
def wma(series, length):
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def calculate_hma(df, length):
    half_length = int(length / 2)
    sqrt_length = int(np.sqrt(length))
    wma_half = wma(df['close'], half_length)
    wma_full = wma(df['close'], length)
    raw_hma = (2 * wma_half) - wma_full
    df['hma'] = wma(raw_hma, sqrt_length)
    return df

# ==========================================
# 4. LOGIKA UTAMA BOT
# ==========================================
def run_bot():
    # flush=True memaksa teks langsung keluar di layar aplikasi HP
    print(f"[{datetime.now().strftime('%H:%M:%S')}] BOT MULAI JALAN...", flush=True)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Menghubungkan ke Indodax...", flush=True)
    last_signal = 0 
    
    while True:
        waktu_sekarang = datetime.now().strftime('%H:%M:%S')
        try:
            # Ambil data market
            bars = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = calculate_hma(df, HMA_LENGTH)
            
            if len(df) < 3:
                print(f"[{waktu_sekarang}] Data tidak cukup, mencoba lagi...", flush=True)
                time.sleep(REFRESH_INTERVAL)
                continue
                
            current_hma = df['hma'].iloc[-1]
            prev_hma = df['hma'].iloc[-2]
            prev_prev_hma = df['hma'].iloc[-3]
            current_close = df['close'].iloc[-1]
            
            is_green_now = current_hma >= prev_hma
            is_green_prev = prev_hma >= prev_prev_hma
            
            raw_buy = is_green_now and not is_green_prev
            raw_sell = not is_green_now and is_green_prev
            
            # Teks monitoring utama wajib muncul setiap detik interval
            print(f"[{waktu_sekarang}] Cek Harga {SYMBOL}: {current_close} | HMA: {current_hma:.2f}", flush=True)
            
            if raw_buy and last_signal != 1:
                tp = current_close * (1 + TAKE_PROFIT_PCT)
                sl = current_close * (1 - STOP_LOSS_PCT)
                print(f" >>> [SINYAL BUY] Harga: {current_close} | TP: {tp} | SL: {sl}", flush=True)
                save_trade('BUY', current_close, tp, sl)
                last_signal = 1
                
            elif raw_sell and last_signal != -1:
                tp = current_close * (1 - TAKE_PROFIT_PCT)
                sl = current_close * (1 + STOP_LOSS_PCT)
                print(f" >>> [SINYAL SELL] Harga: {current_close} | TP: {tp} | SL: {sl}", flush=True)
                save_trade('SELL', current_close, tp, sl)
                last_signal = -1

        except Exception as e:
            # Jika internet HP putus/error, tulisan error akan muncul di sini
            print(f"[{waktu_sekarang}] Koneksi Error: {e}", flush=True)
            
        time.sleep(REFRESH_INTERVAL)

if __name__ == '__main__':
    init_db()
    run_bot()
