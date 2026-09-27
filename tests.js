'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {analyzeText, topicCounts} = require('./analysis');
const {createServer} = require('./server');

test('sensational example has explainable higher review priority than neutral prose', () => {
  const urgent = analyzeText('BREAKING!!! You will not believe this shocking secret truth. Experts say a miracle cure works for everyone. Share this now before it is deleted!');
  const neutral = analyzeText('The city council published its meeting agenda on Tuesday. The document lists a discussion of bus routes and a vote scheduled for Friday.');
  assert.equal(urgent.priority, 'High');
  assert.ok(urgent.reviewScore > neutral.reviewScore);
  assert.ok(urgent.signals.some(signal => signal.id === 'urgency'));
  assert.equal(neutral.priority, 'Low');
  assert.equal(urgent.topic, 'Health');
  assert.match(urgent.disclaimer, /not a truth verdict/);
});

test('input validation and topic counts', () => {
  assert.throws(() => analyzeText('short'), /at least 20/);
  assert.throws(() => analyzeText('a'.repeat(10001)), /under 10,000/);
  assert.deepEqual(topicCounts([{topic: 'Health'}, {topic: 'Health'}, {topic: 'Finance'}]), [['Health', 2], ['Finance', 1]]);
});

test('local server serves the app and analysis API without secrets or external dependencies', async t => {
  const server = createServer();
  await new Promise((resolve, reject) => server.once('error', reject).listen(0, '127.0.0.1', resolve));
  t.after(() => server.close());
  const base = `http://127.0.0.1:${server.address().port}`;
  const html = await fetch(base);
  assert.equal(html.status, 200);
  assert.match(await html.text(), /FALCON · Claim Review Lab/);
  const css = await fetch(base + '/style.css');
  assert.equal(css.status, 200);
  const response = await fetch(base + '/api/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: 'This city news article discusses a scheduled vote by the council on Friday.'})});
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.success, true);
  assert.equal(result.analysis.topic, 'Politics');
  const invalid = await fetch(base + '/api/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: 'tiny'})});
  assert.equal(invalid.status, 422);
  assert.equal((await invalid.json()).success, false);
  const large = await fetch(base + '/api/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: 'a'.repeat(40000)})});
  assert.equal(large.status, 413);
});
