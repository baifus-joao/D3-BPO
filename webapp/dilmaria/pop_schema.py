from __future__ import annotations

from datetime import date, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

DEFAULT_RESPONSIBILITY_DECLARATION = (
    "Declaro que li, compreendi e me responsabilizo pelo cumprimento integral "
    "deste Procedimento Operacional Padrao."
)


def validate_custom_logo_data_url(value: str | None) -> str | None:
    if not value:
        return None
    allowed_prefixes = (
        "data:image/png;base64,",
        "data:image/jpeg;base64,",
        "data:image/jpg;base64,",
    )
    if not any(value.startswith(prefix) for prefix in allowed_prefixes):
        raise ValueError("A logo personalizada deve ser PNG ou JPG em base64.")
    return value


class PopItem(BaseModel):
    numero: str | None = None
    descricao: str = Field(min_length=1)
    observacao: str | None = None


class PopSubsection(BaseModel):
    numero: str | None = None
    titulo: str = Field(min_length=1)
    materiais: list[str] = Field(default_factory=list)
    preparacao: list[str] = Field(default_factory=list)
    etapas_iniciais: list[str] = Field(default_factory=list)
    itens: list[PopItem] = Field(default_factory=list)

    @field_validator("materiais", "preparacao", "etapas_iniciais", mode="before")
    @classmethod
    def normalize_string_lists(cls, value):
        if value is None:
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]


class PopDefinition(BaseModel):
    termo: str = Field(min_length=1)
    descricao: str = Field(min_length=1)


class PopSection(BaseModel):
    numero: str
    titulo: str
    conteudo: list[str] = Field(default_factory=list)
    subsecoes: list[PopSubsection] = Field(default_factory=list)


class PopResponsibilityTerm(BaseModel):
    nome_responsavel: str = Field(min_length=1)
    declaracao: str = Field(default=DEFAULT_RESPONSIBILITY_DECLARATION, min_length=1)
    elaborado_por: str = Field(min_length=1)
    aprovado_por: str = Field(min_length=1)
    local: str = Field(min_length=1)
    data: date | None = None


class PopRequest(BaseModel):
    structure_key: str = Field(default="operacional_padrao", min_length=1)
    titulo: str = Field(min_length=1)
    codigo: str = Field(min_length=1)
    data: date | None = None
    custom_logo_data_url: str | None = None
    objetivo: str = Field(min_length=1)
    documentos_referencia: list[str] = Field(default_factory=list)
    local_aplicacao: str = Field(min_length=1)
    responsabilidade_execucao: str = Field(min_length=1)
    definicoes_siglas: list[PopDefinition] = Field(default_factory=list)
    atividades: list[PopSubsection] = Field(min_length=1)
    criterios_avaliacao: list[str] = Field(min_length=1)
    boas_praticas: list[str] = Field(min_length=1)
    erros_criticos: list[str] = Field(min_length=1)
    termo: PopResponsibilityTerm

    @field_validator(
        "documentos_referencia",
        "criterios_avaliacao",
        "boas_praticas",
        "erros_criticos",
        mode="before",
    )
    @classmethod
    def normalize_text_list(cls, value):
        if value is None:
            return []
        return [item.strip() for item in value if isinstance(item, str) and item.strip()]

    @field_validator(
        "titulo",
        "codigo",
        "objetivo",
        "local_aplicacao",
        "responsabilidade_execucao",
        mode="before",
    )
    @classmethod
    def strip_text_fields(cls, value: str):
        return value.strip() if isinstance(value, str) else value

    @field_validator("custom_logo_data_url")
    @classmethod
    def validate_custom_logo(cls, value: str | None):
        return validate_custom_logo_data_url(value)


class POP(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    titulo: str
    codigo: str
    revisao: str
    data: date
    secoes: list[PopSection]
    termo: PopResponsibilityTerm
    logo_path: str | None = None
    logo_data: bytes | None = None
    structure_key: str
    structure_name: str

    @computed_field
    @property
    def file_stub(self) -> str:
        normalized_code = self.codigo.replace("/", "-").replace("\\", "-").replace(" ", "-")
        normalized_rev = self.revisao.replace(".", "")
        return f"{normalized_code}-{normalized_rev}"


class PopGenerationResult(BaseModel):
    pop: POP
    document_bytes: bytes


class PopDraftPreview(BaseModel):
    draft: PopRequest
    refined_answers: dict[str, str] = Field(default_factory=dict)
    structure_key: str
    structure_name: str
    creation_mode: Literal["advanced", "express"]


class PopExecutionLogEntry(BaseModel):
    timestamp: datetime
    id: str
    titulo: str
    codigo: str
    revisao: str
    data: date
    structure_key: str | None = None
    structure_name: str | None = None


class PopHistorySummary(BaseModel):
    total_execucoes: int = 0
    total_codigos: int = 0
    ultima_execucao_em: datetime | None = None
    recentes: list[PopExecutionLogEntry] = Field(default_factory=list)


class PopDraftFormPayload(BaseModel):
    creation_mode: Literal["advanced", "express"] = "express"
    structure_key: str = ""
    titulo: str = ""
    codigo: str = ""
    data: date | None = None
    custom_logo_data_url: str | None = None
    answers: dict[str, str] = Field(default_factory=dict)
    raw_context: str | None = None
    termo: PopResponsibilityTerm = Field(
        default_factory=lambda: PopResponsibilityTerm(
            nome_responsavel="-",
            elaborado_por="-",
            aprovado_por="-",
            local="-",
        )
    )

    @field_validator("custom_logo_data_url")
    @classmethod
    def validate_draft_custom_logo(cls, value: str | None):
        return validate_custom_logo_data_url(value)


class PopDraftState(BaseModel):
    structure_key: str = ""
    creation_mode: Literal["advanced", "express"] = "express"
    custom_logo_name: str | None = None
    form_payload: PopDraftFormPayload | None = None
    preview: dict | None = None


class SavedPopDraft(BaseModel):
    titulo: str = ""
    codigo: str = ""
    structure_key: str = ""
    saved_at: datetime
    state: PopDraftState


class PopStructureQuestion(BaseModel):
    id: str
    label: str
    help_text: str
    placeholder: str
    required: bool = True


class PopStructureDescriptor(BaseModel):
    key: str
    name: str
    summary: str
    details: str
    allows_custom_logo: bool = False
    logo_formats: list[str] = Field(default_factory=list)
    logo_recommended_size: str | None = None
    logo_help_text: str | None = None
    best_for: list[str]
    sections_overview: list[str]
    activity_blueprint: list[str]
    questions: list[PopStructureQuestion]


class GuidedPopRequest(BaseModel):
    creation_mode: Literal["advanced", "express"] = "express"
    structure_key: str = Field(min_length=1)
    titulo: str = Field(min_length=1)
    codigo: str = Field(min_length=1)
    data: date | None = None
    custom_logo_data_url: str | None = None
    answers: dict[str, str] = Field(default_factory=dict)
    raw_context: str | None = None
    termo: PopResponsibilityTerm

    @field_validator("titulo", "codigo", "raw_context", mode="before")
    @classmethod
    def strip_header_fields(cls, value: str):
        return value.strip() if isinstance(value, str) else value

    @field_validator("custom_logo_data_url")
    @classmethod
    def validate_guided_custom_logo(cls, value: str | None):
        return validate_custom_logo_data_url(value)

    @model_validator(mode="after")
    def validate_by_mode(self):
        if self.creation_mode == "express" and not self.raw_context:
            raise ValueError("O modo express exige um contexto do POP em linguagem cotidiana.")
        if self.creation_mode == "advanced" and not self.answers:
            raise ValueError("O modo avancado exige respostas estruturadas para gerar o POP.")
        return self


class GeneratedPopContent(BaseModel):
    objetivo: str = Field(min_length=1)
    documentos_referencia: list[str] = Field(default_factory=list)
    local_aplicacao: str = Field(min_length=1)
    responsabilidade_execucao: str = Field(min_length=1)
    definicoes_siglas: list[PopDefinition] = Field(default_factory=list)
    atividades: list[PopSubsection] = Field(min_length=1)
    criterios_avaliacao: list[str] = Field(min_length=1)
    boas_praticas: list[str] = Field(min_length=1)
    erros_criticos: list[str] = Field(min_length=1)
