from prometheus_client import Counter, Gauge, Histogram

RWA_TRANSACTIONS = Counter("rwa_transactions_total", "Transactions RWA", ["tx_type", "org", "status"])
RWA_CHAINCODE_DURATION = Histogram(
    "rwa_chaincode_duration_seconds", "Duree chaincode",
    ["function", "status"],
    buckets=[0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5, 10],
)
RWA_ASSETS_BY_STATUS = Gauge("rwa_assets_by_status", "Actifs par statut", ["status"])
RWA_KYC_EXPIRING = Gauge("rwa_kyc_expiring_count", "KYC expirant")
RWA_AML_SCORE = Gauge("rwa_aml_score_avg", "AML score", ["risk_category"])
RWA_COMPLIANCE_BLOCKS = Counter("rwa_compliance_blocks_total", "Compliance Blocks", ["blocked_by"])
RWA_CELERY_TASKS = Counter("rwa_celery_tasks_total", "Taches Celery", ["task_name", "status"])

# Initialise label combinations
RWA_COMPLIANCE_BLOCKS.labels(blocked_by="aml_screening").inc(0)
RWA_COMPLIANCE_BLOCKS.labels(blocked_by="kyc_expired").inc(0)
RWA_CELERY_TASKS.labels(task_name="generate_audit_report", status="success").inc(0)
RWA_CELERY_TASKS.labels(task_name="generate_audit_report", status="failure").inc(0)
RWA_CELERY_TASKS.labels(task_name="sync_fabric_events", status="success").inc(0)
