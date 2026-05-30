-- Migration: Add Moroccan institutions and participants
-- Safe to run multiple times (ON CONFLICT DO NOTHING)

INSERT INTO organizations (
  id, org_code, legal_name, short_name, org_type, lei, bic_swift,
  msp_id, country_code, jurisdiction, regulator_ref, aml_risk_rating,
  onboarded_at, last_audit_date
) VALUES
  ('a1b2c3d4-0008-0008-0008-000000000008',
   'ATW-MA', 'Bank 03 S.A.', 'Bank 03',
   'BANQUE_COMMERCIALE', 'XKZZ2JZF41MRHTR1V493', 'BCMAMAMRXXX',
   'Bank03MSP', 'MA', 'Maroc — Reg 03',
   'BAM-AGR-2006-0001', 'FAIBLE',
   '2025-01-15 09:00:00+01', '2025-03-10'),
  ('a1b2c3d4-0009-0009-0009-000000000009',
   'REG03-MA', 'Autorité Marocaine du Marché des Capitaux', 'REG03',
   'REGULATEUR', 'H3EZTQ2ZKBQP8MA00001', NULL,
   'REG03MSP', 'MA', 'Maroc — Autorité indépendante',
   'REG03-AUTORITE-001', 'TRES_FAIBLE',
   '2025-01-15 09:00:00+01', NULL)
ON CONFLICT (id) DO NOTHING;

-- password_changed_at = NULL forces a password-change prompt on first login
INSERT INTO users (
  id, org_id, email, first_name, last_name,
  role, msp_id, fabric_cert_serial, phone, department, employee_id, created_at
) VALUES
  ('a0000011-0011-0011-0011-000000000011',
   'a1b2c3d4-0008-0008-0008-000000000008',
   'zakaria.rahali@bank03.qx.demo',
   'Zakaria', 'Rahali', 'EMETTEUR', 'Bank03MSP',
   'SN-ATW-PEER-E5F6A1B2C3D8',
   '+212 5 22 58 88 88', 'Digital Assets & Tokenization',
   'ATW-TKN-0001', TRUE, NULL, '2025-01-20 09:00:00+01'),
  ('a0000012-0012-0012-0012-000000000012',
   'a1b2c3d4-0009-0009-0009-000000000009',
   'aya.belakhouad@reg03.qx.demo',
   'Aya', 'Belakhouad', 'REGULATEUR', 'REG03MSP',
   'SN-REG03-PEER-F6A1B2C3D4E9',
   '+212 5 37 68 98 00', 'Division Innovation Financiere',
   'REG03-REG-0001', TRUE, NULL, '2025-01-20 09:00:00+01'),
  ('a0000013-0013-0013-0013-000000000013',
   'a1b2c3d4-0008-0008-0008-000000000008',
   'youssef.alami@bank03.qx.demo',
   'Youssef', 'Alami', 'TRADER', 'Bank03MSP',
   'SN-ATW-PEER-A1B2C3D4E5F8',
   '+212 5 22 58 80 00', 'Fixed Income & Sukuk Trading',
   'ATW-TRD-0042', TRUE, NULL, '2025-01-20 09:00:00+01'),
  ('a0000014-0014-0014-0014-000000000014',
   'a1b2c3d4-0008-0008-0008-000000000008',
   'fatima.benali@bank03.qx.demo',
   'Fatima Zahra', 'Benali', 'COMPLIANCE_OFFICER', 'Bank03MSP',
   'SN-ATW-PEER-B2C3D4E5F6A8',
   '+212 5 22 58 82 30', 'Conformite et LAB',
   'ATW-CMP-0018', TRUE, NULL, '2025-01-20 09:00:00+01'),
  ('a0000015-0015-0015-0015-000000000015',
   'a1b2c3d4-0009-0009-0009-000000000009',
   'mehdi.tahiri@reg03.qx.demo',
   'Mehdi', 'Tahiri', 'AUDITEUR', 'REG03MSP',
   'SN-REG03-PEER-C3D4E5F6A1B9',
   '+212 5 37 68 98 11', 'Audit et Surveillance des Marches',
   'REG03-AUD-0003', TRUE, NULL, '2025-01-20 09:00:00+01')
ON CONFLICT (id) DO NOTHING;
