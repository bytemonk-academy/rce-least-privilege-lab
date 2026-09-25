// Recruiter console. Credentials stay in memory only; reload the page to sign out.
// X-Requested-With stops Spring Security from sending a WWW-Authenticate challenge,
// so the browser never shows its own Basic-auth popup.
(function () {
  let auth = null;
  let applications = [];
  let selectedId = null;
  let pdfUrl = null;

  const $ = (id) => document.getElementById(id);

  async function api(path, opts = {}) {
    const response = await fetch(path, {
      ...opts,
      headers: { Authorization: auth, 'X-Requested-With': 'XMLHttpRequest', ...(opts.headers || {}) },
    });
    if (response.status === 401) throw Object.assign(new Error('Wrong username or password'), { status: 401 });
    if (response.status === 403) throw Object.assign(new Error('Not allowed'), { status: 403 });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response;
  }

  function formatDate(value) {
    if (!value) return '';
    const d = new Date(value);
    return isNaN(d) ? value : d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  }

  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function renderRows() {
    $('count').textContent = `(${applications.length})`;
    if (!applications.length) {
      $('rows').innerHTML = '<tr><td colspan="4" class="empty">No applications yet. Submit one on the Apply page.</td></tr>';
      return;
    }
    $('rows').innerHTML = applications.map((a) => `
      <tr class="clickable ${a.id === selectedId ? 'selected' : ''}" data-id="${a.id}">
        <td><span class="id">${a.id}</span></td>
        <td>${escapeHtml(a.name)}<div class="email">${escapeHtml(a.email)}</div></td>
        <td>${escapeHtml(a.position)}</td>
        <td class="mono" style="font-size:12.5px;color:var(--muted)">${escapeHtml(formatDate(a.submittedAt))}</td>
      </tr>`).join('');
  }

  function select(id) {
    selectedId = id;
    const a = applications.find((x) => x.id === id);
    renderRows();
    if (!a) return;
    $('detail-empty').classList.add('hidden');
    $('detail-body').classList.remove('hidden');
    $('d-name').textContent = a.name;
    $('d-email').textContent = a.email;
    $('d-position').textContent = a.position;
    $('d-key').textContent = a.resumeKey;
    $('d-preview').textContent = a.resumePreview || '(no preview: previews are disabled or the PDF had no text)';
    $('d-pdf').classList.add('hidden');
    if (pdfUrl) { URL.revokeObjectURL(pdfUrl); pdfUrl = null; }
  }

  async function load() {
    const response = await api('/api/applications');
    applications = await response.json();
    renderRows();
    if (selectedId && applications.some((a) => a.id === selectedId)) select(selectedId);
  }

  $('rows').addEventListener('click', (event) => {
    const row = event.target.closest('tr[data-id]');
    if (row) select(Number(row.dataset.id));
  });

  $('d-open').addEventListener('click', async () => {
    const button = $('d-open');
    button.disabled = true;
    button.textContent = 'Downloading from S3…';
    try {
      const response = await api(`/api/applications/${selectedId}/resume`);
      const blob = await response.blob();
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
      pdfUrl = URL.createObjectURL(new Blob([blob], { type: 'application/pdf' }));
      $('d-pdf').src = pdfUrl;
      $('d-pdf').classList.remove('hidden');
    } catch (err) {
      alert(err.message);
    } finally {
      button.disabled = false;
      button.textContent = 'Open resume from S3';
    }
  });

  $('login').addEventListener('submit', async (event) => {
    event.preventDefault();
    const user = $('username').value.trim();
    auth = 'Basic ' + btoa(`${user}:${$('password').value}`);
    const out = $('login-result');
    $('login-btn').disabled = true;
    try {
      await load();
      $('who').textContent = `${user} · ROLE_RECRUITER`;
      $('login-view').classList.add('hidden');
      $('console-view').classList.remove('hidden');
    } catch (err) {
      auth = null;
      out.className = 'result show err';
      out.textContent = `✗ ${err.status || ''} ${err.message}`.trim();
    } finally {
      $('login-btn').disabled = false;
    }
  });

  $('refresh').addEventListener('click', () => load().catch((err) => alert(err.message)));
  $('logout').addEventListener('click', () => {
    auth = null; applications = []; selectedId = null;
    $('password').value = '';
    $('console-view').classList.add('hidden');
    $('login-view').classList.remove('hidden');
    $('login-result').className = 'result';
  });
})();
