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
            # Baca data kustom dari URL browser jika halaman di-refresh
            if isinstance(v, int): st.session_state[k] = int(params[k])
            elif isinstance(v, float): st.session_state[k] = float(params[k])
            else: st.session_state[k] = params[k]
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
# FIX: Menggunakan value dari session_state agar sinkron saat refresh
tf = st.sidebar.selectbox("Timeframe:", options=tf_options, index=tf_options.index(st.session_state.tf) if st.session_state.tf in tf_options else 0)

src_options = ["Close (Penutupan)", "Open (Pembukaan)", "High (Tertinggi)", "Low (Terendah)"]
src_p = st.sidebar.selectbox("Source Data:", options=src_options, index=src_options.index(st.session_state.src) if st.session_state.src in src_options else 0)

# FIX: Menyambungkan parameter value langsung ke st.session_state agar input mengunci otomatis
jumlah_tampilan = st.sidebar.number_input("Jumlah Lilin di Layar:", min_value=10, max_value=300, value=int(st.session_state.jumlah_tampilan), step=10)

l_hma = st.sidebar.number_input("HMA Length:", min_value=2, max_value=50, value=int(st.session_state.l_hma), step=1)
l_ema = st.sidebar.number_input("EMA Length:", min_value=5, max_value=200, value=int(st.session_state.l_ema), step=1)
l_rsi = st.sidebar.number_input("RSI Length:", min_value=5, max_value=30, value=int(st.session_state.l_rsi), step=1)
l_vol = st.sidebar.number_input("Volume MA Length:", min_value=5, max_value=50, value=int(st.session_state.l_vol), step=1)
l_atr = st.sidebar.number_input("ATR Length:", min_value=5, max_value=30, value=int(st.session_state.l_atr), step=1)
m_atr = st.sidebar.number_input("Stop Loss ATR Mult:", min_value=1.0, max_value=4.5, value=float(st.session_state.m_atr), step=0.1)
m_chan = st.sidebar.number_input("Chandelier Trailing Mult:", min_value=1.0, max_value=4.0, value=float(st.session_state.m_chan), step=0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("🔥 Pengaturan Keuangan Agresif")
modal = st.sidebar.number_input("Initial Margin ($):", min_value=10.0, max_value=100000.0, value=float(st.session_state.modal), step=10.0)
lev = st.sidebar.number_input("Leverage:", min_value=1, max_value=50, value=int(st.session_state.lev), step=1)
r_tp1 = st.sidebar.number_input("TP 1 Ratio (Risk:Reward):", min_value=0.3, max_value=5.0, value=float(st.session_state.r_tp1), step=0.1)
fee = st.sidebar.number_input("Trading Fee (%):", min_value=0.0, max_value=1.0, value=float(st.session_state.fee), step=0.01)

st.sidebar.markdown("---")
st.sidebar.subheader("🟡 INTEGRASI API BINANCE FUTURES")
api_key = st.sidebar.text_input("Binance API Key:", type="password")
secret_key = st.sidebar.text_input("Binance Secret Key:", type="password")
mode_trading = st.sidebar.radio("Mode Eksekusi:", ["Simulasi / Testnet", "🚨 LIVE REAL TRADING"], index=0)

# TOMBOL UTAMA UNTUK MENGUNCI PERMANEN KE ALAMAT URL BROWSER
if st.sidebar.button("💾 Kunci & Simpan Setelan"):
    st.session_state.update({"tf": tf, "src": src_p, "jumlah_tampilan": jumlah_tampilan, "l_hma": l_hma, "l_ema": l_ema, "l_rsi": l_rsi, "l_vol": l_vol, "l_atr": l_atr, "m_atr": m_atr, "m_chan": m_chan, "modal": modal, "lev": lev, "r_tp1": r_tp1, "fee": fee})
    # Paksa alamat URL menyimpan string data agar anti-hilang saat F5/Refresh
    st.query_params.update(tf=tf, src=src_p, jumlah_tampilan=str(jumlah_tampilan), l_hma=str(l_hma), l_ema=str(l_ema), l_rsi=str(l_rsi), l_vol=str(l_vol), l_atr=str(l_atr), m_atr=str(m_atr), m_chan=str(m_chan), modal=str(modal), lev=str(lev), r_tp1=str(r_tp1), fee=str(fee))
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
    
    df['hma'] = ta.hma(df[s_map[st.session_state.src]], length=st.session_state.l_hma)
    df['ema'] = ta.ema(df['close'], length=st.session_state.l_ema)
    df['rsi'] = ta.rsi(df['close'], length=st.session_state.l_rsi)
    df['atr'] = ta.atr(df['high'], df['low'], df['close'], length=st.session_state.l_atr)
    df['vol_ma'] = ta.sma(df['volume'], length=st.session_state.l_vol)
    
    df['c_long'] = df['high'].rolling(22).max() - (df['atr'] * st.session_state.m_chan)
    df['c_short'] = df['low'].rolling(22).min() + (df['atr'] * st.session_state.m_chan)
    
    df['is_g'] = df['hma'] >= df['hma'].shift(1)
    df['buy_sig'] = False; df['sell_sig'] = False; last_sig = 0
    
    for i in df.index:
        if i < max(st.session_state.l_hma, st.session_state.l_ema, st.session_state.l_atr, st.session_state.l_vol, 22): continue
        p_long = (df.at[i, 'low'] <= df.at[i, 'ema'] * 1.002) and (df.at[i, 'close'] > df.at[i, 'ema'])
        p_short = (df.at[i, 'high'] >= df.at[i, 'ema'] * 0.998) and (df.at[i, 'close'] < df.at[i, 'ema'])
        
        if df.at[i, 'is_g'] and p_long and (df.at[i, 'rsi'] < 55) and (df.at[i, 'volume'] > df.at[i, 'vol_ma']) and last_sig != 1:
            df.at[i, 'buy_sig'] = True; last_sig = 1
        elif not df.at[i, 'is_g'] and p_short and (df.at[i, 'rsi'] > 45) and (df.at[i, 'volume'] > df.at[i, 'vol_ma']) and last_sig != -1:
            df.at[i, 'sell_sig'] = True; last_sig = -1

    # --- LIVE BANNER SIGNAL ---
    last = df.iloc[-1]
    binance_status = "Mode Simulasi Aktif"
    if last['buy_sig']: 
        st.success(f"### 🟢 SINYAL AKTIF: LONG SEKARANG! | Entry: ${last['close']:,.2f}")
        binance_status = execute_live_binance_order("LONG", last['close'], (st.session_state.modal * 0.30))
    elif last['sell_sig']: 
        st.error(f"### 🔴 SINYAL AKTIF: SHORT SEKARANG! | Entry: ${last['close']:,.2f}")
        binance_status = execute_live_binance_order("SHORT", last['close'], (st.session_state.modal * 0.30))
    else: 
        st.info("### ⚪ STATUS PASAR: WAIT / HOLDING (Menunggu Area Pantulan Valid)")
    
    st.warning(f"🤖 **Status Jembatan API Binance:** {binance_status}")

    # --- 5. FIXED PERCENTAGE COMPOUNDING ENGINE ---
    trades = []; active = None; eq_vals = [st.session_state.modal]; eq_times = [df.loc[0, 'date']]
    c_eq = st.session_state.modal
    
    for i in df.index:
        if active and active['Status'] == "Running":
            if active['Posisi'] == "LONG":
                c_sl = max(active['SL'], df.at[i, 'c_long'])
                if df.at[i, 'low'] <= c_sl:
                    p_net = (((c_sl - active['Entry']) / active['Entry']) * st.session_state.lev) - (st.session_state.fee * 2)
                    c_eq += (p_net / 100) * active['Margin']
                    active.update({'Waktu Close': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'), 'Close': round(c_sl, 2), 'Status': "SL Hit", 'Laba': round(c_eq - active['PrevEq'], 2)})
                    trades.append(active); eq_vals.append(c_eq); eq_times.append(df.at[i, 'date']); active = None
                elif df.at[i, 'high'] >= active['TP1_p']:
                    p_net = (((active['TP1_p'] - active['Entry']) / active['Entry']) * st.session_state.lev) - (st.session_state.fee * 2)
                    c_eq += (p_net / 100) * active['Margin']
                    active.update({'Waktu Close': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'), 'Close': round(active['TP1_p'], 2), 'Status': "TP1 Hit Total", 'Laba': round(c_eq - active['PrevEq'], 2)})
                    trades.append(active); eq_vals.append(c_eq); eq_times.append(df.at[i, 'date']); active = None
                    
            elif active['Posisi'] == "SHORT":
                c_sl = min(active['SL'], df.at[i, 'c_short'])
                if df.at[i, 'high'] >= c_sl:
                    p_net = (((active['Entry'] - c_sl) / active['Entry']) * st.session_state.lev) - (st.session_state.fee * 2)
                    c_eq += (p_net / 100) * active['Margin']
                    active.update({'Waktu Close': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'), 'Close': round(c_sl, 2), 'Status': "SL Hit", 'Laba': round(c_eq - active['PrevEq'], 2)})
                    trades.append(active); eq_vals.append(c_eq); eq_times.append(df.at[i, 'date']); active = None
                elif df.at[i, 'low'] <= active['TP1_p']:
                    p_net = (((active['Entry'] - active['TP1_p']) / active['Entry']) * st.session_state.lev) - (st.session_state.fee * 2)
                    c_eq += (p_net / 100) * active['Margin']
                    active.update({'Waktu Close': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'), 'Close': round(active['TP1_p'], 2), 'Status': "TP1 Hit Total", 'Laba': round(c_eq - active['PrevEq'], 2)})
                    trades.append(active); eq_vals.append(c_eq); eq_times.append(df.at[i, 'date']); active = None

        if df.at[i, 'buy_sig'] and not active:
            sl = df.at[i, 'close'] - (df.at[i, 'atr'] * st.session_state.m_atr)
            j_sl = abs(df.at[i, 'close'] - sl)
            size = c_eq * 0.30
            active = {'Posisi': "LONG", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'), 'Entry': df.at[i, 'close'], 'SL': sl, 'TP1_p': df.at[i, 'close'] + (j_sl * st.session_state.r_tp1), 'Margin': size, 'Waktu Close': "-", 'Close': "-", 'Status': "Running", 'Laba': 0.0, 'PrevEq': c_eq}
        elif df.at[i, 'sell_sig'] and not active:
            sl = df.at[i, 'close'] + (df.at[i, 'atr'] * st.session_state.m_atr)
            j_sl = abs(sl - df.at[i, 'close'])
            size = c_eq * 0.30
            active = {'Posisi': "SHORT", 'Waktu Open': df.at[i, 'date'].strftime('%Y-%m-%d %H:%M'), 'Entry': df.at[i, 'close'], 'SL': sl, 'TP1_p': df.at[i, 'close'] - (j_sl * st.session_state.r_tp1), 'Margin': size, 'Waktu Close': "-", 'Close': "-", 'Status': "Running", 'Laba': 0.0, 'PrevEq': c_eq}

    display_trades = list(trades)
    if active: display_trades.append(active)

    # --- 6. METRICS & RENDERING GRAPH ---
    d_trades = [t for t in trades if t['Status'] != "Running"]
    wr = 0.0; pf = 0.0; mdd = 0.0
    if d_trades:
        w_t = [t for t in d_trades if t['Laba'] > 0]; l_t = [t for t in d_trades if t['Laba'] < 0]
        wr = (len(w_t) / len(d_trades)) * 100
        g_prof = sum([t['Laba'] for t in w_t]); g_loss = abs(sum([t['Laba'] for t in l_t]))
        pf = g_prof / g_loss if g_loss > 0 else g_prof
        eq_s = pd.Series(eq_vals); mdd = abs(((eq_s - eq_s.cummax()) / eq_s.cummax()).min()) * 100

    st.markdown("### 📊 Ringkasan Kinerja Komparatif")
    r1, r2, r3, r4, r5 = st.columns(5)
    r1.metric("Win Rate", f"{wr:.2f}%")
    r2.metric("Profit Factor", f"{pf:.2f}" if pf > 0 else "N/A")
    r3.metric("Max Drawdown (MDD)", f"{mdd:.2f}%")
    r4.metric("Compound ROI", f"{((c_eq - st.session_state.modal)/st.session_state.modal)*100:.2f}%")
    r5.metric("Saldo Akhir", f"${c_eq:,.2f}")

    df_p = df.tail(int(st.session_state.jumlah_tampilan))
    fig = make_subplots(rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.04, row_width=[0.2, 0.2, 0.6])
    fig.add_trace(go.Candlestick(x=df_p['date'], open=df_p['open'], high=df_p['high'], low=df_p['low'], close=df_p['close'], name="Lilin"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_p['date'], y=df_p['hma'], line=dict(color='yellow', width=2), name="HMA"), row=1, col=1)
    fig.add_trace(go.Scatter(x=df_p['date'], y=df_p['ema'], line=dict(color='cyan', width=1, dash='dash'), name="EMA"), row=1, col=1)
    fig.add_trace(go.Bar(x=df_p['date'], y=df_p['volume'], marker_color='orange', name="Volume"), row=2, col=1)
    fig.add_trace(go.Scatter(x=df_p['date'], y=df_p['vol_ma'], line=dict(color='white', width=1), name="Volume MA"), row=2, col=1)
    fig.update_layout(height=650, xaxis_rangeslider_visible=False, template="plotly_dark")
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("### 📈 Kurva Pertumbuhan Ekuitas Modal (Equity Curve)")
    if len(eq_vals) > 1:
        df_equity = pd.DataFrame({"Waktu": eq_times, "Modal ($ USD)": eq_vals})
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=df_equity['Waktu'], y=df_equity['Modal ($ USD)'], mode='lines+markers', line=dict(color='lime', width=2), fill='tozeroy', fillcolor='rgba(0, 255, 0, 0.05)'))
        fig_eq.update_layout(height=300, template="plotly_dark", margin=dict(l=20,r=20,t=20,b=20))
        st.plotly_chart(fig_eq, use_container_width=True)

    if display_trades:
        st.markdown("### 🧾 Log Transaksi")
        df_display_final = pd.DataFrame(display_trades)
        kolom_pilihan = ['Posisi', 'Status', 'Waktu Open', 'Entry', 'SL', 'TP1_p', 'Margin', 'Waktu Close', 'Close', 'Laba']
        df_clean = df_display_final[kolom_pilihan].rename(columns={'TP1_p': 'Target TP', 'Laba': 'Laba Bersih ($)'})
        st.dataframe(df_clean.iloc[::-1], use_container_width=True)

except Exception as err:
    st.error(f"Sistem gagal merender data: {err}")
