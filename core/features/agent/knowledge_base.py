"""Static knowledge base — MiCA, AML/KYC, Fabric architecture docs."""
from __future__ import annotations

KNOWLEDGE_CHUNKS: list[dict[str, str]] = [
    {
        "id": "mica_art68",
        "category": "regulation",
        "title": "MiCA Article 68 — Seuil d'identification",
        "content": (
            "MiCA Article 68 : toute transaction d'actif tokenisé dépassant 1 000 EUR "
            "déclenche une obligation d'identification renforcée du donneur d'ordre et du bénéficiaire. "
            "La plateforme marque automatiquement ces transactions avec identification_required=True "
            "et génère une alerte ART68 dans les logs de conformité."
        ),
    },
    {
        "id": "mica_art76",
        "category": "regulation",
        "title": "MiCA Article 76 — Exigences ISIN/LEI",
        "content": (
            "MiCA Article 76 : les actifs de type OBLIGATION ou DERIVE doivent posséder un "
            "identifiant ISIN valide (12 caractères, format XX[A-Z0-9]{10}) ou un préfixe RWA-. "
            "L'absence de cet identifiant génère une violation non-bloquante de catégorie ART76."
        ),
    },
    {
        "id": "kyc_levels",
        "category": "compliance",
        "title": "Niveaux KYC — Tableau des exigences",
        "content": (
            "Niveau KYC 1 (BASIQUE) : vérification identité simple. "
            "Niveau KYC 2 (STANDARD) : justificatifs domicile + source de fonds. "
            "Niveau KYC 3 (APPROFONDI) : due diligence complète, PEP check, vérification LEI. "
            "Niveau KYC 4 (RENFORCÉ) : audit annuel, visite sur site. "
            "Niveau KYC 5 (INSTITUTIONNEL) : certification ISDA/EFAMA requise. "
            "Le niveau requis par défaut pour les transactions est KYC_REQUIRED_LEVEL=3."
        ),
    },
    {
        "id": "aml_scoring",
        "category": "compliance",
        "title": "Calcul du score AML",
        "content": (
            "Score AML = (jurisdiction_risk x 0.30) + (cross_border_activity x 0.40) + "
            "(unusual_volume x 0.30). "
            "Bonus montant : +0.10 si transaction > 25M EUR, +0.05 si > 5M EUR. "
            "Seuils : FAIBLE < 0.30, MOYEN < 0.60, ELEVÉ ≤ 0.75, CRITIQUE > 0.75. "
            "Blocage si score > MAX_AML_SCORE (0.60). SAR généré si score > SAR_THRESHOLD (0.75)."
        ),
    },
    {
        "id": "asset_types",
        "category": "assets",
        "title": "Types d'actifs RWA supportés",
        "content": (
            "Types d'actifs tokenisés sur la plateforme : "
            "OBLIGATION (obligations d'État/corporate), "
            "OPCVM (fonds communs de placement), "
            "IMMOBILIER (SCPI, REITs tokenisés), "
            "DERIVE (produits dérivés OTC), "
            "MATIERE_PREMIERE (or, pétrole, métaux), "
            "PRIVATE_EQUITY (fonds de capital-investissement), "
            "INFRASTRUCTURE (PPP, fonds d'infrastructure)."
        ),
    },
    {
        "id": "asset_statuses",
        "category": "assets",
        "title": "Statuts des actifs",
        "content": (
            "Statuts possibles : ACTIF (actif négociable), GELE (gel réglementaire REG01, transfert interdit), "
            "EN_EMISSION (phase primaire, pas encore négociable), REMBOURSE (actif arrivé à maturité). "
            "Le gel est initié uniquement par REG01MSP via FreezeAsset. "
            "Le dégel est effectué par UnfreezeAsset après autorisation réglementaire."
        ),
    },
    {
        "id": "fabric_architecture",
        "category": "blockchain",
        "title": "Architecture Hyperledger Fabric",
        "content": (
            "Réseau Fabric : 2 organisations (BANK01MSP, REG01MSP) + 1 orderer. "
            "Channel : rwa-channel. Chaincode : rwa-token (CCAAS). "
            "State DB : CouchDB (requêtes JSON riches). "
            "Fonctions chaincode : TokenizeAsset, TransferAsset, FreezeAsset, UnfreezeAsset, "
            "GetAsset, GetAssetHistory, GetProvenanceTrail, QueryAssets. "
            "Politiques d'endorsement : BANK01MSP pour émission/transfert, "
            "REG01MSP pour gel/dégel."
        ),
    },
    {
        "id": "transaction_types",
        "category": "transactions",
        "title": "Types de transactions",
        "content": (
            "Types de transactions enregistrés : "
            "TOKENISATION (création d'actif), "
            "TRANSFERT (changement de propriétaire), "
            "GEL (freeze réglementaire), "
            "DEGEL (unfreeze réglementaire), "
            "RACHAT (remboursement/redemption), "
            "COUPON_PAIEMENT (versement d'intérêts), "
            "MISE_A_JOUR_VALEUR (revalorisation NAV), "
            "ANNULATION (correction erreur), "
            "REGLEMENT (DVP settlement)."
        ),
    },
    {
        "id": "roles",
        "category": "access_control",
        "title": "Rôles et permissions",
        "content": (
            "Rôles utilisateurs : "
            "EMETTEUR (peut tokeniser et transférer ses actifs), "
            "TRADER (peut initier des transferts), "
            "CUSTODIAN (conservation et transferts autorisés), "
            "REGULATEUR (gel/dégel, lecture compliance), "
            "AUDITEUR (lecture seule toutes données), "
            "COMPLIANCE_OFFICER (KYC/AML, valorisation), "
            "SUPER_ADMIN (tous droits)."
        ),
    },
    {
        "id": "fraud_patterns",
        "category": "fraud",
        "title": "Patterns de fraude détectés par Neo4j",
        "content": (
            "4 patterns de fraude analysés par le moteur Neo4j : "
            "1. Flux circulaire (circular_flow) : actif transféré en boucle entre acteurs. "
            "2. Smurfing : fractionnement de montants élevés en petites transactions < seuil MiCA. "
            "3. Layering : multiples transferts rapides pour masquer l'origine des fonds. "
            "4. Concentration de transferts : un acteur reçoit > 60% du volume total."
        ),
    },
    {
        "id": "saga_pattern",
        "category": "architecture",
        "title": "Pattern SAGA — Cohérence distribuée Fabric/PostgreSQL",
        "content": (
            "La plateforme utilise le pattern SAGA pour garantir la cohérence entre Fabric et PostgreSQL. "
            "Si le commit PostgreSQL échoue après un TransferAsset Fabric réussi, "
            "une transaction de compensation automatique (TransferAsset inversé) est envoyée à Fabric. "
            "Idem pour FreezeAsset : compensation = UnfreezeAsset. "
            "En cas d'échec de la compensation, une alerte CRITIQUE est loggée pour intervention manuelle."
        ),
    },
    {
        "id": "vault_security",
        "category": "security",
        "title": "Sécurité — HashiCorp Vault",
        "content": (
            "Les clés privées Fabric (admin@bank01, admin@reg01-regulateur) sont stockées "
            "dans HashiCorp Vault (moteur KV v2, mount point rwa-fabric). "
            "Les clés ne sont jamais conservées en mémoire au-delà de l'opération de signature. "
            "La mémoire est effacée via ctypes après chaque utilisation (zero-memory). "
            "Token Vault statique en dev/test — AppRole recommandé en production."
        ),
    },
]
