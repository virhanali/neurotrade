"""
Market Screener Service
Scans Binance Futures market for high-volume, volatile opportunities
"""

import ccxt
from typing import List, Dict
from config import settings


class MarketScreener:
    """Screens market for top trading opportunities"""

    def __init__(self):
        """Initialize CCXT Binance Futures client (public API only)"""
        self.exchange = ccxt.binance({
            'enableRateLimit': True,
            'options': {'defaultType': 'future'}
        })

    def get_top_opportunities(self) -> List[str]:
        """
        Screen market for top trading opportunities

        Filter Criteria:
        1. 24h Quote Volume > $50,000,000 (Liquid coins)
        2. 1h Price Change > 1.5% (Volatile coins)

        Returns:
            List of top 5 symbol names sorted by volatility
        """
        try:
            # Load markets first (required for fetch_tickers)
            if not self.exchange.markets:
                self.exchange.load_markets()

            # Fetch all tickers
            tickers = self.exchange.fetch_tickers()

            # Filter USDT futures pairs
            opportunities = []

            for symbol, ticker in tickers.items():
                # Only USDT perpetual futures
                if not symbol.endswith('/USDT:USDT'):
                    continue

                # Extract data
                quote_volume = ticker.get('quoteVolume', 0)
                percentage_change = ticker.get('percentage', 0)

                # Apply filters
                if quote_volume is None or percentage_change is None:
                    continue

                # ✅ NEW: Check if symbol is TRADING (not SETTLING/DELISTED)
                clean_symbol = symbol.replace(':USDT', '')  # Convert 'BTC/USDT:USDT' to 'BTC/USDT'
                
                # Check market status
                if symbol in self.exchange.markets:
                    market = self.exchange.markets[symbol]
                    # Get status string
                    status = market.get('info', {}).get('status', 'UNKNOWN')
                    # Skip if not TRADING
                    if status != 'TRADING':
                        continue

                # Filter by volume and volatility
                if quote_volume >= settings.MIN_VOLUME_USDT and abs(percentage_change) >= settings.MIN_VOLATILITY_1H:
                    opportunities.append({
                        'symbol': clean_symbol,
                        'volume': quote_volume,
                        'volatility': abs(percentage_change),
                        'change': percentage_change,
                    })

            # Sort by volatility (highest first)
            opportunities.sort(key=lambda x: x['volatility'], reverse=True)

            # Return top N symbols
            top_symbols = [opp['symbol'] for opp in opportunities[:settings.TOP_COINS_LIMIT]]

            return top_symbols

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
