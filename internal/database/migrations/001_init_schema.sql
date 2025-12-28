-- NeuroTrade AI Database Schema
-- Migration: 001_init_schema.sql

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ===========================================
-- USERS TABLE
-- ===========================================
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(10) NOT NULL DEFAULT 'USER' CHECK (role IN ('ADMIN', 'USER')),
    mode VARCHAR(10) NOT NULL DEFAULT 'PAPER' CHECK (mode IN ('REAL', 'PAPER')),
    paper_balance DECIMAL(18, 2) DEFAULT 1000.00,
    real_balance_cache DECIMAL(18, 2),
    max_daily_loss DECIMAL(5, 2) DEFAULT 5.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_username ON users(username);

-- ===========================================
-- STRATEGY PRESETS TABLE (Admin Configuration)
-- ===========================================
CREATE TABLE strategy_presets (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    system_prompt TEXT NOT NULL,
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_strategy_presets_active ON strategy_presets(is_active);

-- ===========================================
-- SIGNALS TABLE (History & Review)
-- ===========================================
CREATE TABLE signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    type VARCHAR(10) NOT NULL CHECK (type IN ('LONG', 'SHORT')),
    entry_price DECIMAL(18, 8) NOT NULL,
    sl_price DECIMAL(18, 8) NOT NULL,
    tp_price DECIMAL(18, 8) NOT NULL,
    confidence INT NOT NULL CHECK (confidence >= 0 AND confidence <= 100),
    reasoning TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING', 'EXECUTED', 'REJECTED')),
    review_result VARCHAR(20) CHECK (review_result IN ('WIN', 'LOSS', 'FLOATING')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_signals_symbol ON signals(symbol);
CREATE INDEX idx_signals_status ON signals(status);
CREATE INDEX idx_signals_created_at ON signals(created_at DESC);

-- ===========================================
-- PAPER POSITIONS TABLE (Virtual Trading)
-- ===========================================
CREATE TABLE paper_positions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL CHECK (side IN ('LONG', 'SHORT')),
    entry_price DECIMAL(18, 8) NOT NULL,
    size_usdt DECIMAL(18, 2) NOT NULL,
    sl_price DECIMAL(18, 8) NOT NULL,
    tp_price DECIMAL(18, 8) NOT NULL,
    status VARCHAR(10) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN', 'CLOSED')),
    pnl DECIMAL(18, 2),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX idx_paper_positions_user_id ON paper_positions(user_id);
CREATE INDEX idx_paper_positions_status ON paper_positions(status);
CREATE INDEX idx_paper_positions_symbol ON paper_positions(symbol);

-- ===========================================
-- SEED DATA: Default Strategy Presets
-- ===========================================
INSERT INTO strategy_presets (name, system_prompt, is_active) VALUES
(
    'Aggressive Scalping',
    'You are an aggressive crypto scalping AI. Focus on high-frequency trades with tight stop losses. Target 0.5-1% profits per trade. Prioritize momentum and volume breakouts.',
    false
),
(
    'Conservative Swing',
    'You are a conservative swing trading AI. Focus on longer timeframes (4H-1D). Look for clear trend reversals and support/resistance levels. Target 3-5% profits with wider stop losses.',
    true
),
(
    'Balanced Momentum',
    'You are a balanced momentum trading AI. Combine technical indicators (RSI, MACD, EMA) with price action analysis. Moderate risk-reward ratio of 1:2.',
    false
);

-- ===========================================
-- FUNCTIONS: Auto-update timestamps
-- ===========================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_strategy_presets_updated_at
    BEFORE UPDATE ON strategy_presets
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
