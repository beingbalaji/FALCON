(function() {
  'use strict';
  const $ = id => document.getElementById(id);
  const E = FalconEvidence;
  let worker, sequence = 0, activeId = 0, controller, lastReport;
  const node = (tag, text, cls) => { const n=document.createElement(tag); n.textContent=text; if(cls)n.className=cls; return n; };
  function busy(value) {
    $('verifyBtn').disabled=value; $('diagnosticBtn').disabled=value;
    $('cancelVerify').hidden=!value;
    $('factClaim').disabled=value; $('evidenceMode').disabled=value;
    $('sourceText').disabled=value; $('sourceURL').disabled=value;
  }
  function progress(message) { $('verifyProgress').textContent=message; }
  function stop() {
    activeId=++sequence; controller?.abort(); worker?.terminate(); worker=null; busy(false);
    progress('Cancelled. No assessment was made.');
  }
  function renderSources(evidence) {
    const target=$('evidenceCards'); target.replaceChildren();
    for(const [i,item] of evidence.entries()) {
      const card=node('article','','evidence-card');
      const link=node('a',`${i+1}. ${item.title}`); link.href=item.url; link.target='_blank'; link.rel='noopener noreferrer';
      card.append(link, node('p',`${item.publisher} · ${item.kind === 'user-passage' ? 'Supplied by you; origin not authenticated' : 'Retrieved '+new Date(item.fetchedAt).toLocaleString()}`, 'micro'));
      if(item.updatedAt)card.append(node('p','Article revision: '+new Date(item.updatedAt).toLocaleString(),'micro'));
      card.append(node('blockquote',item.text));
      if(item.scores) {
        const [label]=Object.entries(item.scores).sort((a,b)=>b[1]-a[1])[0];
        card.append(node('p','Model relationship: '+({entailment:'supports', contradiction:'contradicts', neutral:'unclear'}[label]),'relationship'));
        const details=node('details',''); details.append(node('summary','Model scores (not factual confidence)'));
        details.append(node('p',Object.entries(item.scores).map(([k,v])=>`${k}: ${v.toFixed(3)}`).join(' · '),'micro')); card.append(details);
      }
      target.append(card);
    }
  }
  function finish(report) {
    lastReport={claim:$('factClaim').value.trim(), ...report};
    $('evidenceResult').hidden=false;
    $('evidenceStatus').textContent=report.status;
    $('evidenceStatus').dataset.status=report.status.split(' ')[0].toLowerCase();
    $('evidenceSummary').textContent=`Compared ${report.evidence.length} passages from ${report.sourceCount} page(s), representing ${report.publisherCount} publisher(s). ${report.caution}`;
    $('correctedPassage').hidden=!report.correctionPassage;
    $('correctionText').textContent=report.correctionPassage || '';
    renderSources(report.evidence);
    $('exportEvidence').hidden=false;
    busy(false); progress('Comparison complete. Read the cited passages before relying on the result.');
  }
  function ensureWorker() {
    if(worker)return;
    worker=new Worker('evidence-worker.js?v=3',{type:'module'});
    worker.onerror=()=>{progress('The model could not start. Check your internet connection and browser support; the claim remains unverified.'); busy(false); worker?.terminate();worker=null;};
    worker.onmessage=({data})=>{
      if(data.id!==activeId)return;
      if(data.kind==='progress')progress(data.message);
      if(data.kind==='error'){ progress('Assessment unavailable: '+data.message+' No factual verdict was made.'); busy(false); worker?.terminate();worker=null; }
      if(data.kind==='result')finish(data.report);
      if(data.kind==='diagnostics') {
        const correct=data.results.filter(x=>x.correct).length;
        const target=$('diagnosticResults'); target.replaceChildren();
        target.append(node('p',`${correct}/${data.results.length} diagnostic pairs classified as expected. This small hand-written set is a software/model smoke check, not a fact-checking accuracy benchmark.`));
        for(const item of data.results)target.append(node('p',`${item.correct?'PASS':'FAIL'} · ${item.claim} · expected ${item.expected}, predicted ${item.predicted}`,'micro'));
        lastReport={type:'diagnostics',model:E.MODEL,revision:E.REVISION,runAt:new Date().toISOString(),correct,total:data.results.length,results:data.results};
        $('exportEvidence').hidden=false; busy(false); progress('Diagnostic run complete.');
      }
    };
  }
  $('evidenceMode').addEventListener('change',()=>{$('customEvidence').hidden=$('evidenceMode').value!=='passage';});
  document.querySelectorAll('[data-fact-example]').forEach(button=>button.addEventListener('click',()=>{if(!activeId || !$('verifyBtn').disabled)$('factClaim').value=button.dataset.factExample;}));
  $('cancelVerify').addEventListener('click',stop);
  $('verifyBtn').addEventListener('click',async()=>{
    let claim;
    try {claim=E.validateClaim($('factClaim').value);}catch(error){progress(error.message);return;}
    const id=activeId=++sequence;
    busy(true); $('evidenceResult').hidden=true; $('exportEvidence').hidden=true; lastReport=null;
    $('evidenceCards').replaceChildren();
    controller=new AbortController();
    const timer=setTimeout(()=>controller.abort(),25000);
    try {
      let sources;
      if($('evidenceMode').value==='passage') {
        const text=$('sourceText').value.trim();
        if(text.length<30 || text.length>6000)throw new Error('Provide a source passage between 30 and 6,000 characters.');
        const url=new URL($('sourceURL').value);
        if(url.protocol!=='https:')throw new Error('Use an HTTPS source URL.');
        sources=[{title:'Your evidence passage',url:url.href,text,publisher:url.hostname,kind:'user-passage',fetchedAt:new Date().toISOString()}];
      }else{
        progress('Searching English Wikipedia for relevant evidence…');
        sources=await FalconSources.retrieve(claim,fetch,controller.signal);
      }
      if(id!==activeId)return;
      const evidence=E.rankPassages(claim,sources);
      if(!evidence.length){finish(E.decide([]));return;}
      $('evidenceResult').hidden=false; $('evidenceStatus').textContent='Evidence found — awaiting model';
      $('evidenceSummary').textContent='Retrieved passages are shown below. No model decision has been made yet.';
      renderSources(evidence); ensureWorker(); worker.postMessage({id,claim,evidence});
    }catch(error){if(id===activeId){progress(error.name==='AbortError'?'Source retrieval timed out. Try again or supply a source passage.':error.message);busy(false);}}
    finally{clearTimeout(timer);}
  });
  $('diagnosticBtn').addEventListener('click',async()=>{
    const id=activeId=++sequence; busy(true); $('diagnosticResults').replaceChildren();
    try {
      const r=await fetch('diagnostics.json?v=3'); if(!r.ok)throw new Error('Unable to load diagnostic cases.');
      const cases=await r.json(); ensureWorker(); worker.postMessage({id,cases});
    }catch(error){progress(error.message);busy(false);}
  });
  $('exportEvidence').addEventListener('click',()=>{
    if(!lastReport)return;
    const url=URL.createObjectURL(new Blob([JSON.stringify(lastReport,null,2)],{type:'application/json'}));
    const a=node('a','');a.href=url;a.download='falcon-evidence-report.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
})();
