from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webapp.dilmaria.models import DilmariaPopRevision, DilmariaPopRun
from webapp.dilmaria.pop_schema import POP, PopExecutionLogEntry, PopHistorySummary


class PopHistoryService:
    def reserve_revision(self, db: Session, codigo: str) -> str:
        revision = db.scalar(
            select(DilmariaPopRevision).where(DilmariaPopRevision.codigo == codigo)
        )
        if revision is None:
            revision = DilmariaPopRevision(codigo=codigo, current_revision=0)
            db.add(revision)
        else:
            revision.current_revision += 1
        revision.updated_at = datetime.utcnow()
        return f"Rev.{revision.current_revision:02d}"

    def log_execution(self, db: Session, pop: POP, user_id: int, payload_snapshot: dict | None = None) -> None:
        db.add(
            DilmariaPopRun(
                user_id=user_id,
                pop_id=pop.id,
                titulo=pop.titulo,
                codigo=pop.codigo,
                revisao=pop.revisao,
                structure_key=pop.structure_key,
                structure_name=pop.structure_name,
                payload_snapshot=json.dumps(
                    payload_snapshot or {},
                    ensure_ascii=False,
                    default=str,
                ),
            )
        )

    def build_history_summary(self, db: Session, limit: int = 8) -> PopHistorySummary:
        total_execucoes = int(
            db.scalar(select(func.count()).select_from(DilmariaPopRun)) or 0
        )
        total_codigos = int(
            db.scalar(select(func.count()).select_from(DilmariaPopRevision)) or 0
        )
        rows = db.scalars(
            select(DilmariaPopRun).order_by(DilmariaPopRun.created_at.desc()).limit(limit)
        ).all()
        recentes = [
            PopExecutionLogEntry(
                timestamp=row.created_at,
                id=row.pop_id,
                titulo=row.titulo,
                codigo=row.codigo,
                revisao=row.revisao,
                data=row.created_at.date(),
                structure_key=row.structure_key,
                structure_name=row.structure_name,
            )
            for row in rows
        ]
        return PopHistorySummary(
            total_execucoes=total_execucoes,
            total_codigos=total_codigos,
            ultima_execucao_em=recentes[0].timestamp if recentes else None,
            recentes=recentes,
        )
