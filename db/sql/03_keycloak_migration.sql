-- Migration 03: Replace password-based auth with Keycloak SSO
-- Run this migration ONCE against the live database BEFORE deploying the new backend.
--
-- Steps performed:
--   1. Add keycloak_sub column (links our user record to the Keycloak identity).
--   2. Drop columns that are no longer managed by the backend:
--        hashed_password, mfa_enabled, mfa_secret,
--        failed_login_count, locked_until, password_changed_at
--
-- IMPORTANT: Existing users will have keycloak_sub = NULL until they log in
-- via SSO for the first time. The backend matches them by email on first login
-- and then sets keycloak_sub automatically.
--
-- Run with: psql $DATABASE_URL -f 03_keycloak_migration.sql

BEGIN;

-- 1. Add Keycloak subject column (nullable — filled on first SSO login)
ALTER TABLE users
  ADD COLUMN IF NOT EXISTS keycloak_sub VARCHAR(255);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_keycloak_sub
  ON users (keycloak_sub)
  WHERE keycloak_sub IS NOT NULL;

-- 2. Drop legacy authentication columns
ALTER TABLE users
  DROP COLUMN IF EXISTS hashed_password,
  DROP COLUMN IF EXISTS mfa_enabled,
  DROP COLUMN IF EXISTS mfa_secret,
  DROP COLUMN IF EXISTS failed_login_count,
  DROP COLUMN IF EXISTS locked_until,
  DROP COLUMN IF EXISTS password_changed_at;

-- 3. Redis key namespace note (informational — no SQL needed):
--    Old keys: blacklist:{token}, token:invalidated:{user_id}
--    New keys: oidc:blacklist:{jti}, oidc:invalidated:{keycloak_sub}
--    Flush the old namespace after deploying:
--      redis-cli -u $REDIS_URL --scan --pattern 'blacklist:*' | xargs redis-cli -u $REDIS_URL DEL
--      redis-cli -u $REDIS_URL --scan --pattern 'token:invalidated:*' | xargs redis-cli -u $REDIS_URL DEL

COMMIT;
