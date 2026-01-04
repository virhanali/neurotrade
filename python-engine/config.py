"""
NeuroTrade AI - Configuration Module
Loads environment variables and application settings
"""

import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""

    # AI Provider APIs (Required)
    DEEPSEEK_API_KEY: str = os.getenv("DEEPSEEK_API_KEY", "")  # Logic analysis
    OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "")  # Vision analysis

    # Exchange API (Optional - only for real trading)
    BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")
    BINANCE_WS_URL: str = os.getenv("BINANCE_WS_URL", "wss://fstream.binance.com/ws/!ticker@arr")

    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "")

    # Application
    PYTHON_ENV: str = os.getenv("PYTHON_ENV", "development")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info")

    MIN_VOLUME_USDT: float = float(os.getenv("MIN_VOLUME_USDT", "30000000"))  # $30M minimum volume (Lowered to catch Mid-Caps)
    MIN_VOLATILITY_1H: float = float(os.getenv("MIN_VOLATILITY_1H", "0.5"))  # 0.5% min vol
    TOP_COINS_LIMIT: int = int(os.getenv("TOP_COINS_LIMIT", "15"))  # Top 15 is the Sweet Spot (Cost vs Opportunity)
    MAX_RISK_PERCENT: float = float(os.getenv("MAX_RISK_PERCENT", "2.0"))  # Max 2% risk per trade
    MIN_CONFIDENCE: int = int(os.getenv("MIN_CONFIDENCE", "75"))  # Minimum 75% confidence to execute

    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
