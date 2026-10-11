/*
 * End-to-end evaluation of the live FALCON pipeline on evaluation/falcon_eval.csv.
 *
 * Usage: open the deployed app (https://beingbalaji.github.io/FALCON/) in a desktop
 * browser, open the developer console, paste this file and press Enter.
 * Progress is printed to the console; the summary and per-claim results are
 * stored in window.falconEval and downloaded as JSON when the run finishes.
 *
 * Mapping to the three evaluation labels:
 *   Supported ...     -> SUPPORTED
 *   Contradicted ...  -> REFUTED
 *   Insufficient ...  -> NOT ENOUGH INFO
 *   Conflicting ...   -> CONFLICT (counted as wrong for SUPPORTED/REFUTED claims)
 */
(async () => {
  const E = FalconEvidence;
  const parseCsv = text => text.trim().split(/\r?\n/).slice(1).map(line => {
    const m = line.match(/^"(.*)","(.*)"$/);
    return m ? {claim: m[1].replace(/""/g, '"'), expected: m[2]} : null;
  }).filter(Boolean);
  const cases = parseCsv(await (await fetch('evaluation/falcon_eval.csv')).text());

  const worker = new Worker('evidence-worker.js?v=4', {type: 'module'});
  let seq = 0; const pending = {};
  worker.onmessage = ({data}) => {
    const p = pending[data.id];
    if (!p || data.kind === 'progress') return;
    delete pending[data.id];
    data.kind === 'error' ? p.reject(new Error(data.message)) : p.resolve(data);
  };
  const call = msg => new Promise((resolve, reject) => {
    const id = ++seq; pending[id] = {resolve, reject}; worker.postMessage({id, ...msg});
  });
  const toLabel = s => s.startsWith('Supported') ? 'SUPPORTED' : s.startsWith('Contradicted') ? 'REFUTED'
    : s.startsWith('Conflicting') ? 'CONFLICT' : 'NOT ENOUGH INFO';

  const results = [];
  for (const [i, {claim, expected}] of cases.entries()) {
    const record = {claim, expected};
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 30000);
      let report = await FalconFacts.check(claim, fetch, controller.signal);
      record.engine = report ? 'structured' : 'nli';
      if (!report) {
        const evidence = E.rankPassages(claim, await FalconSources.retrieve(claim, fetch, controller.signal));
        report = evidence.length ? (await call({claim, evidence})).report : E.decide([]);
      }
      clearTimeout(timer);
      record.status = report.status;
      record.predicted = toLabel(report.status);
      record.evidence = (report.evidence || []).map(e => ({title: e.title, url: e.url, relevance: e.relevance, scores: e.scores}));
    } catch (error) {
      record.predicted = 'ERROR'; record.error = String(error.message || error);
    }
    record.correct = record.predicted === expected;
    results.push(record);
    console.log(`${i + 1}/${cases.length}`, record.correct ? 'OK  ' : 'MISS', expected, '->', record.predicted, '|', claim);
    await new Promise(r => setTimeout(r, 300));
  }
  worker.terminate();

  const labels = ['SUPPORTED', 'REFUTED', 'NOT ENOUGH INFO'];
  const perClass = Object.fromEntries(labels.map(label => {
    const tp = results.filter(r => r.predicted === label && r.expected === label).length;
    const fp = results.filter(r => r.predicted === label && r.expected !== label).length;
    const fn = results.filter(r => r.predicted !== label && r.expected === label).length;
    const precision = tp + fp ? tp / (tp + fp) : 0, recall = tp + fn ? tp / (tp + fn) : 0;
    return [label, {precision, recall, f1: precision + recall ? 2 * precision * recall / (precision + recall) : 0}];
  }));
  const decisive = results.filter(r => r.predicted === 'SUPPORTED' || r.predicted === 'REFUTED');
  const summary = {
    runAt: new Date().toISOString(), model: E.MODEL, revision: E.REVISION, total: results.length,
    accuracy: results.filter(r => r.correct).length / results.length,
    macroF1: labels.reduce((s, l) => s + perClass[l].f1, 0) / labels.length,
    perClass,
    decisiveAnswers: decisive.length,
    decisivePrecision: decisive.filter(r => r.correct).length / Math.max(decisive.length, 1),
    conflicts: results.filter(r => r.predicted === 'CONFLICT').length,
    errors: results.filter(r => r.predicted === 'ERROR').length,
  };
  window.falconEval = {summary, results};
  console.table(summary);
  const url = URL.createObjectURL(new Blob([JSON.stringify(window.falconEval, null, 2)], {type: 'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = 'falcon-eval-results.json'; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
})();
