"""
Market Screener Service
Scans Binance Futures market for high-volume, volatile opportunities
"""

import ccxt
import logging
import pandas as pd
import ta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from config import settings


class MarketScreener:
    """Screens market for top trading opportunities"""

    def __init__(self):
        """Initialize CCXT Binance Futures client with increased connection pool"""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # Create session with larger connection pool for parallel requests
        session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=20,  # Number of connection pools
            pool_maxsize=20,      # Connections per pool
            max_retries=Retry(total=3, backoff_factor=0.5)
        )
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
            'session': session  # Use custom session with larger pool
        })

    def get_top_opportunities(self) -> List[Dict]:
        """
        Screen market for top trading opportunities [PRO MODE]
        Returns list of candidate dictionaries with metrics.
        
        New Logic (Resource Heavy):
        1. Fetch Top 30 Volatile Candidates
        2. MTF Analysis: Check 15m AND 4H Trends
        3. Volume Spike Detection
        4. Strict RSI + Trend Confluence
        """
        try:
            # Try to get data from WebSocket first (Fastest)
            from services.price_stream import price_stream
            
            raw_tickers = {}
            source = "REST"
            
            if price_stream.is_connected and len(price_stream.get_all_tickers()) > 100:
                raw_tickers = price_stream.get_all_tickers()
                source = "WEBSOCKET"
                logging.info(f"[INFO] Using WebSocket data for screening ({len(raw_tickers)} tickers)")
            else:
                if not self.exchange.markets:
                    self.exchange.load_markets()
                raw_tickers = self.exchange.fetch_tickers()
                logging.warning("[WARN] Using REST API for screening (WebSocket not ready)")

            # Filter USDT futures pairs
            opportunities = []

            for symbol, ticker in raw_tickers.items():
                is_usdt = False
                clean_symbol = ""
                
                if source == "WEBSOCKET":
                     if symbol.endswith("USDT"):
                         is_usdt = True
                         base = symbol[:-4]
                         clean_symbol = f"{base}/USDT"
                else:
                    if symbol.endswith("/USDT:USDT"):
                        is_usdt = True
                        clean_symbol = symbol.replace(":USDT", "")
                
                if not is_usdt:
                    continue

                quote_volume = ticker.get('quoteVolume', 0)
                percentage_change = ticker.get('percentage', 0)

                if quote_volume is None or percentage_change is None:
                    continue
                
                # Check STATUS (active trading only)
                if source == "REST" and symbol in self.exchange.markets:
                    status = self.exchange.markets[symbol].get('info', {}).get('status', 'UNKNOWN')
                    if status != 'TRADING':
                        continue
                
                # Initial pre-filter
                if quote_volume >= settings.MIN_VOLUME_USDT and abs(percentage_change) >= settings.MIN_VOLATILITY_1H:
                    opportunities.append({
                        'symbol': clean_symbol,
                        'volume': quote_volume,
                        'volatility': abs(percentage_change),
                    })

            # Sort by volatility and take Top Candidates (Deep Scan)
            # We scan 150 raw candidates effectively to find the hidden gems.
            # Processing is done locally (CPU), so it's cheap.
            scan_limit = 150
            
            opportunities.sort(key=lambda x: x['volatility'], reverse=True)
            candidates = opportunities[:scan_limit]
            
            logging.info(f"[SCAN] Deep Scanning {len(candidates)} candidates (PARALLEL MTF + Volume) for Top {settings.TOP_COINS_LIMIT}...")
            
            # Define analysis function for parallel execution
            def analyze_candidate(cand: Dict) -> Optional[Dict]:
                """Analyze a single candidate - runs in thread"""
                symbol = cand['symbol']
                try:
                    # 1. Fetch 15m Data (Tactical)
                    ohlcv_15m = self.exchange.fetch_ohlcv(symbol, timeframe='15m', limit=50)
                    if not ohlcv_15m or len(ohlcv_15m) < 50: 
                        return None
                    df_15m = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # 2. Fetch 4h Data (Strategic Trend)
                    ohlcv_4h = self.exchange.fetch_ohlcv(symbol, timeframe='4h', limit=200)
                    if not ohlcv_4h or len(ohlcv_4h) < 200: 
                        return None
                    df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

                    # --- Tech Analysis ---

                    # A. Volume Logic (Smart Money Context)
                    # Calculate Volume Ratio
                    avg_vol = df_15m['volume'].rolling(window=20).mean().iloc[-1]
                    cur_vol = df_15m['volume'].iloc[-1]
                    vol_ratio = cur_vol / avg_vol if avg_vol > 0 else 0
                    
                    # B. Bollinger Band Squeeze Detection
                    # BandWidth = (Upper - Lower) / Middle
                    rolling_mean = df_15m['close'].rolling(window=20).mean()
                    rolling_std = df_15m['close'].rolling(window=20).std()
                    bb_upper = rolling_mean + (rolling_std * 2)
                    bb_lower = rolling_mean - (rolling_std * 2)
                    bb_width = (bb_upper.iloc[-1] - bb_lower.iloc[-1]) / rolling_mean.iloc[-1]
                    
                    is_squeeze = bb_width < 0.02  # Less than 2% width = SQUEEZE

                    # FILTER LOGIC:
                    # 1. Reject Dead Coins (Vol < 0.5x Avg) UNLESS it's a Squeeze (Accumulation)
                    if vol_ratio < 0.5 and not is_squeeze:
                        return None

                    # C. Trend Filter (4H EMA 200) - Keep for direction
                    ema_200_4h = ta.trend.ema_indicator(df_4h['close'], window=200).iloc[-1]
                    current_price = df_15m['close'].iloc[-1]
                    major_trend = "BULL" if current_price > ema_200_4h else "BEAR"

                    # D. RSI (15m)
                    rsi_val = ta.momentum.rsi(df_15m['close'], window=14).iloc[-1]

                    # NEW: ADX (Trend Strength) - Critical for avoiding "Fake Reversals"
                    try:
                        adx_indicator = ta.trend.ADXIndicator(df_15m['high'], df_15m['low'], df_15m['close'], window=14)
                        adx_val = adx_indicator.adx().iloc[-1]
                    except:
                        adx_val = 25 # Fallback

                    # NEW: ATR % (Volatility Quality)
                    try:
                        atr_obj = ta.volatility.AverageTrueRange(df_15m['high'], df_15m['low'], df_15m['close'], window=14)
                        atr_val = atr_obj.average_true_range().iloc[-1]
                        atr_pct = (atr_val / df_15m['close'].iloc[-1]) * 100
                    except:
                        atr_pct = 0.5 # Fallback

                    # FILTER LOGIC (QUALITY CONTROL):
                    # 1. ADX Filter REMOVED -> We want to trade Sideways markets too (Ping Pong Strategy)
                    # if adx_val < 20 and not is_squeeze: return None
                    
                    # 2. Reject Dead Coins (Vol < 0.5x Avg) UNLESS it's a Squeeze (Accumulation)
                    if vol_ratio < 0.5 and not is_squeeze:
                        return None
                    
                    # 3. Reject EXTREMELY Low Volatility (ATR < 0.15%) - Dead coins
                    if atr_pct < 0.15:
                         return None
                    
                    # E. Scoring System (Hybrid: Volatility + Squeeze + Trend Strength)
                    score = 0
                    
                    # Scenario 1: Predictive Alpha (Squeeze) -> HIGHEST PRIORITY
                    if is_squeeze:
                         score += 50  # Huge bonus for squeeze
                         if vol_ratio > 1.0: score += 20  # Squeeze + Volume = BREAKOUT IMMINENT
                    
                    # Scenario 2: Reversal Play (RSI Extreme)
                    elif rsi_val < 35 and major_trend == "BULL": # Oversold in Uptrend
                        score += (35 - rsi_val) * 2
                    elif rsi_val > 65 and major_trend == "BEAR": # Overbought in Downtrend
                        score += (rsi_val - 65) * 2
                        
                    # Scenario 3: Strong Trend Play (ADX > 40)
                    if adx_val > 40:
                        score += 15 # Bonus for strong trend currency
                        
                    # Scenario 4: Breakout Play (Volume Spike)
                    elif vol_ratio > 2.0:
                        score += 30
                    
                    # Baseline Volume Score
                    score += (vol_ratio * 5)

                    if score > 10: # Only return decent candidates
                        result = cand.copy()
                        result['score'] = score
                        result['rsi'] = rsi_val
                        result['trend'] = major_trend
                        result['vol_ratio'] = vol_ratio
                        result['is_squeeze'] = is_squeeze
                        result['adx'] = adx_val
                        result['atr_pct'] = atr_pct
                        return result
                    
                    return None
                    
                except Exception as e:
                    logging.error(f"[WARN] Screener error for {symbol}: {e}")
                    return None
            
            # Execute parallel analysis (10 threads = optimal balance for speed vs rate limit)
            # 10 threads × 2 req = 20 req/sec burst (safe under CloudFront limit)
            final_list = []
            with ThreadPoolExecutor(max_workers=10) as executor:
                futures = {executor.submit(analyze_candidate, cand): cand for cand in candidates}
                
                for future in as_completed(futures):
                    result = future.result()
                    if result is not None:
                        final_list.append(result)
            
            # Sort by Confluence Score
            final_list.sort(key=lambda x: x['score'], reverse=True)

            # Return Top N Candidates (Metrics Included)
            top_candidates = final_list[:settings.TOP_COINS_LIMIT]
            
            logging.info(f"[OK] Selected {len(top_candidates)} coins with Alpha Metrics")
            return top_candidates

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
