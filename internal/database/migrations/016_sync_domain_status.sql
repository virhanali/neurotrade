-- Migration: 016_sync_domain_status.sql
-- Description: Sync all status constraints with domain constants
-- Align signals and positions tables with actual Go domain status values

-- ===========================================
-- UPDATE SIGNALS STATUS CONSTRAINT
-- ===========================================
-- Drop existing constraint
ALTER TABLE signals DROP CONSTRAINT IF EXISTS signals_status_check;

-- Add comprehensive constraint matching domain/signals.go
-- Status: PENDING, EXECUTED, FAILED, REJECTED
ALTER TABLE signals ADD CONSTRAINT signals_status_check 
CHECK (status IN ('PENDING', 'EXECUTED', 'FAILED', 'REJECTED'));

-- ===========================================
-- UPDATE POSITIONS STATUS CONSTRAINT
-- ===========================================
-- Drop existing constraint if it exists
ALTER TABLE positions DROP CONSTRAINT IF EXISTS positions_status_check;

-- Add comprehensive constraint matching domain/position.go
-- Status: OPEN, CLOSED_WIN, CLOSED_LOSS, CLOSED_MANUAL, PENDING_APPROVAL, REJECTED
ALTER TABLE positions ADD CONSTRAINT positions_status_check 
CHECK (status IN ('OPEN', 'CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL', 'PENDING_APPROVAL', 'REJECTED'));


-- ===========================================
-- ADD MISSING COLUMNS TO POSITIONS
-- ===========================================
-- Add closed_by column (how position was closed)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS closed_by VARCHAR(20)
CHECK (closed_by IN ('TP', 'SL', 'TRAILING', 'MANUAL'));

-- Add pnl_percent column (PnL percentage with leverage)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS pnl_percent DECIMAL(10,2);

-- Add leverage column (Leverage used for position)
ALTER TABLE positions ADD COLUMN IF NOT EXISTS leverage DECIMAL(10,2) DEFAULT 20.0;

-- Add signal_id reference to positions
ALTER TABLE positions ADD COLUMN IF NOT EXISTS signal_id UUID REFERENCES signals(id) ON DELETE SET NULL;

-- ===========================================
-- UPDATE EXISTING ROWS
-- ===========================================
-- Set default values for existing positions
UPDATE positions SET closed_by = 'MANUAL' WHERE closed_by IS NULL;
UPDATE positions SET leverage = 20.0 WHERE leverage IS NULL OR leverage = 0;

-- ===========================================
-- PERFORMANCE INDEXES
-- ===========================================
-- Index for faster active position lookups
CREATE INDEX IF NOT EXISTS idx_positions_symbol_status
ON positions(symbol, status)
WHERE status IN ('OPEN', 'PENDING_APPROVAL');

-- Index for faster signal dedup lookups
CREATE INDEX IF NOT EXISTS idx_signals_symbol_status_created
ON signals(symbol, status, created_at DESC);

-- Index for signal_id in positions
CREATE INDEX IF NOT EXISTS idx_positions_signal_id
ON positions(signal_id);

-- Index for positions by user
CREATE INDEX IF NOT EXISTS idx_positions_user_status
ON positions(user_id, status)
WHERE status IN ('OPEN', 'PENDING_APPROVAL');
