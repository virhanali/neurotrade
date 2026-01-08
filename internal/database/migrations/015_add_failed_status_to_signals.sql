-- Migration: 015_add_failed_status_to_signals.sql
-- Description: Update signals status constraint to include 'FAILED'

-- Drop existing constraint
ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_status_check;

-- Add new constraint with 'FAILED' status
ALTER TABLE signals ADD CONSTRAINT signals_status_check 
CHECK (status IN ('PENDING', 'EXECUTED', 'REJECTED', 'FAILED'));
