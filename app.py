import time
import sqlite3
import pandas as pd
import numpy as np
import ccxt
from datetime import datetime

# ==========================================
# 1. KONFIGURASI API INDODAX & PARAMETER
# ==========================================
API_KEY = 'ISI_API_KEY_ANDA_DISINI'
SECRET_KEY = 'ISI_SECRET_KEY_ANDA_DISINI'
SYMBOL = 'BTC/IDR'       
TIMEFRAME = '1d'         
HMA_LENGTH = 2           
REFRESH_INTERVAL = 10    # Dipercepat ke 10 detik agar tulisan refresh cepat muncul

# Parameter Manajemen Risiko
TAKE_PROFIT_PCT = 0.05   # Target Profit (5%)
STOP_LOSS_PCT = 0.02     # Stop Loss (2%)

# Inisialisasi API Indodax via CCXT
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
    print(f"[{datetime.now().strftime('%H:%M:%S')}] DATA DISIMPAN DI DATABASE!")

# ==========================================
# 3. PERHITUNGAN RUMUS INDIKATOR HMA
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
# 4. LOGIKA EKSEKUSI TRADING
# ==========================================
def run_bot():
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Bot Dimulai. Mencoba koneksi ke Indodax...")
    last_signal = 0 
    
    while True:
        waktu_sekarang = datetime.now().strftime('%H:%M:%S')
        try:
            # Ambil data dari bursa
            bars = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = calculate_hma(df, HMA_LENGTH)
            
            if len(df) < 3:
                print(f"[{waktu_sekarang}] Data candlestick kurang, mencoba lagi...")
                time.sleep(REFRESH_INTERVAL)
                continue
                
            current_hma = df['hma'].iloc[-1]
            prev_hma = df['hma'].iloc[-2]
            prev_prev_hma = df['hma'].iloc[-3]
            current_close = df['close'].iloc[-1]
            
            # Logika Arah Kemiringan HMA
            is_green_now = current_hma >= prev_hma
            is_green_prev = prev_hma >= prev_prev_hma
            
            raw_buy = is_green_now and not is_green_prev
            raw_sell = not is_green_now and is_green_prev
            
            # TULISAN TAMPIL SETIAP REFRESH (Pindah baris baru tanpa \r)
            print(f"[{waktu_sekarang}] Refresh Data | Harga {SYMBOL}: {current_close} | HMA: {current_hma:.2f}")
            
            # Cek Sinyal BUY
            if raw_buy and last_signal != 1:
                tp = current_close * (1 + TAKE_PROFIT_PCT)
                sl = current_close * (1 - STOP_LOSS_PCT)
                print(f" >>> [SINYAL BUY] Harga: {current_close} | Target Profit: {tp} | Stop Loss: {sl}")
                save_trade('BUY', current_close, tp, sl)
                last_signal = 1
                
            # Cek Sinyal SELL
            elif raw_sell and last_signal != -1:
                tp = current_close * (1 - TAKE_PROFIT_PCT)
                sl = current_close * (1 + STOP_LOSS_PCT)
                print(f" >>> [SINYAL SELL] Harga: {current_close} | Target Profit: {tp} | Stop Loss: {sl}")
                save_trade('SELL', current_close, tp, sl)
                last_signal = -1

        except Exception as e:
            print(f"[{waktu_sekarang}] Error: {e}")
            
        # Jeda waktu refresh otomatis ke data baru
        time.sleep(REFRESH_INTERVAL)

if __name__ == '__main__':
    init_db()
    run_bot()
