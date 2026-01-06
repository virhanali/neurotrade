"""
Market Screener Service (v4.5)
Scans Binance Futures market for high-volume, volatile opportunities
Enhanced with Whale Detection (Liquidation + Order Book Analysis)
NEW: OHLCV Caching + Circuit Breaker for reliability
"""

import ccxt
import logging
import pandas as pd
import ta
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from functools import lru_cache
from config import settings

# Import Whale Detector
try:
    from services.whale_detector import get_whale_signal_sync
    HAS_WHALE_DETECTOR = True
except ImportError:
    HAS_WHALE_DETECTOR = False
    logging.warning("[SCREENER] Whale detector not available")


class CircuitBreaker:
    """
    Circuit Breaker Pattern - Prevents cascading failures when API is down.
    States: CLOSED (normal) -> OPEN (blocked) -> HALF-OPEN (testing)
    """
    def __init__(self, failure_threshold: int = 5, recovery_time: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"
        self._lock = threading.Lock()
    
    def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        with self._lock:
            # Check if circuit is OPEN
            if self.state == "OPEN":
                if time.time() - self.last_failure_time > self.recovery_time:
                    self.state = "HALF-OPEN"
                    logging.info("[CIRCUIT] State changed to HALF-OPEN (testing recovery)")
                else:
                    remaining = int(self.recovery_time - (time.time() - self.last_failure_time))
                    raise Exception(f"Circuit OPEN - API disabled for {remaining}s")
        
        try:
            result = func(*args, **kwargs)
            with self._lock:
                self.failures = 0
                if self.state == "HALF-OPEN":
                    self.state = "CLOSED"
                    logging.info("[CIRCUIT] State changed to CLOSED (recovered)")
            return result
        except Exception as e:
            with self._lock:
                self.failures += 1
                if self.failures >= self.failure_threshold:
                    self.state = "OPEN"
                    self.last_failure_time = time.time()
                    logging.error(f"[CIRCUIT] State changed to OPEN after {self.failures} failures")
            raise e
    
    def reset(self):
        """Manually reset circuit breaker"""
        with self._lock:
            self.failures = 0
            self.state = "CLOSED"
            logging.info("[CIRCUIT] Manually reset to CLOSED")


class OHLCVCache:
    """
    Hybrid cache for OHLCV data - Redis primary, in-memory fallback.
    15m data cached for 60s, 4h data cached for 300s.
    """
    def __init__(self):
        self._memory_cache = {}
        self._lock = threading.Lock()
        self._ttl = {
            '1m': 30,
            '5m': 60,
            '15m': 60,
            '1h': 300,
            '4h': 300,
        }
        self._redis = None
        self._use_redis = False
        
        # Try to init Redis
        try:
            from services.redis_cache import get_cache
            self._redis = get_cache()
            self._use_redis = self._redis._use_redis
            if self._use_redis:
                logging.info("[CACHE] OHLCVCache using Redis backend")
        except Exception as e:
            logging.info(f"[CACHE] OHLCVCache using memory-only ({e})")
    
    def get(self, symbol: str, timeframe: str) -> Optional[List]:
        """Get cached OHLCV data if not expired"""
        key = f"ohlcv:{symbol}:{timeframe}"
        
        # Try Redis first
        if self._use_redis and self._redis:
            try:
                data = self._redis.get(key)
                if data:
                    return data
            except Exception:
                pass
        
        # Fallback to memory
        with self._lock:
            if key in self._memory_cache:
                data, timestamp = self._memory_cache[key]
                ttl = self._ttl.get(timeframe, 60)
                if time.time() - timestamp < ttl:
                    return data
                else:
                    del self._memory_cache[key]
        return None
    
    def set(self, symbol: str, timeframe: str, data: List):
        """Cache OHLCV data"""
        key = f"ohlcv:{symbol}:{timeframe}"
        ttl = self._ttl.get(timeframe, 60)
        
        # Try Redis first
        if self._use_redis and self._redis:
            try:
                self._redis.set(key, data, ttl)
            except Exception:
                pass
        
        # Also store in memory (fast local access)
        with self._lock:
            self._memory_cache[key] = (data, time.time())
    
    def stats(self) -> Dict:
        """Return cache statistics"""
        stats = {
            "backend": "redis" if self._use_redis else "memory",
            "memory_keys": len(self._memory_cache)
        }
        if self._use_redis and self._redis:
            try:
                redis_stats = self._redis.stats()
                stats.update(redis_stats)
            except Exception:
                pass
        return stats
    
    def clear(self):
        """Clear all cached data"""
        if self._use_redis and self._redis:
            try:
                self._redis.clear_pattern("ohlcv:*")
            except Exception:
                pass
        with self._lock:
            self._memory_cache.clear()


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
        
        # NEW: Initialize cache and circuit breaker
        self.ohlcv_cache = OHLCVCache()
        self.circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_time=60)
    
    def fetch_ohlcv_cached(self, symbol: str, timeframe: str, limit: int) -> Optional[List]:
        """
        Fetch OHLCV data with caching and circuit breaker protection.
        Returns None if circuit is open or fetch fails.
        """
        # 1. Check cache first
        cached = self.ohlcv_cache.get(symbol, timeframe)
        if cached is not None:
            return cached
        
        # 2. Fetch from API with circuit breaker
        try:
            data = self.circuit_breaker.call(
                self.exchange.fetch_ohlcv,
                symbol, timeframe, None, limit
            )
            if data:
                self.ohlcv_cache.set(symbol, timeframe, data)
            return data
        except Exception as e:
            logging.warning(f"[CACHE] Failed to fetch {symbol} {timeframe}: {e}")
            return None

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
                    # 1. Fetch 15m Data (Tactical) - WITH CACHE
                    ohlcv_15m = self.fetch_ohlcv_cached(symbol, '15m', 50)
                    if not ohlcv_15m or len(ohlcv_15m) < 50: 
                        return None
                    df_15m = pd.DataFrame(ohlcv_15m, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    
                    # 2. Fetch 4h Data (Strategic Trend) - WITH CACHE
                    ohlcv_4h = self.fetch_ohlcv_cached(symbol, '4h', 200)
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
                    
                    is_squeeze = bool(bb_width < 0.02)  # Less than 2% width = SQUEEZE

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
                        # Convert all numpy types to native Python types for JSON serialization
                        result['score'] = float(score)
                        result['rsi'] = float(rsi_val) if rsi_val is not None else 50.0
                        result['trend'] = major_trend
                        result['vol_ratio'] = float(vol_ratio)
                        result['vol_z_score'] = float(vol_z_score)
                        result['is_squeeze'] = is_squeeze  # Already bool from above
                        result['adx'] = float(adx_val)
                        result['atr_pct'] = float(atr_pct)
                        result['efficiency_ratio'] = float(efficiency_ratio)

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

                                result['score'] = float(result['score'] + whale_boost)
                            except Exception as e:
                                logging.warning(f"[WHALE] Detection failed for {symbol}: {e}")
                                result['whale_signal'] = 'NEUTRAL'
                                result['whale_confidence'] = 0
                                result['liquidation_pressure'] = 'NONE'
                                result['order_imbalance'] = 0.0
                                result['large_trades_bias'] = 'MIXED'
                        else:
                            # No whale detector available
                            result['whale_signal'] = 'NEUTRAL'
                            result['whale_confidence'] = 0
                            result['liquidation_pressure'] = 'NONE'
                            result['order_imbalance'] = 0.0
                            result['large_trades_bias'] = 'MIXED'

                        # Ensure all numeric values are native Python types
                        result['whale_confidence'] = int(result.get('whale_confidence', 0))
                        result['order_imbalance'] = float(result.get('order_imbalance', 0))
                        if '5min_confirmed' in result:
                            result['5min_confirmed'] = bool(result['5min_confirmed'])

                        # NEW v4.5: Compute suggested_direction (pre-hint for AI)
                        # Priority: Whale Signal > RSI + Trend
                        suggested_direction = "NEUTRAL"
                        whale_sig_final = result.get('whale_signal', 'NEUTRAL')
                        
                        # 1. Whale signal has highest priority
                        if whale_sig_final == 'PUMP_IMMINENT':
                            suggested_direction = "LONG"
                        elif whale_sig_final == 'DUMP_IMMINENT':
                            suggested_direction = "SHORT"
                        elif whale_sig_final == 'SQUEEZE_LONGS':
                            suggested_direction = "SHORT"  # Avoid longs, lean short
                        elif whale_sig_final == 'SQUEEZE_SHORTS':
                            suggested_direction = "LONG"   # Avoid shorts, lean long
                        else:
                            # 2. Fallback to RSI + Trend confluence
                            rsi = result.get('rsi', 50)
                            trend = result.get('trend', 'NEUTRAL')
                            
                            if rsi < 35 and trend == "BULL":
                                suggested_direction = "LONG"  # Oversold in uptrend
                            elif rsi > 65 and trend == "BEAR":
                                suggested_direction = "SHORT"  # Overbought in downtrend
                            elif rsi < 30:
                                suggested_direction = "LONG"  # Extreme oversold
                            elif rsi > 70:
                                suggested_direction = "SHORT"  # Extreme overbought
                        
                        result['suggested_direction'] = suggested_direction
                        
                        if suggested_direction != "NEUTRAL":
                            logging.info(f"[DIRECTION] {symbol}: {suggested_direction} (whale={whale_sig_final}, rsi={result.get('rsi', 0):.1f}, trend={result.get('trend')})")

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

    def scan_pump_candidates(self) -> List[Dict]:
        """
        Low-Cap Pump Scanner - Detects early pump signals on lower volume coins.

        Detection Criteria:
        1. Volume Surge: Current volume > 10x average (extreme activity)
        2. Price Spike: >5% move in last 3 candles (momentum)
        3. Low-Cap Filter: $1M < 24h Volume < $50M (not too illiquid, not whale territory)
        4. Breakout Pattern: Price breaking recent high with volume

        Returns:
            List of pump candidates with metrics
        """
        try:
            from services.price_stream import price_stream

            # Get ticker data
            raw_tickers = {}
            if price_stream.is_connected and len(price_stream.get_all_tickers()) > 100:
                raw_tickers = price_stream.get_all_tickers()
                source = "WEBSOCKET"
            else:
                if not self.exchange.markets:
                    self.exchange.load_markets()
                raw_tickers = self.exchange.fetch_tickers()
                source = "REST"

            # Pre-filter: Low-cap coins with some movement
            low_cap_candidates = []
            for symbol, ticker in raw_tickers.items():
                # Parse symbol
                if source == "WEBSOCKET":
                    if not symbol.endswith("USDT"):
                        continue
                    base = symbol[:-4]
                    clean_symbol = f"{base}/USDT"
                else:
                    if not symbol.endswith("/USDT:USDT"):
                        continue
                    clean_symbol = symbol.replace(":USDT", "")

                quote_volume = ticker.get('quoteVolume', 0) or 0
                pct_change = ticker.get('percentage', 0) or 0

                # Low-cap filter: $1M - $50M volume AND showing some movement (>2%)
                if 1_000_000 < quote_volume < 50_000_000 and abs(pct_change) > 2:
                    low_cap_candidates.append({
                        'symbol': clean_symbol,
                        'volume_24h': quote_volume,
                        'pct_change_24h': pct_change,
                    })

            # Sort by volatility (biggest movers first)
            low_cap_candidates.sort(key=lambda x: abs(x['pct_change_24h']), reverse=True)
            candidates = low_cap_candidates[:50]  # Check top 50 movers

            if not candidates:
                return []

            logging.info(f"[PUMP SCAN] Checking {len(candidates)} low-cap candidates...")

            def analyze_pump(cand: Dict) -> Optional[Dict]:
                """Analyze single candidate for pump signals"""
                symbol = cand['symbol']
                try:
                    # Fetch 5-minute candles (fast timeframe for pump detection)
                    ohlcv = self.exchange.fetch_ohlcv(symbol, '5m', limit=30)
                    if not ohlcv or len(ohlcv) < 20:
                        return None

                    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

                    # Calculate metrics
                    current_vol = df['volume'].iloc[-1]
                    avg_vol = df['volume'].iloc[:-1].mean()  # Exclude current candle
                    vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0

                    # Price change in last 3 candles
                    price_3_ago = df['close'].iloc[-4]
                    current_price = df['close'].iloc[-1]
                    pct_change_3c = ((current_price - price_3_ago) / price_3_ago) * 100 if price_3_ago > 0 else 0

                    # Recent high/low for breakout detection
                    recent_high = df['high'].iloc[-10:-1].max()  # High of last 9 candles (excluding current)
                    recent_low = df['low'].iloc[-10:-1].min()

                    # Breakout detection
                    is_breakout_up = current_price > recent_high
                    is_breakout_down = current_price < recent_low

                    # PUMP DETECTION CRITERIA
                    pump_score = 0
                    pump_signals = []

                    # 1. Volume Surge (Critical)
                    if vol_ratio >= 10:
                        pump_score += 50
                        pump_signals.append(f"VOL_SURGE_{vol_ratio:.1f}x")
                    elif vol_ratio >= 5:
                        pump_score += 30
                        pump_signals.append(f"VOL_HIGH_{vol_ratio:.1f}x")
                    elif vol_ratio >= 3:
                        pump_score += 15
                        pump_signals.append(f"VOL_ELEVATED_{vol_ratio:.1f}x")

                    # 2. Price Momentum (Important)
                    if abs(pct_change_3c) >= 10:
                        pump_score += 40
                        pump_signals.append(f"MOMENTUM_{pct_change_3c:+.1f}%")
                    elif abs(pct_change_3c) >= 5:
                        pump_score += 25
                        pump_signals.append(f"MOVE_{pct_change_3c:+.1f}%")
                    elif abs(pct_change_3c) >= 3:
                        pump_score += 10
                        pump_signals.append(f"SHIFT_{pct_change_3c:+.1f}%")

                    # 3. Breakout Confirmation
                    if is_breakout_up and pct_change_3c > 0:
                        pump_score += 20
                        pump_signals.append("BREAKOUT_UP")
                    elif is_breakout_down and pct_change_3c < 0:
                        pump_score += 20
                        pump_signals.append("BREAKOUT_DOWN")

                    # Minimum score threshold
                    if pump_score < 50:
                        return None

                    # Determine pump type
                    if pct_change_3c > 0:
                        pump_type = "PUMP"
                    else:
                        pump_type = "DUMP"

                    # === DUMP RISK SCORE (0-100) ===
                    # Higher = More likely to dump (risky for LONG, good for SHORT)
                    dump_risk = 0
                    risk_signals = []

                    # 1. Parabolic Rate Detection (>5% per candle = unsustainable)
                    avg_change_per_candle = abs(pct_change_3c) / 3
                    if avg_change_per_candle > 5:
                        dump_risk += 30
                        risk_signals.append("PARABOLIC")
                    elif avg_change_per_candle > 3:
                        dump_risk += 15
                        risk_signals.append("STEEP")

                    # 2. Single Candle Volume Concentration (manipulation signal)
                    max_vol = df['volume'].iloc[-5:].max()
                    avg_vol_5 = df['volume'].iloc[-5:].mean()
                    vol_concentration = max_vol / avg_vol_5 if avg_vol_5 > 0 else 1
                    if vol_concentration > 3:  # One candle has 3x the average of last 5
                        dump_risk += 25
                        risk_signals.append("VOL_SPIKE_SINGLE")
                    elif vol_concentration > 2:
                        dump_risk += 10
                        risk_signals.append("VOL_CONCENTRATED")

                    # 3. Position in Range (at high = dump risk, at low = bounce risk)
                    range_high = df['high'].iloc[-30:].max()
                    range_low = df['low'].iloc[-30:].min()
                    range_size = range_high - range_low
                    if range_size > 0:
                        position_in_range = (current_price - range_low) / range_size
                        if position_in_range > 0.9:  # At top of range
                            dump_risk += 25
                            risk_signals.append("AT_RANGE_TOP")
                        elif position_in_range > 0.75:
                            dump_risk += 10
                            risk_signals.append("NEAR_TOP")
                        elif position_in_range < 0.1:  # At bottom = might bounce
                            dump_risk -= 15
                            risk_signals.append("AT_RANGE_BOTTOM")

                    # 4. 24h Trend Context (negative 24h = weak coin)
                    if cand['pct_change_24h'] < -5:
                        dump_risk += 15
                        risk_signals.append("WEAK_24H")
                    elif cand['pct_change_24h'] > 10:
                        dump_risk += 10  # Extended = pullback likely
                        risk_signals.append("EXTENDED_24H")

                    # Clamp to 0-100
                    dump_risk = max(0, min(100, dump_risk))

                    # Trade recommendation based on type and risk
                    if pump_type == "PUMP":
                        if dump_risk >= 60:
                            trade_action = "AVOID_LONG"  # Too risky, likely to dump
                        elif dump_risk >= 40:
                            trade_action = "CAUTIOUS_LONG"  # Entry with tight SL
                        else:
                            trade_action = "LONG"  # Good entry
                    else:  # DUMP
                        if dump_risk >= 50:
                            trade_action = "SHORT"  # Good short opportunity
                        elif dump_risk >= 30:
                            trade_action = "CAUTIOUS_SHORT"
                        else:
                            trade_action = "AVOID_SHORT"  # Might bounce

                    return {
                        'symbol': symbol,
                        'pump_type': pump_type,
                        'pump_score': int(pump_score),
                        'signals': pump_signals,
                        'vol_ratio': float(round(vol_ratio, 1)),
                        'pct_change_3c': float(round(pct_change_3c, 2)),
                        'pct_change_24h': float(round(cand['pct_change_24h'], 2)),
                        'volume_24h': float(round(cand['volume_24h'] / 1_000_000, 2)),
                        'current_price': float(current_price),
                        'breakout': 'UP' if is_breakout_up else ('DOWN' if is_breakout_down else 'NONE'),
                        'dump_risk': int(dump_risk),
                        'risk_signals': risk_signals,
                        'trade_action': trade_action,
                    }

                except Exception as e:
                    return None

            # Parallel analysis (5 threads to be gentle on API)
            pump_alerts = []
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = {executor.submit(analyze_pump, cand): cand for cand in candidates}
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        pump_alerts.append(result)

            # Sort by pump score
            pump_alerts.sort(key=lambda x: x['pump_score'], reverse=True)

            # Log detected pumps with trade action
            for alert in pump_alerts[:5]:  # Log top 5
                logging.info(
                    f"[PUMP ALERT] {alert['symbol']}: {alert['pump_type']} → {alert['trade_action']} "
                    f"Score={alert['pump_score']} DumpRisk={alert['dump_risk']}% Vol={alert['vol_ratio']}x "
                    f"Move={alert['pct_change_3c']:+.1f}% Risk={alert['risk_signals']}"
                )

            return pump_alerts

        except Exception as e:
            logging.error(f"[PUMP SCAN] Error: {e}")
            return []
