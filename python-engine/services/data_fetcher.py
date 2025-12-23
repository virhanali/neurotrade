"""
Data Fetcher Service
Fetches OHLCV data from Binance Futures and calculates technical indicators
"""

import ccxt
import pandas as pd
from ta.momentum import RSIIndicator
from ta.volatility import AverageTrueRange
from ta.trend import EMAIndicator
from typing import Dict, List, Optional
from config import settings


class DataFetcher:
    """Fetches and processes market data from Binance Futures"""

    def __init__(self):
        """Initialize CCXT Binance Futures client (public endpoints only)"""
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })

    def _fetch_ohlcv(self, symbol: str, timeframe: str, limit: int = 100) -> pd.DataFrame:
        """
        Fetch OHLCV data and convert to DataFrame

        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe (e.g., '1h', '4h')
            limit: Number of candles to fetch

        Returns:
            DataFrame with OHLCV data
        """
        try:
            ohlcv = self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            df = pd.DataFrame(
                ohlcv,
                columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            return df
        except Exception as e:
            raise Exception(f"Failed to fetch OHLCV for {symbol} {timeframe}: {str(e)}")

    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate technical indicators using ta library

        Args:
            df: DataFrame with OHLCV data

        Returns:
            DataFrame with added indicators
        """
        # RSI (14)
        rsi_indicator = RSIIndicator(close=df['close'], window=14)
        df['rsi'] = rsi_indicator.rsi()

        # ATR (14)
        atr_indicator = AverageTrueRange(high=df['high'], low=df['low'], close=df['close'], window=14)
        df['atr'] = atr_indicator.average_true_range()

        # EMA (50, 200)
        ema_50_indicator = EMAIndicator(close=df['close'], window=50)
        df['ema_50'] = ema_50_indicator.ema_indicator()

        ema_200_indicator = EMAIndicator(close=df['close'], window=200)
        df['ema_200'] = ema_200_indicator.ema_indicator()

        return df

    def fetch_btc_context(self) -> Dict:
        """
        Fetch BTC/USDT context to determine overall market direction

        Returns:
            Dict with BTC market data and analysis
        """
        try:
            # Fetch 4H and 1H data
            df_4h = self._fetch_ohlcv('BTC/USDT', '4h', limit=100)
            df_1h = self._fetch_ohlcv('BTC/USDT', '1h', limit=100)

            # Calculate indicators
            df_4h = self._calculate_indicators(df_4h)
            df_1h = self._calculate_indicators(df_1h)

            # Get latest candle data
            latest_1h = df_1h.iloc[-1]
            prev_1h = df_1h.iloc[-2]

            # Calculate 1H percentage change
            pct_change_1h = ((latest_1h['close'] - prev_1h['close']) / prev_1h['close']) * 100

            # Determine trend based on EMAs
            trend_4h = "UPTREND" if latest_1h['ema_50'] > latest_1h['ema_200'] else "DOWNTREND"

            # Market direction
            if pct_change_1h > 1.0:
                direction = "PUMPING"
            elif pct_change_1h < -1.0:
                direction = "DUMPING"
            else:
                direction = "NEUTRAL"

            return {
                "symbol": "BTC/USDT",
                "trend_4h": trend_4h,
                "pct_change_1h": round(float(pct_change_1h), 2),
                "direction": direction,
                "current_price": float(latest_1h['close']),
                "rsi_1h": round(float(latest_1h['rsi']), 2) if pd.notna(latest_1h['rsi']) else 50.0,
                "ema_50": float(latest_1h['ema_50']) if pd.notna(latest_1h['ema_50']) else float(latest_1h['close']),
                "ema_200": float(latest_1h['ema_200']) if pd.notna(latest_1h['ema_200']) else float(latest_1h['close']),
            }

        except Exception as e:
            raise Exception(f"Failed to fetch BTC context: {str(e)}")

    def fetch_target_data(self, symbol: str) -> Dict:
        """
        Fetch target symbol data with technical analysis

        Args:
            symbol: Trading pair (e.g., 'ETH/USDT')

        Returns:
            Dict with 4H and 1H data and indicators
        """
        try:
            # Fetch 4H and 1H data
            df_4h = self._fetch_ohlcv(symbol, '4h', limit=100)
            df_1h = self._fetch_ohlcv(symbol, '1h', limit=100)

            # Calculate indicators
            df_4h = self._calculate_indicators(df_4h)
            df_1h = self._calculate_indicators(df_1h)

            # Get latest candle data
            latest_4h = df_4h.iloc[-1]
            latest_1h = df_1h.iloc[-1]

            # Determine trend
            trend_4h = "UPTREND" if latest_4h['ema_50'] > latest_4h['ema_200'] else "DOWNTREND"
            trend_1h = "UPTREND" if latest_1h['ema_50'] > latest_1h['ema_200'] else "DOWNTREND"

            return {
                "symbol": symbol,
                "data_4h": {
                    "df": df_4h,
                    "trend": trend_4h,
                    "price": float(latest_4h['close']),
                    "rsi": round(float(latest_4h['rsi']), 2) if pd.notna(latest_4h['rsi']) else 50.0,
                    "atr": round(float(latest_4h['atr']), 4) if pd.notna(latest_4h['atr']) else 0.01,
                    "ema_50": float(latest_4h['ema_50']) if pd.notna(latest_4h['ema_50']) else float(latest_4h['close']),
                    "ema_200": float(latest_4h['ema_200']) if pd.notna(latest_4h['ema_200']) else float(latest_4h['close']),
                },
                "data_1h": {
                    "df": df_1h,
                    "trend": trend_1h,
                    "price": float(latest_1h['close']),
                    "rsi": round(float(latest_1h['rsi']), 2) if pd.notna(latest_1h['rsi']) else 50.0,
                    "atr": round(float(latest_1h['atr']), 4) if pd.notna(latest_1h['atr']) else 0.01,
                    "ema_50": float(latest_1h['ema_50']) if pd.notna(latest_1h['ema_50']) else float(latest_1h['close']),
                    "ema_200": float(latest_1h['ema_200']) if pd.notna(latest_1h['ema_200']) else float(latest_1h['close']),
                },
            }

        except Exception as e:
            raise Exception(f"Failed to fetch target data for {symbol}: {str(e)}")
