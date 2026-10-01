/* Rendering uses textContent or escaped text; model suggestions never change status. */
const $ = (selector) => document.querySelector(selector);
const escapeText = (value) => String(value ?? '').replace(/[&<>"']/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[character]);
const state = { csrf: '', labels: {}, ticket: null, version: 0, busy: false, requestKey: null };
const queueNames = { all: 'All conversations', review: 'Human review', open: 'Open tickets', in_progress: 'In progress', resolved: 'Resolved' };
const statusNames = { open: 'Open', in_progress: 'In progress', resolved: 'Resolved' };
const initials = (name) => name.split(/\s+/).slice(0, 2).map((part) => part[0] || '').join('').toUpperCase();
const percent = (score) => `${Math.round(score * 100)}%`;
const dateLabel = (iso) => new Intl.DateTimeFormat('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }).format(new Date(iso));
let toastTimer;
let searchTimer;

async function api(path, options = {}) {
  const headers = { ...(options.headers || {}) };
  if (options.method && options.method !== 'GET') {
    headers['X-CSRF-Token'] = state.csrf;
    headers['Content-Type'] = 'application/json';
  }
  const response = await fetch(path, { ...options, headers });
  let result;
  try { result = await response.json(); }
  catch { throw new Error('The server returned an unreadable response.'); }
  if (!response.ok) throw new Error(result.error || 'This request could not be completed.');
  return result;
}

function toast(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 4500);
}

function stats(values) {
  for (const [selector, key] of [
    ['#count-all', 'total'], ['#count-review', 'needs_review'], ['#count-open', 'open'],
    ['#count-progress', 'in_progress'], ['#count-resolved', 'resolved'], ['#metric-open', 'open'],
    ['#metric-review', 'needs_review'], ['#metric-progress', 'in_progress'], ['#metric-resolved', 'resolved'],
  ]) $(selector).textContent = values[key];
}

function ticketRow(ticket) {
  const route = ticket.intent === 'unassigned' ? 'Needs human routing' : state.labels[ticket.intent];
  const sub = ticket.review_required ? 'Review required' : `${percent(ticket.prediction.score)} model score`;
  return `<a class="ticket-row" href="#ticket/${encodeURIComponent(ticket.id)}">
    <div class="ticket-summary"><span class="avatar">${escapeText(initials(ticket.customer))}</span>
      <div><h3>${escapeText(ticket.subject)}</h3><p><span class="customer-name">${escapeText(ticket.customer)}</span> · ${escapeText(dateLabel(ticket.created_at))}${ticket.priority === 'high' ? ' · High priority' : ''}</p></div>
    </div><div class="routing-label">${escapeText(route)}<small>${escapeText(sub)}</small></div>
    <span class="badge ${ticket.status}">${statusNames[ticket.status]}</span>
  </a>`;
}

async function route() {
  const version = ++state.version;
  const hash = window.location.hash.slice(1) || 'all';
  const isDetail = hash.startsWith('ticket/');
  $('#inbox-view').hidden = isDetail;
  $('#detail-view').hidden = !isDetail;
  document.querySelectorAll('[data-queue]').forEach((link) => link.classList.toggle('active', link.dataset.queue === hash));
  if (isDetail) {
    $('#detail-title').textContent = 'Opening conversation…';
    $('#detail-content').hidden = true;
    state.ticket = null;
    try {
      const id = decodeURIComponent(hash.slice(7));
      const [result, overview] = await Promise.all([api(`/api/tickets/${encodeURIComponent(id)}`), api('/api/tickets')]);
      if (version !== state.version) return;
      stats(overview.stats);
      state.ticket = result.ticket;
      renderDetail(result);
      $('#detail-content').hidden = false;
    } catch (error) {
      if (version !== state.version) return;
      $('#detail-title').textContent = 'This conversation could not be opened';
      toast(error.message);
    }
    return;
  }
  const queue = queueNames[hash] ? hash : 'all';
  $('#list-heading').textContent = queueNames[queue];
  $('#queue-heading').innerHTML = queue === 'all' ? 'Every conversation,<br><span>connected.</span>' : `${escapeText(queueNames[queue])},<br><span>with context.</span>`;
  try {
    const query = $('#search').value.trim();
    const result = await api(`/api/tickets?queue=${encodeURIComponent(queue)}&q=${encodeURIComponent(query)}`);
    if (version !== state.version) return;
    stats(result.stats);
    $('#result-count').textContent = `${result.tickets.length} conversation${result.tickets.length === 1 ? '' : 's'} shown · newest ${result.limit} records`;
    $('#ticket-list').innerHTML = result.tickets.map(ticketRow).join('') || '<div class="empty-state"><strong>A little breathing room.</strong>No conversations match this view.</div>';
  } catch (error) {
    if (version === state.version) toast(error.message);
  }
}

function renderDetail(result) {
  const ticket = result.ticket;
  const prediction = ticket.prediction;
  $('#ticket-reference').textContent = `CONVERSATION / ${ticket.id.slice(0, 10).toUpperCase()}`;
  $('#detail-title').textContent = ticket.subject;
  $('#detail-status').className = `badge ${ticket.status}`;
  $('#detail-status').textContent = statusNames[ticket.status];
  $('#customer-avatar').textContent = initials(ticket.customer);
  $('#customer-name').textContent = ticket.customer;
  $('#customer-contact').textContent = ticket.email || 'Email not provided · internal ticket';
  $('#created-time').textContent = dateLabel(ticket.created_at);
  $('#ticket-message').textContent = ticket.message;
  $('#predicted-label').textContent = state.labels[prediction.predicted_intent];
  $('#score').textContent = percent(prediction.score);
  $('#model-reason').textContent = `${prediction.reason}. Original prediction stays visible after human corrections.`;
  $('#review-pill').className = `pill ${ticket.review_required ? 'review' : 'clear'}`;
  $('#review-pill').textContent = ticket.review_required ? 'Hold for review' : (ticket.human_reviewed ? 'Human reviewed' : 'Suggested route');
  $('#probabilities').innerHTML = prediction.scores.slice(0, 3).map((row) => `<div class="probability"><span>${escapeText(state.labels[row.intent])}</span><progress max="1" value="${row.score}" aria-label="${escapeText(state.labels[row.intent])} model score"></progress><span>${percent(row.score)}</span></div>`).join('');
  $('#evidence').innerHTML = prediction.evidence.length ? prediction.evidence.map((item) => `<span>${escapeText(item)}</span>`).join('') : '<span>No recognised text features</span>';
  $('#intent').value = ticket.intent;
  $('#priority').value = ticket.priority;
  $('#status').value = ticket.status;
  $('#assignee').value = ticket.assignee;
  $('#reviewed').checked = false;
  $('#review-error').textContent = '';
  $('#revision-note').textContent = `Revision ${ticket.revision} · saved changes keep an audit trail`;
  $('#related-list').innerHTML = result.similar.length ? result.similar.map((row) => `<a class="related-ticket" href="#ticket/${encodeURIComponent(row.id)}"><div><strong>${escapeText(row.subject)}</strong><p>${escapeText(row.customer)} · ${statusNames[row.status]}</p></div><span>${row.exact ? 'Same text' : `${percent(row.score)} similarity`} ↗</span></a>`).join('') : '<p class="help">No close text match in the newest 500 other tickets.</p>';
  $('#history-list').innerHTML = result.events.map((event) => {
    const changes = Object.entries(event.details).map(([key, value]) => {
      if (value && typeof value === 'object' && 'before' in value) return `${key.replaceAll('_', ' ')}: ${value.before} → ${value.after}`;
      return `${key.replaceAll('_', ' ')}: ${value}`;
    }).join(' · ');
    return `<li><strong>${event.action === 'created' ? 'Ticket created & locally classified' : event.action === 'reviewed' ? 'Human review confirmed' : 'Workflow updated'}</strong><p>${escapeText(changes)}</p><time>${escapeText(event.actor)} · ${escapeText(dateLabel(event.created_at))}</time></li>`;
  }).join('');
}

$('#review-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (state.busy || !state.ticket) return;
  const ticket = state.ticket;
  state.busy = true;
  $('#save-review').disabled = true;
  $('#review-error').textContent = '';
  try {
    await api(`/api/tickets/${encodeURIComponent(ticket.id)}`, { method: 'PATCH', body: JSON.stringify({ revision: ticket.revision, intent: $('#intent').value, priority: $('#priority').value, status: $('#status').value, assignee: $('#assignee').value, reviewed: $('#reviewed').checked }) });
    toast('Changes saved. The original model suggestion is preserved.');
    await route();
  } catch (error) {
    if (state.ticket?.id === ticket.id) $('#review-error').textContent = error.message;
    else toast(error.message);
  } finally {
    state.busy = false;
    $('#save-review').disabled = false;
  }
});

document.querySelectorAll('[data-create]').forEach((button) => button.addEventListener('click', () => {
  if (state.busy) return;
  state.requestKey = crypto.randomUUID();
  $('#create-form').reset();
  $('#create-error').textContent = '';
  $('#create-dialog').showModal();
  $('#new-customer').focus();
}));
$('#close-dialog').addEventListener('click', () => $('#create-dialog').close());
$('#create-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (state.busy) return;
  state.busy = true;
  $('#create-submit').disabled = true;
  $('#create-error').textContent = '';
  try {
    const result = await api('/api/tickets', { method: 'POST', body: JSON.stringify({ customer: $('#new-customer').value, email: $('#new-email').value, subject: $('#new-subject').value, message: $('#new-message').value, priority: $('#new-priority').value, request_key: state.requestKey }) });
    $('#create-dialog').close();
    window.location.hash = `ticket/${result.ticket.id}`;
    toast(result.ticket.review_required ? 'Conversation created and held for human review.' : 'Conversation created with a local routing suggestion.');
  } catch (error) {
    $('#create-error').textContent = error.message;
  } finally {
    state.busy = false;
    $('#create-submit').disabled = false;
  }
});
$('#search').addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(route, 250);
});
window.addEventListener('hashchange', route);

async function start() {
  try {
    const result = await api('/api/bootstrap');
    state.csrf = result.csrf;
    state.labels = result.intents;
    stats(result.stats);
    $('#training-note').textContent = `Runs locally. No external AI service. ${result.model.training_examples} training examples · ${result.model.source}.`;
    $('#intent').innerHTML = '<option value="unassigned">Choose an intent…</option>' + Object.entries(result.intents).map(([value, label]) => `<option value="${value}">${escapeText(label)}</option>`).join('');
    $('#assignee').innerHTML = result.agents.map((agent) => `<option>${escapeText(agent)}</option>`).join('');
    await route();
  } catch (error) { toast(`Could not start the workspace: ${error.message}`); }
}
start();
