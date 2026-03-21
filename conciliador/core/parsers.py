from pathlib import Path
import re
import tempfile
import unicodedata
import zipfile

import pandas as pd


REPORT_MARKERS = {
    "vendas": ["data prevista de pagamento da venda", "comprovante de venda", "valor bruto da parcela"],
    "recebimentos": ["data de pagamento", "comprovante da venda", "bruto da parcela"],
}


def _normalize_rgb(value):
    text = str(value).strip()
    if not text:
        return "00000000"

    text = re.sub(r"[^0-9A-Fa-f]", "", text).upper()
    if len(text) == 6:
        return f"FF{text}"
    if len(text) == 8:
        return text
    if len(text) < 8:
        return text.zfill(8)
    return text[-8:]


def _sanitize_styles_xml(xml_text):
    def replace_rgb(match):
        value = match.group(1)
        normalized = _normalize_rgb(value)
        return match.group(0).replace(value, normalized)

    return re.sub(r'rgb="([^"]+)"', replace_rgb, xml_text)


def _build_sanitized_workbook(path):
    temp_file = tempfile.NamedTemporaryFile(suffix=Path(path).suffix, delete=False)
    temp_path = Path(temp_file.name)
    temp_file.close()

    with zipfile.ZipFile(path) as src, zipfile.ZipFile(temp_path, "w") as dst:
        for member in src.infolist():
            data = src.read(member.filename)
            if member.filename == "xl/styles.xml":
                text = data.decode("utf-8-sig", errors="replace")
                data = _sanitize_styles_xml(text).encode("utf-8")
            dst.writestr(member, data)

    return temp_path


def _read_excel_resilient(path, **kwargs):
    try:
        return pd.read_excel(path, **kwargs)
    except ValueError as exc:
        message = str(exc).lower()
        if "could not read stylesheet" not in message or Path(path).suffix.lower() != ".xlsx":
            raise

        temp_path = _build_sanitized_workbook(path)
        try:
            return pd.read_excel(temp_path, **kwargs)
        finally:
            temp_path.unlink(missing_ok=True)


def normalize_text(value):
    text = str(value).strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text)


def find_column(df, expected_name):
    target = normalize_text(expected_name)
    mapping = {normalize_text(col): col for col in df.columns}

    if target in mapping:
        return mapping[target]

    for normalized, original in mapping.items():
        if target in normalized:
            return original

    return None


def to_number(series):
    direct = pd.to_numeric(series, errors="coerce")
    text = (
        series.astype(str)
        .str.replace("R$", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(".", "", regex=False)
        .str.replace(",", ".", regex=False)
    )
    alternative = pd.to_numeric(text, errors="coerce")
    return direct.fillna(alternative)


def to_date(series):
    return pd.to_datetime(series, dayfirst=True, errors="coerce")


def parse_parcela(value):
    text = str(value).strip()
    if text in {"", "-", "nan", "None"}:
        return 1, 1, "1/1", True

    match = re.match(r"^(\d+)\s*(?:de|/)\s*(\d+)$", text, flags=re.IGNORECASE)
    if not match:
        return None, None, text, False

    number = int(match.group(1))
    total = int(match.group(2))
    valid = number > 0 and total > 0 and number <= total
    token = f"{number}/{total}"
    return number, total, token, valid


def _find_header_index(raw, required_markers):
    for i in range(len(raw)):
        row = raw.iloc[i].astype(str).map(normalize_text)
        if all((row.str.contains(marker, regex=False)).any() for marker in required_markers):
            return i
    return None


def detect_report_type(path):
    raw = _read_excel_resilient(path, header=None)
    if raw.dropna(how="all").empty:
        return None

    matches = []
    for report_type, markers in REPORT_MARKERS.items():
        if _find_header_index(raw, markers) is not None:
            matches.append(report_type)

    if len(matches) == 1:
        return matches[0]
    return None


def read_report_with_header(path, required_markers):
    raw = _read_excel_resilient(path, header=None)
    if raw.dropna(how="all").empty:
        raise ValueError(f"Arquivo vazio: {Path(path).name}.")

    header_idx = _find_header_index(raw, required_markers)

    if header_idx is None:
        raise ValueError(f"Nao foi possivel localizar o cabecalho em {Path(path).name}.")

    header = raw.iloc[header_idx].tolist()
    data = raw.iloc[header_idx + 1 :].copy()
    data.columns = header
    data = data.dropna(how="all")
    return data


def load_vendas(path_vendas):
    df = read_report_with_header(
        path_vendas,
        required_markers=["data da venda", "comprovante", "parcelas"],
    )
    original = df.copy()

    col_comprovante = find_column(df, "Comprovante de venda")
    col_parcelas = find_column(df, "Parcelas")
    col_data_venda = find_column(df, "Data da venda")
    col_data_prevista = find_column(df, "Data prevista de pagamento da venda")
    col_valor_parcela = find_column(df, "Valor bruto da parcela")
    col_valor_liquido = find_column(df, "Valor liquido da parcela")
    col_status_venda = find_column(df, "Status")
    col_status_pagamento = find_column(df, "Status do pagamento da venda")

    required = [col_comprovante, col_parcelas, col_data_venda, col_valor_parcela]
    if not all(required):
        raise ValueError("Colunas essenciais de vendas nao encontradas.")

    base = pd.DataFrame()
    base["Comprovante"] = df[col_comprovante].astype(str).str.strip()
    base["Parcela Texto"] = df[col_parcelas].astype(str).str.strip()
    base["Data Venda"] = to_date(df[col_data_venda])
    base["Data Prevista"] = to_date(df[col_data_prevista]) if col_data_prevista else pd.NaT
    base["Valor Parcela Venda"] = to_number(df[col_valor_parcela])
    base["Valor Liquido Venda"] = to_number(df[col_valor_liquido]) if col_valor_liquido else pd.NA
    base["Status Venda"] = df[col_status_venda].astype(str).str.strip() if col_status_venda else ""
    base["Status Pagamento Venda"] = (
        df[col_status_pagamento].astype(str).str.strip() if col_status_pagamento else ""
    )

    parsed = base["Parcela Texto"].map(parse_parcela)
    base["Numero Parcela"] = parsed.map(lambda x: x[0])
    base["Total Parcelas"] = parsed.map(lambda x: x[1])
    base["Parcela"] = parsed.map(lambda x: x[2])
    base["Parcela Valida"] = parsed.map(lambda x: x[3])

    base.loc[base["Comprovante"].isin(["", "nan", "None"]), "Comprovante"] = pd.NA
    base["Chave Parcela"] = base.apply(
        lambda r: (
            f"{r['Comprovante']}-{int(r['Numero Parcela'])}/{int(r['Total Parcelas'])}"
            if pd.notna(r["Comprovante"])
            and pd.notna(r["Numero Parcela"])
            and pd.notna(r["Total Parcelas"])
            and r["Parcela Valida"]
            else pd.NA
        ),
        axis=1,
    )
    base["ordem_chave"] = base.groupby("Chave Parcela", dropna=False).cumcount() + 1
    return base, original


def load_recebimentos(path_recebimentos):
    df = read_report_with_header(
        path_recebimentos,
        required_markers=["data de pagamento", "comprovante", "parcelas"],
    )
    original = df.copy()

    col_comprovante = find_column(df, "Comprovante da venda")
    col_parcelas = find_column(df, "Parcelas")
    col_data_pagamento = find_column(df, "Data de pagamento")
    col_codigo_pagamento = find_column(df, "Codigo de pagamento")
    col_bruto_parcela = find_column(df, "Bruto da parcela")
    col_liquido = find_column(df, "Liquido da venda")
    col_desconto = find_column(df, "Desconto MDR")
    col_tipo_pagamento = find_column(df, "Tipo de pagamento")

    required = [col_comprovante, col_parcelas, col_data_pagamento, col_bruto_parcela]
    if not all(required):
        raise ValueError("Colunas essenciais de recebimentos nao encontradas.")

    base = pd.DataFrame()
    base["Comprovante"] = df[col_comprovante].astype(str).str.strip()
    base["Parcela Texto"] = df[col_parcelas].astype(str).str.strip()
    base["Data Pagamento"] = to_date(df[col_data_pagamento])
    base["Codigo Pagamento"] = (
        df[col_codigo_pagamento].astype(str).str.strip() if col_codigo_pagamento else ""
    )
    base["Valor Parcela Recebida"] = to_number(df[col_bruto_parcela])
    base["Valor Liquido Recebido"] = to_number(df[col_liquido]) if col_liquido else pd.NA
    base["Desconto MDR Recebido"] = to_number(df[col_desconto]) if col_desconto else pd.NA
    base["Tipo Pagamento"] = df[col_tipo_pagamento].astype(str).str.strip() if col_tipo_pagamento else ""

    parsed = base["Parcela Texto"].map(parse_parcela)
    base["Numero Parcela"] = parsed.map(lambda x: x[0])
    base["Total Parcelas"] = parsed.map(lambda x: x[1])
    base["Parcela"] = parsed.map(lambda x: x[2])
    base["Parcela Valida"] = parsed.map(lambda x: x[3])

    base.loc[base["Comprovante"].isin(["", "nan", "None"]), "Comprovante"] = pd.NA
    base["Chave Parcela"] = base.apply(
        lambda r: (
            f"{r['Comprovante']}-{int(r['Numero Parcela'])}/{int(r['Total Parcelas'])}"
            if pd.notna(r["Comprovante"])
            and pd.notna(r["Numero Parcela"])
            and pd.notna(r["Total Parcelas"])
            and r["Parcela Valida"]
            else pd.NA
        ),
        axis=1,
    )
    base["ordem_chave"] = base.groupby("Chave Parcela", dropna=False).cumcount() + 1
    return base, original


def find_file_by_keyword(keyword, directory="."):
    files = []
    for pattern in ("*.xlsx", "*.xls"):
        files.extend(
            p
            for p in Path(directory).glob(pattern)
            if keyword in normalize_text(p.name)
            and "conciliacao" not in normalize_text(p.name)
            and "parcelas_geradas" not in normalize_text(p.name)
        )
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    if not files:
        raise FileNotFoundError(f"Nenhum arquivo Excel com '{keyword}' foi encontrado.")

    return files[0]
