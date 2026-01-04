# 🧠 NeuroTrade AI v4.2

> **Production-Grade Hybrid AI Trading Bot for Binance Futures**

NeuroTrade is an intelligent trading system combining a high-performance Go backend for execution with a Python microservice for multi-layer AI analysis. Features self-learning ML, whale detection, and contrarian indicators.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🤖 **Hybrid AI Intelligence** | DeepSeek V3 (Logic) + Qwen3 VL 235B (Vision) |
| 🐋 **Whale Detection (6 Signals)** | Liquidations, Order Book, Funding Rate, L/S Ratio |
| 🧠 **Self-Learning ML** | LightGBM model learns from every trade |
| 📊 **Quant Metrics** | ADX, KER, Volume Z-Score, Bollinger Squeeze |
| ⚡ **15-Second Scan Cycles** | Ultra-aggressive opportunity capture |
| 📈 **Dynamic Trailing Stop** | Auto-locks profits at configurable % |
| 🛡️ **Multi-Layer Protection** | Vision Veto + ML Veto + Risk Cap |
| 📱 **Telegram Notifications** | Real-time alerts for signals and results |
| 🕐 **Golden Hours Filter** | Only trades during optimal market sessions |

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           BINANCE                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐  │
│  │   REST API   │  │  WebSocket   │  │   Futures Data Feed       │  │
│  └──────────────┘  └──────────────┘  └───────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    PYTHON ENGINE (FastAPI)                           │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    PRO SCREENER (12 Threads)                  │   │
│  │  • Multi-Timeframe Analysis (M15 + 4H)                       │   │
│  │  • Volume Anomaly Detection (Z-Score)                        │   │
│  │  • Trend Quality (ADX, KER)                                  │   │
│  │  • Bollinger Squeeze Detection                               │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                │                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐     │
│  │ 🐋 WHALE     │  │ 🤖 AI LOGIC  │  │ 👁️ AI VISION          │     │
│  │ DETECTOR     │  │ DeepSeek V3  │  │ Qwen3 VL 235B         │     │
│  │              │  │              │  │                        │     │
│  │ • Liquidation│  │ • Trend      │  │ • Chart Patterns      │     │
│  │ • Order Book │  │ • Momentum   │  │ • Support/Resistance  │     │
│  │ • Funding    │  │ • Risk Calc  │  │ • Candlestick Signals │     │
│  │ • L/S Ratio  │  │ • Entry/SL/TP│  │ • Visual Confirmation │     │
│  └──────────────┘  └──────────────┘  └────────────────────────┘     │
│                                │                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    🧠 ML LEARNER (LightGBM)                   │   │
│  │  • Records every trade outcome                                │   │
│  │  • Learns ADX/KER/Z-Score → Win Rate correlation             │   │
│  │  • Provides adaptive confidence boost/veto                    │   │
│  │  • Needs 50+ trades to activate                              │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        GO BACKEND (Executor)                         │
│                                                                      │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐     │
│  │ SCHEDULER    │  │TRADING SVC   │  │ BODYGUARD              │     │
│  │ (15 sec)     │  │(3-Layer Def) │  │ (10s loop)             │     │
│  │              │  │              │  │                        │     │
│  │ • Golden Hrs │  │ • Dedup      │  │ • SL/TP Monitor        │     │
│  │ • Cron Jobs  │  │ • Position   │  │ • Trailing Stop        │     │
│  │              │  │ • Balance    │  │ • Auto-close           │     │
│  └──────────────┘  └──────────────┘  └────────────────────────┘     │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PostgreSQL  │  Dashboard (HTMX)  │  Telegram Bot                    │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🐋 Whale Detection System

NeuroTrade includes a sophisticated whale detection system with **6 data sources**:

| Signal | Source | Interpretation |
|--------|--------|----------------|
| **Liquidation Stream** | WebSocket | Longs/Shorts getting rekt → price direction |
| **Order Book Imbalance** | REST API | Buy/sell wall detection |
| **Large Trades** | Recent trades | Smart money flow analysis |
| **Open Interest** | Futures API | Position building/unwinding |
| **Funding Rate** | Futures API | Contrarian indicator (high = bearish) |
| **Long/Short Ratio** | Futures API | Crowd positioning (fade the crowd) |

### Whale Signal Types:
- `PUMP_IMMINENT` → Strong buy setup
- `DUMP_IMMINENT` → Strong sell setup
- `SQUEEZE_LONGS` → Longs getting liquidated
- `SQUEEZE_SHORTS` → Shorts getting squeezed
- `NEUTRAL` → No significant activity

---

## 🧠 Machine Learning System

### How ML Works:

```
1. RECORD: Every closed trade saves metrics to ai_learning_logs
   ├── ADX (trend strength)
   ├── Volume Z-Score (anomaly detection)
   ├── KER (trend efficiency)
   ├── is_squeeze (Bollinger squeeze)
   ├── Screener Score (0-100)
   └── Outcome (WIN/LOSS)

2. TRAIN: After 50+ trades, LightGBM model trains on patterns
   └── Learns: "ADX > 25 + KER > 0.6 → 70% WIN"

3. PREDICT: For new signals, ML provides:
   ├── Win probability (0-100%)
   ├── Confidence boost/reduction
   └── Veto power (rejects low-probability trades)
```

### ML Features Used:

| Feature | Type | Description |
|---------|------|-------------|
| `adx` | Float | Average Directional Index (trend strength) |
| `vol_z_score` | Float | Volume standard deviations from mean |
| `ker` | Float | Kaufman Efficiency Ratio (0-1) |
| `is_squeeze` | Boolean | Bollinger Bands squeeze (accumulation) |
| `score` | Float | Combined screener score |

### ML Activation Status:

| Trades | Status | Behavior |
|--------|--------|----------|
| 0-49 | ⏳ Learning | Fallback to base confidence |
| 50-99 | 🔄 Training | Basic pattern recognition |
| 100-199 | 📈 Improving | Good predictions |
| 200+ | 🧠 Optimized | Full adaptive intelligence |

---

## 🖥️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Go 1.21+, Echo Framework |
| **AI Service** | Python 3.11, FastAPI, Uvicorn |
| **AI Models** | DeepSeek V3 (Logic), Qwen3 VL 235B (Vision) |
| **ML** | LightGBM, scikit-learn |
| **Database** | PostgreSQL 15 |
| **Frontend** | HTML5, TailwindCSS, HTMX, Chart.js |
| **Infrastructure** | Docker, Docker Compose |
| **Real-time** | WebSocket (Binance Futures) |

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- PostgreSQL database
- API Keys: DeepSeek, OpenRouter
- Telegram Bot Token (optional)

### Installation

```bash
# 1. Clone repository
git clone https://github.com/yourusername/neurotrade.git
cd neurotrade

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Run database migrations
psql -U your_user -d your_db -f internal/database/migrations/*.sql

# 4. Start services
docker-compose up --build -d

# 5. Access dashboard
open http://localhost:8080/dashboard
```

---

## ⚙️ Configuration

### Key Environment Variables

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/neurotrade

# AI Services
DEEPSEEK_API_KEY=your_deepseek_key
OPENROUTER_API_KEY=your_openrouter_key

# Trading Parameters
TOP_COINS_LIMIT=15              # Coins to analyze per scan
MIN_VOLUME_USDT=30000000        # Minimum 24h volume ($30M)
MIN_VOLATILITY_1H=0.8           # Minimum 1H change (%)
MIN_CONFIDENCE=75               # Minimum AI confidence (0-100)

# User Settings (in database)
fixed_order_size=5              # USDT per trade
leverage=20                     # Leverage multiplier

# Trailing Stop
TRAILING_ACTIVATE_PCT=1.0       # Activate at 1% profit
TRAILING_DISTANCE_PCT=0.5       # Trail 0.5% behind price

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

---

## 📊 Database Schema

### Key Tables:

| Table | Purpose |
|-------|---------|
| `users` | User settings, balance, leverage |
| `signals` | AI-generated trading signals |
| `paper_positions` | Active and closed positions |
| `ai_learning_logs` | ML training data (ADX, KER, etc.) |

### Paper Position Fields:

| Field | Description |
|-------|-------------|
| `entry_price` | Entry price |
| `sl_price` | Stop loss (dynamic with trailing) |
| `tp_price` | Take profit |
| `exit_price` | Actual exit price |
| `pnl` | Profit/Loss in USD |
| `pnl_percent` | P/L as percentage |
| `closed_by` | TP, SL, TRAILING, or MANUAL |
| `leverage` | Leverage used |

---

## 🛡️ Safety Features

### 1. Multi-Layer Signal Defense
- **Mutex Lock**: Prevents overlapping scans
- **Batch Dedup**: No duplicate signals per batch
- **Active Position Check**: One position per coin

### 2. AI Validation
- **JSON Response Validation**: Prevents AI hallucinations
- **Vision Veto**: Charts can reject logic signals
- **ML Veto**: Low-probability trades rejected

### 3. Risk Management
- **Dynamic Trailing Stop**: Locks profits automatically
- **SL/TP Enforcement**: Bodyguard monitors 24/7
- **Status Correction**: Based on actual PnL, not trigger

### 4. Golden Hours Filter
Only trades during optimal sessions (UTC):
- Asia: 00:00-04:00
- London: 07:00-11:00
- New York: 13:00-18:00

---

## 📈 Performance Tracking

### Position Tracking Fields:
- `closed_by`: How position was closed (TP/SL/TRAILING/MANUAL)
- `pnl_percent`: Percentage gain/loss
- `leverage`: Leverage used for this trade

### Example Stats:
```
Total Trades: 28
Win Rate: 42.9%
Total PnL: +$50.01
Profit Factor: 4.06x
Avg Win: +$6.25
Avg Loss: -$1.54
```

---

## 📁 Project Structure

```
neurotrade/
├── cmd/app/                    # Go application entrypoint
├── internal/
│   ├── delivery/http/          # HTTP handlers & routes
│   ├── domain/                 # Domain models & interfaces
│   ├── repository/             # Database repositories
│   ├── service/                # Bodyguard, Review, VirtualBroker
│   ├── usecase/                # Trading service (core logic)
│   └── infra/                  # Scheduler, Telegram
├── python-engine/
│   ├── services/
│   │   ├── screener.py         # PRO Screener (parallel MTF)
│   │   ├── ai_handler.py       # DeepSeek + Qwen Vision
│   │   ├── whale_detector.py   # 6-Signal Whale Detection
│   │   ├── learner.py          # ML Training & Prediction
│   │   ├── data_fetcher.py     # OHLCV data fetching
│   │   └── price_stream.py     # WebSocket price stream
│   ├── main.py                 # FastAPI application
│   └── config.py               # Settings
├── web/templates/              # Dashboard HTML templates
├── docker-compose.yml
└── README.md
```

---

## 🔧 Operational Commands

```bash
# Start system
docker-compose up --build -d

# View logs
docker logs -f neurotrade-python
docker logs -f neurotrade-go

# Check ML status
curl http://localhost:5000/ml/stats

# Manual scan trigger
curl -X POST http://localhost:8080/admin/scan-now

# Full rebuild
docker-compose down && docker-compose up --build -d
```

---

## 📝 Changelog

### v4.3 (2026-01-05) - UI/UX Revolution
- 🎨 Dashboard overhaul (Path-based routing, Aesthetic Tables)
- 🧠 Brain Health Dashboard with dynamic ML charts
- 🐋 Whale Radar visualization in Dashboard
- 📊 Detailed Trade History & Live Positions view
- ⚡ Optimized Query Performance (IN clause)
- 🚀 Removed manual triggers (100% Automated)

### v4.2 (2026-01-05) - ML & Whale Edition
- 🐋 Whale Detection with 6 signals (Funding, L/S Ratio)
- 🧠 Self-Learning ML (LightGBM)
- 👁️ Vision upgrade to Qwen3 VL 235B
- 📊 Position tracking (closed_by, pnl_percent)
- 🔧 Status fix based on actual PnL

### v4.1 - Quant Metrics Edition
- 📈 ADX, KER, Volume Z-Score, Bollinger Squeeze
- ⚡ Parallel screening (12 threads)
- 🎯 Context-aware AI prompts

### v3.x - Hybrid AI Foundation
- 🤖 Dual AI (Logic + Vision)
- 🛡️ Bodyguard with Trailing Stop
- 📱 Telegram Notifications
- 🖥️ Dashboard with HTMX

---

## 🎯 System Rating

| Component | Rating |
|-----------|--------|
| DeepSeek V3 Logic | 8/10 |
| Qwen3 VL Vision | 8/10 |
| Whale Detection | 8.5/10 |
| Quant Metrics | 8/10 |
| ML Self-Learning | 5/10 → 8/10 (after training) |
| Risk Management | 8/10 |
| **Overall System** | **8/10** |

---

## 📄 License

Private / Proprietary.

---

## 🙏 Acknowledgments

- [DeepSeek](https://deepseek.com) - Logic AI
- [Qwen](https://qwenlm.github.io) - Vision AI
- [LightGBM](https://lightgbm.readthedocs.io) - ML Framework
- [CCXT](https://github.com/ccxt/ccxt) - Exchange connectivity
- [Echo](https://echo.labstack.com) - Go web framework
- [FastAPI](https://fastapi.tiangolo.com) - Python API framework

---

*"Intelligence is the ability to adapt to change."* - Stephen Hawking 🧠
