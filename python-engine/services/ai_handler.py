"""
AI Handler Service
Integrates DeepSeek (Logic) and Gemini (Vision) for hybrid trading analysis
"""

import json
import base64
from typing import Dict, Optional
from io import BytesIO
from openai import OpenAI
from config import settings


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

        # System prompt for DeepSeek
        self.system_prompt = """ROLE: Quantitative Risk Manager & Senior Crypto Analyst.

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

OUTPUT JSON:
{ "symbol": "...", "signal": "LONG/SHORT/WAIT", "confidence": int, "reasoning": "...", "trade_params": { "entry_price": float, "stop_loss": float, "take_profit": float, "suggested_leverage": int, "position_size_usdt": float } }"""

    def analyze_logic(
        self,
        btc_data: Dict,
        target_4h: Dict,
        target_1h: Dict,
        balance: float = 1000.0,
        symbol: str = "UNKNOWN"
    ) -> Dict:
        """
        Analyze trading logic using DeepSeek

        Args:
            btc_data: BTC market context
            target_4h: Target asset 4H data
            target_1h: Target asset 1H data
            balance: Trading balance in USDT
            symbol: Trading symbol

        Returns:
            Dict with trading signal and parameters
        """
        try:
            # Prepare user message with market data
            user_message = f"""MARKET ANALYSIS REQUEST:

GLOBAL MARKET (BTC/USDT):
- Trend 4H: {btc_data['trend_4h']}
- 1H Change: {btc_data['pct_change_1h']}%
- Direction: {btc_data['direction']}
- Current Price: ${btc_data['current_price']:,.2f}
- RSI 1H: {btc_data['rsi_1h']}

TARGET ASSET ({symbol}):
4H CONTEXT:
- Trend: {target_4h['trend']}
- Price: ${target_4h['price']:,.4f}
- RSI: {target_4h['rsi']}
- ATR: {target_4h['atr']}
- EMA 50: ${target_4h['ema_50']:,.4f}
- EMA 200: ${target_4h['ema_200']:,.4f}

1H TRIGGER:
- Trend: {target_1h['trend']}
- Price: ${target_1h['price']:,.4f}
- RSI: {target_1h['rsi']}
- ATR: {target_1h['atr']}
- EMA 50: ${target_1h['ema_50']:,.4f}
- EMA 200: ${target_1h['ema_200']:,.4f}

CAPITAL:
- Balance: ${balance:,.2f} USDT
- Max Risk: 2% (${balance * 0.02:,.2f})

Analyze this data and provide a trading decision in JSON format."""

            # Call DeepSeek API (Reasoner Model)
            response = self.deepseek_client.chat.completions.create(
                model="deepseek-reasoner",
                messages=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_message}
                ],
                temperature=0.3,
                max_tokens=2000, # Increased for COT
            )

            # Parse response
            message = response.choices[0].message
            content = message.content
            reasoning_content = getattr(message, 'reasoning_content', '')

            # Extract JSON from response
            # Sometimes AI wraps JSON in markdown code blocks
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0].strip()

            result = json.loads(json_str)

            # Append Chain of Thought to the reasoning field if available
            if reasoning_content:
                result['reasoning'] = f"[THINKING PROCESS]\n{reasoning_content}\n\n[FINAL ANALYSIS]\n{result.get('reasoning', '')}"

            return result

        except json.JSONDecodeError as e:
            # Fallback if JSON parsing fails
            return {
                "symbol": target_4h.get('symbol', 'UNKNOWN'),
                "signal": "WAIT",
                "confidence": 0,
                "reasoning": f"Failed to parse AI response: {str(e)}",
                "trade_params": None
            }
        except Exception as e:
            raise Exception(f"DeepSeek analysis failed: {str(e)}")

    def analyze_vision(self, image_buffer: BytesIO) -> Dict:
        """
        Analyze chart image using OpenRouter Vision API

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

            # Prompt for vision analysis
            prompt = """Analyze this candlestick chart. Identify key patterns and technical signals.

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

            # Call OpenRouter Vision API (using Google Gemini 2.0 Flash Lite via OpenRouter)
            response = self.vision_client.chat.completions.create(
                model="google/gemini-2.5-flash-lite-preview-09-2025",  # Vision-capable model
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

        return {
            "final_signal": logic_signal if agreement else "WAIT",
            "combined_confidence": combined_confidence,
            "agreement": agreement,
            "logic_analysis": logic_result,
            "vision_analysis": vision_result,
            "recommendation": "EXECUTE" if (agreement and combined_confidence >= settings.MIN_CONFIDENCE) else "SKIP"
        }
