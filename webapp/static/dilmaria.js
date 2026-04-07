const boot = window.DILMARIA_BOOTSTRAP || {}
const API_BASE = "/operacoes/dilmaria/api"
const MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024

const form = document.getElementById("pop-form")
const submitButton = document.getElementById("submit-button")
const message = document.getElementById("message")
const structureList = document.getElementById("structure-list")
const structureDetails = document.getElementById("structure-details")
const questionnaire = document.getElementById("questionnaire")
const questionTemplate = document.getElementById("question-template")
const agentCardTemplate = document.getElementById("agent-card-template")
const expressSection = document.getElementById("express-section")
const advancedSection = document.getElementById("advanced-section")
const rawContextInput = document.getElementById("raw-context")
const dashboardAgentGrid = document.getElementById("dashboard-agent-grid")
const fullAgentGrid = document.getElementById("agent-grid")
const upcomingEvents = document.getElementById("upcoming-events")
const historyList = document.getElementById("history-list")
const historyEmpty = document.getElementById("history-empty")
const historySummary = document.getElementById("history-summary")
const historyLast = document.getElementById("history-last")
const workspaceAgentName = document.getElementById("workspace-agent-name")
const workspaceAgentDescription = document.getElementById("workspace-agent-description")
const workspaceAgentStatus = document.getElementById("workspace-agent-status")
const workspaceAgentTag = document.getElementById("workspace-agent-tag")
const workspaceStructureName = document.getElementById("workspace-structure-name")
const workspaceStructureSummary = document.getElementById("workspace-structure-summary")
const workspaceStructureHighlights = document.getElementById("workspace-structure-highlights")
const draftSection = document.getElementById("draft-section")
const draftStatus = document.getElementById("draft-status")
const draftMessage = document.getElementById("draft-message")
const refinedSection = document.getElementById("refined-section")
const refinedAnswersGrid = document.getElementById("refined-answers-grid")
const draftObjetivo = document.getElementById("draft-objetivo")
const draftDocumentosReferencia = document.getElementById("draft-documentos-referencia")
const draftLocalAplicacao = document.getElementById("draft-local-aplicacao")
const draftResponsabilidadeExecucao = document.getElementById("draft-responsabilidade-execucao")
const draftDefinicoesSiglas = document.getElementById("draft-definicoes-siglas")
const draftActivities = document.getElementById("draft-activities")
const draftCriteriosAvaliacao = document.getElementById("draft-criterios-avaliacao")
const draftBoasPraticas = document.getElementById("draft-boas-praticas")
const draftErrosCriticos = document.getElementById("draft-erros-criticos")
const exportButton = document.getElementById("export-button")
const autosaveStatus = document.getElementById("autosave-status")
const customLogoSection = document.getElementById("custom-logo-section")
const customLogoInput = document.getElementById("custom-logo-input")
const clearLogoButton = document.getElementById("clear-logo-button")
const logoGuidanceFormats = document.getElementById("logo-guidance-formats")
const logoGuidanceSize = document.getElementById("logo-guidance-size")
const logoGuidanceHelp = document.getElementById("logo-guidance-help")
const logoFileName = document.getElementById("logo-file-name")
const settingsUserName = document.getElementById("settings-user-name")
const settingsUserEmail = document.getElementById("settings-user-email")
const settingsUserRole = document.getElementById("settings-user-role")
const settingsAccountLink = document.getElementById("settings-account-link")
const settingsHubLink = document.getElementById("settings-hub-link")

const currentUser = boot.current_user || {}
const csrfToken = boot.csrf_token || ""

const agents = [
  {
    id: "pop-generator",
    name: "Agente de POPs",
    description: "Gera POPs em Word.",
    status: "Ativo",
    tag: "Producao",
    available: true,
  },
  {
    id: "financeiro",
    name: "Agente Financeiro",
    description: "Reservado para a proxima fase.",
    status: "Inativo",
    tag: "Em breve",
    available: false,
  },
  {
    id: "documentos",
    name: "Agente de Documentos",
    description: "Reservado para a proxima fase.",
    status: "Inativo",
    tag: "Em breve",
    available: false,
  },
  {
    id: "atendimento",
    name: "Agente de Atendimento",
    description: "Reservado para a proxima fase.",
    status: "Inativo",
    tag: "Em breve",
    available: false,
  },
]

const releaseItems = [
  "POP Naturale integrado",
  "Historico persistido no banco",
  "Usuarios reaproveitados do D3",
]

let structures = []
let selectedStructureKey = ""
let creationMode = "express"
let currentView = "dashboard"
let draftPreview = null
let draftNeedsRefresh = false
let customLogoDataUrl = ""
let customLogoName = ""
let isHydratingDraft = false
let draftSaveTimer = null
let draftBootstrapReady = false

function setStatusMessage(element, text, status = "") {
  element.textContent = text || ""
  element.classList.remove("flash-success", "flash-error")
  if (status === "success") {
    element.classList.add("flash-success")
  }
  if (status === "error") {
    element.classList.add("flash-error")
  }
}

function setMessage(text, status = "") {
  setStatusMessage(message, text, status)
}

function setDraftMessage(text, status = "") {
  setStatusMessage(draftMessage, text, status)
}

function setAutosaveStatus(text, status = "") {
  setStatusMessage(autosaveStatus, text, status)
}

function extractErrorMessage(payload, fallback) {
  if (payload && typeof payload.detail === "string" && payload.detail.trim()) {
    return payload.detail
  }
  return fallback
}

async function apiFetch(path, options = {}) {
  const { json, headers: rawHeaders, ...rest } = options
  const headers = new Headers(rawHeaders || {})
  headers.set("X-CSRF-Token", csrfToken)
  if (json !== undefined) {
    headers.set("Content-Type", "application/json")
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers,
    body: json !== undefined ? JSON.stringify(json) : rest.body,
  })
  return response
}

function formatDisplayDateTime(value) {
  if (!value) {
    return "-"
  }
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(parsed)
}

function parseMultilineList(value) {
  return String(value || "")
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean)
}

function serializeDefinitionLines(definitions) {
  return (definitions || []).map((item) => `${item.termo}: ${item.descricao}`).join("\n")
}

function parseDefinitionLines(value) {
  return parseMultilineList(value)
    .map((line) => {
      const [term, ...descriptionParts] = line.split(":")
      return {
        termo: (term || "").trim(),
        descricao: descriptionParts.join(":").trim(),
      }
    })
    .filter((item) => item.termo && item.descricao)
}

function serializeItemLines(items) {
  return (items || [])
    .map((item) => (item.observacao ? `${item.descricao} | ${item.observacao}` : item.descricao))
    .join("\n")
}

function parseItemLines(value) {
  return parseMultilineList(value)
    .map((line) => {
      const [description, ...observationParts] = line.split("|")
      const observacao = observationParts.join("|").trim()
      return {
        descricao: (description || "").trim(),
        observacao: observacao || null,
      }
    })
    .filter((item) => item.descricao)
}

function downloadBlob(blob, fileName) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement("a")
  link.href = url
  link.download = fileName
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(url)
}

function readFileAsDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result || ""))
    reader.onerror = () => reject(new Error("Nao foi possivel ler a logo selecionada."))
    reader.readAsDataURL(file)
  })
}

function clearCustomLogoSelection({ keepInput = false } = {}) {
  customLogoDataUrl = ""
  customLogoName = ""
  if (!keepInput && customLogoInput) {
    customLogoInput.value = ""
  }
  logoFileName.textContent = "Nenhuma logo selecionada."
}

function invalidateDraftPreview() {
  if (isHydratingDraft) {
    return
  }
  if (!draftPreview) {
    return
  }
  draftNeedsRefresh = true
  exportButton.disabled = true
  setDraftStatus("Atualizar", false)
  setDraftMessage("Atualize o rascunho para exportar.", "error")
}

function clearDraftPreview() {
  draftPreview = null
  draftNeedsRefresh = false
  draftSection.hidden = true
  exportButton.disabled = true
}

function setDraftStatus(text, ready = false) {
  draftStatus.textContent = text
  draftStatus.classList.remove("status-success", "status-warning")
  draftStatus.classList.add(ready ? "status-success" : "status-warning")
}

function openView(view) {
  currentView = view
  document.querySelectorAll(".dilmaria-view").forEach((section) => {
    section.classList.toggle("is-active", section.dataset.view === view)
  })
  document.querySelectorAll(".dilmaria-tab").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.viewTarget === view)
  })
}

function renderList(container, items, fallback = "Sem itens.") {
  container.innerHTML = ""
  const values = items.length ? items : [fallback]
  values.forEach((item) => {
    const node = document.createElement("li")
    node.textContent = item
    container.appendChild(node)
  })
}

function renderDashboard() {
  document.getElementById("modules-active-count").textContent = 3
  document.getElementById("agents-total-count").textContent = agents.length
  document.getElementById("profile-name").textContent = currentUser.role_label || "-"
  renderList(upcomingEvents, releaseItems)
  renderAgents(dashboardAgentGrid, agents.filter((agent) => agent.available))
  renderAgents(fullAgentGrid, agents)
}

function renderAgents(target, list) {
  target.innerHTML = ""
  list.forEach((agent) => {
    const fragment = agentCardTemplate.content.cloneNode(true)
    const status = fragment.querySelector(".status-badge")
    const tag = fragment.querySelector(".agent-tag")
    const name = fragment.querySelector(".agent-name")
    const description = fragment.querySelector(".agent-description")
    const action = fragment.querySelector(".agent-open-button")

    status.textContent = agent.status
    status.classList.add(agent.available ? "status-success" : "status-warning")
    tag.textContent = agent.tag
    name.textContent = agent.name
    description.textContent = agent.description
    action.textContent = agent.available ? "Abrir" : "Em breve"
    action.disabled = !agent.available
    if (agent.available) {
      action.addEventListener("click", () => openView("workspace"))
    }
    target.appendChild(fragment)
  })
}

function renderQuestionnaire(structure) {
  questionnaire.innerHTML = ""
  ;(structure.questions || []).forEach((question) => {
    const fragment = questionTemplate.content.cloneNode(true)
    const card = fragment.querySelector(".dilmaria-question-card")
    const label = fragment.querySelector(".question-label")
    const help = fragment.querySelector(".question-help")
    const input = fragment.querySelector(".question-input")

    card.dataset.questionId = question.id
    card.dataset.required = question.required ? "true" : "false"
    label.textContent = question.label
    help.textContent = question.help_text
    input.placeholder = question.placeholder || ""
    input.required = Boolean(question.required)

    questionnaire.appendChild(fragment)
  })
  syncModeFieldState()
}

function renderStructureDetails(structure) {
  if (!structure) {
    structureDetails.hidden = true
    return
  }

  structureDetails.hidden = false
  document.getElementById("details-name").textContent = structure.name
  document.getElementById("details-summary").textContent = structure.summary
  document.getElementById("details-description").textContent = structure.details
  renderList(document.getElementById("details-best-for"), structure.best_for || [])
  renderList(document.getElementById("details-sections"), structure.sections_overview || [])
  renderList(document.getElementById("details-activities"), structure.activity_blueprint || [])
  renderQuestionnaire(structure)
  updateLogoControls(structure)
  workspaceStructureName.textContent = structure.name
  workspaceStructureSummary.textContent = structure.summary
  renderList(workspaceStructureHighlights, structure.best_for || [])
}

function renderStructures() {
  structureList.innerHTML = ""
  structures.forEach((structure) => {
    const button = document.createElement("button")
    button.type = "button"
    button.className = "dilmaria-structure-card"
    button.dataset.structureKey = structure.key
    button.innerHTML = `<strong>${structure.name}</strong><span>${structure.summary}</span>`
    button.addEventListener("click", () => selectStructure(structure.key))
    structureList.appendChild(button)
  })
  const naturale = structures.find((item) => item.key === "pop_naturale")
  selectStructure((naturale || structures[0] || {}).key || "")
}

function selectStructure(key) {
  if (!key) {
    return
  }
  if (selectedStructureKey && selectedStructureKey !== key) {
    clearDraftPreview()
  }
  selectedStructureKey = key
  structureList.querySelectorAll(".dilmaria-structure-card").forEach((card) => {
    card.classList.toggle("selected", card.dataset.structureKey === key)
  })
  renderStructureDetails(structures.find((item) => item.key === key))
  queueDraftSave()
}

function updateLogoControls(structure) {
  const allowsCustomLogo = Boolean(structure?.allows_custom_logo)
  customLogoSection.hidden = !allowsCustomLogo
  if (!allowsCustomLogo) {
    clearCustomLogoSelection()
    return
  }
  logoGuidanceFormats.textContent = (structure.logo_formats || []).join(", ") || "PNG, JPG"
  logoGuidanceSize.textContent = structure.logo_recommended_size || "1200 x 400 px"
  logoGuidanceHelp.textContent =
    structure.logo_help_text ||
    "Use preferencialmente PNG horizontal com fundo transparente. Tamanho maximo sugerido: 2 MB."
  logoFileName.textContent = customLogoName || "Nenhuma logo selecionada."
}

async function handleCustomLogoSelected(file) {
  if (!file) {
    clearCustomLogoSelection({ keepInput: true })
    return
  }
  if (!["image/png", "image/jpeg"].includes(file.type)) {
    clearCustomLogoSelection()
    setMessage("Use uma logo em PNG ou JPG.", "error")
    return
  }
  if (file.size > MAX_LOGO_SIZE_BYTES) {
    clearCustomLogoSelection()
    setMessage("A logo deve ter no maximo 2 MB.", "error")
    return
  }
  customLogoDataUrl = await readFileAsDataUrl(file)
  customLogoName = file.name
  logoFileName.textContent = file.name
  setMessage("Logo pronta para uso.", "success")
  invalidateDraftPreview()
  queueDraftSave()
}

function setCreationMode(mode) {
  if (creationMode !== mode) {
    clearDraftPreview()
  }
  creationMode = mode
  expressSection.hidden = mode !== "express"
  advancedSection.hidden = mode !== "advanced"
  document.querySelectorAll(".dilmaria-choice").forEach((card) => {
    card.classList.toggle("selected", card.dataset.mode === mode)
  })
  syncModeFieldState()
  queueDraftSave()
}

function syncModeFieldState() {
  const isExpress = creationMode === "express"
  rawContextInput.disabled = !isExpress
  rawContextInput.required = isExpress
  questionnaire.querySelectorAll(".question-input").forEach((input) => {
    const required = input.closest(".dilmaria-question-card")?.dataset.required === "true"
    input.disabled = isExpress
    input.required = !isExpress && required
  })
}

function buildPayload() {
  const answers = {}
  questionnaire.querySelectorAll(".dilmaria-question-card").forEach((card) => {
    answers[card.dataset.questionId] = card.querySelector(".question-input").value.trim()
  })

  return {
    creation_mode: creationMode,
    structure_key: selectedStructureKey,
    titulo: document.getElementById("titulo").value.trim(),
    codigo: document.getElementById("codigo").value.trim(),
    data: document.getElementById("data").value,
    custom_logo_data_url: customLogoSection.hidden ? null : customLogoDataUrl || null,
    answers: creationMode === "advanced" ? answers : {},
    raw_context: creationMode === "express" ? rawContextInput.value.trim() : "",
    termo: {
      nome_responsavel: document.getElementById("nome-responsavel").value.trim(),
      declaracao: document.getElementById("declaracao").value.trim(),
      elaborado_por: document.getElementById("elaborado-por").value.trim(),
      aprovado_por: document.getElementById("aprovado-por").value.trim(),
      local: document.getElementById("termo-local").value.trim(),
      data: document.getElementById("termo-data").value,
    },
  }
}

function validatePayload(payload) {
  if (!payload.structure_key) return "Escolha uma estrutura."
  if (!payload.titulo || !payload.codigo) return "Preencha titulo e codigo."
  if (!payload.termo.nome_responsavel || !payload.termo.elaborado_por || !payload.termo.aprovado_por) {
    return "Preencha os responsaveis."
  }
  if (creationMode === "express" && !payload.raw_context) return "Descreva o contexto."
  if (creationMode === "advanced") {
    for (const input of questionnaire.querySelectorAll(".question-input:required")) {
      if (!input.value.trim()) {
        return "Responda os campos obrigatorios."
      }
    }
  }
  return ""
}

function renderRefinedAnswers(refinedAnswers) {
  refinedAnswersGrid.innerHTML = ""
  const entries = Object.entries(refinedAnswers || {}).filter(([, value]) => String(value || "").trim())
  refinedSection.hidden = entries.length === 0
  entries.forEach(([key, value]) => {
    const item = document.createElement("article")
    item.className = "dilmaria-refined-item"
    const title = document.createElement("h5")
    title.textContent = key.replaceAll("_", " ")
    const body = document.createElement("p")
    body.textContent = value
    item.append(title, body)
    refinedAnswersGrid.appendChild(item)
  })
}

function createDraftActivityCard(subsection, index) {
  const card = document.createElement("article")
  card.className = "dilmaria-subcard draft-activity-card"
  card.innerHTML = `
    <div class="card-header">
      <div>
        <p class="section-kicker">Subsecao ${index + 1}</p>
        <h3>${subsection.numero || `6.${index + 1}`}</h3>
      </div>
    </div>
    <label class="field">
      <span>Titulo</span>
      <input data-field="titulo" type="text" value="${subsection.titulo || ""}">
    </label>
    <div class="grid two-col">
      <label class="field">
        <span>Materiais</span>
        <textarea data-field="materiais" rows="4">${(subsection.materiais || []).join("\n")}</textarea>
      </label>
      <label class="field">
        <span>Preparacao</span>
        <textarea data-field="preparacao" rows="4">${(subsection.preparacao || []).join("\n")}</textarea>
      </label>
      <label class="field">
        <span>Etapas iniciais</span>
        <textarea data-field="etapas_iniciais" rows="4">${(subsection.etapas_iniciais || []).join("\n")}</textarea>
      </label>
      <label class="field">
        <span>Itens</span>
        <textarea data-field="itens" rows="6">${serializeItemLines(subsection.itens || [])}</textarea>
      </label>
    </div>
  `
  return card
}

function renderDraftPreview(preview) {
  draftPreview = preview
  draftNeedsRefresh = false
  draftSection.hidden = false
  exportButton.disabled = false

  renderRefinedAnswers(preview.refined_answers || {})

  const draft = preview.draft
  draftObjetivo.value = draft.objetivo || ""
  draftDocumentosReferencia.value = (draft.documentos_referencia || []).join("\n")
  draftLocalAplicacao.value = draft.local_aplicacao || ""
  draftResponsabilidadeExecucao.value = draft.responsabilidade_execucao || ""
  draftDefinicoesSiglas.value = serializeDefinitionLines(draft.definicoes_siglas || [])
  draftCriteriosAvaliacao.value = (draft.criterios_avaliacao || []).join("\n")
  draftBoasPraticas.value = (draft.boas_praticas || []).join("\n")
  draftErrosCriticos.value = (draft.erros_criticos || []).join("\n")

  draftActivities.innerHTML = ""
  ;(draft.atividades || []).forEach((subsection, index) => {
    draftActivities.appendChild(createDraftActivityCard(subsection, index))
  })

  setDraftStatus("Pronto", true)
  setDraftMessage("Rascunho gerado. Revise antes de exportar.", "success")
  openView("workspace")
  queueDraftSave()
}

function buildDraftRequest() {
  const payload = buildPayload()
  return {
    structure_key: payload.structure_key,
    titulo: payload.titulo,
    codigo: payload.codigo,
    data: payload.data,
    custom_logo_data_url: payload.custom_logo_data_url,
    termo: payload.termo,
    objetivo: draftObjetivo.value.trim(),
    documentos_referencia: parseMultilineList(draftDocumentosReferencia.value),
    local_aplicacao: draftLocalAplicacao.value.trim(),
    responsabilidade_execucao: draftResponsabilidadeExecucao.value.trim(),
    definicoes_siglas: parseDefinitionLines(draftDefinicoesSiglas.value),
    atividades: Array.from(draftActivities.querySelectorAll(".draft-activity-card")).map((card) => ({
      titulo: card.querySelector('[data-field="titulo"]').value.trim(),
      materiais: parseMultilineList(card.querySelector('[data-field="materiais"]').value),
      preparacao: parseMultilineList(card.querySelector('[data-field="preparacao"]').value),
      etapas_iniciais: parseMultilineList(card.querySelector('[data-field="etapas_iniciais"]').value),
      itens: parseItemLines(card.querySelector('[data-field="itens"]').value),
    })),
    criterios_avaliacao: parseMultilineList(draftCriteriosAvaliacao.value),
    boas_praticas: parseMultilineList(draftBoasPraticas.value),
    erros_criticos: parseMultilineList(draftErrosCriticos.value),
  }
}

function buildPersistedState() {
  return {
    structure_key: selectedStructureKey,
    creation_mode: creationMode,
    custom_logo_name: customLogoName || null,
    form_payload: buildPayload(),
    preview: draftPreview
      ? {
          ...draftPreview,
          draft: buildDraftRequest(),
        }
      : null,
  }
}

function hasMeaningfulDraftState(state) {
  const payload = state.form_payload || {}
  const answerValues = Object.values(payload.answers || {}).some((value) => String(value || "").trim())
  return Boolean(
    payload.titulo ||
      payload.codigo ||
      payload.raw_context ||
      answerValues ||
      (state.preview && state.preview.draft && state.preview.draft.objetivo)
  )
}

function applyFormPayload(payload) {
  document.getElementById("titulo").value = payload.titulo || ""
  document.getElementById("codigo").value = payload.codigo || ""
  document.getElementById("data").value = payload.data || ""
  document.getElementById("nome-responsavel").value = payload.termo?.nome_responsavel || ""
  document.getElementById("declaracao").value = payload.termo?.declaracao || ""
  document.getElementById("elaborado-por").value = payload.termo?.elaborado_por || ""
  document.getElementById("aprovado-por").value = payload.termo?.aprovado_por || ""
  document.getElementById("termo-local").value = payload.termo?.local || ""
  document.getElementById("termo-data").value = payload.termo?.data || ""
  rawContextInput.value = payload.raw_context || ""
  customLogoDataUrl = payload.custom_logo_data_url || ""

  questionnaire.querySelectorAll(".dilmaria-question-card").forEach((card) => {
    const input = card.querySelector(".question-input")
    input.value = payload.answers?.[card.dataset.questionId] || ""
  })
}

function applyPersistedDraft(savedDraft) {
  if (!savedDraft?.state?.form_payload) {
    return
  }

  isHydratingDraft = true
  try {
    if (savedDraft.state.structure_key) {
      selectStructure(savedDraft.state.structure_key)
    }
    setCreationMode(savedDraft.state.creation_mode || "express")
    applyFormPayload(savedDraft.state.form_payload)
    customLogoName = savedDraft.state.custom_logo_name || ""
    updateLogoControls(structures.find((item) => item.key === selectedStructureKey))
    logoFileName.textContent = customLogoName || "Nenhuma logo selecionada."
    if (savedDraft.state.preview?.draft) {
      renderDraftPreview(savedDraft.state.preview)
    }
  } finally {
    isHydratingDraft = false
  }

  const label = savedDraft.codigo || savedDraft.titulo || "ultimo rascunho"
  setAutosaveStatus(`Rascunho restaurado: ${label}.`, "success")
  setMessage("Rascunho restaurado.", "success")
}

async function clearPersistedDraft({ silent = false } = {}) {
  try {
    await apiFetch("/draft", {
      method: "DELETE",
    })
    if (!silent) {
      setAutosaveStatus("Rascunho limpo.", "success")
    }
  } catch (error) {
    if (!silent) {
      setAutosaveStatus("Falha ao limpar rascunho.", "error")
    }
  }
}

async function saveDraftState() {
  const state = buildPersistedState()
  if (!hasMeaningfulDraftState(state)) {
    await clearPersistedDraft({ silent: true })
    setAutosaveStatus("Sem rascunho salvo.")
    return
  }

  try {
    const response = await apiFetch("/draft", {
      method: "POST",
      json: state,
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(extractErrorMessage(error, "Falha ao salvar o rascunho."))
    }
    const saved = await response.json()
    setAutosaveStatus(`Salvo em ${formatDisplayDateTime(saved.saved_at)}.`, "success")
  } catch (error) {
    setAutosaveStatus(error.message || "Falha ao salvar o rascunho.", "error")
  }
}

function queueDraftSave() {
  if (isHydratingDraft || !draftBootstrapReady) {
    return
  }
  if (draftSaveTimer) {
    window.clearTimeout(draftSaveTimer)
  }
  setAutosaveStatus("Salvando...")
  draftSaveTimer = window.setTimeout(() => {
    saveDraftState()
  }, 500)
}

async function loadDraftState() {
  const response = await apiFetch("/draft")
  if (!response.ok) {
    throw new Error("Nao foi possivel carregar o rascunho salvo.")
  }
  const payload = await response.json()
  if (payload.draft) {
    applyPersistedDraft(payload.draft)
    return
  }
  setAutosaveStatus("Sem rascunho salvo.")
}

function renderPopHistory(data) {
  historyList.innerHTML = ""
  const recent = data.recentes || []
  historySummary.textContent = `${data.total_execucoes || 0} execucoes`
  historyLast.textContent = data.ultima_execucao_em
    ? `Ultima: ${formatDisplayDateTime(data.ultima_execucao_em)}`
    : "Sem exportacoes"
  historyEmpty.hidden = recent.length > 0
  recent.forEach((item) => {
    const row = document.createElement("div")
    row.className = "dilmaria-history-row"
    row.innerHTML = `
      <div class="dilmaria-history-grid">
        <div><strong>${item.codigo}</strong></div>
        <div>${item.titulo}</div>
        <div>${item.revisao}</div>
        <div>${formatDisplayDateTime(item.timestamp)}</div>
      </div>
    `
    historyList.appendChild(row)
  })
}

async function loadStructures() {
  const response = await apiFetch("/structures")
  if (!response.ok) {
    throw new Error("Nao foi possivel carregar as estruturas.")
  }
  structures = await response.json()
  renderStructures()
}

async function loadHistory() {
  const response = await apiFetch("/history?limit=8")
  if (!response.ok) {
    throw new Error("Nao foi possivel carregar o historico.")
  }
  renderPopHistory(await response.json())
}

async function loadHealth() {
  const statusCard = document.getElementById("system-health")
  const response = await apiFetch("/health")
  if (!response.ok) {
    statusCard.textContent = "Offline"
    return
  }
  const data = await response.json()
  statusCard.textContent = data.status === "ok" ? "Online" : "Atencao"
}

function fillSettings() {
  settingsUserName.textContent = currentUser.name || "-"
  settingsUserEmail.textContent = currentUser.email || "-"
  settingsUserRole.textContent = currentUser.role_label || "-"
  settingsAccountLink.href = boot.settings_url || "/configuracoes"
  settingsHubLink.href = boot.hub_url || "/hub"
}

document.querySelectorAll(".dilmaria-tab").forEach((button) => {
  button.addEventListener("click", () => openView(button.dataset.viewTarget))
})

document.querySelectorAll("[data-view-target]").forEach((button) => {
  if (!button.classList.contains("dilmaria-tab")) {
    button.addEventListener("click", () => openView(button.dataset.viewTarget))
  }
})

document.querySelectorAll("[data-go-workspace]").forEach((button) => {
  button.addEventListener("click", () => openView("workspace"))
})

document.querySelectorAll(".dilmaria-choice").forEach((button) => {
  button.addEventListener("click", () => setCreationMode(button.dataset.mode))
})

customLogoInput?.addEventListener("change", async (event) => {
  const [file] = event.target.files || []
  try {
    await handleCustomLogoSelected(file)
  } catch (error) {
    clearCustomLogoSelection()
    setMessage(error.message || "Falha ao carregar a logo.", "error")
  }
})

clearLogoButton?.addEventListener("click", () => {
  clearCustomLogoSelection()
  invalidateDraftPreview()
  setMessage("Logo removida.", "success")
  queueDraftSave()
})

form?.addEventListener("input", () => {
  invalidateDraftPreview()
  queueDraftSave()
})

draftSection?.addEventListener("input", () => {
  invalidateDraftPreview()
  queueDraftSave()
})

form?.addEventListener("submit", async (event) => {
  event.preventDefault()
  const payload = buildPayload()
  const validationError = validatePayload(payload)
  if (validationError) {
    setMessage(validationError, "error")
    return
  }

  submitButton.disabled = true
  setMessage("Gerando rascunho...")

  try {
    const response = await apiFetch("/preview", {
      method: "POST",
      json: payload,
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(extractErrorMessage(error, "Nao foi possivel gerar o rascunho."))
    }
    renderDraftPreview(await response.json())
    setMessage("Rascunho pronto.", "success")
  } catch (error) {
    setMessage(error.message || "Falha inesperada ao gerar o rascunho.", "error")
  } finally {
    submitButton.disabled = false
  }
})

exportButton?.addEventListener("click", async () => {
  if (!draftPreview || draftNeedsRefresh) {
    setDraftMessage("Atualize o rascunho antes de exportar.", "error")
    return
  }

  exportButton.disabled = true
  setDraftMessage("Exportando DOCX...")
  try {
    const payload = buildDraftRequest()
    const response = await apiFetch("/run", {
      method: "POST",
      json: payload,
    })
    if (!response.ok) {
      const error = await response.json().catch(() => ({}))
      throw new Error(extractErrorMessage(error, "Nao foi possivel exportar o POP."))
    }
    const revision = response.headers.get("X-POP-Revision") || "Rev.00"
    const code = response.headers.get("X-POP-Code") || payload.codigo
    const blob = await response.blob()
    downloadBlob(blob, `${code}-${revision.replace(".", "")}.docx`)
    setDraftStatus(revision, true)
    setDraftMessage(`POP exportado. ${revision}.`, "success")
    setMessage(`DOCX pronto. ${revision}.`, "success")
    await clearPersistedDraft({ silent: true })
    setAutosaveStatus("Rascunho encerrado apos a exportacao.", "success")
    await loadHistory()
  } catch (error) {
    setDraftMessage(error.message || "Falha inesperada ao exportar o POP.", "error")
  } finally {
    exportButton.disabled = draftNeedsRefresh
  }
})

async function bootstrap() {
  renderDashboard()
  fillSettings()
  document.getElementById("data").value = new Date().toISOString().slice(0, 10)
  document.getElementById("termo-data").value = new Date().toISOString().slice(0, 10)
  document.getElementById("nome-responsavel").value = currentUser.name || ""
  document.getElementById("elaborado-por").value = currentUser.name || ""
  document.getElementById("aprovado-por").value = currentUser.name || ""
  document.getElementById("termo-local").value = "Sao Paulo"
  workspaceAgentName.textContent = agents[0].name
  workspaceAgentDescription.textContent = agents[0].description
  workspaceAgentStatus.textContent = agents[0].status
  workspaceAgentTag.textContent = agents[0].tag
  setCreationMode("express")
  setMessage("Carregando...")

  try {
    await Promise.all([loadStructures(), loadHistory(), loadHealth()])
    await loadDraftState()
    draftBootstrapReady = true
    setMessage("Pronto.")
  } catch (error) {
    setMessage(error.message || "Falha ao carregar o modulo.", "error")
  }
}

bootstrap()
