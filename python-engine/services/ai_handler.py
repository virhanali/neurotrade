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


def get_system_prompt(mode: str = "INVESTOR") -> str:
    """
    Returns the appropriate system prompt based on trading mode
    
    Args:
        mode: Trading mode - "SCALPER" or "INVESTOR"
    
    Returns:
        System prompt string for the Logic LLM
    """
    if mode == "SCALPER":
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

STRATEGY MAP based on MARKET STRUCTURE:
A. IF BANDS ARE FLAT (SIDEWAYS):
   - **Action:** AGGRESSIVE Ping-Pong. Buy Low, Sell High. target opposite band.

B. IF BANDS ARE ANGLED (TRENDING):
   - **Action:** CONSERVATIVE Pullback. Only enter on retest of EMA 20.

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

EXECUTION PARAMETERS:
   - ENTRY: Limit Order.
   - STOP LOSS: TIGHT.
   - LEVERAGE: 
      - Predictive Alpha (Sniper) -> 12x-20x (Tight Stop, Huge Reward).
      - Sideways -> 10x-20x.
      - Trending -> 5x-10x.
      - God Candle -> 0x.

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
    else:  # INVESTOR mode (default)
        return """ROLE: Quantitative Risk Manager & Senior Crypto Analyst.

INPUT DATA:
1. GLOBAL MARKET (BTC/USDT): [Trend 4H, % Change 1H]
2. TARGET ASSET CONTEXT (4H Chart): [Trend, EMA Structure]
3. TARGET ASSET TRIGGER (1H Chart): [Price, RSI, ATR]
4. CAPITAL: [Balance, Max Risk 2%]

LOGIC FLOW:
PHASE 1: THE "BIG BROTHER" FILTER (BTC Check)
- IF BTC is dumping (Drop > 1% in 1H) -> REJECT ALL LONG SIGNALS. Only Short allowed.
- IF BTC is pumping (Rise > 1% in 1H) -> REJECT ALL SHORT SIGNALS. Only Long allowed.

PHASE 2: TREND ALIGNMENT (4H Context)
- IF Target 4H is UPTREND -> Look for LONG.
- IF Target 4H is DOWNTREND -> Look for SHORT.
- IF 1H signal contradicts 4H trend -> RETURN "WAIT".

PHASE 3: EXECUTION (1H Trigger)
- ENTRY: Market Price.
- SL: Technical Level (Swing Low/High) OR 2x ATR.
- TP: Min 1.5 Risk-Reward Ratio.

PHASE 4: RISK SIZING
- Calculate Position Size so loss never exceeds 2% of capital.
- Leverage: Max 5x (Alts), 10x (BTC).

OUTPUT FORMAT (STRICT JSON ONLY):
The final response content MUST be a valid raw JSON object. Do not use markdown blocks.
{ "symbol": "...", "signal": "LONG/SHORT/WAIT", "confidence": int, "reasoning": "...", "trade_params": { "entry_price": float, "stop_loss": float, "take_profit": float, "suggested_leverage": int, "position_size_usdt": float } }"""


def get_vision_prompt(mode: str = "INVESTOR") -> str:
    """
    Returns the appropriate vision analysis prompt based on trading mode
    
    Args:
        mode: Trading mode - "SCALPER" or "INVESTOR"
    
    Returns:
        Vision prompt string for chart analysis
    """
    if mode == "SCALPER":
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
    else:  # INVESTOR mode
        return """Analyze this candlestick chart. Identify key patterns and technical signals.

Look for:
- Chart patterns (Bull Flag, Head & Shoulders, Double Top/Bottom, Triangle, etc.)
- Trend direction and strength
- Support and resistance levels
- Volume confirmation
- Potential reversal or continuation signals

Provide a clear verdict: BULLISH, BEARISH, or NEUTRAL.

Format your response as JSON:
{
    "verdict": "BULLISH/BEARISH/NEUTRAL",
    "confidence": <0-100>,
    "patterns_detected": ["list", "of", "patterns"],
    "key_levels": {
        "support": <price or null>,
        "resistance": <price or null>
    },
    "analysis": "brief explanation"
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
        mode: str = "INVESTOR"
    ) -> Dict:
        """
        Analyze trading logic using DeepSeek

        Args:
            btc_data: BTC market context
            target_4h: Target asset 4H data
            target_trigger: Target asset trigger data (1H for INVESTOR, 15M for SCALPER)
            balance: Trading balance in USDT
            symbol: Trading symbol
            mode: Trading mode - "SCALPER" or "INVESTOR"

        Returns:
            Dict with trading signal and parameters
        """
        try:
            # Get mode-specific system prompt
            system_prompt = get_system_prompt(mode)
            
            # Determine timeframe label based on mode
            trigger_tf = "15M" if mode == "SCALPER" else "1H"
            
            # Build user message with market data
            if mode == "SCALPER":
                # SCALPER mode: Include Bollinger Bands data
                user_message = f"""SCALPER ANALYSIS REQUEST (M15 Timeframe):

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

Analyze for SCALPER entry (Mean Reversion / Ping-Pong strategy). Provide JSON response."""
            else:
                # INVESTOR mode: Standard trend following analysis
                user_message = f"""MARKET ANALYSIS REQUEST:

GLOBAL MARKET (BTC/USDT):
- Trend 4H: {btc_data.get('trend_4h', 'N/A')}
- 1H Change: {btc_data.get('pct_change_1h', 0)}%
- Direction: {btc_data.get('direction', 'N/A')}
- Current Price: ${btc_data.get('current_price', 0):,.2f}
- RSI 1H: {btc_data.get('rsi_1h', 50)}

TARGET ASSET ({symbol}):
4H CONTEXT:
- Trend: {target_4h.get('trend', 'N/A')}
- Price: ${target_4h.get('price', 0):,.4f}
- RSI: {target_4h.get('rsi', 50)}
- ATR: {target_4h.get('atr', 0)}
- EMA 50: ${target_4h.get('ema_50', 0):,.4f}
- EMA 200: ${target_4h.get('ema_200', 0):,.4f}

1H TRIGGER:
- Trend: {target_trigger.get('trend', 'N/A')}
- Price: ${target_trigger.get('price', 0):,.4f}
- RSI: {target_trigger.get('rsi', 50)}
- ATR: {target_trigger.get('atr', 0)}
- EMA 50: ${target_trigger.get('ema_50', 0):,.4f}
- EMA 200: ${target_trigger.get('ema_200', 0):,.4f}

CAPITAL:
- Balance: ${balance:,.2f} USDT
- Max Risk: 2% (${balance * 0.02:,.2f})

Analyze this data and provide a trading decision in JSON format."""

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

    def analyze_vision(self, image_buffer: BytesIO, mode: str = "INVESTOR") -> Dict:
        """
        Analyze chart image using OpenRouter Vision API

        Args:
            image_buffer: BytesIO buffer containing chart PNG
            mode: Trading mode - "SCALPER" or "INVESTOR"

        Returns:
            Dict with visual analysis verdict
        """
        try:
            # Read image bytes and convert to base64
            image_buffer.seek(0)
            image_bytes = image_buffer.read()
            image_base64 = base64.b64encode(image_bytes).decode('utf-8')

            # Get mode-specific vision prompt
            prompt = get_vision_prompt(mode)

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
        Combine DeepSeek logic and Gemini vision results

        Args:
            logic_result: Result from DeepSeek
            vision_result: Result from Gemini

        Returns:
            Combined analysis with final decision
        """
        # Check if both agree or vision is neutral
        logic_signal = logic_result.get('signal', 'WAIT')
        vision_verdict = vision_result.get('verdict', 'NEUTRAL')
        logic_confidence = logic_result.get('confidence', 0)
        vision_confidence = vision_result.get('confidence', 0)
        
        # Check for SCALPER-specific vision validation
        setup_valid = vision_result.get('setup_valid', 'VALID_SETUP')

        # Agreement logic
        agreement = False
        if vision_verdict == "NEUTRAL":
            agreement = True  # Neutral doesn't contradict
        elif logic_signal == "LONG" and vision_verdict == "BULLISH":
            agreement = True
        elif logic_signal == "SHORT" and vision_verdict == "BEARISH":
            agreement = True
        elif logic_signal == "WAIT":
            agreement = True  # WAIT is always safe

        # Calculate combined confidence
        if agreement:
            # Average confidence if both agree
            combined_confidence = int((logic_confidence + vision_confidence) / 2) if vision_verdict != "NEUTRAL" else logic_confidence
        else:
            # Penalize confidence if they disagree
            combined_confidence = max(0, logic_confidence - 30)
        
        # Additional penalty for INVALID_CHOPPY setup in SCALPER mode
        if setup_valid == "INVALID_CHOPPY":
            combined_confidence = max(0, combined_confidence - 20)

        return {
            "final_signal": logic_signal if agreement else "WAIT",
            "combined_confidence": combined_confidence,
            "agreement": agreement,
            "setup_valid": setup_valid,
            "logic_analysis": logic_result,
            "vision_analysis": vision_result,
            "recommendation": "EXECUTE" if (agreement and combined_confidence >= settings.MIN_CONFIDENCE and setup_valid != "INVALID_CHOPPY") else "SKIP"
        }
