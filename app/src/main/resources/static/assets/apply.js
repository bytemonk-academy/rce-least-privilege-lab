// Candidate application form: drag-and-drop PDF upload to the public endpoint.
(function () {
  const $ = (id) => document.getElementById(id);
  const form = $('apply');
  const input = $('resume');
  const drop = $('drop');
  const chip = $('chip');
  const result = $('result');
  const submit = $('submit');
  const MAX = 2 * 1024 * 1024;
  let file = null;

  function error(text) { result.className = 'result show err'; result.textContent = text; }
  function clearError() { result.className = 'result'; result.textContent = ''; }

  function setFile(f) {
    clearError();
    if (!f) { file = null; chip.classList.add('hidden'); drop.classList.remove('hidden'); input.value = ''; return; }
    if (f.type !== 'application/pdf' && !f.name.toLowerCase().endsWith('.pdf')) return error('Please choose a PDF file.');
    if (f.size > MAX) return error('That file is larger than 2 MB.');
    file = f;
    $('fname').textContent = f.name;
    $('fsize').textContent = f.size < 1024 * 1024 ? `${Math.max(1, Math.round(f.size / 1024))} KB` : `${(f.size / 1048576).toFixed(1)} MB`;
    chip.classList.remove('hidden');
    drop.classList.add('hidden');
  }

  input.addEventListener('change', () => setFile(input.files[0]));
  $('remove').addEventListener('click', () => setFile(null));
  ['dragenter', 'dragover'].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.add('over'); }));
  ['dragleave', 'drop'].forEach((t) => drop.addEventListener(t, (e) => { e.preventDefault(); drop.classList.remove('over'); }));
  drop.addEventListener('drop', (e) => setFile(e.dataTransfer.files[0]));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    clearError();
    if (!$('name').value.trim() || !$('email').value.trim()) return error('Please fill in your name and email.');
    if (!file) return error('Please attach your resume as a PDF.');

    const data = new FormData();
    data.append('name', $('name').value.trim());
    data.append('email', $('email').value.trim());
    data.append('position', $('position').value);
    data.append('resume', file, file.name);

    submit.disabled = true;
    submit.textContent = 'Submitting…';
    try {
      const response = await fetch('/api/applications', { method: 'POST', body: data });
      const body = await response.json().catch(() => ({}));
      if (response.status !== 201) return error(body.message || body.error || `Upload failed (${response.status})`);
      $('ref').textContent = `#${body.id}`;
      form.classList.add('hidden');
      $('done').classList.remove('hidden');
    } catch (err) {
      error(`Network error: ${err.message}`);
    } finally {
      submit.disabled = false;
      submit.textContent = 'Submit application';
    }
  });

  $('again').addEventListener('click', () => {
    setFile(null);
    $('done').classList.add('hidden');
    form.classList.remove('hidden');
  });
})();
