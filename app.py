import time
import sqlite3
import pandas as pd
import numpy as np
import ccxt

# ==========================================
# 1. KONFIGURASI API INDODAX & PARAMETER
# ==========================================
API_KEY = 'ISI_API_KEY_ANDA_DISINI'
SECRET_KEY = 'ISI_SECRET_KEY_ANDA_DISINI'
SYMBOL = 'BTC/IDR'       # Sepasang aset yang ditransaksikan
TIMEFRAME = '1d'         # Timeframe harian sesuai skrip Pine
HMA_LENGTH = 2           # Panjang periode HMA sesuai skrip Pine
REFRESH_INTERVAL = 60    # Jeda refresh data market (dalam detik)

# Parameter Manajemen Risiko
TAKE_PROFIT_PCT = 0.05   # Pelebaran profit / TP (Contoh: 5%)
STOP_LOSS_PCT = 0.02     # Batasan rugi / SL (Contoh: 2%)

# Inisialisasi API Indodax via CCXT
exchange = ccxt.indodax({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True
})

# ==========================================
# 2. MANAJEMEN DATABASE (Penyimpanan Data)
# ==========================================
def init_db():
    conn = sqlite3.connect('trading_bot.db')
    cursor = conn.cursor()
    # Tabel riwayat sinyal dan transaksi
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
    print(f" Data {signal_type} berhasil disimpan ke database.")

# ==========================================
# 3. PERHITUNGAN RUMUS INDIKATOR HMA
# ==========================================
def wma(series, length):
    weights = np.arange(1, length + 1)
    return series.rolling(length).apply(lambda x: np.dot(x, weights) / weights.sum(), raw=True)

def calculate_hma(df, length):
    # Rumus asli Hull Moving Average (HMA)
    half_length = int(length / 2)
    sqrt_length = int(np.sqrt(length))
    
    wma_half = wma(df['close'], half_length)
    wma_full = wma(df['close'], length)
    
    raw_hma = (2 * wma_half) - wma_full
    df['hma'] = wma(raw_hma, sqrt_length)
    return df

# ==========================================
# 4. LOGIKA EKSEKUSI TRADING (CORE BOT)
# ==========================================
def run_bot():
    print("Bot berjalan... Menunggu pembaruan data market.")
    last_signal = 0 # Mengunci status sinyal agar bergantian
    
    while True:
        try:
            # Auto-Refresh: Ambil data candlestick terbaru
            bars = exchange.fetch_ohlcv(SYMBOL, TIMEFRAME, limit=100)
            df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = calculate_hma(df, HMA_LENGTH)
            
            if len(df) < 3:
                continue
                
            # Mengambil bar berjalan [ -1 ] dan bar sebelumnya [ -2 ] untuk deteksi cross
            current_hma = df['hma'].iloc[-1]
            prev_hma = df['hma'].iloc[-2]
            prev_prev_hma = df['hma'].iloc[-3]
            current_close = df['close'].iloc[-1]
            
            # Logika Arah Kemiringan HMA (Sesuai is_green / is_red)
            is_green_now = current_hma >= prev_hma
            is_green_prev = prev_hma >= prev_prev_hma
            
            # Sinyal Perubahan Warna Pertama Kali (Raw Signal)
            raw_buy = is_green_now and not is_green_prev
            raw_sell = not is_green_now and is_green_prev
            
            # Eksekusi Sinyal (Sistem Pengunci Bergantian)
            if raw_buy and last_signal != 1:
                tp = current_close * (1 + TAKE_PROFIT_PCT)
                sl = current_close * (1 - STOP_LOSS_PCT)
                
                print(f"\n[SINYAL BUY DETEKSI] Harga: {current_close} | TP: {tp} | SL: {sl}")
                # Eksekusi order riil di Indodax (Aktifkan jika saldo siap)
                # exchange.create_market_buy_order(SYMBOL, jumlah_beli)
                
                save_trade('BUY', current_close, tp, sl)
                last_signal = 1
                
            elif raw_sell and last_signal != -1:
                tp = current_close * (1 - TAKE_PROFIT_PCT)
                sl = current_close * (1 + STOP_LOSS_PCT)
                
                print(f"\n[SINYAL SELL DETEKSI] Harga: {current_close} | TP: {tp} | SL: {sl}")
                # exchange.create_market_sell_order(SYMBOL, jumlah_jual)
                
                save_trade('SELL', current_close, tp, sl)
                last_signal = -1
                
            else:
                print(f"Market Standby... Harga {SYMBOL}: {current_close} | HMA: {current_hma:.2f}", end="\r")

        except Exception as e:
            print(f"\n Terjadi error atau kendala jaringan: {e}")
            
        # Jeda waktu refresh otomatis data baru
        time.sleep(REFRESH_INTERVAL)

if __name__ == '__main__':
    init_db()
    run_bot()
