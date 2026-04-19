import os
import re

MAPPINGS = {
    "backend.features.auth.models": "backend.features.auth.models",
    "backend.features.auth.schemas": "backend.features.auth.schemas",
    "backend.features.auth.router": "backend.features.auth.router",
    "backend.features.auth.organizations_router": "backend.features.auth.organizations_router",
    
    "backend.features.assets.models": "backend.features.assets.models",
    "backend.features.assets.schemas": "backend.features.assets.schemas",
    "backend.features.assets.service": "backend.features.assets.service",
    "backend.features.assets.tasks": "backend.features.assets.tasks",
    "backend.features.assets.router": "backend.features.assets.router",
    "backend.features.assets.valuation_service": "backend.features.assets.valuation_service",
    
    "backend.features.compliance.models": "backend.features.compliance.models",
    "backend.features.compliance.schemas": "backend.features.compliance.schemas",
    "backend.features.compliance.service": "backend.features.compliance.service",
    "backend.features.compliance.tasks": "backend.features.compliance.tasks",
    "backend.features.compliance.router": "backend.features.compliance.router",
    "backend.features.compliance.kyc": "backend.features.compliance.kyc",
    "backend.features.compliance.aml": "backend.features.compliance.aml",
    "backend.features.compliance.sanctions": "backend.features.compliance.sanctions",
    "backend.features.compliance.sar_reporter": "backend.features.compliance.sar_reporter",
    "backend.features.compliance.rules_mica": "backend.features.compliance.rules_mica",
    
    "backend.features.transactions.models": "backend.features.transactions.models",
    "backend.features.transactions.schemas": "backend.features.transactions.schemas",
    "backend.features.transactions.router": "backend.features.transactions.router",
    
    "backend.features.audit.integrity_checker": "backend.features.audit.integrity_checker",
    "backend.features.audit.report_generator": "backend.features.audit.report_generator",
    "backend.features.audit.trail": "backend.features.audit.trail",
    "backend.features.audit.tasks": "backend.features.audit.tasks",
    "backend.features.audit.router": "backend.features.audit.router",
    
    "backend.features.agent.gemini_client": "backend.features.agent.gemini_client",
    "backend.features.agent.groq_client": "backend.features.agent.groq_client",
    "backend.features.agent.rag_pipeline": "backend.features.agent.rag_pipeline",
    "backend.features.agent.retriever": "backend.features.agent.retriever",
    "backend.features.agent.vector_store": "backend.features.agent.vector_store",
    "backend.features.agent.knowledge_base": "backend.features.agent.knowledge_base",
    "backend.features.agent.router": "backend.features.agent.router",
    
    "backend.features.fraud_detection.neo4j_sync": "backend.features.fraud_detection.neo4j_sync",
    "backend.features.fraud_detection.fraud_detection": "backend.features.fraud_detection.fraud_detection",
    
    "backend.core.database_base": "backend.core.database_base",
    "backend.core.celery_app": "backend.core.celery_app",
}

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = content
    for old_path, new_path in MAPPINGS.items():
        # Replace exact imports
        new_content = re.sub(rf'\b{old_path}\b', new_path, new_content)

    if new_content != content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f"Updated {filepath}")

for root, _, files in os.walk('.'):
    if '.venv' in root or '.git' in root or '__pycache__' in root:
        continue
    for file in files:
        if file.endswith('.py'):
            process_file(os.path.join(root, file))
