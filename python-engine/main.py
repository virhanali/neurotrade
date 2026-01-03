"""
NeuroTrade AI - Python Engine
FastAPI service for AI-powered trading signal generation
"""

import asyncio
import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Dict, Optional

from config import settings
from services.data_fetcher import DataFetcher
from services.screener import MarketScreener
from services.charter import ChartGenerator
from services.ai_handler import AIHandler
from services.price_stream import price_stream

# Configure logging with timestamp
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)



app = FastAPI(
    title="NeuroTrade AI Engine",
    description="AI-powered crypto trading signal generator",
    version="0.1.0",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
data_fetcher = DataFetcher()
screener = MarketScreener()
charter = ChartGenerator()
ai_handler = AIHandler()


# Startup/Shutdown events for WebSocket
@app.on_event("startup")
async def startup_event():
    """Start WebSocket price stream on app startup"""
    await price_stream.start()
    print("[WS] WebSocket price stream started")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop WebSocket price stream on app shutdown"""
    await price_stream.stop()
    print("[WS] WebSocket price stream stopped")


# ============================================
# Pydantic Models
# ============================================

class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime


class WelcomeResponse(BaseModel):
    message: str
    version: str


class MarketAnalysisRequest(BaseModel):
    balance: float = Field(default=1000.0, description="Trading balance in USDT")
    mode: str = Field(default="SCALPER", description="Trading mode: SCALPER (M15) or INVESTOR (H1)")
    custom_symbols: Optional[List[str]] = Field(default=None, description="Custom symbols to analyze")


class TradeParams(BaseModel):
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    suggested_leverage: Optional[int] = None
    position_size_usdt: Optional[float] = None


class SignalResult(BaseModel):
    symbol: str
    final_signal: str
    combined_confidence: int
    agreement: bool
    recommendation: str
    logic_reasoning: str
    vision_analysis: str
    trade_params: Optional[TradeParams]


class MarketAnalysisResponse(BaseModel):
    timestamp: datetime
    btc_context: Dict
    opportunities_screened: int
    valid_signals: List[SignalResult]
    execution_time_seconds: float


# ============================================
# API Endpoints
# ============================================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="neurotrade-python-engine",
        timestamp=datetime.utcnow(),
    )


@app.get("/", response_model=WelcomeResponse)
async def root():
    """Root endpoint"""
    return WelcomeResponse(
        message="Welcome to NeuroTrade AI Engine",
        version="0.1.0",
    )


@app.get("/screener/summary")
async def get_screener_summary():
    """Get market screener summary with statistics"""
    try:
        summary = screener.get_screener_summary()
        return summary
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/prices")
async def get_prices(symbols: Optional[str] = None):
    """
    Get real-time prices from WebSocket cache.
    
    Args:
        symbols: Optional comma-separated list of symbols (e.g., "BTCUSDT,ETHUSDT")
                 If not provided, returns all prices.
    
    Returns:
        Dict with prices and metadata
    """
    if symbols:
        symbol_list = [s.strip().upper() for s in symbols.split(",")]
        prices = price_stream.get_prices(symbol_list)
    else:
        prices = price_stream.get_all_prices()
    
    return {
        "prices": prices,
        "count": len(prices),
        "connected": price_stream.is_connected,
        "last_update": price_stream.last_update.isoformat() if price_stream.last_update else None,
    }


@app.post("/analyze/market", response_model=MarketAnalysisResponse)
async def analyze_market(request: MarketAnalysisRequest):
    """
    Analyze market and generate trading signals using Hybrid AI

    Workflow:
    1. Screen market for top opportunities
    2. Fetch BTC context (mode-aware: SCALPER uses 15m, INVESTOR uses 1h)
    3. For each opportunity:
       - Fetch data & generate chart
       - Analyze with DeepSeek (logic) & Gemini (vision) with mode-specific prompts
       - Combine results
    4. Return valid signals (confidence >= 75% and agreement)
    """
    start_time = datetime.utcnow()
    mode = request.mode.upper() if request.mode else "SCALPER"
    
    print(f"\n[TARGET] Market Analysis Started [Mode: {mode}]")

    try:
        # Step 1: Get top opportunities
        if request.custom_symbols:
            top_symbols = request.custom_symbols
        else:
            top_symbols = screener.get_top_opportunities()

        if not top_symbols:
            # No opportunities found - this is normal, not an error
            logging.info("[EMPTY] No trading opportunities passed filters (market too quiet)")
            return MarketAnalysisResponse(
                timestamp=datetime.utcnow(),
                btc_context={},
                opportunities_screened=0,
                valid_signals=[],
                execution_time_seconds=0
            )

        # Step 2: Fetch BTC context (mode-aware)
        btc_context = data_fetcher.fetch_btc_context(mode=mode)

        # --- BTC SLEEP CHECK ---
        # If market is dead flat (< 0.2% move), don't waste AI calls on altcoins.
        # Note: In SCALPER mode, 'pct_change_1h' actually holds the 15m change due to data_fetcher logic.
        btc_volatility = abs(btc_context.get('pct_change_1h', 0))
        if btc_volatility < 0.2:
             logging.info(f"😴 Market Sleepy (BTC Move {btc_volatility}%), skipping Scan to save credits.")
             return MarketAnalysisResponse(
                timestamp=datetime.utcnow(),
                btc_context=btc_context,
                opportunities_screened=0,
                valid_signals=[],
                execution_time_seconds=0
             )

        # Step 3: Analyze each opportunity IN PARALLEL
        # Use Semaphore to limit concurrent AI calls (prevent API rate limit)
        semaphore = asyncio.Semaphore(4)  # Max 4 coins analyzed simultaneously
        
        async def analyze_single_symbol(symbol: str) -> Optional[SignalResult]:
            """Analyze a single symbol - runs concurrently"""
            async with semaphore:
                try:
                    # Fetch target data
                    target_data = await asyncio.to_thread(
                        data_fetcher.fetch_target_data, symbol, mode
                    )

                    # Get chart data
                    chart_timeframe = 'data_15m' if mode == "SCALPER" else 'data_1h'
                    chart_df = target_data.get(chart_timeframe, target_data.get('data_1h', {})).get('df')
                    
                    if chart_df is None:
                        logging.warning(f"[WARN] No chart data available for {symbol}")
                        return None

                    # Generate chart image
                    chart_buffer = await asyncio.to_thread(
                        charter.generate_chart_image, chart_df, symbol
                    )

                    # Run AI analysis concurrently (DeepSeek + Gemini)
                    logic_task = asyncio.create_task(
                        asyncio.to_thread(
                            ai_handler.analyze_logic,
                            btc_context,
                            target_data.get('data_4h', target_data.get('data_1h', {})),
                            target_data.get('data_15m', target_data.get('data_1h', {})) if mode == "SCALPER" else target_data.get('data_1h', {}),
                            request.balance,
                            symbol,
                            mode
                        )
                    )

                    vision_task = asyncio.create_task(
                        asyncio.to_thread(
                            ai_handler.analyze_vision,
                            chart_buffer,
                            mode
                        )
                    )

                    logic_result, vision_result = await asyncio.gather(logic_task, vision_task)

                    # Combine results
                    combined = ai_handler.combine_analysis(logic_result, vision_result)

                    if combined.get('recommendation') == 'EXECUTE':
                        logging.info(f"[SIGNAL] SIGNAL FOUND: {symbol} {combined.get('final_signal')} (Conf: {combined.get('combined_confidence')}%)")
                        trade_params = logic_result.get('trade_params')
                        return SignalResult(
                            symbol=symbol,
                            final_signal=combined['final_signal'],
                            combined_confidence=combined['combined_confidence'],
                            agreement=combined['agreement'],
                            recommendation=combined['recommendation'],
                            logic_reasoning=logic_result.get('reasoning', ''),
                            vision_analysis=vision_result.get('analysis', ''),
                            trade_params=TradeParams(**trade_params) if trade_params else None
                        )
                    return None

                except Exception as e:
                    logging.error(f"Error analyzing {symbol}: {str(e)}")
                    return None
        
        # Run all symbol analyses in parallel
        results = await asyncio.gather(*[analyze_single_symbol(s) for s in top_symbols])
        valid_signals = [r for r in results if r is not None]

        # Calculate execution time
        end_time = datetime.utcnow()
        execution_time = (end_time - start_time).total_seconds()

        # Sanitize btc_context to remove NaN values
        import math
        def sanitize_float(val):
            if isinstance(val, float):
                if math.isnan(val) or math.isinf(val):
                    return 0.0
                return val
            return val

        btc_context = {k: sanitize_float(v) for k, v in btc_context.items()}

        return MarketAnalysisResponse(
            timestamp=end_time,
            btc_context=btc_context,
            opportunities_screened=len(top_symbols),
            valid_signals=valid_signals,
            execution_time_seconds=round(execution_time, 2)
        )

    except Exception as e:
        print(f"CRITICAL ERROR in analyze_market: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
