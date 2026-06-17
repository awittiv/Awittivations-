const API = "";
let activeTab = "text";
let selectedFile = null;
const cdliAtfCache = {};

// ── Tab switching ────────────────────────────────────────────────────────────

function switchTab(tab) {
  activeTab = tab;
  document.getElementById("panel-text").hidden  = tab !== "text";
  document.getElementById("panel-image").hidden = tab !== "image";
  document.getElementById("panel-cdli").hidden  = tab !== "cdli";
  document.getElementById("tab-text").classList.toggle("active",  tab === "text");
  document.getElementById("tab-image").classList.toggle("active", tab === "image");
  document.getElementById("tab-cdli").classList.toggle("active",  tab === "cdli");
  document.getElementById("translate-btn").hidden = tab === "cdli";
  hideResult();
}

// ── Image drop zone ──────────────────────────────────────────────────────────

function initDropZone() {
  const zone = document.getElementById("drop-zone");
  const input = document.getElementById("image-input");

  zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drag-over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("drag-over"));
  zone.addEventListener("drop", e => {
    e.preventDefault();
    zone.classList.remove("drag-over");
    const file = e.dataTransfer.files[0];
    if (file) setImage(file);
  });

  input.addEventListener("change", () => {
    if (input.files[0]) setImage(input.files[0]);
  });
}

function setImage(file) {
  selectedFile = file;
  const reader = new FileReader();
  reader.onload = e => {
    document.getElementById("image-preview").src = e.target.result;
    document.getElementById("drop-zone-inner").hidden = true;
    document.getElementById("image-preview-wrap").hidden = false;
  };
  reader.readAsDataURL(file);
}

function clearImage() {
  selectedFile = null;
  document.getElementById("image-input").value = "";
  document.getElementById("image-preview").src = "";
  document.getElementById("drop-zone-inner").hidden = false;
  document.getElementById("image-preview-wrap").hidden = true;
  hideResult();
}

// ── Submit ───────────────────────────────────────────────────────────────────

async function submitTranslation() {
  if (activeTab === "text") {
    await translateText();
  } else {
    await translateImage();
  }
}

async function translateText() {
  const text = document.getElementById("input-text").value.trim();
  if (!text) return;

  setLoading(true);
  try {
    const res = await fetch(`${API}/api/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Translation failed");
    renderResult(await res.json());
  } catch (e) {
    showError(e.message);
  } finally {
    setLoading(false);
  }
}

async function translateImage() {
  if (!selectedFile) { showError("Please select a tablet photo first."); return; }

  setLoading(true);
  try {
    const form = new FormData();
    form.append("file", selectedFile);
    const res = await fetch(`${API}/api/translate-image`, { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail || "Translation failed");
    renderResult(await res.json(), true);
  } catch (e) {
    showError(e.message);
  } finally {
    setLoading(false);
  }
}

// ── Render ───────────────────────────────────────────────────────────────────

function renderResult(data, fromImage = false) {
  document.getElementById("badge-language").textContent = data.language;
  document.getElementById("badge-genre").textContent = data.genre;

  const periodBadge = document.getElementById("badge-period");
  periodBadge.textContent = data.period || "";
  periodBadge.hidden = !data.period;

  const confEl = document.getElementById("confidence-indicator");
  confEl.textContent = `Confidence: ${data.confidence}`;
  confEl.className = `confidence conf-${data.confidence}`;
  confEl.title = data.confidence_reason;

  const transBox = document.getElementById("transliteration-box");
  if (fromImage && data.transliteration) {
    document.getElementById("transliteration-text").textContent = data.transliteration;
    transBox.hidden = false;
  } else {
    transBox.hidden = true;
  }

  document.getElementById("translation-text").textContent = data.translation;

  const notesBox = document.getElementById("notes-box");
  const notesList = document.getElementById("notes-list");
  notesList.innerHTML = "";
  if (data.notes?.length) {
    data.notes.forEach(note => {
      const li = document.createElement("li");
      li.textContent = note;
      notesList.appendChild(li);
    });
    notesBox.hidden = false;
  } else {
    notesBox.hidden = true;
  }

  document.getElementById("error-box").hidden = true;
  document.getElementById("result-section").hidden = false;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function setLoading(on) {
  const btn = document.getElementById("translate-btn");
  btn.disabled = on;
  btn.textContent = on ? "Translating..." : "Translate";
}

function showError(msg) {
  document.getElementById("error-text").textContent = msg;
  document.getElementById("error-box").hidden = false;
  document.getElementById("result-section").hidden = true;
}

function hideResult() {
  document.getElementById("result-section").hidden = true;
  document.getElementById("error-box").hidden = true;
}

async function loadExamples() {
  try {
    const res = await fetch(`${API}/api/examples`);
    const examples = await res.json();
    const container = document.getElementById("example-buttons");
    examples.forEach(ex => {
      const btn = document.createElement("button");
      btn.className = "example-btn";
      btn.textContent = ex.label;
      btn.onclick = () => { document.getElementById("input-text").value = ex.text; };
      container.appendChild(btn);
    });
  } catch (_) {}
}

// ── CDLI Search ──────────────────────────────────────────────────────────────

async function loadCDLIFilters() {
  try {
    const res = await fetch(`${API}/api/cdli/filters`);
    const { periods, genres } = await res.json();
    const pSel = document.getElementById("cdli-period");
    const gSel = document.getElementById("cdli-genre");
    periods.forEach(p => { const o = document.createElement("option"); o.value = o.textContent = p; pSel.appendChild(o); });
    genres.forEach(g => { const o = document.createElement("option"); o.value = o.textContent = g; gSel.appendChild(o); });
  } catch (_) {}
}

async function cdliSearch() {
  const period = document.getElementById("cdli-period").value;
  const genre  = document.getElementById("cdli-genre").value;
  const btn = document.getElementById("cdli-search-btn");
  const container = document.getElementById("cdli-results");

  btn.disabled = true;
  btn.textContent = "Browsing…";
  container.innerHTML = '<p class="cdli-loading">Fetching tablets from CDLI…</p>';

  try {
    const params = new URLSearchParams({ limit: 12 });
    if (period) params.set("period", period);
    if (genre)  params.set("genre", genre);
    const res = await fetch(`${API}/api/cdli/search?${params}`);
    if (!res.ok) throw new Error((await res.json()).detail || "Browse failed");
    renderCDLIResults(await res.json());
  } catch (e) {
    container.innerHTML = `<p class="cdli-error">${e.message}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Browse";
  }
}

async function cdliLookup() {
  const p = document.getElementById("cdli-pnum-input").value.trim();
  if (!p) return;
  const btn = document.getElementById("cdli-pnum-btn");
  const container = document.getElementById("cdli-results");

  btn.disabled = true;
  btn.textContent = "…";
  container.innerHTML = '<p class="cdli-loading">Looking up tablet…</p>';

  try {
    const res = await fetch(`${API}/api/cdli/search?p_number=${encodeURIComponent(p)}`);
    if (!res.ok) throw new Error((await res.json()).detail || "Lookup failed");
    renderCDLIResults(await res.json());
  } catch (e) {
    container.innerHTML = `<p class="cdli-error">${e.message}</p>`;
  } finally {
    btn.disabled = false;
    btn.textContent = "Lookup";
  }
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function atfSnippet(atf) {
  return atf.split("\n")
    .filter(l => /^\d+['.]/.test(l.trim()))
    .slice(0, 3)
    .map(l => escapeHtml(l.trim()))
    .join("\n");
}

function renderCDLIResults(results) {
  const container = document.getElementById("cdli-results");
  if (!results.length) {
    container.innerHTML = '<p class="cdli-empty">No tablets found. Try different filters.</p>';
    return;
  }

  results.forEach(r => { if (r.atf) cdliAtfCache[r.p_number] = r.atf; });

  container.innerHTML = results.map(r => {
    const snippet = r.atf ? atfSnippet(r.atf) : "";
    return `
    <div class="cdli-card">
      <div class="cdli-thumb-wrap">
        <img class="cdli-thumb" src="${r.photo_url}" alt="${escapeHtml(r.designation)}"
             onerror="this.parentElement.classList.add('no-photo')" loading="lazy" />
      </div>
      <div class="cdli-info">
        <div class="cdli-pnum">
          ${r.p_number}
          ${r.atf ? '<span class="cdli-atf-badge">ATF</span>' : ""}
        </div>
        <div class="cdli-designation">${escapeHtml(r.designation || "—")}</div>
        ${r.period ? `<div class="cdli-meta">${escapeHtml(r.period)}</div>` : ""}
        ${r.genres.length ? `<div class="cdli-meta">${r.genres.map(escapeHtml).join(" · ")}</div>` : ""}
        ${r.museum_no ? `<div class="cdli-museum">${escapeHtml(r.museum_no)}</div>` : ""}
        ${snippet ? `<pre class="cdli-atf-snippet">${snippet}</pre>` : ""}
      </div>
      <button class="cdli-translate-btn" onclick="cdliTranslate('${r.p_number}', this)">
        Translate
      </button>
    </div>`;
  }).join("");
}

async function cdliTranslate(pNumber, btn) {
  btn.disabled = true;
  btn.textContent = "Translating…";
  hideResult();

  const atfText = cdliAtfCache[pNumber] || null;

  try {
    const res = await fetch(`${API}/api/cdli/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ p_number: pNumber, atf_text: atfText }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Translation failed");
    renderResult(await res.json(), true);
    document.getElementById("result-section").scrollIntoView({ behavior: "smooth" });
  } catch (e) {
    showError(`${pNumber}: ${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = "Translate";
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadExamples();
  initDropZone();
  document.getElementById("input-text").addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitTranslation();
  });
  document.getElementById("cdli-pnum-input").addEventListener("keydown", e => {
    if (e.key === "Enter") cdliLookup();
  });
  loadCDLIFilters();
});
