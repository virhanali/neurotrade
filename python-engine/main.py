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
from services.execution import executor

# ML Learner (for learning context)
try:
    from services.learner import learner
    HAS_LEARNER = True
except ImportError:
    learner = None
    HAS_LEARNER = False
    logging.warning("[MAIN] Learner module not available")

# Whale Detector (for liquidation stream)
try:
    from services.whale_detector import whale_detector, start_whale_monitoring
    HAS_WHALE = True
except ImportError:
    HAS_WHALE = False
    logging.warning("[MAIN] Whale detector not available")

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


# Track if streams are started (singleton pattern)
import os
import tempfile

STREAM_LOCK_FILE = os.path.join(tempfile.gettempdir(), 'neurotrade_stream.lock')

def is_primary_worker() -> bool:
    """Check if this is the primary worker that should run streams"""
    try:
        # Try to create lock file - only first worker succeeds
        if not os.path.exists(STREAM_LOCK_FILE):
            with open(STREAM_LOCK_FILE, 'w') as f:
                f.write(str(os.getpid()))
            return True
        
        # Check if the process that created the lock is still alive
        with open(STREAM_LOCK_FILE, 'r') as f:
            pid = int(f.read().strip())
        
        # Check if PID is still running
        try:
            os.kill(pid, 0)  # Signal 0 checks if process exists
            return False  # Lock holder is alive, we're secondary
        except OSError:
            # Lock holder is dead, take over
            with open(STREAM_LOCK_FILE, 'w') as f:
                f.write(str(os.getpid()))
            return True
    except Exception:
        return False  # On error, don't start streams

# Startup/Shutdown events for WebSocket
@app.on_event("startup")
async def startup_event():
    """Start WebSocket price stream and whale detector on app startup"""
    # Only primary worker starts streams (prevents 6 duplicate connections)
    if not is_primary_worker():
        logging.info(f"[WORKER {os.getpid()}] Secondary worker - skipping stream startup")
        return
    
    logging.info(f"[WORKER {os.getpid()}] Primary worker - starting streams")
    
    # Start price stream
    await price_stream.start()
    print("[WS] WebSocket price stream started")

    # Start whale liquidation monitoring (background task)
    if HAS_WHALE:
        asyncio.create_task(start_whale_monitoring())
        print("[WHALE] Liquidation stream started (background)")


@app.on_event("shutdown")
async def shutdown_event():
    """Stop WebSocket price stream and whale detector on app shutdown"""
    # Only primary worker stops streams
    if not is_primary_worker():
        return
    
    await price_stream.stop()
    print("[WS] WebSocket price stream stopped")

    # Close whale detector
    if HAS_WHALE:
        await whale_detector.close()
        print("[WHALE] Whale detector closed")
    
    # Remove lock file
    try:
        os.remove(STREAM_LOCK_FILE)
    except Exception:
        pass


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
    screener_metrics: Optional[Dict] = None  # ML metrics for feedback loop


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


@app.get("/ml/brain-health")
async def get_brain_health():
    """Get ML Brain Health statistics"""
    if not HAS_LEARNER or not learner:
        return {"status": "error", "message": "ML module not available"}
    
    return learner.get_brain_stats()


@app.post("/analyze/market", response_model=MarketAnalysisResponse)
async def analyze_market(request: MarketAnalysisRequest):
    """
    Analyze market and generate trading signals using Hybrid AI (SCALPER MODE ONLY)

    Workflow:
    1. Screen market for top opportunities
    2. Fetch BTC context (SCALPER uses 15m)
    3. For each opportunity:
       - Fetch data & generate chart (M15)
       - Analyze with DeepSeek (logic) & Gemini (vision) using SCALPER prompts
       - Combine results
    4. Return valid signals
    """
    start_time = datetime.utcnow()
    # FORCE SCALPER MODE
    mode = "SCALPER"
    
    print(f"\n[TARGET] Market Analysis Started [Mode: {mode}]")

    try:
        # Step 1: Get top opportunities (List[Dict] with metrics)
        top_candidates = []
        if request.custom_symbols:
            # Create dummy metrics for custom symbols
            top_candidates = [{'symbol': s, 'vol_ratio': 0, 'is_squeeze': False, 'score': 0} for s in request.custom_symbols]
        else:
            top_candidates = screener.get_top_opportunities() # RETURNS List[Dict]

        # Step 1.5: Pump Scanner Integration - Add low-cap pump candidates
        try:
            pump_alerts = screener.scan_pump_candidates()

            # Filter for actionable signals only
            actionable_actions = {'LONG', 'SHORT', 'CAUTIOUS_LONG', 'CAUTIOUS_SHORT'}
            actionable_pumps = [p for p in pump_alerts if p.get('trade_action') in actionable_actions]

            if actionable_pumps:
                # Get existing symbols to avoid duplicates
                existing_symbols = {c['symbol'] for c in top_candidates}

                # Convert pump alerts to candidate format
                for pump in actionable_pumps:
                    if pump['symbol'] not in existing_symbols:
                        # Map pump_type + trade_action to whale_signal for veto compatibility
                        if pump['trade_action'] in ['LONG', 'CAUTIOUS_LONG']:
                            whale_signal = 'PUMP_IMMINENT'
                        elif pump['trade_action'] in ['SHORT', 'CAUTIOUS_SHORT']:
                            whale_signal = 'DUMP_IMMINENT'
                        else:
                            whale_signal = 'NEUTRAL'

                        pump_candidate = {
                            'symbol': pump['symbol'],
                            'vol_ratio': pump.get('vol_ratio', 5.0),
                            'is_squeeze': False,
                            'score': pump.get('pump_score', 50),
                            'whale_signal': whale_signal,
                            'whale_confidence': 100 - pump.get('dump_risk', 50),  # Invert dump_risk
                            'pump_source': True,  # Flag for tracking
                            'pump_type': pump.get('pump_type'),
                            'trade_action': pump.get('trade_action'),
                            'dump_risk': pump.get('dump_risk', 50),
                        }
                        top_candidates.append(pump_candidate)
                        existing_symbols.add(pump['symbol'])

                logging.info(f"[PUMP] Injected {len(actionable_pumps)} pump candidates into analysis queue")
        except Exception as e:
            logging.warning(f"[PUMP] Scanner skipped: {e}")

        # Step 1.6: Priority Sort - Pump candidates first, then by score
        # This ensures extreme movements get analyzed before the market moves further
        def get_priority(candidate):
            # Pump source candidates get highest priority
            is_pump = candidate.get('pump_source', False)
            pump_score = candidate.get('pump_score', 0)
            pct_change = abs(candidate.get('pct_change_3c', 0))
            regular_score = candidate.get('score', 0)
            
            if is_pump and pct_change >= 10:  # EXTREME pump
                return (0, -pct_change)  # Priority 0 (highest), then by movement
            elif is_pump:  # Standard pump
                return (1, -pump_score)  # Priority 1, then by pump score
            else:  # Regular screener candidate
                return (2, -regular_score)  # Priority 2, then by screener score
        
        top_candidates.sort(key=get_priority)
        
        # Log the priority order
        pump_count = sum(1 for c in top_candidates if c.get('pump_source', False))
        if pump_count > 0:
            logging.info(f"[PRIORITY] Processing order: {pump_count} pump candidates first, then {len(top_candidates) - pump_count} regular")

        if not top_candidates:
            # No opportunities found - this is normal, not an error
            logging.info("[EMPTY] No trading opportunities passed filters (market too quiet)")
            return MarketAnalysisResponse(
                timestamp=datetime.utcnow(),
                btc_context={},
                opportunities_screened=0,
                valid_signals=[],
                execution_time_seconds=0
            )

        # Step 2: Fetch BTC context (SCALPER MODE)
        btc_context = data_fetcher.fetch_btc_context(mode="SCALPER")

        # --- BTC SLEEP CHECK (15m volatility) ---
        btc_volatility = abs(btc_context.get('pct_change_1h', 0)) # Note: data_fetcher returns 15m change in this field for SCALPER
        if btc_volatility < 0.2:
             logging.info(f"😴 Market Sleepy (BTC Move {btc_volatility}%), skipping Scan to save credits.")
             return MarketAnalysisResponse(
                timestamp=datetime.utcnow(),
                btc_context=btc_context,
                opportunities_screened=0,
                valid_signals=[],
                execution_time_seconds=0
             )

        # Run all symbol analyses in parallel
        # NEW: Get Learning Context (Global Wisdom)
        learning_ctx = ""
        if HAS_LEARNER and learner:
            learning_ctx = learner.get_learning_context()
            if learning_ctx.strip():
                print(f"[LEARNING] Context Injected: {learning_ctx.strip()}")

        # Semaphore to limit concurrent analyses (prevent API rate limits)
        semaphore = asyncio.Semaphore(6)

        async def analyze_single_candidate(candidate: Dict) -> Optional[SignalResult]:
            """Analyze a single candidate - runs concurrently"""
            symbol = candidate['symbol']
            
            async with semaphore:
                try:
                    # Fetch target data (SCALPER MODE)
                    target_data = await asyncio.to_thread(
                        data_fetcher.fetch_target_data, symbol, "SCALPER"
                    )

                    # Get chart data (M15)
                    chart_df = target_data.get('data_15m', {}).get('df')
                    
                    if chart_df is None:
                        logging.warning(f"[WARN] No chart data available for {symbol}")
                        return None

                    # Generate chart image (M15)
                    chart_buffer = await asyncio.to_thread(
                        charter.generate_chart_image, chart_df, symbol, "15M"
                    )

                    # Run AI analysis concurrently (DeepSeek + Gemini)
                    # Logic args: btc_data, target_4h, target_trigger(15m), balance, symbol, metrics, learning_context
                    logic_task = asyncio.create_task(
                        asyncio.to_thread(
                            ai_handler.analyze_logic,
                            btc_context,
                            target_data.get('data_4h', {}),
                            target_data.get('data_15m', {}),
                            request.balance,
                            symbol,
                            candidate, # Metrics
                            learning_ctx # Wisdom
                        )
                    )

                    # Vision args: chart_buffer
                    vision_task = asyncio.create_task(
                        asyncio.to_thread(
                            ai_handler.analyze_vision,
                            chart_buffer
                        )
                    )

                    logic_result, vision_result = await asyncio.gather(logic_task, vision_task)

                    # Combine results (pass metrics for ML prediction + whale data for Tier 1 veto)
                    whale_signal = candidate.get('whale_signal', 'NEUTRAL')
                    whale_confidence = candidate.get('whale_confidence', 0)
                    combined = ai_handler.combine_analysis(
                        logic_result,
                        vision_result,
                        metrics=candidate,
                        whale_signal=whale_signal,
                        whale_confidence=whale_confidence
                    )

                    if combined.get('recommendation') == 'EXECUTE':
                        ml_prob = combined.get('ml_win_probability', 0.5)
                        logging.info(f"[SIGNAL] SIGNAL FOUND: {symbol} {combined.get('final_signal')} (Conf: {combined.get('combined_confidence')}%, ML: {ml_prob:.0%})")
                        trade_params = logic_result.get('trade_params')
                        return SignalResult(
                            symbol=symbol,
                            final_signal=combined['final_signal'],
                            combined_confidence=combined['combined_confidence'],
                            agreement=combined['agreement'],
                            recommendation=combined['recommendation'],
                            logic_reasoning=logic_result.get('reasoning', ''),
                            vision_analysis=vision_result.get('analysis', ''),
                            trade_params=TradeParams(**trade_params) if trade_params else None,
                            screener_metrics=candidate  # Pass metrics for feedback loop
                        )
                    return None

                except Exception as e:
                    logging.error(f"Error analyzing {symbol}: {str(e)}")
                    return None
        
        # Run all symbol analyses in parallel
        results = await asyncio.gather(*[analyze_single_candidate(c) for c in top_candidates])
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
            opportunities_screened=len(top_candidates),
            valid_signals=valid_signals,
            execution_time_seconds=round(execution_time, 2)
        )

    except Exception as e:
        print(f"CRITICAL ERROR in analyze_market: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

class FeedbackRequest(BaseModel):
    symbol: str
    outcome: str # "WIN" or "LOSS"
    pnl: float
    metrics: Optional[Dict] = {}

@app.post("/feedback")
async def feedback(request: FeedbackRequest):
    """Endpoint to receive trade feedback from Go backend"""
    try:
        from services.learner import learner
        learner.record_outcome(request.symbol, request.metrics, request.outcome, request.pnl)
        return {"status": "ok"}
    except Exception as e:
        logging.error(f"Feedback error: {str(e)}")
        return {"status": "error", "detail": str(e)}


@app.get("/ml/stats")
async def ml_stats():
    """Get ML model performance statistics"""
    try:
        from services.learner import learner
        stats = learner.get_performance_stats()
        regime = learner.get_market_regime()
        threshold = learner.get_recommended_threshold()

        return {
            "status": "ok",
            "stats": stats,
            "market_regime": {
                "regime": regime.regime,
                "win_rate": regime.win_rate,
                "avg_pnl": regime.avg_pnl,
                "sample_size": regime.sample_size,
                "confidence": regime.confidence
            },
            "recommended_confidence_threshold": threshold
        }
    except Exception as e:
        logging.error(f"ML stats error: {str(e)}")
        return {"status": "error", "detail": str(e)}


class PredictionRequest(BaseModel):
    metrics: Dict


@app.post("/ml/predict")
async def ml_predict(request: PredictionRequest):
    """Get ML prediction for a set of metrics"""
    try:
        from services.learner import learner
        prediction = learner.get_prediction(request.metrics)

        return {
            "status": "ok",
            "win_probability": prediction.win_probability,
            "recommended_threshold": prediction.recommended_confidence_threshold,
            "regime": prediction.regime.regime,
            "insights": prediction.insights
        }
    except Exception as e:
        logging.error(f"ML prediction error: {str(e)}")
        return {"status": "error", "detail": str(e)}


# ============================================
# Whale Detection Endpoints (NEW v4.2)
# ============================================

@app.get("/whale/status")
async def whale_status():
    """Get whale detector status and connection info"""
    if not HAS_WHALE:
        return {"status": "unavailable", "reason": "Whale detector not imported"}

    return {
        "status": "ok",
        "liquidation_stream_connected": whale_detector.ws_connected,
        "tracked_symbols": len(whale_detector.liquidations),
        "orderbook_cache_size": len(whale_detector.orderbook_cache),
        "oi_cache_size": len(whale_detector.oi_cache)
    }


class WhaleDetectRequest(BaseModel):
    symbol: str
    current_price: Optional[float] = 0


@app.post("/whale/detect")
async def whale_detect(request: WhaleDetectRequest):
    """
    Detect whale activity for a specific symbol

    Returns:
        - signal: PUMP_IMMINENT, DUMP_IMMINENT, SQUEEZE_LONGS, SQUEEZE_SHORTS, NEUTRAL
        - confidence: 0-100
        - liquidation_pressure: LONG_HEAVY, SHORT_HEAVY, BALANCED, NONE
        - order_imbalance: -100 to +100
        - large_trades_bias: BUYING, SELLING, MIXED
    """
    if not HAS_WHALE:
        return {
            "status": "error",
            "reason": "Whale detector not available"
        }

    try:
        signal = await whale_detector.detect_whale_activity(
            request.symbol,
            request.current_price
        )

        return {
            "status": "ok",
            "symbol": request.symbol,
            "signal": signal.signal,
            "confidence": signal.confidence,
            "liquidation_pressure": signal.liquidation_pressure,
            "order_imbalance": signal.order_imbalance,
            "large_trades_bias": signal.large_trades_bias,
            "reasoning": signal.reasoning,
            "timestamp": signal.timestamp
        }
    except Exception as e:
        logging.error(f"Whale detection error: {str(e)}")
        return {"status": "error", "detail": str(e)}


@app.get("/whale/liquidations/{symbol}")
async def whale_liquidations(symbol: str):
    """Get recent liquidation events for a symbol"""
    if not HAS_WHALE:
        return {"status": "error", "reason": "Whale detector not available"}

    normalized = symbol.replace('/', '').upper()
    pressure, long_liq, short_liq = whale_detector.get_liquidation_pressure(normalized)

    events = []
    if normalized in whale_detector.liquidations:
        for event in list(whale_detector.liquidations[normalized])[-20:]:  # Last 20
            events.append({
                "side": event.side,
                "quantity_usd": event.quantity,
                "price": event.price,
                "timestamp": event.timestamp
            })

    return {
        "status": "ok",
        "symbol": normalized,
        "pressure": pressure,
        "long_liquidations_usd": long_liq,
        "short_liquidations_usd": short_liq,
        "recent_events": events
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


# ============================================
# Execution Endpoints (v6.0 - Real Trading)
# ============================================

class ExecuteEntryRequest(BaseModel):
    symbol: str
    side: str  # LONG/SHORT
    amount_usdt: float
    leverage: int = 20

@app.post("/execute/entry")
async def execute_entry(request: ExecuteEntryRequest):
    """
    Execute entry order on Binance Futures
    """
    logger.info(f"[EXEC] Request Entry: {request.symbol} {request.side} ${request.amount_usdt}")
    result = await executor.execute_entry(
        symbol=request.symbol,
        side=request.side,
        amount_usdt=request.amount_usdt,
        leverage=request.leverage
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

class ExecuteCloseRequest(BaseModel):
    symbol: str
    side: str  # SELL (if Long), BUY (if Short)
    quantity: float

@app.post("/execute/close")
async def execute_close(request: ExecuteCloseRequest):
    """
    Execute closing order (ReduceOnly)
    """
    result = await executor.execute_close(
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

@app.get("/execute/balance")
async def get_real_balance():
    """
    Get real USDT balance from Binance
    """
    result = await executor.get_balance()
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result
