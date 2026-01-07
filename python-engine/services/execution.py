import asyncio
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
        self.default_api_key = os.getenv("BINANCE_API_KEY")
        self.default_api_secret = os.getenv("BINANCE_API_SECRET")
        self.default_client = None
        
        if self.default_api_key and self.default_api_secret:
            self.default_client = ccxt.binance({
                'apiKey': self.default_api_key,
                'secret': self.default_api_secret,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                },
                'enableRateLimit': True
            })
        else:
            logger.warning("[EXEC] Binance credentials not found in ENV. Real trading disabled unless keys provided.")

        # Cache for market rules (precisions)
        self.markets = {}
        self.precisions = {}
        
    async def initialize(self):
        """Fetch exchange info / market rules using default client"""
        if not self.default_client:
            return
            
        try:
            logger.info("[EXEC] Fetching exchange rules from Binance (Default)...")
            # Run blocking call in thread
            self.markets = await asyncio.to_thread(self.default_client.load_markets)
            logger.info(f"[EXEC] Loaded {len(self.markets)} markets rules.")
        except Exception as e:
            logger.error(f"[EXEC] Failed to load market rules: {e}")

    def _get_client(self, api_key: Optional[str] = None, api_secret: Optional[str] = None):
        """
        Get a CCXT client: either a NEW custom one or the DEFAULT one.
        Returns (client, is_temp)
        """
        if api_key and api_secret:
            client = ccxt.binance({
                'apiKey': api_key,
                'secret': api_secret,
                'options': {
                    'defaultType': 'future',
                    'adjustForTimeDifference': True,
                },
                'enableRateLimit': True
            })
            return client, True
        
        return self.default_client, False

    async def _ensure_markets_loaded(self, client):
        """Ensure markets are loaded (using the provided client if global cache is empty)"""
        if not self.markets:
            if not client: return
            try:
                self.markets = await asyncio.to_thread(client.load_markets)
                logger.info(f"[EXEC] Loaded {len(self.markets)} markets rules (On-Demand).")
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
        if decimals <= 0:
            return math.floor(value)
        factor = 10 ** decimals
        return math.floor(value * factor) / factor

    async def execute_entry(self, symbol: str, side: str, amount_usdt: float, leverage: int, 
                          api_key: Optional[str] = None, api_secret: Optional[str] = None) -> Dict:
        """
        Execute a MARKET entry order.
        Amount is in USDT (margin * leverage).
        """
        client, is_temp = self._get_client(api_key, api_secret)
        
        if not client:
            return {"error": "Binance client not initialized (No Keys)"}

        try:
            # 1. Safety: Validate parameters
            if amount_usdt <= 0:
                return {"error": "Invalid amount USDT"}

            # Safety: Cap leverage to Binance maximum
            if leverage > 125:
                logger.warning(f"[EXEC] Leverage {leverage}x exceeds Binance max, capping at 125x")
                leverage = 125
            elif leverage < 1:
                logger.warning(f"[EXEC] Leverage {leverage}x invalid, defaulting to 20x")
                leverage = 20

            # Safety: Check minimum notional ($5)
            if amount_usdt < 5.0:
                return {"error": f"Order value ${amount_usdt:.2f} below Binance minimum ($5). Please increase margin."}

            # 2. Ensure market rules loaded
            await self._ensure_markets_loaded(client)
            
            # 3. Map Side (LONG/SHORT -> BUY/SELL)
            order_side = side.upper()
            if order_side == 'LONG':
                order_side = 'buy'
            elif order_side == 'SHORT':
                order_side = 'sell'
            else:
                order_side = side.lower() # Fallback

            # 4. Calculate quantity
            # Fetch ticker in thread
            ticker = await asyncio.to_thread(client.fetch_ticker, symbol)
            current_price = ticker['last']

            # Notional Value = Margin * Leverage
            notional_value = amount_usdt
            raw_quantity = notional_value / current_price

            # 5. Apply Precision
            qty_precision, price_precision = self._get_precision(symbol)
            quantity = self._round_down(raw_quantity, qty_precision)

            # Double-check Min Notional after precision rounding
            actual_notional = quantity * current_price
            if actual_notional < 5.0:
                logger.warning(f"[EXEC] Order value ${actual_notional:.2f} below $5 after rounding, rejecting")
                return {"error": f"Order value ${actual_notional:.2f} below Binance minimum ($5) after precision rounding"}

            logger.info(f"[EXEC] Placing Order: {side} ({order_side}) {symbol} | Notional: ${notional_value:.2f} | Leverage: {leverage}x | Margin: ${amount_usdt/leverage:.2f} | Qty: {quantity}")

            # 6. Set Leverage First
            try:
                await asyncio.to_thread(client.set_leverage, leverage, symbol)
            except Exception as e:
                logger.warning(f"[EXEC] Leverage set failed (might be already set): {e}")

            # 7. Send Order (IN THREAD)
            order = await asyncio.to_thread(
                client.create_order,
                symbol,
                'market',
                order_side,
                quantity,
                {
                    'positionSide': 'BOTH'
                }
            )

            logger.info(f"[EXEC] Order Filled! ID: {order['id']} @ {order['average']}")

            return {
                "status": "FILLED",
                "orderId": order['id'],
                "avgPrice": order['average'] or current_price,
                "executedQty": order['filled'],
                "commission": 0.0
            }

        except Exception as e:
            logger.error(f"[EXEC] Order Failed: {e}")
            return {"error": str(e)}
        finally:
            if is_temp and client:
                # Sync client doesn't need await close, or precise closing
                pass

    async def execute_close(self, symbol: str, side: str, quantity: float, 
                          api_key: Optional[str] = None, api_secret: Optional[str] = None) -> Dict:
        """
        Close a position (Partial or Full).
        Side should be OPPOSITE to entry (e.g. if Long, side should be passed as SHORT/SELL).
        """
        client, is_temp = self._get_client(api_key, api_secret)
        
        if not client:
            return {"error": "Binance client not initialized (No Keys)"}

        try:
            # Safety: Validate parameters
            if quantity <= 0:
                return {"error": "Invalid quantity"}

            # 1. Ensure market rules loaded
            await self._ensure_markets_loaded(client)

            # 2. Map Side (LONG/SHORT -> BUY/SELL)
            order_side = side.upper()
            if order_side == 'LONG':
                order_side = 'buy'
            elif order_side == 'SHORT':
                order_side = 'sell'
            else:
                order_side = side.lower()

            # 3. Apply Precision for safety
            qty_precision, price_precision = self._get_precision(symbol)
            quantity = self._round_down(quantity, qty_precision)

            logger.info(f"[EXEC] Closing Position: {symbol} | Side: {order_side} | Qty: {quantity} | ReduceOnly: True")

            # 4. Send Market Order (IN THREAD) with reduceOnly
            order = await asyncio.to_thread(
                client.create_order,
                symbol,
                'market',
                order_side,
                quantity,
                {'reduceOnly': True}
            )

            logger.info(f"[EXEC] Close Order Filled! ID: {order['id']} @ {order['average']}")

            return {
                "status": "FILLED",
                "orderId": order['id'],
                "avgPrice": order['average'] or 0.0,
                "executedQty": order['filled'] or quantity
            }
        except Exception as e:
            logger.error(f"[EXEC] Close Order Failed: {e}")
            return {"error": str(e)}
        finally:
            if is_temp and client:
                # Sync client cleanup
                pass

    async def get_balance(self, api_key: Optional[str] = None, api_secret: Optional[str] = None) -> Dict:
        """
        Fetch USDT balance from Binance Futures
        """
        client, is_temp = self._get_client(api_key, api_secret)
        
        if not client:
            return {"error": "Binance client not initialized (No Keys)"}
            
        try:
            # Run in thread to avoid blocking loop
            balance = await asyncio.to_thread(client.fetch_balance)
            
            # Futures balance structure can be tricky, check 'USDT'
            usdt = balance.get('USDT', {})
            total = usdt.get('total', 0.0)
            free = usdt.get('free', 0.0)
            
            # Fallback check 'total' key if needed
            if total == 0 and 'total' in balance:
                total = balance['total'].get('USDT', 0.0)
                free = balance['free'].get('USDT', 0.0)
                
            return {
                "asset": "USDT",
                "total": float(total),
                "free": float(free)
            }
        except Exception as e:
            logger.error(f"[EXEC] Failed to get balance: {e}")
            return {"error": str(e)}
        finally:
            if is_temp and client:
                # Sync client cleanup
                pass

# Global Instance
executor = BinanceExecutor()
