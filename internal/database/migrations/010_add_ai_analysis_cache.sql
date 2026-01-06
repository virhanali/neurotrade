-- Migration: 010_add_ai_analysis_cache.sql
-- Purpose: Store ALL AI analysis results (DeepSeek, Vision, ML prediction)
-- This prevents wasting API credits and enables learning from non-traded signals

CREATE TABLE IF NOT EXISTS ai_analysis_cache (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol VARCHAR(20) NOT NULL,

    -- === DEEPSEEK (LOGIC) RESULTS ===
    logic_signal VARCHAR(10),  -- 'LONG', 'SHORT', 'WAIT'
    logic_confidence INT,     -- 0-100
    logic_reasoning TEXT,      -- DeepSeek reasoning

    -- === VISION (GEMINI) RESULTS ===
    vision_signal VARCHAR(10), -- 'BULLISH', 'BEARISH', 'NEUTRAL'
    vision_confidence INT,     -- 0-100
    vision_reasoning TEXT,      -- Gemini reasoning

    -- === ML PREDICTION RESULTS ===
    ml_win_probability DECIMAL(5, 4), -- 0.0-1.0
    ml_threshold DECIMAL(5, 4),       -- Recommended threshold
    ml_is_trained BOOLEAN,             -- True if model trained, False if rule-based
    ml_insights JSONB,                 -- Array of insight strings

    -- === COMBINED RESULT ===
    final_signal VARCHAR(10),   -- 'LONG', 'SHORT', 'WAIT'
    final_confidence INT,       -- 0-100
    recommendation TEXT,        -- 'EXECUTE', 'SKIP', or reason

    -- === SCREENER METRICS SNAPSHOT ===
    adx DECIMAL(10, 2),
    vol_z_score DECIMAL(10, 2),
    ker DECIMAL(10, 4),
    is_squeeze BOOLEAN,
    screener_score DECIMAL(10, 2),

    -- === WHALE DETECTION ===
    whale_signal VARCHAR(20),   -- 'PUMP_IMMINENT', 'DUMP_IMMINENT', etc
    whale_confidence INT,

    -- === MARKET CONTEXT ===
    btc_trend VARCHAR(10),      -- 'UP', 'DOWN', 'SIDEWAYS'
    hour_of_day INT,            -- 0-23
    day_of_week INT,            -- 0-6 (Monday-Sunday)

    -- === OUTCOME (FOR LEARNING) ===
    -- NULL initially, filled when trade closes
    outcome VARCHAR(10),        -- 'WIN', 'LOSS', or NULL
    pnl DECIMAL(18, 2),        -- Actual PnL if trade executed

    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP

    -- === OPTIMIZATION: INDEXES ===
    -- For quick lookup of analyzed symbols
    -- For ML training queries
    -- For finding non-executed signals for analysis
);

CREATE INDEX IF NOT EXISTS idx_ai_cache_symbol ON ai_analysis_cache(symbol);
CREATE INDEX IF NOT EXISTS idx_ai_cache_timestamp ON ai_analysis_cache(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ai_cache_outcome ON ai_analysis_cache(outcome) WHERE outcome IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_ai_cache_ml_trained ON ai_analysis_cache(ml_is_trained);
CREATE INDEX IF NOT EXISTS idx_ai_cache_final_signal ON ai_analysis_cache(final_signal, final_confidence);

-- Unique constraint: Prevent duplicate analysis for same symbol within 5 minutes
CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_cache_unique_symbol_time
    ON ai_analysis_cache(symbol)
    WHERE created_at > NOW() - INTERVAL '5 minutes';

COMMENT ON TABLE ai_analysis_cache IS 'Cache of ALL AI analysis results for learning and analytics';
COMMENT ON COLUMN ai_analysis_cache.ml_is_trained IS 'TRUE if ML model was trained, FALSE if rule-based fallback was used';
COMMENT ON COLUMN ai_analysis_cache.outcome IS 'Trade outcome (WIN/LOSS) - NULL until trade closes';
