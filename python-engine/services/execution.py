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
            logger.warning("[EXEC] Binance credentials not found in ENV.")

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
                          api_key: Optional[str] = None, api_secret: Optional[str] = None,
                          sl_price: Optional[float] = None, tp_price: Optional[float] = None,
                          trailing_callback: Optional[float] = None,
                          order_type: str = "MARKET", limit_price: Optional[float] = None) -> Dict:
        """
        Execute an entry order (MARKET or LIMIT).
        """
        client, is_temp = self._get_client(api_key, api_secret)
        
        if not client:
            print("DEBUG_EXEC_ERROR: Binance client not initialized (No Keys provided)")
            return {"error": "Binance client not initialized (No Keys)"}

        try:
            # 1. Safety: Validate parameters
            if amount_usdt <= 0:
                print(f"DEBUG_EXEC_ERROR: Invalid amount USDT: {amount_usdt}")
                return {"error": "Invalid amount USDT"}

            # Safety: Cap leverage to Binance maximum
            if leverage > 125:
                leverage = 125
            elif leverage < 1:
                leverage = 20

            # Safety: Check minimum notional ($5)
            if amount_usdt < 5.0:
                print(f"DEBUG_EXEC_ERROR: Order value ${amount_usdt} below minimum")
                return {"error": f"Order value ${amount_usdt:.2f} below Binance minimum ($5). Please increase margin."}

            # 2. Ensure market rules loaded
            await self._ensure_markets_loaded(client)
            
            # 3. Map Side (LONG/SHORT -> BUY/SELL)
            order_side = side.upper()
            if order_side == 'LONG':
                order_side = 'buy'
                close_side = 'sell'
            elif order_side == 'SHORT':
                order_side = 'sell'
                close_side = 'buy'
            else:
                order_side = side.lower() # Fallback
                close_side = 'sell' if order_side == 'buy' else 'buy'

            # 4. Calculate quantity
            # Fetch ticker in thread
            ticker = await asyncio.to_thread(client.fetch_ticker, symbol)
            current_price = ticker['last']

            # Notional Value = Margin * Leverage
            notional_value = amount_usdt
            raw_quantity = notional_value / current_price

            # 5. Apply Precision using CCXT built-in method
            # amount_to_precision returns a string, we need to pass float/string to create_order
            
            # Check if symbol is in client's market cache first, if not reload CLIENT markets
            if symbol not in client.markets:
                 logger.warning(f"[EXEC] Symbol {symbol} not in client cache, reloading...")
                 await asyncio.to_thread(client.load_markets, True)
                 # Update local cache as well
                 self.markets = client.markets
            
            if symbol not in client.markets:
                 print(f"DEBUG_EXEC_ERROR: Symbol {symbol} not found after reload")
                 return {"error": f"Symbol {symbol} not found on Binance Futures"}

            quantity_str = client.amount_to_precision(symbol, raw_quantity)
            quantity = float(quantity_str)
            
            # Use safe get for precision, reload if necessary already handled above but double check
            if symbol not in self.markets:
                 # Last ditch effort
                 self.markets = await asyncio.to_thread(client.load_markets, True)

            price_precision = self.markets[symbol]['precision']['price']

            print(f"DEBUG_EXEC_CALC: {symbol} Price={current_price}, Notional=${notional_value}, RawQty={raw_quantity}, FinalQty={quantity}")

            # Double-check Min Notional after precision rounding
            actual_notional = quantity * current_price
            if actual_notional < 5.0:
                print(f"DEBUG_EXEC_ERROR: Actual notional ${actual_notional} too low after rounding")
                return {"error": f"Order value ${actual_notional:.2f} below Binance minimum ($5) after precision rounding (Qty: {quantity})"}

            logger.info(f"[EXEC] Placing Order: {side} ({order_side}) {symbol} | Notional: ${notional_value:.2f} | Leverage: {leverage}x | Qty: {quantity}")

            # 6. Set Leverage First
            try:
                await asyncio.to_thread(client.set_leverage, leverage, symbol)
            except Exception as e:
                print(f"DEBUG_EXEC_WARN: Set leverage failed/skipped: {e}")

            # Recalculate Qty for LIMIT based on execution price
            exec_price = current_price
            if order_type.upper() == 'LIMIT' and limit_price:
                exec_price = limit_price
                
            notional_value = amount_usdt
            raw_quantity = notional_value / exec_price
            
            # Apply Precision
            # Reload logic already done above
            quantity_str = client.amount_to_precision(symbol, raw_quantity)
            quantity = float(quantity_str)
            
            # Prepare Order Params
            extra_params = {'positionSide': 'BOTH'}
            formatted_price = None
            
            if order_type.upper() == 'LIMIT':
                if not limit_price:
                    return {"error": "Limit price required for LIMIT order"}
                
                formatted_price = float(client.price_to_precision(symbol, limit_price))
                extra_params['timeInForce'] = 'GTC'
                logger.info(f"[EXEC] Placing LIMIT Order: {symbol} @ {formatted_price}")
            
            # 7. Send Entry Order (IN THREAD)
            order = await asyncio.to_thread(
                client.create_order,
                symbol,
                order_type.lower(),
                order_side,
                quantity,
                formatted_price, # Price (None for Market)
                extra_params
            )

            logger.info(f"[EXEC] Order Filled! ID: {order['id']} @ {order['average']}")
            
            filled_qty = float(order['filled'])
            avg_price = float(order['average'] or current_price)
            
            sl_order_id = None
            tp_order_id = None
            
            # 8. Place SL/TP Orders (Strategy Orders) using Standard Endpoint
            # WAIT 1s to ensure Binance backend registers the position (Critical for SL/TP success)
            await asyncio.sleep(1.0)

            # Uses /fapi/v1/order via client.create_order
            if filled_qty > 0:
                # Place STOP LOSS
                if sl_price and sl_price > 0:
                    try:
                        sl_price_str = client.price_to_precision(symbol, sl_price)
                        logger.info(f"[EXEC] Placing SL: {symbol} {close_side} @ {sl_price_str}")
                        
                        sl_order = await asyncio.to_thread(
                            client.create_order,
                            symbol,
                            'STOP_MARKET',
                            close_side,
                            quantity,
                            None,
                            {
                                'stopPrice': float(sl_price_str),
                                'workingType': 'MARK_PRICE',
                                'closePosition': True,
                                'timeInForce': 'GTC'
                            }
                        )
                        sl_order_id = str(sl_order.get('id'))
                        logger.info(f"[EXEC] SL Placed: ID {sl_order_id}")
                    except Exception as e:
                        logger.error(f"[EXEC] Failed to place SL: {e}")
                        # Retry once after shorter delay
                        await asyncio.sleep(1.0)
                        try:
                            sl_order = await asyncio.to_thread(client.create_order, symbol, 'STOP_MARKET', close_side, quantity, None, {
                                'stopPrice': float(sl_price_str), 
                                'workingType': 'MARK_PRICE',
                                'closePosition': True,
                                'timeInForce': 'GTC'
                            })
                            sl_order_id = str(sl_order.get('id'))
                            logger.info(f"[EXEC] SL Placed (Retry): ID {sl_order_id}")
                        except Exception as retry_e:
                            logger.error(f"[EXEC] SL Retry Failed: {retry_e}")

                # Place TAKE PROFIT
                if tp_price and tp_price > 0:
                    try:
                        tp_price_str = client.price_to_precision(symbol, tp_price)
                        logger.info(f"[EXEC] Placing TP: {symbol} {close_side} @ {tp_price_str}")
                        
                        tp_order = await asyncio.to_thread(
                            client.create_order,
                            symbol,
                            'TAKE_PROFIT_MARKET',
                            close_side,
                            quantity,
                            None,
                            {
                                'stopPrice': float(tp_price_str),
                                'workingType': 'MARK_PRICE',
                                'closePosition': True,
                                'timeInForce': 'GTC'
                            }
                        )
                        tp_order_id = str(tp_order.get('id'))
                        logger.info(f"[EXEC] TP Placed: ID {tp_order_id}")
                    except Exception as e:
                        logger.error(f"[EXEC] Failed to place TP: {e}")

            # 9. Return Success
            return {
                "status": "filled",
                "order_id": order['id'],
                "avg_price": avg_price,
                "filled_qty": filled_qty,
                "sl_order_id": sl_order_id,
                "tp_order_id": tp_order_id,
                "message": f"Order filled @ {avg_price:.4f}"
            }

        except Exception as e:
            error_msg = str(e)
            # Try to extract specific Binance error message if available
            if hasattr(e, 'message'): 
                error_msg = e.message
            elif hasattr(e, 'msg'):
                error_msg = e.msg
                
            logger.error(f"[EXEC] Order execution failed for {symbol}: {error_msg}")
            
            # Return detailed error to the user
            return {
                "error": f"Execution Failed: {error_msg}",
                "details": str(e)
            }
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
        Fetch USDT balance from Binance Futures (Event-Driven Prefered)
        """
        # 0. Check Real-Time Cache (0ms latency)
        # Use simple Time-to-Live (TTL) of 60s if stream is active
        # Or if stream is just active and cache is populated, use it.
        import time
        if user_stream.is_running and user_stream.cache["balance"].get("total") > 0:
            last_update = user_stream.cache["balance"].get("updated_at", 0)
            # If data is fresh enough (e.g. < 5 mins) or just trust WS
            if time.time() - last_update < 300: 
                 logger.info("[EXEC] Using Cached Balance (WS Speed)")
                 return {
                    "asset": "USDT",
                    "total": user_stream.cache["balance"]["total"],
                    "free": user_stream.cache["balance"]["free"]
                 }

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
            
            # Update Cache since we fetched it manually
            if user_stream.is_running:
                user_stream.cache["balance"] = {
                    "total": float(total),
                    "free": float(free),
                    "updated_at": time.time()
                }

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

# WebSocket User Data Stream (v10.1 - Cleaned)
class UserDataStream:
    def __init__(self, executor_ref):
        self.executor = executor_ref
        self.listen_key = None
        self.ws_url = "wss://fstream.binance.com/ws/"
        self.is_running = False
        self.last_update = 0
        
        # In-Memory Real-Time Cache
        self.cache = {
            "balance": {"total": 0.0, "free": 0.0, "updated_at": 0},
            "positions": {}  # symbol -> {qty, entryPrice, pnl, etc}
        }

    async def start_stream(self, api_key, api_secret):
        """Start the User Data Stream for a specific user"""
        if self.is_running: return
        
        self.is_running = True
        logger.info("[WS] Starting User Data Stream (Event-Driven Mode)...")
        
        # 1. Get Listen Key
        self.listen_key = await self._get_listen_key(api_key, api_secret)
        if not self.listen_key:
            logger.error("[WS] Failed to get listen key. WS Disabled.")
            self.is_running = False
            return

        # 2. Start Keep-Alive Loop (Every 50 mins)
        asyncio.create_task(self._keep_alive_loop(api_key, api_secret))

        # 3. Start WS Listener
        asyncio.create_task(self._listen_socket())

    async def _get_listen_key(self, api_key, api_secret):
        """Fetch listenKey from Binance REST API"""
        import requests
        url = "https://fapi.binance.com/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": api_key}
        try:
            resp = await asyncio.to_thread(requests.post, url, headers=headers)
            if resp.status_code == 200:
                return resp.json().get("listenKey")
            logger.error(f"[WS] ListenKey Error: {resp.text}")
        except Exception as e:
            logger.error(f"[WS] ListenKey Exception: {e}")
        return None

    async def _keep_alive_loop(self, api_key, api_secret):
        """Renew listenKey every 50 minutes"""
        import requests
        url = "https://fapi.binance.com/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": api_key}
        
        while self.is_running:
            await asyncio.sleep(50 * 60) # 50 mins
            try:
                if self.listen_key:
                    await asyncio.to_thread(requests.put, url, headers=headers)
                    logger.info("[WS] ListenKey renewed")
            except Exception as e:
                logger.error(f"[WS] Keep-alive failed: {e}")

    async def _listen_socket(self):
        """Connect to WebSocket and listen for events"""
        import websockets
        uri = f"{self.ws_url}{self.listen_key}"
        
        while self.is_running:
            try:
                async with websockets.connect(uri) as websocket:
                    logger.info("[WS] Connected to Binance User Stream")
                    while self.is_running:
                        msg = await websocket.recv()
                        await self._handle_message(msg)
            except Exception as e:
                logger.error(f"[WS] Connection error: {e}")
                await asyncio.sleep(5) # Reconnect delay

    async def _handle_message(self, msg_str):
        """Process WS messages (ACCOUNT_UPDATE & ORDER_TRADE_UPDATE)"""
        try:
            data = json.loads(msg_str)
            event_type = data.get("e")
            import time
            now = time.time()
            
            # --- Event: ACCOUNT_UPDATE (Balance & Position specific changes) ---
            if event_type == "ACCOUNT_UPDATE":
                update_data = data.get("a", {})
                
                # 1. Handle Balance (B)
                balances = update_data.get("B", [])
                for asset_info in balances:
                    if asset_info.get("a") == "USDT":
                        wallet_balance = float(asset_info.get("wb"))
                        cross_wallet = float(asset_info.get("cw"))
                        
                        # Update Cache
                        self.cache["balance"] = {
                            "total": wallet_balance,
                            "free": cross_wallet, # Approximation, usually use crossWalletBalance
                            "updated_at": now
                        }
                        logger.debug(f"[WS] Balance Updated: {wallet_balance} USDT")

                # 2. Handle Positions (P) inside ACCOUNT_UPDATE
                positions = update_data.get("P", [])
                for pos in positions:
                    symbol = pos.get("s")
                    amount = float(pos.get("pa"))
                    entry_price = float(pos.get("ep"))
                    upnl = float(pos.get("up"))
                    
                    self.cache["positions"][symbol] = {
                        "amount": amount,
                        "entry_price": entry_price,
                        "unrealized_pnl": upnl,
                        "updated_at": now
                    }
                    if amount == 0:
                        # Optional: Cleanup zero positions or keep for history?
                        # Keeping it as 0 is safer for referencing close status
                        pass

            # --- Event: ORDER_TRADE_UPDATE (Order status changes) ---
            elif event_type == "ORDER_TRADE_UPDATE":
                order_data = data.get("o", {})
                symbol = order_data.get("s")
                status = order_data.get("X") # NEW, PARTIALLY_FILLED, FILLED, CANCELED
                side = order_data.get("S")
                
                logger.info(f"[WS] Order Update: {symbol} {side} -> {status}")
                # We can use this to trigger specific notifications if needed

        except Exception as e:
            pass # Silent fail to prevent loop crash

# Global Instance
executor = BinanceExecutor()
user_stream = UserDataStream(executor)
