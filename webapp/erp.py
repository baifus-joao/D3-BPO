from __future__ import annotations

from datetime import date

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session, selectinload

from .models import BankAccount, ExecutionLog, FinancialCategory, FinancialTransaction, PaymentMethod, Store, User


ROLE_LABELS = {
    "admin": "Admin",
    "operacional": "Operacional",
    "visualizador": "Visualizador",
    "colaborador": "Operacional",
}

ROLE_PERMISSIONS = {
    "admin": {"read", "edit", "upload", "manage_users", "manage_settings"},
    "operacional": {"read", "edit", "upload"},
    "visualizador": {"read"},
    "colaborador": {"read", "edit", "upload"},
}

CONTEXTS = {
    "hub": {
        "id": "hub",
        "label": "D3 Hub",
        "title": "Visão geral",
        "subtitle": "Entrada única para os contextos internos da D3.",
        "href": "/hub",
    },
    "gestao": {
        "id": "gestao",
        "label": "D3 Gestão",
        "title": "Gestão interna",
        "subtitle": "Financeiro e controles da própria D3.",
        "href": "/gestao/dashboard",
    },
    "operacoes": {
        "id": "operacoes",
        "label": "D3 Operações",
        "title": "Ferramentas operacionais",
        "subtitle": "Execução dos serviços financeiros prestados aos clientes.",
        "href": "/operacoes/dashboard",
    },
}

NAV_ITEMS = {
    "hub": [
        {"id": "hub", "label": "Hub", "href": "/hub"},
        {"id": "configuracoes", "label": "Configurações", "href": "/configuracoes"},
    ],
    "gestao": [
        {"id": "dashboard", "label": "Dashboard", "href": "/gestao/dashboard"},
        {"id": "fluxo_caixa", "label": "Fluxo de Caixa", "href": "/gestao/fluxo-caixa"},
        {"id": "cadastros", "label": "Cadastros", "href": "/gestao/cadastros"},
        {"id": "relatorios", "label": "Relatórios", "href": "/gestao/relatorios"},
        {"id": "configuracoes", "label": "Configurações", "href": "/configuracoes"},
    ],
    "operacoes": [
        {"id": "dashboard", "label": "Dashboard", "href": "/operacoes/dashboard"},
        {"id": "conciliacao", "label": "Conciliação", "href": "/operacoes/conciliacao"},
        {"id": "relatorios", "label": "Relatórios", "href": "/operacoes/relatorios"},
        {"id": "configuracoes", "label": "Configurações", "href": "/configuracoes"},
    ],
}


def normalize_role(role: str) -> str:
    return "operacional" if role == "colaborador" else role


def has_permission(user: User, permission: str) -> bool:
    return permission in ROLE_PERMISSIONS.get(normalize_role(user.role), {"read"})


def serialize_user(user: User) -> dict[str, object]:
    normalized = normalize_role(user.role)
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "role": normalized,
        "role_label": ROLE_LABELS.get(normalized, normalized.title()),
        "permissions": sorted(ROLE_PERMISSIONS.get(normalized, {"read"})),
        "is_active": user.is_active,
    }


def build_nav(area: str, active_module: str) -> list[dict[str, object]]:
    items = NAV_ITEMS.get(area, NAV_ITEMS["hub"])
    return [{**item, "active": item["id"] == active_module} for item in items]


def build_contexts(current_area: str | None) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for area_id in ("hub", "gestao", "operacoes"):
        item = CONTEXTS[area_id]
        items.append({**item, "active": area_id == current_area})
    return items


def seed_reference_data(db: Session) -> None:
    return None


def seed_cashflow_data(db: Session) -> None:
    return None


def load_history(db: Session, limit: int = 20) -> list[dict[str, object]]:
    rows = db.scalars(select(ExecutionLog).order_by(desc(ExecutionLog.created_at)).limit(limit)).all()
    return [
        {
            "executed_at": row.created_at.strftime("%d/%m/%Y %H:%M"),
            "user_name": row.user.name if row.user else "Usuário removido",
            "arquivo_vendas": row.arquivo_vendas,
            "arquivo_recebimentos": row.arquivo_recebimentos,
            "arquivo_saida": row.arquivo_saida,
            "qtde_total_processado": row.total_processado,
            "duracao_ms": row.duracao_ms,
            "status": row.status,
            "status_class": history_status_class(row.status),
            "detalhe": row.detalhe,
        }
        for row in rows
    ]


def history_status_class(status_value: str) -> str:
    normalized = status_value.strip().lower()
    if normalized in {"concluído", "concluido"}:
        return "success"
    if normalized == "timeout":
        return "warning"
    if normalized == "erro":
        return "error"
    return "neutral"


def load_users(db: Session) -> list[dict[str, object]]:
    users = db.scalars(select(User).order_by(User.role.asc(), User.name.asc())).all()
    return [serialize_user(user) for user in users]


def load_reference_lists(db: Session) -> dict[str, list[object]]:
    return {
        "stores": db.scalars(select(Store).where(Store.is_active.is_(True)).order_by(Store.name.asc())).all(),
        "accounts": db.scalars(select(BankAccount).where(BankAccount.is_active.is_(True)).order_by(BankAccount.name.asc())).all(),
        "categories": db.scalars(select(FinancialCategory).where(FinancialCategory.is_active.is_(True)).order_by(FinancialCategory.name.asc())).all(),
        "payment_methods": db.scalars(select(PaymentMethod).where(PaymentMethod.is_active.is_(True)).order_by(PaymentMethod.name.asc())).all(),
    }


def count_active_admins(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True))) or 0)


def transaction_query(db: Session):
    return select(FinancialTransaction).options(
        selectinload(FinancialTransaction.category),
        selectinload(FinancialTransaction.bank_account),
        selectinload(FinancialTransaction.payment_method),
        selectinload(FinancialTransaction.store),
        selectinload(FinancialTransaction.created_by),
    )


def permission_flags(user: User) -> dict[str, bool]:
    return {
        "can_upload": has_permission(user, "upload"),
        "can_edit": has_permission(user, "edit"),
        "read_only": not has_permission(user, "edit"),
        "is_admin": has_permission(user, "manage_users"),
    }
