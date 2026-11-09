/* Subpanel / feeder: its form fields, the breaker and building rules, the run-length hint,
   the loads on the subpanel and how its plan marks go to the server. */
(() => {
  const RISE_ALLOWANCE_FT = 10;
  const MAX_LOADS = 6;
  const SAMPLE_RUN_FT = 40;
  let context = null;
  let runEdited = false;
  let trenchEdited = false;

  const field = (name) => context.form.elements[name];
  const radios = (name) => context.$$(`input[name=${name}]`);
  const loadRows = () => context.$$('.sub-load-row');

  /* A breaker can't be larger than the subpanel, so those options are greyed out. */
  function syncBreakers() {
    const size = Number(field('sp_subpanel_amps').value);
    const boxes = radios('sp_breaker_amps');
    boxes.forEach((box) => { box.disabled = Number(box.value) > size; });
    if (!boxes.some((box) => box.checked && !box.disabled)) {
      const open = boxes.filter((box) => !box.disabled);
      const pick = open.find((box) => Number(box.value) === size) || open[open.length - 1];
      if (pick) pick.checked = true;
    }
  }

  /* "Feeds the whole home" only makes sense for a subpanel in the same building. */
  function syncLocation() {
    const same = field('sp_location').value === 'same_building';
    document.getElementById('sp-whole-field').hidden = !same;
    if (!same) document.getElementById('sp-whole').checked = false;
  }

  /* The underground part can't be longer than the run. */
  function syncTrench() {
    field('sp_trench_ft').max = field('sp_run_ft').value || 500;
  }

  /* Fills the run from the measured route, until the tech types their own. */
  function syncRun() {
    const measured = context.measuredFt();
    if (measured === null) return;
    if (!runEdited) field('sp_run_ft').value = measured + RISE_ALLOWANCE_FT;
    if (!trenchEdited) field('sp_trench_ft').value = field('sp_location').value === 'detached_building' ? measured : 0;
    document.getElementById('sp-run-hint').textContent = `${measured} ft measured, plus ${RISE_ALLOWANCE_FT} ft for rises`;
    syncTrench();
  }

  /* A half-filled row would be refused by the server, so make the browser ask for the other half. */
  function syncRow(row) {
    const label = row.querySelector('.sub-load-label');
    const va = row.querySelector('.sub-load-va');
    const started = Boolean(label.value.trim() || va.value);
    label.required = started;
    va.required = started;
  }

  function addRow(label = '', va = '') {
    if (loadRows().length >= MAX_LOADS) return null;
    const row = document.createElement('div');
    row.className = 'sub-load-row';
    row.innerHTML = '<label class="field">Load<input class="sub-load-label" maxlength="60" placeholder="Example: Shop circuits"></label>'
      + '<label class="field">VA<input class="sub-load-va" type="number" min="1" max="60000"></label>'
      + '<button type="button" class="quiet" aria-label="Remove this load">Remove</button>';
    row.querySelector('.sub-load-label').value = label;
    row.querySelector('.sub-load-va').value = va;
    document.getElementById('sub-rows').append(row);
    syncRow(row);
    return row;
  }

  /* A chip fills the next empty row, and adds one while there is room. */
  function fillNextRow(label, va) {
    const empty = loadRows().find((row) => !row.querySelector('.sub-load-label').value.trim() && !row.querySelector('.sub-load-va').value);
    const row = empty || addRow();
    if (!row) return;
    row.querySelector('.sub-load-label').value = label;
    row.querySelector('.sub-load-va').value = va;
    syncRow(row);
  }

  function loads() {
    return loadRows()
      .map((row) => ({ label: row.querySelector('.sub-load-label').value.trim(), va: Number(row.querySelector('.sub-load-va').value) }))
      .filter((load) => load.label && load.va);
  }

  function resetLoads() {
    document.getElementById('sub-rows').innerHTML = '';
    addRow();
  }

  window.PermitJobTypes.register('subpanel', {
    init(ctx) {
      context = ctx;
      const { form } = ctx;
      radios('sp_subpanel_amps').forEach((box) => box.addEventListener('change', syncBreakers));
      radios('sp_location').forEach((box) => box.addEventListener('change', () => { syncLocation(); syncRun(); }));
      field('sp_run_ft').addEventListener('input', () => { runEdited = true; syncTrench(); });
      field('sp_trench_ft').addEventListener('input', () => { trenchEdited = true; });
      form.addEventListener('input', (event) => {
        const row = event.target.closest('.sub-load-row');
        if (row) syncRow(row);
      });
      document.getElementById('sub-rows').addEventListener('click', (event) => {
        const row = event.target.closest('.sub-load-row');
        if (!row || !event.target.closest('button')) return;
        row.remove();
        if (!loadRows().length) addRow();
      });
      document.getElementById('sub-chips').addEventListener('click', (event) => {
        const chip = event.target.closest('button[data-sub-load]');
        if (chip) fillNextRow(chip.dataset.subLoad, chip.dataset.va);
      });
      resetLoads();
      syncBreakers();
      syncLocation();
      syncTrench();
    },
    /* A new property starts a new plan, so the run and trench are ours to fill in again. */
    onProperty() { runEdited = false; trenchEdited = false; },
    onDetails() {
      syncBreakers();
      syncLocation();
      syncRun();
    },
    onSample() {
      field('sp_run_ft').value = SAMPLE_RUN_FT;
      field('sp_trench_ft').value = field('sp_location').value === 'detached_building' ? SAMPLE_RUN_FT : 0;
      document.getElementById('sp-run-hint').textContent = '';
      syncTrench();
    },
    jobFields(data) {
      const location = data.get('sp_location');
      const job = {
        location, material: data.get('sp_material'), conduit: data.get('sp_conduit'),
        whole_dwelling: location === 'same_building' && data.has('sp_whole'),
        subpanel_model: data.get('sp_model').trim(), loads: loads(),
      };
      [['subpanel_amps', 'sp_subpanel_amps'], ['feeder_breaker_amps', 'sp_breaker_amps'], ['run_ft', 'sp_run_ft'],
        ['trench_ft', 'sp_trench_ft'], ['service_amps', 'sp_service_amps'], ['open_breaker_spaces', 'sp_spaces']]
        .forEach(([key, name]) => { job[key] = Number(data.get(name)); });
      return job;
    },
    planFields(marks) {
      return { markers: { panel: marks.points.panel, subpanel: marks.points.subpanel }, route: marks.bends };
    },
  });
})();
