-- Migration: Add Moroccan institutions and participants
-- Safe to run multiple times (ON CONFLICT DO NOTHING)

INSERT INTO organizations (
  id, org_code, legal_name, short_name, org_type, lei, bic_swift,
  msp_id, country_code, jurisdiction, regulator_ref, aml_risk_rating,
  onboarded_at, last_audit_date
) VALUES
  ('a1b2c3d4-0008-0008-0008-000000000008',
   'ATW-MA', 'Attijariwafa Bank S.A.', 'Attijariwafa',
   'BANQUE_COMMERCIALE', 'XKZZ2JZF41MRHTR1V493', 'BCMAMAMRXXX',
   'AttijariwafaMSP', 'MA', 'Maroc — Bank Al-Maghrib / AMMC',
   'BAM-AGR-2006-0001', 'FAIBLE',
   '2025-01-15 09:00:00+01', '2025-03-10'),
  ('a1b2c3d4-0009-0009-0009-000000000009',
   'AMMC-MA', 'Autorité Marocaine du Marché des Capitaux', 'AMMC',
   'REGULATEUR', 'H3EZTQ2ZKBQP8MA00001', NULL,
   'AMMCRegulateurMSP', 'MA', 'Maroc — Autorité indépendante',
   'AMMC-AUTORITE-001', 'TRES_FAIBLE',
   '2025-01-15 09:00:00+01', NULL)
ON CONFLICT (id) DO NOTHING;

-- password_changed_at = NULL forces a password-change prompt on first login
INSERT INTO users (
  id, org_id, email, hashed_password, first_name, last_name,
  role, msp_id, fabric_cert_serial, phone, department, employee_id,
  mfa_enabled, password_changed_at, created_at
) VALUES
  ('a0000011-0011-0011-0011-000000000011',
   'a1b2c3d4-0008-0008-0008-000000000008',
   'zakaria.rahali@attijariwafa.ma',
   crypt('ChangeMe2025!', gen_salt('bf', 12)),
   'Zakaria', 'Rahali', 'EMETTEUR', 'AttijariwafaMSP',
   'SN-ATW-PEER-E5F6A1B2C3D8',
   '+212 5 22 58 88 88', 'Digital Assets & Tokenization',
   'ATW-TKN-0001', TRUE, NULL, '2025-01-20 09:00:00+01'),
  ('a0000012-0012-0012-0012-000000000012',
   'a1b2c3d4-0009-0009-0009-000000000009',
   'aya.belakhouad@ammc.ma',
   crypt('ChangeMe2025!', gen_salt('bf', 12)),
   'Aya', 'Belakhouad', 'REGULATEUR', 'AMMCRegulateurMSP',
   'SN-AMMC-PEER-F6A1B2C3D4E9',
   '+212 5 37 68 98 00', 'Division Innovation Financiere',
   'AMMC-REG-0001', TRUE, NULL, '2025-01-20 09:00:00+01'),
  ('a0000013-0013-0013-0013-000000000013',
   'a1b2c3d4-0008-0008-0008-000000000008',
   'youssef.alami@attijariwafa.ma',
   crypt('ChangeMe2025!', gen_salt('bf', 12)),
   'Youssef', 'Alami', 'TRADER', 'AttijariwafaMSP',
   'SN-ATW-PEER-A1B2C3D4E5F8',
   '+212 5 22 58 80 00', 'Fixed Income & Sukuk Trading',
   'ATW-TRD-0042', TRUE, NULL, '2025-01-20 09:00:00+01'),
  ('a0000014-0014-0014-0014-000000000014',
   'a1b2c3d4-0008-0008-0008-000000000008',
   'fatima.benali@attijariwafa.ma',
   crypt('ChangeMe2025!', gen_salt('bf', 12)),
   'Fatima Zahra', 'Benali', 'COMPLIANCE_OFFICER', 'AttijariwafaMSP',
   'SN-ATW-PEER-B2C3D4E5F6A8',
   '+212 5 22 58 82 30', 'Conformite et LAB',
   'ATW-CMP-0018', TRUE, NULL, '2025-01-20 09:00:00+01'),
  ('a0000015-0015-0015-0015-000000000015',
   'a1b2c3d4-0009-0009-0009-000000000009',
   'mehdi.tahiri@ammc.ma',
   crypt('ChangeMe2025!', gen_salt('bf', 12)),
   'Mehdi', 'Tahiri', 'AUDITEUR', 'AMMCRegulateurMSP',
   'SN-AMMC-PEER-C3D4E5F6A1B9',
   '+212 5 37 68 98 11', 'Audit et Surveillance des Marches',
   'AMMC-AUD-0003', TRUE, NULL, '2025-01-20 09:00:00+01')
ON CONFLICT (id) DO NOTHING;
