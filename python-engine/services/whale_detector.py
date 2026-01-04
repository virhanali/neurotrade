"""
Whale Detector Service (v4.2)
Advanced Pump/Dump Detection using:
1. Binance Futures Liquidation Stream (Real-time)
2. Order Book Imbalance Analysis (Top 20 levels)
3. Large Trade Detection (Aggressor Analysis)
4. Open Interest Delta (Positioning shifts)

This module predicts whale movements BEFORE they happen.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field
from collections import deque
from datetime import datetime, timedelta
import aiohttp
import websockets

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class LiquidationEvent:
    """Single liquidation event"""
    symbol: str
    side: str  # LONG or SHORT
    quantity: float
    price: float
    timestamp: float


@dataclass
class WhaleSignal:
    """Whale detection result"""
    signal: str  # PUMP_IMMINENT, DUMP_IMMINENT, SQUEEZE_LONGS, SQUEEZE_SHORTS, NEUTRAL
    confidence: int  # 0-100
    liquidation_pressure: str  # LONG_HEAVY, SHORT_HEAVY, BALANCED, NONE
    order_imbalance: float  # -100 to +100 (negative = sell heavy, positive = buy heavy)
    large_trades_bias: str  # BUYING, SELLING, MIXED
    reasoning: str
    funding_rate: float = 0.0  # Funding rate percentage (NEW)
    ls_ratio: float = 1.0  # Long/Short ratio (NEW)
    timestamp: float = field(default_factory=time.time)


class WhaleDetector:
    """
    Advanced Whale Detection System for Binance Futures

    Features:
    1. Real-time Liquidation Tracking (WebSocket)
    2. Order Book Depth Analysis
    3. Large Trade Flow Analysis
    4. Open Interest Monitoring
    """

    def __init__(self):
        # Liquidation tracking (rolling 5-minute window)
        self.liquidations: Dict[str, deque] = {}  # symbol -> deque of LiquidationEvent
        self.LIQUIDATION_WINDOW = 300  # 5 minutes

        # Order book cache
        self.orderbook_cache: Dict[str, Dict] = {}  # symbol -> {bids, asks, timestamp}
        self.ORDERBOOK_TTL = 5  # seconds

        # Large trades tracking
        self.large_trades: Dict[str, deque] = {}  # symbol -> deque of trades
        self.LARGE_TRADE_THRESHOLD = 50000  # $50K USD minimum for "large"

        # Open Interest cache
        self.oi_cache: Dict[str, Dict] = {}  # symbol -> {value, timestamp}
        self.OI_TTL = 60  # seconds

        # WebSocket state
        self.ws_connected = False
        self.ws_task: Optional[asyncio.Task] = None

        # HTTP session for REST calls
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session"""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        """Cleanup resources"""
        if self._session and not self._session.closed:
            await self._session.close()
        if self.ws_task:
            self.ws_task.cancel()

    # ========================
    # 1. LIQUIDATION TRACKING
    # ========================

    async def start_liquidation_stream(self):
        """Start WebSocket connection for all liquidation events"""
        url = "wss://fstream.binance.com/ws/!forceOrder@arr"

        while True:
            try:
                async with websockets.connect(url, ping_interval=20) as ws:
                    self.ws_connected = True
                    logger.info("[WHALE] Liquidation stream connected")

                    async for message in ws:
                        await self._process_liquidation(message)

            except Exception as e:
                self.ws_connected = False
                logger.warning(f"[WHALE] Liquidation stream error: {e}, reconnecting...")
                await asyncio.sleep(5)

    async def _process_liquidation(self, message: str):
        """Process incoming liquidation event"""
        try:
            data = json.loads(message)
            order = data.get('o', {})

            symbol = order.get('s', '')  # e.g., BTCUSDT
            side = 'LONG' if order.get('S') == 'SELL' else 'SHORT'  # If SELL, it was a LONG being liquidated
            qty = float(order.get('q', 0))
            price = float(order.get('p', 0))

            event = LiquidationEvent(
                symbol=symbol,
                side=side,
                quantity=qty * price,  # Convert to USD value
                price=price,
                timestamp=time.time()
            )

            # Store in rolling window
            if symbol not in self.liquidations:
                self.liquidations[symbol] = deque(maxlen=1000)
            self.liquidations[symbol].append(event)

            # Log significant liquidations
            if event.quantity > 100000:  # > $100K
                logger.info(f"[WHALE] 🔥 LARGE LIQ: {symbol} {side} ${event.quantity:,.0f}")

        except Exception as e:
            logger.error(f"[WHALE] Liquidation parse error: {e}")

    def get_liquidation_pressure(self, symbol: str) -> Tuple[str, float, float]:
        """
        Analyze recent liquidations to determine pressure direction

        Returns:
            (pressure_type, long_liq_usd, short_liq_usd)
        """
        normalized = symbol.replace('/', '').upper()
        if normalized not in self.liquidations:
            return ('NONE', 0, 0)

        now = time.time()
        cutoff = now - self.LIQUIDATION_WINDOW

        long_liq = 0.0
        short_liq = 0.0

        for event in self.liquidations[normalized]:
            if event.timestamp >= cutoff:
                if event.side == 'LONG':
                    long_liq += event.quantity
                else:
                    short_liq += event.quantity

        total = long_liq + short_liq
        if total < 10000:  # Less than $10K total - insignificant
            return ('NONE', long_liq, short_liq)

        ratio = long_liq / (short_liq + 1)  # +1 to avoid division by zero

        if ratio > 2.0:
            return ('LONG_HEAVY', long_liq, short_liq)
        elif ratio < 0.5:
            return ('SHORT_HEAVY', long_liq, short_liq)
        else:
            return ('BALANCED', long_liq, short_liq)

    # ========================
    # 2. ORDER BOOK ANALYSIS
    # ========================

    async def fetch_orderbook(self, symbol: str, depth: int = 20) -> Optional[Dict]:
        """Fetch order book depth from Binance Futures"""
        normalized = symbol.replace('/', '').upper()

        # Check cache
        if normalized in self.orderbook_cache:
            cached = self.orderbook_cache[normalized]
            if time.time() - cached['timestamp'] < self.ORDERBOOK_TTL:
                return cached

        try:
            session = await self.get_session()
            url = f"https://fapi.binance.com/fapi/v1/depth?symbol={normalized}&limit={depth}"

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()

                    # Parse bids and asks
                    bids = [(float(p), float(q)) for p, q in data.get('bids', [])]
                    asks = [(float(p), float(q)) for p, q in data.get('asks', [])]

                    result = {
                        'bids': bids,
                        'asks': asks,
                        'timestamp': time.time()
                    }

                    self.orderbook_cache[normalized] = result
                    return result

        except Exception as e:
            logger.error(f"[WHALE] Order book fetch error for {symbol}: {e}")

        return None

    def calculate_order_imbalance(self, orderbook: Dict) -> float:
        """
        Calculate buy/sell imbalance from order book

        Returns:
            Float from -100 (all sells) to +100 (all buys)
        """
        if not orderbook:
            return 0.0

        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])

        if not bids or not asks:
            return 0.0

        # Calculate total value (price * quantity) for each side
        bid_value = sum(price * qty for price, qty in bids)
        ask_value = sum(price * qty for price, qty in asks)

        total = bid_value + ask_value
        if total == 0:
            return 0.0

        # Imbalance: positive = more buy orders, negative = more sell orders
        imbalance = ((bid_value - ask_value) / total) * 100

        return imbalance

    def detect_walls(self, orderbook: Dict, current_price: float) -> Dict:
        """
        Detect buy/sell walls in the order book

        Returns:
            Dict with wall locations and sizes
        """
        if not orderbook:
            return {'buy_wall': None, 'sell_wall': None}

        bids = orderbook.get('bids', [])
        asks = orderbook.get('asks', [])

        # Find largest orders within 1% of current price
        buy_wall = None
        sell_wall = None

        for price, qty in bids:
            if price >= current_price * 0.99:  # Within 1% below
                value = price * qty
                if value > 100000:  # $100K+ wall
                    if buy_wall is None or value > buy_wall['value']:
                        buy_wall = {'price': price, 'value': value}

        for price, qty in asks:
            if price <= current_price * 1.01:  # Within 1% above
                value = price * qty
                if value > 100000:  # $100K+ wall
                    if sell_wall is None or value > sell_wall['value']:
                        sell_wall = {'price': price, 'value': value}

        return {
            'buy_wall': buy_wall,
            'sell_wall': sell_wall
        }

    # ========================
    # 3. OPEN INTEREST ANALYSIS
    # ========================

    async def fetch_open_interest(self, symbol: str) -> Optional[float]:
        """Fetch current open interest from Binance Futures"""
        normalized = symbol.replace('/', '').upper()

        # Check cache
        if normalized in self.oi_cache:
            cached = self.oi_cache[normalized]
            if time.time() - cached['timestamp'] < self.OI_TTL:
                return cached['value']

        try:
            session = await self.get_session()
            url = f"https://fapi.binance.com/fapi/v1/openInterest?symbol={normalized}"

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    oi = float(data.get('openInterest', 0))

                    self.oi_cache[normalized] = {
                        'value': oi,
                        'timestamp': time.time()
                    }
                    return oi

        except Exception as e:
            logger.error(f"[WHALE] Open interest fetch error for {symbol}: {e}")

        return None

    # ========================
    # 5. FUNDING RATE ANALYSIS (NEW)
    # ========================

    async def fetch_funding_rate(self, symbol: str) -> Optional[Dict]:
        """
        Fetch current funding rate from Binance Futures
        
        Funding Rate interpretation:
        - Positive: Longs pay shorts = Market is bullish/overleveraged longs = BEARISH signal
        - Negative: Shorts pay longs = Market is bearish/overleveraged shorts = BULLISH signal
        - Extreme (>0.1% or <-0.1%): Strong contrarian signal
        """
        normalized = symbol.replace('/', '').upper()

        try:
            session = await self.get_session()
            url = f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={normalized}"

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    funding_rate = float(data.get('lastFundingRate', 0)) * 100  # Convert to percentage
                    mark_price = float(data.get('markPrice', 0))
                    
                    return {
                        'funding_rate': funding_rate,  # e.g., 0.01 means 0.01%
                        'mark_price': mark_price,
                        'next_funding_time': data.get('nextFundingTime', 0)
                    }

        except Exception as e:
            logger.error(f"[WHALE] Funding rate fetch error for {symbol}: {e}")

        return None

    # ========================
    # 6. LONG/SHORT RATIO (NEW)
    # ========================

    async def fetch_long_short_ratio(self, symbol: str) -> Optional[Dict]:
        """
        Fetch Long/Short ratio from Binance Futures
        
        Interpretation:
        - Ratio > 1.5: Too many longs = BEARISH (crowd is usually wrong)
        - Ratio < 0.67: Too many shorts = BULLISH (shorts may get squeezed)
        - Between 0.8-1.2: Balanced
        """
        normalized = symbol.replace('/', '').upper()

        try:
            session = await self.get_session()
            # Top Trader Long/Short Ratio (Accounts)
            url = f"https://fapi.binance.com/futures/data/topLongShortAccountRatio?symbol={normalized}&period=5m&limit=1"

            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data and len(data) > 0:
                        latest = data[0]
                        long_ratio = float(latest.get('longAccount', 50))
                        short_ratio = float(latest.get('shortAccount', 50))
                        ls_ratio = float(latest.get('longShortRatio', 1.0))
                        
                        return {
                            'long_percent': long_ratio,
                            'short_percent': short_ratio,
                            'ls_ratio': ls_ratio  # e.g., 1.5 means 60% long / 40% short
                        }

        except Exception as e:
            logger.error(f"[WHALE] Long/Short ratio fetch error for {symbol}: {e}")

        return None

    async def fetch_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Fetch recent aggressor trades"""
        normalized = symbol.replace('/', '').upper()

        try:
            session = await self.get_session()
            url = f"https://fapi.binance.com/fapi/v1/trades?symbol={normalized}&limit={limit}"

            async with session.get(url) as resp:
                if resp.status == 200:
                    return await resp.json()

        except Exception as e:
            logger.error(f"[WHALE] Recent trades fetch error for {symbol}: {e}")

        return []

    def analyze_large_trades(self, trades: List[Dict]) -> Tuple[str, float, float]:
        """
        Analyze recent trades for large buyer/seller activity

        Returns:
            (bias: BUYING/SELLING/MIXED, buy_volume, sell_volume)
        """
        if not trades:
            return ('MIXED', 0, 0)

        buy_vol = 0.0
        sell_vol = 0.0

        for trade in trades:
            price = float(trade.get('price', 0))
            qty = float(trade.get('qty', 0))
            is_maker = trade.get('isBuyerMaker', False)

            value = price * qty

            # Only count "large" trades
            if value >= self.LARGE_TRADE_THRESHOLD:
                if is_maker:
                    # Buyer is maker = Seller is aggressor (taker)
                    sell_vol += value
                else:
                    # Seller is maker = Buyer is aggressor (taker)
                    buy_vol += value

        total = buy_vol + sell_vol
        if total < self.LARGE_TRADE_THRESHOLD:
            return ('MIXED', buy_vol, sell_vol)

        ratio = buy_vol / (sell_vol + 1)

        if ratio > 1.5:
            return ('BUYING', buy_vol, sell_vol)
        elif ratio < 0.67:
            return ('SELLING', buy_vol, sell_vol)
        else:
            return ('MIXED', buy_vol, sell_vol)

    # ========================
    # MAIN DETECTION FUNCTION
    # ========================

    async def detect_whale_activity(self, symbol: str, current_price: float = 0) -> WhaleSignal:
        """
        Main function: Analyze all data sources and generate whale signal

        Args:
            symbol: Trading pair (e.g., "BTC/USDT" or "BTCUSDT")
            current_price: Current market price (optional, for wall detection)

        Returns:
            WhaleSignal with prediction and confidence
        """
        normalized = symbol.replace('/', '').upper()

        # Collect all signals in parallel (UPGRADED: +funding +LS ratio)
        try:
            orderbook_task = self.fetch_orderbook(normalized)
            trades_task = self.fetch_recent_trades(normalized)
            oi_task = self.fetch_open_interest(normalized)
            funding_task = self.fetch_funding_rate(normalized)
            ls_ratio_task = self.fetch_long_short_ratio(normalized)

            orderbook, trades, oi, funding, ls_ratio = await asyncio.gather(
                orderbook_task, trades_task, oi_task, funding_task, ls_ratio_task,
                return_exceptions=True
            )

            # Handle exceptions
            if isinstance(orderbook, Exception):
                orderbook = None
            if isinstance(trades, Exception):
                trades = []
            if isinstance(oi, Exception):
                oi = None
            if isinstance(funding, Exception):
                funding = None
            if isinstance(ls_ratio, Exception):
                ls_ratio = None

        except Exception as e:
            logger.error(f"[WHALE] Detection error for {symbol}: {e}")
            return WhaleSignal(
                signal='NEUTRAL',
                confidence=0,
                liquidation_pressure='NONE',
                order_imbalance=0,
                large_trades_bias='MIXED',
                reasoning=f"Detection failed: {e}"
            )

        # 1. Liquidation Pressure
        liq_pressure, long_liq, short_liq = self.get_liquidation_pressure(normalized)

        # 2. Order Book Imbalance
        order_imbalance = self.calculate_order_imbalance(orderbook) if orderbook else 0

        # 3. Wall Detection
        walls = self.detect_walls(orderbook, current_price) if orderbook and current_price > 0 else {}

        # 4. Large Trade Analysis
        trade_bias, buy_vol, sell_vol = self.analyze_large_trades(trades)

        # 5. Funding Rate Analysis (NEW)
        funding_rate = funding.get('funding_rate', 0) if funding else 0

        # 6. Long/Short Ratio Analysis (NEW)
        ls_ratio_val = ls_ratio.get('ls_ratio', 1.0) if ls_ratio else 1.0

        # ========================
        # SIGNAL SYNTHESIS (UPGRADED)
        # ========================

        signal = 'NEUTRAL'
        confidence = 0
        reasons = []

        # === PUMP DETECTION ===
        pump_score = 0

        # Heavy short liquidations = shorts getting rekt = potential pump
        if liq_pressure == 'SHORT_HEAVY':
            pump_score += 30
            reasons.append(f"Short liquidations: ${short_liq:,.0f}")

        # Positive order imbalance = more buyers waiting
        if order_imbalance > 15:
            pump_score += 25
            reasons.append(f"Order book buy-heavy: {order_imbalance:+.1f}%")

        # Large buys dominating
        if trade_bias == 'BUYING':
            pump_score += 25
            reasons.append(f"Large buyers active: ${buy_vol:,.0f}")

        # Buy wall support
        if walls.get('buy_wall'):
            pump_score += 20
            reasons.append(f"Buy wall at ${walls['buy_wall']['price']:,.2f}")

        # CONTRARIAN: Negative funding rate = shorts are paying = BULLISH
        if funding_rate < -0.03:  # < -0.03%
            pump_score += 20
            reasons.append(f"Funding bearish: {funding_rate:.3f}% (contrarian BULL)")
        elif funding_rate < -0.01:
            pump_score += 10
            reasons.append(f"Funding slightly bearish: {funding_rate:.3f}%")

        # CONTRARIAN: Too many shorts = squeeze potential = BULLISH
        if ls_ratio_val < 0.7:  # 70% shorts
            pump_score += 20
            reasons.append(f"L/S ratio {ls_ratio_val:.2f} (SHORT crowded, squeeze risk)")
        elif ls_ratio_val < 0.85:
            pump_score += 10
            reasons.append(f"L/S ratio slightly short: {ls_ratio_val:.2f}")

        # === DUMP DETECTION ===
        dump_score = 0

        # Heavy long liquidations = longs getting rekt = potential dump
        if liq_pressure == 'LONG_HEAVY':
            dump_score += 30
            reasons.append(f"Long liquidations: ${long_liq:,.0f}")

        # Negative order imbalance = more sellers waiting
        if order_imbalance < -15:
            dump_score += 25
            reasons.append(f"Order book sell-heavy: {order_imbalance:+.1f}%")

        # Large sells dominating
        if trade_bias == 'SELLING':
            dump_score += 25
            reasons.append(f"Large sellers active: ${sell_vol:,.0f}")

        # Sell wall resistance
        if walls.get('sell_wall'):
            dump_score += 20
            reasons.append(f"Sell wall at ${walls['sell_wall']['price']:,.2f}")

        # CONTRARIAN: High positive funding rate = longs are paying = BEARISH
        if funding_rate > 0.05:  # > 0.05%
            dump_score += 20
            reasons.append(f"Funding bullish: {funding_rate:.3f}% (contrarian BEAR)")
        elif funding_rate > 0.02:
            dump_score += 10
            reasons.append(f"Funding slightly bullish: {funding_rate:.3f}%")

        # CONTRARIAN: Too many longs = dump risk = BEARISH
        if ls_ratio_val > 1.5:  # 60% longs
            dump_score += 20
            reasons.append(f"L/S ratio {ls_ratio_val:.2f} (LONG crowded, dump risk)")
        elif ls_ratio_val > 1.2:
            dump_score += 10
            reasons.append(f"L/S ratio slightly long: {ls_ratio_val:.2f}")

        # === SQUEEZE DETECTION ===
        # If many longs are liquidated BUT price hasn't dropped much = whale accumulating
        # If many shorts are liquidated BUT price hasn't pumped much = whale distributing

        # === FINAL SIGNAL ===
        if pump_score >= 60:
            signal = 'PUMP_IMMINENT'
            confidence = min(95, pump_score)
        elif dump_score >= 60:
            signal = 'DUMP_IMMINENT'
            confidence = min(95, dump_score)
        elif liq_pressure == 'LONG_HEAVY' and pump_score < 30:
            signal = 'SQUEEZE_LONGS'
            confidence = 50 + int((long_liq / 100000) * 10)  # Scale by liq size
        elif liq_pressure == 'SHORT_HEAVY' and dump_score < 30:
            signal = 'SQUEEZE_SHORTS'
            confidence = 50 + int((short_liq / 100000) * 10)
        else:
            signal = 'NEUTRAL'
            confidence = 100 - max(pump_score, dump_score)  # More neutral = higher confidence in neutral

        confidence = min(100, max(0, confidence))

        return WhaleSignal(
            signal=signal,
            confidence=confidence,
            liquidation_pressure=liq_pressure,
            order_imbalance=order_imbalance,
            large_trades_bias=trade_bias,
            reasoning=' | '.join(reasons) if reasons else 'No significant whale activity',
            funding_rate=funding_rate,
            ls_ratio=ls_ratio_val
        )

    def get_whale_metrics(self, whale_signal: WhaleSignal) -> Dict:
        """
        Convert WhaleSignal to metrics dict for AI prompt injection
        """
        return {
            'whale_signal': whale_signal.signal,
            'whale_confidence': whale_signal.confidence,
            'liquidation_pressure': whale_signal.liquidation_pressure,
            'order_imbalance': whale_signal.order_imbalance,
            'large_trades_bias': whale_signal.large_trades_bias,
            'funding_rate': whale_signal.funding_rate,
            'ls_ratio': whale_signal.ls_ratio,
            'whale_reasoning': whale_signal.reasoning
        }


# Global instance
whale_detector = WhaleDetector()


async def start_whale_monitoring():
    """Start background whale monitoring (call from main.py)"""
    await whale_detector.start_liquidation_stream()


# Convenience function for synchronous code
def get_whale_signal_sync(symbol: str, current_price: float = 0) -> Dict:
    """
    Synchronous wrapper for whale detection
    Use this from non-async code like screener.py
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If already in async context, create a new task
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    whale_detector.detect_whale_activity(symbol, current_price)
                )
                signal = future.result(timeout=5)
        else:
            signal = loop.run_until_complete(
                whale_detector.detect_whale_activity(symbol, current_price)
            )
        return whale_detector.get_whale_metrics(signal)
    except Exception as e:
        logger.warning(f"[WHALE] Sync detection failed: {e}")
        return {
            'whale_signal': 'NEUTRAL',
            'whale_confidence': 0,
            'liquidation_pressure': 'NONE',
            'order_imbalance': 0,
            'large_trades_bias': 'MIXED',
            'whale_reasoning': 'Detection unavailable'
        }
