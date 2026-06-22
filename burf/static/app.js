/* ── Marked config ── */
const renderer = new marked.Renderer();
renderer.code = (code, lang) => {
  const validLang = lang && hljs.getLanguage(lang) ? lang : '';
  const highlighted = validLang
    ? hljs.highlight(code, { language: validLang }).value
    : hljs.highlightAuto(code).value;
  return `
    <div class="code-block">
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

/* ── Search ── */
searchInput.addEventListener('input', () => {
  const q = searchInput.value.trim().toLowerCase();
  renderConvList(q ? allConvs.filter(c => c.title.toLowerCase().includes(q)) : allConvs);
});

/* ── Keyboard shortcuts ── */
document.addEventListener('keydown', e => {
  const mod = e.metaKey || e.ctrlKey;
  if (mod && e.key === 'k') { e.preventDefault(); startNewChat(); }
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

  const label = document.createElement('div');
  label.className = 'conv-section-label';
  label.textContent = 'Recent';
  convList.appendChild(label);

  list.forEach(c => {
    const el = document.createElement('div');
    el.className = 'conv-item' + (c.id === activeConvId ? ' active' : '');
    el.dataset.id = c.id;
    el.innerHTML = `
      <div class="conv-dot"></div>
      <div class="conv-title" title="${esc(c.title)}">${esc(c.title)}</div>
      <button class="conv-del" title="Delete" onclick="deleteConv(event,'${c.id}')">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
      </button>`;

    el.addEventListener('click', () => loadConversation(c.id));

    // Double-click title to rename
    el.querySelector('.conv-title').addEventListener('dblclick', e => {
      e.stopPropagation();
      startRename(el, c.id, c.title);
    });

    convList.appendChild(el);
  });
}

function startRename(el, id, currentTitle) {
  const titleEl = el.querySelector('.conv-title');
  const input = document.createElement('input');
  input.className = 'conv-rename-input';
  input.value = currentTitle;
  titleEl.replaceWith(input);
  input.focus();
  input.select();

  const finish = async () => {
    const newTitle = input.value.trim();
    if (newTitle && newTitle !== currentTitle) {
      await fetch(`/api/conversations/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle }),
      });
      if (id === activeConvId) {
        // update header title if this conv is open — there's no header now, but update allConvs
      }
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
  const res = await fetch(`/api/conversations/${id}`);
  if (!res.ok) return;
  const data = await res.json();

  activeConvId = id;
  messagesEl.innerHTML = '';
  data.messages.forEach(m => appendMessage(m.role, m.content, false, m.created_at));

  showChat();
  scrollToBottom();
  await loadConversations();
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
}

/* ════════════════════════════════════
   View helpers
════════════════════════════════════ */
function showChat()    { welcome.classList.add('hidden'); chatArea.classList.remove('hidden'); }
function showWelcome() { chatArea.classList.add('hidden'); welcome.classList.remove('hidden'); }
function scrollToBottom() { chatArea.scrollTop = chatArea.scrollHeight; }

function esc(str) {
  return String(str)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;')
    .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function formatTime(iso) {
  if (!iso) return '';
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
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
      ${!streaming ? `
      <div class="msg-actions">
        <button class="msg-action-btn" onclick="copyMessage(this)" title="Copy response">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
          </svg>
          Copy
        </button>
      </div>` : ''}`;
  }

  messagesEl.appendChild(el);
  scrollToBottom();
  return el;
}

/* ════════════════════════════════════
   Send / stream
════════════════════════════════════ */
async function send() {
  const text = userInput.value.trim();
  if (!text || isStreaming) return;

  isStreaming    = true;
  stopRequested  = false;
  sendBtn.classList.add('hidden');
  stopBtn.classList.remove('hidden');
  userInput.value = '';
  userInput.style.height = 'auto';
  userInput.disabled = true;

  showChat();
  appendMessage('user', text, false, new Date().toISOString());

  const assistantEl = appendMessage('assistant', '', true);
  const bodyEl = assistantEl.querySelector('.msg-body');

  let fullText    = '';
  let firstToken  = true;
  let newConvId   = activeConvId;

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
          if (p.error) {
            bodyEl.innerHTML = `<div class="msg-error">Error: ${esc(p.error)}</div>`;
          }
        } catch (_) {}
      }
    }

    // Finalize message
    bodyEl.innerHTML = marked.parse(fullText || '…');

    // Add action buttons
    const actions = document.createElement('div');
    actions.className = 'msg-actions';
    actions.innerHTML = `
      <button class="msg-action-btn" onclick="copyMessage(this)" title="Copy response">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        </svg>
        Copy
      </button>`;
    assistantEl.appendChild(actions);

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
  });
}

function copyMessage(btn) {
  const bodyEl = btn.closest('.msg').querySelector('.msg-body');
  navigator.clipboard.writeText(bodyEl.innerText).then(() => {
    btn.classList.add('copied');
    btn.innerHTML = `
      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
        <polyline points="20 6 9 17 4 12"/>
      </svg> Copied`;
    setTimeout(() => {
      btn.classList.remove('copied');
      btn.innerHTML = `
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1"/>
        </svg> Copy`;
    }, 1800);
  });
}
