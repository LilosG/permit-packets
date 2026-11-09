/* EV charger: its form fields, the run-length hint and how its plan marks go to the server. */
(() => {
  const RISE_ALLOWANCE_FT = 10;
  let context = null;
  let runEdited = false;

  /* Fills the wire run and trench from the measured route, until the tech types their own. */
  function syncRun() {
    const measured = context.measuredFt();
    if (measured === null) return;
    const { form } = context;
    if (!runEdited) {
      form.elements.run_ft.value = measured + RISE_ALLOWANCE_FT;
      form.elements.trench_ft.value = form.elements.location.value === 'detached_garage' ? measured : 0;
    }
    document.getElementById('run-hint').textContent = `${measured} ft measured, plus ${RISE_ALLOWANCE_FT} ft for rises`;
  }

  window.PermitJobTypes.register('ev_charger', {
    init(ctx) {
      context = ctx;
      const { form } = ctx;
      form.elements.run_ft.addEventListener('input', () => { runEdited = true; });
      form.elements.trench_ft.addEventListener('input', () => { runEdited = true; });
      ctx.$$('input[name=location]').forEach((input) => input.addEventListener('change', syncRun));
    },
    /* A new property starts a new plan, so the run is ours to fill in again. */
    onProperty() { runEdited = false; },
    onDetails: syncRun,
    onSample() {
      const { form } = context;
      form.elements.run_ft.value = 58;
      form.elements.trench_ft.value = 0;
      document.getElementById('run-hint').textContent = '';
    },
    jobFields(data) {
      const job = {
        charger_model: data.get('charger_model').trim(), has_solar: data.has('has_solar'),
        connection: data.get('connection'), location: data.get('location'),
      };
      ['charger_amps', 'run_ft', 'trench_ft', 'service_amps', 'open_breaker_spaces'].forEach((name) => {
        job[name] = Number(data.get(name));
      });
      return job;
    },
    planFields(marks) {
      return { markers: { panel: marks.points.panel, charger: marks.points.charger }, route: marks.bends };
    },
  });
})();
