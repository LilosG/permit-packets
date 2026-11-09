/* The core flow: job type, property, details, review, submit. Job types plug in through
   window.PermitJobTypes (see job-types/). Everything type-specific comes from /api/job-types
   and from each packet response, so this file knows nothing about any one permit. */
(() => {
  const $ = (selector) => document.querySelector(selector);
  const $$ = (selector) => [...document.querySelectorAll(selector)];
  const esc = (value) => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');

  const TICK_MS = matchMedia('(prefers-reduced-motion: reduce)').matches ? 0 : 320;
  const SAMPLE = { address: '123 Sample St, Oro Valley, AZ 85737', jurisdiction_key: 'oro-valley-az', label: 'Oro Valley, AZ' };
  const ICON_ATTRS = 'viewBox="0 0 28 28" width="28" height="28" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
  const ICONS = {
    ev: `<svg ${ICON_ATTRS}><rect x="4" y="3" width="12" height="22" rx="2"/><path d="M11 8l-3 5h4l-3 5"/><path d="M16 13h4a3 3 0 0 1 3 3v5"/><rect x="20" y="21" width="6" height="4" rx="1"/></svg>`,
    panel: `<svg ${ICON_ATTRS}><rect x="5" y="3" width="18" height="22" rx="2"/><path d="M9 8h4M15 8h4M9 13h4M15 13h4M9 18h4M15 18h4"/></svg>`,
    subpanel: `<svg ${ICON_ATTRS}><rect x="3" y="3" width="13" height="16" rx="2"/><path d="M6 8h2M11 8h2M6 12h2M11 12h2"/><path d="M16 14h3v4"/><rect x="17" y="18" width="8" height="8" rx="1.5"/></svg>`,
  };
  const FALLBACK_ICON = `<svg ${ICON_ATTRS}><rect x="5" y="5" width="18" height="18" rx="2"/></svg>`;

  const form = $('#job');
  let jobTypes = [];
  let current = null;
  let property = null;
  let aerial = null;
  let aerialCredit = null;
  let marks = { points: {}, bends: [] };
  let tool = null;
  let picking = false;
  let packetUrl = null;
  let lastJob = null;
  let lastResult = null;
  let lastType = null;

  const emptyMarks = () => ({ points: {}, bends: [] });
  const modules = () => window.PermitJobTypes.modules;
  const typeModule = () => (current && modules()[current.key]) || {};
  const hasMarks = () => marks.bends.length > 0 || Object.keys(marks.points).length > 0;
  const multiple = () => jobTypes.length > 1;
  const firstStep = () => (multiple() ? 0 : 1);

  /* ---- Steps ---- */
  function stepList() {
    return multiple()
      ? [[0, 'Job type'], [1, 'Property'], [2, 'Details'], [3, 'Review'], [4, 'Submit']]
      : [[1, 'Property'], [2, 'Job'], [3, 'Review'], [4, 'Submit']];
  }
  function renderSteps() {
    const steps = stepList();
    $('#steps').style.setProperty('--steps', String(steps.length));
    $('#steps').innerHTML = steps.map(([number, label]) => `<li data-step="${number}">${esc(label)}</li>`).join('');
  }
  function show(step) {
    $$('[data-panel]').forEach((panel) => { panel.hidden = panel.dataset.panel !== String(step); });
    const now = step === 'building' ? 3 : step;
    $$('ol.steps li').forEach((item) => {
      const number = Number(item.dataset.step);
      item.classList.toggle('done', number < now);
      item.classList.toggle('now', number === now);
    });
    window.scrollTo(0, 0);
  }

  async function api(path, body) {
    const response = await fetch(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
    });
    if (response.status === 401) { location.reload(); throw new Error('Sign in again to continue.'); }
    if (response.ok) return response;
    const data = await response.json().catch(() => ({}));
    const detail = Array.isArray(data.detail) ? data.detail[0]?.msg?.replace(/^Value error, /, '') : data.detail;
    throw new Error(detail || `The request failed (${response.status}). Try again.`);
  }

  /* ---- The selected job type ---- */
  function markerKeys() { return current.markers.map((marker) => marker.key); }
  function firstTool() { return current.markers[0]?.key ?? 'bend'; }

  function renderTools() {
    const bend = '<button type="button" class="tool" data-tool="bend"><span class="dot" style="background:#566572">+</span>Add a bend in the route<span class="state" id="state-bend"></span></button>';
    $('#tools').innerHTML = current.markers.map((marker) =>
      `<button type="button" class="tool" data-tool="${esc(marker.key)}"><span class="dot" style="background:${esc(marker.color)}">${esc(marker.letter)}</span>${esc(marker.prompt)}<span class="state" id="state-${esc(marker.key)}"></span></button>`).join('') + bend;
    const names = current.markers.map((marker) => `the ${marker.key}`).join(', ');
    $('#overlay').setAttribute('aria-label', `Plan of the property. Tap to place ${names} and any bends.`);
    $('#tb-route-block').hidden = !current.route_between;
  }

  /* One type reads "EV permit packets"; several read "Permit packets". */
  function renderHeader() {
    const brand = multiple() ? 'Permit packets' : `${jobTypes[0].short_label} permit packets`;
    $('#brand').textContent = brand;
    document.title = brand.replace('packets', 'Packets').replace('permit', 'Permit');
  }

  /* Shows the form sections that belong to this type, and keeps hidden fields out of the payload. */
  function applyType() {
    const slugName = current.short_label.toLowerCase();
    $('#download').setAttribute('download', `${slugName}-permit-packet-demo.pdf`);
    $$('[data-job-type]').forEach((element) => { element.hidden = element.dataset.jobType !== current.key; });
    $$('[data-uses]').forEach((element) => { element.hidden = !current[`uses_${element.dataset.uses}`]; });
    [...form.elements].forEach((field) => { field.disabled = Boolean(field.closest('[data-job-type][hidden], [data-uses][hidden]')); });
    $('#details-summary').textContent = current.uses_home_loads ? 'Exact nameplate values and contractor' : 'Contractor';
    renderTools();
    tool = firstTool();
    if (property) drawPlan();
  }

  function chooseType(key) {
    const next = jobTypes.find((type) => type.key === key);
    if (!next) return;
    const changed = current && current.key !== next.key;
    current = next;
    applyType();
    if (changed && hasMarks()) {
      marks = emptyMarks();
      tool = firstTool();
      if (property) drawPlan();
    }
    $$('.type-card').forEach((card) => {
      const selected = card.dataset.type === key;
      card.setAttribute('aria-checked', String(selected));
      card.tabIndex = selected ? 0 : -1;
    });
    $('#type-continue').disabled = false;
  }

  function renderTypeCards() {
    $('#type-list').innerHTML = jobTypes.map((type, index) =>
      `<button type="button" class="type-card" role="radio" aria-checked="false" tabindex="${index === 0 ? 0 : -1}" data-type="${esc(type.key)}">${ICONS[type.icon] || FALLBACK_ICON}<span class="type-title">${esc(type.label)}</span><span class="type-blurb">${esc(type.blurb)}</span></button>`).join('');
  }
  $('#type-list').addEventListener('click', (event) => {
    const card = event.target.closest('.type-card');
    if (card) chooseType(card.dataset.type);
  });
  $('#type-list').addEventListener('keydown', (event) => {
    const cards = $$('.type-card');
    const index = cards.indexOf(document.activeElement);
    if (index < 0) return;
    const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[event.key];
    if (!step) return;
    event.preventDefault();
    const next = cards[(index + step + cards.length) % cards.length];
    chooseType(next.dataset.type);
    next.focus();
  });
  $('#type-continue').addEventListener('click', () => show(1));
  $('#change-type').addEventListener('click', () => show(0));

  /* ---- The plan: outlines, lot line and the marked route, in 0-1000 plan units ---- */
  function poly(points, attrs) {
    return `<polygon points="${points.map((p) => p.join(',')).join(' ')}" ${attrs}/>`;
  }
  function routePoints() {
    const between = current.route_between;
    if (!between) return [];
    const [start, end] = between.map((key) => marks.points[key]);
    return start && end ? [start, ...marks.bends, end] : [];
  }
  function measuredFt() {
    const points = routePoints();
    if (!property || !points.length) return null;
    let units = 0;
    for (let i = 1; i < points.length; i += 1) units += Math.hypot(points[i][0] - points[i - 1][0], points[i][1] - points[i - 1][1]);
    return Math.round(units * property.view.feet_per_unit);
  }
  function marker(point, fill, text) {
    return `<g transform="translate(${point[0]} ${point[1]})"><circle r="19" fill="${fill}" stroke="#fff" stroke-width="4"/><text text-anchor="middle" dy="7" font-size="20" font-weight="700" fill="#fff" font-family="IBM Plex Sans, sans-serif">${esc(text)}</text></g>`;
  }
  function drawPlan() {
    /* The photo shows the buildings, and outline data can sit a few feet off. */
    let svg = aerial ? '' : property.buildings.map((building, index) =>
      poly(building, `fill="${index === property.primary_building ? 'rgba(255,255,255,.14)' : 'none'}" stroke="#15212c" stroke-width="${index === property.primary_building ? 4 : 2}"`)).join('');
    if (property.lot.length) {
      svg += poly(property.lot, 'fill="none" stroke="#15212c" stroke-width="7"');
      svg += poly(property.lot, 'fill="none" stroke="#ffd84d" stroke-width="3.5" stroke-dasharray="16 9"');
    }
    const route = routePoints();
    if (route.length) {
      const line = route.map((p) => p.join(',')).join(' ');
      svg += `<polyline points="${line}" fill="none" stroke="#fff" stroke-width="11" stroke-linejoin="round" stroke-linecap="round"/>`;
      svg += `<polyline points="${line}" fill="none" stroke="#c8682a" stroke-width="6" stroke-linejoin="round" stroke-linecap="round"/>`;
    }
    marks.bends.forEach((point) => { svg += `<circle cx="${point[0]}" cy="${point[1]}" r="9" fill="#fff" stroke="#c8682a" stroke-width="5"/>`; });
    current.markers.forEach((spot) => {
      if (marks.points[spot.key]) svg += marker(marks.points[spot.key], spot.color, spot.letter);
    });
    $('#overlay').innerHTML = svg;

    $$('.tool').forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.tool === tool)));
    current.markers.forEach((spot) => { $(`#state-${spot.key}`).textContent = marks.points[spot.key] ? 'Placed' : ''; });
    $('#state-bend').textContent = marks.bends.length ? String(marks.bends.length) : '';
    const feet = measuredFt();
    $('#tb-route').textContent = feet === null ? 'Not marked yet' : `${feet} ft`;
    $('#to-job').disabled = !current.markers.every((spot) => marks.points[spot.key]);
  }

  /* After a marker, the next unplaced one in order, then bends. */
  function nextTool(key) {
    const keys = markerKeys();
    const later = keys.slice(keys.indexOf(key) + 1).find((other) => !marks.points[other]);
    return later || 'bend';
  }

  $('#overlay').addEventListener('click', (event) => {
    const box = event.currentTarget.getBoundingClientRect();
    const point = [
      Math.round((event.clientX - box.left) / box.width * 1000),
      Math.round((event.clientY - box.top) / box.height * 1000),
    ];
    if (picking) { setPicking(false); changeView({ tap: point }); return; }
    if (tool === 'bend') marks.bends.push(point);
    else { marks.points[tool] = point; tool = nextTool(tool); }
    drawPlan();
  });
  $('#tools').addEventListener('click', (event) => {
    const button = event.target.closest('.tool');
    if (!button) return;
    tool = button.dataset.tool;
    drawPlan();
  });
  /* Undo takes back the last bend, then the markers, newest first. */
  $('#undo').addEventListener('click', () => {
    if (marks.bends.length) marks.bends.pop();
    else {
      const last = [...current.markers].reverse().find((spot) => marks.points[spot.key]);
      if (last) { delete marks.points[last.key]; tool = last.key; }
    }
    drawPlan();
  });
  $('#clear').addEventListener('click', () => { marks = emptyMarks(); tool = firstTool(); drawPlan(); });

  async function loadAerial(found) {
    const status = $('#aerial-status');
    status.hidden = false;
    status.textContent = 'Loading the aerial photo, about 15 seconds. You can start marking now.';
    try {
      const response = await api('/api/property/aerial', {
        latitude: found.view.latitude, longitude: found.view.longitude, scale_ft_per_in: found.view.scale_ft_per_in,
      });
      const data = await response.json();
      if (property !== found) return;
      aerial = data.image;
      aerialCredit = data.credit;
      $('#aerial').src = `data:image/jpeg;base64,${aerial}`;
      $('#aerial').hidden = false;
      status.hidden = true;
      drawPlan();
    } catch (error) {
      if (property === found) status.textContent = 'No aerial right now. The plan still works from the outlines.';
    }
  }

  /* ---- Address suggestions as the tech types. Typing the whole address still works. ---- */
  const addressInput = $('#address');
  const suggestionList = $('#suggestions');
  const SUGGEST_DELAY_MS = 220;
  let suggestTimer = null;
  let suggestRequest = 0;
  let activeSuggestion = -1;

  function closeSuggestions() {
    suggestionList.hidden = true;
    suggestionList.innerHTML = '';
    activeSuggestion = -1;
    addressInput.setAttribute('aria-expanded', 'false');
    addressInput.removeAttribute('aria-activedescendant');
  }
  function suggestionItems() { return $$('#suggestions li[role=option]'); }
  function markActive() {
    suggestionItems().forEach((item, index) => item.setAttribute('aria-selected', String(index === activeSuggestion)));
    if (activeSuggestion >= 0) addressInput.setAttribute('aria-activedescendant', `suggestion-${activeSuggestion}`);
    else addressInput.removeAttribute('aria-activedescendant');
  }
  function chooseSuggestion(text) {
    suggestRequest += 1;
    clearTimeout(suggestTimer);
    addressInput.value = text;
    closeSuggestions();
    $('#find').requestSubmit();
  }
  async function loadSuggestions(text, request) {
    const response = await api('/api/property/suggest', { text }).catch(() => null);
    const data = response ? await response.json().catch(() => null) : null;
    if (request !== suggestRequest || document.activeElement !== addressInput) return;
    const suggestions = data?.suggestions || [];
    if (!suggestions.length) { closeSuggestions(); return; }
    suggestionList.innerHTML = suggestions
      .map((item, index) => `<li role="option" id="suggestion-${index}" aria-selected="false">${esc(item)}</li>`).join('')
      + '<li class="credit" role="presentation">Suggestions from OpenStreetMap contributors</li>';
    activeSuggestion = -1;
    suggestionList.hidden = false;
    addressInput.setAttribute('aria-expanded', 'true');
  }
  addressInput.addEventListener('input', () => {
    clearTimeout(suggestTimer);
    suggestRequest += 1;
    const text = addressInput.value.trim();
    if (text.length < 4) { closeSuggestions(); return; }
    const request = suggestRequest;
    suggestTimer = setTimeout(() => loadSuggestions(text, request), SUGGEST_DELAY_MS);
  });
  addressInput.addEventListener('keydown', (event) => {
    const items = suggestionItems();
    if (event.key === 'Escape') { closeSuggestions(); return; }
    if (!items.length) return;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      activeSuggestion = (activeSuggestion + step + items.length) % items.length;
      markActive();
    } else if (event.key === 'Enter' && activeSuggestion >= 0) {
      event.preventDefault();
      chooseSuggestion(items[activeSuggestion].textContent);
    }
  });
  /* mousedown fires before the input loses focus, so the list is still there. */
  suggestionList.addEventListener('mousedown', (event) => {
    const item = event.target.closest('li[role=option]');
    event.preventDefault();
    if (item) chooseSuggestion(item.textContent);
  });
  addressInput.addEventListener('blur', closeSuggestions);

  /* ---- The property ---- */
  function locatedNote(found) {
    if (found.address_confirmed === true) return ['good', 'Matched to the county record'];
    if (found.address_confirmed === false) return ['check', `County lists this parcel as number ${found.parcel_house_number}. Check the house.`];
    if (found.located_by === 'map') return ['good', 'Matched to the house on the map'];
    if (found.located_by === 'tap') return ['good', 'House chosen by you'];
    return ['check', 'Estimated from the street. Check this is the right house.'];
  }

  function showProperty(found) {
    property = found;
    aerial = null;
    aerialCredit = null;
    marks = emptyMarks();
    tool = firstTool();
    typeModule().onProperty?.();
    $('#aerial').hidden = true;
    $('#tb-address').textContent = found.address;
    $('#tb-parcel').textContent = found.parcel_number ? `Parcel ${found.parcel_number}` : 'Parcel lines not set up for this county';
    const [tone, note] = locatedNote(found);
    $('#tb-located').className = `located ${tone}`;
    $('#tb-located').textContent = note;
    $('#tb-city').textContent = found.jurisdiction.label;
    const link = $('#tb-checklist');
    link.textContent = found.jurisdiction.known ? `${found.jurisdiction.checklist.length}-item checklist loaded` : 'General checklist. City rules are added in setup.';
    if (found.jurisdiction.source_url) link.href = found.jurisdiction.source_url; else link.removeAttribute('href');
    $('#tb-scale').textContent = `Plan scale: 1 in = ${found.view.scale_ft_per_in} ft`;
    $('#bar-city').textContent = found.jurisdiction.label;
    $('#site').hidden = false;
    drawPlan();
    loadAerial(found);
  }

  async function changeView(change) {
    const found = property;
    const status = $('#aerial-status');
    status.hidden = false;
    status.textContent = 'Updating the plan';
    try {
      const response = await api('/api/property/view', {
        address: found.address, city: found.city, state: found.state, county_fips: found.county_fips,
        house_number: found.house_number, located_by: found.located_by,
        latitude: found.view.latitude, longitude: found.view.longitude,
        anchor_latitude: found.anchor.latitude, anchor_longitude: found.anchor.longitude,
        scale_ft_per_in: found.view.scale_ft_per_in, job_type: current.key, ...change,
      });
      showProperty(await response.json());
    } catch (error) {
      status.textContent = error.message;
    }
  }

  function setPicking(on) {
    picking = on;
    $('#pick-note').hidden = !on;
  }
  $('#wrong-house').addEventListener('click', () => setPicking(!picking));
  $('#zoom-out').addEventListener('click', () => changeView({ zoom: 1 }));
  $('#zoom-in').addEventListener('click', () => changeView({ zoom: -1 }));

  $('#find').addEventListener('submit', async (event) => {
    event.preventDefault();
    setPicking(false);
    suggestRequest += 1;
    clearTimeout(suggestTimer);
    closeSuggestions();
    const button = $('#find-button');
    $('#find-error').hidden = true;
    button.disabled = true;
    button.textContent = 'Finding';
    try {
      await ready;
      if (!current) throw new Error('No job types are set up for this account.');
      const response = await api('/api/property', { address: $('#address').value, job_type: current.key });
      const found = await response.json();
      showProperty(found);
      $('#site').scrollIntoView({ behavior: TICK_MS ? 'smooth' : 'auto', block: 'start' });
    } catch (error) {
      property = null;
      $('#site').hidden = true;
      $('#bar-city').textContent = 'Demo';
      $('#find-error').textContent = error.message;
      $('#find-error').hidden = false;
    } finally {
      button.disabled = false;
      button.textContent = 'Find property';
    }
  });

  /* What a job type's script can ask of the page. */
  const context = { form, $, $$, measuredFt };

  $('#to-job').addEventListener('click', () => {
    typeModule().onDetails?.();
    $('#job-lead').textContent = property.jurisdiction.known
      ? `${property.address}, using the ${property.jurisdiction.label} checklist.`
      : `${property.address}, using the general checklist. ${property.jurisdiction.name}'s rules are added in setup.`;
    show(2);
  });
  $('#use-sample').addEventListener('click', async () => {
    await ready;
    if (!current) return;
    property = null;
    typeModule().onSample?.();
    $('#job-lead').textContent = `Sample job with a schematic layout, using the ${SAMPLE.label} checklist.`;
    $('#bar-city').textContent = SAMPLE.label;
    show(2);
  });
  $('#back-property').addEventListener('click', () => show(1));
  $$('#appliances input[data-load]').forEach((box) => box.addEventListener('change', () => {
    form.elements[box.dataset.load].value = box.checked ? box.dataset.va : 0;
  }));

  /* ---- The job ---- */
  function jobData() {
    const data = new FormData(form);
    const job = {
      customer: data.get('customer'), contractor: data.get('contractor'), license_number: data.get('license_number'),
      sample_mode: data.has('sample_mode'),
      ...typeModule().jobFields(data),
    };
    if (current.uses_home_loads) {
      job.home = {};
      $$('[data-home]').forEach((input) => { job.home[input.name] = Number(input.value); });
    }
    if (!property) return { ...job, address: SAMPLE.address, jurisdiction_key: SAMPLE.jurisdiction_key };
    const planFields = typeModule().planFields
      ? typeModule().planFields(marks)
      : { markers: marks.points, route: marks.bends };
    return {
      ...job, address: property.address, city: property.city, state: property.state,
      jurisdiction_key: property.jurisdiction.key,
      plan: {
        scale_ft_per_in: property.view.scale_ft_per_in, ...planFields,
        buildings: property.buildings, primary_building: property.primary_building, lot: property.lot,
        parcel_number: property.parcel_number, aerial_base64: aerial,
        credits: [...property.credits.filter((credit) => !aerial || !credit.startsWith('Building')), ...(aerialCredit ? [aerialCredit] : [])],
      },
    };
  }

  const wait = (ms) => new Promise((resolve) => { setTimeout(resolve, ms); });

  async function tickResults(result) {
    $('#build-list').innerHTML = result.build_steps.map((line) => `<li>${esc(line)}</li>`).join('');
    for (const item of $$('#build-list li')) {
      await wait(TICK_MS);
      item.classList.add('done');
    }
    await wait(TICK_MS);
  }

  function renderReview(result) {
    $('#status').classList.toggle('bad', !result.ready);
    $('#status-title').textContent = result.ready ? 'Draft packet ready for review' : 'This job needs a fix first';
    $('#status-note').textContent = result.ready ? 'All engineering checks pass.' : 'See the checks below, then change the job.';
    $('#stats').innerHTML = result.summary.map((stat) => `<div><dt>${esc(stat.label)}</dt><dd>${esc(stat.value)}</dd></div>`).join('');
    $('#checks').innerHTML = result.checks
      .map((check) => `<li><span class="${check.passed ? 'pass' : 'fix'}">${check.passed ? 'Pass' : 'Fix'}</span> ${esc(check.name)}: ${esc(check.result)}</li>`).join('');
    $('#flags').innerHTML = result.flags
      .map((flag) => `<label class="flag"><input type="checkbox"><span>${esc(flag)}</span></label>`).join('');
    $('#approve').dataset.ready = String(result.ready);
    updateApproval();
    const feature = result.feature_page;
    const order = [feature, ...result.pages.map((_, index) => index).filter((index) => index !== feature)]
      .filter((index) => index < result.pages.length);
    $('#pages').innerHTML = order.map((index) => {
      const src = `data:image/jpeg;base64,${result.pages[index]}`;
      const title = result.documents[index]?.title || '';
      return `<a href="${src}" target="_blank" rel="noopener" class="${index === feature ? 'feature' : ''}"><img src="${src}" alt="Packet page ${index + 1}: ${esc(title)}"></a>`;
    }).join('');
    const bytes = Uint8Array.from(atob(result.pdf), (char) => char.charCodeAt(0));
    if (packetUrl) URL.revokeObjectURL(packetUrl);
    packetUrl = URL.createObjectURL(new Blob([bytes], { type: 'application/pdf' }));
    $('#open-packet').href = packetUrl;
    $('#download').href = packetUrl;
  }

  function updateApproval() {
    const boxes = $$('#flags input');
    const reviewed = boxes.filter((box) => box.checked).length;
    const ready = $('#approve').dataset.ready === 'true';
    $('#review-count').textContent = ready ? `${reviewed} of ${boxes.length} items reviewed` : 'Fix the job before it can be approved.';
    $('#approve').disabled = !ready || reviewed < boxes.length;
  }

  function renderSubmit(result) {
    const place = result.jurisdiction;
    $('#how-city').textContent = `Submitting in ${place.label}`;
    const sets = place.sets_required > 1 ? ` The city asks for ${place.sets_required} sets.` : '';
    $('#how-text').textContent = `${place.submit_how}${sets}`;
    const contact = [place.department, place.phone].filter(Boolean).join(', ');
    $('#how-contact').textContent = contact;
    const portal = $('#portal');
    portal.hidden = !place.website;
    if (place.website) { portal.href = place.website; portal.textContent = `Open ${place.website_label}`; }
    $('#fields').innerHTML = result.fields.map((field, index) =>
      `<div><dt>${esc(field.label)}</dt><dd id="field-${index}">${esc(field.value)}</dd><button type="button" class="copy" data-copy="field-${index}">Copy</button></div>`).join('');
    $('#email-section').hidden = !place.email;
    if (place.email) {
      const { subject, body } = result.submission_email;
      $('#email').textContent = `To: ${place.email}\nSubject: ${subject}\n\n${body}`;
      $('#email-open').href = `mailto:${place.email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
    }
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    $('#job-error').hidden = true;
    const job = jobData();
    const type = current;
    $('#build-list').innerHTML = '';
    show('building');
    try {
      const response = await api(`/api/jobs/${type.slug}/packet`, job);
      const result = await response.json();
      lastJob = job;
      lastResult = result;
      lastType = type;
      await tickResults(result);
      renderReview(result);
      show(3);
    } catch (error) {
      show(2);
      $('#job-error').textContent = error.message;
      $('#job-error').hidden = false;
    }
  });

  $('#flags').addEventListener('change', updateApproval);
  $('#approve').addEventListener('click', () => { renderSubmit(lastResult); show(4); });
  $('#edit').addEventListener('click', () => show(2));
  $('#restart').addEventListener('click', () => show(firstStep()));
  $('#documents').addEventListener('click', async () => {
    const button = $('#documents');
    $('#documents-error').hidden = true;
    button.disabled = true;
    try {
      const response = await api(`/api/jobs/${lastType.slug}/documents`, lastJob);
      const named = /filename="([^"]+)"/.exec(response.headers.get('Content-Disposition') || '');
      const link = document.createElement('a');
      link.href = URL.createObjectURL(await response.blob());
      link.download = named ? named[1] : `${lastType.short_label.toLowerCase()}-permit-documents-demo.zip`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (error) {
      $('#documents-error').textContent = error.message;
      $('#documents-error').hidden = false;
    } finally {
      button.disabled = false;
    }
  });
  document.addEventListener('click', async (event) => {
    const button = event.target.closest('[data-copy], #email-copy');
    if (!button) return;
    const source = button.id === 'email-copy' ? $('#email') : document.getElementById(button.dataset.copy);
    await navigator.clipboard.writeText(source.textContent).catch(() => {});
    const label = button.textContent;
    button.textContent = 'Copied';
    setTimeout(() => { button.textContent = label; }, 1200);
  });

  /* ---- Start: learn which job types this client has ---- */
  async function start() {
    try {
      const response = await fetch('/api/job-types');
      if (response.status === 401) { location.reload(); return; }
      if (!response.ok) throw new Error(`The request failed (${response.status}).`);
      jobTypes = (await response.json()).job_types;
    } catch (error) {
      $('#find-error').textContent = 'Could not load the job types. Reload the page to try again.';
      $('#find-error').hidden = false;
      return;
    }
    if (!jobTypes.length) {
      $('#find-error').textContent = 'No job types are set up for this account.';
      $('#find-error').hidden = false;
      return;
    }
    jobTypes.forEach((type) => modules()[type.key]?.init?.(context));
    renderSteps();
    $('#change-type').hidden = !multiple();
    renderHeader();
    if (multiple()) renderTypeCards();
    else chooseType(jobTypes[0].key);
    show(firstStep());
  }
  const ready = start();
})();
