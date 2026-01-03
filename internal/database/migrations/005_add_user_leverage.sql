-- Add leverage column to users table
ALTER TABLE users ADD COLUMN leverage DECIMAL(5, 2) DEFAULT 20.0;
