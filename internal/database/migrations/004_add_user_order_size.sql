-- Add fixed_order_size to users table
ALTER TABLE users ADD COLUMN fixed_order_size DECIMAL(20, 8) DEFAULT 1.0;
