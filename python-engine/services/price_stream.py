"""
WebSocket Price Stream Service
Connects to Binance Futures WebSocket for real-time price updates
"""

import asyncio
import json
import logging
from typing import Dict, Optional
from datetime import datetime

import websockets
from websockets.exceptions import ConnectionClosed
from config import settings

logger = logging.getLogger(__name__)


class PriceStreamService:
    """
    Real-time price stream using Binance Futures WebSocket.
    Maintains an in-memory cache of all prices, updated in real-time.
    """
    
    # Binance Futures WebSocket endpoint for all tickers (Full Ticker)
    # !ticker@arr provides Price, Volume, and Change% needed for both Bodyguard and Screener
    WS_URL = settings.BINANCE_WS_URL
    
    def __init__(self):
        # prices: symbol -> price (for Bodyguard)
        self.prices: Dict[str, float] = {}
        # tickers: symbol -> full ticker data dict (for Screener)
        self.tickers: Dict[str, Dict] = {}
        self.last_update: Optional[datetime] = None
        self.last_error: Optional[str] = None
        self._running = False
        self._ws = None
        self._task = None
    
    async def start(self):
        """Start the WebSocket connection in background"""
        if self._running:
            logger.warning("Price stream already running")
            return
        
        self._running = True
        self.last_error = None
        self._task = asyncio.create_task(self._run_forever())
        logger.info("[WS] Price stream started")
    
    async def stop(self):
        """Stop the WebSocket connection"""
        self._running = False
        if self._ws:
            await self._ws.close()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("[WS] Price stream stopped")
    
    async def _run_forever(self):
        """Main loop with auto-reconnection"""
        reconnect_delay = 5
        max_reconnect_delay = 60
        
        while self._running:
            try:
                await self._connect_and_stream()
                # Reset delay on successful connection
                reconnect_delay = 5
                self.last_error = None
            except ConnectionClosed as e:
                self.last_error = f"ConnectionClosed: {e.code} - {e.reason}"
                logger.warning(f"WebSocket connection closed: {self.last_error}")
                if self._running:
                    logger.info(f"Reconnecting in {reconnect_delay} seconds...")
                    await asyncio.sleep(reconnect_delay)
                    # Exponential backoff with max limit
                    reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
            except Exception as e:
                self.last_error = str(e)
                logger.error(f"WebSocket error: {e}")
                if self._running:
                    logger.info(f"Reconnecting in {reconnect_delay} seconds...")
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 1.5, max_reconnect_delay)
    
    async def _connect_and_stream(self):
        """Connect to WebSocket and process messages"""
        logger.info(f"Connecting to {self.WS_URL}")
        
        async with websockets.connect(
            self.WS_URL,
            ping_interval=30,      # Send ping every 30s (was 20)
            ping_timeout=30,       # Wait 30s for pong (was 10) - more tolerant
            close_timeout=10,      # Allow 10s for graceful close (was 5)
            max_size=10 * 1024 * 1024,  # 10MB max message size
        ) as ws:
            self._ws = ws
            logger.info("[OK] WebSocket connected")
            
            try:
                async for message in ws:
                    if not self._running:
                        break
                    await self._process_message(message)
            except asyncio.CancelledError:
                logger.info("WebSocket stream cancelled")
                raise
            finally:
                self._ws = None
    
    async def _process_message(self, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)
            
            # !ticker@arr returns array of tickers
            if isinstance(data, list):
                for ticker in data:
                    symbol = ticker.get('s')  # Symbol
                    price = ticker.get('c')   # Close price (current)
                    
                    if symbol and price:
                        price_float = float(price)
                        self.prices[symbol] = price_float
                        
                        # Store full ticker data for screener
                        # Map WS fields to what Screener expects
                        self.tickers[symbol] = {
                            'symbol': symbol,
                            'price': price_float,
                            'quoteVolume': float(ticker.get('q', 0)),    # 24h Quote Vol
                            'percentage': float(ticker.get('P', 0)),     # 24h Change %
                            'status': 'TRADING'                          # Assume trading if active on WS
                        }
                
                self.last_update = datetime.utcnow()
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse message: {e}")
            
    def get_price(self, symbol: str) -> Optional[float]:
        """Get current price for a symbol"""
        normalized = symbol.replace("/", "").upper()
        return self.prices.get(normalized)
    
    def get_prices(self, symbols: list = None) -> Dict[str, float]:
        """Get prices for multiple symbols (or all if None)"""
        if symbols is None:
            return self.prices.copy()
        
        result = {}
        for symbol in symbols:
            normalized = symbol.replace("/", "").upper()
            if normalized in self.prices:
                result[symbol] = self.prices[normalized]
        return result
        
    def get_all_tickers(self) -> Dict[str, Dict]:
        """Get all full ticker data (for Screener)"""
        return self.tickers.copy()
    
    def get_all_prices(self) -> Dict[str, float]:
        """Get all cached prices"""
        return self.prices.copy()
    
    @property
    def is_connected(self) -> bool:
        """Check if WebSocket is connected"""
        return self._ws is not None and self._ws.open
    
    @property
    def price_count(self) -> int:
        """Number of prices in cache"""
        return len(self.prices)


# Global instance
price_stream = PriceStreamService()
