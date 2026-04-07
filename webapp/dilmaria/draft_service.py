from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from webapp.dilmaria.models import DilmariaPopDraft
from webapp.dilmaria.pop_schema import PopDraftState, SavedPopDraft


class PopDraftService:
    def load_draft(self, db: Session, user_id: int) -> SavedPopDraft | None:
        draft = db.scalar(
            select(DilmariaPopDraft).where(DilmariaPopDraft.user_id == user_id)
        )
        if draft is None or not draft.payload_snapshot:
            return None
        return SavedPopDraft(
            titulo=draft.titulo,
            codigo=draft.codigo,
            structure_key=draft.structure_key,
            saved_at=draft.updated_at,
            state=PopDraftState.model_validate(json.loads(draft.payload_snapshot)),
        )

    def save_draft(self, db: Session, user_id: int, payload: dict) -> SavedPopDraft:
        state = PopDraftState.model_validate(payload)
        draft = db.scalar(
            select(DilmariaPopDraft).where(DilmariaPopDraft.user_id == user_id)
        )
        if draft is None:
            draft = DilmariaPopDraft(user_id=user_id)
            db.add(draft)

        draft.titulo = (state.form_payload.titulo if state.form_payload else "") or ""
        draft.codigo = (state.form_payload.codigo if state.form_payload else "") or ""
        draft.structure_key = state.structure_key or ""
        draft.payload_snapshot = json.dumps(
            state.model_dump(mode="json"),
            ensure_ascii=False,
            default=str,
        )
        draft.updated_at = datetime.utcnow()
        db.commit()
        return SavedPopDraft(
            titulo=draft.titulo,
            codigo=draft.codigo,
            structure_key=draft.structure_key,
            saved_at=draft.updated_at,
            state=state,
        )

    def clear_draft(self, db: Session, user_id: int) -> bool:
        draft = db.scalar(
            select(DilmariaPopDraft).where(DilmariaPopDraft.user_id == user_id)
        )
        if draft is None:
            return False
        db.delete(draft)
        db.commit()
        return True
