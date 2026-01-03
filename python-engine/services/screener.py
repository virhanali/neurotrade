"""
Market Screener Service
Scans Binance Futures market for high-volume, volatile opportunities
"""

import ccxt
import logging
import pandas as pd
import ta
from typing import List, Dict
from config import settings


class MarketScreener:
    """Screens market for top trading opportunities"""

    def __init__(self):
        """Initialize CCXT Binance Futures client (public API only)"""
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })

    def get_top_opportunities(self) -> List[str]:
        """
        Screen market for top trading opportunities

        Filter Criteria:
        1. 24h Quote Volume > $50,000,000 (Liquid coins)
        2. 1h Price Change > 1.5% (Volatile coins)

        Returns:
            List of top 5 symbol names sorted by volatility
        """
        try:
            # Try to get data from WebSocket first (Fastest)
            # Late import to avoid circular dependency
            from services.price_stream import price_stream
            
            raw_tickers = {}
            source = "REST"
            
            if price_stream.is_connected and len(price_stream.get_all_tickers()) > 100:
                raw_tickers = price_stream.get_all_tickers()
                source = "WEBSOCKET"
                logging.info(f"📊 Using WebSocket data for screening ({len(raw_tickers)} tickers)")
            else:
                # Fallback to REST API
                if not self.exchange.markets:
                    self.exchange.load_markets()
                raw_tickers = self.exchange.fetch_tickers()
                logging.warning("⚠️ Using REST API for screening (WebSocket not ready)")

            # Filter USDT futures pairs
            opportunities = []

            for symbol, ticker in raw_tickers.items():
                
                # Handling different formats (WS dict vs CCXT dict)
                # WS Keys: symbol, price, quoteVolume, percentage
                # CCXT Keys: symbol, quoteVolume, percentage...
                
                # 1. Normalize Symbol
                # WS symbols assume no slash (BTCUSDT), CCXT usually has slash (BTC/USDT)
                # But our WS parser stores 'symbol' as is from stream (e.g. BTCUSDT)
                
                # Check if it is a USDT pair
                is_usdt = False
                clean_symbol = ""
                
                if source == "WEBSOCKET":
                     # WS format: "BTCUSDT"
                     if symbol.endswith("USDT"):
                         is_usdt = True
                         # Insert slash for consistency with system format: BTC/USDT
                         base = symbol[:-4]
                         clean_symbol = f"{base}/USDT"
                else:
                    # CCXT format: "BTC/USDT:USDT" or "BTC/USDT"
                    if symbol.endswith("/USDT:USDT"):
                        is_usdt = True
                        clean_symbol = symbol.replace(":USDT", "")
                
                if not is_usdt:
                    continue

                # 2. Extract Data
                quote_volume = ticker.get('quoteVolume', 0)
                percentage_change = ticker.get('percentage', 0)

                # Apply filters
                if quote_volume is None or percentage_change is None:
                    continue

                # 3. Check STATUS (Only needed for REST, WS implies active)
                if source == "REST":
                    # Check if symbol is TRADING using cached markets
                    # Note: WS stream only sends active tickers usually, but REST sends all
                    if symbol in self.exchange.markets:
                        market = self.exchange.markets[symbol]
                        status = market.get('info', {}).get('status', 'UNKNOWN')
                        if status != 'TRADING':
                            continue
                
                # Filter by volume and volatility
                if quote_volume >= settings.MIN_VOLUME_USDT and abs(percentage_change) >= settings.MIN_VOLATILITY_1H:
                    opportunities.append({
                        'symbol': clean_symbol,
                        'volume': quote_volume,
                        'volatility': abs(percentage_change),
                        'change': percentage_change,
                    })



            # Sort by volatility (highest first) to get Candidates
            opportunities.sort(key=lambda x: x['volatility'], reverse=True)
            
            # Take top 10 candidates for RSI check (Pre-filter)
            candidates = opportunities[:10]
            final_list = []
            
            logging.info(f"🔍 Analyzing RSI for top {len(candidates)} volatile coins...")
            
            for cand in candidates:
                symbol = cand['symbol']
                try:
                    # Fetch small amount of candles for RSI (Fast)
                    ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
                    if not ohlcv or len(ohlcv) < 50:
                        continue
                        
                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # Calculate RSI
                    rsi_series = ta.momentum.rsi(df['close'], window=14)
                    current_rsi = rsi_series.iloc[-1]
                    
                    cand['rsi'] = current_rsi
                    
                    # Logika Score: Prioritaskan RSI Ekstrem (<30 atau >70)
                    # Score = Jarak dari 50 (Neutral)
                    # RSI 30 -> Score 20. RSI 80 -> Score 30.
                    cand['rsi_score'] = abs(current_rsi - 50)
                    
                    # Strict Filter: Only allow signals with momentum (RSI < 40 or > 60)
                    if 40 <= current_rsi <= 60:
                        continue
                        
                    final_list.append(cand)
                    
                except Exception as e:
                    logging.error(f"⚠️ Failed to calc RSI for {symbol}: {e}")
                    continue
            
            # Sort by RSI Score (Most Extreme First)
            # Ini memastikan kita dapat koin yang benar-benar Overbought/Oversold
            final_list.sort(key=lambda x: x['rsi_score'], reverse=True)

            # Return top N symbols (Limit to 5 for AI Analysis safety)
            # Even if we screen 50 coins, we only want AI to deep dive into the top 5
            # 5 coins * 15s avg analysis = 75s (Safe for 2 min cron)
            safe_limit = 5
            top_symbols = [opp['symbol'] for opp in final_list[:safe_limit]]
            
            logging.info(f"✅ Selected {len(top_symbols)} coins (from {len(candidates)} candidates) based on Volatility + RSI")
            return top_symbols

        except Exception as e:
            raise Exception(f"Failed to screen market: {str(e)}")

    def get_screener_summary(self) -> Dict:
        """
        Get detailed screener summary with statistics

        Returns:
            Dict with screener results and metadata
        """
        try:
            # Load markets first
            if not self.exchange.markets:
                self.exchange.load_markets()

            tickers = self.exchange.fetch_tickers()

            # Statistics
            total_pairs = 0
            liquid_pairs = 0
            volatile_pairs = 0
            opportunities = []

            for symbol, ticker in tickers.items():
                if not symbol.endswith('/USDT:USDT'):
                    continue

                total_pairs += 1

                quote_volume = ticker.get('quoteVolume', 0)
                percentage_change = ticker.get('percentage', 0)

                if quote_volume is None or percentage_change is None:
                    continue

                # Check liquid
                if quote_volume >= settings.MIN_VOLUME_USDT:
                    liquid_pairs += 1

                # Check volatile
                if abs(percentage_change) >= settings.MIN_VOLATILITY_1H:
                    volatile_pairs += 1

                # Check both
                if quote_volume >= settings.MIN_VOLUME_USDT and abs(percentage_change) >= settings.MIN_VOLATILITY_1H:
                    opportunities.append({
                        'symbol': symbol.replace(':USDT', ''),
                        'volume': quote_volume,
                        'volatility': abs(percentage_change),
                        'change': percentage_change,
                    })

            # Sort by volatility
            opportunities.sort(key=lambda x: x['volatility'], reverse=True)

            return {
                "total_pairs": total_pairs,
                "liquid_pairs": liquid_pairs,
                "volatile_pairs": volatile_pairs,
                "opportunities_found": len(opportunities),
                "top_opportunities": opportunities[:settings.TOP_COINS_LIMIT],
                "filter_criteria": {
                    "min_volume_usdt": settings.MIN_VOLUME_USDT,
                    "min_volatility_pct": settings.MIN_VOLATILITY_1H,
                }
            }

        except Exception as e:
            raise Exception(f"Failed to get screener summary: {str(e)}")
