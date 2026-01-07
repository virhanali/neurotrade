-- Add Binance API Key and Secret columns to users table
ALTER TABLE users ADD COLUMN binance_api_key VARCHAR(255);
ALTER TABLE users ADD COLUMN binance_api_secret VARCHAR(255);
