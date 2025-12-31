-- Add Auto-Trade flag to users table
ALTER TABLE users ADD COLUMN is_auto_trade_enabled BOOLEAN DEFAULT FALSE;

-- Update paper_positions status check constraint to include new statuses
ALTER TABLE paper_positions DROP CONSTRAINT IF EXISTS paper_positions_status_check;

ALTER TABLE paper_positions ADD CONSTRAINT paper_positions_status_check 
    CHECK (status IN ('OPEN', 'CLOSED', 'CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL', 'PENDING_APPROVAL', 'REJECTED'));
