/*
 * Large-scale evaluation of the live FALCON pipeline on public fact-checking datasets.
 *
 * Usage: open https://beingbalaji.github.io/FALCON/ in a desktop browser, open the developer
 * console, paste this file and press Enter. Progress is saved in localStorage, so the run can
 * be resumed by pasting the file again. When it finishes, results download as JSON.
 *
 * Test set (seeded, reproducible):
 *   FEVER (copenlu/fever_gold_evidence, validation): 500 SUPPORTS + 500 REFUTES + 500 NOT ENOUGH INFO
 *   Climate-FEVER (tdiggelm/climate_fever, test): all claims except DISPUTED
 *   AVeriTeC (pminervini/averitec, dev): Supported, Refuted, Not Enough Evidence (Conflicting excluded)
 */
(async () => {
  const E = FalconEvidence;
  const KEY = 'falconLargeEval';
  const rowsApi = (ds, split, offset) =>
    `https://datasets-server.huggingface.co/rows?dataset=${encodeURIComponent(ds)}&config=default&split=${split}&offset=${offset}&length=100`;
  // Hidden tabs throttle setTimeout heavily; yield through MessageChannel instead.
  const sleep = ms => new Promise(res => { const end = Date.now() + ms; const ch = new MessageChannel();
    ch.port1.onmessage = () => Date.now() >= end ? res() : ch.port2.postMessage(0); ch.port2.postMessage(0); });
  const getJson = async url => { for (let t = 0; ; t++) { try { const r = await fetch(url); if (r.ok) return r.json(); throw new Error(r.status); }
    catch (e) { if (t > 5) throw e; await sleep(3000 * (t + 1)); } } };
  const pull = async (ds, split, offsets, map) => { const out = [];
    for (const o of offsets) { const j = await getJson(rowsApi(ds, split, o)); out.push(...j.rows.map(x => map(x.row))); await sleep(500); }
    return out; };
  const range = (start, end, step) => { const a = []; for (let i = start; i < end; i += step) a.push(i); return a; };

  let state = JSON.parse(localStorage.getItem(KEY) || 'null');
  if (!state) {
    console.log('Loading datasets…');
    const climate = await pull('tdiggelm/climate_fever', 'test', range(0, 1535, 100),
      r => ({claim: r.claim, label: ['SUPPORTED', 'REFUTED', 'NOT ENOUGH INFO', 'DISPUTED'][r.claim_label]}));
    const averitec = await pull('pminervini/averitec', 'dev', range(0, 500, 100),
      r => ({claim: r.claim, label: {Supported: 'SUPPORTED', Refuted: 'REFUTED', 'Not Enough Evidence': 'NOT ENOUGH INFO'}[r.label]}));
    const fever = await pull('copenlu/fever_gold_evidence', 'validation', range(0, 15900, 400),
      r => ({claim: r.claim, label: {SUPPORTS: 'SUPPORTED', REFUTES: 'REFUTED', 'NOT ENOUGH INFO': 'NOT ENOUGH INFO'}[r.label]}));
    let seed = 20261011; const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
    const shuffle = a => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(rnd() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
    const seen = new Set(); const uniq = a => a.filter(x => { const k = x.claim.trim().toLowerCase(); if (seen.has(k)) return false; seen.add(k); return true; });
    const F = uniq(shuffle(fever)); const feverSet = [];
    for (const l of ['SUPPORTED', 'REFUTED', 'NOT ENOUGH INFO']) feverSet.push(...F.filter(x => x.label === l).slice(0, 500));
    const all = shuffle([
      ...feverSet.map(x => ({...x, dataset: 'FEVER'})),
      ...uniq(climate.filter(x => x.label !== 'DISPUTED')).map(x => ({...x, dataset: 'Climate-FEVER'})),
      ...uniq(averitec.filter(x => x.label)).map(x => ({...x, dataset: 'AVeriTeC'})),
    ]);
    state = {cases: all.map((x, i) => ({i, ...x})), results: {}};
    localStorage.setItem(KEY, JSON.stringify(state));
  }

  const queue = state.cases.filter(c => !state.results[c.i]);
  console.log(`${state.cases.length} claims, ${queue.length} remaining`);
  const toLabel = s => s.startsWith('Supported') ? 'SUPPORTED' : s.startsWith('Contradicted') ? 'REFUTED'
    : s.startsWith('Conflicting') ? 'CONFLICT' : 'NOT ENOUGH INFO';
  const fetchRetry = async (url, opts) => { for (let t = 0; ; t++) { const r = await fetch(url, opts);
    if ((r.status !== 429 && r.status < 500) || t >= 4) return r; await sleep(3000 * (t + 1)); } };
  let done = 0;
  const lane = async () => {
    const worker = new Worker('evidence-worker.js?v=4', {type: 'module'}); let seq = 0; const pending = {};
    worker.onmessage = ({data}) => { const p = pending[data.id]; if (!p || data.kind === 'progress') return;
      delete pending[data.id]; data.kind === 'error' ? p.reject(new Error(data.message)) : p.resolve(data); };
    const call = msg => new Promise((resolve, reject) => { const id = ++seq; pending[id] = {resolve, reject}; worker.postMessage({id, ...msg}); });
    while (queue.length) {
      const c = queue.shift(); const rec = {predicted: 'ERROR'};
      try {
        E.validateClaim(c.claim);
        let report = await FalconFacts.check(c.claim, fetchRetry);
        if (!report) {
          const evidence = E.rankPassages(c.claim, await FalconSources.retrieve(c.claim, fetchRetry));
          report = evidence.length ? (await call({claim: c.claim, evidence})).report : E.decide([]);
        }
        rec.predicted = toLabel(report.status);
        rec.evidence = (report.evidence || []).map(e => [e.title, e.relevance, e.scores]);
      } catch (error) { rec.error = String(error.message || error); }
      state.results[c.i] = rec;
      if (++done % 25 === 0) { localStorage.setItem(KEY, JSON.stringify(state)); console.log(`${Object.keys(state.results).length}/${state.cases.length}`); }
      await sleep(0);
    }
    worker.terminate();
  };
  await Promise.all([lane(), lane(), lane(), lane()]);
  localStorage.setItem(KEY, JSON.stringify(state));

  const rows = state.cases.map(c => ({...c, ...state.results[c.i]}));
  const scored = rows.filter(r => r.predicted !== 'ERROR');
  const acc = rs => rs.filter(r => r.predicted === r.label).length / rs.length;
  const summary = {claims: scored.length, accuracy: acc(scored)};
  for (const d of ['FEVER', 'Climate-FEVER', 'AVeriTeC']) summary[d] = acc(scored.filter(r => r.dataset === d));
  console.table(summary);
  const url = URL.createObjectURL(new Blob([JSON.stringify({summary, rows}, null, 1)], {type: 'application/json'}));
  const a = document.createElement('a'); a.href = url; a.download = 'falcon-large-eval.json'; a.click();
})();
