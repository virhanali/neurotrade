"""
AI Handler Service
Integrates DeepSeek (Logic) and Gemini (Vision) for hybrid trading analysis
Supports SCALPER (M15 Mean Reversion) and INVESTOR (H1/4H Trend Following) modes
Enhanced with ML-based win probability prediction (v4.0)
"""

import json
import base64
import logging
from typing import Dict, Optional
from io import BytesIO
from openai import OpenAI
from config import settings

# Import ML learner for predictions
HAS_LEARNER = False
learner = None
try:
    from services.learner import learner as _learner
    learner = _learner
    HAS_LEARNER = learner is not None
except ImportError:
    logging.warning("[AI_HANDLER] Learner module not available")


def get_system_prompt() -> str:
    """Returns the system prompt for SCALPER mode with Whale Detection."""
    return """ROLE: M15 Algo-Trading Unit with Whale Radar.

CONTEXT: Candidate PASSED screener filters (volatility, volume, 4H trend, RSI action zone). Validate final entry.

=== DECISION PRIORITY (TOP TO BOTTOM) ===

1. WHALE SIGNAL (Highest Priority):
   - PUMP_IMMINENT → LONG (whales accumulating)
   - DUMP_IMMINENT → SHORT (whales distributing)  
   - SQUEEZE_LONGS → AVOID LONG (cascade dump risk)
   - SQUEEZE_SHORTS → AVOID SHORT (squeeze risk)
   - NEUTRAL → Use technicals only

2. LIQUIDATION CHECK (Support/Resistance):
   - LONG_HEAVY liquidations → SHORT bias (dump in progress)
   - SHORT_HEAVY liquidations → LONG bias (pump in progress)
   - If your direction MATCHES liquidation pressure → Reduce confidence -10

3. ORDER BOOK IMBALANCE:
   - >+20% buy orders → Support strong, LONG bias
   - <-20% sell orders → Resistance strong, SHORT bias

4. TECHNICAL CONFLUENCE:
   - ADX<25 (Sideways): Mean reversion at BB bands
   - ADX>25 (Trending): Pullback entries on EMA20
   - RSI<35 + BULL trend → LONG
   - RSI>65 + BEAR trend → SHORT

=== CONFIDENCE GUIDELINES (IMPORTANT!) ===
- Base confidence should be 60% if screener passed
- Whale signal agreeing with technicals → 80%+
- Strong momentum (ROC > 1%) → +10%
- Clean structure (no choppy candles) → +5%
- Only use <50% if there are MAJOR red flags

=== TREND FLEXIBILITY ===
1. If 4H Trend is DOWN but:
   - RSI < 35 (oversold) → LONG allowed (mean reversion)
   - Whale says PUMP_IMMINENT → LONG with high confidence
   - Strong support + volume → LONG allowed

2. If 4H Trend is UP but:
   - RSI > 65 (overbought) → SHORT allowed (mean reversion)
   - Whale says DUMP_IMMINENT → SHORT with high confidence
   - Strong resistance + volume → SHORT allowed

=== EXECUTION PARAMS ===
- SL: 0.5% - 2.0% (use ATR for guidance)
- TP: Minimum 1.5:1 RR, Whale signals aim 2-4%
- Leverage: 10-15x

=== OUTPUT (JSON ONLY) ===
{
  "symbol": "string",
  "signal": "LONG" | "SHORT" | "WAIT",
  "confidence": 0-100,
  "reasoning": "Brief: [Key Factor 1] + [Key Factor 2] = [Decision]",
  "trade_params": {
    "entry_price": float,
    "stop_loss": float,
    "take_profit": float,
    "suggested_leverage": int
  }
}"""


def get_vision_prompt() -> str:
    """
    Returns the vision analysis prompt for SCALPER mode (v4.2)
    Enhanced with Whale-Aware Pattern Recognition
    """
    return """ACT AS: Elite Technical Chart Pattern Scanner with SMART MONEY AWARENESS.
CONTEXT: Technical Screener + WHALE DETECTOR indicates price is in a KEY ACTION ZONE.
TASK: IDENTIFY PREDICTIVE STRUCTURES that confirm or deny WHALE ACTIVITY.

🐋 WHALE-AWARE VISUAL ANALYSIS:
Focus on patterns that WHALES create during accumulation/distribution:

1. **ACCUMULATION PATTERNS (PRE-PUMP)**:
   - **SPRING**: Sharp drop below support followed by quick recovery (Wyckoff).
   - **HIGHER LOWS on VOLUME**: Each dip has LESS selling, HIGHER close.
   - **TIGHT CONSOLIDATION**: Very small candles = Calm before storm.
   - **BULLISH DIVERGENCE**: Price makes lower lows, but RSI makes higher lows.
   -> If WHALE DATA says PUMP_IMMINENT: VOTE BULLISH with HIGH confidence.

2. **DISTRIBUTION PATTERNS (PRE-DUMP)**:
   - **UPTHRUST**: Sharp spike above resistance then REJECTED hard.
   - **LOWER HIGHS**: Each rally has LESS buying power.
   - **BEARISH ENGULFING at RESISTANCE**: Big red candle swallows green.
   - **BEARISH DIVERGENCE**: Price makes higher highs, but RSI makes lower highs.
   -> If WHALE DATA says DUMP_IMMINENT: VOTE BEARISH with HIGH confidence.

3. **TRADITIONAL PATTERNS**:
   - **SQUEEZE / TRIANGLE**: Price coiling = PRE-BREAKOUT.
   - **BULL FLAG**: Channel down after pump = CONTINUATION.
   - **BEAR FLAG**: Channel up after dump = CONTINUATION.
   - **DOUBLE BOTTOM/TOP**: Classic reversal.

4. **BOLLINGER BANDS**:
   - **SQUEEZE (Bands Tight)**: EXPLOSION INCOMING.
   - **ALLIGATOR MOUTH (Bands Opening)**: Move in progress.
   - **RIDING THE BAND**: Strong trend, don't counter-trade.

5. **DANGER SIGNALS (REJECT TRADE)**:
   - **GOD CANDLE**: Huge candle with no context = FOMO trap.
   - **FALLING KNIFE**: Multiple big red candles = Don't catch.
   - **EXTENDED FROM BB**: Price too far from middle = Wait for pullback.
   - **CHOPPY NOISE**: No clear structure = INVALID_CHOPPY.

DECISION LOGIC:
- Accumulation Pattern + Squeeze = BULLISH (Sniper Long).
- Distribution Pattern + Resistance = BEARISH (Sniper Short).
- Big candle WITHOUT pattern = NEUTRAL (Chase Prevention).
- No clear structure = INVALID_CHOPPY.
- Extreme extension = DANGEROUS_BREAKOUT.

OUTPUT FORMAT (JSON):
{
    "verdict": "BULLISH/BEARISH/NEUTRAL",
    "confidence": <0-100>,
    "setup_valid": "VALID_SETUP" or "INVALID_CHOPPY" or "DANGEROUS_BREAKOUT",
    "patterns_detected": ["Spring", "Higher Lows", "Squeeze", "Accumulation"],
    "whale_confirmation": "Supports PUMP" or "Supports DUMP" or "Unclear",
    "key_levels": {
        "support": <price or null>,
        "resistance": <price or null>
    },
    "analysis": "Visual analysis with whale-aware interpretation..."
}"""


class AIHandler:
    """Handles AI analysis using DeepSeek and Gemini"""

    def __init__(self):
        """Initialize AI clients"""
        # DeepSeek via OpenAI-compatible API
        self.deepseek_client = OpenAI(
            api_key=settings.DEEPSEEK_API_KEY,
            base_url="https://api.deepseek.com"
        )

        # OpenRouter for Vision Analysis (using GPT-4 Vision or Google Gemini)
        self.vision_client = OpenAI(
            api_key=settings.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )

    def analyze_logic(
        self,
        btc_data: Dict,
        target_4h: Dict,
        target_trigger: Dict,
        balance: float = 1000.0,
        symbol: str = "UNKNOWN",
        metrics: Optional[Dict] = None,
        learning_context: str = ""
    ) -> Dict:
        """
        Analyze trading logic using DeepSeek (SCALPER MODE ONLY)
        ...
        learning_context: Insights from machine learning feedback loop
        """
        try:
            # Get SCALPER system prompt
            system_prompt = get_system_prompt()

            # Prepare Metrics Text (QUANTITATIVE ALPHA)
            metrics_txt = "N/A"
            if metrics:
                vol_ratio = metrics.get('vol_ratio', 0)
                vol_z_score = metrics.get('vol_z_score', 0)
                is_squeeze = metrics.get('is_squeeze', False)
                score = metrics.get('score', 0)
                adx = metrics.get('adx', 0)
                atr_pct = metrics.get('atr_pct', 0)
                ker = metrics.get('efficiency_ratio', 0)

                # Whale Detection Data (NEW v4.2)
                whale_signal = metrics.get('whale_signal', 'NEUTRAL')
                liq_pressure = metrics.get('liquidation_pressure', 'NONE')
                order_imbalance = metrics.get('order_imbalance', 0)
                whale_confidence = metrics.get('whale_confidence', 0)

                squeeze_str = "YES (EXPLOSION IMMINENT - PREPARE ENTRY)" if is_squeeze else "NO"

                vol_str = f"Ratio: {vol_ratio:.2f}x | Z-Score: {vol_z_score:.2f}σ"
                if vol_z_score > 3.0: vol_str += " (BLACK SWAN EVENT - HUGE VOLUME)"
                elif vol_z_score > 2.0: vol_str += " (WHALE ACTIVITY DETECTED)"

                adx_str = f"{adx:.1f}"
                if adx > 25: adx_str += " (TRENDING)"
                else: adx_str += " (SIDEWAYS)"

                ker_str = f"{ker:.2f}"
                if ker > 0.6: ker_str += " (SUPER CLEAN - SNIPER ENTRY)"
                elif ker < 0.3: ker_str += " (MESSY/CHOPPY - CAUTION)"

                # Whale Signal Interpretation
                whale_str = f"{whale_signal}"
                if whale_signal == "PUMP_IMMINENT":
                    whale_str += " 🐋🚀 (WHALES LOADING - HIGH PROBABILITY LONG)"
                elif whale_signal == "DUMP_IMMINENT":
                    whale_str += " 🐋📉 (WHALES EXITING - HIGH PROBABILITY SHORT)"
                elif whale_signal == "SQUEEZE_LONGS":
                    whale_str += " ⚠️ (LONG LIQUIDATIONS BUILDING - AVOID LONGS)"
                elif whale_signal == "SQUEEZE_SHORTS":
                    whale_str += " ⚠️ (SHORT LIQUIDATIONS BUILDING - AVOID SHORTS)"

                # Liquidation Pressure
                liq_str = f"{liq_pressure}"
                if liq_pressure == "LONG_HEAVY":
                    liq_str += " (Many leveraged longs - Dump risk HIGH)"
                elif liq_pressure == "SHORT_HEAVY":
                    liq_str += " (Many leveraged shorts - Pump risk HIGH)"

                # Order Imbalance
                imbalance_str = f"{order_imbalance:+.1f}%"
                if order_imbalance > 20:
                    imbalance_str += " (HEAVY BUY PRESSURE - Bullish)"
                elif order_imbalance < -20:
                    imbalance_str += " (HEAVY SELL PRESSURE - Bearish)"

                # Funding Rate Interpretation (NEW)
                funding_rate = metrics.get('funding_rate', 0)
                funding_str = f"{funding_rate:.4f}%"
                if funding_rate > 0.05:
                    funding_str += " (HIGH - Longs paying, contrarian BEARISH)"
                elif funding_rate > 0.02:
                    funding_str += " (Slightly bullish sentiment)"
                elif funding_rate < -0.03:
                    funding_str += " (NEGATIVE - Shorts paying, contrarian BULLISH)"
                elif funding_rate < -0.01:
                    funding_str += " (Slightly bearish sentiment)"
                else:
                    funding_str += " (Neutral)"

                # Long/Short Ratio Interpretation (NEW)
                ls_ratio = metrics.get('ls_ratio', 1.0)
                ls_str = f"{ls_ratio:.2f}"
                if ls_ratio > 1.5:
                    ls_str += " (LONG CROWDED - contrarian BEARISH, dump risk)"
                elif ls_ratio > 1.2:
                    ls_str += " (Slightly long heavy)"
                elif ls_ratio < 0.7:
                    ls_str += " (SHORT CROWDED - contrarian BULLISH, squeeze risk)"
                elif ls_ratio < 0.85:
                    ls_str += " (Slightly short heavy)"
                else:
                    ls_str += " (Balanced)"

                metrics_txt = f"""
QUANTITATIVE ALPHA METRICS (CRITICAL):
- Volume: {vol_str}
- Trend Efficiency (KER): {ker_str}
- Bollinger Squeeze: {squeeze_str}
- ADX Strategy: {adx_str}
- Volatility (ATR): {atr_pct:.2f}%
- Screener Score: {score}/100

🐋 WHALE DETECTION (SMART MONEY RADAR):
- Whale Signal: {whale_str}
- Liquidation Pressure: {liq_str}
- Order Book Imbalance: {imbalance_str}
- Funding Rate: {funding_str}
- Long/Short Ratio: {ls_str}
- Whale Confidence: {whale_confidence}%

⚡ INTERPRETATION (CONTRARIAN SIGNALS):
- PUMP: Whale PUMP_IMMINENT + Negative Funding + Short Crowded → STRONG LONG
- DUMP: Whale DUMP_IMMINENT + High Funding + Long Crowded → STRONG SHORT
- AVOID LONG: Liquidation LONG_HEAVY (longs getting rekt)
- AVOID SHORT: Liquidation SHORT_HEAVY (shorts getting squeezed)
- L/S Ratio > 1.5 = Too many longs = Dump risk = Bearish
- L/S Ratio < 0.7 = Too many shorts = Squeeze risk = Bullish
"""

            # Inject Learning Context
            if learning_context:
                metrics_txt += f"\n{learning_context}\n"

            # Build user message with market data (SCALPER FORMAT)
            user_message = f"""SCALPER ANALYSIS REQUEST (M15 Timeframe):

{metrics_txt}

GLOBAL MARKET (BTC/USDT):
...

- Trend 4H: {btc_data.get('trend_4h', 'N/A')}
- 15M Change: {btc_data.get('pct_change_15m', btc_data.get('pct_change_1h', 0))}%
- Direction: {btc_data.get('direction', 'N/A')}
- Current Price: ${btc_data.get('current_price', 0):,.2f}
- RSI 15M: {btc_data.get('rsi_15m', btc_data.get('rsi_1h', 50))}

TARGET ASSET ({symbol}):
4H CONTEXT:
- Trend: {target_4h.get('trend', 'N/A')}
- Price: ${target_4h.get('price', 0):,.4f}
- RSI: {target_4h.get('rsi', 50)}
- ATR: {target_4h.get('atr', 0)}

M15 TRIGGER (PRIMARY):
- Trend: {target_trigger.get('trend', 'N/A')}
- Price: ${target_trigger.get('price', 0):,.4f}
- RSI: {target_trigger.get('rsi', 50)}
- ATR: {target_trigger.get('atr', 0)}
- Bollinger Upper: ${target_trigger.get('bb_upper', 'N/A')}
- Bollinger Lower: ${target_trigger.get('bb_lower', 'N/A')}
- Bollinger Middle: ${target_trigger.get('bb_middle', 'N/A')}
- EMA 50: ${target_trigger.get('ema_50', 0):,.4f}
- EMA 200: ${target_trigger.get('ema_200', 0):,.4f}

CAPITAL:
- Balance: ${balance:,.2f} USDT
- Max Risk: 2% (${balance * 0.02:,.2f})

Analyze for SCALPER entry (Mean Reversion / Ping-Pong / Predictive Alpha). Provide JSON response."""

            # Call DeepSeek API (Standard V3 for Speed)
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.1, # Low temp for consistency
                max_tokens=1000,
            )

            # Parse response
            message = response.choices[0].message
            content = message.content
            
            # No reasoning_content in standard models
            reasoning_content = ""

            # Extract JSON from response
            # Sometimes AI wraps JSON in markdown code blocks
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()

            result = json.loads(json_str)

            # === VALIDATION LAYER (Prevent hallucinations) ===
            # 1. Validate signal
            valid_signals = ["LONG", "SHORT", "WAIT"]
            if result.get("signal") not in valid_signals:
                logging.warning(f"[AI] Invalid signal '{result.get('signal')}', defaulting to WAIT")
                result["signal"] = "WAIT"
            
            # 2. Validate confidence (clamp to 0-100)
            conf = result.get("confidence", 0)
            if not isinstance(conf, (int, float)):
                conf = 0
            result["confidence"] = max(0, min(100, int(conf)))
            
            # 3. Ensure trade_params exists
            if result.get("signal") != "WAIT" and not result.get("trade_params"):
                logging.warning(f"[AI] Signal {result['signal']} but no trade_params, forcing WAIT")
                result["signal"] = "WAIT"
                result["confidence"] = 0
            
            # 4. Validate trade_params if present
            if result.get("trade_params"):
                tp = result["trade_params"]
                required = ["entry_price", "stop_loss", "take_profit"]
                for field in required:
                    if field not in tp or tp[field] is None or tp[field] <= 0:
                        logging.warning(f"[AI] Invalid trade_params.{field}, forcing WAIT")
                        result["signal"] = "WAIT"
                        result["confidence"] = 0
                        break
                
                # 5. NEW: Validate SL/TP distances (Quality Control)
                if result.get("signal") != "WAIT":
                    entry = tp.get("entry_price", 0)
                    sl = tp.get("stop_loss", 0)
                    take_profit = tp.get("take_profit", 0)
                    
                    if entry > 0 and sl > 0 and take_profit > 0:
                        # Calculate distances as percentage
                        sl_distance_pct = abs(entry - sl) / entry * 100
                        tp_distance_pct = abs(take_profit - entry) / entry * 100
                        
                        # Risk:Reward ratio
                        rr_ratio = tp_distance_pct / sl_distance_pct if sl_distance_pct > 0 else 0
                        
                        # Constraints (IMPROVED v5.0 - Reduce SL hits)
                        MIN_SL_PCT = 0.5    # Minimum 0.5% SL (was 0.1% - too tight!)
                        MAX_SL_PCT = 2.5    # Maximum 2.5% SL (was 5.0% - tighter capital protection)
                        MIN_RR = 1.3        # Minimum 1.3:1 Risk:Reward (was 1.1 - better quality)
                        
                        rejection_reasons = []
                        
                        if sl_distance_pct < MIN_SL_PCT:
                            rejection_reasons.append(f"SL too tight ({sl_distance_pct:.2f}% < {MIN_SL_PCT}%)")
                        
                        if sl_distance_pct > MAX_SL_PCT:
                            rejection_reasons.append(f"SL too wide ({sl_distance_pct:.2f}% > {MAX_SL_PCT}%)")
                        
                        if rr_ratio < MIN_RR:
                            rejection_reasons.append(f"Bad RR ({rr_ratio:.1f}:1 < {MIN_RR}:1)")
                        
                        if rejection_reasons:
                            logging.warning(f"[AI] Trade rejected: {', '.join(rejection_reasons)}")
                            result["signal"] = "WAIT"
                            result["confidence"] = 0
                            result["reasoning"] = f"REJECTED: {', '.join(rejection_reasons)}"
                        else:
                            logging.info(f"[AI] Trade params valid: SL={sl_distance_pct:.2f}%, TP={tp_distance_pct:.2f}%, RR={rr_ratio:.1f}:1")

            return result

        except json.JSONDecodeError as e:
            # Fallback if JSON parsing fails
            logging.error(f"[AI] JSON Parse Error. Raw Content: {content[:500]}...")
            return {
                "symbol": str(symbol),
                "signal": "WAIT",
                "confidence": 0,
                "reasoning": f"Failed to parse AI response: {str(e)}",
                "trade_params": None
            }
        except Exception as e:
            raise Exception(f"DeepSeek analysis failed: {str(e)}")

    def analyze_vision(self, image_buffer: BytesIO) -> Dict:
        """
        Analyze chart image using OpenRouter Vision API (SCALPER MODE)

        Args:
            image_buffer: BytesIO buffer containing chart PNG

        Returns:
            Dict with visual analysis verdict
        """
        try:
            # Read image bytes and convert to base64
            image_buffer.seek(0)
            image_bytes = image_buffer.read()
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')

            # Get SCALPER vision prompt
            prompt = get_vision_prompt()

            # Call OpenRouter Vision API
            # Using Gemini 2.0 Flash Lite - Fast & Efficient Multimodal Model
            response = self.vision_client.chat.completions.create(
                model="google/gemini-2.5-flash-lite",  # Gemini 2.0 Flash Lite
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                temperature=0.2,  # Lower for more consistent analysis
                max_tokens=1500   # More tokens for detailed analysis
            )

            # Parse response
            content = response.choices[0].message.content

            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            result = json.loads(content)

            return result

        except json.JSONDecodeError as e:
            # Fallback
            return {
                "verdict": "NEUTRAL",
                "confidence": 0,
                "setup_valid": "INVALID_CHOPPY",
                "patterns_detected": [],
                "key_levels": {"support": None, "resistance": None},
                "analysis": f"Failed to parse vision response: {str(e)}"
            }
        except Exception as e:
            raise Exception(f"OpenRouter vision analysis failed: {str(e)}")

    def combine_analysis(self, logic_result: Dict, vision_result: Dict, metrics: Dict = None, whale_signal: str = 'NEUTRAL', whale_confidence: int = 0) -> Dict:
        """
        Combine DeepSeek logic and Gemini vision results using HYBRID AGGRESSIVE VETO
        Enhanced with ML-based win probability prediction (v4.0) + WHALE DETECTION VETO (Tier 1)
        + PUMP FAST TRACK (v4.3) - Lower thresholds for extreme pump/dump signals

        PHILOSOPHY: Balance Quality with Quantity for Small Cap Growth.
        Allow 'Neutral' charts if Logic is strong (Mathematical Reversal).
        Use ML to boost confidence or veto low-probability trades.
        NEW: SQUEEZE VETO prevents trading into liquidation cascades.
        NEW: PUMP FAST TRACK - Extreme movements get priority execution.
        """
        logic_signal = logic_result.get('signal', 'WAIT')
        vision_verdict = vision_result.get('verdict', 'NEUTRAL')
        logic_confidence = logic_result.get('confidence', 0)
        vision_confidence = vision_result.get('confidence', 0)
        setup_valid = vision_result.get('setup_valid', 'VALID_SETUP')

        # === 0. MOMENTUM FAST TRACK DETECTION ===
        # Use new directional momentum for fast track (replaces old pump scanner)
        momentum_direction = metrics.get('momentum_direction', 'NEUTRAL') if metrics else 'NEUTRAL'
        momentum_confidence = metrics.get('momentum_confidence', 0) if metrics else 0
        pump_vol_ratio = metrics.get('vol_ratio', 0) if metrics else 0
        roc_3 = abs(metrics.get('roc_3', 0)) if metrics else 0
        
        # Extreme movement: High momentum confidence + strong ROC
        is_extreme_movement = momentum_confidence >= 80 and roc_3 >= 2.0
        # Standard strong momentum
        is_strong_momentum = momentum_direction in ['PUMP', 'DUMP'] and momentum_confidence >= 60
        
        # Calculate adjusted threshold for strong momentum signals
        pump_threshold_reduction = 0
        if is_extreme_movement:
            pump_threshold_reduction = 15  # High confidence momentum: 75 -> 60
            logging.info(f"[MOMENTUM FAST TRACK] Strong movement: {momentum_direction} {momentum_confidence}%, ROC3={roc_3:.1f}%")
        elif is_strong_momentum:
            pump_threshold_reduction = 10  # Standard momentum: 75 -> 65
            logging.info(f"[MOMENTUM FAST TRACK] Direction: {momentum_direction} ({momentum_confidence}%)")

        # === 1. ML PREDICTION (if available) ===
        ml_win_prob = 0.5
        ml_threshold = settings.MIN_CONFIDENCE
        ml_insights = []
        ml_is_trained = False  # Flag: Is ML model trained with real data?

        if HAS_LEARNER and learner is not None and metrics:
            try:
                prediction = learner.get_prediction(metrics)
                ml_win_prob = prediction.win_probability
                ml_threshold = prediction.recommended_confidence_threshold
                ml_insights = prediction.insights

                # Check if ML is actually trained (not just rule-based fallback)
                # Rule-based fallback returns values between 0.3-0.7 typically
                # ML model can be more extreme (closer to 0 or 1)
                ml_is_trained = getattr(learner, 'model', None) is not None and getattr(learner, 'scaler', None) is not None

                if ml_is_trained:
                    logging.info(f"[ML] TRAINED Model - Win Prob: {ml_win_prob:.0%}, Threshold: {ml_threshold}%")
                else:
                    logging.info(f"[ML] Rule-Based Fallback - Win Prob: {ml_win_prob:.0%} (Collecting data...)")
            except Exception as e:
                logging.warning(f"[ML] Prediction failed: {e}")

        # === 1. WHALE SQUEEZE VETO (Tier 1 - Prevents Liquidation Cascades) ===
        # Hard veto: Don't trade INTO liquidation squeezes
        whale_veto_reason = None
        if whale_signal == 'SQUEEZE_LONGS' and logic_signal == 'LONG':
            whale_veto_reason = f"SQUEEZE_LONGS detected - Avoid LONG (cascade dump risk) [Conf: {whale_confidence}%]"
        elif whale_signal == 'SQUEEZE_SHORTS' and logic_signal == 'SHORT':
            whale_veto_reason = f"SQUEEZE_SHORTS detected - Avoid SHORT (short squeeze risk) [Conf: {whale_confidence}%]"

        if whale_veto_reason:
            logging.warning(f"[WHALE VETO] {whale_veto_reason}")
            return {
                "final_signal": "WAIT",
                "combined_confidence": 0,
                "agreement": False,
                "setup_valid": setup_valid,
                "logic_analysis": logic_result,
                "vision_analysis": vision_result,
                "recommendation": f"SKIP (Whale Veto: {whale_veto_reason})",
                "ml_win_probability": ml_win_prob,
                "ml_insights": ml_insights,
                "whale_veto": True
            }

        # === 3. HARD SAFETY CHECK ===
        # If Vision explicitly says chart is garbage (Choppy/Unreadable), we SKIP.
        # This protects you from burning fees in sideways noise.
        if setup_valid != "VALID_SETUP":
            return {
                "final_signal": "WAIT",
                "combined_confidence": 0,
                "agreement": False,
                "setup_valid": setup_valid,
                "logic_analysis": logic_result,
                "vision_analysis": vision_result,
                "recommendation": "SKIP (Vision Veto: Invalid/Choppy Setup)",
                "ml_win_probability": ml_win_prob,
                "ml_insights": ml_insights
            }

        # === 4. ML VETO CHECK ===
        # ONLY apply ML Veto if ML is actually trained with real data
        # If ML is not trained, we use standard Logic + Vision system
        if ml_is_trained and ml_win_prob < 0.3 and logic_confidence < 85:
            return {
                "final_signal": "WAIT",
                "combined_confidence": 0,
                "agreement": False,
                "setup_valid": setup_valid,
                "logic_analysis": logic_result,
                "vision_analysis": vision_result,
                "recommendation": f"SKIP (ML Veto: Win Prob {ml_win_prob:.0%} too low)",
                "ml_win_probability": ml_win_prob,
                "ml_insights": ml_insights,
                "ml_is_trained": ml_is_trained
            }

        # === NEW v5.0: QUALITY FILTER VETO ===
        # Check screener quality metrics and apply penalties/veto
        quality_veto_reasons = []
        quality_penalty = 0
        
        if metrics:
            # 1. Market Structure Check
            structure = metrics.get('structure', 'UNKNOWN')
            if structure == 'CHOPPY':
                quality_penalty += 15
                quality_veto_reasons.append("CHOPPY market structure")
            
            # 2. 1H Confirmation Check
            h1_confirmed = metrics.get('h1_confirmed', True)
            h1_conflict = metrics.get('h1_conflict', False)
            if h1_conflict or not h1_confirmed:
                quality_penalty += 20
                quality_veto_reasons.append(f"1H timeframe conflict: {metrics.get('h1_reason', 'N/A')}")
            
            # 3. S/R Proximity Check
            sr_near = metrics.get('sr_near', False)
            if sr_near:
                sr_level = metrics.get('sr_level_type', 'S/R')
                sr_dist = metrics.get('sr_distance_pct', 0)
                quality_penalty += 10
                quality_veto_reasons.append(f"Entry near {sr_level} ({sr_dist:.2f}%)")
            
            # 4. Volume Sustainability Check
            vol_sustained = metrics.get('vol_sustained', True)
            vol_strong = metrics.get('vol_strong_candles', 3)
            if not vol_sustained and vol_strong == 0:
                quality_penalty += 10
                quality_veto_reasons.append("No sustained volume")
            
            # 5. Funding Rate Filter (NEW)
            funding_bias = metrics.get('funding_bias', 'NEUTRAL')
            logic_signal = logic_result.get('signal', 'WAIT')
            
            # Penalize trades against funding pressure
            if funding_bias == 'SHORT_BIAS' and logic_signal == 'LONG':
                quality_penalty += 15
                quality_veto_reasons.append("LONG against high funding (expect dump)")
            elif funding_bias == 'LONG_BIAS' and logic_signal == 'SHORT':
                quality_penalty += 15
                quality_veto_reasons.append("SHORT against negative funding (expect pump)")
        
        # Log quality issues
        if quality_veto_reasons:
            logging.info(f"[QUALITY] Issues detected: {', '.join(quality_veto_reasons)} | Total penalty: -{quality_penalty}")
        
        # Hard veto if too many quality issues
        if quality_penalty >= 50:
            return {
                "final_signal": "WAIT",
                "combined_confidence": 0,
                "agreement": False,
                "setup_valid": setup_valid,
                "logic_analysis": logic_result,
                "vision_analysis": vision_result,
                "recommendation": f"SKIP (Quality Veto: {', '.join(quality_veto_reasons)})",
                "ml_win_probability": ml_win_prob,
                "ml_insights": ml_insights,
                "quality_veto": True,
                "quality_issues": quality_veto_reasons
            }

        # === 5. HYBRID AGREEMENT LOGIC ===
        agreement = False
        
        # Get RSI from metrics for extreme condition check
        rsi_value = metrics.get('rsi', 50) if metrics else 50
        is_rsi_extreme = rsi_value < 30 or rsi_value > 70

        # --- VISION SAFETY OVERRIDE ---
        # Refine Vision Verdict based on strong keywords in the reasoning text
        # This prevents cases where verdict is NEUTRAL but reasoning says "Avoid Shorting"
        vision_reasoning = vision_result.get('analysis', '').upper()
        has_strong_bull_keywords = any(k in vision_reasoning for k in ['ACCUMULATION', 'SPRING', 'SNIPER LONG', 'AVOID SHORT', 'PUMP IMMINENT'])
        has_strong_bear_keywords = any(k in vision_reasoning for k in ['DISTRIBUTION', 'AVOID LONG', 'SNIPER SHORT', 'DUMP IMMINENT', 'UTAD'])

        if has_strong_bull_keywords:
            if vision_verdict == "NEUTRAL": 
                logging.info("[VISION] Upgrading verdict to BULLISH based on strong keywords")
                vision_verdict = "BULLISH"
            if logic_signal == "SHORT":
                logging.warning("[SAFETY] Vision detects ACCUMULATION/SPRING - Vetoing Logic SHORT signal!")
                # Force disagreement
                vision_verdict = "BULLISH"
        
        if has_strong_bear_keywords:
            if vision_verdict == "NEUTRAL":
                logging.info("[VISION] Upgrading verdict to BEARISH based on strong keywords")
                vision_verdict = "BEARISH"
            if logic_signal == "LONG":
                logging.warning("[SAFETY] Vision detects DISTRIBUTION - Vetoing Logic LONG signal!")
                vision_verdict = "BEARISH"


        # Scenario A: PERFECT AGREEMENT (Best Quality)
        if logic_signal == "LONG" and vision_verdict == "BULLISH":
            agreement = True
        elif logic_signal == "SHORT" and vision_verdict == "BEARISH":
            agreement = True

        # Scenario X: RSI SUPER EXTREME (Override Vision Veto)
        # If RSI is extremely overextended (>80 or <20), Mean Reversion probability is very high
        # We allow Logic to override Vision's safe/long-term bias in these rare scalping cases.
        # UPDATED: Lowered to 80/20 based on TAO winning trade (RSI 83)
        elif logic_signal == "SHORT" and rsi_value > 80:
            logging.warning(f"[OVERRIDE] RSI SUPER EXTREME ({rsi_value:.1f}) > 80 - Taking SHORT despite Vision")
            agreement = True
        elif logic_signal == "LONG" and rsi_value < 20:
            logging.warning(f"[OVERRIDE] RSI SUPER EXTREME ({rsi_value:.1f}) < 20 - Taking LONG despite Vision")
            agreement = True

        # Scenario B: LOGIC OVERRIDE
        elif logic_signal != "WAIT" and vision_verdict == "NEUTRAL":
            if logic_confidence > 70:
                agreement = True
                logging.info(f"[AGREEMENT] Logic Override: {logic_confidence}%")
            elif logic_confidence > 60 and is_rsi_extreme:
                agreement = True
                logging.info(f"[AGREEMENT] RSI Extreme Override: RSI={rsi_value}")

        # Scenario C: ML BOOST - works with rule-based fallback too
        elif logic_signal != "WAIT" and ml_win_prob > 0.65:
            if logic_confidence > 60:
                agreement = True
                logging.info(f"[ML] Boosting trade - ML prob: {ml_win_prob:.0%}")

        # Scenario D: CONFLICT (Safety)
        # DeepSeek says LONG, Vision says BEARISH -> HARD REJECT.

        # === 6. CONFIDENCE SYNTHESIS (ML-Enhanced) ===
        combined_confidence = 0
        if agreement:
            if vision_verdict == "NEUTRAL":
                # If Vision was neutral, rely mostly on Logic confidence
                combined_confidence = logic_confidence
            else:
                # If both agreed, average them for stability
                combined_confidence = int((logic_confidence + vision_confidence) / 2)

            # ML Confidence Boost: ONLY if ML is actually trained
            if ml_is_trained and ml_win_prob > 0.65:
                boost = int((ml_win_prob - 0.5) * 20)  # Up to +10 points
                combined_confidence = min(100, combined_confidence + boost)
                logging.info(f"[ML] Confidence boosted by {boost} (Win Prob: {ml_win_prob:.0%})")
            
            # NEW v5.0: Apply Quality Penalty
            if quality_penalty > 0:
                combined_confidence = max(0, combined_confidence - quality_penalty)
                logging.info(f"[QUALITY] Confidence reduced by {quality_penalty} (issues: {len(quality_veto_reasons)})")

        # === 7. MOMENTUM CONFIDENCE BOOST ===
        # For strong momentum, boost confidence if direction matches
        momentum_boost = 0
        if is_extreme_movement and agreement:
            # Extreme movement + AI agrees = boost confidence
            momentum_boost = min(10, int(momentum_confidence / 10))  # +10 max for 100% conf
            combined_confidence = min(100, combined_confidence + momentum_boost)
            logging.info(f"[MOMENTUM] Confidence boosted +{momentum_boost} (extreme movement)")
        elif is_strong_momentum and agreement:
            # Strong momentum gets small boost
            momentum_boost = min(5, int(momentum_confidence / 20))  # +5 max
            combined_confidence = min(100, combined_confidence + momentum_boost)
            logging.info(f"[MOMENTUM] Confidence boosted +{momentum_boost} (strong direction)")

        # === DYNAMIC THRESHOLD (Quality-based) ===
        final_signal = logic_signal if agreement else "WAIT"
        
        # Base threshold from ML or settings
        base_threshold = ml_threshold if HAS_LEARNER else settings.MIN_CONFIDENCE
        
        # Dynamic adjustment based on signal quality
        # Tier 1: Whale + Vision agree = lowest threshold (high conviction)
        # Tier 2: Logic + Vision agree = medium threshold
        # Tier 3: Logic only = highest threshold
        
        has_whale_signal = whale_signal in ['PUMP_IMMINENT', 'DUMP_IMMINENT']
        has_vision_agree = (logic_signal == "LONG" and vision_verdict == "BULLISH") or \
                          (logic_signal == "SHORT" and vision_verdict == "BEARISH")
        
        if has_whale_signal and has_vision_agree:
            # Tier 1: Strong confluence - aggressive threshold
            effective_threshold = 60
            logging.info(f"[THRESHOLD] Tier 1 (Whale+Vision): {effective_threshold}%")
        elif has_vision_agree:
            # Tier 2: Good agreement - medium threshold
            effective_threshold = 65
            logging.info(f"[THRESHOLD] Tier 2 (Vision agree): {effective_threshold}%")
        elif has_whale_signal:
            # Tier 2b: Whale signal but no vision agree
            effective_threshold = 68
            logging.info(f"[THRESHOLD] Tier 2b (Whale only): {effective_threshold}%")
        else:
            # Tier 3: Logic only - conservative
            effective_threshold = max(55, base_threshold - pump_threshold_reduction)
            if pump_threshold_reduction > 0:
                logging.info(f"[THRESHOLD] Tier 3 (Momentum): {base_threshold}% -> {effective_threshold}%")

        recommendation = "SKIP"
        if agreement and combined_confidence >= effective_threshold:
            recommendation = "EXECUTE"
            logging.info(f"[EXECUTE] Confidence {combined_confidence}% >= Threshold {effective_threshold}%")

        # === CACHE ANALYSIS FOR LEARNING ===
        # Save ALL analysis results (not just trades) to ai_analysis_cache
        if HAS_LEARNER and learner is not None and metrics:
            try:
                # Build analysis cache data
                cache_data = {
                    'symbol': metrics.get('symbol', 'UNKNOWN'),
                    'logic_signal': logic_result.get('signal'),
                    'logic_confidence': logic_result.get('confidence', 0),
                    'logic_reasoning': logic_result.get('reasoning', ''),
                    'vision_signal': vision_result.get('verdict'),  # FIX: Was 'signal', but Vision returns 'verdict'
                    'vision_confidence': vision_result.get('confidence', 0),
                    'vision_reasoning': vision_result.get('analysis', ''),  # FIX: Was 'reasoning', but Vision returns 'analysis'
                    'ml_win_probability': ml_win_prob,
                    'ml_threshold': int(ml_threshold),  # Ensure INT for database
                    'ml_is_trained': ml_is_trained,
                    'ml_insights': ml_insights,
                    'final_signal': final_signal,
                    'final_confidence': combined_confidence,
                    'recommendation': recommendation,
                    'adx': metrics.get('adx'),
                    'vol_z_score': metrics.get('vol_z_score'),
                    'ker': metrics.get('efficiency_ratio', metrics.get('ker', 0)),
                    'is_squeeze': metrics.get('is_squeeze'),
                    'screener_score': metrics.get('score'),
                    'whale_signal': whale_signal,
                    'whale_confidence': whale_confidence,
                    'btc_trend': 'UNKNOWN',  # Could be extracted from logic_result
                }

                # Cache the analysis
                learner.cache_analysis(cache_data)

            except Exception as e:
                logging.error(f"[LEARNER] Failed to cache analysis: {e}")

        return {
            "final_signal": final_signal,
            "combined_confidence": combined_confidence,
            "agreement": agreement,
            "setup_valid": setup_valid,
            "logic_analysis": logic_result,
            "vision_analysis": vision_result,
            "recommendation": recommendation,
            "ml_win_probability": ml_win_prob,
            "ml_threshold": effective_threshold,
            "ml_insights": ml_insights,
            "ml_is_trained": ml_is_trained,
            # Momentum tracking metadata
            "momentum_direction": momentum_direction,
            "momentum_confidence": momentum_confidence,
            "is_extreme_movement": is_extreme_movement,
            "is_strong_momentum": is_strong_momentum,
            "momentum_boost_applied": momentum_boost,
            "threshold_reduction": pump_threshold_reduction,
            # Quality filter metadata
            "quality_penalty": quality_penalty,
            "quality_issues": quality_veto_reasons if quality_veto_reasons else []
        }
