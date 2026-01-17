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
    DEEPSEEK_API_KEY: str
    OPENROUTER_API_KEY: str
    
    # Exchange API (Optional - only for real trading)
    BINANCE_API_KEY: str = ""
    BINANCE_API_SECRET: str = ""
    BINANCE_WS_URL: str = "wss://fstream.binance.com/ws/!ticker@arr"
    
    # Database
    DATABASE_URL: str = ""
    
    # Application
    PYTHON_ENV: str = "development"
    LOG_LEVEL: str = "info"
    
    # Trading Parameters
    MIN_VOLUME_USDT: float = 30000000.0  # $30M minimum volume (Lowered to catch Mid-Caps)
    MIN_VOLATILITY_1H: float = 0.8  # 0.5% min vol
    TOP_COINS_LIMIT: int = 15  # Top 15 is Sweet Spot (Cost vs Opportunity)
    MAX_RISK_PERCENT: float = 2.0  # Max 2% risk per trade
    MIN_CONFIDENCE: int = 75  # Minimum 75% confidence to execute
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"  # Allow extra fields


# Global settings instance
settings = Settings()

