-- Migration: 013_add_time_columns_to_logs.sql
-- Purpose: Add hour_of_day and day_of_week columns to ai_learning_logs for ML training

DO $$ 
BEGIN
    -- Add hour_of_day column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'ai_learning_logs' 
                   AND column_name = 'hour_of_day') THEN
        ALTER TABLE ai_learning_logs ADD COLUMN hour_of_day INT;
        -- Backfill from timestamp
        UPDATE ai_learning_logs SET hour_of_day = EXTRACT(HOUR FROM timestamp);
        RAISE NOTICE 'Added hour_of_day column';
    END IF;

    -- Add day_of_week column
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                   WHERE table_name = 'ai_learning_logs' 
                   AND column_name = 'day_of_week') THEN
        ALTER TABLE ai_learning_logs ADD COLUMN day_of_week INT;
        -- Backfill from timestamp (0=Sunday in EXTRACT, but Python uses 0=Monday)
        -- PostgreSQL DOW: 0=Sunday, 1=Monday... But we'll use raw value
        UPDATE ai_learning_logs SET day_of_week = EXTRACT(DOW FROM timestamp)::INT;
        RAISE NOTICE 'Added day_of_week column';
    END IF;
END $$;

COMMENT ON COLUMN ai_learning_logs.hour_of_day IS 'Hour of day (0-23) when trade was recorded';
COMMENT ON COLUMN ai_learning_logs.day_of_week IS 'Day of week (0=Sunday, 6=Saturday) when trade was recorded';
