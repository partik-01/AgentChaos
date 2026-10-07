// Educational playback of the recorded timeout examples. No API or payment execution.
(() => {
  let policy = 'flawed';
  let step = 0;
  const common = [
    {
      title: '“Please refund 300 cents.”',
      description: 'Alice requests a $3.00 refund from her $10.00 payment. Agent Chaos starts with a fresh simulated database and records the request before any tools run.',
      refunded: 0, knowledge: 'Requested',
      agentDetail: 'The customer wants 300 cents. Nothing has executed yet.',
      label: 'THE BUSINESS RULE',
      evidence: 'Refund 300 cents to Alice, once. The request ID identifies this one customer intent.'
    },
    {
      title: 'The agent checks Alice’s payment.',
      description: 'The agent calls get_payment. The service confirms that pay_alice belongs to Alice and that 1,000 cents remain refundable. A 300-cent refund is allowed.',
      refunded: 0, knowledge: 'Eligible',
      agentDetail: 'Ownership and refundable balance are confirmed.',
      label: 'THE FIRST TOOL CALL',
      evidence: 'get_payment returns authoritative payment information. The ledger still has no refund.'
    },
    {
      title: 'The payment service commits the refund.',
      description: 'The agent calls create_refund for 300 cents. SQLite records one successful refund and reduces the remaining refundable balance to 700 cents. The response has not reached the agent yet.',
      refunded: 300, knowledge: 'Waiting',
      agentDetail: 'The agent has made the call, but has not received a result.',
      label: 'THE ECONOMIC EFFECT',
      evidence: 'Refund rf_000001 is committed. A missing response cannot undo the refund.'
    },
    {
      title: 'A timeout hides the successful result.',
      description: 'The fault middleware lets creation finish, then replaces its response with a timeout. This is the after_timeout fault on the first create_refund call. The actual refund stays committed.',
      refunded: 300, knowledge: 'Unknown',
      agentDetail: 'The tool reports a timeout and says execution is unknown.',
      label: 'STATE AND OBSERVATION DIVERGE',
      evidence: 'Backend: succeeded. Agent observation: timeout. “I did not get a response” does not mean “nothing happened.”'
    }
  ];
  const endings = {
    flawed: [
      {
        title: 'A fresh retry creates another refund.',
        description: 'The flawed agent treats the timeout as a failed refund. It retries with a new idempotency key. The service accepts this as another operation and commits a second 300-cent refund.',
        refunded: 600, knowledge: 'Says completed',
        agentDetail: 'The reply says “Refunded 300 USD cents for payment pay_alice.”',
        label: 'THE RETRY MISTAKE',
        evidence: 'attempt:1 and attempt:2 are different keys. A service can enforce each key correctly while the agent duplicates the customer’s intent.', bad: true
      },
      {
        title: 'The verifier exposes the duplicate.',
        description: 'The verifier reads the final ledger independently of the agent’s reply. Alice requested 300 cents once, but two refund rows total 600 cents. The report marks this run as an agent failure.',
        refunded: 600, knowledge: 'Agent failure',
        agentDetail: 'The final result comes from deterministic checks, not the agent’s success message.',
        label: 'EXPECTED 300 · OBSERVED 600',
        evidence: 'Violated rules: exact_total_refunded, no_duplicate_economic_effect, and exact_amount_per_request. The recorded fault and both commits are retained.', bad: true
      }
    ],
    corrected: [
      {
        title: 'The agent confirms the original refund.',
        description: 'The corrected agent keeps the original key, request:refund-001, and calls get_refund_status. It observes that the first 300-cent refund succeeded, so it does not create a second refund.',
        refunded: 300, knowledge: 'Confirmed',
        agentDetail: 'The status observation confirms the payment, customer, request, and 300-cent amount.',
        label: 'RECONCILE BEFORE CLAIMING SUCCESS',
        evidence: 'If status were unavailable, retrying creation with the same key and identical parameters would return the original refund. If confirmation remained unavailable, the agent should report uncertainty.'
      },
      {
        title: 'One request. One refund. A pass.',
        description: 'The verifier finds one 300-cent refund for Alice’s request, no change to Bob’s payment, and a completion claim supported by a matching tool observation. The scripted run passes.',
        refunded: 300, knowledge: 'Pass',
        agentDetail: 'The reported outcome agrees with the independently verified business result.',
        label: 'EXPECTED 300 · OBSERVED 300',
        evidence: 'The runner saves initial state, final state, messages, tool events, and the exact fault. Rerunning restores the original starting state to test the policy again.'
      }
    ]
  };
  const byId = id => document.getElementById(id);
  function render() {
    const current = [...common, ...endings[policy]][step];
    byId('step-count').textContent = `STEP ${step + 1} OF 6`;
    byId('stage-title').textContent = current.title;
    byId('stage-description').textContent = current.description;
    byId('ledger-value').textContent = `${current.refunded.toLocaleString('en-US')} cents`;
    byId('ledger-detail').textContent = `${(1000 - current.refunded).toLocaleString('en-US')} cents remain refundable.`;
    byId('agent-value').textContent = current.knowledge;
    byId('agent-detail').textContent = current.agentDetail;
    byId('evidence-label').textContent = current.label;
    byId('evidence-text').textContent = current.evidence;
    byId('explanation').classList.toggle('bad', Boolean(current.bad));
    byId('previous').disabled = step === 0;
    byId('next').disabled = step === 5;
    byId('next').textContent = step === 5 ? 'Walkthrough complete' : 'Next step →';
    document.querySelectorAll('[data-step]').forEach(button => {
      const index = Number(button.dataset.step);
      if (index === step) button.setAttribute('aria-current', 'step');
      else button.removeAttribute('aria-current');
      button.classList.toggle('done', index < step);
    });
    document.querySelectorAll('[data-policy]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.policy === policy));
    });
  }
  byId('next').addEventListener('click', () => { step = Math.min(step + 1, 5); render(); });
  byId('previous').addEventListener('click', () => { step = Math.max(step - 1, 0); render(); });
  byId('restart').addEventListener('click', () => { step = 0; render(); });
  document.querySelectorAll('[data-step]').forEach(button => {
    button.addEventListener('click', () => { step = Number(button.dataset.step); render(); });
  });
  document.querySelectorAll('[data-policy]').forEach(button => {
    button.addEventListener('click', () => { policy = button.dataset.policy; render(); });
  });
  document.querySelectorAll('[data-copy]').forEach(button => {
    button.addEventListener('click', async () => {
      const code = byId(button.dataset.copy);
      try {
        await navigator.clipboard.writeText(code.textContent);
        byId('copy-status').textContent = 'Command copied. Paste it into your terminal after the quick start.';
      } catch {
        const range = document.createRange();
        range.selectNodeContents(code);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        byId('copy-status').textContent = 'Command selected. Use your browser’s copy shortcut.';
      }
    });
  });
  render();
})();
