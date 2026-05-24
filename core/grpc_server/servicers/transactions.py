"""gRPC servicer for the Transactions service."""
from __future__ import annotations

import grpc
import grpc.aio
from sqlalchemy import func, select

from core.core.database import AsyncSessionLocal
from core.features.transactions.models import Transaction
from core.grpc_generated import transactions_pb2, transactions_pb2_grpc


class TransactionsServicer(transactions_pb2_grpc.TransactionsServiceServicer):

    async def ListTransactions(
        self,
        request: transactions_pb2.ListRequest,
        context: grpc.aio.ServicerContext,
    ) -> transactions_pb2.TransactionList:
        async with AsyncSessionLocal() as db:
            stmt = select(Transaction)
            if request.tx_type:
                stmt = stmt.where(Transaction.tx_type == request.tx_type)
            if request.has_regulatory:
                stmt = stmt.where(Transaction.regulatory_flag == request.regulatory_flag)
            stmt = stmt.order_by(Transaction.created_at.desc())
            stmt = stmt.limit(request.limit or 50).offset(request.offset or 0)
            txs = (await db.execute(stmt)).scalars().all()

        return transactions_pb2.TransactionList(
            transactions=[_tx_to_proto(t) for t in txs]
        )

    async def GetTransactionStats(
        self,
        request: transactions_pb2.StatsRequest,
        context: grpc.aio.ServicerContext,
    ) -> transactions_pb2.TransactionStats:
        async with AsyncSessionLocal() as db:
            total = (await db.execute(select(func.count(Transaction.id)))).scalar() or 0
            frozen = (await db.execute(
                select(func.coalesce(func.sum(Transaction.amount), 0))
                .where(Transaction.tx_type == "GEL")
            )).scalar() or 0

        return transactions_pb2.TransactionStats(
            total_transactions=total,
            volume_frozen=float(frozen),
        )

    async def GetTransaction(
        self,
        request: transactions_pb2.TxRefRequest,
        context: grpc.aio.ServicerContext,
    ) -> transactions_pb2.TransactionResponse:
        async with AsyncSessionLocal() as db:
            stmt = select(Transaction).where(Transaction.tx_ref == request.tx_ref)
            tx = (await db.execute(stmt)).scalar_one_or_none()

        if not tx:
            await context.abort(grpc.StatusCode.NOT_FOUND, "Transaction not found")
        return _tx_to_proto(tx)


def _tx_to_proto(t: Transaction) -> transactions_pb2.TransactionResponse:
    return transactions_pb2.TransactionResponse(
        tx_ref=t.tx_ref or "",
        fabric_tx_id=t.fabric_tx_id or "",
        tx_type=t.tx_type or "",
        amount=float(t.amount) if t.amount is not None else 0.0,
        currency=t.currency or "",
        initiator_id=str(t.initiator_id) if t.initiator_id else "",
        from_owner_id=str(t.from_owner_id) if t.from_owner_id else "",
        to_owner_id=str(t.to_owner_id) if t.to_owner_id else "",
        regulatory_flag=bool(t.regulatory_flag),
        status=t.status or "",
        created_at=t.created_at.isoformat() if t.created_at else "",
    )
