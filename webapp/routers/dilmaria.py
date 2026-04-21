from __future__ import annotations

from io import BytesIO

from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse

from conciliador.service import ConciliationUserError

from webapp.dependencies import (
    get_csrf_token,
    get_db_session,
    render_page,
    require_user,
    validate_csrf_header,
)
from webapp.dilmaria.doc_formatter_schema import DocFormatterPayload
from webapp.dilmaria.doc_formatter_service import run_doc_formatter_agent
from webapp.dilmaria.draft_service import PopDraftService
from webapp.dilmaria.exceptions import AgentExecutionError
from webapp.dilmaria.history_service import PopHistoryService as DilmariaPopHistoryService
from webapp.dilmaria.pop_schema import PopRequest
from webapp.dilmaria.pop_service import preview_pop_generator_agent, run_pop_generator_agent
from webapp.dilmaria.pop_structures import list_pop_structures
from webapp.erp import has_permission, serialize_user

router = APIRouter()


@router.get("/operacoes/dilmaria", response_class=HTMLResponse)
async def dilmaria_page(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            return RedirectResponse("/login", status_code=status.HTTP_303_SEE_OTHER)
        if not has_permission(user, "read"):
            return RedirectResponse("/operacoes/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        return render_page(
            request,
            user,
            "dilmaria.html",
            "operacoes",
            "dilmaria",
            "DilmarIA",
            "Modulo de agentes com foco em POPs e automacao documental.",
            {
                "dilmaria_bootstrap": {
                    "current_user": serialize_user(user),
                    "csrf_token": get_csrf_token(request),
                    "settings_url": "/configuracoes",
                    "hub_url": "/hub",
                    "uses_host_openai_env": True,
                }
            },
        )


@router.get("/operacoes/dilmaria/api/health")
async def dilmaria_health(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Sessao obrigatoria.")
        return {"status": "ok"}


@router.get("/operacoes/dilmaria/api/structures")
async def dilmaria_structures(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Sessao obrigatoria.")
        return [item.model_dump(mode="json") for item in list_pop_structures()]


@router.get("/operacoes/dilmaria/api/history")
async def dilmaria_history(request: Request, limit: int = Query(default=8)):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Sessao obrigatoria.")
        safe_limit = max(1, min(limit, 20))
        history = DilmariaPopHistoryService().build_history_summary(db, limit=safe_limit)
        return history.model_dump(mode="json")


@router.get("/operacoes/dilmaria/api/draft")
async def dilmaria_draft(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Sessao obrigatoria.")
        draft = PopDraftService().load_draft(db, user.id)
        if draft is None:
            return {"draft": None}
        return {"draft": draft.model_dump(mode="json")}


@router.post("/operacoes/dilmaria/api/draft")
async def dilmaria_save_draft(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Sessao obrigatoria.")
        if not has_permission(user, "edit"):
            raise HTTPException(status_code=403, detail="Acesso nao autorizado.")
        try:
            validate_csrf_header(request)
            payload = await request.json()
            saved = PopDraftService().save_draft(db, user.id, payload)
            return saved.model_dump(mode="json")
        except ConciliationUserError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/operacoes/dilmaria/api/draft")
async def dilmaria_clear_draft(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Sessao obrigatoria.")
        if not has_permission(user, "edit"):
            raise HTTPException(status_code=403, detail="Acesso nao autorizado.")
        try:
            validate_csrf_header(request)
            cleared = PopDraftService().clear_draft(db, user.id)
            return {"cleared": cleared}
        except ConciliationUserError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/operacoes/dilmaria/api/preview")
async def dilmaria_preview(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Sessao obrigatoria.")
        if not has_permission(user, "edit"):
            raise HTTPException(status_code=403, detail="Acesso nao autorizado.")
        try:
            validate_csrf_header(request)
            payload = await request.json()
            preview = await preview_pop_generator_agent(payload)
            return preview.model_dump(mode="json")
        except ConciliationUserError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AgentExecutionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/operacoes/dilmaria/api/run")
async def dilmaria_run(request: Request):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Sessao obrigatoria.")
        if not has_permission(user, "edit"):
            raise HTTPException(status_code=403, detail="Acesso nao autorizado.")
        try:
            validate_csrf_header(request)
            payload = PopRequest.model_validate(await request.json()).model_dump(mode="python")
            result = await run_pop_generator_agent(db, user.id, payload)
        except ConciliationUserError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except AgentExecutionError as exc:
            db.rollback()
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception:
            db.rollback()
            raise
        PopDraftService().clear_draft(db, user.id)

        output_name = f"{result.pop.file_stub}.docx"
        return StreamingResponse(
            BytesIO(result.document_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={
                "Content-Disposition": f'attachment; filename="{output_name}"',
                "X-POP-Code": result.pop.codigo,
                "X-POP-Revision": result.pop.revisao,
            },
        )


@router.post("/operacoes/dilmaria/api/doc-formatter/run")
async def dilmaria_doc_formatter_run(
    request: Request,
    template: UploadFile = File(...),
    text: str = Form(...),
    mode: str = Form("placeholder"),
    csrf_token: str = Form(default=""),
):
    with get_db_session() as db:
        user = require_user(request, db)
        if not user:
            raise HTTPException(status_code=401, detail="Sessao obrigatoria.")
        if not has_permission(user, "edit"):
            raise HTTPException(status_code=403, detail="Acesso nao autorizado.")
        if str(csrf_token) != str(request.session.get("csrf_token", "")):
            raise HTTPException(status_code=400, detail="Sessao invalida ou expirada.")
        if not template.filename or not template.filename.lower().endswith(".docx"):
            raise HTTPException(status_code=400, detail="Apenas arquivos .docx sao permitidos.")
        if not text.strip():
            raise HTTPException(status_code=400, detail="O texto para formatacao e obrigatorio.")

        payload = DocFormatterPayload(
            filename=template.filename,
            content_type=template.content_type,
            template_bytes=await template.read(),
            text=text,
            mode=mode,
        )
        try:
            result = await run_doc_formatter_agent(payload.model_dump(mode="python"))
        except AgentExecutionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        filename = template.filename.rsplit(".", 1)[0]
        output_name = f"{filename}-formatado.docx"
        return StreamingResponse(
            BytesIO(result.document_bytes),
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": f'attachment; filename="{output_name}"'},
        )
