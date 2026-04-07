from __future__ import annotations

from webapp.dilmaria.exceptions import AgentExecutionError
from webapp.dilmaria.pop_schema import PopStructureDescriptor, PopStructureQuestion


COMMON_QUESTIONS = [
    PopStructureQuestion(
        id="contexto_operacional",
        label="Contexto operacional",
        help_text="Explique o processo, o ambiente e o motivo do POP existir.",
        placeholder="Ex.: Procedimento usado na preparacao da sala clinica antes e apos o atendimento.",
    ),
    PopStructureQuestion(
        id="documentos_referencia",
        label="Documentos de referencia",
        help_text="Liste manuais, normas ou POPs relacionados. Um item por linha.",
        placeholder="Ex.: Manual de biosseguranca\nInstrucao interna de limpeza",
    ),
    PopStructureQuestion(
        id="local_aplicacao",
        label="Local de aplicacao",
        help_text="Informe onde o POP sera executado.",
        placeholder="Ex.: Salas clinicas, recepcao, setor financeiro.",
    ),
    PopStructureQuestion(
        id="responsaveis_execucao",
        label="Responsaveis pela execucao",
        help_text="Informe cargos ou perfis que executam o processo.",
        placeholder="Ex.: Auxiliar de saude bucal, recepcionista, gestor da unidade.",
    ),
    PopStructureQuestion(
        id="definicoes_siglas",
        label="Definicoes e siglas",
        help_text="Opcional. Use um item por linha no formato TERMO: descricao.",
        placeholder="Ex.: EPI: Equipamento de protecao individual",
        required=False,
    ),
    PopStructureQuestion(
        id="materiais_recursos",
        label="Materiais e recursos",
        help_text="Liste materiais, sistemas, ferramentas ou insumos necessarios.",
        placeholder="Ex.: Luva, sistema ERP, checklist impresso.",
    ),
    PopStructureQuestion(
        id="preparacao_inicial",
        label="Preparacao inicial",
        help_text="Explique o que precisa estar pronto antes de executar o processo.",
        placeholder="Ex.: Conferir disponibilidade de insumos, acessar sistema, validar agenda.",
    ),
    PopStructureQuestion(
        id="fluxo_atividades",
        label="Fluxo das atividades",
        help_text="Descreva as etapas principais do processo em ordem. Um passo por linha.",
        placeholder="Ex.: Higienizar superficies\nRegistrar checklist\nLiberar sala",
    ),
    PopStructureQuestion(
        id="criterios_avaliacao",
        label="Criterios de avaliacao",
        help_text="Defina como verificar se o procedimento foi executado corretamente.",
        placeholder="Ex.: Checklist completo e assinado\nAmbiente liberado sem pendencias",
    ),
    PopStructureQuestion(
        id="boas_praticas",
        label="Boas praticas e conformidade",
        help_text="Liste cuidados, conformidades e comportamentos esperados.",
        placeholder="Ex.: Registrar nao conformidades imediatamente",
    ),
    PopStructureQuestion(
        id="erros_criticos",
        label="Erros criticos ou falhas proibidas",
        help_text="Liste o que nao pode acontecer durante a execucao.",
        placeholder="Ex.: Iniciar atendimento sem limpeza concluida",
    ),
]


POP_STRUCTURES = [
    PopStructureDescriptor(
        key="pop_naturale",
        name="POP Naturale",
        summary="Estrutura institucional da Naturale com cabecalho oficial no header do Word e termo final no layout padrao da clinica.",
        details=(
            "Usa o modelo oficial da Naturale para preservar o cabecalho com logo, titulo, codigo, revisao e data, "
            "alem do termo de responsabilidade e das assinaturas no fechamento original do documento."
        ),
        best_for=[
            "POPs oficiais da Naturale",
            "Documentos que precisam seguir o layout institucional da clinica",
            "Procedimentos com fechamento formal de responsabilidade e aprovacao",
        ],
        sections_overview=[
            "Cabecalho institucional Naturale",
            "1. Objetivo",
            "2. Documentos de Referencia",
            "3. Local de Aplicacao",
            "4. Responsabilidade / Execucao",
            "5. Definicoes e Siglas",
            "6. Descricao das Atividades",
            "7. Regras e Controle",
            "Termo de Responsabilidade Naturale",
        ],
        activity_blueprint=[
            "6.1 Normas Gerais",
            "6.2 Execucao do Procedimento",
            "6.3 Encerramento e Registros",
        ],
        questions=COMMON_QUESTIONS,
    ),
    PopStructureDescriptor(
        key="operacional_padrao",
        name="POP Operacional Padrao",
        summary="Modelo base para rotinas operacionais com foco em execucao, controle e conformidade.",
        details=(
            "Ideal para procedimentos repetitivos com etapas claras, materiais definidos, "
            "regras de conformidade e verificacao final."
        ),
        allows_custom_logo=True,
        logo_formats=["PNG", "JPG"],
        logo_recommended_size="1200 x 400 px",
        logo_help_text="Use preferencialmente PNG horizontal com fundo transparente. Tamanho maximo sugerido: 2 MB.",
        best_for=[
            "Rotinas de limpeza",
            "Fluxos operacionais internos",
            "Procedimentos de apoio e suporte",
        ],
        sections_overview=[
            "1. Objetivo",
            "2. Documentos de Referencia",
            "3. Local de Aplicacao",
            "4. Responsabilidade / Execucao",
            "5. Definicoes e Siglas",
            "6. Descricao das Atividades",
            "7. Regras e Controle",
            "8. Termo de Responsabilidade",
        ],
        activity_blueprint=[
            "6.1 Normas Gerais",
            "6.2 Execucao do Procedimento",
            "6.3 Encerramento e Registros",
        ],
        questions=COMMON_QUESTIONS,
    ),
    PopStructureDescriptor(
        key="clinico_assistencial",
        name="POP Clinico Assistencial",
        summary="Estrutura para processos assistenciais com foco em preparo, execucao tecnica e seguranca.",
        details=(
            "Indicado para atendimento clinico, biosseguranca, preparo do ambiente, "
            "execucao assistencial e finalizacao segura."
        ),
        allows_custom_logo=True,
        logo_formats=["PNG", "JPG"],
        logo_recommended_size="1200 x 400 px",
        logo_help_text="Use preferencialmente PNG horizontal com fundo transparente. Tamanho maximo sugerido: 2 MB.",
        best_for=[
            "Atendimento clinico",
            "Biosseguranca",
            "Preparacao e liberacao de sala",
        ],
        sections_overview=[
            "1. Objetivo",
            "2. Documentos de Referencia",
            "3. Local de Aplicacao",
            "4. Responsabilidade / Execucao",
            "5. Definicoes e Siglas",
            "6. Descricao das Atividades",
            "7. Regras e Controle",
            "8. Termo de Responsabilidade",
        ],
        activity_blueprint=[
            "6.1 Preparacao do Atendimento",
            "6.2 Execucao Clinica",
            "6.3 Finalizacao e Biosseguranca",
        ],
        questions=COMMON_QUESTIONS,
    ),
    PopStructureDescriptor(
        key="administrativo_controle",
        name="POP Administrativo e Controle",
        summary="Modelo para rotinas administrativas com foco em registros, aprovacoes e rastreabilidade.",
        details=(
            "Melhor para processos de escritorio, controles administrativos, "
            "cadastros, conferencias e fluxos de aprovacao."
        ),
        allows_custom_logo=True,
        logo_formats=["PNG", "JPG"],
        logo_recommended_size="1200 x 400 px",
        logo_help_text="Use preferencialmente PNG horizontal com fundo transparente. Tamanho maximo sugerido: 2 MB.",
        best_for=[
            "Financeiro",
            "Recepcao e cadastro",
            "Fluxos de aprovacao e conferencia",
        ],
        sections_overview=[
            "1. Objetivo",
            "2. Documentos de Referencia",
            "3. Local de Aplicacao",
            "4. Responsabilidade / Execucao",
            "5. Definicoes e Siglas",
            "6. Descricao das Atividades",
            "7. Regras e Controle",
            "8. Termo de Responsabilidade",
        ],
        activity_blueprint=[
            "6.1 Preparacao da Rotina",
            "6.2 Execucao Administrativa",
            "6.3 Conferencia e Registro Final",
        ],
        questions=COMMON_QUESTIONS,
    ),
]


def list_pop_structures() -> list[PopStructureDescriptor]:
    return POP_STRUCTURES


def get_pop_structure(structure_key: str) -> PopStructureDescriptor:
    for structure in POP_STRUCTURES:
        if structure.key == structure_key:
            return structure
    raise AgentExecutionError(f"Estrutura de POP invalida: {structure_key}")
