# hhma-btc-app
# Bot Trading Indodax Multi-Pair Pro Server
Bot trading standalone otomatis berjalan 24 jam di server cloud tanpa ketergantungan browser HP.

## Spesifikasi Terpasang:
1. **Framework**: Streamlit Cloud + SQLite Memori Permanen (`trading_bot.db`).
2. **Indikator**: Rumus Kontinu HMA Periode 20 (Timeframe 4 Jam / 4h).
3. **Data Feed**: Jalur Stabil Internasional Binance Data API.
4. **Logika Eksekusi**: Terikat Pengunci Database (BUY -> SELL -> BUY) Anti-Sinyal Palsu.
5. **Manajemen Risiko**: Rem Saldo Otomatis (Anti-Saldo Kosong) + Filter Likuiditas Minimum Volume.
6. **Daftar Pair**: BTC/IDR, ETH/IDR, USDT/IDR, SOL/IDR, DOGE/IDR.
