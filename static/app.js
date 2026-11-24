const $ = (selector) => document.querySelector(selector);
const statusNames = {unverified: "Not checked yet", reviewed: "Reviewed", corroborated: "Independent support found", disputed: "Disputed"};
const alertStatusNames = {needs_action: "Needs action", reported: "Reported", removed: "Removed", false_positive: "Not a match"};
let researchCases = [];
let activeCase = null;

// Old uncached forms could put entered research text in the home-page URL.
if (window.location.pathname === "/" && window.location.search) {
  window.history.replaceState({}, "", "/");
}

function caseId() {
  return activeCase ? String(activeCase.id) : null;
}

function updateCaseSummary() {
  const summary = $("#case-summary");
  const statusButton = $("#case-status-button");
  const protectedButtons = [
    $("#search-form button"), $("#exposure-form button"), $("#evidence-form button"),
  ];
  const canCollect = Boolean(activeCase && activeCase.status === "open");
  protectedButtons.forEach((button) => { button.disabled = !canCollect; });
  statusButton.hidden = !activeCase;
  if (activeCase) {
    statusButton.textContent = activeCase.status === "open" ? "Close case" : "Reopen case";
    summary.textContent = `${activeCase.status === "open" ? "Open case" : "Closed case"} · ${activeCase.question}\nScope: ${activeCase.scope}\nAuthority recorded: ${activeCase.authorization_basis.replaceAll("_", " ")} · ${activeCase.evidence_count} source(s) · ${activeCase.alert_count} alert(s)`;
  } else if ($("#case-select").value === "all") {
    summary.textContent = "Viewing all saved records, including older records not assigned to a case. You can review saved records here; select an open case or create one to collect new sources.";
  } else {
    summary.textContent = "Select or create a research case before searching or saving sources.";
  }
}

async function loadCases(preferredId = null) {
  researchCases = await api("/cases");
  const select = $("#case-select");
  const savedChoice = preferredId || localStorage.getItem("atlas.activeCaseId");
  select.replaceChildren();
  const allOption = document.createElement("option");
  allOption.value = "all";
  allOption.textContent = "All saved records";
  select.append(allOption);
  researchCases.forEach((item) => {
    const option = document.createElement("option");
    option.value = String(item.id);
    option.textContent = `${item.title} · ${item.status}`;
    select.append(option);
  });
  select.value = researchCases.some((item) => String(item.id) === String(savedChoice))
    ? String(savedChoice) : "all";
  activeCase = researchCases.find((item) => String(item.id) === select.value) || null;
  if (activeCase) localStorage.setItem("atlas.activeCaseId", String(activeCase.id));
  updateCaseSummary();
  await Promise.all([loadEvidence(), loadAlerts(), loadCaseActivity()]);
}

async function loadCaseActivity() {
  const list = $("#case-activity-list");
  list.replaceChildren();
  if (!activeCase) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "Select a case to view its activity.";
    list.append(empty);
    return;
  }
  const events = await api(`/cases/${activeCase.id}/activity?limit=50`);
  if (!events.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No activity recorded for this case yet.";
    list.append(empty);
    return;
  }
  events.forEach((event) => {
    const item = document.createElement("article");
    item.className = "activity-item";
    const summary = document.createElement("p");
    summary.textContent = event.summary;
    const timestamp = document.createElement("time");
    timestamp.dateTime = event.occurred_at;
    timestamp.textContent = new Date(event.occurred_at).toLocaleString();
    item.append(summary, timestamp);
    list.append(item);
  });
}

async function createCase(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const fields = new FormData(form);
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    const item = await api("/cases", {
      method: "POST",
      body: JSON.stringify({
        title: fields.get("title").trim(),
        question: fields.get("question").trim(),
        scope: fields.get("scope").trim(),
        authorization_basis: fields.get("authorization_basis"),
        authorized: fields.get("authorized") === "on",
      }),
    });
    form.reset();
    localStorage.setItem("atlas.activeCaseId", String(item.id));
    await loadCases(item.id);
    showMessage("#case-message", "Case created. New searches and saved sources will be attached to it.");
  } catch (error) {
    showMessage("#case-message", error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function toggleCaseStatus() {
  if (!activeCase) return;
  const status = activeCase.status === "open" ? "closed" : "open";
  try {
    await api(`/cases/${activeCase.id}`, {method: "PATCH", body: JSON.stringify({status})});
    await loadCases(activeCase.id);
    showMessage("#case-message", status === "closed" ? "Case closed. Its saved records remain available." : "Case reopened.");
  } catch (error) {
    showMessage("#case-message", error.message, true);
  }
}

function showMessage(selector, message, isError = false) {
  const element = $(selector);
  element.textContent = message;
  element.classList.toggle("error", isError);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Content-Type": "application/json", ...(options.headers || {})},
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = body.detail;
    const message = Array.isArray(detail)
      ? detail.map((item) => {
          if (item?.type === "string_pattern_mismatch") return "Enter a username using letters, numbers, dots, underscores, or hyphens; @ at the beginning is optional.";
          if (item?.type === "missing") return "Fill in all required fields and try again.";
          return item?.msg || "Check the information and try again.";
        }).join(" ")
      : typeof detail === "string" ? detail : `Request failed (${response.status}).`;
    throw new Error(message);
  }
  return body;
}

function addLink(container, url, label) {
  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = label || url;
  container.append(link);
}

function resultCard(result) {
  const card = document.createElement("article");
  card.className = "result-card";
  const title = document.createElement("h3");
  title.textContent = result.title || "Untitled source";
  const source = document.createElement("span");
  source.className = "source-tag";
  source.textContent = result.source || "Public source";
  const titleRow = document.createElement("div");
  titleRow.className = "result-heading";
  titleRow.append(title, source);
  card.append(titleRow);
  if (result.url) addLink(card, result.url, result.url);
  if (result.snippet) {
    const snippet = document.createElement("p");
    snippet.textContent = result.snippet;
    card.append(snippet);
  }
  return card;
}

function showCoverage(items) {
  const list = $("#coverage-list");
  list.replaceChildren();
  items.forEach((item) => {
    const row = document.createElement("div");
    row.className = "coverage-item";
    const text = document.createElement("span");
    const count = item.result_count === 1 ? "1 result" : `${item.result_count} results`;
    text.textContent = `${item.source}: ${count}${item.saved_count ? `, ${item.saved_count} saved` : ""}`;
    const state = document.createElement("span");
    state.className = `coverage-status coverage-${item.status}`;
    state.textContent = item.status.replaceAll("_", " ");
    row.append(text, state);
    if (item.note) {
      const note = document.createElement("small");
      note.textContent = item.note;
      row.append(note);
    }
    list.append(row);
  });
}

async function runSearch(event) {
  event.preventDefault();
  if (!activeCase || activeCase.status !== "open") {
    showMessage("#search-message", "Choose or create an open case before searching.", true);
    return;
  }
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  showMessage("#search-message", "Searching public sources…");
  $("#search-results").replaceChildren();
  try {
    const params = new URLSearchParams({q: $("#query").value.trim(), limit: "5", case_id: caseId()});
    const data = await api(`/research?${params}`);
    showCoverage(data.coverage);
    if (data.results_count === 0) {
      showMessage("#search-message", "None of the connected sources returned a match. Try a shorter phrase or another spelling. This does not mean the information does not exist elsewhere.");
    } else {
      showMessage("#search-message", `Found ${data.results_count} result(s) across the connected sources; saved ${data.saved_to_database}. Saved links are not automatically fact-checked.`);
    }
    data.results.forEach((result) => $("#search-results").append(resultCard(result)));
    await loadCases(caseId());
  } catch (error) {
    showCoverage([]);
    showMessage("#search-message", error.message, true);
  } finally {
    button.disabled = false;
  }
}

async function runExposureCheck(event) {
  event.preventDefault();
  if (!activeCase || activeCase.status !== "open") {
    showMessage("#exposure-message", "Choose or create an open case before checking a username.", true);
    return;
  }
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  showMessage("#exposure-message", "Checking search-result snippets. The matching page text and direct link will not be shown or saved…");
  try {
    const data = await api("/exposure-check?limit=10", {
      method: "POST",
      body: JSON.stringify({platform: $("#platform").value, username: $("#username").value.trim().replace(/^@/, ""), case_id: activeCase.id, authorized: true}),
    });
    $("#username").value = "";
    const direct = data.direct_check;
    const directSummary = direct.status === "found"
      ? `Direct ${data.platform} check: a public profile exists.`
      : direct.status === "not_found"
        ? `Direct ${data.platform} check: no public profile was returned for that username.`
        : `${data.platform} direct check: ${direct.message}`;
    const providerSummary = data.index_check.providers
      .map((item) => `${item.provider}: ${item.status.replaceAll("_", " ")} (${item.result_count})`)
      .join("; ");
    const indexSummary = data.index_check.status === "unavailable"
      ? `Web index check unavailable. ${providerSummary}.`
      : data.index_check.status === "no_results"
        ? `No indexed matches across the checked search engines; this is not proof that none exist. ${providerSummary}.`
        : `${data.provider} returned ${data.results_count} indexed result(s). ${providerSummary}.`;
    showMessage("#exposure-message", `${directSummary} ${indexSummary} ${data.notice} Saved ${data.alerts_saved} redacted alert(s).`);
    const directLink = $("#username-profile-link");
    directLink.replaceChildren();
    if (direct.profile_url) addLink(directLink, direct.profile_url, "Open the public GitHub profile");
    await loadCases(caseId());
  } catch (error) {
    $("#username-profile-link").replaceChildren();
    showMessage("#exposure-message", error.message, true);
  } finally {
    button.disabled = false;
  }
}

function alertCard(alert, controls = true) {
  const card = document.createElement("article");
  card.className = "record alert-record";
  const head = document.createElement("div");
  head.className = "record-head";
  const title = document.createElement("h3");
  title.textContent = alert.category;
  const badge = document.createElement("span");
  badge.className = `status alert-status-${alert.status || "needs_action"}`;
  badge.textContent = alertStatusNames[alert.status || "needs_action"];
  head.append(title, badge);
  card.append(head);
  const domain = document.createElement("p");
  const relatedCase = researchCases.find((entry) => entry.id === alert.case_id);
  domain.textContent = `Website: ${alert.source_domain} · Platform: ${alert.platform} · Case: ${relatedCase?.title || "Unassigned legacy record"}`;
  card.append(domain);
  const reportLink = document.createElement("a");
  reportLink.href = alert.report_url;
  reportLink.target = "_blank";
  reportLink.rel = "noopener noreferrer";
  reportLink.textContent = "Open the platform’s reporting instructions";
  card.append(reportLink);
  const meta = document.createElement("div");
  meta.className = "record-meta";
  meta.textContent = alert.recorded_at
    ? `Possible match · ${new Date(alert.recorded_at).toLocaleString()}`
    : "Possible match · just now";
  card.append(meta);
  if (!controls) return card;

  const controlsRow = document.createElement("div");
  controlsRow.className = "record-actions";
  const select = document.createElement("select");
  Object.entries(alertStatusNames).forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    option.selected = value === alert.status;
    select.append(option);
  });
  const save = document.createElement("button");
  save.type = "button";
  save.textContent = "Update status";
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await api(`/exposure-alerts/${alert.id}`, {method: "PATCH", body: JSON.stringify({status: select.value})});
      await loadAlerts();
    } catch (error) {
      showMessage("#exposure-message", error.message, true);
    } finally {
      save.disabled = false;
    }
  });
  controlsRow.append(select, save);
  card.append(controlsRow);
  return card;
}

async function loadAlerts() {
  const params = new URLSearchParams();
  if (activeCase) params.set("case_id", activeCase.id);
  const alerts = await api(`/exposure-alerts?${params}`);
  const list = $("#alerts-list");
  list.replaceChildren();
  if (!alerts.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No exposure alerts saved yet.";
    list.append(empty);
    return;
  }
  alerts.forEach((alert) => list.append(alertCard(alert)));
}

function evidenceCard(item) {
  const card = document.createElement("article");
  card.className = "record";
  const head = document.createElement("div");
  head.className = "record-head";
  const title = document.createElement("h3");
  title.textContent = item.title;
  const badge = document.createElement("span");
  badge.className = `status status-${item.verification_status}`;
  badge.textContent = statusNames[item.verification_status] || item.verification_status;
  head.append(title, badge);
  card.append(head);
  addLink(card, item.source_url, item.source_url);
  if (item.description) {
    const note = document.createElement("p");
    note.textContent = item.description;
    card.append(note);
  }
  const meta = document.createElement("div");
  meta.className = "record-meta";
  const type = document.createElement("span");
  const relatedCase = researchCases.find((entry) => entry.id === item.case_id);
  const caseLabel = relatedCase ? `Case: ${relatedCase.title}` : "Unassigned legacy record";
  type.textContent = `${item.source_type || "source"} · ${caseLabel}`;
  const date = document.createElement("span");
  date.textContent = new Date(item.recorded_at).toLocaleString();
  meta.append(type, date);
  card.append(meta);
  if (item.verification_note) {
    const verificationNote = document.createElement("p");
    verificationNote.textContent = `Review note: ${item.verification_note}`;
    card.append(verificationNote);
  }
  const controls = document.createElement("div");
  controls.className = "record-actions";
  const select = document.createElement("select");
  Object.entries(statusNames).forEach(([value, text]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = text;
    option.selected = value === item.verification_status;
    select.append(option);
  });
  const noteInput = document.createElement("input");
  noteInput.maxLength = 2000;
  noteInput.placeholder = "What did you check? (optional)";
  noteInput.value = item.verification_note || "";
  const save = document.createElement("button");
  save.type = "button";
  save.textContent = "Save review";
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await api(`/evidence/${item.id}/verification`, {
        method: "PATCH",
        body: JSON.stringify({status: select.value, note: noteInput.value}),
      });
      await loadEvidence();
    } catch (error) {
      showMessage("#evidence-message", error.message, true);
    } finally {
      save.disabled = false;
    }
  });
  controls.append(select, noteInput, save);
  card.append(controls);
  return card;
}

async function loadEvidence() {
  const params = new URLSearchParams();
  const search = $("#evidence-search").value.trim();
  const status = $("#evidence-status").value;
  if (search) params.set("search", search);
  if (status) params.set("status", status);
  if (activeCase) params.set("case_id", activeCase.id);
  const data = await api(`/evidence?${params}`);
  const list = $("#evidence-list");
  list.replaceChildren();
  $("#evidence-count").textContent = data.length;
  if (!data.length) {
    const empty = document.createElement("p");
    empty.className = "empty";
    empty.textContent = "No saved sources match this filter yet.";
    list.append(empty);
    return;
  }
  data.forEach((item) => list.append(evidenceCard(item)));
}

async function addEvidence(event) {
  event.preventDefault();
  if (!activeCase || activeCase.status !== "open") {
    showMessage("#evidence-message", "Choose or create an open case before saving a source.", true);
    return;
  }
  const form = event.currentTarget;
  const fields = new FormData(form);
  const button = form.querySelector("button");
  button.disabled = true;
  try {
    await api("/evidence", {
      method: "POST",
      body: JSON.stringify({
        title: fields.get("title").trim(),
        source_url: fields.get("source_url").trim(),
        description: fields.get("description").trim(),
        source_type: "manual",
        case_id: activeCase.id,
      }),
    });
    form.reset();
    showMessage("#evidence-message", "Saved. The source starts as not checked yet until you review it.");
    await loadCases(caseId());
  } catch (error) {
    showMessage("#evidence-message", error.message, true);
  } finally {
    button.disabled = false;
  }
}

$("#search-form").addEventListener("submit", runSearch);
$("#exposure-form").addEventListener("submit", runExposureCheck);
$("#evidence-form").addEventListener("submit", addEvidence);
$("#case-create-form").addEventListener("submit", createCase);
$("#case-status-button").addEventListener("click", toggleCaseStatus);
$("#case-select").addEventListener("change", () => {
  const selected = $("#case-select").value;
  activeCase = researchCases.find((item) => String(item.id) === selected) || null;
  if (activeCase) localStorage.setItem("atlas.activeCaseId", String(activeCase.id));
  else localStorage.removeItem("atlas.activeCaseId");
  updateCaseSummary();
  Promise.all([loadEvidence(), loadAlerts(), loadCaseActivity()]).catch((error) => showMessage("#case-message", error.message, true));
});
$("#refresh-evidence").addEventListener("click", () => loadEvidence().catch((e) => showMessage("#evidence-message", e.message, true)));
$("#refresh-alerts").addEventListener("click", () => loadAlerts().catch((e) => showMessage("#exposure-message", e.message, true)));
$("#evidence-status").addEventListener("change", () => loadEvidence().catch((e) => showMessage("#evidence-message", e.message, true)));
let searchTimer;
$("#evidence-search").addEventListener("input", () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => loadEvidence().catch((e) => showMessage("#evidence-message", e.message, true)), 250);
});
$("#year").textContent = new Date().getFullYear();
loadCases().catch((error) => showMessage("#case-message", error.message, true));
