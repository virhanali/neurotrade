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
        """Initialize CCXT Binance Futures client with increased connection pool"""
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        # Create session with larger connection pool for parallel requests
        session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=Retry(total=3, backoff_factor=0.5)
        )
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'},
            'session': session
        })
    
    def validate_symbol(self, symbol: str) -> bool:
        """
        Validate if symbol is tradeable (status = TRADING)
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            
        Returns:
            True if symbol is TRADING, False otherwise
        """
        try:
            # Load markets if not already loaded
            if not self.exchange.markets:
                self.exchange.load_markets()
            
            # Check if symbol exists
            if symbol not in self.exchange.markets:
                print(f"[WARN]  Symbol {symbol} not found in markets")
                return False
            
            # Get market info
            market = self.exchange.markets[symbol]
            
            # Check status explicitly (TRADING, SETTLING, DELISTED, etc.)
            status = market.get('info', {}).get('status', 'UNKNOWN')
            
            if status != 'TRADING':
                print(f"[WARN]  Symbol {symbol} status is {status} (not TRADING)")
                return False
            
            return True
            
        except Exception as e:
            print(f"[ERROR] Error validating symbol {symbol}: {str(e)}")
            return False


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

    def fetch_btc_context(self, mode: str = "INVESTOR") -> Dict:
        """
        Fetch BTC/USDT context to determine overall market direction
        
        Args:
            mode: Trading mode - "SCALPER" uses 15m candles, "INVESTOR" uses 1h candles

        Returns:
            Dict with BTC market data and analysis
        """
        try:
            # Fetch 4H data for trend context
            df_4h = self._fetch_ohlcv('BTC/USDT', '4h', limit=100)
            df_4h = self._calculate_indicators(df_4h)
            
            # For SCALPER mode, use 15m candles for trigger data
            if mode == "SCALPER":
                df_trigger = self._fetch_ohlcv('BTC/USDT', '15m', limit=100)
                trigger_label = "15m"
            else:
                df_trigger = self._fetch_ohlcv('BTC/USDT', '1h', limit=100)
                trigger_label = "1h"

            # Calculate indicators
            df_trigger = self._calculate_indicators(df_trigger)

            # Get latest candle data
            latest_trigger = df_trigger.iloc[-1]
            prev_trigger = df_trigger.iloc[-2]

            # Calculate percentage change (based on trigger timeframe)
            pct_change = ((latest_trigger['close'] - prev_trigger['close']) / prev_trigger['close']) * 100

            # Determine trend based on EMAs
            trend_4h = "UPTREND" if latest_trigger['ema_50'] > latest_trigger['ema_200'] else "DOWNTREND"

            # Market direction with mode-specific thresholds
            # SCALPER mode: more sensitive thresholds (±1.5% for 15m)
            # INVESTOR mode: standard thresholds (±1% for 1h)
            if mode == "SCALPER":
                pump_threshold = 1.5
                dump_threshold = -1.5
            else:
                pump_threshold = 1.0
                dump_threshold = -1.0

            if pct_change > pump_threshold:
                direction = "PUMPING"
            elif pct_change < dump_threshold:
                direction = "DUMPING"
            else:
                direction = "NEUTRAL"

            return {
                "symbol": "BTC/USDT",
                "trend_4h": trend_4h,
                f"pct_change_{trigger_label}": round(float(pct_change), 2),
                "pct_change_1h": round(float(pct_change), 2),  # Keep for backward compatibility
                "direction": direction,
                "current_price": float(latest_trigger['close']),
                f"rsi_{trigger_label}": round(float(latest_trigger['rsi']), 2) if pd.notna(latest_trigger['rsi']) else 50.0,
                "rsi_1h": round(float(latest_trigger['rsi']), 2) if pd.notna(latest_trigger['rsi']) else 50.0,  # Backward compat
                "ema_50": float(latest_trigger['ema_50']) if pd.notna(latest_trigger['ema_50']) else float(latest_trigger['close']),
                "ema_200": float(latest_trigger['ema_200']) if pd.notna(latest_trigger['ema_200']) else float(latest_trigger['close']),
                "mode": mode,
                "timeframe": trigger_label,
            }

        except Exception as e:
            raise Exception(f"Failed to fetch BTC context: {str(e)}")

    def fetch_target_data(self, symbol: str, mode: str = "INVESTOR") -> Dict:
        """
        Fetch target symbol data with technical analysis

        Args:
            symbol: Trading pair (e.g., 'ETH/USDT')
            mode: Trading mode - "SCALPER" uses 15m candles as primary trigger, "INVESTOR" uses 1h

        Returns:
            Dict with timeframe data and indicators based on mode
        """
        try:
            # Always fetch 4H data for context
            df_4h = self._fetch_ohlcv(symbol, '4h', limit=100)
            df_4h = self._calculate_indicators(df_4h)
            latest_4h = df_4h.iloc[-1]
            trend_4h = "UPTREND" if latest_4h['ema_50'] > latest_4h['ema_200'] else "DOWNTREND"
            
            # Fetch 1H data (context for both modes)
            df_1h = self._fetch_ohlcv(symbol, '1h', limit=100)
            df_1h = self._calculate_indicators(df_1h)
            latest_1h = df_1h.iloc[-1]
            trend_1h = "UPTREND" if latest_1h['ema_50'] > latest_1h['ema_200'] else "DOWNTREND"
            
            result = {
                "symbol": symbol,
                "mode": mode,
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
            
            # For SCALPER mode, also fetch 15m candles as primary trigger data
            if mode == "SCALPER":
                df_15m = self._fetch_ohlcv(symbol, '15m', limit=100)
                df_15m = self._calculate_indicators(df_15m)
                latest_15m = df_15m.iloc[-1]
                trend_15m = "UPTREND" if latest_15m['ema_50'] > latest_15m['ema_200'] else "DOWNTREND"
                
                # Add Bollinger Bands for SCALPER mode (Mean Reversion strategy)
                from ta.volatility import BollingerBands
                bb = BollingerBands(close=df_15m['close'], window=20, window_dev=2)
                df_15m['bb_upper'] = bb.bollinger_hband()
                df_15m['bb_lower'] = bb.bollinger_lband()
                df_15m['bb_middle'] = bb.bollinger_mavg()
                latest_15m = df_15m.iloc[-1]
                
                result["data_15m"] = {
                    "df": df_15m,
                    "trend": trend_15m,
                    "price": float(latest_15m['close']),
                    "rsi": round(float(latest_15m['rsi']), 2) if pd.notna(latest_15m['rsi']) else 50.0,
                    "atr": round(float(latest_15m['atr']), 4) if pd.notna(latest_15m['atr']) else 0.01,
                    "ema_50": float(latest_15m['ema_50']) if pd.notna(latest_15m['ema_50']) else float(latest_15m['close']),
                    "ema_200": float(latest_15m['ema_200']) if pd.notna(latest_15m['ema_200']) else float(latest_15m['close']),
                    "bb_upper": round(float(latest_15m['bb_upper']), 4) if pd.notna(latest_15m['bb_upper']) else None,
                    "bb_lower": round(float(latest_15m['bb_lower']), 4) if pd.notna(latest_15m['bb_lower']) else None,
                    "bb_middle": round(float(latest_15m['bb_middle']), 4) if pd.notna(latest_15m['bb_middle']) else None,
                }
            
            return result

        except Exception as e:
            raise Exception(f"Failed to fetch target data for {symbol}: {str(e)}")
