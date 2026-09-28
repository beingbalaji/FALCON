'use strict';
const {test} = require('node:test');
const assert = require('node:assert/strict');
const {analyzeText, topicCounts} = require('./analysis');
const {createServer} = require('./server');

test('writing cues do not turn into factual predictions', () => {
  const urgent = analyzeText('BREAKING!!! You will not believe this shocking secret truth. Experts say a miracle cure works for everyone. Share this now before it is deleted!');
  const trueStyle = analyzeText('Two plus two equals four according to basic arithmetic.');
  const falseStyle = analyzeText('Two plus two equals five according to basic arithmetic.');
  const userClaim = analyzeText('Narendra Modi is the prime minister of India.');
  const reversedClaim = analyzeText('Narendra Modi is not the prime minister of India.');
  assert.ok(urgent.cueCount > trueStyle.cueCount);
  assert.ok(urgent.signals.some(signal => signal.id === 'urgency'));
  for (const report of [urgent, trueStyle, falseStyle, userClaim, reversedClaim]) {
    assert.equal(report.verificationStatus, 'Unverified');
    assert.equal(report.factualVerdict, null);
    assert.equal('reviewScore' in report, false);
    assert.equal('priority' in report, false);
  }
  assert.equal(trueStyle.cueCount, falseStyle.cueCount);
  assert.equal(userClaim.cueCount, reversedClaim.cueCount);
  assert.equal(urgent.topic, 'Health');
  assert.match(urgent.disclaimer, /No sources were checked/);
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
  const markup = await html.text();
  assert.match(markup, /FALCON · Claim Review Lab/);
  assert.match(markup, /app\.js\?v=4/);
  const css = await fetch(base + '/style.css');
  assert.equal(css.status, 200);
  const response = await fetch(base + '/api/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: 'This city news article discusses a scheduled vote by the council on Friday.'})});
  assert.equal(response.status, 200);
  const result = await response.json();
  assert.equal(result.success, true);
  assert.equal(result.analysis.topic, 'Politics');
  assert.equal(result.analysis.verificationStatus, 'Unverified');
  assert.equal(result.analysis.factualVerdict, null);
  const invalid = await fetch(base + '/api/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: 'tiny'})});
  assert.equal(invalid.status, 422);
  assert.equal((await invalid.json()).success, false);
  const large = await fetch(base + '/api/analyze', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({text: 'a'.repeat(40000)})});
  assert.equal(large.status, 413);
});

const E = require('./evidence-core');
const {retrieve} = require('./evidence-sources');
const source = {title:'Example source',url:'https://example.org/evidence',publisher:'Example',text:'The capital city of Australia is Canberra.'};
const support = {...source,scores:{entailment:.97,contradiction:.02,neutral:.01}};
const refute = {...source,url:'https://example.org/other',scores:{entailment:.02,contradiction:.97,neutral:.01}};
test('evidence decisions abstain on missing or weak evidence and preserve conflicts',()=>{
  assert.equal(E.decide([]).status,'Insufficient evidence');
  assert.equal(E.decide([{...source,scores:{entailment:.60,contradiction:.35,neutral:.05}}]).status,'Insufficient evidence');
  assert.equal(E.decide([support]).status,'Supported by retrieved evidence');
  assert.equal(E.decide([refute]).correctionPassage,source.text);
  const conflict=E.decide([support,refute]);
  assert.equal(conflict.status,'Conflicting evidence');
  assert.equal(conflict.correctionPassage,null);
  assert.equal(conflict.publisherCount,1); // Two Wikipedia pages are not two independent publishers.
  assert.equal(E.decide([{...source,scores:{entailment:NaN,contradiction:0,neutral:0}}]).status,'Insufficient evidence');
});
test('retrieval relevance is independent of claim negation and excludes unrelated passages',()=>{
  assert.equal(E.searchQuery('Canberra is the capital of Australia.'),E.searchQuery('Canberra is not the capital of Australia.'));
  assert.equal(E.rankPassages('Sydney is the capital of Australia.',[source]).length,1);
  assert.equal(E.rankPassages('A doctor works in a hospital.',[source]).length,0);
  assert.throws(()=>E.validateClaim('x'.repeat(351)),/350/);
  assert.throws(()=>E.softmax([NaN,1,2]),/invalid/);
  const scores=E.softmax([0,10,0]);assert.ok(scores.entailment>.99);
});
test('live source adapter preserves revision citation and fails on network errors',async()=>{
  const calls=[];
  const fetchMock=async url=>{
    calls.push(url);
    return {ok:true,json:async()=>calls.length===1 ? {query:{search:[{pageid:10}]}} : {query:{pages:[{title:'Canberra',extract:source.text,fullurl:'https://en.wikipedia.org/wiki/Canberra',revisions:[{revid:123,timestamp:'2026-01-01T00:00:00Z'}]}]}}};
  };
  const results=await retrieve('Sydney is the capital of Australia.',fetchMock);
  assert.equal(results[0].url,'https://en.wikipedia.org/w/index.php?oldid=123');
  assert.equal(results[0].publisher,'Wikipedia');
  assert.ok(new URL(calls[0]).searchParams.get('srsearch').includes('sydney'));
  await assert.rejects(()=>retrieve('Sydney is the capital of Australia.',async()=>({ok:false,status:503})),/503/);
});

const F=require('./structured-facts');
const statement=(id,extra={})=>({rank:'preferred',mainsnak:{snaktype:'value',datavalue:{value:{id}}},references:[{snaks:{}}],...extra});
const timeQualifier=(time,precision=11)=>({datavalue:{value:{time,precision}}});
test('structured facts reject historical, future, disputed, and uncertain records',()=>{
  const now='2026-09-28T00:00:00Z';
  assert.equal(F.parse('Narendra Modi is not the prime minister of India.').negated,true);
  assert.equal(F.parse('Narendra Modi was the prime minister of India.'),null);
  assert.equal(F.parse('Canberra is the capital of Australia and Paris is in France.'),null);
  assert.equal(F.currentStatements([statement('Q1',{qualifiers:{P582:[timeQualifier('+2025-01-01T00:00:00Z')]}})],now).length,0);
  assert.equal(F.currentStatements([statement('Q1',{qualifiers:{P580:[timeQualifier('+2027-01-01T00:00:00Z')]}})],now).length,0);
  assert.equal(F.currentStatements([statement('Q1',{qualifiers:{P580:[timeQualifier('+1913-00-00T00:00:00Z',9)]}})],now).length,1);
  assert.equal(F.currentStatements([statement('Q1',{qualifiers:{P580:[timeQualifier('+2026-00-00T00:00:00Z',9)]}})],now).length,0);
  assert.equal(F.currentStatements([statement('Q1',{qualifiers:{P1310:[{}]}})],now).length,0);
  assert.equal(F.currentStatements([statement('Q1',{rank:'deprecated'})],now).length,0);
});
test('structured checks compare resolved IDs, handle negation, and abstain on ambiguity',async()=>{
  const entities={Q1:{id:'Q1',labels:{en:{value:'Australia'}},lastrevid:123,claims:{P36:[statement('Q2')]}},Q2:{id:'Q2',labels:{en:{value:'Canberra'}}},Q3:{id:'Q3',labels:{en:{value:'Sydney'}}}};
  const mock=async url=>{const p=new URL(url).searchParams;return {ok:true,json:async()=>p.get('action')==='wbsearchentities'?{search:Object.values(entities).filter(e=>e.labels.en.value===p.get('search')).map(e=>({id:e.id}))}:{entities:Object.fromEntries(p.get('ids').split('|').map(id=>[id,entities[id]]))}};};
  assert.equal((await F.check('Canberra is the capital of Australia.',mock)).status,'Supported by structured source');
  assert.equal((await F.check('Sydney is the capital of Australia.',mock)).status,'Contradicted by structured source');
  assert.equal((await F.check('Canberra is not the capital of Australia.',mock)).status,'Contradicted by structured source');
  assert.equal((await F.check('Sydney is not the capital of Australia.',mock)).status,'Supported by structured source');
  assert.equal((await F.check('Unknown is the capital of Australia.',mock)).status,'Insufficient evidence');
  entities.Q1.claims.P36.push(statement('Q4'));
  entities.Q4={id:'Q4',labels:{en:{value:'Another capital'}}};
  assert.equal((await F.check('Sydney is the capital of Australia.',mock)).status,'Insufficient evidence');
  entities.Q1.claims.P36=[statement('Q2',{references:[]})];
  assert.equal((await F.check('Sydney is the capital of Australia.',mock)).status,'Insufficient evidence');
  await assert.rejects(()=>F.check('Sydney is the capital of Australia.',async()=>({ok:false,status:503})),/503/);
});
