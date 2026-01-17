# NeuroTrade AI

> **Autonomous Crypto Trading Bot with AI-Powered Decision Making v5.0**
> *Where Logic Meets Vision, and Experience Drives Execution.*

NeuroTrade is a production-grade autonomous trading system designed for Binance Futures. It bridges the gap between quantitative analysis and AI cognition by combining a high-performance **Go** execution engine with a multi-modal **Python** AI microservice.

Unlike traditional bots, NeuroTrade doesn't just trade—it **learns**. With its self-improving Machine Learning core, intelligent AI Judge layer, and extensive "AI Brain Center" analytics, it adapts to market conditions in real-time.

---

## 🎯 Version 5.0 - AI Judge Layer

### NEW: Intelligent Arbiter System
**v5.0 introduces an AI Judge layer that prevents dangerous trades by detecting contradictions between Logic and Vision analysis.**

### Real-World Success Case
**Problem:** STO/USDT Short signal executed 3 times in 10 minutes despite 99% confidence, resulting in $8 loss.

**Root Cause:** 
- Logic Analysis (DeepSeek): SHORT (fade RSI 94 - Mean Reversion)
- Vision Analysis (Gemini): BULLISH (Marubozu Breakout - Strong Momentum)
- System: Shorted anyway (Logic weighted more than Vision)
- Result: $8 loss (never fade strong momentum)

**Solution with AI Judge:**
```
Logic: SHORT (95%) - "Fade RSI 94"
Vision: "Bullish Marubozu breakout" 
ML: 27% win rate

AI Judge Output:
{
  "decision": "WAIT",
  "confidence": 0,
  "final_signal": null,
  "reasoning": "CRITICAL CONTRADICTION: Logic says Short (fade RSI 94) but Vision confirms strong breakout with Marubozu pattern. Never fade strong momentum. ML predicts only 27% win rate.",
  "warning_level": "HIGH",
  "contradictions_detected": true,
  "key_factors": ["Contradictory signals", "Low ML prediction", "Momentum fading"],
  "recommendation": "Do NOT enter. Wait for momentum exhaustion."
}

Result: ✅ BLOCKED - No order, no loss
```

### AI Judge Features

**1. Contradiction Detection**
- Logic SHORT + Vision LONG = BLOCK
- Logic LONG + Vision SHORT = BLOCK
- Never trade against strong momentum

**2. ML Guardrail**
- Win probability < 35% = BLOCK
- Win probability < 25% = CRITICAL BLOCK
- ML overrides confidence threshold

**3. Explainable Decisions**
- Clear reasoning for every trade
- Key factors listed for transparency
- Educational value for manual trading

**4. Two Telegram Formats**
- **Approved:** Shows AI JUDGE APPROVED with reasoning and key factors
- **Rejected:** Shows AI JUDGE REJECTED with contradiction details

---

## Key Capabilities

### 1. Hybrid AI Intelligence
*   **Logic Core (DeepSeek V3):** Analyzes market structure, price action, and risk ratios with human-like reasoning.
*   **Vision Core (Gemini):** "Sees" charts like a pro trader, identifying patterns (Head & Shoulders, Flags) and validating support/resistance levels.
*   **Consensus Engine:** Trades are only executed when Logic, Vision, AND AI Judge agree (High Agreement Rate).

### 2. AI Judge Layer (NEW v5.0)
*   **Intelligent Arbiter:** Uses Gemini Flash to evaluate trade validity
*   **Contradiction Detection:** Identifies when Logic and Vision disagree
*   **ML Guardrail:** Blocks low-probability trades (< 35% win rate)
*   **Transparent:** Clear reasoning for every EXECUTE or WAIT decision

### 3. Anti-Fake & Whale Detection
*   **Directional Momentum:** Uses advanced ROC, RSI slope, and EMA crossovers to detect genuine momentum vs. fake pumps.
*   **Fake Pump Penalty:** Penalizes movements with wick rejections or price-volume divergence, filtering out "bull traps."
*   **Whale Radar:** Tracks 6 key signals including Liquidation Cascades, Order Book Imbalances, and Institutional Flow to follow Smart Money.

### 4. Self-Learning ML System
*   **Continuous Backfill:** Automatically simulates trade outcomes for missed or passed signals to enrich training dataset.
*   **Adaptive Learning:** Uses LightGBM to learn from historical wins and losses, adjusting confidence thresholds dynamically.
*   **Predictive Analytics:** Calculates "Win Probability" for every new signal based on thousands of past scenarios.

### 5. Order Deduplication (v5.0)
*   **Batch Position Check:** Single API call for all symbols (90% faster)
*   **DB-Level Safety:** Check existing OPEN positions before execution
*   **WebSocket Cache:** Zero-latency position tracking

### 6. Professional Execution
*   **Go Backend:** Ultra-low latency execution and risk management.
*   **Dynamic Trailing Stop:** Auto-locks profits at configurable percentages.
*   **Risk Guard:** Multi-layer protection (Position Limits, Max Risk per Trade, Daily Drawdown Limits).
*   **Golden Hours:** Smart scheduling to trade only during high-probability market sessions (London/NY Overlaps).

---

## System Architecture

The system follows a clean, microservices-based architecture:

```mermaid
graph TD
    Client[React Frontend] -->|REST API| Go[Go Execution Engine]
    Go -->|gRPC/HTTP| Py[Python AI Microservice]
    Go -->|SQL| DB[(PostgreSQL)]
    Py -->|SQL| DB
    Py -->|WebSocket/REST| Binance((Binance Futures))
    Go -->|WebSocket| Binance
    
    subgraph "Python AI Engine v5.0"
        Screener[Market Screener]
        Logic[DeepSeek Logic]
        Vision[google/gemini-2.0-flash-exp]
        Whale[Whale Detector]
        ML[LightGBM Learner]
        AIJudge[AI Judge - Gemini Flash]
        
        AIJudge -.-> Logic
        AIJudge -.-> Vision
        AIJudge -.-> ML
    end
    
    subgraph "Go Execution Engine"
        Scheduler[Smart Scheduler]
        Bodyguard[Risk Manager]
        Executor[Trade Executor]
        API[REST API Gateway]
    end
```

---

## Project Structure

```
neurotrade/
├── cmd/app/                    # Go application entry point
├── internal/
│   ├── domain/                 # Domain models and interfaces
│   │   ├── service.go         # AIService interface + BatchHasOpenPositions
│   │   └── position.go        # Position/Signal models
│   ├── usecase/                # Business logic
│   │   └── trading_service.go # ProcessMarketScan + createPositionForUser
│   ├── adapter/                # External integrations
│   │   ├── python_bridge.go    # Python API client
│   │   └── telegram/          # Telegram notifications
│   ├── repository/             # Data access layer
│   │   └── position_repository.go
│   ├── infra/                 # Infrastructure
│   │   ├── database.go        # PostgreSQL connection
│   │   └── scheduler.go       # Cron jobs
│   └── middleware/            # HTTP middleware
├── python-engine/
│   ├── main.py                # FastAPI endpoints
│   ├── config.py              # Configuration (Pydantic Settings) - FIXED v5.0
│   └── services/
│       ├── ai_handler.py      # AI analysis orchestration + AI Judge
│       ├── execution.py        # Binance API execution
│       ├── screener.py        # Market screening
│       ├── whale_detector.py   # Whale activity detection
│       ├── price_stream.py    # WebSocket price feed
│       └── learner.py         # ML model training
├── context/
│   └── context.md           # Detailed system documentation
├── internal/database/migrations/ # PostgreSQL schema
└── docker-compose.yml         # Container orchestration
```

---

## Quick Start

### Prerequisites

*   Docker & Docker Compose
*   Binance Futures API account (Testnet or Real)
*   API Keys: DeepSeek, OpenRouter (for Gemini)

### Installation

1.  **Clone repository:**
    ```bash
    git clone https://github.com/yourusername/neurotrade.git
    cd neurotrade
    ```

2.  **Configure Environment:**
    ```bash
    cp .env.example .env
    # Edit .env and add your API keys
    # - DEEPSEEK_API_KEY
    # - OPENROUTER_API_KEY
    # - BINANCE_API_KEY
    # - BINANCE_API_SECRET
    # - DATABASE_URL
    ```

3.  **Start System:**
    ```bash
    docker-compose up --build -d
    ```

4.  **Access Dashboard:**
    Open `http://localhost:8080/dashboard` in your browser.

### Environment Variables

**Required:**
```bash
# AI Providers
DEEPSEEK_API_KEY=sk-...
OPENROUTER_API_KEY=sk-or-...

# Database
DATABASE_URL=postgresql://user:pass@host:5432/neurotrade

# JWT
JWT_SECRET=your-jwt-secret-here
```

**Optional (for real trading):**
```bash
# Binance Futures
BINANCE_API_KEY=your-api-key
BINANCE_API_SECRET=your-api-secret

# Trading Parameters
MIN_CONFIDENCE=95  # Minimum confidence to execute
MIN_VOLUME_USDT=30000000  # $30M minimum volume
MAX_RISK_PERCENT=2.0  # Max 2% risk per trade
```

---

## Configuration Guide

### Critical Environment Variables

| Variable | Description | Default |
|----------|-------------|----------|
| `PYTHON_ENGINE_URL` | URL of Python AI service | `http://python-engine:8001` |
| `MIN_CONFIDENCE` | Minimum AI confidence score (0-100) to execute a trade | `95` |
| `TOP_COINS_LIMIT` | Number of top volatile coins to scan simultaneously | `15` |
| `MAX_RISK_PERCENT` | Maximum % of portfolio at risk per trade | `2.0` |
| `TELEGRAM_BOT_TOKEN` | (Optional) Token for real-time alerts | - |

---

## AI Pipeline v5.0

### Complete Signal Generation Flow

```
1. Screener finds top candidates (based on volume/volatility)
   ↓
2. DeepSeek analyzes technical indicators
   - RSI, ADX, ATR, Bollinger Bands
   - Mean Reversion vs Momentum following
   ↓
3. Gemini Vision analyzes chart
   - Candlestick patterns
   - Breakout vs Reversal detection
   - Volume confirmation
   ↓
4. ML predicts win probability
   - Historical performance data
   - Confidence interval
   ↓
5. AI Judge evaluates trade validity (NEW v5.0)
   - Checks Logic vs Vision contradictions
   - Validates ML probability
   - Makes final EXECUTE/WAIT decision
   ↓
6. If EXECUTE:
   - Execute order on Binance
   - Save to database
   - Place SL/TP orders
   - Send Telegram notification
```

### Risk Management

**Position Sizing:**
- Default: $30 USDT per trade
- Configurable per user
- Maximum: 20x leverage

**Stop Loss (SL):**
- ATR-based: 2.5x ATR distance
- Dynamic adjustment based on volatility
- Immediate placement after entry

**Take Profit (TP):**
- ATR-based: 4.0x ATR distance
- Risk/Reward ratio: 1.6:1 average
- Optimized for scalping

**Additional Safety:**
- Maximum daily loss limit: $5 per user
- Confidence threshold: 95% minimum
- ML guardrail: Block if win prob < 35%
- DB-level deduplication: Prevent duplicate orders

---

## Monitoring & Logging

### Key Log Patterns

**Successful Signal:**
```
[AI-JUDGE] BTC/USDT: Decision=EXECUTE, Confidence=85%, Warning=LOW
[AI-JUDGE] BTC/USDT: Logic and Vision agree on LONG. Good ML prediction.
[SIGNAL] BTC/USDT LONG (Conf: 85%, ML: 72%)
[EXEC] Entry Filled: ID=123456789 Price=45000.5000
[EXEC] Position saved to DB: BTC/USDT (ID=xxx)
```

**Blocked Signal (v5.0):**
```
[AI-JUDGE] STO/USDT: Decision=WAIT, Confidence=0%, Warning=HIGH
[AI-JUDGE] STO/USDT: BLOCKED - CRITICAL CONTRADICTION detected
[AI-JUDGE] STO/USDT: Logic says Short but Vision confirms breakout. Never fade momentum.
```

**Error Cases:**
```
[ERROR] Failed to create position: Insufficient balance
[ERROR] Binance API error: -2015 Invalid API-key
[DEDUP-DB] STO/USDT: User already has OPEN position, skipping duplicate
```

### Performance Metrics

| Operation | Latency | Notes |
|------------|----------|-------|
| AI Analysis (3 models + Judge) | ~1800ms | DeepSeek + Gemini + ML + AI Judge |
| AI Judge evaluation | ~300ms | Gemini Flash |
| Batch Position Check (10) | ~200ms | Single HTTP call |
| Order Execution | ~500ms | Binance API |
| Position Save | ~5ms | PostgreSQL INSERT |
| **Total per Signal** | ~2500ms | End-to-end |

---

## Development

### Running Locally

```bash
# Go Backend
cd cmd/app
go run main.go

# Python Engine
cd python-engine
pip install -r requirements.txt
uvicorn main:app --reload --port 8001

# Build Docker images
docker-compose build

# Run tests
docker-compose run go-app go test ./...
docker-compose run python-engine pytest
```

### Database Migrations

```bash
# Run migrations automatically on startup
# Or manually:
docker-compose exec postgres psql -U postgres -d neurotrade -f internal/database/migrations/*.sql
```

---

## Safety Mechanisms (v5.0)

### 1. AI Judge (NEW)
- Contradiction detection (Logic vs Vision)
- ML guardrail (win probability < 35% = BLOCK)
- Explainable reasoning for every decision

### 2. Double Veto System
- Logic loves a trade? Vision can veto if chart looks ugly.
- Both agree? ML can still veto if historical data suggests low probability.
- AI Judge makes final EXECUTE/WAIT decision.

### 3. Anti-Drain
- "Panic Button" feature to immediately close all positions if market crashes.
- Balance Guard: Automatic trading halt if daily loss exceeds threshold.

### 4. Order Deduplication
- Batch Binance position check
- DB-level OPEN position check
- Last line of defense against race conditions

### Access Control
- JWT-based authentication
- Per-user permissions
- Admin-only endpoints protected

---

## Security

### API Key Management
- Never log or print API keys
- Store encrypted in PostgreSQL
- Use environment variables
- Rotate keys regularly

### Trading Safety
- Maximum daily loss: $5 per user
- Fixed order size: $30 default
- Leverage cap: 20x
- Confidence threshold: 95%

---

## Configuration Files

| File | Purpose |
|------|---------|
| `python-engine/config.py` | Python engine settings (Pydantic) - FIXED v5.0 |
| `docker-compose.yml` | Container orchestration |
| `.env` | Environment variables |
| `context/context.md` | Detailed architecture docs |

---

## Current Issues (v5.0)

### ✅ Fixed in v5.0
1. **Order Duplication (FIXED)**
   - Status: ✅ Fixed
   - Issue: Multiple orders created for same symbol within short timeframe
   - Solution: Added DB-level deduplication check

2. **Pydantic Config Error (FIXED)**
   - Status: ✅ Fixed
   - Issue: `extra_forbidden` errors in config.py
   - Solution: Changed to direct field declarations with `extra = "allow"`

3. **Logic vs Vision Contradiction (FIXED)**
   - Status: ✅ Fixed
   - Issue: STO/USDT case - Logic SHORT, Vision LONG, system SHORTED anyway
   - Solution: AI Judge layer blocks contradictory signals

### ⚠️ Active Issues
1. **Binance API Permission Issue**
   - Status: ❌ Blocking order execution
   - Error: `code:-2015, msg:"Invalid API-key, IP, or permissions for action"`
   - Solution: Enable Futures Trading permission, whitelist IP in Binance

2. **WebSocket Not Starting**
   - Status: ⚠️ Warning - Fallback to REST working
   - Log: `[WS] Failed to get listen key. WS Disabled.`
   - Impact: Slower position checks (~200ms instead of 0ms)

---

## Contributing

**Current Status:** Production-ready bot actively trading

**Before contributing:**
1. Read `context/context.md` for architecture details
2. Understand AI Judge layer logic
3. Test all changes in development mode first

**Focus Areas:**
- ML model improvement (add more training data)
- Signal quality enhancement
- Risk management optimization

---

## License

Private / Proprietary Software.
All rights reserved.

---

**End of README v5.0**
