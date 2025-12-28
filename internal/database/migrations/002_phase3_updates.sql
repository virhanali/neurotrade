-- NeuroTrade AI Database Schema
-- Migration: 002_phase3_updates.sql
-- Phase 3: Paper Trading & Auto-Review Engine Updates

-- ===========================================
-- UPDATE SIGNALS TABLE
-- ===========================================
-- Add review_pnl column to track floating PnL percentage
ALTER TABLE signals
ADD COLUMN IF NOT EXISTS review_pnl DECIMAL(10, 2);

-- ===========================================
-- UPDATE PAPER_POSITIONS TABLE
-- ===========================================
-- Add signal_id to link position to signal
ALTER TABLE paper_positions
ADD COLUMN IF NOT EXISTS signal_id UUID REFERENCES signals(id) ON DELETE SET NULL;

-- Rename size_usdt to size (base asset size)
ALTER TABLE paper_positions
RENAME COLUMN size_usdt TO size;

-- Add exit_price column
ALTER TABLE paper_positions
ADD COLUMN IF NOT EXISTS exit_price DECIMAL(18, 8);

-- Increase status column length to support CLOSED_WIN and CLOSED_LOSS
ALTER TABLE paper_positions
ALTER COLUMN status TYPE VARCHAR(20);

-- Update status column to support CLOSED_WIN and CLOSED_LOSS
ALTER TABLE paper_positions
DROP CONSTRAINT IF EXISTS paper_positions_status_check;

ALTER TABLE paper_positions
ADD CONSTRAINT paper_positions_status_check
CHECK (status IN ('OPEN', 'CLOSED_WIN', 'CLOSED_LOSS'));

-- Add index on signal_id
CREATE INDEX IF NOT EXISTS idx_paper_positions_signal_id ON paper_positions(signal_id);

COMMENT ON COLUMN signals.review_pnl IS 'Floating PnL percentage for signal review';
COMMENT ON COLUMN paper_positions.signal_id IS 'Reference to the signal that created this position';
COMMENT ON COLUMN paper_positions.size IS 'Position size in base asset (BTC, ETH, etc.)';
COMMENT ON COLUMN paper_positions.exit_price IS 'Exit price when position is closed';
