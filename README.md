# NeuroTrade AI v2.0

NeuroTrade is a hybrid high-frequency trading system designed for aggressive scalping on Binance Futures. It combines a high-performance Go backend for execution safety with a Python microservice for AI-driven technical analysis.

## Architecture

The system utilizes a microservices architecture bridged by REST APIs and WebSockets.

### 1. Python Engine (The Brain)
*   **Role**: Stateless inference server for AI analysis and real-time data streaming.
*   **Core Components**:
    *   **Price Streamer**: Connects to Binance WebSocket (`!ticker@arr`) for sub-second price updates.
    *   **Volatility Screener**: Filters top 5 volatile assets using RSI and Volume metrics locally before AI processing.
    *   **Vision Analyst (Gemini 2.0 Flash Lite)**: Analyzes generated chart images for candlestick patterns (Engulfing, Pinbars) and market structure.
    *   **Logic Analyst (DeepSeek V3)**: Reasons through market trends and liquidity concepts to confirm trade validity.

### 2. Go Backend (The Executor)
*   **Role**: State management, order execution, and money management.
*   **Core Components**:
    *   **Trading Service**: Orchestrates the signal lifecycle. Implements a 3-layer protection system (Mutex Lock, Batch Deduplication, Active Position Check) to prevent race conditions and duplicate orders.
    *   **Bodyguard Service**: A defensive background worker running every 10 seconds. It monitors active positions against real-time prices (fetched from Python Engine) to execute Stop Loss or Take Profit orders immediately.
    *   **User Repository**: Manages per-user trading configurations such as leverage and margin size.

## Key Features

*   **Hybrid Intelligence**: Combines LLM reasoning (DeepSeek) with Multimodal Vision (Gemini) for high-confidence signals.
*   **Aggressive Scalping**: Optimized for M15 timeframes with a 2-minute scan interval.
*   **Database-Driven Configuration**: Trading parameters (Leverage, Order Size, Max Loss) are configurable per user via the database, allowing for flexible risk management.
*   **Real-time Dashboard**: A Neobrutalism-styled admin dashboard built with Go Templates and HTMX, featuring live PnL estimation and manual overrides.
*   **Paper Trading**: Fully simulated execution engine that mimics Binance Futures mechanics, including leverage simulation.

## Tech Stack

*   **Backend**: Go (Golang) 1.21+
*   **AI Service**: Python 3.11, FastAPI
*   **Database**: PostgreSQL 15
*   **Frontend**: HTML5, TailwindCSS, HTMX
*   **Infrastructure**: Docker, Docker Compose

## Configuration

Required environment variables in `.env`:

```bash
# Database Connection
DATABASE_URL=postgresql://user:pass@host:5432/db

# AI Service Configuration
DEEPSEEK_API_KEY=your_deepseek_key
OPENROUTER_API_KEY=your_openrouter_key
GEMINI_MODEL=google/gemini-2.0-flash-lite-001

# Trading Parameters (System Defaults)
# Note: User-specific settings in the database take precedence.
TZ=Asia/Jakarta

# Telegram Notification
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Installation

1.  Clone the repository.
2.  Copy `.env.example` to `.env` and fill in the required keys.
3.  Start the services using Docker Compose:

```bash
docker-compose up --build -d
```

4.  Access the dashboard at `http://localhost:8080`.

## License

Private / Proprietary.
