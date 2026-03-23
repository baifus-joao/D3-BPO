from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal

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
        "title": "Visao geral",
        "subtitle": "Entrada unica para os contextos da D3.",
        "href": "/hub",
    },
    "gestao": {
        "id": "gestao",
        "label": "D3 Gestao",
        "title": "Gestao",
        "subtitle": "Financeiro e controles internos.",
        "href": "/gestao/dashboard",
    },
    "operacoes": {
        "id": "operacoes",
        "label": "D3 Operacoes",
        "title": "Operacoes",
        "subtitle": "Execucao dos servicos para clientes.",
        "href": "/operacoes/dashboard",
    },
}

NAV_ITEMS = {
    "hub": [
        {"id": "hub", "label": "Hub", "href": "/hub"},
        {"id": "relatorios", "label": "Relatorios", "href": "/relatorios"},
        {"id": "configuracoes", "label": "Configuracoes", "href": "/configuracoes"},
    ],
    "gestao": [
        {"id": "dashboard", "label": "Dashboard", "href": "/gestao/dashboard"},
        {"id": "fluxo_caixa", "label": "Fluxo de caixa", "href": "/gestao/fluxo-caixa"},
        {"id": "cadastros", "label": "Cadastros", "href": "/gestao/cadastros"},
        {"id": "relatorios", "label": "Relatorios", "href": "/gestao/relatorios"},
        {"id": "configuracoes", "label": "Configuracoes", "href": "/configuracoes"},
    ],
    "operacoes": [
        {"id": "dashboard", "label": "Dashboard", "href": "/operacoes/dashboard"},
        {"id": "conciliacao", "label": "Conciliacao", "href": "/operacoes/conciliacao"},
        {"id": "relatorios", "label": "Relatorios", "href": "/operacoes/relatorios"},
        {"id": "configuracoes", "label": "Configuracoes", "href": "/configuracoes"},
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
            "user_name": row.user.name if row.user else "Usuario removido",
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
    if normalized in {"concluido", "concluído"}:
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


def report_catalog(area: str) -> list[dict[str, str]]:
    if area == "management":
        return [
            {"label": "Fluxo de caixa", "status": "Ativo", "description": "Entradas, saidas, saldo e leitura por conta."},
            {"label": "Cadastros", "status": "Base", "description": "Cobertura para categorias, contas, lojas e formas."},
            {"label": "Novos modulos", "status": "Em breve", "description": "Espaco para fiscal, compras, metas e novos paineis."},
        ]
    return [
        {"label": "Conciliacao", "status": "Ativo", "description": "Execucoes, falhas, volume e tempo medio."},
        {"label": "Equipe", "status": "Base", "description": "Produtividade por usuario e historico operacional."},
        {"label": "Novos modulos", "status": "Em breve", "description": "Espaco para SLA, filas, auditoria e novas rotinas."},
    ]


def load_management_reports(db: Session) -> dict[str, object]:
    items = db.scalars(
        transaction_query(db).order_by(FinancialTransaction.transaction_date.desc(), FinancialTransaction.id.desc())
    ).all()

    entradas_realizadas = sum(
        (Decimal(item.amount) for item in items if item.type == "ENTRADA" and item.status == "realizado"),
        Decimal("0"),
    )
    saidas_realizadas = sum(
        (Decimal(item.amount) for item in items if item.type == "SAIDA" and item.status == "realizado"),
        Decimal("0"),
    )
    previsto_aberto = sum(
        (Decimal(item.amount) for item in items if item.status == "previsto"),
        Decimal("0"),
    )
    resultado = entradas_realizadas - saidas_realizadas

    monthly_totals: dict[str, dict[str, Decimal]] = defaultdict(lambda: {"ENTRADA": Decimal("0"), "SAIDA": Decimal("0")})
    for item in sorted(items, key=lambda row: row.transaction_date):
        key = item.transaction_date.strftime("%m/%Y")
        monthly_totals[key][item.type] += Decimal(item.amount)
    monthly_rows = []
    for key, values in list(monthly_totals.items())[-6:]:
        monthly_rows.append(
            {
                "label": key,
                "entradas": values["ENTRADA"],
                "saidas": values["SAIDA"],
                "resultado": values["ENTRADA"] - values["SAIDA"],
            }
        )

    category_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    account_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    recent_rows = []
    for item in items:
        if item.type == "SAIDA":
            label = item.category.name if item.category else "Sem categoria"
            category_totals[label] += Decimal(item.amount)
        account_label = item.bank_account.name if item.bank_account else "Sem conta"
        signed = Decimal(item.amount) if item.type == "ENTRADA" else -Decimal(item.amount)
        account_totals[account_label] += signed

    for item in items[:8]:
        recent_rows.append(
            {
                "date": item.transaction_date.strftime("%d/%m/%Y"),
                "description": item.description,
                "category": item.category.name if item.category else "-",
                "status": item.status,
                "status_class": "success" if item.status == "realizado" else "warning",
                "amount": Decimal(item.amount) if item.type == "ENTRADA" else -Decimal(item.amount),
            }
        )

    top_categories = [
        {"label": label, "value": value}
        for label, value in sorted(category_totals.items(), key=lambda pair: pair[1], reverse=True)[:6]
    ]
    account_rows = [
        {"label": label, "value": value}
        for label, value in sorted(account_totals.items(), key=lambda pair: pair[1], reverse=True)
    ]

    return {
        "report_type": "management",
        "report_catalog": report_catalog("management"),
        "report_sections": [
            {"label": "Fluxo de caixa", "caption": "Resumo mensal, top categorias e saldo por conta."},
            {"label": "Movimentacoes", "caption": "Ultimos lancamentos para leitura rapida."},
            {"label": "Escala", "caption": "Pronto para receber novos blocos por modulo."},
        ],
        "metrics": [
            {"label": "Entradas realizadas", "value": entradas_realizadas, "tone": "success"},
            {"label": "Saidas realizadas", "value": saidas_realizadas, "tone": "danger"},
            {"label": "Previsto em aberto", "value": previsto_aberto, "tone": "warning"},
            {"label": "Resultado", "value": resultado, "tone": "neutral"},
        ],
        "monthly_rows": monthly_rows,
        "top_categories": top_categories,
        "account_rows": account_rows,
        "recent_rows": recent_rows,
    }


def load_operational_reports(db: Session) -> dict[str, object]:
    logs = db.scalars(
        select(ExecutionLog).options(selectinload(ExecutionLog.user)).order_by(desc(ExecutionLog.created_at))
    ).all()

    total = len(logs)
    success_count = sum(1 for item in logs if item.status.strip().lower() in {"concluido", "concluído"})
    error_count = sum(1 for item in logs if item.status.strip().lower() == "erro")
    avg_duration = int(sum(item.duracao_ms for item in logs) / total) if total else 0
    success_rate = (success_count / total * 100) if total else 0

    by_user: dict[str, dict[str, int]] = defaultdict(lambda: {"runs": 0, "processed": 0, "errors": 0})
    recent_errors = []
    for item in logs:
        user_name = item.user.name if item.user else "Usuario removido"
        by_user[user_name]["runs"] += 1
        by_user[user_name]["processed"] += item.total_processado
        if item.status.strip().lower() == "erro":
            by_user[user_name]["errors"] += 1
            if len(recent_errors) < 6:
                recent_errors.append(
                    {
                        "executed_at": item.created_at.strftime("%d/%m/%Y %H:%M"),
                        "user_name": user_name,
                        "detail": item.detalhe or "Falha sem detalhe.",
                    }
                )

    user_rows = [
        {"label": label, "runs": value["runs"], "processed": value["processed"], "errors": value["errors"]}
        for label, value in sorted(by_user.items(), key=lambda pair: pair[1]["runs"], reverse=True)
    ]

    recent_runs = [
        {
            "executed_at": item.created_at.strftime("%d/%m/%Y %H:%M"),
            "user_name": item.user.name if item.user else "Usuario removido",
            "status": item.status,
            "status_class": history_status_class(item.status),
            "processed": item.total_processado,
            "duration": item.duracao_ms,
        }
        for item in logs[:8]
    ]

    return {
        "report_type": "operations",
        "report_catalog": report_catalog("operations"),
        "report_sections": [
            {"label": "Conciliacao", "caption": "Execucoes, taxa de sucesso e tempo medio."},
            {"label": "Equipe", "caption": "Volume por usuario e leitura dos erros."},
            {"label": "Escala", "caption": "Pronto para SLA, auditoria e novas rotinas."},
        ],
        "metrics": [
            {"label": "Execucoes", "value": total, "tone": "neutral", "kind": "count"},
            {"label": "Concluidas", "value": success_count, "tone": "success", "kind": "count"},
            {"label": "Taxa de sucesso", "value": round(success_rate, 1), "tone": "success", "kind": "percent"},
            {"label": "Tempo medio", "value": avg_duration, "tone": "warning", "kind": "duration"},
        ],
        "user_rows": user_rows,
        "recent_errors": recent_errors,
        "recent_runs": recent_runs,
        "error_count": error_count,
    }
