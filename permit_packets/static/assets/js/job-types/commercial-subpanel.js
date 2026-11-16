/* Commercial subpanel / feeder: its form fields, the breaker and trench rules, the run-length hint,
   the loads on the subpanel and how its plan marks go to the server. */
(() => {
  const RISE_ALLOWANCE_FT = 10;
  const MAX_LOADS = 8;
  const SAMPLE_RUN_FT = 85;
  let context = null;
  let runEdited = false;
  let trenchEdited = false;

  const field = (name) => context.form.elements[name];
  const radios = (name) => context.$$(`input[name=${name}]`);
  const loadRows = () => context.$$('.com-load-row');
  const text = (row, selector) => row.querySelector(selector);

  /* A breaker can't be larger than the subpanel, so those options are greyed out. */
  function syncBreakers() {
    const size = Number(field('cs_subpanel_amps').value);
    const boxes = radios('cs_breaker_amps');
    boxes.forEach((box) => { box.disabled = Number(box.value) > size; });
    if (!boxes.some((box) => box.checked && !box.disabled)) {
      const open = boxes.filter((box) => !box.disabled);
      const pick = open.find((box) => Number(box.value) === size) || open[open.length - 1];
      if (pick) pick.checked = true;
    }
  }

  /* The underground part can't be longer than the run. */
  function syncTrench() {
    field('cs_trench_ft').max = field('cs_run_ft').value || 500;
  }

  /* Fills the run from the measured route, until the tech types their own. */
  function syncRun() {
    const measured = context.measuredFt();
    if (measured === null) return;
    if (!runEdited) field('cs_run_ft').value = measured + RISE_ALLOWANCE_FT;
    if (!trenchEdited) field('cs_trench_ft').value = field('cs_location').value === 'detached_building' ? measured : 0;
    document.getElementById('cs-run-hint').textContent = `${measured} ft measured, plus ${RISE_ALLOWANCE_FT} ft for rises`;
    syncTrench();
  }

  /* A half-filled row would be refused by the server, so make the browser ask for the other half. */
  function syncRow(row) {
    const label = text(row, '.com-load-label');
    const kva = text(row, '.com-load-kva');
    const started = Boolean(label.value.trim() || kva.value);
    label.required = started;
    kva.required = started;
  }

  function addRow(label = '', kva = '', continuous = false) {
    if (loadRows().length >= MAX_LOADS) return null;
    const row = document.createElement('div');
    row.className = 'com-load-row';
    row.innerHTML = '<label class="field">Load<input class="com-load-label" maxlength="60" placeholder="Example: Kitchen equipment"></label>'
      + '<label class="field">kVA<input class="com-load-kva" type="number" min="0.1" max="500" step="0.1"></label>'
      + '<label class="choice"><input type="checkbox" class="com-load-cont"><span>Continuous</span></label>'
      + '<button type="button" class="quiet" aria-label="Remove this load">Remove</button>';
    text(row, '.com-load-label').value = label;
    text(row, '.com-load-kva').value = kva;
    text(row, '.com-load-cont').checked = continuous;
    document.getElementById('cs-rows').append(row);
    syncRow(row);
    return row;
  }

  /* A chip fills the next empty row, and adds one while there is room. */
  function fillNextRow(label, kva, continuous) {
    const empty = loadRows().find((row) => !text(row, '.com-load-label').value.trim() && !text(row, '.com-load-kva').value);
    const row = empty || addRow();
    if (!row) return;
    text(row, '.com-load-label').value = label;
    text(row, '.com-load-kva').value = kva;
    text(row, '.com-load-cont').checked = continuous;
    syncRow(row);
  }

  function loads() {
    return loadRows()
      .map((row) => ({
        label: text(row, '.com-load-label').value.trim(), kva: Number(text(row, '.com-load-kva').value),
        continuous: text(row, '.com-load-cont').checked,
      }))
      .filter((load) => load.label && load.kva);
  }

  function resetLoads() {
    document.getElementById('cs-rows').innerHTML = '';
    addRow();
  }

  window.PermitJobTypes.register('commercial_subpanel', {
    init(ctx) {
      context = ctx;
      const { form } = ctx;
      radios('cs_subpanel_amps').forEach((box) => box.addEventListener('change', syncBreakers));
      radios('cs_location').forEach((box) => box.addEventListener('change', syncRun));
      field('cs_run_ft').addEventListener('input', () => { runEdited = true; syncTrench(); });
      field('cs_trench_ft').addEventListener('input', () => { trenchEdited = true; });
      form.addEventListener('input', (event) => {
        const row = event.target.closest('.com-load-row');
        if (row) syncRow(row);
      });
      document.getElementById('cs-rows').addEventListener('click', (event) => {
        const row = event.target.closest('.com-load-row');
        if (!row || !event.target.closest('button')) return;
        row.remove();
        if (!loadRows().length) addRow();
      });
      document.getElementById('cs-chips').addEventListener('click', (event) => {
        const chip = event.target.closest('button[data-load]');
        if (chip) fillNextRow(chip.dataset.load, chip.dataset.kva, chip.dataset.continuous === '1');
      });
      resetLoads();
      syncBreakers();
      syncTrench();
    },
    /* A new property starts a new plan, so the run and trench are ours to fill in again. */
    onProperty() { runEdited = false; trenchEdited = false; },
    onDetails() {
      syncBreakers();
      syncRun();
    },
    onSample() {
      field('cs_run_ft').value = SAMPLE_RUN_FT;
      field('cs_trench_ft').value = field('cs_location').value === 'detached_building' ? SAMPLE_RUN_FT : 0;
      document.getElementById('cs-run-hint').textContent = '';
      syncTrench();
    },
    jobFields(data) {
      const job = {
        system: data.get('cs_system'), demand_basis: data.get('cs_demand_basis'),
        building_use: data.get('cs_use').trim(), location: data.get('cs_location'),
        material: data.get('cs_material'), conduit: data.get('cs_conduit'),
        subpanel_model: data.get('cs_model').trim(), loads: loads(),
        existing_demand_kva: Number(data.get('cs_demand_kva')),
      };
      [['service_amps', 'cs_service_amps'], ['open_breaker_spaces', 'cs_spaces'], ['subpanel_amps', 'cs_subpanel_amps'],
        ['feeder_breaker_amps', 'cs_breaker_amps'], ['run_ft', 'cs_run_ft'], ['trench_ft', 'cs_trench_ft']]
        .forEach(([key, name]) => { job[key] = Number(data.get(name)); });
      return { ...job, ...window.PermitJobTypes.electricalFields(data) };
    },
    planFields(marks) {
      return { markers: { panel: marks.points.panel, subpanel: marks.points.subpanel }, route: marks.bends };
    },
  });
})();
