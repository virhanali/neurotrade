"""
AI Handler Service
Integrates DeepSeek (Logic) and Gemini (Vision) for hybrid trading analysis
Supports SCALPER (M15 Mean Reversion) and INVESTOR (H1/4H Trend Following) modes
"""

import json
import base64
from typing import Dict, Optional
from io import BytesIO
from openai import OpenAI
from config import settings


def get_system_prompt() -> str:
    """
    Returns the system prompt for SCALPER mode (M15 Smart Money/Predictive Alpha)
    """
    return """ROLE: Elite Algo-Trading Execution Unit (M15 Specialist).
CONTEXT: This candidate has ALREADY PASSED strict technical filters:
1. High Volatility & Volume Spike detected.
2. 4H Trend Alignment confirmed (Screener Logic).
3. RSI is in "Action Zone" (Oversold/Overbought).

YOUR MISSION: Validate the M15 Swing Setup and generate PRECISE execution parameters.

CRITICAL WARNING (LOSS PREVENTION):
- DO NOT FIGHT MOMENTUM. Touching a Bollinger Band is NOT a signal.
- RSI > 70 is NOT a Short signal if the last candle is a big Green Marubozu (Breakout).
- RSI < 30 is NOT a Long signal if the last candle is a big Red Marubozu (Dump).
- YOU MUST SEE REJECTION (Long Wicks) or REVERSAL PATTERNS (Engulfing) before entry.

STRATEGY MAP based on QUANTITATIVE DATA (ADX):
A. IF ADX < 25 (WEAK TREND / SIDEWAYS):
   - **MODE:** PING-PONG SCALPER (Mean Reversion).
   - **ACTION:** Buy at Lower Bollinger Band. Sell at Upper Bollinger Band.
   - **FORBIDDEN:** Do NOT chase Breakouts here (Most are fakeouts).

B. IF ADX > 25 (STRONG TREND):
   - **MODE:** MOMENTUM RIDER (Trend Following).
   - **ACTION:** Enter on Pullback to EMA 20 or Valid Breakout with Volume.
   - **FORBIDDEN:** Do NOT Counter-Trade. (If Bullish Trend, NO SHORTS).

C. IF PREDICTIVE ALPHA (THE "SMART MONEY" SETUP):
   - **Scenario:** Price is coiling tight (Bollinger Squeeze) or moving in a Channel.
   - **PRE-PUMP SIGNALS:**
     1. "The Squeeze": Bands are super tight.
     2. "Silent Accumulation": Price is flat, but Volume is slowly rising (Green candles dominant).
     3. "Higher Lows": Sellers try to push down, but wicks keep closing higher.
     -> ACTION: LONG on the first forceful Breakout candle.
   - **PRE-DUMP SIGNALS:**
     1. "Distribution": Price struggles at resistance with long Upper Wicks.
     2. "Lower Highs": Buyers consistenly failing to make new highs.
     3. "Bear Flag": Weak bounce after a drop.
     -> ACTION: SHORT on the breakdown of support.

D. IF EXTREME VOLATILITY (GOD CANDLE):
   - **Action:** HARD WAIT. Stop all trading. Let the dust settle.

EXECUTION PARAMETERS (STRICT RISK MANAGEMENT):
   - ENTRY: Limit Order at Current Price.
   - STOP LOSS (SL) CALCULATION for High Leverage (20x):
     - LONG: Low of previous candle MINUS (ATR * 0.5) buffer.
     - SHORT: High of previous candle PLUS (ATR * 0.5) buffer.
     - HARD CAP: SL distance MUST NOT exceed 1.5% price movement (to avoid liquidation).
   - TAKE PROFIT (TP) CALCULATION:
     - MINIMUM Risk-to-Reward (RR): 1:2 (TP distance must be 2x SL distance).
     - AIM FOR: 3% - 5% price movement for Pump/Dump setups.
   - LEVERAGE: 
      - Predictive Alpha (Sniper) -> 15x-20x.
      - Trend Rider -> 10x-15x.
      - Sideways Ping-Pong -> 20x (Tight SL).

OUTPUT FORMAT (JSON ONLY):
The final response content MUST be a valid raw JSON object. Do not use markdown blocks.
{
  "symbol": "string",
  "signal": "LONG" | "SHORT" | "WAIT",
  "confidence": 0-100,
  "reasoning": "Strategy: Predictive Alpha? Identified Accumulation/Distribution? ...",
  "trade_params": {
    "entry_price": float,
    "stop_loss": float,
    "take_profit": float,
    "suggested_leverage": int,
    "position_size_usdt": float
  }
}"""


def get_vision_prompt() -> str:
    """
    Returns the vision analysis prompt for SCALPER mode
    """
    return """ACT AS: Elite Technical Chart Pattern Scanner.
CONTEXT: Technical Screener indicates price is in a KEY ACTION ZONE.
TASK: IDENTIFY PREDICTIVE STRUCTURES (Pump/Dump Precursors).

VISUAL CHECKLIST:
1. **PREDICTIVE PATTERNS (THE ALPHA)**:
   - **SQUEEZE / TRIANGLE**: Price coiling into a point + Low Volatility. -> PRE-BREAKOUT.
   - **BULL FLAG**: Channel down after a sharp move up. -> BULLISH.
   - **BEAR FLAG**: Channel up after a sharp move down. -> BEARISH.
   - **HIGHER LOWS**: Wicks keep closing higher (Buyers stepping up). -> BULLISH.
   - **LOWER HIGHS**: Wicks keep closing lower (Sellers pressing down). -> BEARISH.

2. **BOLLINGER BANDS**:
   - **ALLIGATOR MOUTH**: Bands opening wide? -> EXPLOSION DETECTED.
   - **FLAT/PARALLEL**: Sideways Range? -> RANGE PLAY.

3. **CANDLESTICK SIGNALS**:
   - **REJECTION**: Long Wicks at key levels.
   - **MOMENTUM**: Big Marubozu candles.

DECISION LOGIC:
- Predictive Pattern + Contracting Bands -> VOTE BULLISH/BEARISH (Pre-Breakout / Sniper).
- Band Expansion + Momentum AFTER Pattern -> VOTE BULLISH/BEARISH (Valid Breakout Entry).
- Band Expansion (Random) + Big Candle -> VOTE NEUTRAL (Chase/FOMO Prevention).
- Flat Bands + Rejection Wick -> VOTE BULLISH/BEARISH (Range Setup).

OUTPUT FORMAT (JSON):
{
    "verdict": "BULLISH/BEARISH/NEUTRAL",
    "confidence": <0-100>,
    "setup_valid": "VALID_SETUP" or "INVALID_CHOPPY" or "DANGEROUS_BREAKOUT",
    "patterns_detected": ["Ascending Triangle", "Bull Flag", "Squeeze", "Higher Lows"],
    "key_levels": {
        "support": <price or null>,
        "resistance": <price or null>
    },
    "analysis": "Visual analysis of predictive structures and patterns..."
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
        metrics: Optional[Dict] = None
    ) -> Dict:
        """
        Analyze trading logic using DeepSeek (SCALPER MODE ONLY)

        Args:
            btc_data: BTC market context
            target_4h: Target asset 4H data
            target_trigger: Target asset trigger data (15M)
            balance: Trading balance in USDT
            symbol: Trading symbol
            metrics: Alpha metrics from screener (Optional)

        Returns:
            Dict with trading signal and parameters
        """
        try:
            # Get SCALPER system prompt
            system_prompt = get_system_prompt()
            
            # Prepare Metrics Text
            metrics_txt = "N/A"
            if metrics:
                vol_ratio = metrics.get('vol_ratio', 0)
                is_squeeze = metrics.get('is_squeeze', False)
                score = metrics.get('score', 0)
                adx = metrics.get('adx', 0)
                atr_pct = metrics.get('atr_pct', 0)
                
                squeeze_str = "YES (EXPLOSION IMMINENT - PREPARE ENTRY)" if is_squeeze else "NO"
                
                vol_str = f"{vol_ratio:.2f}x"
                if vol_ratio > 3.0: vol_str += " (WHALE ACTIVITY DETECTED - FOLLOW SMART MONEY)"
                elif vol_ratio > 1.5: vol_str += " (Elevated)"
                else: vol_str += " (Normal)"
                
                adx_str = f"{adx:.1f} (WEAK)" if adx < 25 else f"{adx:.1f} (STRONG)"
                if adx > 50: adx_str = f"{adx:.1f} (SUPER TREND - DO NOT FADE)"
                
                metrics_txt = f"""
QUANTITATIVE ALPHA METRICS (CRITICAL):
- Volume Ratio (RVOL): {vol_str}
- Bollinger Squeeze: {squeeze_str}
- ADX (Trend Strength): {adx_str}
- Volatility (ATR): {atr_pct:.2f}%
- Screener Score: {score}/100
"""

            # Build user message with market data (SCALPER FORMAT)
            user_message = f"""SCALPER ANALYSIS REQUEST (M15 Timeframe):

{metrics_txt}

GLOBAL MARKET (BTC/USDT):
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

            return result

        except json.JSONDecodeError as e:
            # Fallback if JSON parsing fails
            print(f"DEBUG: JSON Parse Error. Raw Content: {content[:500]}...") # Print first 500 chars of raw content
            return {
                "symbol": str(symbol), # Ensure symbol is string
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

            # Call OpenRouter Vision API (using Google Gemini 2.0 Flash Lite via OpenRouter)
            response = self.vision_client.chat.completions.create(
                model="google/gemini-2.0-flash-lite-001",  # Cost-effective Vision model
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
                temperature=0.3,
                max_tokens=1000
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

    def combine_analysis(self, logic_result: Dict, vision_result: Dict) -> Dict:
        """
        Combine DeepSeek logic and Gemini vision results using HYBRID AGGRESSIVE VETO
        
        PHILOSOPHY: Balance Quality with Quantity for Small Cap Growth.
        Allow 'Neutral' charts if Logic is strong (Mathematical Reversal).
        """
        logic_signal = logic_result.get('signal', 'WAIT')
        vision_verdict = vision_result.get('verdict', 'NEUTRAL')
        logic_confidence = logic_result.get('confidence', 0)
        vision_confidence = vision_result.get('confidence', 0)
        setup_valid = vision_result.get('setup_valid', 'VALID_SETUP')

        # === 1. HARD SAFETY CHECK ===
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
                "recommendation": "SKIP (Vision Veto: Invalid/Choppy Setup)"
            }

        # === 2. HYBRID AGREEMENT LOGIC ===
        agreement = False
        
        # Scenario A: PERFECT AGREEMENT (Best Quality)
        if logic_signal == "LONG" and vision_verdict == "BULLISH":
            agreement = True
        elif logic_signal == "SHORT" and vision_verdict == "BEARISH":
            agreement = True
            
        # Scenario B: LOGIC OVERRIDE (Quantity Booster)
        # If Vision is NEUTRAL (unsure), but DeepSeek is VERY CONFIDENT (>75%), we take it.
        # DeepSeek sees math (RSI Div) that Vision might miss.
        elif logic_signal != "WAIT" and vision_verdict == "NEUTRAL":
            if logic_confidence > 75:
                agreement = True
        
        # Scenario C: CONFLICT (Safety)
        # DeepSeek says LONG, Vision says BEARISH -> HARD REJECT.
        
        # === 3. CONFIDENCE SYNTHESIS ===
        combined_confidence = 0
        if agreement:
            if vision_verdict == "NEUTRAL":
                # If Vision was neutral, rely mostly on Logic confidence
                combined_confidence = logic_confidence
            else:
                # If both agreed, average them for stability
                combined_confidence = int((logic_confidence + vision_confidence) / 2)
        
        # Final Decision
        final_signal = logic_signal if agreement else "WAIT"
        
        recommendation = "SKIP"
        if agreement and combined_confidence >= settings.MIN_CONFIDENCE:
            recommendation = "EXECUTE"

        return {
            "final_signal": final_signal,
            "combined_confidence": combined_confidence,
            "agreement": agreement,
            "setup_valid": setup_valid,
            "logic_analysis": logic_result,
            "vision_analysis": vision_result,
            "recommendation": recommendation
        }
