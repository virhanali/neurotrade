"""
NeuroTrade AI - Technical Indicators Module
Provides calculation methods for market regime detection and risk profiling
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """
    Technical indicator calculations for market analysis
    All methods are static and can be used independently
    """
    
    @staticmethod
    def calculate_atr(candles: List[dict], period: int = 14) -> float:
        """
        Calculate Average True Range (ATR)
        
        Args:
            candles: List of OHLCV dicts with keys: open, high, low, close, volume
            period: ATR period (default 14)
            
        Returns:
            ATR value (absolute price)
        """
        if len(candles) < period + 1:
            logger.warning(f"Insufficient candles for ATR calculation: {len(candles)} < {period + 1}")
            return 0.0
        
        try:
            df = pd.DataFrame(candles)
            
            # True Range calculation
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            
            # ATR is EMA of True Range
            atr = true_range.ewm(span=period, adjust=False).mean().iloc[-1]
            
            return float(atr)
        
        except Exception as e:
            logger.error(f"ATR calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_atr_percent(candles: List[dict], period: int = 14) -> float:
        """
        Calculate ATR as percentage of current price
        
        Args:
            candles: List of OHLCV dicts
            period: ATR period (default 14)
            
        Returns:
            ATR percentage (e.g., 1.8 for 1.8%)
        """
        atr = TechnicalIndicators.calculate_atr(candles, period)
        
        if not candles or atr == 0:
            return 0.0
        
        current_price = candles[-1]['close']
        
        if current_price == 0:
            return 0.0
        
        atr_percent = (atr / current_price) * 100
        
        return float(atr_percent)
    
    @staticmethod
    def calculate_adx(candles: List[dict], period: int = 14) -> float:
        """
        Calculate Average Directional Index (ADX)
        Measures trend strength (0-100)
        
        Args:
            candles: List of OHLCV dicts
            period: ADX period (default 14)
            
        Returns:
            ADX value (0-100, higher = stronger trend)
        """
        if len(candles) < period * 2:
            logger.warning(f"Insufficient candles for ADX calculation: {len(candles)} < {period * 2}")
            return 0.0
        
        try:
            df = pd.DataFrame(candles)
            
            # Calculate +DM and -DM
            high_diff = df['high'].diff()
            low_diff = -df['low'].diff()
            
            plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
            minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
            
            # Calculate True Range
            high_low = df['high'] - df['low']
            high_close = np.abs(df['high'] - df['close'].shift())
            low_close = np.abs(df['low'] - df['close'].shift())
            true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            
            # Smooth with EMA
            atr = true_range.ewm(span=period, adjust=False).mean()
            plus_di = 100 * pd.Series(plus_dm).ewm(span=period, adjust=False).mean() / atr
            minus_di = 100 * pd.Series(minus_dm).ewm(span=period, adjust=False).mean() / atr
            
            # Calculate DX
            dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
            
            # ADX is EMA of DX
            adx = dx.ewm(span=period, adjust=False).mean().iloc[-1]
            
            return float(adx)
        
        except Exception as e:
            logger.error(f"ADX calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_roc(candles: List[dict], period: int = 20) -> float:
        """
        Calculate Rate of Change (ROC)
        Measures momentum as percentage change
        
        Args:
            candles: List of OHLCV dicts
            period: ROC period (default 20)
            
        Returns:
            ROC percentage (e.g., 3.5 for 3.5% change)
        """
        if len(candles) < period + 1:
            logger.warning(f"Insufficient candles for ROC calculation: {len(candles)} < {period + 1}")
            return 0.0
        
        try:
            df = pd.DataFrame(candles)
            
            current_price = df['close'].iloc[-1]
            past_price = df['close'].iloc[-period - 1]
            
            if past_price == 0:
                return 0.0
            
            roc = ((current_price - past_price) / past_price) * 100
            
            return float(roc)
        
        except Exception as e:
            logger.error(f"ROC calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_bollinger_bands(
        candles: List[dict], 
        period: int = 20, 
        std_dev: float = 2.0
    ) -> Dict[str, float]:
        """
        Calculate Bollinger Bands
        Useful for detecting ranging markets (price within bands)
        
        Args:
            candles: List of OHLCV dicts
            period: Moving average period (default 20)
            std_dev: Standard deviation multiplier (default 2.0)
            
        Returns:
            Dict with keys: upper, middle, lower, bandwidth_percent
        """
        if len(candles) < period:
            logger.warning(f"Insufficient candles for Bollinger Bands: {len(candles)} < {period}")
            return {"upper": 0.0, "middle": 0.0, "lower": 0.0, "bandwidth_percent": 0.0}
        
        try:
            df = pd.DataFrame(candles)
            
            # Middle band (SMA)
            middle = df['close'].rolling(window=period).mean().iloc[-1]
            
            # Standard deviation
            std = df['close'].rolling(window=period).std().iloc[-1]
            
            # Upper and lower bands
            upper = middle + (std_dev * std)
            lower = middle - (std_dev * std)
            
            # Bandwidth as percentage of price
            bandwidth_percent = ((upper - lower) / middle) * 100 if middle != 0 else 0.0
            
            return {
                "upper": float(upper),
                "middle": float(middle),
                "lower": float(lower),
                "bandwidth_percent": float(bandwidth_percent)
            }
        
        except Exception as e:
            logger.error(f"Bollinger Bands calculation error: {e}")
            return {"upper": 0.0, "middle": 0.0, "lower": 0.0, "bandwidth_percent": 0.0}
    
    @staticmethod
    def calculate_support_resistance(candles: List[dict], lookback: int = 50) -> Dict[str, any]:
        """
        Calculate support and resistance levels using pivot points
        
        Args:
            candles: List of OHLCV dicts (should be H1 timeframe)
            lookback: Number of candles to analyze (default 50)
            
        Returns:
            Dict with support/resistance levels and nearest levels
        """
        if len(candles) < lookback:
            logger.warning(f"Insufficient candles for S/R calculation: {len(candles)} < {lookback}")
            return {
                "support_levels": [],
                "resistance_levels": [],
                "nearest_support": 0.0,
                "nearest_resistance": 0.0,
                "pivot_point": 0.0
            }
        
        try:
            df = pd.DataFrame(candles[-lookback:])
            current_price = candles[-1]['close']
            
            # Calculate pivot point (classic method)
            high = df['high'].max()
            low = df['low'].min()
            close = df['close'].iloc[-1]
            
            pivot = (high + low + close) / 3
            
            # Calculate support and resistance levels
            r1 = (2 * pivot) - low
            r2 = pivot + (high - low)
            r3 = high + 2 * (pivot - low)
            
            s1 = (2 * pivot) - high
            s2 = pivot - (high - low)
            s3 = low - 2 * (high - pivot)
            
            # Find local highs and lows (swing points)
            df['is_pivot_high'] = (
                (df['high'] > df['high'].shift(1)) & 
                (df['high'] > df['high'].shift(-1))
            )
            df['is_pivot_low'] = (
                (df['low'] < df['low'].shift(1)) & 
                (df['low'] < df['low'].shift(-1))
            )
            
            pivot_highs = df[df['is_pivot_high']]['high'].tolist()
            pivot_lows = df[df['is_pivot_low']]['low'].tolist()
            
            # Combine with calculated levels
            resistance_levels = sorted(set([r1, r2, r3] + pivot_highs), reverse=True)
            support_levels = sorted(set([s1, s2, s3] + pivot_lows), reverse=True)
            
            # Find nearest levels
            nearest_resistance = min(
                [r for r in resistance_levels if r > current_price],
                default=current_price * 1.02
            )
            nearest_support = max(
                [s for s in support_levels if s < current_price],
                default=current_price * 0.98
            )
            
            return {
                "support_levels": support_levels[:5],  # Top 5
                "resistance_levels": resistance_levels[:5],
                "nearest_support": float(nearest_support),
                "nearest_resistance": float(nearest_resistance),
                "pivot_point": float(pivot)
            }
        
        except Exception as e:
            logger.error(f"Support/Resistance calculation error: {e}")
            return {
                "support_levels": [],
                "resistance_levels": [],
                "nearest_support": 0.0,
                "nearest_resistance": 0.0,
                "pivot_point": 0.0
            }
    
    @staticmethod
    def calculate_ema(candles: List[dict], period: int) -> float:
        """
        Calculate Exponential Moving Average (EMA)
        
        Args:
            candles: List of OHLCV dicts
            period: EMA period
            
        Returns:
            EMA value
        """
        if len(candles) < period:
            return 0.0
        
        try:
            df = pd.DataFrame(candles)
            ema = df['close'].ewm(span=period, adjust=False).mean().iloc[-1]
            return float(ema)
        
        except Exception as e:
            logger.error(f"EMA calculation error: {e}")
            return 0.0
    
    @staticmethod
    def calculate_rsi(candles: List[dict], period: int = 14) -> float:
        """
        Calculate Relative Strength Index (RSI)
        
        Args:
            candles: List of OHLCV dicts
            period: RSI period (default 14)
            
        Returns:
            RSI value (0-100)
        """
        if len(candles) < period + 1:
            return 50.0  # Neutral
        
        try:
            df = pd.DataFrame(candles)
            
            # Calculate price changes
            delta = df['close'].diff()
            
            # Separate gains and losses
            gains = delta.where(delta > 0, 0)
            losses = -delta.where(delta < 0, 0)
            
            # Calculate average gains and losses
            avg_gain = gains.ewm(span=period, adjust=False).mean()
            avg_loss = losses.ewm(span=period, adjust=False).mean()
            
            # Calculate RS and RSI
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return float(rsi.iloc[-1])
        
        except Exception as e:
            logger.error(f"RSI calculation error: {e}")
            return 50.0
