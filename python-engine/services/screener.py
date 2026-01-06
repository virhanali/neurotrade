"""
Market Screener Service (v4.2)
Scans Binance Futures market for high-volume, volatile opportunities
Enhanced with Whale Detection (Liquidation + Order Book Analysis)
"""

import ccxt
import logging
import pandas as pd
import ta
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from config import settings

# Import Whale Detector
try:
    from services.whale_detector import get_whale_signal_sync
    HAS_WHALE_DETECTOR = True
except ImportError:
    HAS_WHALE_DETECTOR = False
    logging.warning("[SCREENER] Whale detector not available")


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

    def check_5min_confirmation(self, symbol: str, whale_signal: str) -> bool:
        """
        Check if 5-minute timeframe confirms the 15-minute whale signal.
        (Tier 2 / Option 2 enhancement - 5-min confirmation layer)

        Returns True if 5-min supports the signal, False if contradicts.
        This reduces false signals and improves entry timing.
        """
        try:
            # Only check confirmation for strong whale signals
            if whale_signal not in ['PUMP_IMMINENT', 'DUMP_IMMINENT']:
                return True  # Non-whale signals don't need 5-min confirmation

            # Fetch last 5 candles of 5-minute timeframe
            ohlcv = self.exchange.fetch_ohlcv(symbol, '5m', limit=5)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            if len(df) < 2:
                return True  # Not enough data, allow trade

            # Simple 5-min breakout confirmation
            current_close = df.iloc[-1]['close']
            prev_open = df.iloc[-2]['open']
            prev_high = df.iloc[-2]['high']
            prev_low = df.iloc[-2]['low']

            if whale_signal == 'PUMP_IMMINENT':
                # For pump: 5-min should be breaking above previous candle high
                confirmed = current_close > prev_high
                if confirmed:
                    logging.info(f"[5-MIN CONFIRM] {symbol}: 5-min breakout UP confirmed for PUMP_IMMINENT")
                else:
                    logging.info(f"[5-MIN] {symbol}: PUMP signal but 5-min NOT breaking (no confirmation)")
                return confirmed

            elif whale_signal == 'DUMP_IMMINENT':
                # For dump: 5-min should be breaking below previous candle low
                confirmed = current_close < prev_low
                if confirmed:
                    logging.info(f"[5-MIN CONFIRM] {symbol}: 5-min breakout DOWN confirmed for DUMP_IMMINENT")
                else:
                    logging.info(f"[5-MIN] {symbol}: DUMP signal but 5-min NOT breaking (no confirmation)")
                return confirmed

            return True

        except Exception as e:
            logging.warning(f"[5-MIN CONFIRM] Failed for {symbol}: {e}")
            return True  # On error, allow trade (don't block)

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

                    # NEW: Kaufman Efficiency Ratio (KER) - The "Clean Trend" Detector
                    # Period 10
                    try:
                        closes = df_15m['close'].values
                        change = abs(closes[-1] - closes[-11]) # Net move
                        # Sum of absolute period-to-period changes (Volatility)
                        volatility = sum(abs(closes[i] - closes[i-1]) for i in range(-10, 0)) 
                        efficiency_ratio = change / volatility if volatility != 0 else 0
                    except:
                        efficiency_ratio = 0.5

                    # NEW: Volume Z-Score (Sigma) - Statistical Anomaly
                    try:
                        vol_series = df_15m['volume']
                        vol_mean = vol_series.rolling(window=20).mean().iloc[-1]
                        vol_std = vol_series.rolling(window=20).std().iloc[-1]
                        vol_z_score = (vol_series.iloc[-1] - vol_mean) / vol_std if vol_std > 0 else 0
                    except:
                        vol_z_score = 0

                    # FILTER LOGIC (QUALITY CONTROL):
                    # 1. Reject Messy/Choppy Price Action (ER < 0.25)
                    # Unless it's a Squeeze (Accumulation is often messy)
                    if efficiency_ratio < 0.25 and not is_squeeze:
                         return None

                    # 2. Reject Dead Coins (Vol < 0.5x Avg) UNLESS Squeeze
                    if vol_ratio < 0.5 and not is_squeeze:
                        return None
                    
                    # 3. Reject EXTREMELY Low Volatility (ATR < 0.15%)
                    if atr_pct < 0.15:
                         return None
                    
                    # E. Scoring System (Updated with Quant Metrics)
                    score = 0
                    
                    # 1. ALPHA: Squeeze (Accumulation)
                    if is_squeeze:
                         score += 40
                         if vol_z_score > 2.0: score += 30 # Squeeze + Volume Anomaly = JACKPOT
                    
                    # 2. TREND QUALITY: Efficiency Ratio
                    if efficiency_ratio > 0.7:
                        score += 40 # Super Smooth trend
                    elif efficiency_ratio > 0.5:
                        score += 20 # Bonus for Clean Trend (Easy to trade)
                    
                    # 3. MOMENTUM: RSI Extremes
                    if rsi_val < 35 and major_trend == "BULL": score += 15
                    elif rsi_val > 65 and major_trend == "BEAR": score += 15
                        
                    # 4. STATISTICAL ANOMALY: Volume Z-Score
                    if vol_z_score > 3.0: # 3 Sigma Event (99.7% Rare)
                        score += 35 
                    
                    # Baseline
                    score += (vol_ratio * 5)
                    score += (adx_val / 5)

                    if score > 15:
                        result = cand.copy()
                        result['score'] = score
                        result['rsi'] = rsi_val
                        result['trend'] = major_trend
                        result['vol_ratio'] = vol_ratio
                        result['vol_z_score'] = vol_z_score
                        result['is_squeeze'] = is_squeeze
                        result['adx'] = adx_val
                        result['atr_pct'] = atr_pct
                        result['efficiency_ratio'] = efficiency_ratio

                        # WHALE DETECTION (NEW v4.2)
                        # Get whale signal for this candidate
                        if HAS_WHALE_DETECTOR:
                            try:
                                whale_data = get_whale_signal_sync(symbol, current_price)
                                result['whale_signal'] = whale_data.get('whale_signal', 'NEUTRAL')
                                result['whale_confidence'] = whale_data.get('whale_confidence', 0)
                                result['liquidation_pressure'] = whale_data.get('liquidation_pressure', 'NONE')
                                result['order_imbalance'] = whale_data.get('order_imbalance', 0)
                                result['large_trades_bias'] = whale_data.get('large_trades_bias', 'MIXED')

                                # BOOST SCORE for strong whale signals (Tier 3: Progressive Scoring)
                                whale_sig = result['whale_signal']
                                whale_conf = result['whale_confidence']
                                whale_boost = 0

                                # Tier 2: 5-Minute Confirmation Check (Optional 2 enhancement)
                                # Only check for strong PUMP/DUMP signals to confirm entry timing
                                if whale_sig in ['PUMP_IMMINENT', 'DUMP_IMMINENT']:
                                    m5_confirmed = self.check_5min_confirmation(symbol, whale_sig)
                                    result['5min_confirmed'] = m5_confirmed
                                    if not m5_confirmed:
                                        logging.info(f"[5-MIN] {symbol}: {whale_sig} signal rejected - 5-min confirmation failed")
                                        result['whale_signal'] = 'NEUTRAL'  # Downgrade to neutral
                                        whale_sig = 'NEUTRAL'
                                        whale_conf = 0
                                else:
                                    result['5min_confirmed'] = True

                                # Tier 3: Progressive Whale Scoring (non-linear, confidence-based)
                                if whale_sig in ['PUMP_IMMINENT', 'DUMP_IMMINENT']:
                                    # Scale from +25 (60% conf) to +50 (95% conf)
                                    # Formula: 25 + (confidence - 60) * 0.5
                                    if whale_conf >= 60:
                                        whale_boost = min(50, 25 + int((whale_conf - 60) * 0.5))
                                        logging.info(f"[WHALE] {symbol}: {whale_sig} detected + 5-min confirmed! Progressive boost +{whale_boost} (conf: {whale_conf}%)")
                                elif whale_sig in ['SQUEEZE_LONGS', 'SQUEEZE_SHORTS']:
                                    # Scale from +10 (50% conf) to +25 (80% conf)
                                    # Formula: 10 + (confidence - 50) * 0.5
                                    if whale_conf >= 50:
                                        whale_boost = min(25, 10 + int((whale_conf - 50) * 0.3))
                                        logging.info(f"[WHALE] {symbol}: {whale_sig} detected! Progressive boost +{whale_boost} (conf: {whale_conf}%)")

                                result['score'] += whale_boost
                            except Exception as e:
                                logging.warning(f"[WHALE] Detection failed for {symbol}: {e}")
                                result['whale_signal'] = 'NEUTRAL'
                                result['whale_confidence'] = 0
                                result['liquidation_pressure'] = 'NONE'
                                result['order_imbalance'] = 0
                                result['large_trades_bias'] = 'MIXED'
                        else:
                            # No whale detector available
                            result['whale_signal'] = 'NEUTRAL'
                            result['whale_confidence'] = 0
                            result['liquidation_pressure'] = 'NONE'
                            result['order_imbalance'] = 0
                            result['large_trades_bias'] = 'MIXED'

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
