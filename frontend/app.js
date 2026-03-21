/* global state */
let sessionId   = null;
let customerName = '';
let isReturning  = false;

/* ── Session start ──────────────────────────────────────────────────────── */
async function startSession(returning) {
  const inputId = returning ? 'returning-name' : 'guest-name';
  const input   = document.getElementById(inputId);
  const name    = input.value.trim();

  if (!name) {
    input.classList.add('shake');
    input.addEventListener('animationend', () => input.classList.remove('shake'), { once: true });
    input.focus();
    return;
  }

  customerName = name;
  isReturning  = returning;

  try {
    const res = await fetch('/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customer_name: name, is_returning: returning }),
    });
    if (!res.ok) throw new Error(await res.text());

    const data = await res.json();
    sessionId = data.session_id;
    openChat(data.message);

  } catch (err) {
    console.error(err);
    alert('Could not start a session. Is the server running?');
  }
}

/* ── Open/close chat ────────────────────────────────────────────────────── */
function openChat(welcomeMessage) {
  document.getElementById('landing').classList.remove('active');

  const chat = document.getElementById('chat');
  chat.classList.add('active');

  // Header
  document.getElementById('header-customer').textContent = customerName;
  const typeBadge = document.getElementById('header-type');
  if (isReturning) {
    typeBadge.textContent  = '⭐ Returning Customer';
    typeBadge.className    = 'type-badge type-returning';
  } else {
    typeBadge.textContent  = 'Guest';
    typeBadge.className    = 'type-badge type-guest';
  }

  // Guest banner
  document.getElementById('guest-banner').style.display = isReturning ? 'none' : 'flex';

  // Clear old messages, show welcome
  document.getElementById('messages').innerHTML = '';
  appendMessage('ai', welcomeMessage);

  document.getElementById('user-input').focus();
}

function goBack() {
  sessionId    = null;
  customerName = '';
  isReturning  = false;

  document.getElementById('chat').classList.remove('active');
  document.getElementById('landing').classList.add('active');
  document.getElementById('messages').innerHTML = '';

  // Reset name inputs
  document.getElementById('guest-name').value     = '';
  document.getElementById('returning-name').value = '';
}

/* ── Send message ───────────────────────────────────────────────────────── */
async function sendMessage() {
  const input   = document.getElementById('user-input');
  const message = input.value.trim();
  if (!message || !sessionId) return;

  input.value = '';
  appendMessage('human', message);
  setLoading(true);

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sessionId, message }),
    });
    if (!res.ok) throw new Error(await res.text());

    const data = await res.json();
    appendMessage('ai', data.response, data.quote_reference);

  } catch (err) {
    console.error(err);
    appendMessage('ai', 'Sorry, something went wrong. Please try again.');
  } finally {
    setLoading(false);
  }
}

/* ── Render messages ────────────────────────────────────────────────────── */
function appendMessage(type, text, quoteRef = null) {
  const messages = document.getElementById('messages');

  const wrap   = document.createElement('div');
  wrap.className = `message message-${type}`;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = text;
  wrap.appendChild(bubble);

  if (quoteRef) {
    const badge = document.createElement('div');
    badge.className   = 'quote-badge';
    badge.textContent = `📋 Quote Ref: ${quoteRef}`;
    wrap.appendChild(badge);
  }

  messages.appendChild(wrap);
  messages.scrollTop = messages.scrollHeight;
}

/* ── Loading / typing indicator ─────────────────────────────────────────── */
function setLoading(on) {
  const btn   = document.getElementById('send-btn');
  const input = document.getElementById('user-input');
  const msgs  = document.getElementById('messages');

  if (on) {
    btn.disabled   = true;
    btn.textContent = '…';
    input.disabled  = true;

    const typing = document.createElement('div');
    typing.className = 'message message-ai';
    typing.id        = 'typing-indicator';
    typing.innerHTML = '<div class="bubble typing"><span></span><span></span><span></span></div>';
    msgs.appendChild(typing);
    msgs.scrollTop = msgs.scrollHeight;
  } else {
    btn.disabled    = false;
    btn.textContent  = 'Send';
    input.disabled   = false;
    const typing = document.getElementById('typing-indicator');
    if (typing) typing.remove();
    input.focus();
  }
}

/* ── Returning-customer upgrade modal ───────────────────────────────────── */
function showLoginPrompt() {
  const modal = document.getElementById('login-modal');
  document.getElementById('modal-name').value = customerName;
  modal.style.display = 'flex';
  setTimeout(() => document.getElementById('modal-name').focus(), 50);
}

function closeModal() {
  document.getElementById('login-modal').style.display = 'none';
}

function closeModalOnBackdrop(e) {
  if (e.target === document.getElementById('login-modal')) closeModal();
}

async function upgradeToReturning() {
  const name = document.getElementById('modal-name').value.trim();
  if (!name) {
    document.getElementById('modal-name').classList.add('shake');
    document.getElementById('modal-name')
      .addEventListener('animationend', () =>
        document.getElementById('modal-name').classList.remove('shake'),
      { once: true });
    return;
  }

  closeModal();

  // Start a fresh session as returning customer
  appendMessage('ai', 'Applying your loyalty discount and restarting your session…');

  try {
    const res = await fetch('/api/session/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ customer_name: name, is_returning: true }),
    });
    if (!res.ok) throw new Error(await res.text());

    const data = await res.json();
    sessionId    = data.session_id;
    customerName = name;
    isReturning  = true;

    // Update header + hide banner
    document.getElementById('header-customer').textContent = name;
    const typeBadge = document.getElementById('header-type');
    typeBadge.textContent = '⭐ Returning Customer';
    typeBadge.className   = 'type-badge type-returning';
    document.getElementById('guest-banner').style.display = 'none';

    // Clear old messages and present fresh welcome
    document.getElementById('messages').innerHTML = '';
    appendMessage('ai', data.message);
    appendMessage('ai', '✅ Your loyalty discount is now active — please describe your problem and we\'ll get a quote to you shortly.');

  } catch (err) {
    console.error(err);
    appendMessage('ai',
      'Sorry, could not apply your discount. You can also mention "I\'m a returning customer" in the chat and we\'ll honour it.');
  }
}

/* ── Keyboard shortcuts on landing ────────────────────────────────────────  */
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('guest-name')
    .addEventListener('keydown', e => { if (e.key === 'Enter') startSession(false); });

  document.getElementById('returning-name')
    .addEventListener('keydown', e => { if (e.key === 'Enter') startSession(true); });
});
