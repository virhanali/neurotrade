-- Migration: 012_fix_ai_analysis_cache.sql
-- Purpose: 
-- 1. Add missing columns (funding_rate, ls_ratio, whale_score)
-- 2. Add unique constraint for ON CONFLICT to work

-- Add missing columns if they don't exist
DO $$ 
BEGIN
    -- Add funding_rate column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'ai_analysis_cache' 
                   AND column_name = 'funding_rate') THEN
        ALTER TABLE ai_analysis_cache ADD COLUMN funding_rate DECIMAL(10, 6);
        RAISE NOTICE 'Added funding_rate column';
    END IF;

    -- Add ls_ratio column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'ai_analysis_cache' 
                   AND column_name = 'ls_ratio') THEN
        ALTER TABLE ai_analysis_cache ADD COLUMN ls_ratio DECIMAL(10, 4);
        RAISE NOTICE 'Added ls_ratio column';
    END IF;

    -- Add whale_score column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'ai_analysis_cache' 
                   AND column_name = 'whale_score') THEN
        ALTER TABLE ai_analysis_cache ADD COLUMN whale_score INT;
        RAISE NOTICE 'Added whale_score column';
    END IF;
END $$;

-- Add unique constraint on (symbol, created_at) for ON CONFLICT to work
-- First check if it already exists
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'uq_ai_cache_symbol_created_at'
    ) THEN
        ALTER TABLE ai_analysis_cache 
        ADD CONSTRAINT uq_ai_cache_symbol_created_at 
        UNIQUE (symbol, created_at);
        RAISE NOTICE 'Added unique constraint on (symbol, created_at)';
    END IF;
END $$;

COMMENT ON COLUMN ai_analysis_cache.funding_rate IS 'Funding rate at time of analysis';
COMMENT ON COLUMN ai_analysis_cache.ls_ratio IS 'Long/Short ratio at time of analysis';
COMMENT ON COLUMN ai_analysis_cache.whale_score IS 'Whale detection score 0-100';
