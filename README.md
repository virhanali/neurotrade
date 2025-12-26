# NeuroTrade

An AI-powered cryptocurrency trading system that combines deep learning analysis with technical indicators to generate automated trading signals. This is a Minimum Viable Product (MVP) currently in active development.

## Overview

NeuroTrade is a hybrid AI trading system that analyzes cryptocurrency markets using dual AI models: DeepSeek R1 for logical market analysis and Google Gemini 2.0 Flash for visual chart pattern recognition. The system automatically scans markets, generates trading signals, and manages positions through a paper trading environment.

## Current Status: MVP

This project is in MVP stage with core functionality implemented and tested. The system is production-ready for paper trading but requires additional testing and refinement before live trading deployment.

## Architecture

The system follows clean architecture principles with clear separation of concerns:

**Backend Services:**
- Go application (Chi/Echo framework) - Core trading logic, API endpoints, signal management
- Python AI engine (FastAPI) - Market analysis, AI inference, technical indicators
- PostgreSQL - Persistent data storage for signals, positions, and user data
- Redis - Caching and session management

**AI Components:**
- DeepSeek R1 - Logical market analysis using technical indicators (RSI, MACD, EMA, Bollinger Bands)
- Google Gemini 2.0 Flash - Visual chart pattern recognition and confirmation
- Hybrid decision system - Combines both AI outputs with confidence scoring

**Infrastructure:**
- Docker containerization for all services
- Nginx reverse proxy with SSL support
- Automated deployment scripts
- Health monitoring and logging

## Key Features

### Market Analysis
- Automated market scanning with configurable filters (volume, volatility)
- Multi-timeframe analysis (1h and 4h charts)
- Real-time price tracking via Binance API
- Top N coin selection based on trading opportunity scoring

### AI-Powered Signals
- Dual AI analysis for higher accuracy
- Confidence scoring system (0-100%)
- Agreement verification between logic and vision models
- Automatic trade parameter calculation (entry, stop-loss, take-profit)
- Position sizing based on risk management rules

### Paper Trading
- Virtual broker with realistic fee simulation (0.05% maker/taker)
- Automatic position creation from high-confidence signals
- Real-time position monitoring and PnL tracking
- Auto-review system that audits signal performance
- Emergency panic button to close all positions

### User Management
- JWT-based authentication
- Role-based access control (Admin/User)
- Paper/Real trading mode toggle
- Individual user balance tracking

### Notifications
- Telegram integration for signal alerts
- Trade execution notifications
- Performance review reports
- Timezone-aware timestamps

### Web Interface
- Login and authentication
- Real-time dashboard with position updates
- Trading mode switcher
- Admin panel for system configuration
- Strategy preset management

## Technical Stack

**Backend:**
- Go 1.21+ (Golang)
- Python 3.11
- PostgreSQL 15
- Redis 7

**Frameworks:**
- Echo (Go web framework)
- FastAPI (Python API framework)
- HTMX (Frontend interactivity)

**AI/ML:**
- DeepSeek API
- Google Gemini API
- TA-Lib (Technical Analysis Library)
- Pandas, NumPy (Data processing)

**DevOps:**
- Docker & Docker Compose
- Nginx
- Let's Encrypt SSL
- UFW Firewall
- Fail2Ban

## Project Structure

```
neurotrade/
├── cmd/app/                 # Go application entry point
├── internal/
│   ├── domain/             # Business entities
│   ├── repository/         # Data access layer
│   ├── usecase/            # Business logic
│   ├── service/            # Background services
│   ├── delivery/http/      # API handlers
│   ├── adapter/            # External integrations
│   └── middleware/         # Authentication, logging
├── python-engine/          # AI analysis service
│   ├── services/           # Market data, AI handlers
│   ├── main.py            # FastAPI application
│   └── config.py          # Configuration
├── migrations/             # Database schema
├── web/                   # Frontend templates
├── scripts/               # Deployment automation
├── nginx/                 # Reverse proxy config
└── docker-compose.prod.yml # Production orchestration
```

## Configuration

The system is configured entirely through environment variables defined in `.env` file:

**Required Variables:**
- Database credentials (PostgreSQL)
- AI API keys (DeepSeek, Google Gemini)
- Telegram bot credentials
- JWT secret for authentication

**Trading Parameters:**
- MIN_VOLUME_USDT - Minimum 24h trading volume filter
- MIN_VOLATILITY_1H - Minimum hourly price movement
- TOP_COINS_LIMIT - Number of coins to analyze per scan
- MAX_RISK_PERCENT - Maximum risk per trade
- MIN_CONFIDENCE - Minimum AI confidence threshold

See `.env.production.example` for complete configuration reference.

## Deployment

The system includes automated deployment scripts for VPS environments:

**Initial Setup:**
```bash
./scripts/vps-setup.sh      # Install Docker, configure firewall
./scripts/setup-ssl.sh       # Configure SSL certificates
```

**Deployment:**
```bash
./scripts/deploy.sh          # Automated deployment with backup
```

**Manual Deployment:**
```bash
docker-compose -f docker-compose.prod.yml up -d --build
```

See `DEPLOYMENT.md` for detailed deployment instructions.

## API Endpoints

**Authentication:**
- POST /api/auth/login
- POST /api/auth/logout
- POST /api/auth/register

**User Endpoints (Protected):**
- GET /api/user/me
- GET /api/user/positions
- POST /api/user/mode/toggle
- POST /api/user/panic-button

**Admin Endpoints (Admin Only):**
- GET /api/admin/strategies
- PUT /api/admin/strategies/active
- GET /api/admin/system/health
- GET /api/admin/statistics
- POST /api/admin/market-scan/trigger

## Automated Services

**Market Scanner:**
- Runs hourly at minute 59
- Scans top opportunities
- Generates AI signals
- Creates positions automatically

**Virtual Broker:**
- Checks positions every minute
- Monitors stop-loss and take-profit levels
- Executes automatic position closures
- Updates PnL in real-time

**Auto-Review:**
- Runs at minute 5 every hour
- Audits closed positions
- Calculates win/loss statistics
- Sends performance reports

## Development

**Local Development:**
```bash
# Start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Access services
# Go API: http://localhost:8080
# Python Engine: http://localhost:8000
# PostgreSQL: localhost:5432
```

**Default Credentials:**
- Username: default
- Password: password123
- Role: ADMIN
- Balance: $1000 USDT

## Monitoring

**Health Checks:**
- GET /health (both Go and Python services)
- Docker health check integration
- Automatic service restart on failure

**Logs:**
- JSON file logging with rotation
- Container logs via Docker
- Nginx access and error logs

## Security

**Implemented:**
- JWT token authentication
- Bcrypt password hashing
- Role-based access control
- SQL injection prevention (parameterized queries)
- CORS configuration
- Firewall rules (UFW)
- SSH protection (Fail2Ban)
- SSL/TLS encryption

**Production Checklist:**
- Strong database passwords
- Secure JWT secret (32+ characters)
- Valid SSL certificates
- Firewall configured (ports 22, 80, 443 only)
- Regular backups
- API rate limiting (recommended)

## Limitations (MVP)

**Current Limitations:**
- Paper trading only (no live order execution)
- Single exchange support (Binance)
- No backtesting engine
- Basic strategy customization
- Polling-based updates (no WebSockets)
- Limited historical data analysis
- No multi-user portfolio management

**Known Issues:**
- Health check timing during startup
- No refresh token implementation
- Basic error recovery
- Limited mobile responsiveness

## Roadmap

**Planned Improvements:**
- Live trading integration with Binance API
- Backtesting engine with historical data
- WebSocket real-time updates
- Advanced strategy builder
- Multi-exchange support
- Performance analytics dashboard
- Mobile application
- Email notifications
- API rate limiting
- Comprehensive test coverage

## License

This project is proprietary software. All rights reserved.

## Support

For issues, questions, or contributions, please contact the development team.

## Disclaimer

This software is provided for educational and research purposes. Cryptocurrency trading carries significant financial risk. The developers are not responsible for any financial losses incurred through the use of this system. Always conduct thorough testing in paper trading mode before considering live trading. Past performance does not guarantee future results.
