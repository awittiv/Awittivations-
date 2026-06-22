/* ──────────────────────────────────────────────────────────
   Burf — frontend logic
   ────────────────────────────────────────────────────────── */

marked.setOptions({
  highlight: (code, lang) => {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value;
    }
    return hljs.highlightAuto(code).value;
  },
  breaks: true,
  gfm: true,
});

/* ── State ── */
let activeConvId = null;
let isStreaming = false;

/* ── DOM refs ── */
const welcome    = document.getElementById('welcome');
const chatArea   = document.getElementById('chat-area');
const messages   = document.getElementById('messages');
const chatTitle  = document.getElementById('chat-title');
const convList   = document.getElementById('conv-list');
const userInput  = document.getElementById('user-input');
const sendBtn    = document.getElementById('send-btn');
const newChatBtn = document.getElementById('new-chat-btn');
const delConvBtn = document.getElementById('delete-conv-btn');

/* ── Boot ── */
loadConversations();

/* ── Input auto-resize + enable send ── */
userInput.addEventListener('input', () => {
  userInput.style.height = 'auto';
  userInput.style.height = Math.min(userInput.scrollHeight, 160) + 'px';
  sendBtn.disabled = !userInput.value.trim() || isStreaming;
});

userInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (!sendBtn.disabled) send();
  }
});

sendBtn.addEventListener('click', send);
newChatBtn.addEventListener('click', startNewChat);
delConvBtn.addEventListener('click', deleteCurrentConv);

/* ── Suggestion cards ── */
document.querySelectorAll('.suggestion-card').forEach(card => {
  card.addEventListener('click', () => {
    userInput.value = card.dataset.msg;
    userInput.dispatchEvent(new Event('input'));
    send();
  });
});

/* ── Functions ── */

async function loadConversations() {
  const res = await fetch('/api/conversations');
  const list = await res.json();
  renderConvList(list);
}

function renderConvList(list) {
  convList.innerHTML = '';
  if (!list.length) {
    convList.innerHTML = '<div style="padding:12px 10px;color:#444;font-size:12px;">No conversations yet</div>';
    return;
  }
  list.forEach(c => {
    const el = document.createElement('div');
    el.className = 'conv-item' + (c.id === activeConvId ? ' active' : '');
    el.dataset.id = c.id;
    el.innerHTML = `<div class="conv-item-icon"></div><div class="conv-title" title="${escHtml(c.title)}">${escHtml(c.title)}</div>`;
    el.addEventListener('click', () => loadConversation(c.id));
    convList.appendChild(el);
  });
}

async function loadConversation(id) {
  const res = await fetch(`/api/conversations/${id}`);
  if (!res.ok) return;
  const data = await res.json();

  activeConvId = id;
  chatTitle.textContent = data.title;
  messages.innerHTML = '';

  data.messages.forEach(m => appendMessage(m.role, m.content, false));

  showChat();
  scrollToBottom();
  await loadConversations();
}

function startNewChat() {
  activeConvId = null;
  messages.innerHTML = '';
  chatTitle.textContent = 'New Chat';
  showWelcome();
  document.querySelectorAll('.conv-item').forEach(el => el.classList.remove('active'));
  userInput.focus();
}

async function deleteCurrentConv() {
  if (!activeConvId) return;
  if (!confirm('Delete this conversation?')) return;
  await fetch(`/api/conversations/${activeConvId}`, { method: 'DELETE' });
  startNewChat();
  await loadConversations();
}

function showChat() {
  welcome.classList.add('hidden');
  chatArea.classList.remove('hidden');
}

function showWelcome() {
  chatArea.classList.add('hidden');
  welcome.classList.remove('hidden');
}

function scrollToBottom() {
  messages.scrollTop = messages.scrollHeight;
}

function escHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

function appendMessage(role, content, streaming = false) {
  const msg = document.createElement('div');
  msg.className = `message ${role}`;

  const avatarLetter = role === 'user' ? 'J' : 'B';
  const label = role === 'user' ? 'You' : 'Burf';

  const contentHtml = role === 'assistant'
    ? marked.parse(content || '')
    : escHtml(content).replace(/\n/g, '<br>');

  msg.innerHTML = `
    <div class="msg-avatar">${avatarLetter}</div>
    <div class="msg-body">
      <div class="msg-label">${label}</div>
      <div class="msg-content">${contentHtml}${streaming ? '<span class="cursor-blink"></span>' : ''}</div>
    </div>
  `;

  messages.appendChild(msg);
  scrollToBottom();
  return msg;
}

async function send() {
  const text = userInput.value.trim();
  if (!text || isStreaming) return;

  isStreaming = true;
  sendBtn.disabled = true;
  userInput.value = '';
  userInput.style.height = 'auto';

  showChat();
  appendMessage('user', text, false);

  // Streaming assistant message
  const assistantEl = appendMessage('assistant', '', true);
  const contentEl = assistantEl.querySelector('.msg-content');

  let fullText = '';
  let newConvId = activeConvId;

  try {
    const response = await fetch('/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ conversation_id: activeConvId, message: text }),
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.trim() || line.startsWith(':')) continue;

        if (line.startsWith('event:')) continue;

        if (line.startsWith('data:')) {
          const raw = line.slice(5).trim();
          try {
            const parsed = JSON.parse(raw);

            if (parsed.token !== undefined) {
              fullText += parsed.token;
              contentEl.innerHTML = marked.parse(fullText) + '<span class="cursor-blink"></span>';
              scrollToBottom();
            }

            if (parsed.conversation_id) {
              newConvId = parsed.conversation_id;
              if (parsed.title) chatTitle.textContent = parsed.title;
            }

            if (parsed.error) {
              contentEl.innerHTML = `<span style="color:#e55">Error: ${escHtml(parsed.error)}</span>`;
            }
          } catch (_) {}
        }
      }
    }

    // Finalize
    contentEl.innerHTML = marked.parse(fullText || '(no response)');
    document.querySelectorAll('.msg-content pre code').forEach(el => hljs.highlightElement(el));

    activeConvId = newConvId;
    await loadConversations();

  } catch (err) {
    contentEl.innerHTML = `<span style="color:#e55">Connection error: ${escHtml(err.message)}</span>`;
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
    userInput.focus();
  }
}
