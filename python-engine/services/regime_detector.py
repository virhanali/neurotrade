"""
NeuroTrade AI - Market Regime Detector
Detects market regime (RANGING, TRENDING, EXPLOSIVE) for adaptive trading
"""

import logging
from typing import Dict, List
from datetime import datetime, timedelta
from services.indicators import TechnicalIndicators

logger = logging.getLogger(__name__)


class MarketRegimeDetector:
    """
    Detects market regime using multiple indicators and timeframes
    
    Regimes:
    - RANGING: Sideways market, good for scalping (ADX < 20, ATR < 1.5%)
    - TRENDING: Directional market, good for swing trades (ADX 25-35, ATR 2-3%)
    - EXPLOSIVE: Parabolic move, high risk (ADX > 35, ROC > 3%)
    """
    
    def __init__(self, executor):
        """
        Initialize regime detector
        
        Args:
            executor: BinanceExecutor instance for fetching candles
        """
        self.executor = executor
        self.cache = {}  # {symbol: (timestamp, regime_data)}
        self.cache_ttl = 300  # 5 minutes cache
    
    def detect_regime(
        self, 
        symbol: str, 
        timeframes: List[str] = None
    ) -> Dict[str, any]:
        """
        Detect market regime for a symbol
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            timeframes: List of timeframes to analyze (default: ["5m", "15m", "1h"])
            
        Returns:
            Dict with regime analysis:
            {
                "regime": "RANGING" | "TRENDING" | "EXPLOSIVE",
                "confidence": 0-100,
                "adx": float,
                "atr_percent": float,
                "roc": float,
                "timeframe_alignment": {"5m": "RANGING", "15m": "RANGING", "1h": "TRENDING"},
                "is_aligned": bool,
                "indicators": {...},
                "generated_at": ISO timestamp
            }
        """
        if timeframes is None:
            timeframes = ["5m", "15m", "1h"]
        
        # Check cache
        cache_key = f"{symbol}_{'-'.join(timeframes)}"
        if cache_key in self.cache:
            cached_time, regime_data = self.cache[cache_key]
            if (datetime.now() - cached_time).total_seconds() < self.cache_ttl:
                logger.info(f"[REGIME-CACHE] HIT: {symbol} (age={(datetime.now() - cached_time).total_seconds():.0f}s)")
                return regime_data
        
        try:
            # Analyze each timeframe
            timeframe_regimes = {}
            all_indicators = {}
            
            for tf in timeframes:
                regime_data = self._analyze_timeframe(symbol, tf)
                timeframe_regimes[tf] = regime_data["regime"]
                all_indicators[tf] = regime_data["indicators"]
            
            # Use primary timeframe (first one, usually 5m for entry timing)
            primary_tf = timeframes[0]
            primary_regime = timeframe_regimes[primary_tf]
            primary_indicators = all_indicators[primary_tf]
            
            # Check alignment across timeframes
            regime_counts = {}
            for regime in timeframe_regimes.values():
                regime_counts[regime] = regime_counts.get(regime, 0) + 1
            
            # Alignment: all timeframes agree
            is_aligned = len(regime_counts) == 1
            
            # Confidence based on alignment and indicator strength
            confidence = self._calculate_confidence(
                primary_indicators,
                is_aligned,
                len(timeframes)
            )
            
            result = {
                "regime": primary_regime,
                "confidence": confidence,
                "adx": primary_indicators["adx"],
                "atr_percent": primary_indicators["atr_percent"],
                "roc": primary_indicators["roc"],
                "timeframe_alignment": timeframe_regimes,
                "is_aligned": is_aligned,
                "indicators": all_indicators,
                "generated_at": datetime.now().isoformat()
            }
            
            # Cache result
            self.cache[cache_key] = (datetime.now(), result)
            
            logger.info(
                f"[REGIME] {symbol}: {primary_regime} "
                f"(ADX={primary_indicators['adx']:.1f}, "
                f"ATR={primary_indicators['atr_percent']:.2f}%, "
                f"ROC={primary_indicators['roc']:.2f}%, "
                f"Aligned={is_aligned}, Conf={confidence}%)"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"[REGIME-ERROR] {symbol}: {e}")
            # Return conservative default
            return {
                "regime": "UNKNOWN",
                "confidence": 0,
                "adx": 0,
                "atr_percent": 0,
                "roc": 0,
                "timeframe_alignment": {},
                "is_aligned": False,
                "indicators": {},
                "generated_at": datetime.now().isoformat(),
                "error": str(e)
            }
    
    def _analyze_timeframe(self, symbol: str, timeframe: str) -> Dict[str, any]:
        """
        Analyze single timeframe to determine regime
        
        Args:
            symbol: Trading pair
            timeframe: Timeframe string (e.g., "5m", "1h")
            
        Returns:
            Dict with regime and indicators
        """
        # Fetch candles (need enough for indicators)
        limit = 200  # Enough for ADX (14*2) and other indicators
        candles = self.executor.fetch_ohlcv(symbol, timeframe, limit)
        
        if not candles or len(candles) < 50:
            logger.warning(f"[REGIME] Insufficient candles for {symbol} {timeframe}: {len(candles)}")
            return {
                "regime": "UNKNOWN",
                "indicators": {
                    "adx": 0,
                    "atr_percent": 0,
                    "roc": 0,
                    "bb_bandwidth": 0,
                    "rsi": 50
                }
            }
        
        # Calculate indicators
        adx = TechnicalIndicators.calculate_adx(candles, period=14)
        atr_percent = TechnicalIndicators.calculate_atr_percent(candles, period=14)
        roc = TechnicalIndicators.calculate_roc(candles, period=20)
        bb = TechnicalIndicators.calculate_bollinger_bands(candles, period=20)
        rsi = TechnicalIndicators.calculate_rsi(candles, period=14)
        
        indicators = {
            "adx": adx,
            "atr_percent": atr_percent,
            "roc": abs(roc),  # Use absolute value for regime detection
            "bb_bandwidth": bb["bandwidth_percent"],
            "rsi": rsi
        }
        
        # Determine regime based on indicators
        regime = self._classify_regime(indicators)
        
        return {
            "regime": regime,
            "indicators": indicators
        }
    
    def _classify_regime(self, indicators: Dict[str, float]) -> str:
        """
        Classify market regime based on indicator values
        
        Args:
            indicators: Dict with adx, atr_percent, roc, bb_bandwidth
            
        Returns:
            "RANGING" | "TRENDING" | "EXPLOSIVE"
        """
        adx = indicators["adx"]
        atr_percent = indicators["atr_percent"]
        roc = indicators["roc"]
        bb_bandwidth = indicators["bb_bandwidth"]
        
        # EXPLOSIVE: Very strong trend with high momentum
        if adx > 35 or roc > 3.0:
            return "EXPLOSIVE"
        
        # RANGING: Weak trend, low volatility, narrow bands
        if adx < 20 and atr_percent < 2.0 and bb_bandwidth < 4.0:
            return "RANGING"
        
        # TRENDING: Medium trend strength
        if adx >= 25:
            return "TRENDING"
        
        # Edge case: ADX 20-25 (transition zone)
        # Use ATR and BB bandwidth to decide
        if atr_percent < 1.5 and bb_bandwidth < 3.5:
            return "RANGING"
        else:
            return "TRENDING"
    
    def _calculate_confidence(
        self, 
        indicators: Dict[str, float], 
        is_aligned: bool,
        num_timeframes: int
    ) -> int:
        """
        Calculate confidence score (0-100) for regime detection
        
        Args:
            indicators: Primary timeframe indicators
            is_aligned: Whether all timeframes agree
            num_timeframes: Number of timeframes analyzed
            
        Returns:
            Confidence score (0-100)
        """
        confidence = 50  # Base confidence
        
        # Bonus for timeframe alignment
        if is_aligned:
            confidence += 20
        
        # Bonus for strong indicator signals
        adx = indicators["adx"]
        atr_percent = indicators["atr_percent"]
        
        # Strong ADX signal
        if adx > 30 or adx < 15:
            confidence += 15
        
        # Clear ATR signal
        if atr_percent > 2.5 or atr_percent < 1.2:
            confidence += 10
        
        # Penalty for weak signals (transition zone)
        if 18 < adx < 22:  # ADX in transition zone
            confidence -= 10
        
        # Cap at 100
        confidence = min(100, max(0, confidence))
        
        return confidence
    
    def get_regime_parameters(self, regime: str) -> Dict[str, any]:
        """
        Get recommended trading parameters for a regime
        
        Args:
            regime: "RANGING" | "TRENDING" | "EXPLOSIVE"
            
        Returns:
            Dict with trading parameters
        """
        params = {
            "RANGING": {
                "ml_threshold": 25,
                "sl_atr_multiplier": 1.0,
                "tp_atr_multiplier": 1.5,
                "entry_type": "LIMIT",
                "description": "Scalping mode - tight SL/TP, LIMIT entries"
            },
            "TRENDING": {
                "ml_threshold": 35,
                "sl_atr_multiplier": 2.0,
                "tp_atr_multiplier": 3.5,
                "entry_type": "MARKET",
                "description": "Swing mode - medium SL/TP, MARKET entries"
            },
            "EXPLOSIVE": {
                "ml_threshold": 45,
                "sl_atr_multiplier": 3.0,
                "tp_atr_multiplier": 5.0,
                "entry_type": "MARKET",
                "description": "Momentum mode - wide SL/TP, strict threshold"
            },
            "UNKNOWN": {
                "ml_threshold": 40,
                "sl_atr_multiplier": 2.5,
                "tp_atr_multiplier": 4.0,
                "entry_type": "MARKET",
                "description": "Conservative mode - default parameters"
            }
        }
        
        return params.get(regime, params["UNKNOWN"])
