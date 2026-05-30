-- ZKP (Zero-Knowledge Proof) tables for decentralised zk-KYC
-- Credential: issued server-side, stored client-side only (never persisted here)
-- Nullifiers: stored server-side to prevent proof replay

CREATE TABLE IF NOT EXISTS zkp_credentials (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id       UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    public_key_x  TEXT NOT NULL,          -- secp256k1 public key X hex
    public_key_y  TEXT NOT NULL,          -- secp256k1 public key Y hex
    age_ok        BOOLEAN NOT NULL DEFAULT FALSE,
    kyc_ok        BOOLEAN NOT NULL DEFAULT FALSE,
    not_sanctioned BOOLEAN NOT NULL DEFAULT FALSE,
    kyc_level     INTEGER NOT NULL DEFAULT 0,
    issuer_sig    TEXT NOT NULL,           -- ECDSA signature (hex) over claim JSON
    issued_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL,
    revoked       BOOLEAN NOT NULL DEFAULT FALSE,
    revoked_at    TIMESTAMPTZ,
    revoked_reason TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_zkp_credentials_user_pubkey
    ON zkp_credentials (user_id, public_key_x);

CREATE INDEX IF NOT EXISTS ix_zkp_credentials_user ON zkp_credentials (user_id);
CREATE INDEX IF NOT EXISTS ix_zkp_credentials_expires ON zkp_credentials (expires_at);

-- Nullifiers: one-time proof tokens that prevent replay attacks
CREATE TABLE IF NOT EXISTS zkp_nullifiers (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    nullifier_hex TEXT NOT NULL UNIQUE,   -- SHA-256(user_secret || purpose)
    purpose       TEXT NOT NULL,          -- e.g. "asset_transfer", "kyc_gate"
    public_key_x  TEXT NOT NULL,          -- links to credential without revealing user_id
    used_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_zkp_nullifiers_nullifier ON zkp_nullifiers (nullifier_hex);
CREATE INDEX IF NOT EXISTS ix_zkp_nullifiers_used_at   ON zkp_nullifiers (used_at);

-- Platform ZKP key pair (one row only — rotated manually)
CREATE TABLE IF NOT EXISTS zkp_platform_keys (
    id            SERIAL PRIMARY KEY,
    public_key_x  TEXT NOT NULL,
    public_key_y  TEXT NOT NULL,
    -- private key is stored in Vault, NOT here
    active        BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
