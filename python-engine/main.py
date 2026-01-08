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
            top_candidates = screener.get_top_opportunities()

        # Sort by screener score (highest first)
        top_candidates.sort(key=lambda x: x.get('score', 0), reverse=True)

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

        # --- BTC SLEEP CHECK ---
        BTC_VOLATILITY_THRESHOLD_15M = 0.1
        btc_volatility_15m = abs(btc_context.get('pct_change_1h', 0))
        btc_rsi = btc_context.get('rsi_1h', 50)
        btc_in_extreme = btc_rsi < 35 or btc_rsi > 65
        
        if btc_volatility_15m < BTC_VOLATILITY_THRESHOLD_15M and not btc_in_extreme:
            logging.info(f"[BTC Sleepy] BTC Move {btc_volatility_15m:.2f}% < {BTC_VOLATILITY_THRESHOLD_15M}%, RSI={btc_rsi:.0f} - skipping")
            return MarketAnalysisResponse(
                timestamp=datetime.utcnow(),
                btc_context=btc_context,
                opportunities_screened=0,
                valid_signals=[],
                execution_time_seconds=0
            )
        
        if btc_volatility_15m < BTC_VOLATILITY_THRESHOLD_15M and btc_in_extreme:
            logging.info(f"[BTC EXTREME] Low vol but RSI={btc_rsi:.0f} - proceeding")

        # Run all symbol analyses in parallel
        # NEW: Get Learning Context (Global Wisdom)
        learning_ctx = ""
        if HAS_LEARNER and learner:
            learning_ctx = learner.get_learning_context()
            if learning_ctx.strip():
                print(f"[LEARNING] Context Injected: {learning_ctx.strip()}")

        # Semaphore to limit concurrent analyses (prevent API rate limits)
        semaphore = asyncio.Semaphore(2)

        async def analyze_single_candidate(candidate: Dict) -> Optional[SignalResult]:
            """Analyze a single candidate - runs concurrently"""
            symbol = candidate['symbol']
            score = candidate.get('score', 0)
            
            MIN_SCORE_FOR_AI = 40
            if score < MIN_SCORE_FOR_AI:
                logging.debug(f"[SKIP-AI] {symbol}: Score {score} < {MIN_SCORE_FOR_AI} - Skipping AI")
                return None
            
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

                    # === COST OPTIMIZATION: Logic First, Vision Only If Needed ===
                    # Step 1: Run Logic Analysis (cheaper API)
                    logic_result = await asyncio.to_thread(
                        ai_handler.analyze_logic,
                        btc_context,
                        target_data.get('data_4h', {}),
                        target_data.get('data_15m', {}),
                        request.balance,
                        symbol,
                        candidate,  # Metrics
                        learning_ctx  # Wisdom
                    )
                    
                    # Step 2: Check if Logic warrants Vision analysis
                    logic_signal = logic_result.get('signal', 'WAIT')
                    logic_confidence = logic_result.get('confidence', 0)
                    
                    # Skip Vision if Logic already says WAIT or low confidence
                    # UPDATED: Lowered from 65 to 55 to allow more signals through
                    # This increases vision API cost but improves signal detection
                    VISION_THRESHOLD = 55  # Minimum Logic confidence to call Vision
                    
                    if logic_signal == 'WAIT' or logic_confidence < VISION_THRESHOLD:
                        logging.info(f"[SKIP-VISION] {symbol}: Logic={logic_signal} Conf={logic_confidence}% (threshold={VISION_THRESHOLD}%) - Saving Vision API cost")
                        return None
                    
                    # Step 3: Logic passed, now call Vision (more expensive API)
                    logging.info(f"[CALL-VISION] {symbol}: Logic={logic_signal} Conf={logic_confidence}% - Proceeding with Vision analysis")
                    
                    vision_result = await asyncio.to_thread(
                        ai_handler.analyze_vision,
                        chart_buffer
                    )

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


@app.get("/analytics/ai-behavior")
async def ai_behavior_analytics():
    """
    Get AI behavior analytics from ai_analysis_cache.
    Works even without trade outcomes - pure observational data.
    """
    try:
        from services.learner import learner
        
        if not learner.engine:
            return {"status": "error", "detail": "Database not connected"}
        
        from sqlalchemy import text
        
        with learner.engine.connect() as conn:
            # 1. AI Agreement Breakdown
            agreement = conn.execute(text("""
                SELECT 
                    COUNT(*) as total,
                    SUM(CASE WHEN logic_signal = vision_signal THEN 1 ELSE 0 END) as consensus,
                    SUM(CASE WHEN logic_signal IN ('LONG', 'SHORT') AND vision_signal != logic_signal THEN 1 ELSE 0 END) as vision_vetoed,
                    SUM(CASE WHEN vision_signal IN ('LONG', 'SHORT') AND logic_signal != vision_signal THEN 1 ELSE 0 END) as logic_vetoed
                FROM ai_analysis_cache
                WHERE created_at > NOW() - INTERVAL '7 days'
            """)).fetchone()
            
            agreement_rate = (agreement[1] / agreement[0] * 100) if agreement[0] and agreement[0] > 0 else 0
            
            # 2. Confidence Distribution
            confidence_dist = conn.execute(text("""
                SELECT 
                    CASE 
                        WHEN final_confidence >= 80 THEN 'HIGH (80+)'
                        WHEN final_confidence >= 60 THEN 'MEDIUM (60-79)'
                        ELSE 'LOW (<60)'
                    END as confidence_level,
                    COUNT(*) as count
                FROM ai_analysis_cache
                WHERE created_at > NOW() - INTERVAL '7 days'
                GROUP BY 1
                ORDER BY 2 DESC
            """)).fetchall()
            
            # 3. Recommendation Distribution
            rec_dist = conn.execute(text("""
                SELECT 
                    recommendation,
                    COUNT(*) as count,
                    ROUND(AVG(final_confidence), 1) as avg_confidence
                FROM ai_analysis_cache
                WHERE created_at > NOW() - INTERVAL '7 days'
                GROUP BY recommendation
                ORDER BY count DESC
            """)).fetchall()
            
            # 4. Whale Signal Distribution
            whale_dist = conn.execute(text("""
                SELECT 
                    whale_signal,
                    COUNT(*) as count,
                    ROUND(AVG(whale_confidence), 1) as avg_whale_conf
                FROM ai_analysis_cache
                WHERE created_at > NOW() - INTERVAL '7 days'
                GROUP BY whale_signal
                ORDER BY count DESC
            """)).fetchall()
            
            # 5. Hourly Pattern
            hourly = conn.execute(text("""
                SELECT 
                    hour_of_day,
                    COUNT(*) as total,
                    SUM(CASE WHEN recommendation = 'EXECUTE' THEN 1 ELSE 0 END) as execute_count
                FROM ai_analysis_cache
                WHERE created_at > NOW() - INTERVAL '7 days'
                GROUP BY hour_of_day
                ORDER BY hour_of_day
            """)).fetchall()
            
            # 6. Top Analyzed Symbols
            top_symbols = conn.execute(text("""
                SELECT 
                    symbol,
                    COUNT(*) as analyzed_count,
                    ROUND(AVG(screener_score), 1) as avg_score,
                    ROUND(AVG(final_confidence), 1) as avg_confidence
                FROM ai_analysis_cache
                WHERE created_at > NOW() - INTERVAL '7 days'
                GROUP BY symbol
                ORDER BY analyzed_count DESC
                LIMIT 10
            """)).fetchall()
            
            # 7. Total Stats & Accuracy Matrix
            totals = conn.execute(text("""
                SELECT 
                    COUNT(*) as total_analyzed,
                    SUM(CASE WHEN recommendation = 'EXECUTE' THEN 1 ELSE 0 END) as total_execute,
                    SUM(CASE WHEN outcome IS NOT NULL THEN 1 ELSE 0 END) as with_outcome,
                    SUM(CASE WHEN outcome = 'WIN' THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN outcome = 'LOSS' THEN 1 ELSE 0 END) as losses
                FROM ai_analysis_cache
                WHERE created_at > NOW() - INTERVAL '7 days'
            """)).fetchone()
        
        return {
            "status": "ok",
            "period": "last_7_days",
            "summary": {
                "total_analyzed": totals[0] or 0,
                "total_execute": totals[1] or 0,
                "with_outcome": totals[2] or 0,
                "wins": totals[3] or 0,
                "losses": totals[4] or 0,
                "execute_rate": round((totals[1] or 0) / max(totals[0], 1) * 100, 1),
                "ai_agreement_rate": round(agreement_rate, 1),
                "agreement_breakdown": {
                    "consensus": agreement[1] or 0,
                    "vision_vetoed": agreement[2] or 0,
                    "logic_vetoed": agreement[3] or 0
                }
            },
            "confidence_distribution": [
                {"level": row[0], "count": row[1]} for row in confidence_dist
            ],
            "recommendation_distribution": [
                {"recommendation": row[0], "count": row[1], "avg_confidence": float(row[2] or 0)} 
                for row in rec_dist
            ],
            "whale_signals": [
                {"signal": row[0], "count": row[1], "avg_confidence": float(row[2] or 0)} 
                for row in whale_dist
            ],
            "hourly_pattern": [
                {"hour": row[0], "total": row[1], "execute_count": row[2]} 
                for row in hourly
            ],
            "top_symbols": [
                {"symbol": row[0], "count": row[1], "avg_score": float(row[2] or 0), "avg_confidence": float(row[3] or 0)} 
                for row in top_symbols
            ]
        }
        
    except Exception as e:
        logging.error(f"AI analytics error: {str(e)}")
        return {"status": "error", "detail": str(e)}


# ============================================
# ML Backfill Endpoints (Simulated Outcomes)
# ============================================

@app.post("/ml/backfill-outcomes")
async def backfill_simulated_outcomes(hours_back: int = 24, limit: int = 50):
    """
    Backfill simulated outcomes for old signals.
    
    This allows ML to learn from "hypothetical" trades.
    Checks historical prices to determine if signal would have been WIN or LOSS.
    
    Args:
        hours_back: How far back to look for signals (default 24h)
        limit: Max signals to process (default 50)
    """
    try:
        from services.learner import learner
        from sqlalchemy import text
        import ccxt
        
        if not learner.engine:
            return {"status": "error", "detail": "Database not connected"}
        
        exchange = ccxt.binanceusdm({'enableRateLimit': True})
        
        # Get signals without outcomes that are old enough for simulation
        with learner.engine.connect() as conn:
            signals = conn.execute(text("""
                SELECT 
                    id, symbol, logic_signal, final_confidence,
                    screener_score, created_at
                FROM ai_analysis_cache
                WHERE outcome IS NULL
                AND created_at < NOW() - INTERVAL '1 hour'
                AND created_at > NOW() - INTERVAL :hours_back
                AND logic_signal IN ('LONG', 'SHORT')
                ORDER BY created_at ASC
                LIMIT :limit
            """), {"hours_back": f"{hours_back} hours", "limit": limit}).fetchall()
        
        if not signals:
            return {
                "status": "ok",
                "message": "No signals to backfill",
                "processed": 0
            }
        
        processed = 0
        wins = 0
        losses = 0
        
        for signal in signals:
            try:
                signal_id = signal[0]
                symbol = signal[1]
                direction = signal[2]  # LONG or SHORT
                confidence = signal[3]
                created_at = signal[5]
                
                # Fetch 15m candles from signal time + 4 hours
                # (simulate 4 hour hold time for scalping)
                ohlcv = exchange.fetch_ohlcv(symbol, '15m', limit=20)
                if not ohlcv or len(ohlcv) < 5:
                    continue
                
                # Get entry price (first candle close after signal)
                entry_price = ohlcv[0][4]
                
                # Define SL/TP ratios (standard 1:2 R:R)
                if direction == "LONG":
                    sl_price = entry_price * 0.99  # 1% SL
                    tp_price = entry_price * 1.02  # 2% TP
                else:
                    sl_price = entry_price * 1.01  # 1% SL
                    tp_price = entry_price * 0.98  # 2% TP
                
                # Check if TP or SL hit first
                outcome = None
                pnl = 0.0
                
                for candle in ohlcv[1:]:
                    high = candle[2]
                    low = candle[3]
                    
                    if direction == "LONG":
                        if low <= sl_price:
                            outcome = "LOSS"
                            pnl = -1.0
                            break
                        elif high >= tp_price:
                            outcome = "WIN"
                            pnl = 2.0
                            break
                    else:  # SHORT
                        if high >= sl_price:
                            outcome = "LOSS"
                            pnl = -1.0
                            break
                        elif low <= tp_price:
                            outcome = "WIN"
                            pnl = 2.0
                            break
                
                # If neither hit, check final price
                if outcome is None:
                    final_price = ohlcv[-1][4]
                    if direction == "LONG":
                        pnl = ((final_price - entry_price) / entry_price) * 100
                    else:
                        pnl = ((entry_price - final_price) / entry_price) * 100
                    outcome = "WIN" if pnl > 0 else "LOSS"
                
                # Update database
                with learner.engine.connect() as conn:
                    conn.execute(text("""
                        UPDATE ai_analysis_cache
                        SET outcome = :outcome, pnl = :pnl
                        WHERE id = :id
                    """), {"outcome": outcome, "pnl": pnl, "id": signal_id})
                    conn.commit()
                
                processed += 1
                if outcome == "WIN":
                    wins += 1
                else:
                    losses += 1
                    
            except Exception as e:
                logging.warning(f"[BACKFILL] Failed to process {signal[1]}: {e}")
                continue
        
        # Trigger model retrain if we have new data
        if processed >= 10:
            learner._check_retrain()
        
        return {
            "status": "ok",
            "processed": processed,
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / max(processed, 1) * 100, 1),
            "message": f"Backfilled {processed} signals with simulated outcomes"
        }
        
    except Exception as e:
        logging.error(f"Backfill error: {str(e)}")
        return {"status": "error", "detail": str(e)}


# ============================================
# Whale Detection Endpoints
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
    api_key: Optional[str] = None
    api_secret: Optional[str] = None

@app.post("/execute/entry")
async def execute_entry(request: ExecuteEntryRequest):
    """
    Execute entry order on Binance Futures
    """
    logging.info(f"[EXEC] Request Entry: {request.symbol} {request.side} ${request.amount_usdt}")
    result = await executor.execute_entry(
        symbol=request.symbol,
        side=request.side,
        amount_usdt=request.amount_usdt,
        leverage=request.leverage,
        api_key=request.api_key,
        api_secret=request.api_secret
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

class ExecuteCloseRequest(BaseModel):
    symbol: str
    side: str  # SELL (if Long), BUY (if Short)
    quantity: float
    api_key: Optional[str] = None
    api_secret: Optional[str] = None

@app.post("/execute/close")
async def execute_close(request: ExecuteCloseRequest):
    """
    Execute closing order (ReduceOnly)
    """
    result = await executor.execute_close(
        symbol=request.symbol,
        side=request.side,
        quantity=request.quantity,
        api_key=request.api_key,
        api_secret=request.api_secret
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result

class BalanceRequest(BaseModel):
    api_key: Optional[str] = None
    api_secret: Optional[str] = None

@app.post("/execute/balance")
async def get_real_balance(request: BalanceRequest):
    """
    Get real USDT balance from Binance
    """
    result = await executor.get_balance(
        api_key=request.api_key,
        api_secret=request.api_secret
    )
    
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
        
    return result
