// Candidate application form: posts multipart data to the public endpoint.
(function () {
  const form = document.getElementById('apply');
  const fileInput = document.getElementById('resume');
  const fileLabel = document.getElementById('file-label');
  const result = document.getElementById('result');
  const submit = document.getElementById('submit');

  fileInput.addEventListener('change', () => {
    const f = fileInput.files[0];
    fileLabel.textContent = f ? `${f.name} · ${(f.size / 1024).toFixed(1)} KB` : 'Choose a file';
  });

  function show(kind, text) {
    result.className = `result show ${kind}`;
    result.textContent = text;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    submit.disabled = true;
    submit.textContent = 'Uploading…';
    try {
      const response = await fetch('/api/applications', { method: 'POST', body: new FormData(form) });
      const body = await response.json().catch(() => ({}));
      if (response.status === 201) {
        show('ok', `✓ Application #${body.id} received.\n  Resume stored in S3, preview generated, record saved.`);
        fileInput.value = '';
        fileLabel.textContent = 'Choose another file to apply again';
      } else {
        show('err', `✗ ${response.status} ${body.message || body.error || 'Upload failed'}`);
      }
    } catch (err) {
      show('err', `✗ Network error: ${err.message}`);
    } finally {
      submit.disabled = false;
      submit.textContent = 'Submit application';
    }
  });
})();
