import streamlit as st
import pandas as pd
import pandas_ta_classic as ta
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import ccxt 

st.set_page_config(page_title="HHMA Sniper BTC Max Pro", layout="wide")
st.title("🛡️ HHMA Renko Sniper Pro - Binance Futures Trading Bot")

# --- 1. DEFINISI PENGATURAN AWAL PABRIK ---
DEFAULTS = {
    "tf": "4 Jam (4h)", "src": "Close (Penutupan)", "jumlah_tampilan": 10,       
    "l_hma": 5, "l_ema": 5, "l_rsi": 5, "l_vol": 5, "l_atr": 5,                 
    "m_atr": 2.5, "m_chan": 1.0, "modal": 100.0, "lev": 25, "r_tp1": 1.50, "fee": 0.04                 
}

# --- 2. SINKRONISASI MEMORI URL & SESSION STATE (ANTI-RESET) ---
params = st.query_params

for k, v in DEFAULTS.items():
    if k not in st.session_state:
        if k in params:
            # Baca data kustom dari URL browser jika halaman di-refresh dengan konversi tipe data yang tepat
            if isinstance(v, int): 
                st.session_state[k] = int(params[k])
            elif isinstance(v, float): 
                st.session_state[k] = float(params[k])
            else: 
                st.session_state[k] = params[k]
        else:
            st.session_state[k] = v

def reset_to_factory():
    for k, v in DEFAULTS.items(): 
        st.session_state[k] = v
    st.query_params.clear()
    st.rerun()

# --- 3. CONTROL PANEL (SIDEBAR - INPUT DUA ARAH) ---
st.sidebar.header("🕹️ PANEL KENDALI UTAMA")

if st.sidebar.button("🔄 Reset ke Pengaturan Awal"):
    reset_to_factory()

st.sidebar.markdown("---")
tf_options = ["4 Jam (4h)", "1 Hari (Daily)"]
# FIX: Menggunakan parameter 'key' yang terikat langsung ke session_state
st.sidebar.selectbox("Timeframe:", options=tf_options, index=tf_options.index(st.session_state.tf) if st.session_state.tf in tf_options else 0, key="tf")

src_options = ["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"]
st.sidebar.selectbox("Source Data:", options=src_options, index=src_options.index(st.session_state.src) if st.session_state.src in src_options else 0, key="src")

# FIX: Setiap input menggunakan parameter 'key' agar nilainya otomatis terkunci di session_state saat diubah
st.sidebar.number_input("Jumlah Lilin di Layar:", min_value=10, max_value=300, step=10, key="jumlah_tampilan")

l_hma = st.sidebar.number_input("HMA Length:", min_value=2, max_value=50, step=1, key="l_hma")
l_ema = st.sidebar.number_input("EMA Length:", min_value=5, max_value=200, step=1, key="l_ema")
l_rsi = st.sidebar.number_input("RSI Length:", min_value=5, max_value=30, step=1, key="l_rsi")
l_vol = st.sidebar.number_input("Volume MA Length:", min_value=5, max_value=50, step=1, key="l_vol")
l_atr = st.sidebar.number_input("ATR Length:", min_value=5, max_value=30, step=1, key="l_atr")
m_atr = st.sidebar.number_input("Stop Loss ATR Mult:", min_value=1.0, max_value=4.5, step=0.1, key="m_atr")
m_chan = st.sidebar.number_input("Chandelier Trailing Mult:", min_value=1.0, max_value=4.0, step=0.1, key="m_chan")

st.sidebar.markdown("---")
st.sidebar.subheader("🔥 Pengaturan Keuangan Agresif")
st.sidebar.number_input("Initial Margin ($):", min_value=10.0, max_value=100000.0, step=10.0, key="modal")
st.sidebar.number_input("Leverage:", min_value=1, max_value=50, step=1, key="lev")
st.sidebar.number_input("TP 1 Ratio (Risk:Reward):", min_value=0.3, max_value=5.0, step=0.1, key="r_tp1")
st.sidebar.number_input("Trading Fee (%):", min_value=0.0, max_value=1.0, step=0.01, key="fee")

st.sidebar.markdown("---")
st.sidebar.subheader("🟡 INTEGRASI API BINANCE FUTURES")
api_key = st.sidebar.text_input("Binance API Key:", type="password")
secret_key = st.sidebar.text_input("Binance Secret Key:", type="password")
mode_trading = st.sidebar.radio("Mode Eksekusi:", ["Simulasi / Testnet", "🚨 LIVE REAL TRADING"], index=0)

# TOMBOL UTAMA UNTUK MENGUNCI PERMANEN KE ALAMAT URL BROWSER
if st.sidebar.button("💾 Kunci & Simpan Setelan"):
    # Paksa alamat URL menyimpan string data terbaru dari session_state agar anti-hilang saat F5/Refresh
    st.query_params.update(
        tf=st.session_state.tf, 
        src=st.session_state.src, 
        jumlah_tampilan=str(st.session_state.jumlah_tampilan), 
        l_hma=str(st.session_state.l_hma), 
        l_ema=str(st.session_state.l_ema), 
        l_rsi=str(st.session_state.l_rsi), 
        l_vol=str(st.session_state.l_vol), 
        l_atr=str(st.session_state.l_atr), 
        m_atr=str(st.session_state.m_atr), 
        m_chan=str(st.session_state.m_chan), 
        modal=str(st.session_state.modal), 
        lev=str(st.session_state.lev), 
        r_tp1=str(st.session_state.r_tp1), 
        fee=str(st.session_state.fee)
    )
    st.success("💾 Setelan berhasil dikunci secara permanen di alamat web Anda!")

# --- API BINANCE ORDER EXECUTION ---
def execute_live_binance_order(posisi, entry_price, margin_size):
    if not api_key or not secret_key:
        return "⚠️ API Key kosong. Eksekusi Live diabaikan."
    try:
        exchange = ccxt.binance({
            'apiKey': api_key, 'secret': secret_key,
            'options': {'defaultType': 'future'}, 'enableRateLimit': True
        })
        if mode_trading == "Simulasi / Testnet":
            exchange.set_sandbox_mode(True)
        symbol = 'BTC/USDT'
        exchange.fapiPrivatePostLeverage({'symbol': 'BTCUSDT', 'leverage': int(st.session_state.lev)})
        quantity_btc = (float(margin_size) * float(st.session_state.lev)) / float(entry_price)
        quantity_btc = round(quantity_btc, 3)
        if quantity_btc <= 0: return "❌ Ukuran Margin terlalu kecil."
        
        if posisi == "LONG":
            exchange.create_market_buy_order(symbol, quantity_btc)
            return f"🚀 Binance Sukses: LONG {quantity_btc} BTC"
        elif posisi == "SHORT":
            exchange.create_market_sell_order(symbol, quantity_btc)
            return f"📉 Binance Sukses: SHORT {quantity_btc} BTC"
    except Exception as e:
        return f"❌ Gagal API Binance: {str(e)}"

# --- 4. DATA FETCHING & TA CALCULATION ---
t_map = {"4 Jam (4h)": "4h", "1 Hari (Daily)": "1d"}
p_map = {"4 Jam (4h)": "180d", "1 Hari (Daily)": "730d"}
s_map = {"Close (Penutupan)": "close", "Open (Pembukaan)": "open", "High (Tertinggi)": "high", "Low (Terendah)": "low"}

@st.cache_data(ttl=30)
def load_data(p, i):
    df = yf.Ticker("BTC-USD").history(period=p, interval=i).reset_index()
    c_map = {'Date': 'date', 'Datetime': 'date', 'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'}
    return df.rename(columns={k: v for k, v in c_map.items() if k in df.columns})

try:
    df = load_data(p_map[st.session_state.tf], t_map[st.session_state.tf])
    
    if df['date'].dt.tz is not None:
        df['date'] = df['date'].dt.tz_convert('Asia/Jakarta').dt.tz_localize(None)
    else:
        df['date'] = df['date'].dt.tz_localize('UTC').dt.tz_convert('Asia/Jakarta').dt.tz_localize(None)
        
    st.write(df.head(int(st.session_state.jumlah_tampilan))) # Contoh kelanjutan visualisasi data aman

except Exception as e:
    st.error(f"Gagal memproses data: {e}")
