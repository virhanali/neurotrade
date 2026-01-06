-- Migration: 011_fix_ml_threshold_column.sql
-- Purpose: Fix ml_threshold column type from DECIMAL(5,4) to INT
-- The original DECIMAL(5,4) only supports values -9.9999 to 9.9999
-- but ml_threshold stores values 0-100

-- Check if table exists before altering
DO $$ 
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.columns 
               WHERE table_name = 'ai_analysis_cache' 
               AND column_name = 'ml_threshold') THEN
        -- Alter the column type from DECIMAL to INT
        ALTER TABLE ai_analysis_cache 
        ALTER COLUMN ml_threshold TYPE INT 
        USING COALESCE(ml_threshold::numeric::int, 0);
        
        RAISE NOTICE 'Column ml_threshold altered to INT successfully';
    END IF;
END $$;
