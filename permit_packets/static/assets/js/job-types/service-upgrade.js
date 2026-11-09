/* Panel / service upgrade: its form fields, the service-size rules, the wire-length hint,
   the planned loads and how its plan marks go to the server. */
(() => {
  const EXTRA_WIRE_FT = 5;
  const MAX_PLANNED_LOADS = 4;
  const SMALLEST_NEW_SERVICE = 100;
  const PREFERRED_NEW_SERVICE = 200;
  const SAMPLE_WIRE_FT = 8;
  let context = null;
  let wireEdited = false;
  let busEdited = false;

  const field = (name) => context.form.elements[name];
  const radios = (name) => context.$$(`input[name=${name}]`);
  const plannedRows = () => context.$$('.planned-row');

  /* A replacement keeps the size; an upgrade has to go up. Options that break that are greyed out. */
  function syncService() {
    const replacement = field('scope').value === 'replacement';
    const existingBoxes = radios('existing_service_amps');
    /* There is no 60 A size to replace a 60 A panel with, so a 60 A service can only be upgraded. */
    existingBoxes.forEach((box) => { box.disabled = replacement && Number(box.value) < SMALLEST_NEW_SERVICE; });
    if (existingBoxes.find((box) => box.checked)?.disabled) existingBoxes.find((box) => !box.disabled).checked = true;

    const existing = Number(field('existing_service_amps').value);
    const newBoxes = radios('new_service_amps');
    newBoxes.forEach((box) => {
      const amps = Number(box.value);
      box.disabled = replacement ? amps !== existing : amps <= existing;
    });
    if (!newBoxes.some((box) => box.checked && !box.disabled)) {
      const open = newBoxes.filter((box) => !box.disabled);
      const pick = replacement ? open[0] : open.find((box) => Number(box.value) === PREFERRED_NEW_SERVICE) || open[0];
      if (pick) pick.checked = true;
    }
    const bus = field('bus_amps');
    bus.min = field('new_service_amps').value;
    if (!busEdited) bus.value = field('new_service_amps').value;
  }

  /* Fills the wire length from the measured route, until the tech types their own. */
  function syncWire() {
    const measured = context.measuredFt();
    if (measured === null) return;
    if (!wireEdited) field('se_length_ft').value = measured + EXTRA_WIRE_FT;
    document.getElementById('wire-hint').textContent = `${measured} ft measured, plus ${EXTRA_WIRE_FT} ft to reach the equipment`;
  }

  function syncElectrodes() {
    const boxes = radios('electrodes');
    boxes[0].setCustomValidity(boxes.some((box) => box.checked) ? '' : 'Pick at least one grounding electrode.');
  }

  function syncSolar() {
    const on = document.getElementById('solar').checked;
    document.getElementById('pv-field').hidden = !on;
    document.getElementById('pv-breaker').required = on;
  }

  /* A half-filled row would be refused by the server, so make the browser ask for the other half. */
  function syncRow(row) {
    const label = row.querySelector('.planned-label');
    const va = row.querySelector('.planned-va');
    const started = Boolean(label.value.trim() || va.value);
    label.required = started;
    va.required = started;
  }

  function addRow(label = '', va = '') {
    if (plannedRows().length >= MAX_PLANNED_LOADS) return null;
    const row = document.createElement('div');
    row.className = 'planned-row';
    row.innerHTML = '<label class="field">Load<input class="planned-label" maxlength="60" placeholder="Example: Heat pump"></label>'
      + '<label class="field">VA<input class="planned-va" type="number" min="1" max="60000"></label>'
      + '<button type="button" class="quiet" aria-label="Remove this planned load">Remove</button>';
    row.querySelector('.planned-label').value = label;
    row.querySelector('.planned-va').value = va;
    document.getElementById('planned-rows').append(row);
    syncRow(row);
    return row;
  }

  /* A chip fills the next empty row, and adds one while there is room. */
  function fillNextRow(label, va) {
    const empty = plannedRows().find((row) => !row.querySelector('.planned-label').value.trim() && !row.querySelector('.planned-va').value);
    const row = empty || addRow();
    if (!row) return;
    row.querySelector('.planned-label').value = label;
    row.querySelector('.planned-va').value = va;
    syncRow(row);
  }

  function plannedLoads() {
    return plannedRows()
      .map((row) => ({ label: row.querySelector('.planned-label').value.trim(), va: Number(row.querySelector('.planned-va').value) }))
      .filter((load) => load.label && load.va);
  }

  function resetPlanned() {
    document.getElementById('planned-rows').innerHTML = '';
    addRow();
  }

  window.PermitJobTypes.register('service_upgrade', {
    init(ctx) {
      context = ctx;
      const { form } = ctx;
      ['scope', 'existing_service_amps'].forEach((name) => radios(name).forEach((box) => box.addEventListener('change', syncService)));
      radios('new_service_amps').forEach((box) => box.addEventListener('change', syncService));
      field('bus_amps').addEventListener('input', () => { busEdited = true; });
      field('se_length_ft').addEventListener('input', () => { wireEdited = true; });
      radios('electrodes').forEach((box) => box.addEventListener('change', syncElectrodes));
      document.getElementById('solar').addEventListener('change', syncSolar);
      form.addEventListener('input', (event) => {
        const row = event.target.closest('.planned-row');
        if (row) syncRow(row);
      });
      document.getElementById('planned-rows').addEventListener('click', (event) => {
        const row = event.target.closest('.planned-row');
        if (!row || !event.target.closest('button')) return;
        row.remove();
        if (!plannedRows().length) addRow();
      });
      document.getElementById('planned-chips').addEventListener('click', (event) => {
        const chip = event.target.closest('button[data-planned]');
        if (chip) fillNextRow(chip.dataset.planned, chip.dataset.va);
      });
      resetPlanned();
      syncService();
      syncElectrodes();
      syncSolar();
    },
    /* A new property starts a new plan, so the wire length is ours to fill in again. */
    onProperty() { wireEdited = false; },
    onDetails() {
      syncService();
      syncWire();
    },
    onSample() {
      syncService();
      field('se_length_ft').value = SAMPLE_WIRE_FT;
      document.getElementById('wire-hint').textContent = '';
    },
    jobFields(data) {
      const solar = data.has('solar');
      const job = {
        scope: data.get('scope'), equipment: data.get('equipment'), service_drop: data.get('service_drop'),
        relocated: data.get('relocated') === 'yes', material: data.get('material'), conduit: data.get('conduit'),
        electrodes: data.getAll('electrodes'), panel_model: data.get('panel_model').trim(),
        existing_brand: data.get('existing_brand'), utility: data.get('utility').trim(),
        meter_number: data.get('meter_number').trim(), has_solar: solar,
        pv_breaker_amps: solar ? Number(data.get('pv_breaker_amps')) : 0,
        planned_loads: plannedLoads(),
      };
      ['existing_service_amps', 'new_service_amps', 'se_length_ft', 'bus_amps'].forEach((name) => {
        job[name] = Number(data.get(name));
      });
      return job;
    },
    planFields(marks) {
      return { markers: { meter: marks.points.meter, panel: marks.points.panel }, route: marks.bends };
    },
  });
})();
