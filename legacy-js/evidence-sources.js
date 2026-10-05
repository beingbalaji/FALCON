(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./evidence-core'));
  else root.FalconSources = factory(root.FalconEvidence);
})(typeof globalThis !== 'undefined' ? globalThis : this, function(E) {
  'use strict';
  async function retrieve(claim, fetchImpl = fetch, signal) {
    const request = async params => {
      const url = new URL('https://en.wikipedia.org/w/api.php');
      url.search = new URLSearchParams({format:'json', formatversion:'2', origin:'*', ...params});
      const response = await fetchImpl(url.toString(), {signal, credentials:'omit'});
      if (!response.ok) throw new Error(`Wikipedia returned HTTP ${response.status}. Try again or use your own evidence passage.`);
      const data = await response.json();
      if (data.error) throw new Error('Wikipedia could not process the evidence search.');
      return data;
    };
    const query = E.searchQuery(claim);
    if (!query) return [];
    const search = await request({action:'query', list:'search', srsearch:query, srlimit:'4', srprop:''});
    const hits = search.query?.search || [];
    if (!hits.length) return [];
    const pageids = hits.map(x=>x.pageid).join('|');
    const data = await request({action:'query', prop:'extracts|info|revisions', pageids,
      exintro:'1', explaintext:'1', inprop:'url', rvprop:'ids|timestamp'});
    const fetchedAt = new Date().toISOString();
    return (data.query?.pages || []).filter(p=>p.extract && p.fullurl).map(p=>({
      title:p.title, text:p.extract.slice(0,6000), publisher:'Wikipedia',
      url:p.revisions?.[0]?.revid ? `https://en.wikipedia.org/w/index.php?oldid=${p.revisions[0].revid}` : p.fullurl,
      liveUrl:p.fullurl, revision:p.revisions?.[0]?.revid || null,
      updatedAt:p.revisions?.[0]?.timestamp || null, fetchedAt, kind:'live-encyclopedia'
    }));
  }
  return {retrieve};
});
