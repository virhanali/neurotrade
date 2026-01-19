"""
NeuroTrade AI - Volatility Profiler
Calculates volatility metrics and percentile ranking across symbols
"""

import logging
from typing import Dict, List
from datetime import datetime
from services.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class VolatilityProfiler:
    """
    Analyzes volatility and ranks symbols by volatility percentile
    Used for adaptive SL/TP sizing
    """
    
    def __init__(self, executor):
        """
        Initialize volatility profiler
        
        Args:
            executor: BinanceExecutor instance for fetching candles
        """
        self.executor = executor
        self.volatility_cache = {}  # {symbol: (timestamp, volatility_data)}
        self.percentile_cache = {}  # Global percentile data
        self.cache_ttl = 300  # 5 minutes
    
    def calculate_volatility_profile(
        self, 
        symbol: str,
        all_symbols: List[str] = None
    ) -> Dict[str, any]:
        """
        Calculate volatility profile for a symbol
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            all_symbols: List of all symbols for percentile calculation (optional)
            
        Returns:
            Dict with volatility metrics:
            {
                "atr_percent": float,
                "volatility_percentile": int (0-100),
                "classification": "LOW" | "MEDIUM" | "HIGH",
                "historical_vol_20d": float,
                "vol_trend": "INCREASING" | "DECREASING" | "STABLE",
                "is_high_volatility": bool,
                "is_low_volatility": bool
            }
        """
        # Check cache
        if symbol in self.volatility_cache:
            cached_time, vol_data = self.volatility_cache[symbol]
            if (datetime.now() - cached_time).total_seconds() < self.cache_ttl:
                logger.debug(f"[VOL-CACHE] HIT: {symbol}")
                return vol_data
        
        try:
            # Fetch 1h candles for volatility calculation
            candles = self.executor.fetch_ohlcv(symbol, "1h", limit=200)
            
            if not candles or len(candles) < 50:
                logger.warning(f"[VOL] Insufficient candles for {symbol}: {len(candles)}")
                return self._get_default_profile()
            
            # Calculate current ATR%
            atr_percent = TechnicalIndicators.calculate_atr_percent(candles, period=14)
            
            # Calculate historical volatility (20-day rolling)
            historical_vol_20d = self._calculate_historical_volatility(candles, period=20)
            
            # Calculate volatility trend
            vol_trend = self._calculate_volatility_trend(candles)
            
            # Calculate percentile (if all_symbols provided)
            percentile = 50  # Default
            if all_symbols:
                percentile = self._calculate_percentile(symbol, atr_percent, all_symbols)
            
            # Classify volatility
            classification = self._classify_volatility(percentile)
            
            result = {
                "atr_percent": atr_percent,
                "volatility_percentile": percentile,
                "classification": classification,
                "historical_vol_20d": historical_vol_20d,
                "vol_trend": vol_trend,
                "is_high_volatility": percentile > 70,
                "is_low_volatility": percentile < 30,
                "generated_at": datetime.now().isoformat()
            }
            
            # Cache result
            self.volatility_cache[symbol] = (datetime.now(), result)
            
            logger.info(
                f"[VOL] {symbol}: {atr_percent:.2f}% "
                f"(Percentile={percentile}, Class={classification}, Trend={vol_trend})"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"[VOL-ERROR] {symbol}: {e}")
            return self._get_default_profile()
    
    def _calculate_historical_volatility(
        self, 
        candles: List[dict], 
        period: int = 20
    ) -> float:
        """
        Calculate historical volatility (standard deviation of returns)
        
        Args:
            candles: List of OHLCV dicts
            period: Rolling window period
            
        Returns:
            Historical volatility as percentage
        """
        if len(candles) < period + 1:
            return 0.0
        
        try:
            import pandas as pd
            import numpy as np
            
            df = pd.DataFrame(candles)
            
            # Calculate log returns
            df['returns'] = np.log(df['close'] / df['close'].shift(1))
            
            # Calculate rolling standard deviation
            rolling_std = df['returns'].rolling(window=period).std()
            
            # Annualize (assuming 24h trading, 365 days)
            # For crypto: multiply by sqrt(24*365) for hourly data
            annualized_vol = rolling_std.iloc[-1] * np.sqrt(24 * 365) * 100
            
            return float(annualized_vol)
        
        except Exception as e:
            logger.error(f"Historical volatility calculation error: {e}")
            return 0.0
    
    def _calculate_volatility_trend(self, candles: List[dict]) -> str:
        """
        Determine if volatility is increasing, decreasing, or stable
        
        Args:
            candles: List of OHLCV dicts
            
        Returns:
            "INCREASING" | "DECREASING" | "STABLE"
        """
        if len(candles) < 50:
            return "STABLE"
        
        try:
            # Compare recent ATR (last 5 days) vs older ATR (5-20 days ago)
            recent_candles = candles[-120:]  # Last 5 days (hourly)
            older_candles = candles[-480:-120]  # 5-20 days ago
            
            recent_atr = TechnicalIndicators.calculate_atr_percent(recent_candles, period=14)
            older_atr = TechnicalIndicators.calculate_atr_percent(older_candles, period=14)
            
            if older_atr == 0:
                return "STABLE"
            
            change_percent = ((recent_atr - older_atr) / older_atr) * 100
            
            if change_percent > 20:
                return "INCREASING"
            elif change_percent < -20:
                return "DECREASING"
            else:
                return "STABLE"
        
        except Exception as e:
            logger.error(f"Volatility trend calculation error: {e}")
            return "STABLE"
    
    def _calculate_percentile(
        self, 
        symbol: str, 
        atr_percent: float, 
        all_symbols: List[str]
    ) -> int:
        """
        Calculate volatility percentile based on ABSOLUTE ATR thresholds.
        
        OPTIMIZATION: Instead of fetching all symbols and comparing (N API calls),
        we use fixed ATR% breakpoints based on historical crypto volatility:
        
        - ATR < 1.0%: Very low volatility (5th percentile)
        - ATR 1.0-1.5%: Low volatility (20th percentile)  
        - ATR 1.5-2.0%: Medium-low (40th percentile)
        - ATR 2.0-2.5%: Medium (50th percentile)
        - ATR 2.5-3.0%: Medium-high (65th percentile)
        - ATR 3.0-4.0%: High (80th percentile)
        - ATR > 4.0%: Very high (95th percentile)
        
        This saves ~20 API calls per scan while maintaining accuracy.
        
        Args:
            symbol: Current symbol
            atr_percent: Current symbol's ATR%
            all_symbols: List of all symbols (IGNORED in this optimization)
            
        Returns:
            Percentile rank (0-100)
        """
        # Absolute ATR% breakpoints (based on historical crypto data)
        if atr_percent < 1.0:
            return 5
        elif atr_percent < 1.2:
            return 15
        elif atr_percent < 1.5:
            return 25
        elif atr_percent < 1.8:
            return 40
        elif atr_percent < 2.0:
            return 50
        elif atr_percent < 2.5:
            return 65
        elif atr_percent < 3.0:
            return 75
        elif atr_percent < 4.0:
            return 85
        elif atr_percent < 5.0:
            return 92
        else:
            return 98
    
    def _classify_volatility(self, percentile: int) -> str:
        """
        Classify volatility based on percentile
        
        Args:
            percentile: Volatility percentile (0-100)
            
        Returns:
            "LOW" | "MEDIUM" | "HIGH"
        """
        if percentile < 30:
            return "LOW"
        elif percentile > 70:
            return "HIGH"
        else:
            return "MEDIUM"
    
    def _get_default_profile(self) -> Dict[str, any]:
        """
        Return default volatility profile (for error cases)
        """
        return {
            "atr_percent": 2.0,
            "volatility_percentile": 50,
            "classification": "MEDIUM",
            "historical_vol_20d": 0.0,
            "vol_trend": "STABLE",
            "is_high_volatility": False,
            "is_low_volatility": False,
            "generated_at": datetime.now().isoformat()
        }
    
    def get_volatility_adjustment(self, classification: str) -> float:
        """
        Get SL/TP multiplier adjustment based on volatility
        
        Args:
            classification: "LOW" | "MEDIUM" | "HIGH"
            
        Returns:
            Multiplier adjustment (e.g., 1.3 for high volatility)
        """
        adjustments = {
            "LOW": 0.8,     # Tighter SL/TP
            "MEDIUM": 1.0,  # No adjustment
            "HIGH": 1.3     # Wider SL/TP
        }
        
        return adjustments.get(classification, 1.0)
