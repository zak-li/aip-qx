"""gRPC server entry point.

Starts the async gRPC server on the port defined by GRPC_PORT (default 50051).
FastAPI remains running on its own port exclusively to serve the React SPA,
/health, and /metrics — browsers cannot speak gRPC without a proxy.

Usage:
    python -m core.grpc_server.server
"""
from __future__ import annotations

import asyncio
import logging
import signal

import grpc
import grpc.aio

from core.config import settings
from core.core.logging_config import setup_logging
from core.grpc_generated import (
    agent_pb2_grpc,
    assets_pb2_grpc,
    audit_pb2_grpc,
    auth_pb2_grpc,
    compliance_pb2_grpc,
    organizations_pb2_grpc,
    transactions_pb2_grpc,
    zkp_pb2_grpc,
)
from core.grpc_server.interceptors import AuthInterceptor, LoggingInterceptor
from core.grpc_server.servicers.agent import AgentServicer
from core.grpc_server.servicers.assets import AssetsServicer
from core.grpc_server.servicers.audit import AuditServicer
from core.grpc_server.servicers.auth import AuthServicer
from core.grpc_server.servicers.compliance import ComplianceServicer
from core.grpc_server.servicers.organizations import OrganizationsServicer
from core.grpc_server.servicers.transactions import TransactionsServicer
from core.grpc_server.servicers.zkp import ZKPServicer

setup_logging(settings.log_level)
logger = logging.getLogger(__name__)


async def serve() -> None:
    server = grpc.aio.server(
        interceptors=[LoggingInterceptor(), AuthInterceptor()],
        options=[
            ("grpc.keepalive_time_ms", 30_000),
            ("grpc.keepalive_timeout_ms", 10_000),
            ("grpc.keepalive_permit_without_calls", True),
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.max_receive_message_length", 4 * 1024 * 1024),
        ],
    )

    # Register all 8 servicers.
    auth_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    assets_pb2_grpc.add_AssetsServiceServicer_to_server(AssetsServicer(), server)
    compliance_pb2_grpc.add_ComplianceServiceServicer_to_server(ComplianceServicer(), server)
    transactions_pb2_grpc.add_TransactionsServiceServicer_to_server(TransactionsServicer(), server)
    audit_pb2_grpc.add_AuditServiceServicer_to_server(AuditServicer(), server)
    agent_pb2_grpc.add_AgentServiceServicer_to_server(AgentServicer(), server)
    zkp_pb2_grpc.add_ZKPServiceServicer_to_server(ZKPServicer(), server)
    organizations_pb2_grpc.add_OrganizationsServiceServicer_to_server(OrganizationsServicer(), server)

    port = settings.grpc_port
    listen_addr = f"[::]:{port}"

    _use_tls = (
        settings.environment == "production"
        and bool(settings.grpc_server_cert)
        and bool(settings.grpc_server_key)
        and bool(settings.grpc_ca_cert)
    )
    if _use_tls:
        with open(settings.grpc_server_cert, "rb") as f:  # noqa: ASYNC230
            cert_chain = f.read()
        with open(settings.grpc_server_key, "rb") as f:  # noqa: ASYNC230
            private_key = f.read()
        with open(settings.grpc_ca_cert, "rb") as f:  # noqa: ASYNC230
            root_cert = f.read()
        credentials = grpc.ssl_server_credentials(
            [(private_key, cert_chain)],
            root_certificates=root_cert,
            require_client_auth=True,
        )
        server.add_secure_port(listen_addr, credentials)
        logger.info(f"gRPC server starting (mTLS) on {listen_addr}")
    else:
        server.add_insecure_port(listen_addr)
        if settings.environment == "production":
            logger.warning(
                "gRPC server starting in INSECURE mode in production! "
                "Set GRPC_SERVER_CERT, GRPC_SERVER_KEY, and GRPC_CA_CERT "
                "to enable mTLS. Without mTLS, gRPC should NOT be exposed "
                "outside the host."
            )
        else:
            logger.info(f"gRPC server starting (insecure) on {listen_addr}")

    await server.start()

    loop = asyncio.get_running_loop()

    async def _shutdown() -> None:
        logger.info("gRPC server shutting down…")
        await server.stop(grace=5)

    loop.add_signal_handler(signal.SIGTERM, lambda: asyncio.create_task(_shutdown()))
    loop.add_signal_handler(signal.SIGINT,  lambda: asyncio.create_task(_shutdown()))

    await server.wait_for_termination()


if __name__ == "__main__":
    asyncio.run(serve())
