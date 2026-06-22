/* ── Marked config ── */
const renderer = new marked.Renderer();
renderer.code = (code, lang) => {
  const valid = lang && hljs.getLanguage(lang) ? lang : '';
  const highlighted = valid
    ? hljs.highlight(code, { language: valid }).value
    : hljs.highlightAuto(code).value;
  return `<div class="code-block">
    <div class="code-block-header">
      <span class="code-lang">${lang || 'code'}</span>
      <button class="copy-btn" onclick="copyCode(this)">Copy</button>
    </div>
    <pre><code>${highlighted}</code></pre>
  </div>`;
};
marked.setOptions({ renderer, breaks: true, gfm: true });

/* ── State ── */
let activeConvId  = null;
let isStreaming   = false;
let stopRequested = false;
let allConvs      = [];

/* ── DOM ── */
const welcome     = document.getElementById('welcome');
const chatArea    = document.getElementById('chat-area');
const messagesEl  = document.getElementById('messages');
const convList    = document.getElementById('conv-list');
const userInput   = document.getElementById('user-input');
const sendBtn     = document.getElementById('send-btn');
const stopBtn     = document.getElementById('stop-btn');
const newChatBtn  = document.getElementById('new-chat-btn');
const searchInput = document.getElementById('search-input');
const scrollBtn   = document.getElementById('scroll-btn');
const toastEl     = document.getElementById('toasts');

/* ── Boot ── */
loadConversations();
userInput.focus();

/* ── Input resize ── */
userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 180) + 'px';
  sendBtn.disabled = !userInput.value.trim() || isStreaming;
});
userInput.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); if (!sendBtn.disabled) send(); }
});

sendBtn.addEventListener('click', send);
stopBtn.addEventListener('click', () => { stopRequested = true; });
newChatBtn.addEventListener('click', startNewChat);
scrollBtn.addEventListener('click', () => { chatArea.scrollTop = chatArea.scrollHeight; });

/* ── Smart scroll button ── */
chatArea.addEventListener('scroll', () => {
  const fromBottom = chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight;
  scrollBtn.classList.toggle('hidden', fromBottom < 150);
});

/* ── Search ── */
searchInput.addEventListener('input', () => {
  const q = searchInput.value.trim().toLowerCase();
  renderConvList(q ? allConvs.filter(c => c.title.toLowerCase().includes(q)) : allConvs);
});

/* ── Keyboard shortcuts ── */
document.addEventListener('keydown', e => {
  if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); startNewChat(); }
  if (e.key === 'Escape' && document.activeElement === userInput) userInput.blur();
});

/* ── Suggestion cards ── */
document.querySelectorAll('.card').forEach(card => {
  card.addEventListener('click', () => {
    userInput.value = card.dataset.msg;
    userInput.dispatchEvent(new Event('input'));
    send();
  });
});

/* ════════════════════════════════════
   Date helpers
════════════════════════════════════ */
function toLocal(iso) {
  return new Date(iso && !iso.endsWith('Z') ? iso + 'Z' : iso);
}

function relativeTime(iso) {
  const d = toLocal(iso);
  const diffMs  = Date.now() - d.getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin <  1)  return 'now';
  if (diffMin < 60)  return `${diffMin}m`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH   < 24)  return `${diffH}h`;
  if (diffH   < 48)  return 'yesterday';
  return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

function formatTime(iso) {
  if (!iso) return '';
  return toLocal(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function groupByDate(list) {
  const now = new Date();
  const startOf = d => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const todayMs     = startOf(now);
  const yesterdayMs = todayMs - 86400000;
  const weekMs      = todayMs - 6 * 86400000;

  const groups = [
    { label: 'Today',     items: [] },
    { label: 'Yesterday', items: [] },
    { label: 'This week', items: [] },
    { label: 'Earlier',   items: [] },
  ];

  list.forEach(c => {
    const ms = startOf(toLocal(c.updated_at));
    if      (ms >= todayMs)     groups[0].items.push(c);
    else if (ms >= yesterdayMs) groups[1].items.push(c);
    else if (ms >= weekMs)      groups[2].items.push(c);
    else                        groups[3].items.push(c);
  });

  return groups.filter(g => g.items.length);
}

/* ════════════════════════════════════
   Conversations
════════════════════════════════════ */
async function loadConversations() {
  const res = await fetch('/api/conversations');
  allConvs = await res.json();
  renderConvList(allConvs);
}

function renderConvList(list) {
  convList.innerHTML = '';
  if (!list.length) {
    convList.innerHTML = '<div class="conv-empty">No conversations yet</div>';
    return;
  }

  for (const group of groupByDate(list)) {
    const labelEl = document.createElement('div');
    labelEl.className = 'conv-group-label';
    labelEl.textContent = group.label;
    convList.appendChild(labelEl);

    group.items.forEach(c => {
      const el = document.createElement('div');
      el.className = 'conv-item' + (c.id === activeConvId ? ' active' : '');
      el.dataset.id = c.id;
      el.innerHTML = `
        <div class="conv-dot"></div>
        <div class="conv-title" title="${esc(c.title)}">${esc(c.title)}</div>
        <div class="conv-meta">
          <span class="conv-time">${relativeTime(c.updated_at)}</span>
          <button class="conv-del" title="Delete" onclick="deleteConv(event,'${c.id}')">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>`;

      el.addEventListener('click', () => loadConversation(c.id));
      el.querySelector('.conv-title').addEventListener('dblclick', e => {
        e.stopPropagation();
        startRename(el, c.id, c.title);
      });
      convList.appendChild(el);
    });
  }
}

function startRename(el, id, currentTitle) {
  const titleEl = el.querySelector('.conv-title');
  const input = document.createElement('input');
  input.className = 'conv-rename-input';
  input.value = currentTitle;
  titleEl.replaceWith(input);
  input.focus(); input.select();

  const finish = async () => {
    const newTitle = input.value.trim();
    if (newTitle && newTitle !== currentTitle) {
      await fetch(`/api/conversations/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle }),
      });
    }
    await loadConversations();
  };

  input.addEventListener('blur', finish);
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); input.blur(); }
    if (e.key === 'Escape') { input.value = currentTitle; input.blur(); }
  });
}

async function loadConversation(id) {
  if (id === activeConvId) return;

  activeConvId = id;
  showChat();
  showSkeleton();
  await loadConversations();

  const res = await fetch(`/api/conversations/${id}`);
  if (!res.ok) return;
  const data = await res.json();

  messagesEl.innerHTML = '';
  data.messages.forEach(m => appendMessage(m.role, m.content, false, m.created_at));
  scrollToBottom(true);
  userInput.focus();
}

function showSkeleton() {
  messagesEl.innerHTML = `
    <div class="skeleton-wrap">
      <div class="skeleton-msg">
        <div style="display:flex;gap:8px;align-items:center">
          <div class="skel skel-avatar"></div>
          <div class="skel skel-short"></div>
        </div>
        <div class="skel skel-long"></div>
        <div class="skel skel-xl"></div>
        <div class="skel skel-med"></div>
      </div>
      <div class="skeleton-msg" style="align-items:flex-end">
        <div class="skel skel-short"></div>
      </div>
      <div class="skeleton-msg">
        <div style="display:flex;gap:8px;align-items:center">
          <div class="skel skel-avatar"></div>
          <div class="skel skel-short"></div>
        </div>
        <div class="skel skel-xl"></div>
        <div class="skel skel-long"></div>
        <div class="skel skel-med"></div>
        <div class="skel skel-long"></div>
      </div>
    </div>`;
}

function startNewChat() {
  activeConvId = null;
  messagesEl.innerHTML = '';
  showWelcome();
  document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
  userInput.focus();
}

async function deleteConv(e, id) {
  e.stopPropagation();
  await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
  if (id === activeConvId) startNewChat();
  await loadConversations();
  toast('Conversation deleted');
}

/* ════════════════════════════════════
   View helpers
════════════════════════════════════ */
function showChat()    { welcome.classList.add('hidden'); chatArea.classList.remove('hidden'); }
function showWelcome() { chatArea.classList.add('hidden'); welcome.classList.remove('hidden'); }

function scrollToBottom(force = false) {
  const fromBottom = chatArea.scrollHeight - chatArea.scrollTop - chatArea.clientHeight;
  if (force || fromBottom < 200) chatArea.scrollTop = chatArea.scrollHeight;
}

function esc(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

/* ── Toast ── */
function toast(msg, type = 'success') {
  const el = document.createElement('div');
  el.className = `toast ${type}`;
  el.textContent = msg;
  toastEl.appendChild(el);
  requestAnimationFrame(() => { requestAnimationFrame(() => el.classList.add('show')); });
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 250);
  }, 2000);
}

/* ════════════════════════════════════
   Messages
════════════════════════════════════ */
function appendMessage(role, content, streaming = false, createdAt = null) {
  const el = document.createElement('div');
  el.className = `msg ${role}`;
  const timeStr = formatTime(createdAt);

  if (role === 'user') {
    el.innerHTML = `
      <div class="msg-bubble">${esc(content).replace(/\n/g,'<br>')}</div>
      ${timeStr ? `<div class="msg-time">${timeStr}</div>` : ''}`;
  } else {
    const bodyHtml = streaming
      ? '<div class="thinking"><span></span><span></span><span></span></div>'
      : (content ? marked.parse(content) : '');

    el.innerHTML = `
      <div class="msg-header">
        <div class="msg-avatar">B</div>
        <span class="msg-name">Burf</span>
        ${timeStr ? `<span class="msg-time-inline">${timeStr}</span>` : ''}
      </div>
      <div class="msg-body">${bodyHtml}</div>
      ${!streaming ? '<div class="msg-actions"></div>' : ''}`;

    if (!streaming) addMessageActions(el, content);
  }

  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

function addMessageActions(el, rawText) {
  const actions = el.querySelector('.msg-actions');
  if (!actions) return;
  actions.innerHTML = `
    <button class="msg-action-btn" onclick="copyMessage(this)">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="9" y="9" width="13" height="13" rx="2"/>
        <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
      </svg>
      Copy
    </button>`;
}

/* ════════════════════════════════════
   Send / stream
════════════════════════════════════ */
async function send() {
  const text = userInput.value.trim();
  if (!text || isStreaming) return;

  isStreaming   = true;
  stopRequested = false;
  sendBtn.classList.add('hidden');
  stopBtn.classList.remove('hidden');
  userInput.value = '';
  userInput.style.height = 'auto';
  userInput.disabled = true;

  showChat();
  appendMessage('user', text, false, new Date().toISOString());

  const assistantEl = appendMessage('assistant', '', true);
  const bodyEl = assistantEl.querySelector('.msg-body');

  let fullText   = '';
  let firstToken = true;
  let newConvId  = activeConvId;

  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: activeConvId, message: text }),
    });

    const reader  = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer    = '';

    outer: while (true) {
      if (stopRequested) { reader.cancel(); break; }
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (stopRequested) break outer;
        if (!line.trim() || line.startsWith(':') || line.startsWith('event:')) continue;
        if (!line.startsWith('data:')) continue;

        try {
          const p = JSON.parse(line.slice(5).trim());
          if (p.token !== undefined) {
            if (firstToken) { firstToken = false; bodyEl.innerHTML = ''; }
            fullText += p.token;
            bodyEl.innerHTML = marked.parse(fullText) + '<span class="cursor"></span>';
            scrollToBottom();
          }
          if (p.conversation_id) newConvId = p.conversation_id;
          if (p.error) bodyEl.innerHTML = `<div class="msg-error">Error: ${esc(p.error)}</div>`;
        } catch (_) {}
      }
    }

    bodyEl.innerHTML = marked.parse(fullText || '…');
    addMessageActions(assistantEl, fullText);

    activeConvId = newConvId;
    await loadConversations();

  } catch (err) {
    bodyEl.innerHTML = `<div class="msg-error">Connection error: ${esc(err.message)}</div>`;
  } finally {
    isStreaming = false;
    stopBtn.classList.add('hidden');
    sendBtn.classList.remove('hidden');
    sendBtn.disabled = true;
    userInput.disabled = false;
    userInput.focus();
  }
}

/* ── Copy utilities ── */
function copyCode(btn) {
  const code = btn.closest('.code-block').querySelector('code').innerText;
  navigator.clipboard.writeText(code).then(() => {
    btn.textContent = 'Copied!';
    btn.classList.add('copied');
    setTimeout(() => { btn.textContent = 'Copy'; btn.classList.remove('copied'); }, 1800);
    toast('Code copied');
  });
}

function copyMessage(btn) {
  const bodyEl = btn.closest('.msg').querySelector('.msg-body');
  navigator.clipboard.writeText(bodyEl.innerText).then(() => {
    btn.classList.add('copied');
    btn.innerHTML = `
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="20 6 9 17 4 12"/>
      </svg> Copied`;
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = `
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2"/>
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        </svg> Copy`;
    }, 1800);
    toast('Copied to clipboard');
  });
}
