-- Add whale metrics to ai_learning_logs for correlation analysis
ALTER TABLE ai_learning_logs 
ADD COLUMN IF NOT EXISTS funding_rate DECIMAL(10, 8),
ADD COLUMN IF NOT EXISTS ls_ratio DECIMAL(10, 4),
ADD COLUMN IF NOT EXISTS whale_score DECIMAL(5, 2);
