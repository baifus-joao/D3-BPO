from dataclasses import dataclass
from pathlib import Path

from .core.aggregations import (
    daily_received,
    forecast_from_sales,
    paid_sales_missing_receipt,
)
from .core.parsers import detect_report_type, find_file_by_keyword, load_recebimentos, load_vendas
from .core.writer import save_objective_report


class ConciliationUserError(Exception):
    def __init__(self, message, file_path=None):
        super().__init__(message)
        self.file_path = Path(file_path) if file_path else None


def _raise_file_error(path: Path, label: str, exc: Exception) -> None:
    message = str(exc).lower()
    actual_type = None
    try:
        actual_type = detect_report_type(path)
    except Exception:
        actual_type = None

    expected_type = label
    if actual_type and actual_type != expected_type:
        raise ConciliationUserError(
            f"O arquivo '{path.name}' foi enviado em {label}, mas parece ser um relatorio de {actual_type}. "
            "Confira os campos e tente novamente.",
            file_path=path,
        )

    if "arquivo vazio" in message or "worksheet is empty" in message:
        raise ConciliationUserError(
            f"O arquivo '{path.name}' informado em {label} esta vazio. Exporte o relatorio novamente e tente outra vez.",
            file_path=path,
        ) from exc

    if "colunas essenciais de vendas nao encontradas" in message:
        raise ConciliationUserError(
            f"O arquivo '{path.name}' nao tem as colunas obrigatorias do relatorio de vendas. "
            "Confira se a exportacao foi feita no layout correto.",
            file_path=path,
        ) from exc

    if "colunas essenciais de recebimentos nao encontradas" in message:
        raise ConciliationUserError(
            f"O arquivo '{path.name}' nao tem as colunas obrigatorias do relatorio de recebimentos. "
            "Confira se a exportacao foi feita no layout correto.",
            file_path=path,
        ) from exc

    if "nao foi possivel localizar o cabecalho" in message:
        raise ConciliationUserError(
            f"O arquivo '{path.name}' nao corresponde ao layout esperado em {label}. "
            "Verifique se voce exportou o relatorio correto.",
            file_path=path,
        ) from exc

    if (
        "could not read stylesheet" in message
        or "badzipfile" in message
        or "file is not a zip file" in message
        or "could not determine file format" in message
    ):
        raise ConciliationUserError(
            f"O arquivo '{path.name}' informado em {label} parece estar corrompido ou com estrutura invalida. "
            "Abra e salve novamente a planilha, ou gere uma nova exportacao.",
            file_path=path,
        ) from exc

    raise ConciliationUserError(
        f"O arquivo '{path.name}' informado em {label} nao esta no formato esperado para a conciliacao. "
        "Revise o arquivo e tente novamente.",
        file_path=path,
    ) from exc


@dataclass
class ConciliationResult:
    arquivo_vendas: Path
    arquivo_recebimentos: Path
    arquivo_saida: Path
    qtde_linhas_vendas: int
    qtde_linhas_recebimentos: int
    qtde_recebido_por_dia: int
    qtde_previsao: int
    qtde_vendas_pagas_sem_recebimento: int


def _validate_excel_input(path: Path, label: str) -> Path:
    if not path.exists():
        raise ConciliationUserError(f"O arquivo de {label} nao foi encontrado:\n{path}", file_path=path)

    if path.suffix.lower() not in {".xlsx", ".xls"}:
        raise ConciliationUserError(
            f"O arquivo de {label} precisa ser uma planilha Excel (.xlsx ou .xls).\nArquivo informado: {path.name}",
            file_path=path,
        )

    return path


def _validate_output_path(output_path: Path) -> Path:
    if output_path.suffix.lower() != ".xlsx":
        raise ConciliationUserError("O arquivo de saida deve terminar com .xlsx.")

    output_dir = output_path.parent
    if output_dir and not output_dir.exists():
        raise ConciliationUserError(
            f"A pasta de destino nao existe:\n{output_dir}\n\nEscolha outra pasta para salvar a conciliacao."
        )

    return output_path


def run_conciliation(
    output_path="conciliacao_objetiva.xlsx",
    vendas_path=None,
    recebimentos_path=None,
    workdir=".",
):
    if vendas_path is None:
        vendas_path = find_file_by_keyword("vendas", directory=workdir)
    if recebimentos_path is None:
        recebimentos_path = find_file_by_keyword("recebimentos", directory=workdir)

    vendas_path = Path(vendas_path)
    recebimentos_path = Path(recebimentos_path)
    output_path = Path(output_path)

    if vendas_path.resolve() == recebimentos_path.resolve():
        raise ConciliationUserError(
            "O mesmo arquivo foi informado em vendas e recebimentos. Selecione um relatorio diferente em cada campo."
        )

    vendas_path = _validate_excel_input(vendas_path, label="vendas")
    recebimentos_path = _validate_excel_input(recebimentos_path, label="recebimentos")
    output_path = _validate_output_path(output_path)

    try:
        vendas, vendas_original = load_vendas(vendas_path)
    except Exception as exc:
        _raise_file_error(vendas_path, "vendas", exc)

    try:
        recebimentos, receb_original = load_recebimentos(recebimentos_path)
    except Exception as exc:
        _raise_file_error(recebimentos_path, "recebimentos", exc)

    received_daily = daily_received(recebimentos)
    forecast_sales = forecast_from_sales(vendas)
    paid_missing = paid_sales_missing_receipt(vendas, recebimentos)

    output = save_objective_report(
        vendas_original=vendas_original,
        receb_original=receb_original,
        received_daily=received_daily,
        forecast_sales=forecast_sales,
        paid_missing=paid_missing,
        output_path=output_path,
    )

    return ConciliationResult(
        arquivo_vendas=vendas_path,
        arquivo_recebimentos=recebimentos_path,
        arquivo_saida=output,
        qtde_linhas_vendas=len(vendas_original),
        qtde_linhas_recebimentos=len(receb_original),
        qtde_recebido_por_dia=len(received_daily),
        qtde_previsao=len(forecast_sales),
        qtde_vendas_pagas_sem_recebimento=len(paid_missing),
    )
