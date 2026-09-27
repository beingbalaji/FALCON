(function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const KEY = 'falcon-review-summaries-v1';
  const EXAMPLES = {
    urgent: 'BREAKING!!! You won’t believe this shocking secret truth. Experts say a miracle cure works for everyone. Share this now before it is deleted!',
    neutral: 'The city council published its meeting agenda on Tuesday. The document lists a discussion of bus routes and a vote scheduled for Friday.'
  };
  let history = loadHistory();

  function loadHistory() {
    try {
      const saved = JSON.parse(localStorage.getItem(KEY) || '[]');
      return Array.isArray(saved) ? saved.filter(x => x && typeof x.topic === 'string' && typeof x.reviewScore === 'number').slice(0, 40) : [];
    } catch { return []; }
  }
  function saveHistory() {
    try { localStorage.setItem(KEY, JSON.stringify(history)); } catch { /* Private browsing may block storage. */ }
  }
  function textElement(tag, content, className) {
    const element = document.createElement(tag);
    element.textContent = content;
    if (className) element.className = className;
    return element;
  }
  function setError(message) {
    $('error').textContent = message;
    $('error').hidden = !message;
  }
  function renderReport(report) {
    $('result').hidden = false;
    $('priority').textContent = report.priority;
    $('priority').style.color = report.priority === 'High' ? 'var(--red)' : report.priority === 'Medium' ? 'var(--amber)' : 'var(--mint)';
    $('priorityNote').textContent = report.priority === 'High' ? 'Several writing cues warrant careful source review.' : report.priority === 'Medium' ? 'Some writing cues are worth checking.' : 'Few listed writing cues were found; verification is still needed.';
    $('score').textContent = report.reviewScore;
    $('meterFill').style.width = `${report.reviewScore}%`;
    $('meterFill').style.background = report.priority === 'High' ? 'var(--red)' : report.priority === 'Medium' ? 'var(--amber)' : 'var(--mint)';
    $('disclaimer').textContent = report.disclaimer;
    $('topic').textContent = report.topic;
    $('words').textContent = report.metrics.words;
    $('sentences').textContent = report.metrics.sentences;
    const list = $('signals'); list.replaceChildren();
    if (!report.signals.length) list.append(textElement('li', 'No listed rhetorical cues matched. The claim still needs independent verification.'));
    for (const signal of report.signals) {
      const li = document.createElement('li');
      li.append(textElement('strong', signal.label), textElement('span', signal.detail));
      if (signal.examples.length) li.append(textElement('p', `Matched: ${signal.examples.join(', ')}`, 'micro'));
      list.append(li);
    }
    const keywords = $('keywords'); keywords.replaceChildren();
    for (const word of report.keywords) keywords.append(textElement('span', word));
    if (!report.keywords.length) keywords.append(textElement('span', 'No repeated themes'));
    document.querySelectorAll('.checklist input').forEach(box => { box.checked = false; });
    $('result').scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  function renderDashboard() {
    $('total').textContent = history.length;
    $('highCount').textContent = history.filter(x => x.priority === 'High').length;
    const chart = $('topics'); chart.replaceChildren();
    const counts = FalconAnalysis.topicCounts(history);
    if (!counts.length) chart.append(textElement('p', 'Analyze a sample to see topics.', 'muted'));
    for (const [name, count] of counts) {
      const row = document.createElement('div'); row.className = 'topic-row';
      const bar = textElement('div', '', 'bar');
      const fill = document.createElement('i'); fill.style.width = `${Math.round(count / history.length * 100)}%`;
      bar.append(fill); row.append(textElement('span', name), bar, textElement('strong', String(count))); chart.append(row);
    }
    const recent = $('recent'); recent.replaceChildren();
    if (!history.length) recent.append(textElement('p', 'No reviews yet.', 'muted'));
    for (const entry of history.slice(0, 8)) {
      const row = document.createElement('div'); row.className = 'recent-item';
      const info = textElement('span', `${entry.topic} · ${entry.words} words`);
      const time = textElement('time', new Date(entry.at).toLocaleString()); time.dateTime = entry.at;
      const badge = textElement('span', `${entry.priority} · ${entry.reviewScore}`, `badge ${entry.priority.toLowerCase()}`);
      row.append(info, time, badge); recent.append(row);
    }
  }
  $('claim').addEventListener('input', () => { $('length').textContent = `${$('claim').value.length.toLocaleString()} / 10,000`; setError(''); });
  document.querySelectorAll('[data-example]').forEach(button => button.addEventListener('click', () => {
    $('claim').value = EXAMPLES[button.dataset.example];
    $('claim').dispatchEvent(new Event('input'));
    $('claim').focus();
  }));
  $('analyzeBtn').addEventListener('click', () => {
    try {
      const report = FalconAnalysis.analyzeText($('claim').value);
      setError(''); renderReport(report);
      history.unshift({at: new Date().toISOString(), topic: report.topic, priority: report.priority, reviewScore: report.reviewScore, words: report.metrics.words});
      history = history.slice(0, 40); saveHistory(); renderDashboard();
    } catch (error) { setError(error.message); }
  });
  $('exportBtn').addEventListener('click', () => {
    const blob = new Blob([JSON.stringify({project: 'FALCON', method: 'language signals v1', note: 'Review priorities are not truth verdicts.', summaries: history}, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a'); link.href = url; link.download = 'falcon-review-summaries.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
  $('clearBtn').addEventListener('click', () => {
    if (!history.length || !confirm('Delete all saved review summaries from this browser?')) return;
    history = []; saveHistory(); renderDashboard();
  });
  renderDashboard();
})();
