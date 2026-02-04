-- Migration: Add subscription_expired column to users table
-- Date: 2025-12-19
-- Purpose: Separate subscription expiration status from banned status
--          This implements proper architecture where:
--          - banned = true for REAL bans (spam, violations, admin action)
--          - subscription_expired = true for expired subscriptions (soft limit)

-- Add the column with default value false
ALTER TABLE users
ADD COLUMN IF NOT EXISTS subscription_expired BOOLEAN DEFAULT false;

-- Add comment for documentation
COMMENT ON COLUMN users.subscription_expired IS 'Indicates if user subscription has expired (soft limit, not a ban)';

-- Update existing users based on their current subscription status
-- If subscription timestamp is in the past, mark as expired
UPDATE users
SET subscription_expired = CASE
    WHEN subscription < EXTRACT(EPOCH FROM NOW()) THEN true
    ELSE false
END
WHERE subscription_expired IS NULL OR subscription_expired = false;

-- Note: After this migration, check_and_proceed_subscriptions.py must be updated
-- to use subscription_expired instead of banned for expired subscriptions
