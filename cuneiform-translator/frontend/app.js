const API = "";
let activeTab = "text";
let selectedFile = null;

// ── Tab switching ────────────────────────────────────────────────────────────

function switchTab(tab) {
  activeTab = tab;
  document.getElementById("panel-text").hidden = tab !== "text";
  document.getElementById("panel-image").hidden = tab !== "image";
  document.getElementById("tab-text").classList.toggle("active", tab === "text");
  document.getElementById("tab-image").classList.toggle("active", tab === "image");
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

// ── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  loadExamples();
  initDropZone();
  document.getElementById("input-text").addEventListener("keydown", e => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) submitTranslation();
  });
});
