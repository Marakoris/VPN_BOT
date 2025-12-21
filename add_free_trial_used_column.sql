-- Migration: Add free_trial_used column to users table
-- Date: 2025-12-19
-- Purpose: Track if user has already used the free trial period

-- Add the column with default value false
ALTER TABLE users
ADD COLUMN IF NOT EXISTS free_trial_used BOOLEAN DEFAULT false;

-- Add comment for documentation
COMMENT ON COLUMN users.free_trial_used IS 'Indicates if user has already used the 3-day free trial';

-- Update existing users: set free_trial_used to false (default)
-- This ensures all existing users can use the free trial once
UPDATE users
SET free_trial_used = false
WHERE free_trial_used IS NULL;
