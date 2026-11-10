/* 240 V circuit: its form fields (they change with the appliance), the run-length hint
   and how its plan marks go to the server. */
(() => {
  const RISE_ALLOWANCE_FT = 10;
  const SAMPLE_RUN_FT = 40;
  const VOLTS = 240;
  const HVAC = ['heat_pump', 'mini_split'];
  let context = null;
  let runEdited = false;
  let trenchEdited = false;

  const field = (name) => context.form.elements[name];
  const appliance = () => context.form.querySelector('input[name=ac_appliance]:checked').value;

  /* Shows only the fields for this appliance. A hidden field is disabled so the browser doesn't
     ask for it and it stays out of the payload. */
  function syncAppliance() {
    const chosen = appliance();
    context.$$('[data-ac]').forEach((element) => {
      const shown = element.dataset.ac.split(' ').includes(chosen);
      element.hidden = !shown;
      element.querySelectorAll('input').forEach((input) => { input.disabled = !shown; });
    });
    syncKilowatts();
  }

  /* The amps a heater of this size draws at 240 V. */
  function syncKilowatts() {
    const kw = Number(field('ac_heater_kw').value);
    const amps = Math.round(kw * 1000 / VOLTS * 10) / 10;
    document.getElementById('ac-kw-hint').textContent = kw > 0 ? `Works out to ${amps} A at ${VOLTS} V` : '';
  }

  /* The underground part can't be longer than the run. */
  function syncTrench() {
    field('ac_trench_ft').max = field('ac_run_ft').value || 500;
  }

  /* Fills the run from the measured route, until the tech types their own. */
  function syncRun() {
    const measured = context.measuredFt();
    if (measured === null) return;
    if (!runEdited) field('ac_run_ft').value = measured + RISE_ALLOWANCE_FT;
    if (!trenchEdited) field('ac_trench_ft').value = 0;
    document.getElementById('ac-run-hint').textContent = `${measured} ft measured, plus ${RISE_ALLOWANCE_FT} ft for rises`;
    syncTrench();
  }

  const optionalNumber = (value) => (value === '' || value === null ? null : Number(value));

  window.PermitJobTypes.register('appliance_circuit', {
    init(ctx) {
      context = ctx;
      ctx.$$('input[name=ac_appliance]').forEach((box) => box.addEventListener('change', syncAppliance));
      field('ac_heater_kw').addEventListener('input', syncKilowatts);
      field('ac_run_ft').addEventListener('input', () => { runEdited = true; syncTrench(); });
      field('ac_trench_ft').addEventListener('input', () => { trenchEdited = true; });
      syncAppliance();
      syncTrench();
    },
    /* A new property starts a new plan, so the run and trench are ours to fill in again. */
    onProperty() { runEdited = false; trenchEdited = false; },
    onDetails() {
      syncAppliance();
      syncRun();
    },
    onSample() {
      syncAppliance();
      field('ac_run_ft').value = SAMPLE_RUN_FT;
      field('ac_trench_ft').value = 0;
      document.getElementById('ac-run-hint').textContent = '';
      syncTrench();
    },
    jobFields(data) {
      const chosen = appliance();
      const job = {
        appliance: chosen, appliance_model: data.get('ac_model').trim(),
        location: data.get('ac_location'), wiring: data.get('ac_wiring'),
        run_ft: Number(data.get('ac_run_ft')), trench_ft: Number(data.get('ac_trench_ft')),
        service_amps: Number(data.get('ac_service_amps')), open_breaker_spaces: Number(data.get('ac_spaces')),
        terminals_75c: data.has('ac_75c'),
      };
      if (chosen === 'hot_tub' || chosen === 'other') job.nameplate_amps = Number(data.get('ac_nameplate_amps'));
      if (chosen === 'sauna') job.heater_kw = Number(data.get('ac_heater_kw'));
      if (HVAC.includes(chosen)) {
        job.mca = Number(data.get('ac_mca'));
        job.mocp = Number(data.get('ac_mocp'));
      } else {
        job.manufacturer_breaker = optionalNumber(data.get('ac_breaker'));
      }
      if (chosen === 'hot_tub') {
        job.gfci = data.get('ac_gfci');
        job.disconnect_distance_ft = Number(data.get('ac_disconnect_ft'));
      }
      if (chosen === 'other') {
        job.continuous = data.has('ac_continuous');
        job.needs_neutral = data.has('ac_neutral');
      }
      return job;
    },
    planFields(marks) {
      return { markers: { panel: marks.points.panel, appliance: marks.points.appliance }, route: marks.bends };
    },
  });
})();
