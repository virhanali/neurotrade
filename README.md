# 🧠 NeuroTrade AI v3.1

> **Ultra-Performance Hybrid AI Trading Bot for Binance Futures**

NeuroTrade is a production-grade, high-frequency trading system combining a high-performance Go backend for execution safety with a Python microservice for AI-driven technical analysis. Optimized for aggressive scalping with institutional-grade signal filtering.

---

## ✨ Key Features

| Feature | Description |
|---------|-------------|
| 🤖 **Hybrid AI Intelligence** | Combines DeepSeek V3 (Logic Reasoning) + Gemini 2.0 Flash Lite (Vision Pattern Recognition) |
| ⚡ **15-Second Scan Cycles** | Ultra-aggressive opportunity capture with Mutex protection against overlaps |
| 🔍 **PRO Screener** | Multi-Timeframe (15m + 4H) analysis with Volume Anomaly & Trend Alignment filters |
| 🚀 **Parallel Processing** | 12-thread OHLCV fetching - scans 60 coins in ~2-3 seconds |
| 💤 **BTC Sleep Check** | Saves AI costs by skipping scans when market is flat (< 0.2% BTC move) |
| 🛡️ **3-Layer Protection** | Mutex Lock + Batch Deduplication + Active Position Check |
| 📈 **Dynamic Trailing Stop** | Locks in profits by trailing SL at 0.5% when profit > 1.0% |
| 📊 **Real-time Dashboard** | Live PnL analytics, signal filtering, and one-click Panic Button |
| 📱 **Telegram Notifications** | Instant alerts for new signals and trade results |
| 🔄 **Paper Trading** | Full simulation engine mimicking Binance Futures mechanics |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         EXTERNAL                                 │
│  ┌─────────────┐    ┌─────────────────────────────────────────┐ │
│  │   Binance   │───▶│  WebSocket (!ticker@arr) + REST API     │ │
│  └─────────────┘    └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    PYTHON ENGINE (6 Workers)                     │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Price Stream │  │ BTC Gatekeeper│  │ PRO Screener (12 Thr) │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Chart Gen    │  │ DeepSeek V3  │  │ Gemini 2.0 Flash Lite │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      GO BACKEND (Executor)                       │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────┐ │
│  │ Scheduler    │  │Trading Svc   │  │ Bodyguard (10s loop)   │ │
│  │ (15 sec)     │  │(3-Layer Def) │  │ (SL/TP + Trailing)     │ │
│  └──────────────┘  └──────────────┘  └────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  PostgreSQL │ Dashboard (HTMX) │ Telegram Bot                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🖥️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Go 1.21+, Echo Framework |
| **AI Service** | Python 3.11, FastAPI, Uvicorn (6 workers) |
| **AI Models** | DeepSeek V3 (Logic), Gemini 2.0 Flash Lite (Vision) |
| **Database** | PostgreSQL 15 |
| **Frontend** | HTML5, TailwindCSS, HTMX, Chart.js |
| **Infrastructure** | Docker, Docker Compose, Coolify |
| **Real-time** | WebSocket (Binance !ticker@arr) |

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- PostgreSQL database
- API Keys: DeepSeek, OpenRouter (for Gemini)
- Telegram Bot Token (optional)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/yourusername/neurotrade.git
cd neurotrade
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your API keys and database URL
```

3. **Start services**
```bash
docker-compose up --build -d
```

4. **Access dashboard**
```
http://localhost:8080/dashboard
```

---

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# Database
DATABASE_URL=postgresql://user:pass@host:5432/neurotrade

# AI Services
DEEPSEEK_API_KEY=your_deepseek_key
OPENROUTER_API_KEY=your_openrouter_key

# Screener Settings
TOP_COINS_LIMIT=15              # Coins to analyze (recommended: 10-15)
MIN_VOLUME_USDT=50000000        # Minimum 24h volume ($50M)
MIN_VOLATILITY_1H=1.5           # Minimum 1H change (%)
MIN_CONFIDENCE=75               # Minimum AI confidence to execute

# Telegram Notifications
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id

# Timezone
TZ=Asia/Jakarta
```

---

## 📊 Performance Metrics

| Metric | Value |
|--------|-------|
| **Scan Frequency** | Every 15 seconds |
| **Scan Duration** | ~2-3 seconds (60 coins) |
| **Parallel Threads** | 12 (Screener) |
| **Uvicorn Workers** | 6 |
| **Binance API Usage** | ~480 req/min (limit: 1200) |
| **AI Cost (Quiet)** | ~$0/day |
| **AI Cost (Active)** | ~$5-15/day |

---

## 📁 Project Structure

```
neurotrade/
├── cmd/app/                    # Go application entrypoint
├── internal/
│   ├── delivery/http/          # HTTP handlers & routes
│   ├── domain/                 # Domain models & interfaces
│   ├── repository/             # Database repositories
│   ├── service/                # Bodyguard, Review services
│   ├── usecase/                # Trading service (core logic)
│   └── infra/                  # Scheduler, Telegram
├── python-engine/
│   ├── services/
│   │   ├── screener.py         # PRO Screener (parallel MTF)
│   │   ├── ai_handler.py       # DeepSeek + Gemini integration
│   │   ├── data_fetcher.py     # OHLCV data fetching
│   │   ├── charter.py          # Chart generation
│   │   └── price_stream.py     # WebSocket price stream
│   ├── main.py                 # FastAPI application
│   └── config.py               # Settings
├── web/templates/              # Dashboard HTML templates
├── docker-compose.yml
└── README.md
```

---

## 🛡️ Safety Features

1. **3-Layer Signal Defense**
   - Mutex Lock: Prevents overlapping scans
   - Batch Deduplication: No duplicate signals per batch
   - Active Position Check: One position per coin

2. **Trailing Stop**
   - Activates at 1.0% profit
   - Trails at 0.5% distance
   - Locks in profits during pumps

3. **Panic Button**
   - One-click liquidation of all positions
   - Accessible from dashboard

4. **BTC Sleep Check**
   - Skips analysis when market is flat
   - Saves 100% AI cost during dead markets

---

## 📈 Dashboard Features

- **Stats Cards**: Balance, Positions, Win Rate, Total PnL
- **AI Signals List**: Sorted (Running first), Filterable (All/Running/Wins/Losses)
- **Performance Chart**: Cumulative PnL over time
- **Manual Controls**: Scan Now, Approve/Decline, Panic Button
- **Real-time Updates**: Auto-refresh via HTMX every 10s

---

## 🔧 Operational Commands

```bash
# Start system
docker-compose up --build -d

# View logs
docker logs -f <container_id>

# Check resource usage
docker stats

# Restart after config change
docker-compose restart

# Full rebuild
docker-compose down && docker-compose up --build -d
```

---

## 📝 Changelog

### v3.1 (2026-01-04) - Ultra Performance Edition
- ⚡ Parallel OHLCV fetching (12 threads)
- 🚀 15-second scan cycles
- 🔧 Optimized for 16-core / 32GB VPS
- 🛠️ Signal status synchronization fix
- 📊 Performance analytics chart
- 🎯 Context-aware AI prompts

### v3.0 - PRO Screener Edition
- 🔍 Multi-Timeframe Analysis (15m + 4H)
- 📈 Volume Anomaly Detection
- 📉 EMA 200 Trend Alignment
- 🎯 Confluence Scoring

### v2.x - Foundation
- 🤖 Hybrid AI (DeepSeek + Gemini)
- 🛡️ Bodyguard with Trailing Stop
- 📱 Telegram Notifications
- 🖥️ Dashboard with HTMX

---

## 📄 License

Private / Proprietary.

---

## 🙏 Acknowledgments

- [DeepSeek](https://deepseek.com) - Logic AI
- [Google Gemini](https://ai.google.dev) - Vision AI
- [CCXT](https://github.com/ccxt/ccxt) - Exchange connectivity
- [Echo](https://echo.labstack.com) - Go web framework
- [FastAPI](https://fastapi.tiangolo.com) - Python API framework

---

*"Code is law, but risk management is king."* 👑
