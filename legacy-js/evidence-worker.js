import './evidence-core.js?v=3';
const E = self.FalconEvidence;
let tokenizer, model;
const send = (id, kind, payload) => self.postMessage({id, kind, ...payload});
async function loadModel(id) {
  if (model) return;
  send(id, 'progress', {message: 'Downloading the trained model (about 90 MB on first use). It is cached by this browser.'});
  const {AutoTokenizer, AutoModelForSequenceClassification, env} = await import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1/dist/transformers.min.js');
  env.allowLocalModels = false;
  env.backends.onnx.wasm.numThreads = 1;
  const options = {revision: E.REVISION, progress_callback: p => {
    if (p.status === 'progress' && p.file && p.file.endsWith('.onnx')) send(id,'progress',{message:`Downloading model: ${Math.round(p.progress || 0)}%`});
  }};
  tokenizer = await AutoTokenizer.from_pretrained(E.MODEL, options);
  model = await AutoModelForSequenceClassification.from_pretrained(E.MODEL, {...options, dtype:'q8', device:'wasm'});
  // Fail closed if the pinned model's label order ever disagrees with our mapping.
  const labels = model.config.id2label;
  if (!labels || String(labels[0]).toLowerCase() !== 'contradiction' || String(labels[1]).toLowerCase() !== 'entailment' || String(labels[2]).toLowerCase() !== 'neutral') {
    model = null; throw new Error('Unexpected model label mapping; inference has been stopped.');
  }
}
async function infer(premise, claim) {
  const inputs = tokenizer(premise, {text_pair: claim, padding: true, truncation: true, max_length:384});
  const output = await model(inputs);
  return E.softmax(Array.from(output.logits.data));
}
self.onmessage = async event => {
  const {id, claim, evidence, cases} = event.data;
  try {
    await loadModel(id);
    if (cases) {
      const results = [];
      for (const [i, item] of cases.entries()) {
        send(id,'progress',{message:`Diagnostic ${i+1} of ${cases.length}`});
        const scores = await infer(item.evidence, item.claim);
        const predicted = Object.entries(scores).sort((a,b)=>b[1]-a[1])[0][0];
        results.push({...item, scores, predicted, correct:predicted === item.expected});
      }
      send(id,'diagnostics',{results}); return;
    }
    const assessed = [];
    for (const [i, item] of evidence.entries()) {
      send(id,'progress',{message:`Comparing passage ${i+1} of ${evidence.length}…`});
      assessed.push({...item, scores:await infer(item.text, claim)});
    }
    send(id,'result',{report:E.decide(assessed)});
  } catch (error) { send(id,'error',{message:error.message || 'The evidence model could not run.'}); }
};
