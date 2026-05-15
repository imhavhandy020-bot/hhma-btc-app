import time
import json
import os
import ccxt
import pandas as pd
import pandas_ta as ta

# ==============================================================================
# 🕹️ PANEL KENDALI UTAMA & KONFIGURASI PARAMETER
# ==============================================================================
CONFIG = {
    "symbol": "BTC/IDR",
    "timeframe": "4h",            # Fokus satu timeframe utama
    "source_data": "close",
    "indicators": {
        "hma_length": 5,
        "ema_length": 5,
        "rsi_length": 5,
        "volume_ma_length": 5,
        "atr_length": 5
    },
    "risk_management": {
        "stop_loss_atr_mult": 2.50,
        "chandelier_trailing_mult": 1.00,
        "tp_1_ratio": 1.50         # Risk:Reward Ratio
    },
    "financials": {
        "aggressive_allocation": 1.00, # 100% Saldo sekali beli (All-In)
        # Struktur biaya INDODAX IDR Market 2026 (All-In Fee + CFX + Pajak)
        "maker_fee": 0.001111,         # 0.1111%
        "taker_fee": 0.003211          # 0.3211%
    },
    "api_integration": {
        "api_key": "YOUR_INDODAX_API_KEY",
        "secret_key": "YOUR_INDODAX_SECRET_KEY",
        "mode_simulasi": True          # TRUE = Testnet/Simulasi, FALSE = Real Trading
    }
}

STATE_FILE = "bot_state_persistence.json"

# ==============================================================================
# 🔒 STRUKTUR PERSISTENSI DATA (Anti-Loss Saat Restart/Refresh)
# ==============================================================================
def load_bot_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "status_pasar": "WAIT / HOLDING",
        "saldo_simulasi_idr": 10000000.0, # Modal awal simulasi Rp 10 Juta
        "saldo_simulasi_btc": 0.0,
        "last_entry_price": 0.0,
        "total_trades": 0,
        "win_trades": 0,
        "total_profit_loss": 0.0
    }

def save_bot_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=4)

# Inisialisasi API INDODAX via CCXT
def init_exchange():
    return ccxt.indodax({
        'apiKey': CONFIG["api_integration"]["api_key"],
        'secret': CONFIG["api_integration"]["secret_key"],
        'enableRateLimit': True,
    })

# ==============================================================================
# 📊 ENGINE ENGINE INDIKATOR (HHMA & RENKO SNIPER LOGIC)
# ==============================================================================
def fetch_and_calculate_indicators(exchange):
    try:
        # Mengambil data candlestick historis dari pasar INDODAX
        ohlcv = exchange.fetch_ohlcv(CONFIG["symbol"], timeframe=CONFIG["timeframe"], limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # Kalkulasi Moving Average Komposit (HMA & EMA)
        df['hma'] = ta.hma(df['close'], length=CONFIG["indicators"]["hma_length"])
        df['ema'] = ta.ema(df['close'], length=CONFIG["indicators"]["ema_length"])
        
        # Kalkulasi Pendukung Volatilitas & Momentum
        df['rsi'] = ta.rsi(df['close'], length=CONFIG["indicators"]["rsi_length"])
        df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=CONFIG["indicators"]["atr_length"])
        df['volume_ma'] = ta.sma(df['volume'], length=CONFIG["indicators"]["volume_ma_length"])
        
        return df.iloc[-1], df.iloc[-2] # Mengembalikan bar data saat ini dan data sebelumnya
    except Exception as e:
        print(f"❌ [ERROR] Gagal mengambil data pasar: {e}")
        return None, None

# ==============================================================================
# 🤖 LOGIKA EKSEKUSI & SIMULASI KINERJA AGRESIF
# ==============================================================================
def run_bot_cycle():
    exchange = init_exchange()
    state = load_bot_state()
    
    print("==================================================================")
    print(f"🛡️ HHMA Renko Sniper Pro - Berjalan Pada Fokus Timeframe: {CONFIG['timeframe']}")
    print(f"⚪ STATUS PASAR SAAT INI: {state['status_pasar']}")
    print("==================================================================")
    
    current_bar, prev_bar = fetch_and_calculate_indicators(exchange)
    if current_bar is None:
        return

    close_price = current_bar['close']
    hma = current_bar['hma']
    ema = current_bar['ema']
    rsi = current_bar['rsi']
    atr = current_bar['atr']
    
    print(f"📊 Live Data BTC/IDR -> Close: {close_price:,.0f} | HMA(5): {hma:,.0f} | RSI(5): {rsi:.2f}")

    # --- LOGIKA EMULASI SINYAL SNIPER (Pembalikan Arah / Pantulan Valid) ---
    # Sinyal Beli: Harga memotong ke atas HMA, HMA > EMA, dan RSI keluar dari zona oversold (< 35)
    buy_signal = (close_price > hma) and (hma > ema) and (prev_bar['rsi'] < 35 or rsi > 30)
    
    # Perhitungan Jarak Resiko Komparatif
    stop_loss_distance = atr * CONFIG["risk_management"]["stop_loss_atr_mult"]
    target_profit_distance = stop_loss_distance * CONFIG["risk_management"]["tp_1_ratio"]

    if state["status_pasar"] == "WAIT / HOLDING":
        if buy_signal:
            print("🚨 [SIGNAL] Sinyal Pantulan Valid Terdeteksi! Menjalankan Pembelian Agresif...")
            
            # Hitung kalkulasi pemotongan dana + fee taker INDODAX pasar IDR
            fee_pembelian = state["saldo_simulasi_idr"] * CONFIG["financials"]["taker_fee"]
            dana_bersih = state["saldo_simulasi_idr"] - fee_pembelian
            
            state["saldo_simulasi_btc"] = dana_bersih / close_price
            state["saldo_simulasi_idr"] = 0.0
            state["last_entry_price"] = close_price
            state["status_pasar"] = "IN_POSITION"
            
            print(f"🟩 [EXECUTION] Sukses Beli di Harga: Rp {close_price:,.0f}")
            print(f"📋 Parameter Pengaman -> SL: Rp {close_price - stop_loss_distance:,.0f} | TP: Rp {close_price + target_profit_distance:,.0f}")
            save_bot_state(state)

    elif state["status_pasar"] == "IN_POSITION":
        entry = state["last_entry_price"]
        sl_level = entry - stop_loss_distance
        tp_level = entry + target_profit_distance
        
        # Periksa kondisi Target Profit atau Stop Loss
        if close_price >= tp_level or close_price <= sl_level:
            is_win = close_price >= tp_level
            status_trade = "PROFIT (TP 1)" if is_win else "LOSING (SL)"
            
            # Eksekusi Penjualan Saldo BTC (All-In)
            gross_idr = state["saldo_simulasi_btc"] * close_price
            fee_penjualan = gross_idr * CONFIG["financials"]["taker_fee"]
            state["saldo_simulasi_idr"] = gross_idr - fee_penjualan
            state["saldo_simulasi_btc"] = 0.0
            
            # Pembaharuan Metrik Performa Komparatif
            state["total_trades"] += 1
            if is_win:
                state["win_trades"] += 1
            
            state["status_pasar"] = "WAIT / HOLDING"
            win_rate = (state["win_trades"] / state["total_trades"]) * 100
            
            print(f"🚨 [EXIT] Posisi Ditutup Pada Kondisi {status_trade} di Harga: Rp {close_price:,.0f}")
            print(f"📊 STATISTIK TERBARU -> Win Rate: {win_rate:.2f}% | Total Trades: {state['total_trades']}")
            print(f"💰 Saldo Dompet IDR Saat Ini: Rp {state['saldo_simulasi_idr']:,.2f}")
            save_bot_state(state)

if __name__ == "__main__":
    # Menjalankan bot secara continuous loop mengikuti interval update lilin 4 jam
    while True:
        run_bot_cycle()
        # Melakukan pengecekan berkala ke pasar setiap 60 detik
        time.sleep(60)
