-- Migration: 006_add_ai_learning_logs.sql
CREATE TABLE IF NOT EXISTS ai_learning_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,
    outcome VARCHAR(10) NOT NULL CHECK (outcome IN ('WIN', 'LOSS')),
    pnl DECIMAL(18, 2),
    
    -- Quant Metrics Snapshot
    adx DECIMAL(10, 2),
    vol_z_score DECIMAL(10, 2),
    ker DECIMAL(10, 4), -- Kaufman Efficiency Ratio
    is_squeeze BOOLEAN,
    score DECIMAL(10, 2), -- Screener Score
    
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ai_learning_symbol ON ai_learning_logs(symbol);
CREATE INDEX IF NOT EXISTS idx_ai_learning_outcome ON ai_learning_logs(outcome);
CREATE INDEX IF NOT EXISTS idx_ai_learning_timestamp ON ai_learning_logs(timestamp DESC);
