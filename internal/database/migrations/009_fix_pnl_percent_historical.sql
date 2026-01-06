-- Migration 009: Fix historical PnL percentages (Binance-style)
-- Formula: PnL % = (PnL / Initial Margin) × 100
-- Where Initial Margin = (Size × Entry Price) / Leverage
-- Run this once to correct historical data

-- Fix all closed positions with Binance-style PnL percentage
UPDATE paper_positions 
SET pnl_percent = CASE 
    WHEN (size * entry_price / COALESCE(NULLIF(leverage, 0), 20)) > 0 THEN
        (COALESCE(pnl, 0) / (size * entry_price / COALESCE(NULLIF(leverage, 0), 20))) * 100
    ELSE 0
END
WHERE status IN ('CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL')
AND exit_price IS NOT NULL
AND size > 0
AND entry_price > 0;

-- Also fix status based on actual PnL
UPDATE paper_positions
SET status = 'CLOSED_WIN'
WHERE status = 'CLOSED_LOSS'
AND COALESCE(pnl, 0) > 0;

UPDATE paper_positions
SET status = 'CLOSED_LOSS'
WHERE status = 'CLOSED_WIN'
AND COALESCE(pnl, 0) < 0;

-- Verify
SELECT 
    symbol,
    side,
    entry_price,
    exit_price,
    size,
    leverage,
    pnl,
    pnl_percent,
    status
FROM paper_positions
WHERE status IN ('CLOSED_WIN', 'CLOSED_LOSS', 'CLOSED_MANUAL')
ORDER BY closed_at DESC
LIMIT 10;
