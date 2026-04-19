CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE TYPE asset_type_enum AS ENUM (
    'OBLIGATION', 'OPCVM', 'ACTION', 'IMMOBILIER',
    'MATIERE_PREMIERE', 'DERIVE', 'INFRASTRUCTURE', 'PRIVATE_EQUITY'
);
CREATE TYPE asset_status_enum AS ENUM (
    'EN_EMISSION', 'ACTIF', 'TRANSFERE', 'GELE', 'EN_LITIGE',
    'REGLE', 'EXPIRE', 'RACHETE', 'ANNULE'
);
CREATE TYPE kyc_status_enum AS ENUM (
    'NON_INITIE', 'EN_COURS', 'APPROUVE', 'REJETE', 'EXPIRE', 'SUSPENDU'
);
CREATE TYPE risk_category_enum AS ENUM (
    'TRES_FAIBLE', 'FAIBLE', 'MODERE', 'ELEVE', 'CRITIQUE'
);
CREATE TYPE user_role_enum AS ENUM (
    'SUPER_ADMIN', 'ADMIN_ORG', 'EMETTEUR', 'CUSTODIAN',
    'TRADER', 'REGULATEUR', 'AUDITEUR', 'COMPLIANCE_OFFICER', 'READONLY'
);
CREATE TYPE transaction_type_enum AS ENUM (
    'TOKENISATION', 'TRANSFERT', 'GEL', 'DEGEL', 'RACHAT',
    'COUPON_PAIEMENT', 'MISE_A_JOUR_VALEUR', 'ANNULATION', 'REGLEMENT'
);
CREATE TYPE org_type_enum AS ENUM (
    'BANQUE_CENTRALE', 'BANQUE_COMMERCIALE', 'FONDS_INVESTISSEMENT',
    'CUSTODIAN', 'REGULATEUR', 'BROKER_DEALER', 'ASSURANCE', 'FINTECH'
);
CREATE TABLE organizations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_code            VARCHAR(20)  UNIQUE NOT NULL,
    legal_name          VARCHAR(255) NOT NULL,
    short_name          VARCHAR(100) NOT NULL,
    org_type            org_type_enum NOT NULL,
    lei                 CHAR(20)     UNIQUE NOT NULL,
    bic_swift           VARCHAR(11),
    msp_id              VARCHAR(100) UNIQUE NOT NULL,
    country_code        CHAR(2)      NOT NULL,
    jurisdiction        VARCHAR(100) NOT NULL,
    regulator_ref       VARCHAR(50),
    aml_risk_rating     risk_category_enum DEFAULT 'FAIBLE',
    is_active           BOOLEAN      DEFAULT TRUE,
    onboarded_at        TIMESTAMPTZ  NOT NULL,
    last_audit_date     DATE,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);
CREATE TABLE users (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    org_id              UUID NOT NULL REFERENCES organizations(id),
    email               VARCHAR(255) UNIQUE NOT NULL,
    hashed_password     VARCHAR(255) NOT NULL,
    first_name          VARCHAR(100) NOT NULL,
    last_name           VARCHAR(100) NOT NULL,
    role                user_role_enum NOT NULL,
    msp_id              VARCHAR(100) NOT NULL,
    fabric_cert_serial  VARCHAR(128),
    phone               VARCHAR(20),
    department          VARCHAR(100),
    employee_id         VARCHAR(50),
    is_active           BOOLEAN      DEFAULT TRUE,
    mfa_enabled         BOOLEAN      DEFAULT FALSE,
    failed_login_count  INT          DEFAULT 0,
    locked_until        TIMESTAMPTZ,
    last_login          TIMESTAMPTZ,
    password_changed_at TIMESTAMPTZ  DEFAULT NOW(),
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);
CREATE TABLE assets (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id            VARCHAR(50)  UNIQUE NOT NULL,
    isin                VARCHAR(12)  UNIQUE,
    figi                VARCHAR(12),
    cusip               VARCHAR(9),
    sedol               VARCHAR(7),
    asset_type          asset_type_enum NOT NULL,
    asset_name          VARCHAR(255) NOT NULL,
    issuer_org_id       UUID         NOT NULL REFERENCES organizations(id),
    current_owner_id    UUID         REFERENCES users(id),
    nominal_value       NUMERIC(20,4) NOT NULL,
    current_value       NUMERIC(20,4),
    currency            CHAR(3)      NOT NULL DEFAULT 'EUR',
    status              asset_status_enum DEFAULT 'EN_EMISSION',
    issuance_date       DATE         NOT NULL,
    maturity_date       DATE,
    coupon_rate         NUMERIC(6,4),
    coupon_frequency    VARCHAR(20),
    rating_moodys       VARCHAR(10),
    rating_sp           VARCHAR(10),
    rating_fitch        VARCHAR(10),
    underlying_asset    TEXT,
    prospectus_hash     VARCHAR(128),
    fabric_tx_id        VARCHAR(128),
    fabric_block_number BIGINT,
    last_valuation_date DATE,
    total_transfers     INT          DEFAULT 0,
    is_fractionalized   BOOLEAN      DEFAULT FALSE,
    fraction_count      INT,
    metadata            JSONB        DEFAULT '{}',
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);
CREATE TABLE transactions (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tx_ref              VARCHAR(50)  UNIQUE NOT NULL,
    fabric_tx_id        VARCHAR(128) UNIQUE NOT NULL,
    fabric_block_number BIGINT       NOT NULL,
    fabric_channel      VARCHAR(100) NOT NULL DEFAULT 'rwa-channel',
    chaincode_name      VARCHAR(100) NOT NULL DEFAULT 'rwa-token',
    tx_type             transaction_type_enum NOT NULL,
    asset_id            UUID         NOT NULL REFERENCES assets(id),
    initiator_id        UUID         NOT NULL REFERENCES users(id),
    from_owner_id       UUID         REFERENCES users(id),
    to_owner_id         UUID         REFERENCES users(id),
    amount              NUMERIC(20,4),
    price               NUMERIC(20,4),
    currency            CHAR(3)      DEFAULT 'EUR',
    exchange_rate       NUMERIC(12,6),
    settlement_date     DATE,
    clearing_ref        VARCHAR(100),
    endorsing_orgs      TEXT[],
    endorsement_count   INT,
    justification       TEXT,
    regulatory_flag     BOOLEAN      DEFAULT FALSE,
    sar_generated       BOOLEAN      DEFAULT FALSE,
    status              VARCHAR(30)  DEFAULT 'CONFIRME',
    processing_time_ms  INT,
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);
CREATE TABLE compliance_records (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    participant_id      UUID         NOT NULL REFERENCES users(id),
    kyc_status          kyc_status_enum DEFAULT 'NON_INITIE',
    kyc_level           INT          DEFAULT 1,
    aml_score           NUMERIC(5,4) DEFAULT 0,
    risk_category       risk_category_enum DEFAULT 'FAIBLE',
    sanctions_screened  BOOLEAN      DEFAULT FALSE,
    sanctions_hit       BOOLEAN      DEFAULT FALSE,
    pep_status          BOOLEAN      DEFAULT FALSE,
    adverse_media       BOOLEAN      DEFAULT FALSE,
    sar_count           INT          DEFAULT 0,
    check_provider      VARCHAR(100),
    check_reference     VARCHAR(128),
    documents_verified  TEXT[],
    checked_by          UUID         REFERENCES users(id),
    approved_by         UUID         REFERENCES users(id),
    check_date          TIMESTAMPTZ  DEFAULT NOW(),
    expires_at          TIMESTAMPTZ  NOT NULL,
    notes               TEXT,
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    updated_at          TIMESTAMPTZ  DEFAULT NOW()
);
CREATE TABLE sar_reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sar_ref             VARCHAR(50)  UNIQUE NOT NULL,
    transaction_id      UUID         REFERENCES transactions(id),
    reported_user_id    UUID         NOT NULL REFERENCES users(id),
    reporting_officer   UUID         NOT NULL REFERENCES users(id),
    reason_code         VARCHAR(20)  NOT NULL,
    reason_description  TEXT         NOT NULL,
    amount_involved     NUMERIC(20,4),
    currency            CHAR(3),
    submitted_to        VARCHAR(100) NOT NULL,
    submission_date     TIMESTAMPTZ,
    acknowledgement_ref VARCHAR(128),
    is_tipping_off_risk BOOLEAN      DEFAULT FALSE,
    status              VARCHAR(30)  DEFAULT 'DRAFT',
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);
CREATE TABLE audit_logs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id            UUID         DEFAULT uuid_generate_v4(),
    user_id             UUID         REFERENCES users(id),
    org_id              UUID         REFERENCES organizations(id),
    endpoint            VARCHAR(200) NOT NULL,
    http_method         VARCHAR(10)  NOT NULL,
    ip_address          INET         NOT NULL,
    request_body        JSONB,
    response_code       SMALLINT     NOT NULL,
    fabric_tx_id        VARCHAR(128),
    duration_ms         INT,
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);
CREATE TABLE asset_valuations (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    asset_id            UUID         NOT NULL REFERENCES assets(id),
    valuation_date      DATE         NOT NULL,
    nav                 NUMERIC(20,6) NOT NULL,
    nav_currency        CHAR(3)      NOT NULL DEFAULT 'EUR',
    yield_to_maturity   NUMERIC(8,6),
    duration            NUMERIC(8,4),
    convexity           NUMERIC(10,6),
    credit_spread_bps   NUMERIC(8,2),
    valuation_method    VARCHAR(50),
    pricing_source      VARCHAR(100),
    validated_by        UUID         REFERENCES users(id),
    created_at          TIMESTAMPTZ  DEFAULT NOW(),
    UNIQUE(asset_id, valuation_date)
);
CREATE TABLE kyc_documents (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id             UUID         NOT NULL REFERENCES users(id),
    document_type       VARCHAR(50)  NOT NULL,
    document_number     VARCHAR(100),
    issuing_country     CHAR(2),
    issued_date         DATE,
    expiry_date         DATE,
    file_hash           VARCHAR(128) NOT NULL,
    verified            BOOLEAN      DEFAULT FALSE,
    verified_by         UUID         REFERENCES users(id),
    verified_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);
CREATE TABLE network_events (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_name          VARCHAR(100) NOT NULL,
    chaincode_name      VARCHAR(100) NOT NULL,
    fabric_tx_id        VARCHAR(128) NOT NULL,
    fabric_block_number BIGINT       NOT NULL,
    payload             JSONB        NOT NULL,
    processed           BOOLEAN      DEFAULT FALSE,
    processed_at        TIMESTAMPTZ,
    error_count         INT          DEFAULT 0,
    created_at          TIMESTAMPTZ  DEFAULT NOW()
);
CREATE INDEX idx_assets_status         ON assets(status);
CREATE INDEX idx_assets_type           ON assets(asset_type);
CREATE INDEX idx_assets_issuer         ON assets(issuer_org_id);
CREATE INDEX idx_assets_isin           ON assets(isin);
CREATE INDEX idx_transactions_asset    ON transactions(asset_id);
CREATE INDEX idx_transactions_type     ON transactions(tx_type);
CREATE INDEX idx_transactions_date     ON transactions(created_at DESC);
CREATE INDEX idx_transactions_fabric   ON transactions(fabric_tx_id);
CREATE INDEX idx_compliance_user       ON compliance_records(participant_id);
CREATE INDEX idx_compliance_status     ON compliance_records(kyc_status);
CREATE INDEX idx_audit_logs_user       ON audit_logs(user_id);
CREATE INDEX idx_audit_logs_date       ON audit_logs(created_at DESC);
CREATE INDEX idx_valuations_asset_date ON asset_valuations(asset_id, valuation_date DESC);
CREATE INDEX idx_users_org             ON users(org_id);
CREATE INDEX idx_users_email           ON users(email);
