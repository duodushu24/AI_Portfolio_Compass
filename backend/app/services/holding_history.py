from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import HoldingObservationBatch, PositionSnapshot
from app.services.providers import normalize_market


def utc_naive(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def new_batch(db: Session, account_id: str, observed_at: datetime, *, completeness="partial",
              market="", source="manual", sync_id="") -> HoldingObservationBatch:
    batch = HoldingObservationBatch(account_id=account_id, market=normalize_market(market) if market else "",
        observed_at=utc_naive(observed_at), completeness=completeness, source=source,
        sync_id=sync_id, created_at=datetime.now(timezone.utc).replace(tzinfo=None))
    db.add(batch)
    db.flush()
    return batch


def positions_as_of(db: Session, account_id: str | None = None, at: datetime | None = None,
                    excluded_sync_ids: set[str] | None = None, *, include_void: bool = False) -> list[PositionSnapshot]:
    """Replay small local observation history. A successful full scope resets only that scope.

    Legacy observations have unknown completeness and only affect their own symbols.
    A void row suppresses that fact and older rows, without inventing a sale.
    """
    row_query = select(PositionSnapshot)
    batch_query = select(HoldingObservationBatch)
    if account_id and account_id != "all":
        row_query = row_query.where(PositionSnapshot.account_id == account_id)
        batch_query = batch_query.where(HoldingObservationBatch.account_id == account_id)
    if at:
        at = utc_naive(at)
        row_query = row_query.where(PositionSnapshot.snapshot_time <= at)
        batch_query = batch_query.where(HoldingObservationBatch.observed_at <= at)
    if excluded_sync_ids:
        row_query = row_query.where(PositionSnapshot.sync_id.notin_(excluded_sync_ids))
        batch_query = batch_query.where(HoldingObservationBatch.sync_id.notin_(excluded_sync_ids))
    rows = list(db.scalars(row_query).all())
    batches = list(db.scalars(batch_query).all())
    members: dict[int, list[PositionSnapshot]] = {}
    events = []
    known_batches = {b.id for b in batches}
    for row in rows:
        if row.batch_id in known_batches:
            members.setdefault(row.batch_id, []).append(row)
        else:
            events.append((utc_naive(row.snapshot_time), 0, row.id, "row", row))
    for batch in batches:
        events.append((batch.observed_at, 1, batch.id, "batch", batch))
    state: dict[tuple[str, str], PositionSnapshot] = {}
    for _, _, _, kind, fact in sorted(events, key=lambda event: event[:3]):
        if kind == "batch":
            if fact.completeness == "full":
                state = {key: row for key, row in state.items()
                         if row.account_id != fact.account_id or (fact.market and normalize_market(row.market) != normalize_market(fact.market))}
            for row in members.get(fact.id, []):
                state[(row.account_id, row.code)] = row
        else:
            state[(fact.account_id, fact.code)] = fact
    return sorted((row for row in state.values() if (row.quantity > 0 and not row.is_void) or (include_void and row.is_void)),
                  key=lambda row: (-row.position_weight, row.account_id, row.code))
