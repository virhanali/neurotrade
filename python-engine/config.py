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
    MIN_VOLATILITY_1H: float = 0.8  # 0.8% min vol
    TOP_COINS_LIMIT: int = 15  # Top 15 is Sweet Spot (Cost vs Opportunity)
    MAX_RISK_PERCENT: float = 10.0  # 10% per trade (optimized for small accounts $50-200)
    MIN_CONFIDENCE: int = 75  # Minimum 75% confidence to execute
    
    # v6.0: Adaptive ML Thresholds per Market Regime
    ML_THRESHOLD_RANGING: int = 25  # Lower threshold for ranging scalping
    ML_THRESHOLD_TRENDING: int = 35  # Standard threshold for trending
    ML_THRESHOLD_EXPLOSIVE: int = 45  # Strict threshold to avoid FOMO
    
    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "allow"  # Allow extra fields


# Global settings instance
settings = Settings()

