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
  document.getElementById("panel-ml").hidden    = tab !== "ml";
  document.getElementById("panel-pe").hidden    = tab !== "pe";
  document.getElementById("tab-text").classList.toggle("active",  tab === "text");
  document.getElementById("tab-image").classList.toggle("active", tab === "image");
  document.getElementById("tab-cdli").classList.toggle("active",  tab === "cdli");
  document.getElementById("tab-ml").classList.toggle("active",    tab === "ml");
  document.getElementById("tab-pe").classList.toggle("active",    tab === "pe");
  document.getElementById("translate-btn").hidden = tab === "cdli" || tab === "ml" || tab === "pe";
  hideResult();
  if (tab === "ml") loadMlStatus();
  if (tab === "pe") peSearch();
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

// ── ML Sign Classifier ───────────────────────────────────────────────────────

let mlSelectedFile = null;

async function loadMlStatus() {
  try {
    const res = await fetch(`${API}/api/ml/status`);
    const s = await res.json();
    const icon = document.getElementById("ml-status-icon");
    const text = document.getElementById("ml-status-text");
    const btn  = document.getElementById("ml-translate-btn");
    if (s.available) {
      icon.textContent = "✓";
      const acc = s.best_val_acc ? ` · clf ${(s.best_val_acc * 100).toFixed(1)}%` : "";
      const det = s.detector_available
        ? ` · detector recall ${((s.detector_recall || 0) * 100).toFixed(0)}%`
        : " · no detector";
      text.textContent = `Model ready · ${s.n_classes} sign classes${acc}${det}`;
      document.getElementById("ml-status-bar").classList.add("ml-ready");
      btn.disabled = false;
    } else {
      icon.textContent = "⚙";
      text.textContent = `Model training… ${s.reason}`;
      btn.disabled = true;
    }
  } catch (_) {}
}

function setMlImage(file) {
  mlSelectedFile = file;
  const reader = new FileReader();
  reader.onload = e => {
    const img = document.getElementById("ml-image-preview");
    img.src = e.target.result;
    document.getElementById("ml-drop-zone-inner").hidden = true;
    document.getElementById("ml-image-preview-wrap").hidden = false;
    clearDetections();
  };
  reader.readAsDataURL(file);
}

function clearMlImage() {
  mlSelectedFile = null;
  document.getElementById("ml-image-input").value = "";
  document.getElementById("ml-image-preview").src = "";
  document.getElementById("ml-drop-zone-inner").hidden = false;
  document.getElementById("ml-image-preview-wrap").hidden = true;
  clearDetections();
  hideResult();
}

function clearDetections() {
  _lastDetections = null; _lastImgW = null; _lastImgH = null;
  const canvas = document.getElementById("ml-detect-canvas");
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
}

function drawDetections(detections, imgNaturalW, imgNaturalH) {
  if (!detections || !detections.length) return;

  const img = document.getElementById("ml-image-preview");
  const canvas = document.getElementById("ml-detect-canvas");

  // Match canvas pixel size to the image's rendered size
  const rect = img.getBoundingClientRect();
  canvas.width  = rect.width;
  canvas.height = rect.height;

  // Image is letterboxed (object-fit: contain) — compute actual render area
  const imgAspect = imgNaturalW / imgNaturalH;
  const boxAspect = rect.width / rect.height;
  let renderW, renderH, offsetX, offsetY;
  if (imgAspect > boxAspect) {
    renderW = rect.width;
    renderH = rect.width / imgAspect;
    offsetX = 0;
    offsetY = (rect.height - renderH) / 2;
  } else {
    renderH = rect.height;
    renderW = rect.height * imgAspect;
    offsetX = (rect.width - renderW) / 2;
    offsetY = 0;
  }

  const scaleX = renderW / imgNaturalW;
  const scaleY = renderH / imgNaturalH;

  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // Confident signs: warm palette. Uncertain (sign ends with ?): grey dashed.
  const palette = ["#e8a020", "#d45010", "#20a870", "#6060e0", "#c03080"];

  detections.forEach((d, i) => {
    const x = offsetX + d.x1 * scaleX;
    const y = offsetY + d.y1 * scaleY;
    const w = (d.x2 - d.x1) * scaleX;
    const h = (d.y2 - d.y1) * scaleY;
    const uncertain = d.sign && d.sign.endsWith("?");
    const color = uncertain ? "#888888" : palette[i % palette.length];

    // Box — dashed for uncertain signs
    ctx.save();
    ctx.strokeStyle = color;
    ctx.lineWidth = uncertain ? 1 : 1.5;
    if (uncertain) ctx.setLineDash([3, 3]);
    ctx.strokeRect(x, y, w, h);
    ctx.restore();

    // Semi-transparent fill — dimmer for uncertain
    ctx.fillStyle = color + (uncertain ? "18" : "28");
    ctx.fillRect(x, y, w, h);

    // Label above box
    const label = d.sign;
    const fontSize = Math.max(9, Math.min(13, h * 0.55));
    ctx.font = `${uncertain ? "normal" : "bold"} ${fontSize}px monospace`;
    const textW = ctx.measureText(label).width;
    const labelX = Math.min(x, canvas.width - textW - 3);
    const labelY = y > fontSize + 2 ? y - 2 : y + h + fontSize + 1;

    ctx.fillStyle = color;
    ctx.fillText(label, labelX, labelY);
  });
}

async function mlRecognize() {
  if (!mlSelectedFile) { showError("Please upload a tablet photo first."); return; }
  const btn = document.getElementById("ml-translate-btn");
  btn.disabled = true;
  btn.textContent = "Running classifier…";
  hideResult();

  try {
    const form = new FormData();
    form.append("file", mlSelectedFile);
    const res = await fetch(`${API}/api/ml/recognize`, { method: "POST", body: form });
    if (!res.ok) throw new Error((await res.json()).detail || "Recognition failed");
    const data = await res.json();
    renderResult(data, true);

    // Inject confidence stats into notes
    if (data.n_signs != null) {
      const confPct = data.avg_clf_conf != null ? Math.round(data.avg_clf_conf * 100) : "?";
      const uncertainNote = data.n_uncertain > 0
        ? `${data.n_uncertain} of ${data.n_signs} signs are uncertain (marked ?) — classifier confidence below 35%.`
        : `All ${data.n_signs} signs passed the 35% confidence threshold.`;
      const notesList = document.getElementById("notes-list");
      if (notesList) {
        const li = document.createElement("li");
        li.style.color = data.n_uncertain > data.n_signs * 0.2 ? "#8b1a1a" : "#2d5a1b";
        li.textContent = `Automated reading: ${data.n_signs} signs detected, avg classifier confidence ${confPct}%. ${uncertainNote}`;
        notesList.prepend(li);
        document.getElementById("notes-box").hidden = false;
      }
    }

    // Draw bounding boxes once the image has rendered
    const img = document.getElementById("ml-image-preview");
    _lastDetections = data.detections; _lastImgW = data.image_width; _lastImgH = data.image_height;
    const doDraw = () => drawDetections(data.detections, data.image_width, data.image_height);
    if (img.complete) doDraw(); else img.onload = doDraw;
  } catch (e) {
    showError(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Sign Detector + Translate";
  }
}

// ── Init ─────────────────────────────────────────────────────────────────────

let _lastDetections = null, _lastImgW = null, _lastImgH = null;
window.addEventListener("resize", () => {
  if (_lastDetections) drawDetections(_lastDetections, _lastImgW, _lastImgH);
});

document.addEventListener("DOMContentLoaded", () => {
  loadExamples();
  initDropZone();
  document.getElementById("input-text").addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitTranslation();
  });
  document.getElementById("cdli-pnum-input").addEventListener("keydown", e => {
    if (e.key === "Enter") cdliLookup();
  });
  document.getElementById("pe-search-input").addEventListener("keydown", e => {
    if (e.key === "Enter") peSearch();
  });
  loadCDLIFilters();

  // ML tab drop zone
  const mlZone  = document.getElementById("ml-drop-zone");
  const mlInput = document.getElementById("ml-image-input");
  mlZone.addEventListener("dragover", e => { e.preventDefault(); mlZone.classList.add("drag-over"); });
  mlZone.addEventListener("dragleave", () => mlZone.classList.remove("drag-over"));
  mlZone.addEventListener("drop", e => {
    e.preventDefault(); mlZone.classList.remove("drag-over");
    if (e.dataTransfer.files[0]) setMlImage(e.dataTransfer.files[0]);
  });
  mlInput.addEventListener("change", () => { if (mlInput.files[0]) setMlImage(mlInput.files[0]); });
});

// ── Proto-Elamite structural analysis ────────────────────────────────────────

const PE_SYSTEM_COLORS = {
  counting: "#c27b2c",
  grain:    "#5a8a3c",
  area:     "#4a7ab5",
  "time?":  "#8a5ab5",
  unknown:  "#888",
};

const PE_PATTERN_LABELS = {
  ledger:       { label: "Ledger",       desc: "Each row records a different commodity" },
  "ration-list":{ label: "Ration List",  desc: "Repeated commodity, varying quantities" },
  list:         { label: "List",         desc: "Short list of entries" },
  unknown:      { label: "Unknown",      desc: "Pattern unclear" },
};

let peSelectMode = false;
let peSelected = new Set();
let peTabletCache = [];

async function peSearch() {
  const q = document.getElementById("pe-search-input").value.trim();
  const resultsEl  = document.getElementById("pe-results");
  const analysisEl = document.getElementById("pe-analysis-panel");
  const corpusEl   = document.getElementById("pe-corpus-panel");
  analysisEl.hidden = true;
  corpusEl.hidden   = true;
  resultsEl.style.display = "";
  resultsEl.innerHTML = "<p class='cdli-loading'>Loading Proto-Elamite tablets…</p>";

  const params = new URLSearchParams({ limit: 16 });
  if (q) params.set("q", q);

  try {
    const res = await fetch(`${API}/api/proto-elamite/search?${params}`);
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    peTabletCache = await res.json();
    renderPeResults(peTabletCache);
  } catch (e) {
    resultsEl.innerHTML = `<p class="cdli-error">Error: ${e.message}</p>`;
  }
}

function renderPeResults(tablets) {
  const el = document.getElementById("pe-results");
  if (!tablets.length) {
    el.innerHTML = "<p class='cdli-loading'>No Proto-Elamite tablets found.</p>";
    return;
  }
  el.innerHTML = tablets.map(t => {
    const checked = peSelected.has(t.p_number);
    const selectAttr = peSelectMode
      ? `onclick="peToggleCard('${t.p_number}',this)" class="cdli-card pe-selectable${checked ? ' pe-selected' : ''}"`
      : `onclick="peAnalyze('${t.p_number}','${escHtml(t.designation)}')" class="cdli-card"`;
    return `
    <div ${selectAttr} data-pnum="${t.p_number}">
      ${peSelectMode ? `<div class="pe-check-box">${checked ? "&#10003;" : ""}</div>` : ""}
      <div class="cdli-card-img-wrap">
        <img src="${t.photo_url}" alt="${escHtml(t.p_number)}" loading="lazy"
             onerror="this.parentElement.innerHTML='<div class=\\'cdli-card-no-img\\'>No photo</div>'" />
      </div>
      <div class="cdli-card-info">
        <strong>${escHtml(t.p_number)}</strong>
        <span class="cdli-designation">${escHtml(t.designation)}</span>
        ${t.museum_no ? `<span class="cdli-museum">${escHtml(t.museum_no)}</span>` : ""}
        <span class="cdli-period">Proto-Elamite (ca. 3100–2900 BC)</span>
      </div>
    </div>`;
  }).join("");
}

function peToggleSelect() {
  peSelectMode = !peSelectMode;
  const btn = document.getElementById("pe-select-btn");
  const bar = document.getElementById("pe-corpus-bar");
  btn.classList.toggle("active", peSelectMode);
  bar.hidden = !peSelectMode;
  if (!peSelectMode) {
    peSelected.clear();
    peUpdateCorpusBtn();
  }
  renderPeResults(peTabletCache);
}

function peToggleCard(pnum, cardEl) {
  if (peSelected.has(pnum)) {
    peSelected.delete(pnum);
    cardEl.classList.remove("pe-selected");
    cardEl.querySelector(".pe-check-box").innerHTML = "";
  } else {
    peSelected.add(pnum);
    cardEl.classList.add("pe-selected");
    cardEl.querySelector(".pe-check-box").innerHTML = "&#10003;";
  }
  peUpdateCorpusBtn();
}

function peUpdateCorpusBtn() {
  const n = peSelected.size;
  document.getElementById("pe-selected-count").textContent = `${n} selected`;
  const btn = document.getElementById("pe-corpus-btn");
  btn.textContent = n >= 2 ? `Analyze Corpus (${n})` : "Analyze Corpus";
  btn.disabled = n < 2;
}

function peClearSelection() {
  peSelected.clear();
  peUpdateCorpusBtn();
  renderPeResults(peTabletCache);
}

async function peCorpus() {
  const pNumbers = [...peSelected];
  if (pNumbers.length < 2) return;

  const resultsEl  = document.getElementById("pe-results");
  const corpusEl   = document.getElementById("pe-corpus-panel");
  const titleEl    = document.getElementById("pe-corpus-title");

  resultsEl.style.display = "none";
  document.getElementById("pe-analysis-panel").hidden = true;
  corpusEl.hidden = false;
  titleEl.textContent = `${pNumbers.length} tablets`;
  ["pe-corpus-patterns","pe-corpus-signs","pe-corpus-numsys","pe-corpus-pairs"].forEach(
    id => document.getElementById(id).innerHTML = "<p>Loading…</p>"
  );

  try {
    const res = await fetch(`${API}/api/proto-elamite/corpus`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({ p_numbers: pNumbers }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const data = await res.json();
    renderCorpus(data, pNumbers.length);
  } catch (e) {
    document.getElementById("pe-corpus-patterns").innerHTML =
      `<p class="cdli-error">${e.message}</p>`;
  }
}

function renderCorpus(data, nTablets) {
  document.getElementById("pe-corpus-title").textContent =
    `${nTablets} tablets — ${data.n_tablets} analysed`;

  // Pattern distribution
  const patTotal = Object.values(data.pattern_dist || {}).reduce((s,v)=>s+v,0);
  document.getElementById("pe-corpus-patterns").innerHTML =
    Object.entries(data.pattern_dist || {}).sort((a,b)=>b[1]-a[1]).map(([pat, cnt]) => {
      const info = PE_PATTERN_LABELS[pat] || { label: pat };
      const pct  = Math.round(cnt / patTotal * 100);
      return `<div class="pe-bar-row">
        <span class="pe-bar-label">${info.label}</span>
        <div class="pe-bar-track">
          <div class="pe-bar-fill" style="width:${pct}%;background:#7a4a1a"></div>
        </div>
        <span class="pe-bar-count">${cnt} (${pct}%)</span>
      </div>`;
    }).join("") || "<p>No data.</p>";

  // Top signs
  const signs = data.top_signs || [];
  const maxSig = signs.length ? signs[0][1] : 1;
  document.getElementById("pe-corpus-signs").innerHTML = signs.slice(0,25).map(([sign, cnt]) => {
    const pct = Math.round(cnt / maxSig * 100);
    return `<div class="pe-bar-row">
      <span class="pe-bar-label pe-msign-inline">${escHtml(sign)}</span>
      <div class="pe-bar-track">
        <div class="pe-bar-fill" style="width:${pct}%;background:#b85c2c"></div>
      </div>
      <span class="pe-bar-count">${cnt}</span>
    </div>`;
  }).join("") || "<p>No signs.</p>";

  // Numerical systems
  const sysDist = data.n_system_dist || {};
  const sysTotal = Object.values(sysDist).reduce((s,v)=>s+v,0);
  const nToks = data.top_n_tokens || [];
  document.getElementById("pe-corpus-numsys").innerHTML =
    (sysTotal === 0 ? "<p>No numerals.</p>" :
      Object.entries(sysDist).sort((a,b)=>b[1]-a[1]).map(([sys, cnt]) => {
        const pct = Math.round(cnt / sysTotal * 100);
        const col = PE_SYSTEM_COLORS[sys] || PE_SYSTEM_COLORS.unknown;
        return `<div class="pe-bar-row">
          <span class="pe-bar-label">${sys}</span>
          <div class="pe-bar-track">
            <div class="pe-bar-fill" style="width:${pct}%;background:${col}"></div>
          </div>
          <span class="pe-bar-count">${pct}%</span>
        </div>`;
      }).join("")
    ) + `<div class="pe-n-tokens">${nToks.slice(0,12).map(([t,c])=>
      `<span class="pe-n-chip">${escHtml(t)}×${c}</span>`).join(" ")}</div>`;

  // Co-occurrence pairs
  const pairs = data.top_cooccur_pairs || [];
  document.getElementById("pe-corpus-pairs").innerHTML = pairs.length === 0
    ? "<p>No pairs found.</p>"
    : `<div class="pe-pairs-grid">${pairs.map(p =>
        `<div class="pe-pair-chip" title="${p.count} co-occurrences">
          <span class="pe-msign-inline">${escHtml(p.signs[0])}</span>
          <span class="pe-pair-sep">+</span>
          <span class="pe-msign-inline">${escHtml(p.signs[1])}</span>
          <span class="pe-pair-count">${p.count}</span>
        </div>`
      ).join("")}</div>`;
}

function peCorpusBack() {
  document.getElementById("pe-corpus-panel").hidden = true;
  document.getElementById("pe-results").style.display = "";
}

async function peAnalyze(pNumber, designation) {
  const resultsEl  = document.getElementById("pe-results");
  const analysisEl = document.getElementById("pe-analysis-panel");
  const titleEl    = document.getElementById("pe-analysis-title");
  const badgeEl    = document.getElementById("pe-pattern-badge");
  const atfEl      = document.getElementById("pe-atf-text");
  const structEl   = document.getElementById("pe-struct-summary");
  const numEl      = document.getElementById("pe-num-systems");
  const freqEl     = document.getElementById("pe-sign-freq");
  const entriesEl  = document.getElementById("pe-entries");

  resultsEl.style.display = "none";
  analysisEl.hidden  = false;
  titleEl.textContent = `${pNumber} — ${designation}`;
  badgeEl.textContent = "Loading…";
  atfEl.textContent   = "";
  structEl.innerHTML = numEl.innerHTML = freqEl.innerHTML = entriesEl.innerHTML = "<p>Loading…</p>";

  try {
    const res = await fetch(`${API}/api/proto-elamite/analyze/${pNumber}`);
    if (!res.ok) throw new Error((await res.json()).detail || res.statusText);
    const a = await res.json();
    renderPeAnalysis(a);
  } catch (e) {
    badgeEl.textContent = "Error";
    structEl.innerHTML = `<p class="cdli-error">${e.message}</p>`;
  }
}

function renderPeAnalysis(a) {
  const pat = PE_PATTERN_LABELS[a.pattern] || PE_PATTERN_LABELS.unknown;
  document.getElementById("pe-pattern-badge").textContent = pat.label;
  document.getElementById("pe-pattern-badge").title = pat.desc;

  // ATF with sign highlighting
  const highlighted = a.atf
    .split("\n")
    .map(line => {
      const esc = escHtml(line);
      // highlight M-signs in terracotta
      return esc.replace(/(M\d+(?:[~@][a-z0-9]+)?|\|M[^|]+\|)/g,
        '<span class="pe-msign">$1</span>');
    })
    .join("\n");
  document.getElementById("pe-atf-text").innerHTML = highlighted;

  // Structure summary
  document.getElementById("pe-struct-summary").innerHTML = `
    <table class="pe-stat-table">
      <tr><td>Pattern</td><td><strong>${pat.label}</strong> — ${pat.desc}</td></tr>
      <tr><td>Data entries</td><td>${a.n_entries}</td></tr>
      <tr><td>Header signs</td><td>${a.n_header_signs}</td></tr>
      <tr><td>Declared totals</td><td>${a.declared_totals.length}</td></tr>
      <tr><td>Unique signs</td><td>${Object.keys(a.sign_freq).length}</td></tr>
    </table>
    ${a.declared_totals.length ? renderDeclaredTotals(a.declared_totals) : ""}
  `;

  // Numerical systems
  const sysDist = a.n_system_dist || a.n_system_freq || {};
  const sysTotal = Object.values(sysDist).reduce((s, v) => s + v, 0);
  document.getElementById("pe-num-systems").innerHTML = sysTotal === 0
    ? "<p>No numerals found.</p>"
    : Object.entries(sysDist).sort((x, y) => y[1] - x[1]).map(([sys, cnt]) => {
        const pct = Math.round(cnt / sysTotal * 100);
        const col = PE_SYSTEM_COLORS[sys] || PE_SYSTEM_COLORS.unknown;
        return `
          <div class="pe-bar-row">
            <span class="pe-bar-label">${sys}</span>
            <div class="pe-bar-track">
              <div class="pe-bar-fill" style="width:${pct}%;background:${col}"></div>
            </div>
            <span class="pe-bar-count">${pct}%</span>
          </div>`;
      }).join("") + `<div class="pe-n-tokens">${renderNTokens(a.top_n_tokens || a.n_token_freq)}</div>`;

  // Sign frequency bars
  const signFreq = Array.isArray(a.sign_freq) ? a.sign_freq : Object.entries(a.sign_freq).sort((x,y)=>y[1]-x[1]);
  const maxFreq = signFreq.length ? signFreq[0][1] : 1;
  document.getElementById("pe-sign-freq").innerHTML = signFreq.slice(0, 15).map(([sign, cnt]) => {
    const pct = Math.round(cnt / maxFreq * 100);
    return `
      <div class="pe-bar-row">
        <span class="pe-bar-label pe-msign-inline">${escHtml(sign)}</span>
        <div class="pe-bar-track">
          <div class="pe-bar-fill" style="width:${pct}%;background:#b85c2c"></div>
        </div>
        <span class="pe-bar-count">${cnt}</span>
      </div>`;
  }).join("") || "<p>No signs.</p>";

  // Entry table
  const entries = (a.entries || []).filter(e => !e.is_header && e.numerals.length);
  document.getElementById("pe-entries").innerHTML = entries.length === 0
    ? "<p>No data entries found.</p>"
    : `<table class="pe-entry-table">
        <thead><tr><th>Line</th><th>Surface</th><th>Signs</th><th>Quantities</th></tr></thead>
        <tbody>
          ${entries.map(e => `
            <tr class="${e.is_total ? 'pe-total-row' : ''}">
              <td>${e.line_no}${e.is_total ? " ∑" : ""}</td>
              <td>${e.surface}</td>
              <td>${e.signs.map(s => `<span class="pe-msign-inline">${escHtml(s)}</span>`).join(" ")}</td>
              <td>${e.numerals.map(n => `${n.count}(${escHtml(n.token)})`).join(" ")}</td>
            </tr>
          `).join("")}
        </tbody>
      </table>`;
}

function renderDeclaredTotals(totals) {
  return `<div class="pe-totals">
    <strong>Declared totals:</strong>
    ${totals.map(t =>
      `<span class="pe-total-chip">${t.numerals.map(n=>`${n.count}(${n.token})`).join(" ")}</span>`
    ).join(" ")}
  </div>`;
}

function renderNTokens(tokFreq) {
  const arr = Array.isArray(tokFreq)
    ? tokFreq
    : Object.entries(tokFreq).sort((a,b)=>b[1]-a[1]);
  return arr.slice(0,10).map(([tok, cnt]) =>
    `<span class="pe-n-chip" title="${tok}">${tok}×${cnt}</span>`
  ).join(" ");
}

function peBack() {
  document.getElementById("pe-results").style.display = "";
  document.getElementById("pe-analysis-panel").hidden = true;
}

function escHtml(s) {
  return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");
}
