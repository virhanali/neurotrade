
import ccxt
import os
import json
import math
import logging
from decimal import Decimal, ROUND_DOWN
from typing import Dict, Optional, Tuple

logger = logging.getLogger("execution")

class BinanceExecutor:
    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")
        self.dry_run = os.getenv("BINANCE_DRY_RUN", "false").lower() == "true"
        
        if not self.api_key or not self.api_secret:
            logger.warning("[EXEC] Binance credentials not found. Real trading disabled.")
            self.client = None
            return

        # Initialize CCXT Binance Futures
        self.client = ccxt.binance({
            'apiKey': self.api_key,
            'secret': self.api_secret,
            'options': {
                'defaultType': 'future',
                'adjustForTimeDifference': True,
            },
            'enableRateLimit': True
        })
        
        # Cache for market rules (precisions)
        self.markets = {}
        self.precisions = {}
        
    async def initialize(self):
        """Fetch exchange info / market rules"""
        if not self.client:
            return
            
        try:
            logger.info("[EXEC] Fetching exchange rules from Binance...")
            self.markets = self.client.load_markets()
            logger.info(f"[EXEC] Loaded {len(self.markets)} markets rules.")
        except Exception as e:
            logger.error(f"[EXEC] Failed to load market rules: {e}")

    def _get_precision(self, symbol: str) -> Tuple[int, int]:
        """
        Get quantity and price precision for a symbol.
        Returns: (amount_precision, price_precision)
        """
        if symbol not in self.markets:
            # Fallback defaults
            return 3, 2
            
        market = self.markets[symbol]
        
        # CCXT unifies precision info
        price_precision = market['precision']['price']
        amount_precision = market['precision']['amount']
        
        return amount_precision, price_precision

    def _round_down(self, value: float, decimals: int) -> float:
        """Round DOWN to specific decimal places (SAFE for quantity)"""
        factor = 10 ** decimals
        return math.floor(value * factor) / factor

    def _round_price(self, value: float, decimals: int) -> float:
        """Round NEAREST for price"""
        return round(value, decimals)

    async def set_leverage(self, symbol: str, leverage: int):
        """Set leverage for the symbol"""
        if not self.client: return
        try:
            await self.client.set_leverage(leverage, symbol)
        except Exception as e:
            logger.error(f"[EXEC] Failed to set leverage: {e}")

    async def execute_entry(self, symbol: str, side: str, amount_usdt: float, leverage: int) -> Dict:
        """
        Execute a MARKET entry order.
        Amount is in USDT (margin * leverage).
        """
        if not self.client:
            return {"error": "Binance client not initialized"}

        try:
            # 1. Ensure market rules loaded
            if symbol not in self.markets:
                self.markets = self.client.load_markets()

            # 2. Calculate quantity
            ticker = self.client.fetch_ticker(symbol)
            current_price = ticker['last']
            
            # Notional Value = Margin * Leverage
            # Quantity = Notional / Price
            # Example: $10 Margin * 20x = $200 Notional. Price $50. Qty = 4.
            notional_value = amount_usdt  # This assumes amount_usdt IS the notional size (Total Value)
            
            raw_quantity = notional_value / current_price
            
            # 3. Apply Precision
            qty_precision, price_precision = self._get_precision(symbol)
            
            # SAFE ROUND DOWN for quantity (Verify LOT_SIZE)
            quantity = self._round_down(raw_quantity, qty_precision)
            
            # Check Min Notional (Binance usually $5)
            if quantity * current_price < 5.0:
                return {"error": "Order value too small (Min $5)"}

            logger.info(f"[EXEC] Placing Order: {side} {symbol} | ${notional_value:.2f} | Qty: {quantity}")

            # 4. Set Leverage First
            try:
                self.client.set_leverage(leverage, symbol)
            except Exception as e:
                logger.warning(f"[EXEC] Leverage set failed (might be already set): {e}")

            if self.dry_run:
                logger.info("[EXEC] DRY RUN MODE: Order simulated.")
                return {
                    "status": "FILLED",
                    "orderId": "SIMULATED",
                    "avgPrice": current_price,
                    "executedQty": quantity,
                    "dry_run": True
                }

            # 5. Send Order
            # CCXT create_order(symbol, type, side, amount, price, params)
            order = self.client.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),  # 'buy' or 'sell'
                amount=quantity,
                params={
                    'positionSide': 'BOTH' # For Hedge Mode if needed, defaulting to One-way usually
                }
            )

            logger.info(f"[EXEC] Order Filled! ID: {order['id']} @ {order['average']}")
            
            return {
                "status": "FILLED",
                "orderId": order['id'],
                "avgPrice": order['average'] or current_price, # Sometimes average is missing in fast execution
                "executedQty": order['filled'],
                "commission": 0.0 # TODO: Parse commission from fills
            }

        except Exception as e:
            logger.error(f"[EXEC] Order Failed: {e}")
            return {"error": str(e)}

    async def execute_close(self, symbol: str, side: str, quantity: float) -> Dict:
        """
        Close a position (Partial or Full).
        Side should be OPPOSITE to entry (e.g. if Long, side='sell').
        """
        if not self.client: return {"error": "No client"}
        
        try:
            # Send Market Order to Reduce Only
            order = self.client.create_order(
                symbol=symbol,
                type='market',
                side=side.lower(),
                amount=quantity,
                params={'reduceOnly': True}
            )
            return {"status": "FILLED", "orderId": order['id']}
        except Exception as e:
            return {"error": str(e)}

# Global Instance
executor = BinanceExecutor()
