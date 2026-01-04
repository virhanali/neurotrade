-- Add new columns to paper_positions table for better tracking
-- closed_by: How the position was closed (TP, SL, TRAILING, MANUAL)
-- leverage: Leverage used for this position
-- pnl_percent: PnL as percentage (matches Binance display)

ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS closed_by VARCHAR(20);
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS leverage DECIMAL(10, 2) DEFAULT 20.0;
ALTER TABLE paper_positions ADD COLUMN IF NOT EXISTS pnl_percent DECIMAL(10, 4);

-- Add index for closed_by for analytics
CREATE INDEX IF NOT EXISTS idx_paper_positions_closed_by ON paper_positions(closed_by);

COMMENT ON COLUMN paper_positions.closed_by IS 'How position was closed: TP, SL, TRAILING, MANUAL';
COMMENT ON COLUMN paper_positions.leverage IS 'Leverage used for this position';
COMMENT ON COLUMN paper_positions.pnl_percent IS 'PnL as percentage (with leverage effect)';
