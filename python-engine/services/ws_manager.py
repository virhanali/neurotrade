
import asyncio
import json
import logging
import time
from typing import Dict, Optional, Callable, Awaitable
import websockets
from websockets.exceptions import ConnectionClosed
import aiohttp
from config import settings

# Configure logging
logger = logging.getLogger("WS_MANAGER")

class WebSocketManager:
    """
    Manages User Data Streams (Private) for real-time Order and Balance updates.
    Replaces REST polling for account status.
    """
    def __init__(self):
        self.base_ws_url = settings.BINANCE_WS_URL.replace("wss://fstream.binance.com/ws", "wss://fstream.binance.com/ws") # Ensure base
        if "testnet" in self.base_ws_url:
             self.base_rest_url = "https://testnet.binancefuture.com"
        else:
             self.base_rest_url = "https://fapi.binance.com"
        
        # User Streams
        # key: api_key, value: {"listen_key": str, "ws_task": Task, "keep_alive_task": Task, "balance_cache": Dict}
        self.active_users: Dict[str, Dict] = {}
        
        # Callbacks
        self.on_order_update: Optional[Callable[[Dict, str, str], Awaitable[None]]] = None
        
        self.running = False

    async def start(self):
        """Start the WebSocket Manager"""
        self.running = True
        logger.info("Starting User Data Stream Manager...")

    async def stop(self):
        """Stop all streams"""
        self.running = False
        
        # Stop all user streams
        for api_key in list(self.active_users.keys()):
            await self.stop_user_stream(api_key)

    def get_cached_balance(self, api_key: str) -> Optional[float]:
        """Get cached balance for user if available"""
        if api_key in self.active_users:
            return self.active_users[api_key].get("total_balance")
        return None

    async def start_user_stream(self, api_key: str, api_secret: str):
        """
        Start a User Data Stream for a specific user.
        """
        if api_key in self.active_users:
            # Stream already active
            return

        try:
            # 1. Get Listen Key via REST
            listen_key = await self._get_listen_key(api_key)
            if not listen_key:
                logger.error("Failed to obtain Listen Key")
                return

            # 2. Start WS Connection
            ws_task = asyncio.create_task(self._user_stream_listener(listen_key, api_key, api_secret))
            
            # 3. Start Keep-Alive Task (Ping every 50 mins)
            keep_alive_task = asyncio.create_task(self._keep_alive_listen_key(listen_key, api_key))
            
            self.active_users[api_key] = {
                "listen_key": listen_key,
                "ws_task": ws_task,
                "keep_alive_task": keep_alive_task,
                "api_secret": api_secret,
                "total_balance": 0.0, # Will be updated by WS
                "available_balance": 0.0
            }
            logger.info(f"Started User Stream for ...{api_key[-4:]}")

        except Exception as e:
            logger.error(f"Failed to start user stream: {e}")

    async def stop_user_stream(self, api_key: str):
        if api_key in self.active_users:
            user_data = self.active_users[api_key]
            
            if user_data.get("ws_task"):
                user_data["ws_task"].cancel()
            if user_data.get("keep_alive_task"):
                user_data["keep_alive_task"].cancel()
                
            del self.active_users[api_key]
            logger.info(f"Stopped User Stream for ...{api_key[-4:]}")

    async def _get_listen_key(self, api_key: str) -> Optional[str]:
        async with aiohttp.ClientSession() as session:
            try:
                url = f"{self.base_rest_url}/fapi/v1/listenKey"
                headers = {"X-MBX-APIKEY": api_key}
                async with session.post(url, headers=headers) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("listenKey")
                    else:
                        logger.error(f"Error getting ListenKey: {resp.status} {await resp.text()}")
                        return None
            except Exception as e:
                logger.error(f"Error getting ListenKey: {e}")
                return None

    async def _keep_alive_listen_key(self, listen_key: str, api_key: str):
        url = f"{self.base_rest_url}/fapi/v1/listenKey"
        headers = {"X-MBX-APIKEY": api_key}
        
        while self.running:
            await asyncio.sleep(50 * 60) # 50 minutes
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.put(url, headers=headers) as resp:
                        if resp.status == 200:
                            logger.debug(f"ListenKey Keep-Alive success for ...{api_key[-4:]}")
                        else:
                            logger.warning(f"ListenKey Keep-Alive failed: {resp.status}")
                            # If ListenKey is invalid, we should probably restart the stream
            except Exception as e:
                 logger.error(f"ListenKey Keep-Alive error: {e}")

    async def _user_stream_listener(self, listen_key: str, api_key: str, api_secret: str):
        # Construct WS URL with listenKey
        # Official format: wss://fstream.binance.com/ws/<listenKey>
        url = f"{settings.BINANCE_WS_URL}/{listen_key}"
        if "testnet" in settings.BINANCE_WS_URL:
             url = f"{settings.BINANCE_WS_URL}/ws/{listen_key}"

        while self.running:
            try:
                async with websockets.connect(url) as ws:
                    logger.info(f"Connected to User Stream for ...{api_key[-4:]}")
                    
                    while self.running:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        
                        # FIX: Handle potential list messages or non-dict payloads
                        if isinstance(data, list):
                            # Some keep-alive or batched messages might be lists
                            # logger.debug(f"[WS] Received list payload (ignoring): {data}")
                            continue
                            
                        if not isinstance(data, dict):
                             continue

                        event_type = data.get('e')
                        
                        # HANDLE ORDER UPDATES
                        if event_type == 'ORDER_TRADE_UPDATE':
                            order_data = data.get('o', {})
                            status = order_data.get('X') # FILLED, NEW
                            symbol = order_data.get('s')
                            
                            logger.info(f"[WS] Order Update {symbol}: {status}")

                            if status == 'FILLED' or status == 'PARTIALLY_FILLED':
                                # Callback to Execution Service
                                if self.on_order_update:
                                    # Run callback non-blocking
                                    asyncio.create_task(self.on_order_update(order_data, api_key, api_secret))
                                    
                        # HANDLE BALANCE UPDATES
                        elif event_type == 'ACCOUNT_UPDATE':
                            # Data structure based on Binance API
                            # "a": {"B": [...balances...], "P": [...positions...]}
                            update_data = data.get('a', {})
                            balances = update_data.get('B', [])
                            
                            total_wallet_balance = 0.0
                            total_cross_wallet = 0.0
                            
                            for bal in balances:
                                if bal.get('a') == 'USDT':
                                    wallet_balance = float(bal.get('wb', 0))
                                    cross_wallet = float(bal.get('cw', 0))
                                    
                                    # Update cache
                                    if api_key in self.active_users:
                                        self.active_users[api_key]["total_balance"] = wallet_balance
                                        self.active_users[api_key]["available_balance"] = cross_wallet
                                    
                                    logger.debug(f"[WS] Balance Update USDT: {wallet_balance}")

            except ConnectionClosed:
                logger.warning(f"User Stream connection closed for ...{api_key[-4:]}, reconnecting...")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"User Stream error: {e}")
                await asyncio.sleep(5)

# Global Instance
ws_manager = WebSocketManager()
