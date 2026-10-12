// Local display checks only. Full trace verification remains in the Python CLI.
(() => {
  'use strict';
  const MAX_BYTES = 10 * 1024 * 1024;
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  function need(condition, message) { if (!condition) throw new Error(message); }
  function parseTrace(text) {
    need(typeof text === 'string', 'Expected JSON text.');
    const data = JSON.parse(text);
    need(object(data) && data.trace_version === 1, 'Open a version-1 single-run trace, not a suite or comparison summary.');
    need(typeof data.run_id === 'string' && object(data.scenario) && typeof data.scenario.name === 'string', 'Missing run or scenario identity.');
    for (const name of ['initial_state', 'final_state']) {
      const state = data[name];
      need(object(state) && Array.isArray(state.payments) && Array.isArray(state.refunds), `Missing ${name} ledger.`);
      for (const row of [...state.payments, ...state.refunds]) {
        need(object(row) && typeof row.payment_id === 'string' && typeof row.customer_id === 'string' && Number.isSafeInteger(row.amount_cents) && row.amount_cents > 0, `Invalid ${name} ledger row or unsafe cent amount.`);
      }
      for (const row of state.refunds) need(typeof row.refund_id === 'string' && typeof row.request_id === 'string' && typeof row.idempotency_key === 'string', `Missing ${name} refund identity.`);
    }
    need(object(data.result) && ['pass', 'agent_failure', 'harness_error', 'inconclusive'].includes(data.result.status), 'Missing or unsupported recorded verdict.');
    for (const name of ['tool_events', 'backend_events', 'responses', 'messages', 'fault_schedule']) need(Array.isArray(data[name]), `Missing ${name} evidence.`);
    need(Array.isArray(data.result.violations) && Array.isArray(data.result.expected_intents), 'Missing rule or expected-intent evidence.');
    for (const rule of data.result.violations) need(object(rule) && typeof rule.rule === 'string' && 'expected' in rule && 'observed' in rule && Array.isArray(rule.event_indices), 'Incomplete violated rule.');
    for (const event of data.tool_events) need(object(event) && Number.isSafeInteger(event.index) && typeof event.tool === 'string' && object(event.arguments) && object(event.observed) && Array.isArray(event.backend_events) && 'fault' in event && 'backend_result' in event, 'Incomplete tool event.');
    for (const response of data.responses) {
      need(object(response) && Number.isSafeInteger(response.turn) && Number.isSafeInteger(response.tool_event_end) && Array.isArray(response.claims), 'Incomplete customer-response evidence.');
      for (const claim of response.claims) need(object(claim) && typeof claim.text === 'string' && typeof claim.status === 'string', 'Incomplete customer claim.');
    }
    need(object(data.agent) && object(data.configuration) && object(data.trial_summary), 'Missing agent, configuration, or trial counts.');
    need(data.trial_summary.total_trials === 1 && Number.isSafeInteger(data.trial_summary.failure_count) && [0, 1].includes(data.trial_summary.failure_count), 'Invalid single-run trial counts.');
    need(object(data.result.conversation_assessment), 'Missing separate conversation assessment.');
    need(typeof data.reproduction_command === 'string' && typeof data.created_at === 'string' && typeof data.source_commit === 'string' && typeof data.package_version === 'string' && typeof data.scenario_sha256 === 'string' && typeof data.latency_ms === 'number' && Number.isFinite(data.latency_ms), 'Missing reproduction or version metadata.');
    return data;
  }
  function ledgerRows(data) {
    return data.final_state.payments.map(payment => {
      const sum = state => state.refunds.filter(r => r.payment_id === payment.payment_id).reduce((total, r) => {
        need(Number.isSafeInteger(total + r.amount_cents), 'Refund total exceeds browser integer precision.');
        return total + r.amount_cents;
      }, 0);
      const initial = sum(data.initial_state), final = sum(data.final_state);
      return [payment.payment_id, payment.customer_id, payment.amount_cents, initial, final, final - initial, payment.amount_cents - final];
    });
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = { parseTrace, ledgerRows, MAX_BYTES };
  if (typeof document === 'undefined') return;

  const byId = id => document.getElementById(id);
  const pretty = value => JSON.stringify(value, null, 2);
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = String(text);
    if (className) node.className = className;
    return node;
  }
  function section(parent, title) {
    const node = element('section');
    node.append(element('h2', title));
    parent.append(node);
    return node;
  }
  function table(parent, headers, rows) {
    if (!rows.length) { parent.append(element('p', 'No entries recorded.', 'empty')); return; }
    const wrapper = element('div', undefined, 'scroll'), grid = element('table');
    const head = element('thead'), heading = element('tr');
    headers.forEach(name => { const cell = element('th', name); cell.scope = 'col'; heading.append(cell); });
    head.append(heading);
    const body = element('tbody');
    rows.forEach(values => {
      const row = element('tr');
      values.forEach(value => { const cell = element('td'); cell.append(element('pre', typeof value === 'object' ? pretty(value) : value)); row.append(cell); });
      body.append(row);
    });
    grid.append(head, body); wrapper.append(grid); parent.append(wrapper);
  }
  function evidence(parent, title, value) {
    const node = section(parent, title), details = element('details');
    details.append(element('summary', 'Show recorded JSON'), element('pre', pretty(value)));
    node.append(details);
  }
  function render(data, name) {
    // Build off-DOM so a display error cannot leave a partial verdict on screen.
    const content = element('div');
    const overview = section(content, `Recorded outcome: ${data.result.status.replaceAll('_', ' ')}`);
    overview.append(element('p', `${data.scenario.name} · ${data.run_id} · ${name}`, 'meta'));
    overview.append(element('p', 'Imported evidence — not reverified by this browser. No agent was executed.'));
    const metrics = element('div', undefined, 'metrics');
    [['Recorded verdict', data.result.status], ['Recorded failure count', data.trial_summary.failure_count], ['Recorded total trials', data.trial_summary.total_trials]].forEach(([label, value]) => {
      const metric = element('div', undefined, 'metric'); metric.append(element('strong', value), element('span', label)); metrics.append(metric);
    });
    overview.append(metrics);
    if (data.result.error) overview.append(element('p', `Recorded harness error: ${data.result.error}`));
    table(section(content, 'Violated rules'), ['Rule', 'Expected', 'Observed', 'Event references'], data.result.violations.map(v => [v.rule, v.expected, v.observed, v.event_indices]));
    table(section(content, 'Payment ledger · integer USD cents'), ['Payment', 'Customer', 'Payment amount', 'Refunded before', 'Refunded after', 'New refund total', 'Remaining'], ledgerRows(data));
    evidence(content, 'Expected customer intents', data.result.expected_intents);
    table(section(content, 'Tool timeline · backend versus agent observation'), ['Event / tool', 'Arguments', 'Exact recorded fault', 'Backend result and effects', 'Agent observed'], data.tool_events.map(e => [`${e.index} / ${e.tool}`, e.arguments, e.fault, {result: e.backend_result, events: e.backend_events}, e.observed]));
    evidence(content, 'Customer messages', data.messages);
    evidence(content, 'Customer-facing claims and response boundaries', data.responses);
    evidence(content, 'Conversation assessment · recorded separately', data.result.conversation_assessment);
    evidence(content, 'Initial ledger snapshot', data.initial_state);
    evidence(content, 'Final ledger snapshot', data.final_state);
    evidence(content, 'Seeded fault schedule and backend events', {fault_schedule: data.fault_schedule, backend_events: data.backend_events});
    evidence(content, 'Model, prompt, configuration and recorded versions', {agent: data.agent, configuration: data.configuration, created_at: data.created_at, package_version: data.package_version, source_commit: data.source_commit, scenario_sha256: data.scenario_sha256, latency_ms: data.latency_ms});
    const reproduce = section(content, 'Recorded reproduction command');
    reproduce.append(element('p', 'Shown as text only. Check its path and contents before using it. Run the CLI from your project environment; live model reruns require credentials and may vary.'), element('pre', data.reproduction_command));
    byId('trace-output').replaceChildren(...content.childNodes);
    byId('trace-output').hidden = false;
  }
  let generation = 0;
  function clear(message = 'No trace loaded.', error = false) {
    byId('trace-output').replaceChildren(); byId('trace-output').hidden = true;
    byId('clear').disabled = true;
    byId('import-status').textContent = message;
    byId('import-status').classList.toggle('error', error);
  }
  async function load(name, read) {
    const current = ++generation;
    clear(`Reading ${name}…`);
    try {
      const text = await read();
      if (current !== generation) return;
      need(new TextEncoder().encode(text).length <= MAX_BYTES, 'Trace exceeds the 10 MiB display limit. Use the CLI.');
      render(parseTrace(text), name);
      byId('clear').disabled = false;
      byId('import-status').textContent = `Loaded ${name} locally. Display structure checked; full consistency not verified.`;
    } catch (error) {
      if (current === generation) clear(`Cannot display this trace: ${error.message}`, true);
    }
  }
  byId('trace-file').addEventListener('change', () => {
    const file = byId('trace-file').files[0];
    if (!file) return;
    load(file.name, async () => { need(file.size <= MAX_BYTES, 'Trace exceeds the 10 MiB display limit. Use the CLI.'); return file.text(); });
  });
  byId('clear').addEventListener('click', () => { ++generation; byId('trace-file').value = ''; clear(); });
  document.querySelectorAll('[data-sample]').forEach(button => button.addEventListener('click', () => {
    byId('trace-file').value = '';
    load(button.dataset.sample, async () => {
      const response = await fetch(button.dataset.sample, {credentials: 'omit'});
      need(response.ok, 'Example could not be loaded. Serve examples/ locally or choose its JSON file above.');
      return response.text();
    });
  }));
})();
