"""
Market Screener Service
Scans Binance Futures market for trading opportunities with multi-timeframe analysis.
"""

import ccxt
import logging
import pandas as pd
import numpy as np
import ta
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from functools import lru_cache
from config import settings
import math

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
        
        # Session for direct Binance API calls (non-CCXT)
        self.session = session
    
    def calculate_efficiency_ratio(self, closes: np.array, period: int = 10) -> float:
        """
        Calculate Kaufman Efficiency Ratio (KER) / Fractal Efficiency.
        ER = Direction / Volatility
        Range: 0.0 (Choppy) to 1.0 (Smooth Trend).
        > 0.3 usually indicates a tradeable trend.
        """
        if len(closes) < period + 1:
            return 0.0
        
        # Direction: Net change over period
        direction = abs(closes[-1] - closes[-period-1])
        
        # Volatility: Sum of absolute changes candle-to-candle
        volatility = np.sum(np.abs(np.diff(closes[-period-1:])))
        
        if volatility == 0:
            return 0.0
            
        return direction / volatility

    def calculate_hurst_exponent(self, closes: np.array, min_window: int = 10) -> float:
        """
        Calculate Hurst Exponent (H) to detect Market Regime.
        H < 0.5: Mean Reverting ( choppy / range-bound ) -> Ideal for RSI Reversal
        H ~ 0.5: Random Walk ( unpredictable noise ) -> AVOID
        H > 0.5: Trending ( persistent ) -> Ideal for Breakouts / Momentum
        
        Using simplified R/S analysis suitable for shorter timeframes.
        """
        try:
            if len(closes) < min_window * 2:
                return 0.5
            
            # Use log-returns for stationarity
            log_returns = np.diff(np.log(closes))
            
            # Simple R/S analysis on varying window sizes
            # We split the data into chunks and calc R/S
            # This is a simplified "scalar" Hurst for speed (not full fractal dim)
            
            # Check 3 different lags to estimate H
            lags = range(2, 20)
            tau = []
            lagvec = []
            
            for lag in lags:
                # Calculate Price difference (Volatility at lag)
                pp = np.subtract(closes[lag:], closes[:-lag])
                lagvec.append(lag)
                tau.append(np.sqrt(np.std(pp)))
            
            # Slope of log(tau) vs log(lag) approximates H
            # H = log(sigma) / log(time_lag)
            if len(lagvec) < 2 or len(tau) < 2:
                return 0.5
                
            m = np.polyfit(np.log(lagvec), np.log(tau), 1)
            hurst = m[0] * 2.0 # Adjusted for standard price series (non-integrated)
            
            # Clamp result
            return max(0.0, min(1.0, hurst))
            
        except Exception as e:
            # logging.warning(f"[HURST] Error: {e}")
            return 0.5

    def calculate_volume_z_score(self, volumes: np.array, window: int = 20) -> float:
        """
        Calculate Volume Z-Score (Standard Deviations from mean).
        Z > 3.0 implies statistically significant outlier (Whale/Breakout).
        """
        if len(volumes) < window:
            return 0.0
            
        recent_vol = volumes[-window:]
        mean = np.mean(recent_vol)
        std = np.std(recent_vol)
        
        if std == 0:
            return 0.0
            
        current_vol = volumes[-1]
        z_score = (current_vol - mean) / std
        return z_score
    
    def fetch_market_sentiment(self, symbol: str) -> Dict:
        """
        Fetch market sentiment data from Binance Futures API.
        Combines: Open Interest, Top Trader Positions, Taker Buy/Sell Volume, Funding Rate.
        """
        binance_symbol = symbol.replace("/", "")
        base_url = "https://fapi.binance.com"
        
        result = {
            'oi_change_pct': 0,
            'top_trader_long_ratio': 50,
            'taker_buy_ratio': 50,
            'funding_rate': 0,
            'sentiment_score': 0,
            'sentiment_signal': 'NEUTRAL',
            'funding_bias': 'NEUTRAL'
        }
        
        try:
            # 1. Open Interest
            try:
                oi_resp = self.session.get(
                    f"{base_url}/fapi/v1/openInterest",
                    params={"symbol": binance_symbol},
                    timeout=3
                )
                if oi_resp.status_code == 200:
                    current_oi = float(oi_resp.json().get('openInterest', 0))
                    oi_hist_resp = self.session.get(
                        f"{base_url}/futures/data/openInterestHist",
                        params={"symbol": binance_symbol, "period": "5m", "limit": 2},
                        timeout=3
                    )
                    if oi_hist_resp.status_code == 200 and oi_hist_resp.json():
                        hist_data = oi_hist_resp.json()
                        if len(hist_data) >= 2:
                            prev_oi = float(hist_data[-2].get('sumOpenInterest', current_oi))
                            if prev_oi > 0:
                                result['oi_change_pct'] = ((current_oi - prev_oi) / prev_oi) * 100
            except Exception as e:
                logging.debug(f"[SENTIMENT] OI fetch failed for {symbol}: {e}")
            
            # 2. Top Trader Long/Short Ratio
            try:
                top_resp = self.session.get(
                    f"{base_url}/futures/data/topLongShortPositionRatio",
                    params={"symbol": binance_symbol, "period": "5m", "limit": 1},
                    timeout=3
                )
                if top_resp.status_code == 200 and top_resp.json():
                    data = top_resp.json()[0]
                    result['top_trader_long_ratio'] = float(data.get('longAccount', 50)) * 100
            except Exception as e:
                logging.debug(f"[SENTIMENT] Top Trader fetch failed for {symbol}: {e}")
            
            # 3. Taker Buy/Sell Ratio
            try:
                taker_resp = self.session.get(
                    f"{base_url}/futures/data/takerlongshortRatio",
                    params={"symbol": binance_symbol, "period": "5m", "limit": 1},
                    timeout=3
                )
                if taker_resp.status_code == 200 and taker_resp.json():
                    data = taker_resp.json()[0]
                    buy_vol = float(data.get('buyVol', 1))
                    sell_vol = float(data.get('sellVol', 1))
                    total = buy_vol + sell_vol
                    result['taker_buy_ratio'] = (buy_vol / total) * 100 if total > 0 else 50
            except Exception as e:
                logging.debug(f"[SENTIMENT] Taker fetch failed for {symbol}: {e}")
            
            # 4. Funding Rate (NEW)
            try:
                funding_resp = self.session.get(
                    f"{base_url}/fapi/v1/fundingRate",
                    params={"symbol": binance_symbol, "limit": 1},
                    timeout=3
                )
                if funding_resp.status_code == 200 and funding_resp.json():
                    data = funding_resp.json()[0]
                    result['funding_rate'] = float(data.get('fundingRate', 0)) * 100  # Convert to %
                    
                    # Funding bias: Extreme funding = contrarian signal
                    if result['funding_rate'] > 0.05:
                        result['funding_bias'] = 'SHORT_BIAS'  # Too many longs, expect dump
                    elif result['funding_rate'] < -0.05:
                        result['funding_bias'] = 'LONG_BIAS'   # Too many shorts, expect pump
                    else:
                        result['funding_bias'] = 'NEUTRAL'
            except Exception as e:
                logging.debug(f"[SENTIMENT] Funding fetch failed for {symbol}: {e}")
            
            # Calculate combined sentiment score
            oi_factor = min(10, max(-10, result['oi_change_pct'] * 5))
            top_factor = (result['top_trader_long_ratio'] - 50) * 1.5
            taker_factor = (result['taker_buy_ratio'] - 50) * 1.0
            
            # Funding contrarian: positive funding = bearish pressure, negative = bullish
            funding_factor = -result['funding_rate'] * 50  # -0.1% funding = +5 bullish
            
            sentiment = (taker_factor * 0.35) + (top_factor * 0.35) + (oi_factor * 0.15) + (funding_factor * 0.15)
            result['sentiment_score'] = max(-100, min(100, sentiment))
            
            if result['sentiment_score'] > 20:
                result['sentiment_signal'] = 'BULLISH'
            elif result['sentiment_score'] < -20:
                result['sentiment_signal'] = 'BEARISH'
            else:
                result['sentiment_signal'] = 'NEUTRAL'
            
            logging.debug(f"[SENTIMENT] {symbol}: OI={result['oi_change_pct']:.2f}%, "
                        f"Funding={result['funding_rate']:.4f}%, "
                        f"Score={result['sentiment_score']:.0f} ({result['sentiment_signal']})")
            
        except Exception as e:
            logging.warning(f"[SENTIMENT] Failed for {symbol}: {e}")
        
        return result
    
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

    def check_1h_confirmation(self, symbol: str, direction: str) -> tuple:
        """
        Check if 1H timeframe confirms the suggested direction. Returns (confirmed, reason).
        UPDATED: More flexible for trend reversals and crypto futures trading.
        """
        try:
            ohlcv = self.fetch_ohlcv_cached(symbol, '1h', 20)
            if not ohlcv or len(ohlcv) < 15:
                return True, "Insufficient 1H data (allowing trade)"

            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # Calculate 1H indicators
            ema_9 = ta.trend.ema_indicator(df['close'], window=9).iloc[-1]
            ema_21 = ta.trend.ema_indicator(df['close'], window=21).iloc[-1]
            current_price = df['close'].iloc[-1]
            rsi_1h = ta.momentum.rsi(df['close'], window=14).iloc[-1]

            # Calculate MACD for momentum confirmation
            try:
                macd_ind = ta.trend.MACD(close=df['close'], window_slow=26, window_fast=12, window_sign=9)
                macd_1h = macd_ind.macd().iloc[-1]
                macd_signal_1h = macd_ind.macd_signal().iloc[-1]
                macd_bearish_1h = macd_1h < macd_signal_1h
                macd_bullish_1h = macd_1h > macd_signal_1h
            except:
                macd_bearish_1h = False
                macd_bullish_1h = False

            # Trend direction from EMAs
            ema_bullish = ema_9 > ema_21 and current_price > ema_9
            ema_bearish = ema_9 < ema_21 and current_price < ema_9
            ema_neutral = not ema_bullish and not ema_bearish

            if direction == "LONG":
                # For LONG: Only VETO if 1H is STRONGLY bearish (not just slightly bearish)
                # OLD: Blocked if ema_bearish and rsi_1h < 40
                # NEW: Only block if EXTREME bearish confluence
                if ema_bearish and rsi_1h < 35 and macd_bearish_1h:
                    # All three bearish = very strong downtrend, avoid longs
                    return False, f"1H EXTREME BEARISH (EMA-, RSI={rsi_1h:.1f}, MACD-)"
                elif rsi_1h < 30:  # Extreme oversold = reversal opportunity
                    return True, f"1H Extreme Oversold Reversal (RSI={rsi_1h:.1f})"
                elif ema_bullish:
                    return True, f"1H BULLISH confirmation (EMA9>EMA21, RSI={rsi_1h:.1f})"
                elif ema_neutral or rsi_1h > 40:
                    # Neutral 1H or RSI not extreme = allow 15M signal
                    return True, f"1H Neutral/Weak bearish (RSI={rsi_1h:.1f}) - allowing 15M LONG"
                else:
                    # Mild bearish on 1H = allow trade with reduced confidence (penalty applied separately)
                    return True, f"1H Mild bearish (RSI={rsi_1h:.1f}) - 15M signal priority"

            elif direction == "SHORT":
                # For SHORT: Only VETO if 1H is STRONGLY bullish (not just slightly bullish)
                # OLD: Blocked if ema_bullish and rsi_1h > 60
                # NEW: Only block if EXTREME bullish confluence
                if ema_bullish and rsi_1h > 65 and macd_bullish_1h:
                    # All three bullish = very strong uptrend, avoid shorts
                    return False, f"1H EXTREME BULLISH (EMA+, RSI={rsi_1h:.1f}, MACD+)"
                elif rsi_1h > 70:  # Extreme overbought = reversal opportunity
                    return True, f"1H Extreme Overbought Reversal (RSI={rsi_1h:.1f})"
                elif ema_bearish:
                    return True, f"1H BEARISH confirmation (EMA9<EMA21, RSI={rsi_1h:.1f})"
                elif ema_neutral or rsi_1h < 60:
                    # Neutral 1H or RSI not extreme = allow 15M signal
                    return True, f"1H Neutral/Weak bullish (RSI={rsi_1h:.1f}) - allowing 15M SHORT"
                else:
                    # Mild bullish on 1H = allow trade with reduced confidence (penalty applied separately)
                    return True, f"1H Mild bullish (RSI={rsi_1h:.1f}) - 15M signal priority"

            return True, "1H Check passed"

        except Exception as e:
            logging.warning(f"[1H CONFIRM] Failed for {symbol}: {e}")
            return True, f"1H check error: {e}"

    def detect_early_reversal(self, df_15m: pd.DataFrame, df_1h: pd.DataFrame) -> dict:
        """
        Detect early reversal phase when 15M is reversing but 1H hasn't confirmed yet.
        This helps prioritize 15M signals during trend transitions.

        Returns dict with:
        - is_early_reversal: bool
        - reversal_type: 'BULLISH' | 'BEARISH' | 'NONE'
        - confidence: 0-100
        - signals: list of detection signals
        """
        try:
            if len(df_15m) < 20 or len(df_1h) < 10:
                return {'is_early_reversal': False, 'reversal_type': 'NONE', 'confidence': 0, 'signals': []}

            signals = []
            reversal_score = 0
            reversal_type = 'NONE'

            # Get 15M indicators
            price_15m = df_15m['close'].iloc[-1]
            rsi_15m = ta.momentum.rsi(df_15m['close'], window=14).iloc[-1]
            macd_15m = df_15m['macd'].iloc[-1] if 'macd' in df_15m else None
            macd_signal_15m = df_15m['macd_signal'].iloc[-1] if 'macd_signal' in df_15m else None
            macd_diff_15m = df_15m['macd_diff'].iloc[-1] if 'macd_diff' in df_15m else None
            macd_diff_prev_15m = df_15m['macd_diff'].iloc[-2] if 'macd_diff' in df_15m else None

            # Get 1H indicators
            price_1h = df_1h['close'].iloc[-1]
            rsi_1h = ta.momentum.rsi(df_1h['close'], window=14).iloc[-1]
            macd_1h = df_1h['macd'].iloc[-1] if 'macd' in df_1h else None
            macd_signal_1h = df_1h['macd_signal'].iloc[-1] if 'macd_signal' in df_1h else None

            # BULLISH REVERSAL DETECTION
            # 15M showing bullish signs but 1H still bearish = early bullish reversal
            if rsi_15m < 35 and rsi_1h < 45:  # Both oversold/bearish
                # Check if 15M is recovering (MACD turning up)
                if macd_diff_15m is not None and macd_diff_prev_15m is not None:
                    if macd_diff_15m > macd_diff_prev_15m:  # MACD histogram increasing
                        reversal_score += 30
                        signals.append("15M MACD recovering from oversold")
                        reversal_type = 'BULLISH'

                # Check if price making higher lows on 15M
                lows_15m = df_15m['low'].iloc[-5:].values
                if len(lows_15m) >= 3:
                    if lows_15m[-1] > lows_15m[-2] > lows_15m[-3]:
                        reversal_score += 20
                        signals.append("15M higher lows pattern")
                        reversal_type = 'BULLISH'

            # BEARISH REVERSAL DETECTION
            # 15M showing bearish signs but 1H still bullish = early bearish reversal
            elif rsi_15m > 65 and rsi_1h > 55:  # Both overbought/bullish
                # Check if 15M is weakening (MACD turning down)
                if macd_diff_15m is not None and macd_diff_prev_15m is not None:
                    if macd_diff_15m < macd_diff_prev_15m:  # MACD histogram decreasing
                        reversal_score += 30
                        signals.append("15M MACD weakening from overbought")
                        reversal_type = 'BEARISH'

                # Check if price making lower highs on 15M
                highs_15m = df_15m['high'].iloc[-5:].values
                if len(highs_15m) >= 3:
                    if highs_15m[-1] < highs_15m[-2] < highs_15m[-3]:
                        reversal_score += 20
                        signals.append("15M lower highs pattern")
                        reversal_type = 'BEARISH'

            # RSI Divergence Detection (Advanced)
            # Price making new high but RSI making lower high = bearish divergence
            try:
                price_last3 = df_15m['close'].iloc[-3:].values
                rsi_last3 = ta.momentum.rsi(df_15m['close'], window=14).iloc[-3:].values

                if price_last3[-1] > max(price_last3[:-1]) and rsi_last3[-1] < max(rsi_last3[:-1]):
                    reversal_score += 25
                    signals.append("Bearish RSI divergence on 15M")
                    reversal_type = 'BEARISH'
                elif price_last3[-1] < min(price_last3[:-1]) and rsi_last3[-1] > min(rsi_last3[:-1]):
                    reversal_score += 25
                    signals.append("Bullish RSI divergence on 15M")
                    reversal_type = 'BULLISH'
            except:
                pass

            # Confidence calculation
            confidence = min(100, reversal_score)
            is_early_reversal = confidence >= 40  # Need at least 40 confidence

            if is_early_reversal:
                logging.info(f"[EARLY REVERSAL] {reversal_type} detected! Confidence: {confidence}% | Signals: {signals}")

            return {
                'is_early_reversal': is_early_reversal,
                'reversal_type': reversal_type,
                'confidence': confidence,
                'signals': signals
            }

        except Exception as e:
            logging.warning(f"[EARLY REVERSAL] Detection failed: {e}")
            return {'is_early_reversal': False, 'reversal_type': 'NONE', 'confidence': 0, 'signals': []}

    def check_market_structure(self, df_15m: pd.DataFrame) -> dict:
        """Analyze market structure for HH/HL (uptrend) or LH/LL (downtrend)."""
        try:
            if len(df_15m) < 20:
                return {'structure': 'UNKNOWN', 'quality': 50, 'swings': []}
            
            highs = df_15m['high'].values
            lows = df_15m['low'].values
            
            # Find swing highs and lows (last 15 candles)
            swing_highs = []
            swing_lows = []
            
            for i in range(-13, -2):  # Check from -13 to -3 (need neighbors)
                # Swing high: higher than both neighbors
                if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                    swing_highs.append((i, highs[i]))
                # Swing low: lower than both neighbors
                if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                    swing_lows.append((i, lows[i]))
            
            if len(swing_highs) < 2 or len(swing_lows) < 2:
                return {'structure': 'UNCLEAR', 'quality': 40, 'swings': []}
            
            # Analyze last 2 swing highs and lows
            last_high = swing_highs[-1][1]
            prev_high = swing_highs[-2][1]
            last_low = swing_lows[-1][1]
            prev_low = swing_lows[-2][1]
            
            higher_highs = last_high > prev_high
            higher_lows = last_low > prev_low
            lower_highs = last_high < prev_high
            lower_lows = last_low < prev_low
            
            # Determine structure
            structure = 'CHOPPY'
            quality = 30
            
            if higher_highs and higher_lows:
                structure = 'UPTREND'
                quality = 80
            elif lower_highs and lower_lows:
                structure = 'DOWNTREND'
                quality = 80
            elif higher_lows and not higher_highs:
                structure = 'ACCUMULATION'  # Building base
                quality = 60
            elif lower_highs and not lower_lows:
                structure = 'DISTRIBUTION'  # Topping
                quality = 60
            else:
                structure = 'CHOPPY'
                quality = 30
            
            return {
                'structure': structure,
                'quality': quality,
                'higher_highs': higher_highs,
                'higher_lows': higher_lows,
                'last_swing_high': float(last_high),
                'last_swing_low': float(last_low)
            }
            
        except Exception as e:
            logging.warning(f"[STRUCTURE] Analysis failed: {e}")
            return {'structure': 'ERROR', 'quality': 50, 'swings': []}

    def check_sr_proximity(self, df_15m: pd.DataFrame, entry_price: float) -> dict:
        """Check if entry price is too close to support/resistance levels."""
        try:
            if len(df_15m) < 30:
                return {'near_sr': False, 'distance_pct': 999}
            
            # Find recent key levels (last 30 candles)
            recent_high = df_15m['high'].iloc[-30:-1].max()
            recent_low = df_15m['low'].iloc[-30:-1].min()
            
            # Also check Bollinger Bands as dynamic S/R
            rolling_mean = df_15m['close'].rolling(window=20).mean().iloc[-1]
            rolling_std = df_15m['close'].rolling(window=20).std().iloc[-1]
            bb_upper = rolling_mean + (rolling_std * 2)
            bb_lower = rolling_mean - (rolling_std * 2)
            
            # Key levels to check
            key_levels = [recent_high, recent_low, bb_upper, bb_lower]
            
            # Find nearest level
            min_distance_pct = 999
            nearest_level = None
            level_type = None
            
            for level in key_levels:
                distance_pct = abs(entry_price - level) / entry_price * 100
                if distance_pct < min_distance_pct:
                    min_distance_pct = distance_pct
                    nearest_level = level
                    if level == recent_high:
                        level_type = 'RESISTANCE'
                    elif level == recent_low:
                        level_type = 'SUPPORT'
                    elif level == bb_upper:
                        level_type = 'BB_UPPER'
                    else:
                        level_type = 'BB_LOWER'
            
            # Entry within 0.3% of S/R is risky
            near_sr = min_distance_pct < 0.3
            
            return {
                'near_sr': near_sr,
                'distance_pct': float(min_distance_pct),
                'nearest_level': float(nearest_level) if nearest_level else None,
                'level_type': level_type
            }
            
        except Exception as e:
            logging.warning(f"[S/R CHECK] Analysis failed: {e}")
            return {'near_sr': False, 'distance_pct': 999}

    def check_volume_sustainability(self, df_15m: pd.DataFrame) -> dict:
        """Check if volume is sustained (not just a spike)."""
        try:
            if len(df_15m) < 15:
                return {'sustained': False, 'strong_candles': 0, 'avg_ratio': 0}
            
            # Calculate average volume (excluding last 3 candles)
            avg_vol = df_15m['volume'].iloc[-15:-3].mean()
            
            if avg_vol == 0:
                return {'sustained': False, 'strong_candles': 0, 'avg_ratio': 0}
            
            # Check last 3 candles
            vol_ratios = []
            strong_candles = 0
            
            for i in range(-3, 0):
                ratio = df_15m['volume'].iloc[i] / avg_vol
                vol_ratios.append(ratio)
                if ratio > 1.2:  # Above average
                    strong_candles += 1
            
            # Sustained = at least 2 of 3 candles have elevated volume
            sustained = strong_candles >= 2
            avg_ratio = sum(vol_ratios) / len(vol_ratios)
            
            return {
                'sustained': sustained,
                'strong_candles': strong_candles,
                'avg_ratio': float(avg_ratio),
                'candle_ratios': [float(r) for r in vol_ratios]
            }
            
        except Exception as e:
            logging.warning(f"[VOL SUSTAIN] Analysis failed: {e}")
            return {'sustained': False, 'strong_candles': 0, 'avg_ratio': 0}

    def calculate_directional_momentum(self, df_15m: pd.DataFrame) -> dict:
        """Calculate directional momentum to predict PUMP or DUMP."""
        try:
            if len(df_15m) < 25:
                return {'direction': 'NEUTRAL', 'confidence': 0, 'factors': []}
            
            closes = df_15m['close'].values
            highs = df_15m['high'].values
            lows = df_15m['low'].values
            volumes = df_15m['volume'].values
            opens = df_15m['open'].values
            
            pump_score = 0
            dump_score = 0
            factors = []
            fake_signals = []
            fake_penalty = 0
            
            # ===========================================
            # ANTI-FAKE DETECTION (Run first)
            # ===========================================
            
            # 1. Single Candle Dominance (manipulation signal)
            # If one candle has >75% of the total move, it's likely fake (Relaxed from 60%)
            total_move = abs(closes[-1] - closes[-5])
            max_single_move = max(abs(closes[i] - closes[i-1]) for i in range(-4, 0))
            if total_move > 0 and max_single_move / total_move > 0.75:
                fake_penalty += 10 # Reduced from 20
                fake_signals.append("SINGLE_CANDLE_DOMINANCE")
            
            # 2. Wick Rejection (price rejected at highs/lows)
            last_candle_body = abs(closes[-1] - opens[-1])
            last_candle_range = highs[-1] - lows[-1]
            if last_candle_range > 0:
                body_ratio = last_candle_body / last_candle_range
                # Long wick = rejection
                if body_ratio < 0.25:  # Body is less than 25% of range (Relaxed from 30%)
                    fake_penalty += 5 # Reduced from 15
                    fake_signals.append("WICK_REJECTION")
            
            # 3. Volume Divergence (price up but volume decreasing)
            vol_trend = (volumes[-1] + volumes[-2]) / 2 - (volumes[-3] + volumes[-4]) / 2
            price_trend = closes[-1] - closes[-4]
            # Bullish price but bearish volume = weak/fake
            if price_trend > 0 and vol_trend < 0:
                fake_penalty += 5 # Reduced from 15
                fake_signals.append("VOL_DIVERGENCE_BULL")
            elif price_trend < 0 and vol_trend < 0:
                fake_penalty += 5 # Reduced from 10
                fake_signals.append("VOL_DIVERGENCE_BEAR")
            
            # 4. Immediate Reversal Check (last candle reversing)
            prev_direction = closes[-2] - closes[-3]
            curr_direction = closes[-1] - closes[-2]
            # Only checking strong reversals (>80% retracement) - Relaxed from 50%
            if prev_direction > 0 and curr_direction < 0 and abs(curr_direction) > abs(prev_direction) * 0.8:
                fake_penalty += 10 # Reduced from 20
                fake_signals.append("REVERSAL_CANDLE")
            elif prev_direction < 0 and curr_direction > 0 and abs(curr_direction) > abs(prev_direction) * 0.8:
                fake_penalty += 10 # Reduced from 20
                fake_signals.append("REVERSAL_CANDLE")
            
            # 1. Price Rate of Change (ROC)
            # ROC 3 candles (45 min)
            roc_3 = ((closes[-1] - closes[-4]) / closes[-4]) * 100 if closes[-4] > 0 else 0
            # ROC 5 candles (75 min)
            roc_5 = ((closes[-1] - closes[-6]) / closes[-6]) * 100 if closes[-6] > 0 else 0
            
            if roc_3 > 1.0:  # >1% up in 3 candles
                pump_score += 20
                factors.append(f"ROC3: +{roc_3:.1f}% (bullish)")
            elif roc_3 < -1.0:
                dump_score += 20
                factors.append(f"ROC3: {roc_3:.1f}% (bearish)")
            
            if roc_5 > 1.5:  # >1.5% up in 5 candles
                pump_score += 15
                factors.append(f"ROC5: +{roc_5:.1f}% (bullish)")
            elif roc_5 < -1.5:
                dump_score += 15
                factors.append(f"ROC5: {roc_5:.1f}% (bearish)")
            
            # 2. MACD Crossover (CRITICAL - Primary Momentum Indicator)
            # MACD histogram crossing zero = momentum shift
            try:
                macd = df_15m['macd'].iloc[-1] if 'macd' in df_15m else None
                macd_signal = df_15m['macd_signal'].iloc[-1] if 'macd_signal' in df_15m else None
                macd_diff = df_15m['macd_diff'].iloc[-1] if 'macd_diff' in df_15m else None
                macd_diff_prev = df_15m['macd_diff'].iloc[-2] if 'macd_diff' in df_15m else None

                if macd is not None and macd_signal is not None and macd_diff is not None:
                    # Bullish MACD crossover (histogram crosses above zero)
                    if macd_diff > 0 and macd_diff_prev <= 0:
                        pump_score += 30
                        factors.append("MACD BULLISH CROSS 🚀")
                    # Bearish MACD crossover (histogram crosses below zero)
                    elif macd_diff < 0 and macd_diff_prev >= 0:
                        dump_score += 30
                        factors.append("MACD BEARISH CROSS 📉")
                    # Already bullish momentum
                    elif macd > macd_signal:
                        pump_score += 15
                        factors.append(f"MACD bullish (diff: {macd_diff:.2f})")
                    # Already bearish momentum
                    elif macd < macd_signal:
                        dump_score += 15
                        factors.append(f"MACD bearish (diff: {macd_diff:.2f})")
            except Exception as e:
                logging.warning(f"[MACD] Calculation failed: {e}")

            # 3. EMA 9/21 Crossover (Secondary confirmation)
            ema_9 = ta.trend.ema_indicator(df_15m['close'], window=9).iloc[-1]
            ema_21 = ta.trend.ema_indicator(df_15m['close'], window=21).iloc[-1]
            ema_9_prev = ta.trend.ema_indicator(df_15m['close'], window=9).iloc[-2]
            ema_21_prev = ta.trend.ema_indicator(df_15m['close'], window=21).iloc[-2]

            # Bullish crossover (EMA9 crosses above EMA21)
            if ema_9 > ema_21 and ema_9_prev <= ema_21_prev:
                pump_score += 20
                factors.append("EMA9/21 BULLISH CROSS ⬆️")
            # Bearish crossover
            elif ema_9 < ema_21 and ema_9_prev >= ema_21_prev:
                dump_score += 20
                factors.append("EMA9/21 BEARISH CROSS ⬇️")
            # Already bullish
            elif ema_9 > ema_21:
                pump_score += 8
                factors.append("EMA9 > EMA21 (bullish)")
            # Already bearish
            elif ema_9 < ema_21:
                dump_score += 8
                factors.append("EMA9 < EMA21 (bearish)")

            # 4. MA Breakout Detection (7, 25, 99)
            # Price breaking above/below multiple MAs = strong signal
            try:
                current_price = closes[-1]
                ma_7 = df_15m['ma_7'].iloc[-1] if 'ma_7' in df_15m else None
                ma_25 = df_15m['ma_25'].iloc[-1] if 'ma_25' in df_15m else None
                ma_99 = df_15m['ma_99'].iloc[-1] if 'ma_99' in df_15m else None

                if ma_7 is not None and ma_25 is not None and ma_99 is not None:
                    # Check if price is above/below all MAs
                    above_all_mas = current_price > ma_7 and current_price > ma_25 and current_price > ma_99
                    below_all_mas = current_price < ma_7 and current_price < ma_25 and current_price < ma_99

                    # Check for MA breakout (price crossed MA7 in last 2 candles)
                    price_prev = closes[-2]
                    ma_7_prev = df_15m['ma_7'].iloc[-2]

                    # Bullish breakout (price crossed above MA7)
                    if current_price > ma_7 and price_prev <= ma_7_prev:
                        pump_score += 25
                        factors.append("MA7 BREAKOUT UP ⬆️")
                        if above_all_mas:
                            pump_score += 10
                            factors.append("Above ALL MAs (strong trend)")
                    # Bearish breakout (price crossed below MA7)
                    elif current_price < ma_7 and price_prev >= ma_7_prev:
                        dump_score += 25
                        factors.append("MA7 BREAKOUT DOWN ⬇️")
                        if below_all_mas:
                            dump_score += 10
                            factors.append("Below ALL MAs (strong downtrend)")
                    # Already trending
                    elif above_all_mas:
                        pump_score += 12
                        factors.append("Above ALL MAs (uptrend)")
                    elif below_all_mas:
                        dump_score += 12
                        factors.append("Below ALL MAs (downtrend)")
            except Exception as e:
                logging.warning(f"[MA BREAKOUT] Calculation failed: {e}")

            # 5. RSI Slope (Momentum acceleration)
            rsi_series = ta.momentum.rsi(df_15m['close'], window=14)
            rsi_now = rsi_series.iloc[-1]
            rsi_prev = rsi_series.iloc[-3]  # 3 candles ago
            rsi_slope = rsi_now - rsi_prev
            
            if rsi_slope > 5:  # RSI increasing fast
                pump_score += 15
                factors.append(f"RSI slope: +{rsi_slope:.1f} (accelerating up)")
            elif rsi_slope < -5:  # RSI decreasing fast
                dump_score += 15
                factors.append(f"RSI slope: {rsi_slope:.1f} (accelerating down)")
            
            # RSI zones bonus
            if rsi_now < 35 and rsi_slope > 0:  # Recovering from oversold
                pump_score += 10
                factors.append(f"RSI {rsi_now:.0f} recovering from oversold")
            elif rsi_now > 65 and rsi_slope < 0:  # Dropping from overbought
                dump_score += 10
                factors.append(f"RSI {rsi_now:.0f} dropping from overbought")

            # 6. Volume-Price Confirmation
            vol_avg = np.mean(volumes[-10:-3])
            
            bullish_vol_candles = 0
            bearish_vol_candles = 0
            
            for i in range(-3, 0):
                candle_up = closes[i] > opens[i]  # Green candle
                high_vol = volumes[i] > vol_avg * 1.2  # Above average volume
                
                if candle_up and high_vol:
                    bullish_vol_candles += 1
                elif not candle_up and high_vol:
                    bearish_vol_candles += 1
            
            if bullish_vol_candles >= 2:
                pump_score += 20
                factors.append(f"Volume confirms UP ({bullish_vol_candles}/3 bullish)")
            elif bearish_vol_candles >= 2:
                dump_score += 20
                factors.append(f"Volume confirms DOWN ({bearish_vol_candles}/3 bearish)")

            # 7. HH/HL Pattern (Last 5 candles) - Market structure
            recent_highs = highs[-5:]
            recent_lows = lows[-5:]
            
            higher_highs = all(recent_highs[i] >= recent_highs[i-1] for i in range(1, len(recent_highs)))
            higher_lows = all(recent_lows[i] >= recent_lows[i-1] for i in range(1, len(recent_lows)))
            lower_highs = all(recent_highs[i] <= recent_highs[i-1] for i in range(1, len(recent_highs)))
            lower_lows = all(recent_lows[i] <= recent_lows[i-1] for i in range(1, len(recent_lows)))
            
            if higher_highs and higher_lows:
                pump_score += 20
                factors.append("HH + HL pattern (strong bullish)")
            elif lower_highs and lower_lows:
                dump_score += 20
                factors.append("LH + LL pattern (strong bearish)")
            
            # Final calculation with anti-fake penalty
            total_score = pump_score + dump_score

            # UPDATED: Lowered threshold from 25 to 20 for crypto futures (more signals)
            # Crypto is more volatile and needs lower threshold to catch early movements
            MIN_SCORE_THRESHOLD = 20  # Was 25 before

            # Apply fake penalty to confidence
            if pump_score > dump_score and pump_score >= MIN_SCORE_THRESHOLD:
                direction = "PUMP"
                base_confidence = int((pump_score / max(total_score, 1)) * 100)
                confidence = max(0, min(95, base_confidence - fake_penalty))
            elif dump_score > pump_score and dump_score >= MIN_SCORE_THRESHOLD:
                direction = "DUMP"
                base_confidence = int((dump_score / max(total_score, 1)) * 100)
                confidence = max(0, min(95, base_confidence - fake_penalty))
            else:
                direction = "NEUTRAL"
                confidence = 0
            
            # If fake penalty is too high, downgrade to NEUTRAL
            if fake_penalty >= 40:
                direction = "NEUTRAL"
                confidence = 0
                logging.info(f"[MOMENTUM] Signal downgraded to NEUTRAL due to fake detection: {fake_signals}")
            elif fake_penalty >= 20 and confidence > 0:
                logging.info(f"[MOMENTUM] Confidence reduced by {fake_penalty}% due to: {fake_signals}")
            
            return {
                'direction': direction,
                'confidence': confidence,
                'pump_score': pump_score,
                'dump_score': dump_score,
                'roc_3': float(roc_3),
                'roc_5': float(roc_5),
                'ema_bullish': bool(ema_9 > ema_21),
                'rsi_slope': float(rsi_slope),
                'factors': factors,
                'fake_penalty': fake_penalty,
                'fake_signals': fake_signals
            }
            
        except Exception as e:
            logging.warning(f"[MOMENTUM] Analysis failed: {e}")
            return {'direction': 'NEUTRAL', 'confidence': 0, 'factors': [str(e)]}

    def get_top_opportunities(self) -> List[Dict]:
        """Screen market for top trading opportunities. Returns list of candidates with metrics."""
        try:
            # Try to get data from WebSocket (MANDATORY)
            from services.price_stream import price_stream
            
            raw_tickers = {}
            source = "WEBSOCKET"
            
            # Wait for WS to warm up if empty (up to 15s - increased for slow connections)
            retries = 0
            ticker_count = len(price_stream.get_all_tickers())
            logging.info(f"[SCREENER] Waiting for WebSocket... (current: {ticker_count} tickers, connected: {price_stream.is_connected})")
            
            while ticker_count < 10 and retries < 30:
                time.sleep(0.5)
                retries += 1
                ticker_count = len(price_stream.get_all_tickers())
            
            if ticker_count > 10:
                raw_tickers = price_stream.get_all_tickers()
                logging.info(f"[SCREENER] Using WebSocket data ({len(raw_tickers)} tickers)")
            else:
                # FALLBACK: Use Direct REST API (fapi) when WebSocket is down
                # We bypass CCXT here to ensure we hit fapi.binance.com and avoid api.binance.com (Spot) 503 errors
                ws_error = getattr(price_stream, 'last_error', 'Unknown')
                logging.warning(f"[SCREENER] WebSocket down (tickers={ticker_count}, connected={price_stream.is_connected}, error='{ws_error}'), using REST fallback")
                
                try:
                    import requests
                    source = "DIRECT_REST"
                    # Using Futures API directly
                    resp = requests.get("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=10)
                    if resp.status_code != 200:
                        raise Exception(f"HTTP {resp.status_code}")
                    
                    data = resp.json()
                    # Convert to dict keyed by symbol
                    raw_tickers = {item['symbol']: item for item in data}
                    logging.info(f"[SCREENER] Using DIRECT REST data ({len(raw_tickers)} tickers)")
                    
                except Exception as e:
                    logging.error(f"[SCREENER-CRITICAL] REST fallback also failed: {e}")
                    # Try one more valid endpoint (Premium Index) just in case, or fail
                    return []

            # Filter USDT futures pairs
            opportunities = []

            for symbol, ticker in raw_tickers.items():
                is_usdt = False
                clean_symbol = ""
                
                # Handle raw symbols from WS or Direct REST (e.g. "BTCUSDT")
                if source in ["WEBSOCKET", "DIRECT_REST"]:
                     if symbol.endswith("USDT"):
                         is_usdt = True
                         base = symbol[:-4]
                         clean_symbol = f"{base}/USDT"
                
                # Handle CCXT format (e.g. "BTC/USDT:USDT")
                else:
                    if symbol.endswith("/USDT:USDT"):
                        is_usdt = True
                        clean_symbol = symbol.replace(":USDT", "")
                
                if not is_usdt:
                    continue

                # Map fields based on source
                if source == "WEBSOCKET":
                    # WS format (from price_stream): quoteVolume, percentage
                    quote_volume = ticker.get('quoteVolume', 0)
                    percentage_change = ticker.get('percentage', 0)
                elif source == "DIRECT_REST":
                    # Binance API format: quoteVolume, priceChangePercent
                    quote_volume = float(ticker.get('quoteVolume', 0))
                    percentage_change = float(ticker.get('priceChangePercent', 0))
                else:
                    # CCXT format
                    quote_volume = ticker.get('quoteVolume', 0)
                    percentage_change = ticker.get('percentage', 0)

                if quote_volume is None or percentage_change is None:
                    continue
                
                # Check STATUS (active trading only) - Skip for Direct Rest/WS as we assume active if ticking
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

                    # Calculate indicators for 15M (needed for MACD scoring and MA breakout)
                    try:
                        # MACD
                        macd_15m_ind = ta.trend.MACD(close=df_15m['close'], window_slow=26, window_fast=12, window_sign=9)
                        df_15m['macd'] = macd_15m_ind.macd()
                        df_15m['macd_signal'] = macd_15m_ind.macd_signal()
                        df_15m['macd_diff'] = macd_15m_ind.macd_diff()

                        # Moving Averages
                        df_15m['ma_7'] = ta.trend.sma_indicator(df_15m['close'], window=7)
                        df_15m['ma_25'] = ta.trend.sma_indicator(df_15m['close'], window=25)
                        df_15m['ma_99'] = ta.trend.sma_indicator(df_15m['close'], window=99)
                    except Exception as e:
                        logging.warning(f"[15M INDICATORS] Failed to calculate for {symbol}: {e}")

                    # 2. Fetch 1h Data (For early reversal detection) - WITH CACHE
                    ohlcv_1h = self.fetch_ohlcv_cached(symbol, '1h', 30)
                    if not ohlcv_1h or len(ohlcv_1h) < 20:
                        # If 1H data fails, create empty dataframe to avoid errors
                        df_1h = pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                    else:
                        df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                        # Calculate indicators for 1H (needed for early reversal detection)
                        try:
                            macd_1h_ind = ta.trend.MACD(close=df_1h['close'], window_slow=26, window_fast=12, window_sign=9)
                            df_1h['macd'] = macd_1h_ind.macd()
                            df_1h['macd_signal'] = macd_1h_ind.macd_signal()
                            df_1h['macd_diff'] = macd_1h_ind.macd_diff()
                        except Exception as e:
                            logging.warning(f"[1H INDICATORS] Failed to calculate for {symbol}: {e}")

                    # 3. Fetch 4h Data (Strategic Trend) - WITH CACHE
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

                    # NEW: Hurst Exponent (Market Regime)
                    # H > 0.5 = Trending, H < 0.5 = Mean Reversion
                    try:
                        hurst = self.calculate_hurst_exponent(df_15m['close'].values)
                        if hurst > 0.6: regime = "TRENDING"
                        elif hurst < 0.4: regime = "MEAN_REVERSION"
                        else: regime = "RANDOM_WALK"
                    except:
                        hurst = 0.5
                        regime = "UNKNOWN"

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
                    
                    # New: Calculate Directional Momentum (Fix for NameError)
                    momentum_data = self.calculate_directional_momentum(df_15m)
                    momentum_direction = momentum_data.get('direction', 'NEUTRAL')
                    momentum_confidence = momentum_data.get('confidence', 0)

                    # E. Scoring System (UPGRADED for 10/10 Speed & Precision)
                    score = 0
                    
                    # 1. EXPLOSIVE MOMENTUM (The "Must Catch" Breakout)
                    # High Velocity (ROC) + High Fuel (Volume)
                    # ROC_3 is % change in last 3 candles (45 mins)
                    roc_val = float(momentum_data.get('roc_3', 0))
                    if abs(roc_val) > 1.5 and vol_ratio > 2.0:
                        score += 50
                        logging.info(f"[MATH 10/10] {symbol}: EXPLOSIVE MOVE (ROC={roc_val:.1f}%, Vol={vol_ratio:.1f}x)")
                    elif abs(roc_val) > 1.0 and vol_ratio > 1.5:
                        score += 30

                    # 2. TREND PURITY (Kaufman Efficiency Ratio)
                    # In Futures, we want "Clean" trends, not choppy garbage.
                    if efficiency_ratio > 0.8:
                        score += 40 # Perfect Trend (Algorithm's Dream)
                    elif efficiency_ratio > 0.6:
                        score += 20 # Clean Trend
                    
                    # 3. STATISTICAL ANOMALY: Volume Z-Score (Sigma)
                    # 3 Sigma = 99.7% Probability of Event
                    if vol_z_score > 4.0:
                        score += 40 # Black Swan Volume
                    elif vol_z_score > 3.0: 
                        score += 25 
                    
                    # 4. SQUEEZE (Potential Energy)
                    if is_squeeze:
                         score += 30
                         if vol_z_score > 2.0: score += 20 # Squeeze + Volume = Expansion soon

                    # 5. RSI DYNAMICS (Speed > Level)
                    # We care more about SLOPE than absolute level for scalping
                    rsi_slope = float(momentum_data.get('rsi_slope', 0))
                    if major_trend == 'BULL':
                        if rsi_val < 40: score += 15 # Dip buy opportunity
                        if rsi_slope > 3: score += 10 # Accelerating UP
                    elif major_trend == 'BEAR':
                        if rsi_val > 60: score += 15 # Short rally opportunity
                        if rsi_slope < -3: score += 10 # Accelerating DOWN

                    # 6. MARKET SENTIMENT & ORDER FLOW (Real-Time Pressure)
                    # Fetching this EARLY to include in score
                    try:
                        sentiment_data = self.fetch_market_sentiment(symbol)
                        sent_score = sentiment_data.get('sentiment_score', 0)
                        
                        # Add Sentiment directly to Score (Reactive Element)
                        # Max range: -50 to +50 -> Scaled to +/- 25 effect
                        sentiment_impact = sent_score * 0.4
                        
                        # Directional check: Only add if aligns with momentum
                        if (momentum_direction == 'PUMP' or roc_val > 0) and sentiment_impact > 0:
                            score += sentiment_impact
                        elif (momentum_direction == 'DUMP' or roc_val < 0) and abs(sentiment_impact) > 0:
                            score += abs(sentiment_impact) # Add positive score for strong negative sentiment
                            
                        # FUNDING TRAP DETECTION (The "Smart Money" Filter)
                        funding_rate = sentiment_data.get('funding_rate', 0)
                        
                        # Trap 1: Crowded Longs (High Funding + Stalling Price)
                        if funding_rate > 0.03 and rsi_val < 50:
                            score -= 30
                            logging.info(f"[TRAP] {symbol}: Long Trap! High Funding ({funding_rate}%) but Week Price")
                        
                        # Trap 2: Crowded Shorts (Negative Funding + Strong Price)
                        if funding_rate < -0.03 and rsi_val > 50:
                            score += 30 # Short Squeeze imminent
                            logging.info(f"[OPPORTUNITY] {symbol}: Short Squeeze! Neg Funding ({funding_rate}%) + Strong Price")

                    except Exception as e:
                        logging.warning(f"[SENTIMENT] Failed during scoring: {e}")
                        sentiment_data = {}

                    # Baseline additions
                    score += (vol_ratio * 5)
                    score += (adx_val / 5)

                    # Quality Penalties
                    structure_data = self.check_market_structure(df_15m)
                    structure_type = structure_data.get('structure', 'UNCLEAR')
                    
                    if structure_type == 'CHOPPY' and not is_squeeze:
                        score -= 20 # Punish chop unless squeezing
                    
                    # S/R Penalty
                    sr_check = self.check_sr_proximity(df_15m, current_price)
                    if sr_check.get('near_sr', False):
                        score -= 15

                    # --- Final JSON Construction ---
                    if score > 20: # Lowered threshold to see more candidate flows
                        result = cand.copy()
                        result['score'] = float(score)
                        result['rsi'] = float(rsi_val)
                        result['trend'] = major_trend
                        result['vol_ratio'] = float(vol_ratio)
                        result['vol_z_score'] = float(vol_z_score)
                        result['efficiency_ratio'] = float(efficiency_ratio)
                        result['is_squeeze'] = bool(is_squeeze)
                        
                        # Sentiment Data
                        result['oi_change_pct'] = sentiment_data.get('oi_change_pct', 0)
                        result['top_trader_long'] = sentiment_data.get('top_trader_long_ratio', 50)
                        result['taker_buy_ratio'] = sentiment_data.get('taker_buy_ratio', 50)
                        result['funding_rate'] = sentiment_data.get('funding_rate', 0)
                        result['sentiment_score'] = sentiment_data.get('sentiment_score', 0)
                        
                        # Momentum Data
                        result['momentum_direction'] = momentum_direction
                        result['momentum_confidence'] = float(momentum_confidence)
                        result['roc_3'] = roc_val
                        
                        # Market Regime (Hurst)
                        result['hurst'] = float(hurst)
                        result['market_regime'] = regime
                        
                        # CRITICAL: Ensure Price Data is passed for Execution
                        result['current_price'] = float(current_price)
                        result['atr_val'] = float(atr_val) if atr_val and not np.isnan(atr_val) else (current_price * 0.01)
                        
                        # Whale Logic (Sync)
                        if HAS_WHALE_DETECTOR:
                            try:
                                whale_data = get_whale_signal_sync(symbol, current_price)
                                result['whale_signal'] = whale_data.get('whale_signal', 'NEUTRAL')
                                result['whale_confidence'] = float(whale_data.get('whale_confidence', 0))
                                result['liquidation_pressure'] = whale_data.get('liquidation_pressure', 'NONE')
                                result['order_imbalance'] = whale_data.get('order_imbalance', 0)
                                result['large_trades_bias'] = whale_data.get('large_trades_bias', 'MIXED')

                                # Whale Score Boost
                                whale_conf = result['whale_confidence']
                                if whale_conf > 60:
                                    boost = (whale_conf - 60) * 0.8
                                    result['score'] += boost
                            except Exception:
                                result['whale_signal'] = 'NEUTRAL'
                                result['whale_confidence'] = 0
                                result['liquidation_pressure'] = 'NONE'
                                result['order_imbalance'] = 0.0
                                result['large_trades_bias'] = 'MIXED'
                        else:
                             # No whale detector
                            result['whale_signal'] = 'NEUTRAL'
                            result['whale_confidence'] = 0
                            result['liquidation_pressure'] = 'NONE'
                            result['order_imbalance'] = 0.0
                            result['large_trades_bias'] = 'MIXED'

                        # NEW v4.5: Compute suggested_direction (pre-hint for AI)
                        # Priority: Whale Signal > Momentum > RSI + Trend
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
                        # 2. Momentum direction (stronger than RSI alone)
                        elif momentum_direction == "PUMP" and momentum_confidence >= 60:
                            suggested_direction = "LONG"
                            logging.debug(f"[DIRECTION] {symbol}: LONG from MOMENTUM ({momentum_confidence}%)")
                        elif momentum_direction == "DUMP" and momentum_confidence >= 60:
                            suggested_direction = "SHORT"
                            logging.debug(f"[DIRECTION] {symbol}: SHORT from MOMENTUM ({momentum_confidence}%)")
                        else:
                            # 3. Fallback to RSI + Trend confluence
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
                        
                        # NEW: Early Reversal Detection
                        # Detect if we're in early reversal phase (15M reversing, 1H lagging)
                        early_reversal_data = self.detect_early_reversal(df_15m, df_1h)
                        is_early_reversal = early_reversal_data.get('is_early_reversal', False)
                        reversal_type = early_reversal_data.get('reversal_type', 'NONE')
                        reversal_confidence = early_reversal_data.get('confidence', 0)

                        result['early_reversal'] = is_early_reversal
                        result['reversal_type'] = reversal_type
                        result['reversal_confidence'] = reversal_confidence

                        # 1H confirmation layer
                        h1_confirmed = True
                        h1_reason = ""

                        if suggested_direction != "NEUTRAL":
                            h1_confirmed, h1_reason = self.check_1h_confirmation(symbol, suggested_direction)
                            result['h1_confirmed'] = h1_confirmed
                            result['h1_reason'] = h1_reason

                            if not h1_confirmed:
                                # Priority 1: Strong whale signals override 1H rejection
                                if whale_sig_final in ['PUMP_IMMINENT', 'DUMP_IMMINENT'] and result.get('whale_confidence', 0) >= 80:
                                    logging.info(f"[1H] {symbol}: {h1_reason} - BUT WHALE SIGNAL OVERRIDE ({whale_sig_final} {result.get('whale_confidence')}%)")
                                    result['h1_override'] = 'WHALE_SIGNAL'
                                # Priority 2: Early reversal detected - reduce penalty
                                elif is_early_reversal:
                                    # Check if reversal type matches suggested direction
                                    reversal_matches = (
                                        (reversal_type == 'BULLISH' and suggested_direction == 'LONG') or
                                        (reversal_type == 'BEARISH' and suggested_direction == 'SHORT')
                                    )
                                    if reversal_matches and reversal_confidence >= 50:
                                        # High confidence early reversal - minimal penalty
                                        score_penalty = 10  # Reduced from 25
                                        result['score'] = float(max(0, result['score'] - score_penalty))
                                        result['h1_override'] = 'EARLY_REVERSAL'
                                        logging.debug(f"[EARLY REVERSAL] {symbol}: {reversal_type} detected ({reversal_confidence}%) - "
                                                   f"Override 1H conflict with reduced penalty (-{score_penalty})")
                                    else:
                                        # Reversal detected but low confidence - standard penalty
                                        score_penalty = 18  # Slightly reduced from 25
                                        result['score'] = float(max(0, result['score'] - score_penalty))
                                        result['h1_conflict'] = True
                                        logging.debug(f"[1H] {symbol}: {suggested_direction} - early reversal phase, reduced penalty (-{score_penalty})")
                                else:
                                    # No override: Apply standard score penalty
                                    score_penalty = 25
                                    result['score'] = float(max(0, result['score'] - score_penalty))
                                    result['h1_conflict'] = True
                                    logging.warning(f"[1H] {symbol}: {suggested_direction} rejected - {h1_reason} (-{score_penalty} score)")

                                # If score drops too low, downgrade direction
                                if result['score'] < 30:
                                    suggested_direction = "NEUTRAL"
                                    logging.debug(f"[1H] {symbol}: Direction downgraded to NEUTRAL (score too low)")
                            else:
                                logging.debug(f"[1H] {symbol}: {suggested_direction} confirmed - {h1_reason}")
                        else:
                            result['h1_confirmed'] = True
                            result['h1_reason'] = "No direction to confirm"

                        
                        result['suggested_direction'] = suggested_direction
                        
                        if suggested_direction != "NEUTRAL":
                            logging.debug(f"[DIRECTION] {symbol}: {suggested_direction} (whale={whale_sig_final}, rsi={result.get('rsi', 0):.1f}, trend={result.get('trend')}, h1={h1_confirmed})")

                        return result

                    return None
                    
                except Exception as e:
                    logging.error(f"[WARN] Screener error for {symbol}: {e}")
                    return None
            
            # Execute parallel analysis
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
            # Validate with Executor (Ensure we can actually trade it)
            from services.execution import executor
            
            # Ensure markets are loaded in executor for validation
            if not executor.markets:
                 try:
                     # Attempt sync load if empty (using default client)
                     if executor.default_client:
                         executor.markets = executor.default_client.load_markets()
                 except Exception as e:
                     logging.warning(f"[SCREENER] Failed to load executor markets for validation: {e}")

            low_cap_candidates = []
            for symbol, ticker in raw_tickers.items():
                # Parse symbol
                formatted_symbol = symbol
                
                if source == "WEBSOCKET":
                    if not symbol.endswith("USDT"):
                        continue
                    base = symbol[:-4]
                    formatted_symbol = f"{base}/USDT"
                elif source == "REST":
                    # REST Usually returns "BTC/USDT" or "BTC/USDT:USDT"
                    # We want "BTC/USDT"
                    if not symbol.endswith("USDT"): continue
                    if ":" in symbol:
                        formatted_symbol = symbol.split(":")[0]

                # CRITICAL: Filter out coins that CCXT doesn't recognize (Can't execute)
                if executor.markets and formatted_symbol not in executor.markets:
                    # logging.debug(f"[SCREENER] Skipping {formatted_symbol} - Not in Executor Markets")
                    continue

                # Filter Logic...
                quote_volume = float(ticker.get('quoteVolume', 0)) if source == "WEBSOCKET" else float(ticker.get('quoteVolume', 0))
                percentage = float(ticker.get('percentage', 0)) if source == "WEBSOCKET" else float(ticker.get('percentage', 0))
                
                # Check liquid (using passed clean symbol)
                clean_symbol = formatted_symbol

                # Low-cap filter: $1M - $50M volume AND showing some movement (>2%)
                if 1_000_000 < quote_volume < 50_000_000 and abs(percentage) > 2:
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
                        pump_signals.append(f"VOL_SPIKE_{vol_ratio:.1f}x")
                    
                    # 4. Determine Direction
                    if rsi > 70:
                        pump_type = "DUMP" # We expect DUMP (Short)
                        trade_action = "SHORT"
                        if rsi > 80: trade_action = "STRONG_SHORT" # Strong Short
                    elif rsi < 30:
                        pump_type = "PUMP" # We expect PUMP (Long)
                        trade_action = "LONG"
                        if rsi < 20: trade_action = "STRONG_LONG" # Strong Long
                    else:
                        pump_type = "NEUTRAL"
                        trade_action = "WAIT"

                    # 5. Filter out boring coins
                    if pump_score < 40:  # If not extreme enough
                         return None

                    # Reset dump_risk (not used in same way for Mean Rev)
                    dump_risk = 0 # Placeholder

                    # === FAKE PUMP/DUMP WARNING LOGGING ===
                    # Log detailed fake detection for debugging
                    if trade_action in ["AVOID_LONG", "AVOID_SHORT", "WAIT"]: # Added WAIT to avoid logging neutral
                        risk_summary = ", ".join(risk_signals[:3])  # Top 3 reasons
                        logging.warning(f"[FAKE DETECTED] {symbol} {pump_type} - Score={int(pump_score)} DumpRisk={int(dump_risk)}% Action={trade_action} Reasons: {risk_summary}")
                    elif trade_action in ["CAUTIOUS_LONG", "CAUTIOUS_SHORT"]:
                        risk_summary = ", ".join(risk_signals[:2])
                        logging.info(f"[CAUTIOUS] {symbol} {pump_type} - Score={int(pump_score)} DumpRisk={int(dump_risk)}% Action={trade_action} Reasons: {risk_summary}")



                    return {
                        'symbol': symbol,
                        'pump_type': pump_type,
                        'pump_score': int(pump_score),
                        'signals': pump_signals,
                        'vol_ratio': float(round(vol_ratio, 1)),
                        'pct_change_3c': float(round(pct_change_3c, 2)),
                        'pct_change_24h': float(round(cand['pct_change_24h'], 2)),
                        'dump_risk': int(dump_risk),
                        'risk_signals': risk_signals,
                        'trade_action': trade_action
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
