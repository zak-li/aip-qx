CREATE OR REPLACE VIEW v_asset_portfolio AS
SELECT
    a.asset_id,
    a.asset_name,
    a.isin,
    a.asset_type,
    a.status,
    a.nominal_value,
    a.current_value,
    a.currency,
    ROUND(((a.current_value - a.nominal_value) / a.nominal_value) * 100, 4) AS pnl_pct,
    a.coupon_rate,
    a.maturity_date,
    a.rating_moodys,
    a.rating_sp,
    o.short_name       AS issuer_name,
    o.lei              AS issuer_lei,
    CONCAT(u.first_name, ' ', u.last_name) AS current_owner_name,
    a.total_transfers,
    a.fabric_tx_id,
    a.fabric_block_number,
    a.last_valuation_date,
    a.created_at       AS tokenized_at
FROM assets a
JOIN organizations o ON a.issuer_org_id  = o.id
LEFT JOIN users u    ON a.current_owner_id = u.id;
CREATE OR REPLACE VIEW v_transaction_history AS
SELECT
    t.tx_ref,
    t.fabric_tx_id,
    t.fabric_block_number,
    t.tx_type,
    a.asset_id,
    a.isin,
    a.asset_name,
    CONCAT(ui.first_name, ' ', ui.last_name)  AS initiator_name,
    oi.short_name                              AS initiator_org,
    CONCAT(uf.first_name, ' ', uf.last_name)  AS from_owner,
    CONCAT(ut.first_name, ' ', ut.last_name)  AS to_owner,
    t.amount,
    t.price,
    t.currency,
    t.settlement_date,
    t.clearing_ref,
    t.endorsing_orgs,
    t.endorsement_count,
    t.justification,
    t.regulatory_flag,
    t.sar_generated,
    t.status,
    t.processing_time_ms,
    t.created_at
FROM transactions t
JOIN assets a           ON t.asset_id      = a.id
JOIN users ui           ON t.initiator_id  = ui.id
JOIN organizations oi   ON ui.org_id       = oi.id
LEFT JOIN users uf      ON t.from_owner_id = uf.id
LEFT JOIN users ut      ON t.to_owner_id   = ut.id
ORDER BY t.created_at DESC;
CREATE OR REPLACE VIEW v_compliance_dashboard AS
SELECT
    CONCAT(u.first_name, ' ', u.last_name) AS participant_name,
    u.email,
    u.role,
    o.short_name   AS organization,
    o.lei          AS org_lei,
    cr.kyc_status,
    cr.kyc_level,
    cr.aml_score,
    cr.risk_category,
    cr.sanctions_hit,
    cr.pep_status,
    cr.adverse_media,
    cr.sar_count,
    cr.check_provider,
    cr.check_date,
    cr.expires_at,
    CASE
        WHEN cr.expires_at < NOW()                          THEN 'EXPIRE'
        WHEN cr.expires_at < NOW() + INTERVAL '30 days'    THEN 'EXPIRATION_PROCHE'
        ELSE 'VALIDE'
    END AS kyc_validity_status
FROM compliance_records cr
JOIN users u         ON cr.participant_id = u.id
JOIN organizations o ON u.org_id          = o.id;
CREATE OR REPLACE VIEW v_risk_exposure AS
SELECT
    o.short_name     AS organization,
    a.asset_type,
    a.currency,
    COUNT(*)                    AS asset_count,
    SUM(a.nominal_value)        AS total_nominal,
    SUM(a.current_value)        AS total_current,
    ROUND(AVG(a.coupon_rate), 4) AS avg_coupon_rate,
    MIN(a.maturity_date)        AS nearest_maturity,
    MAX(a.maturity_date)        AS furthest_maturity
FROM assets a
JOIN organizations o ON a.issuer_org_id = o.id
WHERE a.status = 'ACTIF'
GROUP BY o.short_name, a.asset_type, a.currency
ORDER BY total_nominal DESC;
CREATE OR REPLACE VIEW v_valuation_latest AS
SELECT DISTINCT ON (av.asset_id)
    a.asset_id,
    a.asset_name,
    a.isin,
    a.asset_type,
    a.currency,
    av.valuation_date,
    av.nav,
    av.yield_to_maturity,
    av.duration,
    av.convexity,
    av.credit_spread_bps,
    av.valuation_method,
    av.pricing_source,
    CONCAT(u.first_name, ' ', u.last_name) AS validated_by_name
FROM asset_valuations av
JOIN assets a        ON av.asset_id    = a.id
LEFT JOIN users u    ON av.validated_by = u.id
ORDER BY av.asset_id, av.valuation_date DESC;
CREATE OR REPLACE FUNCTION get_asset_full_audit(p_asset_id VARCHAR)
RETURNS TABLE (
    tx_ref          VARCHAR,
    fabric_tx_id    VARCHAR,
    block_number    BIGINT,
    tx_type         VARCHAR,
    initiator       TEXT,
    from_owner      TEXT,
    to_owner        TEXT,
    amount          NUMERIC,
    justification   TEXT,
    regulatory_flag BOOLEAN,
    created_at      TIMESTAMPTZ
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.tx_ref,
        t.fabric_tx_id,
        t.fabric_block_number,
        t.tx_type,
        CONCAT(ui.first_name, ' ', ui.last_name)::TEXT,
        CONCAT(uf.first_name, ' ', uf.last_name)::TEXT,
        CONCAT(ut.first_name, ' ', ut.last_name)::TEXT,
        t.amount,
        t.justification,
        t.regulatory_flag,
        t.created_at
    FROM transactions t
    JOIN assets a       ON t.asset_id      = a.id
    JOIN users ui       ON t.initiator_id  = ui.id
    LEFT JOIN users uf  ON t.from_owner_id = uf.id
    LEFT JOIN users ut  ON t.to_owner_id   = ut.id
    WHERE a.asset_id = p_asset_id
    ORDER BY t.created_at ASC;
END;
$$ LANGUAGE plpgsql;
CREATE OR REPLACE FUNCTION flag_high_risk_transactions()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.amount > 5000000 THEN
        NEW.regulatory_flag := TRUE;
    END IF;
    IF NEW.amount > 1000000 THEN
        UPDATE compliance_records
        SET sar_count = sar_count + 1
        WHERE participant_id = NEW.initiator_id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_flag_high_risk
BEFORE INSERT ON transactions
FOR EACH ROW EXECUTE FUNCTION flag_high_risk_transactions();
CREATE OR REPLACE FUNCTION refresh_asset_current_value()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE assets
    SET current_value       = NEW.nav,
        last_valuation_date = NEW.valuation_date,
        updated_at          = NOW()
    WHERE id = NEW.asset_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER trg_update_asset_value
AFTER INSERT ON asset_valuations
FOR EACH ROW EXECUTE FUNCTION refresh_asset_current_value();
CREATE OR REPLACE FUNCTION get_org_portfolio_summary(p_org_id UUID)
RETURNS JSONB AS $$
DECLARE result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'total_assets',      COUNT(*),
        'total_nominal_eur', SUM(CASE WHEN a.currency = 'EUR' THEN a.nominal_value
                                      ELSE a.nominal_value / 1.0832 END),
        'total_current_eur', SUM(CASE WHEN a.currency = 'EUR' THEN a.current_value
                                      ELSE a.current_value / 1.0832 END),
        'active_count',      COUNT(*) FILTER (WHERE a.status = 'ACTIF'),
        'frozen_count',      COUNT(*) FILTER (WHERE a.status = 'GELE'),
        'emission_count',    COUNT(*) FILTER (WHERE a.status = 'EN_EMISSION')
    ) INTO result
    FROM assets a
    WHERE a.issuer_org_id = p_org_id;
    RETURN result;
END;
$$ LANGUAGE plpgsql;
