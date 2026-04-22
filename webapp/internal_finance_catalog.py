from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import FinancialCategory


INTERNAL_FINANCE_CATEGORY_BLUEPRINT = (
    {
        "name": "Operacional",
        "display_name": "Operacional",
        "type": "SAIDA",
        "color": "#ff8a65",
        "subcategories": [
            "Aluguel",
            "Condomínio",
            "IPTU",
            "Energia elétrica",
            "Água",
            "Internet",
            "Telefone",
            "Limpeza",
            "Segurança",
        ],
    },
    {
        "name": "Compras / Estoque",
        "display_name": "Compras / Estoque",
        "type": "SAIDA",
        "color": "#ff9f40",
        "subcategories": [
            "Compra de mercadorias",
            "Reposição de estoque",
            "Bonificações concedidas",
            "Perdas / avarias",
            "Ajuste de estoque",
        ],
    },
    {
        "name": "Logística",
        "display_name": "Logística",
        "type": "SAIDA",
        "color": "#f5b041",
        "subcategories": [
            "Frete",
            "Combustível",
            "Manutenção de veículos",
            "Pedágios",
            "Seguro de transporte",
        ],
    },
    {
        "name": "Pessoal",
        "display_name": "Pessoal",
        "type": "SAIDA",
        "color": "#ec7063",
        "subcategories": [
            "Salários",
            "Vale transporte",
            "Vale alimentação",
            "Comissão",
            "Bonificação",
            "Freelancers",
            "Encargos trabalhistas",
            "Rescisões",
        ],
    },
    {
        "name": "Administrativo",
        "display_name": "Administrativo",
        "type": "SAIDA",
        "color": "#af7ac5",
        "subcategories": [
            "Material de escritório",
            "Software / sistemas",
            "Assinaturas (SaaS)",
            "Consultorias",
            "Honorários contábeis",
            "Jurídico",
        ],
    },
    {
        "name": "Marketing e Comercial",
        "display_name": "Marketing e Comercial",
        "type": "SAIDA",
        "color": "#f06292",
        "subcategories": [
            "Tráfego pago",
            "Redes sociais",
            "Design / criativos",
            "Impressos",
            "Promoções",
            "Parcerias",
        ],
    },
    {
        "name": "Financeiro",
        "display_name": "Financeiro",
        "type": "SAIDA",
        "color": "#e57373",
        "subcategories": [
            "Taxas bancárias",
            "Juros pagos",
            "Multas",
            "Tarifas de cartão",
            "Antecipação de recebíveis",
        ],
    },
    {
        "name": "Manutenção",
        "display_name": "Manutenção",
        "type": "SAIDA",
        "color": "#a1887f",
        "subcategories": [
            "Manutenção predial",
            "Equipamentos",
            "TI / informática",
        ],
    },
    {
        "name": "Transferências internas - Saídas",
        "display_name": "Transferências internas",
        "type": "SAIDA",
        "color": "#90a4ae",
        "subcategories": [
            "Envio para lojas",
            "Ajuste entre caixas",
            "Transferência entre contas",
        ],
    },
    {
        "name": "Outros",
        "display_name": "Outros",
        "type": "SAIDA",
        "color": "#8d6e63",
        "subcategories": [
            "Despesas diversas",
            "Doações",
            "Investimentos",
        ],
    },
    {
        "name": "Vendas",
        "display_name": "Vendas",
        "type": "ENTRADA",
        "color": "#22ffc4",
        "subcategories": [
            "Venda PDV - Dinheiro",
            "Venda PDV - Débito",
            "Venda PDV - Crédito à vista",
            "Venda PDV - Crédito parcelado",
            "Venda online",
        ],
    },
    {
        "name": "Recebimentos financeiros",
        "display_name": "Recebimentos financeiros",
        "type": "ENTRADA",
        "color": "#26c6da",
        "subcategories": [
            "PIX recebido",
            "Transferência recebida",
            "Depósito",
        ],
    },
    {
        "name": "Operadoras de cartão",
        "display_name": "Operadoras de cartão",
        "type": "ENTRADA",
        "color": "#42a5f5",
        "subcategories": [
            "Recebimento débito",
            "Recebimento crédito",
            "Recebimento parcelado",
            "Antecipação de recebíveis",
        ],
    },
    {
        "name": "Transferências internas - Entradas",
        "display_name": "Transferências internas",
        "type": "ENTRADA",
        "color": "#64b5f6",
        "subcategories": [
            "Recebimento entre lojas",
            "Ajuste de caixa",
            "Transferência entre contas",
        ],
    },
    {
        "name": "Outros recebimentos",
        "display_name": "Outros recebimentos",
        "type": "ENTRADA",
        "color": "#4dd0e1",
        "subcategories": [
            "Reembolso",
            "Devolução de fornecedor",
            "Bonificação recebida",
            "Indenizações",
        ],
    },
    {
        "name": "Comercial / Serviços",
        "display_name": "Comercial / Serviços",
        "type": "ENTRADA",
        "color": "#26a69a",
        "subcategories": [
            "Prestação de serviços",
            "Consultoria",
            "Treinamentos",
            "Projetos",
        ],
    },
    {
        "name": "Investimentos / Extras",
        "display_name": "Investimentos / Extras",
        "type": "ENTRADA",
        "color": "#66bb6a",
        "subcategories": [
            "Rendimentos",
            "Juros recebidos",
            "Aportes",
        ],
    },
)


BLUEPRINT_BY_NAME = {item["name"]: item for item in INTERNAL_FINANCE_CATEGORY_BLUEPRINT}


def display_financial_category(name: str) -> str:
    item = BLUEPRINT_BY_NAME.get(name)
    if item:
        return str(item["display_name"])
    return name


def iter_predefined_categories() -> Iterable[dict[str, object]]:
    return INTERNAL_FINANCE_CATEGORY_BLUEPRINT


def predefined_subcategory_map() -> dict[str, list[str]]:
    return {
        str(item["name"]): list(item["subcategories"])
        for item in INTERNAL_FINANCE_CATEGORY_BLUEPRINT
    }


def seed_internal_finance_categories(db: Session) -> None:
    existing = {
        name
        for name in db.scalars(select(FinancialCategory.name)).all()
    }
    changed = False
    for item in INTERNAL_FINANCE_CATEGORY_BLUEPRINT:
        if str(item["name"]) in existing:
            continue
        db.add(
            FinancialCategory(
                name=str(item["name"]),
                type=str(item["type"]),
                color=str(item["color"]),
                is_active=True,
            )
        )
        changed = True
    if changed:
        db.commit()
