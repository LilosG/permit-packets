/* Commercial Level 2 EV chargers: its form fields, the run-length hint, the energy management and
   indoor-ventilation fields, and how its plan marks go to the server. */
(() => {
  const RISE_ALLOWANCE_FT = 10;
  const SAMPLE_RUN_FT = 120;
  let context = null;
  let runEdited = false;
  let trenchEdited = false;

  const field = (name) => context.form.elements[name];
  const radios = (name) => context.$$(`input[name=${name}]`);
  const underground = () => field('ce_location').value === 'parking_lot';

  /* The underground part can't be longer than the run. */
  function syncTrench() {
    field('ce_trench_ft').max = field('ce_run_ft').value || 500;
  }

  /* The limit only matters when an energy management system is used; ventilation only indoors. */
  function syncOptions() {
    const managed = document.getElementById('ce-managed').checked;
    document.getElementById('ce-managed-field').hidden = !managed;
    field('ce_managed_amps').disabled = !managed;
    const indoors = field('ce_location').value === 'parking_garage';
    document.getElementById('ce-venting-field').hidden = !indoors;
    field('ce_venting').disabled = !indoors;
  }

  /* Fills the run from the measured route, until the tech types their own. */
  function syncRun() {
    const measured = context.measuredFt();
    if (measured === null) return;
    if (!runEdited) field('ce_run_ft').value = measured + RISE_ALLOWANCE_FT;
    if (!trenchEdited) field('ce_trench_ft').value = underground() ? measured : 0;
    document.getElementById('ce-run-hint').textContent = `${measured} ft measured to the nearest charger, plus ${RISE_ALLOWANCE_FT} ft for rises. Enter the longest run.`;
    syncTrench();
  }

  window.PermitJobTypes.register('commercial_ev_charger', {
    init(ctx) {
      context = ctx;
      field('ce_run_ft').addEventListener('input', () => { runEdited = true; syncTrench(); });
      field('ce_trench_ft').addEventListener('input', () => { trenchEdited = true; });
      radios('ce_location').forEach((box) => box.addEventListener('change', () => { syncOptions(); syncRun(); }));
      document.getElementById('ce-managed').addEventListener('change', syncOptions);
      syncOptions();
      syncTrench();
    },
    /* A new property starts a new plan, so the run and trench are ours to fill in again. */
    onProperty() { runEdited = false; trenchEdited = false; },
    onDetails() {
      syncOptions();
      syncRun();
    },
    onSample() {
      field('ce_run_ft').value = SAMPLE_RUN_FT;
      field('ce_trench_ft').value = underground() ? 90 : 0;
      document.getElementById('ce-run-hint').textContent = '';
      syncTrench();
    },
    jobFields(data) {
      const job = {
        system: data.get('ce_system'), demand_basis: data.get('ce_demand_basis'),
        building_use: data.get('ce_use').trim(), location: data.get('ce_location'),
        charger_model: data.get('ce_model').trim(), existing_demand_kva: Number(data.get('ce_demand_kva')),
        load_management: data.has('ce_managed'),
      };
      [['service_amps', 'ce_service_amps'], ['open_breaker_spaces', 'ce_spaces'], ['charger_count', 'ce_count'],
        ['charger_amps', 'ce_amps'], ['run_ft', 'ce_run_ft'], ['trench_ft', 'ce_trench_ft']]
        .forEach(([key, name]) => { job[key] = Number(data.get(name)); });
      if (job.load_management) job.managed_limit_amps = Number(data.get('ce_managed_amps'));
      if (data.get('ce_accessible') !== '' && data.get('ce_accessible') !== null) job.accessible_spaces = Number(data.get('ce_accessible'));
      if (data.get('ce_venting')) job.charger_venting_required = data.get('ce_venting') === 'yes';
      return { ...job, ...window.PermitJobTypes.electricalFields(data) };
    },
    planFields(marks) {
      return { markers: { panel: marks.points.panel, charger: marks.points.charger }, route: marks.bends };
    },
  });
})();
