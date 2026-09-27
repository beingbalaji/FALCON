/* FALCON review signals. Shared by the browser and the local Node server.
 * These transparent rules measure language patterns, never factual truth. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.FalconAnalysis = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const MAX_LENGTH = 10000;
  const TOPICS = [
    ['Health', /\b(?:health|doctor|hospital|vaccine|virus|cure|medicine|disease|patient|clinical)\b/gi],
    ['Politics', /\b(?:election|vote|minister|government|parliament|policy|president|politic)\b/gi],
    ['Finance', /\b(?:bank|stock|market|investment|crypto|rupee|dollar|inflation|tax|profit)\b/gi],
    ['Technology', /\b(?:ai|technology|software|data|app|internet|cyber|robot|algorithm)\b/gi],
    ['Climate', /\b(?:climate|weather|flood|heatwave|emission|environment|rainfall)\b/gi]
  ];
  const RULES = [
    { id: 'sensational', label: 'Sensational phrasing', weight: 16,
      detail: 'Attention-grabbing language can make a claim feel urgent without adding evidence.',
      pattern: /\b(?:shocking|unbelievable|miracle|secret truth|you won.t believe|mind.blown|exposed)\b/gi },
    { id: 'urgency', label: 'Urgent sharing request', weight: 18,
      detail: 'Requests to spread a claim quickly are a reason to pause and check the source.',
      pattern: /\b(?:share (?:this|now|immediately)|forward (?:this|now)|before (?:it.s|it is) deleted|spread the word)\b/gi },
    { id: 'absolute', label: 'Absolute or sweeping claim', weight: 13,
      detail: 'Broad claims need specific, independent supporting evidence.',
      pattern: /\b(?:everyone knows|no one wants you to know|100% guaranteed|always works|never fails|all (?:doctors|scientists|experts) agree)\b/gi },
    { id: 'authority', label: 'Unspecified authority', weight: 12,
      detail: 'A named study or expert can be checked; vague attribution is harder to verify.',
      pattern: /\b(?:experts say|scientists say|a study proves|sources confirm|research shows)\b/gi }
  ];
  const STOP = new Set('the and that with from this have they were been into about their there would could should these those after before while where what when whose your more than then just over under says said says news article post claim claims for are you was has had its not but all can our out now new via who how why one two three also only many some will may might'.split(' '));

  function analyzeText(input) {
    if (typeof input !== 'string') throw new TypeError('Text must be a string.');
    const text = input.trim().replace(/\r\n/g, '\n');
    if (text.length < 20) throw new RangeError('Enter at least 20 characters to review.');
    if (text.length > MAX_LENGTH) throw new RangeError('Keep the text under 10,000 characters.');

    const words = text.match(/[\p{L}\p{N}]+(?:['’][\p{L}]+)?/gu) || [];
    const sentences = text.split(/[.!?]+/).filter(s => s.trim()).length || 1;
    const signals = [];
    for (const rule of RULES) {
      const matches = Array.from(text.matchAll(rule.pattern)).slice(0, 3).map(m => m[0]);
      if (matches.length) signals.push({id: rule.id, label: rule.label, detail: rule.detail, weight: rule.weight, examples: matches});
    }
    const exclamations = (text.match(/!/g) || []).length;
    if (exclamations >= 3 || /!{2,}/.test(text)) {
      signals.push({id: 'punctuation', label: 'Emphatic punctuation', weight: 9,
        detail: 'Repeated exclamation marks can add emotional pressure, not evidence.', examples: [`${exclamations} exclamation marks`]});
    }
    const letterWords = words.filter(w => /\p{L}/u.test(w));
    const caps = letterWords.filter(w => w.length >= 4 && w === w.toUpperCase()).length;
    if (letterWords.length >= 5 && caps / letterWords.length >= 0.18) {
      signals.push({id: 'capitalization', label: 'Frequent capital letters', weight: 8,
        detail: 'Many all-capital words suggest emphasis; they do not establish truth.', examples: [`${caps} all-capital words`]});
    }
    const score = Math.min(90, 10 + signals.reduce((sum, s) => sum + s.weight, 0));
    const priority = score >= 48 ? 'High' : score >= 25 ? 'Medium' : 'Low';
    const topicCounts = TOPICS.map(([name, pattern]) => ({name, count: (text.match(pattern) || []).length}));
    topicCounts.sort((a, b) => b.count - a.count);
    const topic = topicCounts[0].count ? topicCounts[0].name : 'General';
    const frequency = new Map();
    for (const word of words) {
      const key = word.toLocaleLowerCase('en');
      if (key.length < 4 || STOP.has(key) || /^\d+$/.test(key)) continue;
      frequency.set(key, (frequency.get(key) || 0) + 1);
    }
    const keywords = [...frequency].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 6).map(([word]) => word);
    return {
      priority, reviewScore: score, topic, keywords, signals,
      metrics: {words: words.length, sentences, exclamations, allCapsWords: caps},
      method: 'Transparent language signals v1',
      disclaimer: 'This score is a review priority based on writing patterns. It is not a truth verdict, model confidence, or fact-check result.'
    };
  }

  function topicCounts(entries) {
    const counts = new Map();
    for (const entry of entries) {
      const topic = entry && typeof entry.topic === 'string' ? entry.topic : 'General';
      counts.set(topic, (counts.get(topic) || 0) + 1);
    }
    return [...counts].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  }
  return {analyzeText, topicCounts, MAX_LENGTH};
});
