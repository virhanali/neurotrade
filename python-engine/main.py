"""
NeuroTrade AI - Python Engine
FastAPI service for AI-powered trading signal generation
"""

import asyncio
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
    entry_price: float
    stop_loss: float
    take_profit: float
    suggested_leverage: int
    position_size_usdt: float


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
    
    print(f"\n🎯 Market Analysis Started [Mode: {mode}]")

    try:
        # Step 1: Get top opportunities
        if request.custom_symbols:
            top_symbols = request.custom_symbols
        else:
            top_symbols = screener.get_top_opportunities()

        if not top_symbols:
            raise HTTPException(status_code=404, detail="No trading opportunities found")

        # Step 2: Fetch BTC context (mode-aware)
        btc_context = data_fetcher.fetch_btc_context(mode=mode)

        # Step 3: Analyze each opportunity
        valid_signals = []

        for symbol in top_symbols:
            try:
                # Fetch target data (mode-aware: SCALPER uses 15m, INVESTOR uses 1h/4h)
                target_data = data_fetcher.fetch_target_data(symbol, mode=mode)

                # Get the appropriate timeframe data for chart generation
                chart_timeframe = 'data_15m' if mode == "SCALPER" else 'data_1h'
                chart_df = target_data.get(chart_timeframe, target_data.get('data_1h', {})).get('df')
                
                if chart_df is None:
                    print(f"⚠️ No chart data available for {symbol}")
                    continue

                # Generate chart image
                chart_buffer = charter.generate_chart_image(
                    df=chart_df,
                    symbol=symbol
                )

                # Run AI analysis concurrently with mode-aware prompts
                logic_task = asyncio.create_task(
                    asyncio.to_thread(
                        ai_handler.analyze_logic,
                        btc_context,
                        target_data.get('data_4h', target_data.get('data_1h', {})),
                        target_data.get('data_15m', target_data.get('data_1h', {})) if mode == "SCALPER" else target_data.get('data_1h', {}),
                        request.balance,
                        symbol,
                        mode  # Pass mode to AI handler
                    )
                )

                vision_task = asyncio.create_task(
                    asyncio.to_thread(
                        ai_handler.analyze_vision,
                        chart_buffer,
                        mode  # Pass mode to vision analysis
                    )
                )

                # Wait for both to complete
                logic_result, vision_result = await asyncio.gather(logic_task, vision_task)

                # Combine results
                combined = ai_handler.combine_analysis(logic_result, vision_result)

                # Log analysis results
                current_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n=== Analysis for {symbol} [{current_time_str}] [Mode: {mode}] ===")
                print(f"Logic Signal: {logic_result.get('signal', 'N/A')}")
                print(f"Logic Confidence: {logic_result.get('confidence', 0)}%")
                print(f"Vision Verdict: {vision_result.get('verdict', 'N/A')}")
                print(f"Vision Confidence: {vision_result.get('confidence', 0)}%")
                print(f"Setup Valid: {combined.get('setup_valid', 'N/A')}")
                print(f"Agreement: {combined['agreement']}")
                print(f"Combined Confidence: {combined['combined_confidence']}%")
                print(f"Recommendation: {combined['recommendation']}")
                print("--- AI Reasoning ---")
                print(logic_result.get('reasoning', 'No reasoning available')[:500] + "...") # Limit to 500 chars to avoid massive logs
                print(f"==============================\n")

                # Check if signal meets criteria
                if combined['recommendation'] == 'EXECUTE':
                    trade_params = logic_result.get('trade_params')

                    signal = SignalResult(
                        symbol=symbol,
                        final_signal=combined['final_signal'],
                        combined_confidence=combined['combined_confidence'],
                        agreement=combined['agreement'],
                        recommendation=combined['recommendation'],
                        logic_reasoning=logic_result.get('reasoning', ''),
                        vision_analysis=vision_result.get('analysis', ''),
                        trade_params=TradeParams(**trade_params) if trade_params else None
                    )
                    valid_signals.append(signal)

            except Exception as e:
                # Log error but continue with other symbols
                print(f"Error analyzing {symbol}: {str(e)}")
                continue

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
