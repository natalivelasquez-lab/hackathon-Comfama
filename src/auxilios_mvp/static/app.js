const state = {
  dashboard: null,
  selected: new Set(),
};

const $ = (id) => document.getElementById(id);

async function getJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || "Solicitud no completada");
  }
  return payload;
}

function showToast(message) {
  const toast = $("toast");
  toast.textContent = message;
  toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2600);
}

function statusLabel(status) {
  if (status === "NUEVA") return "Nueva";
  if (status === "MODIFICADA") return "Modificada";
  return "Procesada";
}

function decisionLabel(status) {
  if (status === "APROBAR") return "Aprobada";
  if (status === "RECHAZAR") return "Rechazada";
  return "Revisión";
}

function setText(id, value) {
  $(id).textContent = value ?? "";
}

async function refreshDashboard() {
  const dashboard = await getJson("/api/dashboard");
  state.dashboard = dashboard;
  renderDashboard(dashboard);
}

function renderDashboard(dashboard) {
  const counts = dashboard.counts || {};
  setText("notificationBadge", counts.notifications || 0);
  setText(
    "notificationText",
    counts.notifications ? `${counts.notifications} solicitud(es) por revisar` : "Sin solicitudes nuevas"
  );
  setText("countTotal", counts.total || 0);
  setText("countNew", counts.new || 0);
  setText("countModified", counts.modified || 0);
  setText("countProcessed", counts.processed || 0);
  setText("approvedTotal", counts.approved || 0);
  setText("rejectedTotal", counts.rejected || 0);
  setText("reviewTotal", counts.review || 0);
  setText("drawerApproved", counts.approved || 0);
  setText("drawerRejected", counts.rejected || 0);
  setText("drawerReview", counts.review || 0);
  setText("requestsPath", dashboard.requests_dir || "");
  renderRequests(dashboard.requests || []);
  renderRecommendations(dashboard.recommendations || []);
  renderJob(dashboard.job || {});
}

function renderRequests(requests) {
  const root = $("requestList");
  if (!requests.length) {
    root.innerHTML = `<div class="request-item"><div><div class="request-title">No hay solicitudes cargadas</div><div class="request-meta">La carpeta local no contiene expedientes pendientes.</div></div></div>`;
    return;
  }
  root.innerHTML = requests
    .map(
      (item) => `
        <article class="request-item">
          <div>
            <div class="request-title">${item.request_id || "Sin solicitud"} · ${item.benefit_code || "Sin beneficio"}</div>
            <div class="request-meta">Empleado ${item.employee_id || "sin cédula"} · ${item.files_count || 0} archivo(s)</div>
            <div class="request-meta">${item.recommendation?.summary || "Sin recomendación registrada"}</div>
          </div>
          <span class="tag ${item.status}">${statusLabel(item.status)}</span>
        </article>
      `
    )
    .join("");
}

function renderRecommendations(recommendations) {
  const root = $("recommendationsTable");
  if (!recommendations.length) {
    root.innerHTML = `<tr><td colspan="8">No hay recomendaciones generadas todavía.</td></tr>`;
    return;
  }
  root.innerHTML = recommendations
    .map((item) => {
      const checked = state.selected.has(item.id) ? "checked" : "";
      const approved = item.approved ? `<span class="approved-mark">Aprobada</span>` : "Pendiente";
      const confidence = item.confidence === null || item.confidence === undefined ? "" : Number(item.confidence).toFixed(2);
      return `
        <tr>
          <td><input class="row-check" type="checkbox" data-id="${item.id}" ${checked} aria-label="Seleccionar ${item.request_id || ""}"></td>
          <td>${item.request_id || ""}</td>
          <td>${item.employee_id || ""}</td>
          <td>${item.benefit_code || ""}</td>
          <td><span class="decision ${item.recommended_status}">${decisionLabel(item.recommended_status)}</span></td>
          <td>${confidence}</td>
          <td>${item.summary || ""}</td>
          <td>${approved}</td>
        </tr>
      `;
    })
    .join("");
  document.querySelectorAll(".row-check").forEach((checkbox) => {
    checkbox.addEventListener("change", (event) => {
      const id = event.target.dataset.id;
      if (event.target.checked) state.selected.add(id);
      else state.selected.delete(id);
    });
  });
}

function renderJob(job) {
  setText("jobStatus", job.running ? "Ejecución activa" : job.error ? "Ejecución con error" : "Sin ejecución activa");
  const logs = job.logs || [];
  $("logBox").innerHTML = logs.length
    ? logs.map((item) => `<div class="log-line"><strong>${item.time}</strong> ${item.message}</div>`).join("")
    : `<div class="log-line">Sin eventos recientes.</div>`;
  $("logBox").scrollTop = $("logBox").scrollHeight;
  const text = logs.map((item) => item.message).join(" ");
  setStep("stepScan", true);
  setStep("stepAnalyze", /Analizando documento|Solicitudes detectadas/.test(text));
  setStep("stepRecommend", /Generando recomendacion|Resultado:/.test(text));
  setStep("stepOutput", /Escribiendo archivos|Proceso terminado/.test(text));
}

function setStep(id, active) {
  $(id).classList.toggle("active", Boolean(active));
}

async function startAnalysis(mode) {
  const payload = await getJson("/api/analyze", {
    method: "POST",
    body: JSON.stringify({ mode }),
  });
  showToast(payload.message || "Análisis iniciado");
  await refreshDashboard();
}

async function approveSelected() {
  const ids = [...state.selected];
  if (!ids.length) {
    showToast("No hay recomendaciones seleccionadas");
    return;
  }
  await getJson("/api/recommendations/approve", {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
  showToast("Recomendaciones aprobadas");
  await refreshDashboard();
}

async function sendSusFactory() {
  const ids = [...state.selected];
  if (!ids.length) {
    showToast("No hay recomendaciones seleccionadas");
    return;
  }
  const payload = await getJson("/api/sus-factory", {
    method: "POST",
    body: JSON.stringify({ ids }),
  });
  showToast(payload.message || "Acción registrada");
  await refreshDashboard();
}

function toggleMetrics(open) {
  $("metricsDrawer").classList.toggle("open", open);
  $("metricsDrawer").setAttribute("aria-hidden", open ? "false" : "true");
}

function bindEvents() {
  $("analyzePending").addEventListener("click", () => startAnalysis("pending").catch((error) => showToast(error.message)));
  $("reprocessAll").addEventListener("click", () => startAnalysis("all").catch((error) => showToast(error.message)));
  $("refreshDashboard").addEventListener("click", () => refreshDashboard().then(() => showToast("Vista actualizada")));
  $("approveSelected").addEventListener("click", () => approveSelected().catch((error) => showToast(error.message)));
  $("sendSusFactory").addEventListener("click", () => sendSusFactory().catch((error) => showToast(error.message)));
  $("metricsButton").addEventListener("click", () => toggleMetrics(true));
  $("closeMetrics").addEventListener("click", () => toggleMetrics(false));
  $("selectAll").addEventListener("change", (event) => {
    state.selected.clear();
    if (event.target.checked && state.dashboard) {
      (state.dashboard.recommendations || []).forEach((item) => state.selected.add(item.id));
    }
    renderRecommendations(state.dashboard?.recommendations || []);
  });
}

bindEvents();
refreshDashboard().catch((error) => showToast(error.message));
setInterval(refreshDashboard, 3000);

if (document.body.dataset.openMetrics === "true") {
  toggleMetrics(true);
}
