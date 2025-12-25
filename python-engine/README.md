# NeuroTrade AI - Python Intelligence Engine

AI-powered trading signal generator using Hybrid AI (DeepSeek + Gemini Vision).

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                  PYTHON INTELLIGENCE ENGINE                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │   Screener   │───▶│ Data Fetcher │───▶│   Charter    │  │
│  │  (Market)    │    │   (CCXT)     │    │ (mplfinance) │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│         │                    │                    │          │
│         └────────────────────┴────────────────────┘          │
│                              │                               │
│                    ┌─────────▼─────────┐                     │
│                    │   AI Handler      │                     │
│                    │  (Hybrid Logic)   │                     │
│                    └─────────┬─────────┘                     │
│                              │                               │
│              ┌───────────────┴───────────────┐               │
│              │                               │               │
│     ┌────────▼────────┐           ┌─────────▼────────┐      │
│     │  DeepSeek API   │           │   Gemini Vision  │      │
│     │ (Logic Analysis)│           │ (Chart Analysis) │      │
│     └────────┬────────┘           └─────────┬────────┘      │
│              │                               │               │
│              └───────────────┬───────────────┘               │
│                              │                               │
│                    ┌─────────▼─────────┐                     │
│                    │  Combined Signal  │                     │
│                    │   (Confidence)    │                     │
│                    └───────────────────┘                     │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

## Features

### 1. Market Screener
- Scans **all Binance Futures USDT pairs**
- Filters by:
  - Volume > $50M (liquid coins)
  - Volatility > 1.5% (1H change)
- Returns **Top 5 opportunities**

### 2. Data Fetcher
- Fetches OHLCV data (4H + 1H timeframes)
- Calculates indicators: RSI, ATR, EMA (50, 200)
- Monitors **BTC context** (market filter)

### 3. Chart Generator
- Binance-style candlestick charts
- Bollinger Bands + Volume
- EMA overlays (50, 200)

### 4. Hybrid AI System

#### DeepSeek (Logic)
**Role:** Quantitative Risk Manager
- Applies **4-phase decision flow**:
  1. BTC Filter (reject contradicting signals)
  2. Trend Alignment (4H context)
  3. Execution (1H trigger)
  4. Risk Sizing (2% max risk)
- Returns JSON with entry, SL, TP, leverage

#### Gemini Vision (Visual)
**Role:** Pattern Recognition
- Analyzes chart images
- Detects patterns (Bull Flag, H&S, etc.)
- Returns: BULLISH/BEARISH/NEUTRAL

#### Combined Decision
- **Execute** if:
  - Both agree OR vision is neutral
  - Confidence ≥ 75%

## API Endpoints

### `GET /health`
Health check endpoint.

### `GET /screener/summary`
Get market screener statistics.

**Response:**
```json
{
  "total_pairs": 150,
  "liquid_pairs": 45,
  "volatile_pairs": 12,
  "opportunities_found": 8,
  "top_opportunities": [...]
}
```

### `POST /analyze/market`
Main analysis endpoint - generates trading signals.

**Request:**
```json
{
  "balance": 1000.0,
  "custom_symbols": ["BTC/USDT", "ETH/USDT"] // Optional
}
```

**Response:**
```json
{
  "timestamp": "2024-01-01T12:00:00",
  "btc_context": {
    "trend_4h": "UPTREND",
    "pct_change_1h": 1.5,
    "direction": "PUMPING"
  },
  "opportunities_screened": 5,
  "valid_signals": [
    {
      "symbol": "ETH/USDT",
      "final_signal": "LONG",
      "combined_confidence": 82,
      "agreement": true,
      "recommendation": "EXECUTE",
      "trade_params": {
        "entry_price": 2250.50,
        "stop_loss": 2230.00,
        "take_profit": 2280.75,
        "suggested_leverage": 5,
        "position_size_usdt": 200.0
      }
    }
  ],
  "execution_time_seconds": 12.5
}
```

## Configuration

Set these environment variables in `.env`:

```bash
# Binance API
BINANCE_API_KEY=your_key
BINANCE_API_SECRET=your_secret

# DeepSeek API (logic)
DEEPSEEK_API_KEY=your_key

# Gemini API (vision)
OPENROUTER_API_KEY=your_key
```

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

## Docker

```bash
# Build
docker build -t neurotrade-python-engine .

# Run
docker run -p 8000:8000 --env-file .env neurotrade-python-engine
```

## Technical Stack

| Component | Library |
|-----------|---------|
| Web Framework | FastAPI |
| Exchange | CCXT (Binance Futures) |
| Indicators | ta (Technical Analysis) |
| Charts | mplfinance |
| AI Logic | DeepSeek (OpenAI SDK) |
| AI Vision | Gemini (Google GenAI) |
| Data | Pandas, NumPy |

## Workflow

1. **Screen Market** → Filter top volatile + liquid coins
2. **Fetch BTC** → Get market direction (PUMPING/DUMPING)
3. **For each coin:**
   - Fetch 4H + 1H data
   - Calculate indicators (RSI, ATR, EMA)
   - Generate chart image
   - **DeepSeek:** Analyze logic + risk
   - **Gemini:** Analyze chart patterns
   - **Combine:** Check agreement + confidence
4. **Return** → Valid signals (≥75% confidence)

## Error Handling

- Individual coin failures don't stop the pipeline
- Continues analyzing remaining symbols
- Returns partial results if some succeed

## Performance

- Concurrent AI calls (asyncio)
- Typical execution: 10-15s for 5 coins
- Chart generation: ~1s per chart
- AI analysis: ~2-3s per coin
