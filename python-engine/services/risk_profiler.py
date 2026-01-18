"""
NeuroTrade AI - Dynamic Risk Profiler
Main module that combines regime detection and volatility profiling
to generate adaptive trading parameters for each symbol
"""

import logging
from typing import Dict, List
from datetime import datetime
from services.regime_detector import MarketRegimeDetector
from services.volatility_profiler import VolatilityProfiler
from config import settings

logger = logging.getLogger(__name__)


class DynamicRiskProfiler:
    """
    Generates dynamic risk profiles for symbols based on:
    1. Market Regime (RANGING/TRENDING/EXPLOSIVE)
    2. Volatility (LOW/MEDIUM/HIGH)
    3. Multi-timeframe confirmation
    
    Output: Adaptive parameters (SL/TP multipliers, ML threshold, entry type)
    """
    
    def __init__(self, executor):
        """
        Initialize dynamic risk profiler
        
        Args:
            executor: BinanceExecutor instance
        """
        self.executor = executor
        self.regime_detector = MarketRegimeDetector(executor)
        self.volatility_profiler = VolatilityProfiler(executor)
        self.profile_cache = {}  # {symbol: (timestamp, profile)}
        self.cache_ttl = 300  # 5 minutes
    
    def get_profile(
        self, 
        symbol: str,
        all_symbols: List[str] = None,
        timeframes: List[str] = None
    ) -> Dict[str, any]:
        """
        Generate complete risk profile for a symbol
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            all_symbols: List of all symbols for volatility percentile (optional)
            timeframes: Timeframes to analyze (default: ["5m", "15m", "1h"])
            
        Returns:
            Complete risk profile:
            {
                "symbol": str,
                "market_regime": str,
                "regime_confidence": int,
                "volatility_percentile": int,
                "volatility_classification": str,
                "atr_percent": float,
                "sl_atr_multiplier": float,
                "tp_atr_multiplier": float,
                "entry_type": str,
                "ml_confidence_threshold": int,
                "max_position_size_usdt": float,
                "timeframe_alignment": dict,
                "is_regime_aligned": bool,
                "vol_trend": str,
                "generated_at": str,
                "cache_hit": bool
            }
        """
        # Check cache
        if symbol in self.profile_cache:
            cached_time, profile = self.profile_cache[symbol]
            if (datetime.now() - cached_time).total_seconds() < self.cache_ttl:
                profile["cache_hit"] = True
                logger.debug(f"[PROFILE-CACHE] HIT: {symbol}")
                return profile
        
        try:
            # Step 1: Detect market regime
            regime_data = self.regime_detector.detect_regime(symbol, timeframes)
            
            # Step 2: Calculate volatility profile
            vol_data = self.volatility_profiler.calculate_volatility_profile(
                symbol, 
                all_symbols
            )
            
            # Step 3: Select adaptive parameters
            params = self._select_adaptive_parameters(
                regime_data["regime"],
                vol_data
            )
            
            # Step 4: Validate profile
            self._validate_profile(params)
            
            # Step 5: Build complete profile
            profile = {
                "symbol": symbol,
                "market_regime": regime_data["regime"],
                "regime_confidence": regime_data["confidence"],
                "volatility_percentile": vol_data["volatility_percentile"],
                "volatility_classification": vol_data["classification"],
                "atr_percent": vol_data["atr_percent"],
                "sl_atr_multiplier": params["sl_atr_multiplier"],
                "tp_atr_multiplier": params["tp_atr_multiplier"],
                "entry_type": params["entry_type"],
                "ml_confidence_threshold": params["ml_threshold"],
                "max_position_size_usdt": params["max_position_size"],
                "timeframe_alignment": regime_data.get("timeframe_alignment", {}),
                "is_regime_aligned": regime_data.get("is_aligned", False),
                "vol_trend": vol_data["vol_trend"],
                "generated_at": datetime.now().isoformat(),
                "cache_hit": False
            }
            
            # Cache profile
            self.profile_cache[symbol] = (datetime.now(), profile)
            
            # Log profile
            logger.info(
                f"[PROFILE] {symbol}: {profile['market_regime']} "
                f"(Vol={vol_data['classification']}, "
                f"SL={params['sl_atr_multiplier']:.1f}x, "
                f"TP={params['tp_atr_multiplier']:.1f}x, "
                f"ML>={params['ml_threshold']}%, "
                f"Entry={params['entry_type']})"
            )
            
            return profile
        
        except Exception as e:
            logger.error(f"[PROFILE-ERROR] {symbol}: {e}")
            return self._get_default_profile(symbol)
    
    def _select_adaptive_parameters(
        self, 
        regime: str, 
        vol_data: Dict[str, any]
    ) -> Dict[str, any]:
        """
        Select trading parameters based on regime and volatility
        
        Args:
            regime: Market regime (RANGING/TRENDING/EXPLOSIVE)
            vol_data: Volatility profile data
            
        Returns:
            Dict with adaptive parameters
        """
        # Base parameters per regime
        base_params = {
            "RANGING": {
                "sl_atr_multiplier": 1.0,
                "tp_atr_multiplier": 1.5,
                "ml_threshold": settings.ML_THRESHOLD_RANGING,  # 25
                "entry_type": "LIMIT",
                "max_position_size": 50.0
            },
            "TRENDING": {
                "sl_atr_multiplier": 2.0,
                "tp_atr_multiplier": 3.5,
                "ml_threshold": settings.ML_THRESHOLD_TRENDING,  # 35
                "entry_type": "MARKET",
                "max_position_size": 75.0
            },
            "EXPLOSIVE": {
                "sl_atr_multiplier": 3.0,
                "tp_atr_multiplier": 5.0,
                "ml_threshold": settings.ML_THRESHOLD_EXPLOSIVE,  # 45
                "entry_type": "MARKET",
                "max_position_size": 100.0
            },
            "UNKNOWN": {
                "sl_atr_multiplier": 2.5,
                "tp_atr_multiplier": 4.0,
                "ml_threshold": 40,
                "entry_type": "MARKET",
                "max_position_size": 60.0
            }
        }
        
        params = base_params.get(regime, base_params["UNKNOWN"]).copy()
        
        # Adjust based on volatility
        vol_adjustment = self.volatility_profiler.get_volatility_adjustment(
            vol_data["classification"]
        )
        
        params["sl_atr_multiplier"] *= vol_adjustment
        params["tp_atr_multiplier"] *= vol_adjustment
        
        # Special case: EXPLOSIVE with LOW volatility = suspicious (likely fake breakout)
        if regime == "EXPLOSIVE" and vol_data["classification"] == "LOW":
            logger.warning(
                f"[PROFILE-WARN] EXPLOSIVE regime with LOW volatility (suspicious)"
            )
            # Make it harder to trade
            params["ml_threshold"] = 50  # Very strict
            params["sl_atr_multiplier"] *= 1.5  # Wider SL
        
        # Special case: RANGING with HIGH volatility = choppy (reduce position size)
        if regime == "RANGING" and vol_data["classification"] == "HIGH":
            logger.warning(
                f"[PROFILE-WARN] RANGING regime with HIGH volatility (choppy)"
            )
            params["max_position_size"] *= 0.7  # Reduce position size
        
        # Adjust based on volatility trend
        if vol_data["vol_trend"] == "INCREASING":
            # Volatility increasing = widen SL to avoid stop-outs
            params["sl_atr_multiplier"] *= 1.1
            params["tp_atr_multiplier"] *= 1.1
        elif vol_data["vol_trend"] == "DECREASING":
            # Volatility decreasing = tighten SL/TP
            params["sl_atr_multiplier"] *= 0.95
            params["tp_atr_multiplier"] *= 0.95
        
        return params
    
    def _validate_profile(self, params: Dict[str, any]) -> None:
        """
        Validate profile parameters (sanity checks)
        
        Args:
            params: Profile parameters
            
        Raises:
            ValueError if parameters are invalid
        """
        # SL/TP must be positive
        if params["sl_atr_multiplier"] <= 0 or params["tp_atr_multiplier"] <= 0:
            raise ValueError(
                f"Invalid SL/TP multipliers: "
                f"SL={params['sl_atr_multiplier']}, TP={params['tp_atr_multiplier']}"
            )
        
        # TP must be greater than SL (positive R:R)
        if params["tp_atr_multiplier"] <= params["sl_atr_multiplier"]:
            raise ValueError(
                f"TP must be > SL: TP={params['tp_atr_multiplier']}, "
                f"SL={params['sl_atr_multiplier']}"
            )
        
        # ML threshold must be between 0-100
        if not 0 <= params["ml_threshold"] <= 100:
            raise ValueError(f"Invalid ML threshold: {params['ml_threshold']}")
        
        # Entry type must be valid
        if params["entry_type"] not in ["MARKET", "LIMIT"]:
            raise ValueError(f"Invalid entry type: {params['entry_type']}")
        
        # Position size must be positive
        if params["max_position_size"] <= 0:
            raise ValueError(f"Invalid position size: {params['max_position_size']}")
    
    def _get_default_profile(self, symbol: str) -> Dict[str, any]:
        """
        Return conservative default profile (for error cases)
        
        Args:
            symbol: Trading pair
            
        Returns:
            Default profile with conservative parameters
        """
        return {
            "symbol": symbol,
            "market_regime": "UNKNOWN",
            "regime_confidence": 0,
            "volatility_percentile": 50,
            "volatility_classification": "MEDIUM",
            "atr_percent": 2.0,
            "sl_atr_multiplier": 2.5,
            "tp_atr_multiplier": 4.0,
            "entry_type": "MARKET",
            "ml_confidence_threshold": 40,
            "max_position_size_usdt": 60.0,
            "timeframe_alignment": {},
            "is_regime_aligned": False,
            "vol_trend": "STABLE",
            "generated_at": datetime.now().isoformat(),
            "cache_hit": False,
            "error": "Failed to generate profile, using defaults"
        }
    
    def clear_cache(self, symbol: str = None) -> None:
        """
        Clear profile cache
        
        Args:
            symbol: Specific symbol to clear (None = clear all)
        """
        if symbol:
            if symbol in self.profile_cache:
                del self.profile_cache[symbol]
                logger.info(f"[PROFILE-CACHE] Cleared: {symbol}")
        else:
            self.profile_cache.clear()
            logger.info("[PROFILE-CACHE] Cleared all")
    
    def get_cache_stats(self) -> Dict[str, any]:
        """
        Get cache statistics
        
        Returns:
            Dict with cache stats
        """
        total_cached = len(self.profile_cache)
        
        # Count fresh vs stale
        fresh = 0
        stale = 0
        for cached_time, _ in self.profile_cache.values():
            age = (datetime.now() - cached_time).total_seconds()
            if age < self.cache_ttl:
                fresh += 1
            else:
                stale += 1
        
        return {
            "total_cached": total_cached,
            "fresh": fresh,
            "stale": stale,
            "cache_ttl_seconds": self.cache_ttl
        }
