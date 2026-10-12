const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { parseTrace, ledgerRows, MAX_BYTES } = require('../examples/viewer.js');
const fixture = name => fs.readFileSync(path.join(__dirname, '..', 'examples', name), 'utf8');

test('real failed and corrected recordings show their actual economic difference', () => {
  const failed = parseTrace(fixture('timeout-flawed.json'));
  const corrected = parseTrace(fixture('timeout-corrected.json'));
  assert.equal(failed.result.status, 'agent_failure');
  assert.equal(corrected.result.status, 'pass');
  assert.deepEqual(ledgerRows(failed).find(row => row[0] === 'pay_alice'), ['pay_alice', 'alice', 1000, 0, 600, 600, 400]);
  assert.deepEqual(ledgerRows(corrected).find(row => row[0] === 'pay_alice'), ['pay_alice', 'alice', 1000, 0, 300, 300, 700]);
  assert.equal(failed.tool_events[1].observed.error, 'timeout');
  assert.equal(failed.tool_events[1].backend_result.status, 'succeeded');
});

test('summary reports, malformed JSON and unsupported versions cannot become displayed runs', () => {
  for (const input of ['null', '[]', '{broken', fixture('benchmark-summary.json'), '{"trace_version":2}']) {
    assert.throws(() => parseTrace(input));
  }
});

for (const field of ['initial_state', 'final_state', 'result', 'tool_events', 'responses', 'messages', 'backend_events', 'agent', 'configuration', 'trial_summary', 'fault_schedule', 'scenario_sha256']) {
  test(`missing ${field} fails before display`, () => {
    const trace = JSON.parse(fixture('timeout-flawed.json'));
    delete trace[field];
    assert.throws(() => parseTrace(JSON.stringify(trace)));
  });
}

test('prior refunds are separated from new economic effect', () => {
  const trace = parseTrace(fixture('timeout-corrected.json'));
  trace.initial_state.refunds = [trace.final_state.refunds[0]];
  assert.deepEqual(ledgerRows(trace).find(row => row[0] === 'pay_alice').slice(3), [300, 300, 0, 700]);
});

test('unsafe integer amounts and aggregate overflow are rejected rather than rounded', () => {
  const trace = JSON.parse(fixture('timeout-flawed.json'));
  trace.final_state.refunds[0].amount_cents = Number.MAX_SAFE_INTEGER + 1;
  assert.throws(() => parseTrace(JSON.stringify(trace)), /unsafe cent amount/);
  trace.final_state.refunds[0].amount_cents = Number.MAX_SAFE_INTEGER;
  assert.throws(() => ledgerRows(parseTrace(JSON.stringify(trace))), /integer precision/);
  assert.equal(MAX_BYTES, 10 * 1024 * 1024);
});

test('viewer preserves raw customer text and evidence without claiming full validation', () => {
  const trace = JSON.parse(fixture('timeout-corrected.json'));
  const hostile = '<img src="https://example.invalid/tracker" onerror="alert(1)">';
  trace.responses[0].claims[0].text = hostile;
  trace.scenario_sha256 = 'changed';
  const text = JSON.stringify(trace);
  assert.equal(parseTrace(text).responses[0].claims[0].text, hostile);
  assert.equal(JSON.stringify(parseTrace(text)), text);
  // This intentionally accepts displayable but inconsistent evidence. The page
  // labels it as recorded, not reverified; full validation belongs to the CLI.
});
