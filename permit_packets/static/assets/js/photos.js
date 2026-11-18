/* Optional site photos for any job type. Each photo is shrunk here (long side 1600 px, JPEG) so the request
   stays small, and it is re-encoded again on the server, which drops the phone's location data. */
(() => {
  const MAX_PHOTOS = 6;
  const LONG_SIDE = 1600;
  const LABELS = [
    'Existing meter and panel', 'Proposed panel location', 'Gas meter and clearances',
    'Service entrance and conduit route', 'Charger location', 'Other',
  ];
  const photos = [];
  const $ = (selector) => document.querySelector(selector);
  const list = $('#photo-list');
  const input = $('#photo-input');
  const error = $('#photo-error');
  if (!list || !input) return;

  const showError = (message) => { error.textContent = message || ''; error.hidden = !message; };

  function shrink(file) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const image = new Image();
      image.onload = () => {
        const scale = Math.min(1, LONG_SIDE / Math.max(image.naturalWidth, image.naturalHeight));
        const canvas = document.createElement('canvas');
        canvas.width = Math.max(1, Math.round(image.naturalWidth * scale));
        canvas.height = Math.max(1, Math.round(image.naturalHeight * scale));
        canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
        resolve({ dataUrl, base64: dataUrl.split(',')[1] });
      };
      image.onerror = () => { URL.revokeObjectURL(url); reject(new Error(file.name)); };
      image.src = url;
    });
  }

  function render() {
    list.replaceChildren(...photos.map((photo, index) => {
      const row = document.createElement('div');
      row.className = 'photo-row';
      const thumb = document.createElement('img');
      thumb.src = photo.dataUrl;
      thumb.alt = photo.label;
      const fields = document.createElement('div');
      const select = document.createElement('select');
      select.setAttribute('aria-label', 'What the photo shows');
      LABELS.forEach((label) => select.add(new Option(label, label, false, label === photo.label)));
      select.addEventListener('change', () => { photo.label = select.value; });
      const caption = document.createElement('input');
      caption.type = 'text';
      caption.maxLength = 120;
      caption.placeholder = 'Caption (optional)';
      caption.value = photo.caption;
      caption.addEventListener('input', () => { photo.caption = caption.value; });
      fields.append(select, caption);
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'quiet';
      remove.textContent = 'Remove';
      remove.addEventListener('click', () => { photos.splice(index, 1); render(); });
      row.append(thumb, fields, remove);
      return row;
    }));
    input.disabled = photos.length >= MAX_PHOTOS;
  }

  input.addEventListener('change', async () => {
    showError('');
    const files = [...input.files].slice(0, MAX_PHOTOS - photos.length);
    for (const file of files) {
      try {
        const { dataUrl, base64 } = await shrink(file);
        if (base64.length > 850000) { showError(`${file.name} is too large. Use a smaller photo.`); continue; }
        const total = photos.reduce((sum, photo) => sum + photo.image_base64.length, 0);
        if (total + base64.length > 3100000) { showError('Too many photos for one packet. Remove one or use smaller photos.'); break; }
        photos.push({ dataUrl, label: LABELS[Math.min(photos.length, LABELS.length - 1)], caption: '', image_base64: base64 });
      } catch {
        showError(`${file.name} could not be read. Use a JPEG or PNG photo.`);
      }
    }
    input.value = '';
    render();
  });

  window.PermitPhotos = {
    get: () => photos.map(({ label, caption, image_base64 }) => ({ label, caption, image_base64 })),
  };
  render();
})();
