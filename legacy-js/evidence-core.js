/* Evidence decisions are relationships to passages, never guaranteed world truth. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FalconEvidence = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const MODEL = 'Xenova/nli-deberta-v3-xsmall';
  const REVISION = '2a4f614a701367a02d51389039afc998faeda637';
  const STOP = new Set('a an the is are was were be been being in on at to of for from by with and or but not no never does do did has have had it its that this as currently now today'.split(' '));
  function terms(text) { return [...new Set((text.toLowerCase().match(/[a-z0-9]+/g) || []).filter(t => t.length > 1 && !STOP.has(t)))]; }
  function validateClaim(text) {
    if (typeof text !== 'string' || text.trim().length < 10) throw new Error('Enter one factual claim of at least 10 characters.');
    if (text.trim().length > 350) throw new Error('Use one short claim, up to 350 characters.');
    if (!/[a-zA-Z]/.test(text)) throw new Error('This model supports English text.');
    return text.trim();
  }
  function searchQuery(claim) { return terms(claim).slice(0, 12).join(' '); }
  function rankPassages(claim, sources) {
    const query = terms(claim);
    const output = [];
    for (const source of sources) {
      if (!source.text || !source.url || !/^https:\/\//.test(source.url)) continue;
      // Keep neighbouring sentences together so pronouns retain some context.
      const sentences = source.text.replace(/\s+/g, ' ').match(/[^.!?]+(?:[.!?]+|$)/g) || [];
      for (let i = 0; i < sentences.length; i += 2) {
        const passage = sentences.slice(i, i + 2).join(' ').trim().slice(0, 1300);
        const words = new Set(terms(passage));
        const matched = query.filter(t => words.has(t)).length;
        const coverage = matched / Math.max(query.length, 1);
        if (matched < Math.min(2, query.length) || coverage < 0.3) continue;
        output.push({...source, text: passage, relevance: coverage});
      }
    }
    const seen = new Set();
    return output.sort((a,b) => b.relevance - a.relevance).filter(x => {
      const key = x.text.toLowerCase();
      if (seen.has(key)) return false;
      seen.add(key); return true;
    }).slice(0, 6);
  }
  function softmax(logits) {
    if (logits.length !== 3 || !logits.every(Number.isFinite)) throw new Error('The model returned invalid scores.');
    const max = Math.max(...logits), exps = logits.map(x => Math.exp(x-max));
    const sum = exps.reduce((a,b) => a+b,0);
    return {contradiction: exps[0]/sum, entailment: exps[1]/sum, neutral: exps[2]/sum};
  }
  function decide(evidence) {
    const strong = (x, label) => x.scores && Number.isFinite(x.scores[label]) && x.scores[label] >= 0.9 &&
      x.scores[label] - Math.max(...Object.entries(x.scores).filter(([k]) => k !== label).map(([,v]) => v)) >= 0.35;
    const supports = evidence.filter(x => strong(x, 'entailment'));
    const contradicts = evidence.filter(x => strong(x, 'contradiction'));
    let status = 'Insufficient evidence';
    if (supports.length && contradicts.length) status = 'Conflicting evidence';
    else if (supports.length) status = 'Supported by retrieved evidence';
    else if (contradicts.length) status = 'Contradicted by retrieved evidence';
    const relevant = status === 'Conflicting evidence' ? [...supports, ...contradicts] : supports.length ? supports : contradicts;
    return {status, evidence, decisiveEvidence: relevant, sourceCount: new Set(evidence.map(x => x.url)).size,
      publisherCount: new Set(evidence.map(x => x.publisher)).size,
      correctionPassage: status === 'Contradicted by retrieved evidence' ? contradicts[0].text : null,
      assessedAt: new Date().toISOString(), model: MODEL, revision: REVISION,
      caution: 'This is a model comparison with retrieved passages. Sources may be incomplete, outdated, or wrong. Model scores are not probabilities that a claim is true.'};
  }
  return {MODEL, REVISION, terms, validateClaim, searchQuery, rankPassages, softmax, decide};
});
