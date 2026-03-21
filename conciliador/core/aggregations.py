import pandas as pd

from .parsers import normalize_text


def reconcile(vendas, recebimentos):
    merged = vendas.merge(
        recebimentos,
        on=["Chave Parcela", "ordem_chave"],
        how="outer",
        suffixes=("_venda", "_receb"),
    )

    merged["Tem Venda"] = merged["Comprovante_venda"].notna()
    merged["Tem Recebimento"] = merged["Comprovante_receb"].notna()
    merged["Diferenca Bruta"] = merged["Valor Parcela Recebida"] - merged["Valor Parcela Venda"]
    merged["Diferenca Liquida"] = merged["Valor Liquido Recebido"] - merged["Valor Liquido Venda"]
    merged["Atraso Dias"] = (merged["Data Pagamento"] - merged["Data Prevista"]).dt.days

    def classify(row):
        if row["Tem Venda"] and row["Tem Recebimento"]:
            dif_bruta = row["Diferenca Bruta"]
            dif_liq = row["Diferenca Liquida"]
            ok_bruta = pd.notna(dif_bruta) and abs(dif_bruta) <= 0.01
            ok_liq = pd.isna(dif_liq) or abs(dif_liq) <= 0.01
            if ok_bruta and ok_liq:
                return "Conciliado"
            return "Divergente"
        if row["Tem Venda"] and not row["Tem Recebimento"]:
            return "Somente Vendas"
        if row["Tem Recebimento"] and not row["Tem Venda"]:
            return "Somente Recebimentos"
        return "Indefinido"

    merged["Status Conciliacao"] = merged.apply(classify, axis=1)
    return merged


def daily_received(recebimentos):
    base = recebimentos[recebimentos["Data Pagamento"].notna()].copy()
    daily = (
        base.groupby("Data Pagamento", as_index=False)
        .agg(
            Quantidade_Lancamentos=("Comprovante", "size"),
            Valor_Bruto_Recebido=("Valor Parcela Recebida", "sum"),
            Valor_Liquido_Recebido=("Valor Liquido Recebido", "sum"),
            Desconto_MDR=("Desconto MDR Recebido", "sum"),
        )
        .sort_values("Data Pagamento")
    )
    daily["Ano"] = daily["Data Pagamento"].dt.year
    daily["Mes"] = daily["Data Pagamento"].dt.month
    daily["Ano-Mes"] = daily["Data Pagamento"].dt.strftime("%Y-%m")
    return daily.rename(columns={"Data Pagamento": "Data"})


def forecast_from_sales(vendas):
    base = vendas[vendas["Data Prevista"].notna()].copy()
    forecast = (
        base.groupby("Data Prevista", as_index=False)
        .agg(
            Quantidade_Parcelas=("Chave Parcela", "size"),
            Valor_Bruto_Previsto=("Valor Parcela Venda", "sum"),
            Valor_Liquido_Previsto=("Valor Liquido Venda", "sum"),
        )
        .sort_values("Data Prevista")
    )
    forecast["Ano"] = forecast["Data Prevista"].dt.year
    forecast["Mes"] = forecast["Data Prevista"].dt.month
    forecast["Ano-Mes"] = forecast["Data Prevista"].dt.strftime("%Y-%m")
    return forecast.rename(columns={"Data Prevista": "Data"})


def paid_sales_missing_receipt(vendas, recebimentos):
    received_keys = set(recebimentos["Chave Parcela"].dropna().astype(str))
    base = vendas.copy()

    status_paid = (
        base["Status Pagamento Venda"]
        .astype(str)
        .map(normalize_text)
        .str.contains("paga", na=False)
    )
    missing = ~base["Chave Parcela"].astype(str).isin(received_keys)
    out = base[status_paid & missing].copy()
    out["Motivo"] = "Pagamento marcado como pago em vendas, mas sem registro no recebimento."

    cols = [
        "Comprovante",
        "Parcela",
        "Data Venda",
        "Data Prevista",
        "Valor Parcela Venda",
        "Valor Liquido Venda",
        "Status Venda",
        "Status Pagamento Venda",
        "Chave Parcela",
        "Motivo",
    ]
    return out[cols].sort_values(["Data Prevista", "Comprovante"], na_position="last")
