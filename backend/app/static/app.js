const state = {
  workflows: [],
  selectedWorkflowId: null,
  clusterJobs: [],
  analysisResults: [],
};

const pageMode = document.body.dataset.page || "workflow";

const workflowList = document.querySelector("#workflow-list");
const workflowCount = document.querySelector("#workflow-count");
const workflowForm = document.querySelector("#workflow-form");
const clusterConfigForm = document.querySelector("#cluster-config-form");
const workflowEmpty = document.querySelector("#workflow-empty");
const workflowDetails = document.querySelector("#workflow-details");
const advanceButton = document.querySelector("#advance-button");
const templateSelect = document.querySelector("#template-select");
const executorSelect = document.querySelector('select[name="executor"]');
const remoteSettings = document.querySelector("#remote-settings");
const templateHelp = document.querySelector("#template-help");
const templateBadge = document.querySelector("#template-badge");
const calculationTypeSelect = document.querySelector("#calculation-type-select");
const structureSourceField = document.querySelector("#structure-source");
const jobSettingsList = document.querySelector("#job-settings-list");
const submissionPreview = document.querySelector("#submission-preview");
const filePreviewGrid = document.querySelector("#file-preview-grid");
const workflowRecipeSelect = document.querySelector("#workflow-recipe-select");
const workflowPlanPreview = document.querySelector("#workflow-plan-preview");
const clusterJobsList = document.querySelector("#cluster-jobs-list");
const refreshClusterButton = document.querySelector("#refresh-cluster-button");
const clusterScopeSelect = document.querySelector("#cluster-scope-select");
const clusterConfigSummary = document.querySelector("#cluster-config-summary");
const clusterTarget = document.querySelector("#cluster-target");
const clusterModeNote = document.querySelector("#cluster-mode-note");
const analysisResultsGrid = document.querySelector("#analysis-results-grid");
const refreshAnalysisButton = document.querySelector("#refresh-analysis-button");
const applyRecommendationButton = document.querySelector("#apply-recommendation-button");
const recommendationPreviewCard = document.querySelector("#recommendation-preview-card");
const bindingReferenceSelect = document.querySelector("#binding-reference-select");
const bindingEnergyButton = document.querySelector("#binding-energy-button");
const bindingEnergyResult = document.querySelector("#binding-energy-result");
const ecnButton = document.querySelector("#ecn-button");
const ecnResult = document.querySelector("#ecn-result");
const tabButtons = document.querySelectorAll("[data-tab-target]");
const tabPanels = document.querySelectorAll("[data-tab-panel]");

state.templates = [];
state.recommendationPreview = null;
state.activeTab = "overview";
state.bindingEnergyResult = null;
state.ecnResult = null;
state.clusterConfig = null;

function readWorkflowIdFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("workflow_id");
}

function readTabFromUrl() {
  const params = new URLSearchParams(window.location.search);
  return params.get("tab");
}

function writeNavigationStateToUrl({ workflowId, tab }, { replace = false } = {}) {
  const url = new URL(window.location.href);
  if (workflowId) {
    url.searchParams.set("workflow_id", workflowId);
  } else {
    url.searchParams.delete("workflow_id");
  }
  if (tab && pageMode === "workflow") {
    url.searchParams.set("tab", tab);
  } else {
    url.searchParams.delete("tab");
  }
  if (replace) {
    window.history.replaceState({ workflowId, tab }, "", url);
    return;
  }
  window.history.pushState({ workflowId, tab }, "", url);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Falha ao comunicar com a API.");
  }

  const contentType = response.headers.get("content-type") || "";
  return contentType.includes("application/json") ? response.json() : response.text();
}

function badgeClass(status) {
  if (status === "failed") return "badge failed";
  if (status === "warning") return "badge warning";
  if (status === "running") return "badge running";
  return "badge";
}

function renderWorkflowList() {
  if (workflowCount) {
    workflowCount.textContent = String(state.workflows.length);
  }
  renderBindingReferenceOptions();

  if (!state.workflows.length) {
    workflowList.innerHTML = '<div class="empty-state">Nenhum workflow criado ainda.</div>';
    return;
  }

  workflowList.innerHTML = state.workflows
    .map((workflow) => `
      <article class="workflow-item ${workflow.workflow_id === state.selectedWorkflowId ? "active" : ""}" data-id="${workflow.workflow_id}">
        <h3>${workflow.project_name}</h3>
        <div class="workflow-meta">
          <span class="${badgeClass(workflow.job_status)}">${workflow.job_status}</span>
          <span class="badge secondary">${workflow.agent_status}</span>
        </div>
        <p><strong>${workflow.executor}</strong></p>
        <p>${workflow.goal}</p>
      </article>
    `)
    .join("");

  document.querySelectorAll(".workflow-item").forEach((item) => {
    item.addEventListener("click", async () => {
      await selectWorkflow(item.dataset.id);
    });
  });
}

function renderClusterJobs() {
  if (!clusterJobsList) return;
  if (!state.clusterJobs.length) {
    clusterJobsList.innerHTML = '<div class="empty-state">Nenhum job em execucao ou na fila no cluster.</div>';
    return;
  }

  clusterJobsList.innerHTML = state.clusterJobs
    .map(
      (job) => `
        <article class="cluster-job-item">
          <div class="workflow-meta">
            <h3>${job.project_name || job.name || "job sem nome"}</h3>
            <span class="${badgeClass(normalizeClusterState(job.state))}">${job.state}</span>
          </div>
          <dl class="cluster-job-meta">
            <div>
              <dt>Job ID</dt>
              <dd>${formatValue(job.scheduler_job_id)}</dd>
            </div>
            <div>
              <dt>Dono</dt>
              <dd>${formatValue(job.owner)}</dd>
            </div>
            <div>
              <dt>Fila</dt>
              <dd>${formatValue(job.queue)}</dd>
            </div>
            <div>
              <dt>Tempo</dt>
              <dd>${formatValue(job.runtime)}</dd>
            </div>
            <div>
              <dt>Nos</dt>
              <dd>${formatValue(job.nodes)}</dd>
            </div>
          </dl>
          <p><strong>Remote path:</strong> ${formatValue(job.remote_path)}</p>
          ${
            job.workflow_id
              ? `<p><strong>Workflow local:</strong> ${job.workflow_id}</p>`
              : "<p><strong>Workflow local:</strong> nao associado</p>"
          }
        </article>
      `,
    )
    .join("");
}

function renderClusterConfig() {
  if (!clusterConfigSummary || !state.clusterConfig) return;
  const config = state.clusterConfig;

  if (clusterTarget) {
    clusterTarget.textContent = config.ssh_target || "-";
  }
  if (clusterModeNote) {
    clusterModeNote.textContent = config.dry_run
      ? "Executor em dry-run. O backend so prepara e simula a submissao."
      : "Executor remoto ativo. O backend esta pronto para usar SSH, SCP e sbatch.";
  }

  clusterConfigSummary.innerHTML = `
    <article class="preview-item">
      <div class="workflow-meta">
        <h4>Alvo remoto</h4>
        <span class="${badgeClass(config.dry_run ? "warning" : "running")}">${config.dry_run ? "dry-run" : "remoto"}</span>
      </div>
      <dl class="results-list">
        <div>
          <dt>SSH target</dt>
          <dd>${formatValue(config.ssh_target)}</dd>
        </div>
        <div>
          <dt>Host</dt>
          <dd>${formatValue(config.ssh_host)}</dd>
        </div>
        <div>
          <dt>Usuario</dt>
          <dd>${formatValue(config.ssh_user)}</dd>
        </div>
        <div>
          <dt>Base remota</dt>
          <dd>${formatValue(config.remote_base_dir)}</dd>
        </div>
        <div>
          <dt>Identidade</dt>
          <dd>${formatValue(config.identity_file)}</dd>
        </div>
        <div>
          <dt>Modo</dt>
          <dd>${config.dry_run ? "dry-run" : "execucao remota"}</dd>
        </div>
        <div>
          <dt>Senha temporaria</dt>
          <dd>${config.has_session_password ? "carregada nesta sessao" : "nao informada"}</dd>
        </div>
      </dl>
    </article>
  `;

  if (clusterConfigForm) {
    clusterConfigForm.elements.ssh_host.value = config.ssh_host || "";
    clusterConfigForm.elements.ssh_user.value = config.ssh_user || "";
    clusterConfigForm.elements.remote_base_dir.value = config.remote_base_dir || "";
    clusterConfigForm.elements.identity_file.value = config.identity_file || "";
    clusterConfigForm.elements.session_password.value = "";
    clusterConfigForm.elements.dry_run.checked = Boolean(config.dry_run);
  }
}

function renderWorkflowDetails(workflow, filePreviews = []) {
  workflowEmpty.classList.add("hidden");
  workflowDetails.classList.remove("hidden");

  const jobBadge = document.querySelector("#job-status");
  const agentBadge = document.querySelector("#agent-status");
  jobBadge.textContent = `job: ${workflow.job_status}`;
  jobBadge.className = badgeClass(workflow.job_status);
  agentBadge.textContent = `agent: ${workflow.agent_status}`;
  agentBadge.className = `${badgeClass(workflow.agent_status)} secondary`;

  document.querySelector("#summary-text").textContent = workflow.latest_summary;
  document.querySelector("#next-step-text").textContent = workflow.latest_next_step;

  document.querySelector("#results-list").innerHTML = Object.entries(workflow.latest_results)
    .map(([key, value]) => `
      <div>
        <dt>${key}</dt>
        <dd>${value === null ? "-" : value}</dd>
      </div>
    `)
    .join("");

  document.querySelector("#execution-list").innerHTML = Object.entries(workflow.execution_metadata || {})
    .map(([key, value]) => `
      <div>
        <dt>${key}</dt>
        <dd>${formatValue(value)}</dd>
      </div>
    `)
    .join("");

  if (jobSettingsList) {
    jobSettingsList.innerHTML = Object.entries(workflow.job_settings || {})
      .filter(([, value]) => value !== null && value !== "")
      .map(([key, value]) => `
        <div>
          <dt>${key}</dt>
          <dd>${formatValue(value)}</dd>
        </div>
      `)
      .join("") || "<div><dt>job_settings</dt><dd>-</dd></div>";
  }

  if (submissionPreview) {
    submissionPreview.innerHTML = buildSubmissionPreview(workflow);
  }
  if (filePreviewGrid) {
    filePreviewGrid.innerHTML = buildFilePreview(filePreviews);
  }
  if (workflowPlanPreview) {
    workflowPlanPreview.innerHTML = buildWorkflowPlanPreview(workflow);
  }
  if (recommendationPreviewCard) {
    recommendationPreviewCard.innerHTML = buildRecommendationPreview(state.recommendationPreview);
  }
  if (bindingEnergyResult) {
    bindingEnergyResult.innerHTML = buildBindingEnergyPreview(state.bindingEnergyResult);
  }
  if (ecnResult) {
    ecnResult.innerHTML = buildEcnPreview(state.ecnResult);
  }
  if (analysisResultsGrid) {
    analysisResultsGrid.innerHTML = buildAnalysisPreview(state.analysisResults);
  }
  renderActiveTab();
  bindFileEditors();

  document.querySelector("#history-list").innerHTML = workflow.history
    .slice()
    .reverse()
    .map((entry) => `
      <article class="history-item">
        <div class="workflow-meta">
          <strong>Etapa ${entry.step}</strong>
          <span class="${badgeClass(entry.job_status)}">${entry.job_status}</span>
        </div>
        <p><strong>Agente:</strong> ${entry.agent_status}</p>
        <p>${entry.summary}</p>
        <p><strong>Proximo:</strong> ${entry.next_step}</p>
      </article>
    `)
    .join("");
}

function renderBindingReferenceOptions() {
  if (!bindingReferenceSelect) return;
  const selectedValues = new Set(Array.from(bindingReferenceSelect.selectedOptions).map((option) => option.value));
  const options = state.workflows
    .filter((workflow) => workflow.workflow_id !== state.selectedWorkflowId)
    .map(
      (workflow) =>
        `<option value="${workflow.workflow_id}" ${selectedValues.has(workflow.workflow_id) ? "selected" : ""}>${workflow.project_name}</option>`,
    );
  bindingReferenceSelect.innerHTML = options.length
    ? options.join("")
    : '<option value="">Nenhum workflow de referencia disponivel</option>';
}

function renderActiveTab() {
  if (!tabButtons.length || !tabPanels.length) return;
  tabButtons.forEach((button) => {
    button.classList.toggle("active", button.dataset.tabTarget === state.activeTab);
  });
  tabPanels.forEach((panel) => {
    panel.classList.toggle("active", panel.dataset.tabPanel === state.activeTab);
  });
}

function buildBindingEnergyPreview(result) {
  if (!result) {
    return `
      <article class="preview-item">
        <h4>Calculo nao executado</h4>
        <p>Selecione um ou mais workflows de referencia para calcular a energia de ligacao.</p>
      </article>
    `;
  }

  const references = Array.isArray(result.references) ? result.references : [];
  return `
    <article class="preview-item">
      <div class="workflow-meta">
        <h4>Resultado da energia de ligacao</h4>
        <span class="badge secondary">${formatValue(result.binding_energy_ev)} eV</span>
      </div>
      <p>${result.summary}</p>
      <p><strong>Formula:</strong> ${formatValue(result.formula)}</p>
      <dl class="results-list">
        <div>
          <dt>Sistema total</dt>
          <dd>${formatValue(result.target?.project_name)} (${formatValue(result.target?.energy_ev)} eV)</dd>
        </div>
        <div>
          <dt>Numero de referencias</dt>
          <dd>${references.length}</dd>
        </div>
      </dl>
      ${
        references.length
          ? `<ul>${references.map((entry) => `<li>${entry.project_name}: ${entry.energy_ev} eV</li>`).join("")}</ul>`
          : "<p>Nenhuma referencia usada.</p>"
      }
    </article>
  `;
}

function buildEcnPreview(result) {
  if (!result) {
    return `
      <article class="preview-item">
        <h4>ECN nao calculado</h4>
        <p>Use o workflow selecionado para calcular o ECN diretamente do POSCAR.</p>
      </article>
    `;
  }

  return `
    <article class="preview-item">
      <div class="workflow-meta">
        <h4>Resultado do ECN</h4>
        <span class="badge secondary">${formatValue(result.average_ecn)}</span>
      </div>
      <p>${result.summary}</p>
      <p><strong>Especies detectadas:</strong> ${formatValue(result.species_labels)}</p>
      <p><strong>Contagens detectadas:</strong> ${formatValue(result.species_counts)}</p>
      <dl class="results-list">
        <div>
          <dt>Numero de atomos</dt>
          <dd>${formatValue(result.n_atoms)}</dd>
        </div>
        <div>
          <dt>ECN medio</dt>
          <dd>${formatValue(result.average_ecn)}</dd>
        </div>
        <div>
          <dt>ECN total</dt>
          <dd>${formatValue(result.total_ecn)}</dd>
        </div>
        <div>
          <dt>Awabl medio</dt>
          <dd>${formatValue(result.weighted_average_bond_length)} A</dd>
        </div>
      </dl>
      <p><strong>ECN por atomo:</strong> ${formatValue(result.ecn_by_atom)}</p>
      <p><strong>rmin por atomo:</strong> ${formatValue(result.rmin_by_atom)}</p>
      <p><strong>rwabl por atomo:</strong> ${formatValue(result.rwabl_by_atom)}</p>
    </article>
  `;
}

function buildRecommendationPreview(preview) {
  if (!preview) {
    return `
      <article class="preview-item">
        <h4>Recomendacao indisponivel</h4>
        <p>Carregue as analises deste workflow para ver o proximo calculo materializavel.</p>
      </article>
    `;
  }

  return `
    <article class="preview-item recommendation-preview-item">
      <div class="workflow-meta">
        <h4>Proxima acao sugerida</h4>
        <span class="badge secondary">${preview.calculation_type}</span>
      </div>
      <p>${preview.summary}</p>
      <dl class="results-list">
        <div>
          <dt>Etapa recomendada</dt>
          <dd>${formatValue(preview.recommended_step)}</dd>
        </div>
        <div>
          <dt>Objetivo gerado</dt>
          <dd>${formatValue(preview.goal)}</dd>
        </div>
        <div>
          <dt>Estrutura herdada</dt>
          <dd>${formatValue(preview.structure_origin)}</dd>
        </div>
        <div>
          <dt>Origem da estrutura</dt>
          <dd>${formatValue(preview.structure_source)}</dd>
        </div>
      </dl>
    </article>
  `;
}

function buildAnalysisPreview(results) {
  if (!results.length) {
    return `
      <article class="preview-item">
        <h4>Analises indisponiveis</h4>
        <p>Nenhuma analise carregada para este workflow.</p>
      </article>
    `;
  }

  return results
    .map(
      (result) => {
        let visualHtml = "";
        
        // 1. Renderizador Visual para Band Gap
        if (result.tool === "band_gap_check" && result.status !== "unavailable") {
          const details = result.details || {};
          const bg = details.band_gap_ev;
          const fermi = details.e_fermi;
          const vbm = details.vbm;
          const cbm = details.cbm;
          
          if (fermi !== null && vbm !== null && cbm !== null) {
            visualHtml = `
              <div class="visual-band-gap-diagram">
                <div class="band-block conduction-band">
                  <div class="band-label">Banda de Condução (CBM)</div>
                  <div class="band-energy">${cbm.toFixed(4)} eV</div>
                </div>
                <div class="gap-region">
                  <div class="fermi-line" title="Nível de Fermi">
                    <span class="fermi-label">E-Fermi: ${fermi.toFixed(4)} eV</span>
                  </div>
                  <div class="gap-badge ${bg > 0 ? "semiconductor" : "metallic"}">
                    ${bg > 0 ? `Gap: ${bg.toFixed(4)} eV` : "Comportamento Metálico"}
                  </div>
                </div>
                <div class="band-block valence-band">
                  <div class="band-label">Banda de Valência (VBM)</div>
                  <div class="band-energy">${vbm.toFixed(4)} eV</div>
                </div>
              </div>
            `;
          }
        }
        
        // 2. Renderizador Visual para Caminho NEB
        if (result.tool === "neb_path_check" && result.status !== "unavailable") {
          const details = result.details || {};
          const totalImg = details.image_count || 0;
          const convergedImg = details.converged_images_count || 0;
          const maxForce = details.max_force;
          const imagesList = Array.isArray(details.images_found) ? details.images_found : [];
          
          if (totalImg > 0) {
            visualHtml = `
              <div class="visual-neb-path">
                <h5>Caminho de Reação NEB (${convergedImg}/${totalImg} Convergidos)</h5>
                <div class="neb-node-chain">
                  ${imagesList.map((imgName, index) => {
                    const isEndNode = index === 0 || index === (totalImg - 1);
                    const isConverged = index < convergedImg;
                    let nodeClass = "neb-node";
                    if (isEndNode) nodeClass += " endpoint";
                    nodeClass += isConverged ? " converged" : " pending";
                    
                    return `
                      <div class="${nodeClass}">
                        <div class="node-dot"></div>
                        <div class="node-name">${imgName}</div>
                      </div>
                      ${index < (totalImg - 1) ? '<div class="neb-connector"></div>' : ''}
                    `;
                  }).join("")}
                </div>
                ${maxForce !== null ? `
                  <div class="neb-force-metric">
                    <span>Força Máxima de Transição:</span>
                    <strong class="${maxForce < 0.05 ? "good" : "warn"}">${maxForce.toFixed(4)} eV/Å</strong>
                  </div>
                ` : ""}
              </div>
            `;
          }
        }

        return `
          <article class="preview-item">
            <div class="workflow-meta">
              <h4>${result.title}</h4>
              <span class="${badgeClass(result.status)}">${result.status}</span>
            </div>
            <p>${result.summary}</p>
            ${visualHtml}
            <dl class="results-list">
              ${Object.entries(result.details || {})
                .map(
                  ([key, value]) => `
                    <div>
                      <dt>${key}</dt>
                      <dd>${formatValue(value)}</dd>
                    </div>
                  `,
                )
                .join("")}
            </dl>
          </article>
        `;
      }
    )
    .join("");
}

function formatValue(value) {
  if (value === null || value === undefined || value === "") return "-";
  if (Array.isArray(value)) return value.join(", ");
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function normalizeClusterState(state) {
  const normalized = String(state || "").toUpperCase();
  if (normalized.includes("RUN")) return "running";
  if (normalized.includes("PEND") || normalized.includes("SUBMIT")) return "warning";
  if (normalized.includes("FAIL") || normalized.includes("CANCEL") || normalized.includes("TIMEOUT")) return "failed";
  return "ready";
}

function buildSubmissionPreview(workflow) {
  const execution = workflow.execution_metadata || {};
  const settings = workflow.job_settings || {};
  const uploadedFiles = String(execution.uploaded_files || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  const syncedArtifacts = Array.isArray(execution.synced_artifacts) ? execution.synced_artifacts : [];
  const structureSource = typeof settings.structure_source === "string" ? settings.structure_source.trim() : "";
  const structurePreview = structureSource
    ? structureSource.split("\n").slice(0, 6).join("\n")
    : "Estrutura herdada do template selecionado.";

  return [
    {
      title: "Template aplicado",
      body: `
        <p><strong>Nome:</strong> ${formatValue(execution.template_name)}</p>
        <p><strong>Origem:</strong> ${formatValue(execution.template_source)}</p>
        <p><strong>Perfil:</strong> ${formatValue(execution.template_type)}</p>
      `,
    },
    {
      title: "Arquivos enviados",
      body: uploadedFiles.length
        ? `<ul>${uploadedFiles.map((file) => `<li>${file}</li>`).join("")}</ul>`
        : "<p>Nenhum arquivo listado.</p>",
    },
    {
      title: "Estrutura utilizada",
      body: `<pre>${escapeHtml(structurePreview)}</pre>`,
    },
    {
      title: "Artefatos sincronizados",
      body: syncedArtifacts.length
        ? `<ul>${syncedArtifacts.map((file) => `<li>${file}</li>`).join("")}</ul>`
        : "<p>Nenhum artefato sincronizado ainda.</p>",
    },
  ]
    .map(
      (section) => `
        <article class="preview-item">
          <h4>${section.title}</h4>
          ${section.body}
        </article>
      `,
    )
    .join("");
}

function buildWorkflowPlanPreview(workflow) {
  const execution = workflow.execution_metadata || {};
  const stages = Array.isArray(execution.workflow_stages) ? execution.workflow_stages : [];
  const currentStage = execution.current_stage_name;

  if (!stages.length) {
    return `
      <article class="preview-item">
        <h4>Workflow simples</h4>
        <p>Este workflow nao possui encadeamento cientifico multi-etapa configurado.</p>
      </article>
    `;
  }

  return stages
    .map(
      (stageName, index) => `
        <article class="preview-item">
          <h4>Etapa ${index + 1}: ${stageName}</h4>
          <p>${stageName === currentStage ? "Etapa atual em preparo ou execucao." : "Etapa planejada no pipeline."}</p>
        </article>
      `,
    )
    .join("");
}

function buildFilePreview(filePreviews) {
  if (!filePreviews.length) {
    return `
      <article class="preview-item">
        <h4>Arquivos indisponiveis</h4>
        <p>Nenhum preview carregado.</p>
      </article>
    `;
  }

  return filePreviews
    .map(
      (file) => `
        <article class="preview-item">
          <h4>${file.name}</h4>
          ${
            isEditableFile(file.name)
              ? `
                <div class="preview-editor">
                  <textarea data-file-editor="${file.name}" rows="12">${escapeHtml(file.content || "")}</textarea>
                  <div class="preview-actions">
                    <button type="button" data-save-file="${file.name}">Salvar ${file.name}</button>
                  </div>
                </div>
              `
              : file.exists
                ? `<pre>${escapeHtml(file.content || "(arquivo vazio)")}</pre>`
                : "<p>Arquivo nao encontrado neste workflow.</p>"
          }
        </article>
      `,
    )
    .join("");
}

function isEditableFile(filename) {
  return filename === "INCAR" || filename === "KPOINTS";
}

function bindFileEditors() {
  document.querySelectorAll("[data-save-file]").forEach((button) => {
    button.addEventListener("click", async () => {
      if (!state.selectedWorkflowId) return;

      const filename = button.dataset.saveFile;
      const editor = document.querySelector(`[data-file-editor="${filename}"]`);
      if (!editor) return;

      const payload = {};
      if (filename === "INCAR") {
        payload.incar = editor.value;
      }
      if (filename === "KPOINTS") {
        payload.kpoints = editor.value;
      }

      await request(`/workflows/${state.selectedWorkflowId}/files`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      await selectWorkflow(state.selectedWorkflowId, false);
    });
  });
}

function escapeHtml(text) {
  return text
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

async function loadTemplates() {
  if (!templateSelect) return;
  const templates = await request("/templates");
  state.templates = templates;
  const currentValue = templateSelect.value;

  templateSelect.innerHTML = [
    '<option value="">auto</option>',
    ...templates.map(
      (template) =>
        `<option value="${template.name}">${template.name} (${template.source} | ${template.calc_type})</option>`,
    ),
  ].join("");

  if (templates.some((template) => template.name === currentValue)) {
    templateSelect.value = currentValue;
  }

  updateTemplateHint();
}

async function loadClusterJobs() {
  const scope = clusterScopeSelect?.value || "user";
  state.clusterJobs = await request(`/cluster/jobs?scope=${encodeURIComponent(scope)}`);
  renderClusterJobs();
}

async function loadClusterConfig() {
  state.clusterConfig = await request("/cluster/config");
  renderClusterConfig();
}

async function loadAnalysisResults(workflowId) {
  state.analysisResults = await request(`/workflows/${workflowId}/analysis`);
}

async function loadRecommendationPreview(workflowId) {
  state.recommendationPreview = await request(`/workflows/${workflowId}/recommendation-preview`);
}

function updateRemoteSettingsVisibility() {
  if (!executorSelect || !remoteSettings) return;
  const isRemote = executorSelect.value === "ssh_slurm";
  remoteSettings.classList.toggle("hidden", !isRemote);
}

function updateTemplateHint() {
  if (!templateBadge || !templateHelp || !templateSelect) return;
  const selected = state.templates.find((template) => template.name === templateSelect.value);

  if (!selected) {
    templateBadge.textContent = "template auto";
    templateHelp.textContent =
      "Sem template fixo: o backend escolhe um preset builtin com base no objetivo, no cenario e no tipo de calculo.";
    return;
  }

  templateBadge.textContent = `${selected.source} | ${selected.calc_type}`;
  templateHelp.textContent = `Template selecionado: ${selected.name}. Origem ${selected.source} com perfil ${selected.calc_type}.`;
}

function parseKpointsMesh(formData) {
  const values = ["kx", "ky", "kz"]
    .map((key) => formData.get(key))
    .map((value) => (value ? Number.parseInt(value, 10) : null));

  return values.every((value) => Number.isInteger(value) && value > 0) ? values : null;
}

async function loadWorkflows() {
  state.workflows = await request("/workflows");
  renderWorkflowList();

  const tabFromUrl = readTabFromUrl();
  if (tabFromUrl && Array.from(tabButtons).some((button) => button.dataset.tabTarget === tabFromUrl)) {
    state.activeTab = tabFromUrl;
  }

  const workflowIdFromUrl = readWorkflowIdFromUrl();
  if (workflowIdFromUrl) {
    const fromUrl = state.workflows.find((workflow) => workflow.workflow_id === workflowIdFromUrl);
    if (fromUrl) {
      state.selectedWorkflowId = fromUrl.workflow_id;
      writeNavigationStateToUrl(
        { workflowId: fromUrl.workflow_id, tab: state.activeTab },
        { replace: true },
      );
    }
  }

  if (state.selectedWorkflowId) {
    const existing = state.workflows.find((workflow) => workflow.workflow_id === state.selectedWorkflowId);
    if (existing) {
      await selectWorkflow(existing.workflow_id, false, "replace");
      return;
    }
  }

  if (state.workflows.length && !state.selectedWorkflowId) {
    await selectWorkflow(state.workflows[0].workflow_id, false, "replace");
  }
}

async function selectWorkflow(workflowId, refreshList = true, historyMode = "push") {
  state.selectedWorkflowId = workflowId;
  state.bindingEnergyResult = null;
  state.ecnResult = null;
  writeNavigationStateToUrl(
    { workflowId, tab: state.activeTab },
    { replace: historyMode === "replace" },
  );
  const workflowPromise = request(`/workflows/${workflowId}`);
  const filePreviewPromise = pageMode === "analysis"
    ? Promise.resolve([])
    : request(`/workflows/${workflowId}/files-preview`);
  const analysisPromises = pageMode === "analysis"
    ? [loadAnalysisResults(workflowId), loadRecommendationPreview(workflowId)]
    : [];
  const [workflow, filePreviews] = await Promise.all([workflowPromise, filePreviewPromise, ...analysisPromises]);
  renderWorkflowDetails(workflow, filePreviews);

  if (refreshList) {
    renderWorkflowList();
  }
}

if (workflowForm) {
  workflowForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(workflowForm);
    const structureSource = String(formData.get("structure_source") || "").trim();
    const payload = {
      project_name: formData.get("project_name"),
      goal: formData.get("goal"),
      executor: formData.get("executor"),
      scenario: formData.get("scenario"),
      auto_apply_fixes: formData.get("auto_apply_fixes") === "on",
      template_name: formData.get("template_name") || null,
      calculation_type: formData.get("calculation_type") || null,
      structure_source: structureSource || null,
      kpoints_mesh: parseKpointsMesh(formData),
      workflow_recipe: formData.get("workflow_recipe") || null,
    };

    const workflow = await request("/workflows/mock", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    workflowForm.reset();
    updateRemoteSettingsVisibility();
    updateTemplateHint();
    state.selectedWorkflowId = workflow.workflow_id;
    await loadWorkflows();
  });
}

if (clusterConfigForm) {
  clusterConfigForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(clusterConfigForm);
    const payload = {
      ssh_host: String(formData.get("ssh_host") || "").trim(),
      ssh_user: String(formData.get("ssh_user") || "").trim(),
      remote_base_dir: String(formData.get("remote_base_dir") || "").trim(),
      identity_file: String(formData.get("identity_file") || "").trim() || null,
      dry_run: formData.get("dry_run") === "on",
    };
    const sessionPassword = String(formData.get("session_password") || "").trim();

    const submitButton = clusterConfigForm.querySelector('button[type="submit"]');
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Salvando...";
    }
    try {
      state.clusterConfig = await request("/cluster/config", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (sessionPassword) {
        state.clusterConfig = await request("/cluster/session-password", {
          method: "POST",
          body: JSON.stringify({ password: sessionPassword }),
        });
      }
      renderClusterConfig();
      await loadClusterJobs();
    } finally {
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "Salvar configuracao";
      }
    }
  });
}

if (executorSelect) {
  executorSelect.addEventListener("change", () => {
    updateRemoteSettingsVisibility();
  });
}

if (templateSelect) {
  templateSelect.addEventListener("change", () => {
    updateTemplateHint();
  });
}

if (calculationTypeSelect) {
  calculationTypeSelect.addEventListener("change", () => {
    updateTemplateHint();
  });
}

tabButtons.forEach((button) => {
  button.addEventListener("click", () => {
    state.activeTab = button.dataset.tabTarget;
    renderActiveTab();
    writeNavigationStateToUrl(
      { workflowId: state.selectedWorkflowId, tab: state.activeTab },
      { replace: false },
    );
  });
});

if (bindingEnergyButton && bindingReferenceSelect && bindingEnergyResult) {
  bindingEnergyButton.addEventListener("click", async () => {
    if (!state.selectedWorkflowId) return;
    const referenceIds = Array.from(bindingReferenceSelect.selectedOptions)
      .map((option) => option.value)
      .filter(Boolean);
    if (!referenceIds.length) {
      bindingEnergyResult.innerHTML = `
        <article class="preview-item">
          <h4>Referencias ausentes</h4>
          <p>Selecione ao menos um workflow de referencia para calcular a energia de ligacao.</p>
        </article>
      `;
      return;
    }

    bindingEnergyButton.disabled = true;
    bindingEnergyButton.textContent = "Calculando...";
    try {
      state.bindingEnergyResult = await request("/analysis/binding-energy", {
        method: "POST",
        body: JSON.stringify({
          target_workflow_id: state.selectedWorkflowId,
          reference_workflow_ids: referenceIds,
        }),
      });
      bindingEnergyResult.innerHTML = buildBindingEnergyPreview(state.bindingEnergyResult);
    } finally {
      bindingEnergyButton.disabled = false;
      bindingEnergyButton.textContent = "Calcular energia de ligacao";
    }
  });
}

if (ecnButton && ecnResult) {
  ecnButton.addEventListener("click", async () => {
    if (!state.selectedWorkflowId) return;
    ecnButton.disabled = true;
    ecnButton.textContent = "Calculando...";
    try {
      state.ecnResult = await request(`/workflows/${state.selectedWorkflowId}/ecn`);
      ecnResult.innerHTML = buildEcnPreview(state.ecnResult);
    } finally {
      ecnButton.disabled = false;
      ecnButton.textContent = "Calcular ECN";
    }
  });
}

if (advanceButton) {
  advanceButton.addEventListener("click", async () => {
    if (!state.selectedWorkflowId) return;
    await request(`/workflows/${state.selectedWorkflowId}/advance`, {
      method: "POST",
    });
    await loadWorkflows();
    await loadClusterJobs();
  });
}

if (refreshClusterButton) {
  refreshClusterButton.addEventListener("click", async () => {
    refreshClusterButton.disabled = true;
    refreshClusterButton.textContent = "Atualizando...";
    try {
      await loadClusterJobs();
    } finally {
      refreshClusterButton.disabled = false;
      refreshClusterButton.textContent = "Atualizar fila";
    }
  });
}

if (clusterScopeSelect) {
  clusterScopeSelect.addEventListener("change", async () => {
    await loadClusterJobs();
  });
}

if (refreshAnalysisButton) {
  refreshAnalysisButton.addEventListener("click", async () => {
    if (!state.selectedWorkflowId) return;
    refreshAnalysisButton.disabled = true;
    refreshAnalysisButton.textContent = "Atualizando...";
    try {
      await Promise.all([
        loadAnalysisResults(state.selectedWorkflowId),
        loadRecommendationPreview(state.selectedWorkflowId),
      ]);
      await selectWorkflow(state.selectedWorkflowId, false);
    } finally {
      refreshAnalysisButton.disabled = false;
      refreshAnalysisButton.textContent = "Atualizar analises";
    }
  });
}

if (applyRecommendationButton) {
  applyRecommendationButton.addEventListener("click", async () => {
    if (!state.selectedWorkflowId) return;
    applyRecommendationButton.disabled = true;
    applyRecommendationButton.textContent = "Aplicando...";
    try {
      const createdWorkflow = await request(`/workflows/${state.selectedWorkflowId}/apply-recommendation`, {
        method: "POST",
      });
      state.selectedWorkflowId = createdWorkflow.workflow_id;
      await loadWorkflows();
    } finally {
      applyRecommendationButton.disabled = false;
      applyRecommendationButton.textContent = "Aplicar recomendacao";
    }
  });
}

window.addEventListener("popstate", async () => {
  const workflowIdFromUrl = readWorkflowIdFromUrl();
  const tabFromUrl = readTabFromUrl();
  const previousTab = state.activeTab;
  if (tabFromUrl && Array.from(tabButtons).some((button) => button.dataset.tabTarget === tabFromUrl)) {
    state.activeTab = tabFromUrl;
  }
  if ((!workflowIdFromUrl || workflowIdFromUrl === state.selectedWorkflowId) && previousTab !== state.activeTab) {
    renderActiveTab();
    return;
  }
  if (!workflowIdFromUrl || workflowIdFromUrl === state.selectedWorkflowId) return;
  const existing = state.workflows.find((workflow) => workflow.workflow_id === workflowIdFromUrl);
  if (!existing) {
    await loadWorkflows();
    return;
  }
  state.selectedWorkflowId = workflowIdFromUrl;
  const workflowPromise = request(`/workflows/${workflowIdFromUrl}`);
  const filePreviewPromise = pageMode === "analysis"
    ? Promise.resolve([])
    : request(`/workflows/${workflowIdFromUrl}/files-preview`);
  const analysisPromises = pageMode === "analysis"
    ? [loadAnalysisResults(workflowIdFromUrl), loadRecommendationPreview(workflowIdFromUrl)]
    : [];
  const [workflow, filePreviews] = await Promise.all([workflowPromise, filePreviewPromise, ...analysisPromises]);
  state.bindingEnergyResult = null;
  renderWorkflowDetails(workflow, filePreviews);
  renderWorkflowList();
});

loadWorkflows().catch((error) => {
  if (workflowList) {
    workflowList.innerHTML = `<div class="empty-state">${error.message}</div>`;
  }
});

if (clusterJobsList) {
  loadClusterJobs().catch((error) => {
    clusterJobsList.innerHTML = `<div class="empty-state">${error.message}</div>`;
  });
}

if (clusterConfigSummary || clusterConfigForm) {
  loadClusterConfig().catch((error) => {
    if (clusterConfigSummary) {
      clusterConfigSummary.innerHTML = `<div class="empty-state">${error.message}</div>`;
    }
    if (clusterModeNote) {
      clusterModeNote.textContent = error.message;
    }
  });
}

if (templateSelect) {
  loadTemplates().catch((error) => {
    templateSelect.innerHTML = `<option value="">${error.message}</option>`;
  });
}

updateRemoteSettingsVisibility();
