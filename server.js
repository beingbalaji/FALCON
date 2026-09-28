'use strict';
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const {analyzeText} = require('./analysis');

const FILES = new Map([
  ['/', ['index.html', 'text/html; charset=utf-8']],
  ['/index.html', ['index.html', 'text/html; charset=utf-8']],
  ['/app.js', ['app.js', 'text/javascript; charset=utf-8']],
  ['/analysis.js', ['analysis.js', 'text/javascript; charset=utf-8']],
  ['/evidence-core.js', ['evidence-core.js', 'text/javascript; charset=utf-8']],
  ['/evidence-sources.js', ['evidence-sources.js', 'text/javascript; charset=utf-8']],
  ['/evidence-worker.js', ['evidence-worker.js', 'text/javascript; charset=utf-8']],
  ['/evidence-ui.js', ['evidence-ui.js', 'text/javascript; charset=utf-8']],
  ['/diagnostics.json', ['diagnostics.json', 'application/json; charset=utf-8']],
  ['/style.css', ['style.css', 'text/css; charset=utf-8']]
]);

function json(res, status, value) {
  res.writeHead(status, {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'});
  res.end(JSON.stringify(value));
}

function createServer() {
  return http.createServer((req, res) => {
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Referrer-Policy', 'no-referrer');
    res.setHeader('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self' https://cdn.jsdelivr.net 'wasm-unsafe-eval'; worker-src 'self' blob:; connect-src 'self' https://en.wikipedia.org https://huggingface.co https://*.huggingface.co https://*.hf.co https://cdn.jsdelivr.net; img-src 'self' data:; base-uri 'none'; form-action 'none'");
    const url = new URL(req.url, 'http://localhost');
    if (req.method === 'GET' && url.pathname === '/health') return json(res, 200, {status: 'ok', mode: 'local'});
    if (req.method === 'POST' && url.pathname === '/api/analyze') {
      if (!/^application\/json(?:\s*;|\s*$)/i.test(req.headers['content-type'] || '')) return json(res, 415, {error: 'Send application/json.'});
      let body = '';
      let tooLarge = false;
      req.setEncoding('utf8');
      req.on('data', chunk => {
        if (tooLarge) return;
        body += chunk;
        if (body.length > 30000) { tooLarge = true; json(res, 413, {success: false, error: 'Request is too large.'}); }
      });
      req.on('end', () => {
        if (tooLarge) return;
        try {
          const value = JSON.parse(body);
          const analysis = analyzeText(value.text);
          json(res, 200, {success: true, analysis});
        } catch (error) {
          json(res, error instanceof SyntaxError ? 400 : 422, {success: false, error: error.message});
        }
      });
      return;
    }
    const file = FILES.get(url.pathname);
    if (req.method !== 'GET' || !file) return json(res, 404, {error: 'Not found.'});
    fs.readFile(path.join(__dirname, file[0]), (error, contents) => {
      if (error) return json(res, 500, {error: 'Unable to read app file.'});
      res.writeHead(200, {'Content-Type': file[1], 'Cache-Control': 'no-store'});
      res.end(contents);
    });
  });
}

if (require.main === module) {
  const port = Number(process.env.PORT || 3000);
  createServer().listen(port, '127.0.0.1', () => console.log(`FALCON: http://127.0.0.1:${port}`));
}
module.exports = {createServer};
