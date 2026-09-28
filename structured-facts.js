/* Narrow, explicit relation checks. No entity values are hard-coded. */
(function(root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory();
  else root.FalconFacts = factory();
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
  'use strict';
  const normalize = s => s.toLowerCase().replace(/[.]+$/, '').replace(/\s+/g, ' ').trim();
  function parse(claim) {
    const match = claim.trim().match(/^(.+?) is (not )?(?:the )?(capital(?: city)?|prime minister|head of government) of (.+?)[.!]?$/i);
    if (!match || /\b(and|or|because|since|before|after|in \d{4})\b/i.test(claim)) return null;
    return {subject:match[1].trim(), negated:!!match[2], relation:match[3].toLowerCase(), place:match[4].trim(), property:/^capital/i.test(match[3])?'P36':'P6'};
  }
  // Reject historical, future, deprecated, uncertain, or context-qualified statements.
  function currentStatements(statements, now) {
    const time = new Date(now).getTime();
    const valid = (statements || []).filter(s => {
      if (s.rank === 'deprecated' || s.mainsnak?.snaktype !== 'value' || !s.mainsnak.datavalue?.value?.id) return false;
      const q=s.qualifiers || {};
      if (Object.keys(q).some(k=>!['P580','P582','P7452'].includes(k))) return false;
      for (const [property, direction] of [['P580',1],['P582',-1]]) {
        for (const snak of q[property] || []) {
          const value=snak.datavalue?.value;
          if (!value || value.precision < 9) return false;
          const raw=value.time.replace(/^\+/, '');
          // Coarse year/month qualifiers are usable only when the entire period is past/future.
          const year=Number(raw.slice(0,4)), month=Number(raw.slice(5,7));
          const earliest=value.precision===9 ? Date.UTC(year,0,1) : value.precision===10 ? Date.UTC(year,month-1,1) : Date.parse(raw);
          const latest=value.precision===9 ? Date.UTC(year+1,0,1)-1 : value.precision===10 ? Date.UTC(year,month,1)-1 : earliest;
          if (earliest<=time && latest>=time && value.precision<11) return false;
          const date=direction===1 ? latest : earliest;
          if (!Number.isFinite(date) || (direction===1 ? date>time : date<=time)) return false;
        }
      }
      return true;
    });
    return valid.some(s=>s.rank==='preferred') ? valid.filter(s=>s.rank==='preferred') : valid;
  }
  async function check(claim, fetchImpl=fetch, signal, now=new Date().toISOString()) {
    const parsed=parse(claim);
    if (!parsed) return null;
    const request=async params=>{
      const url=new URL('https://www.wikidata.org/w/api.php');
      url.search=new URLSearchParams({format:'json',origin:'*',...params});
      const r=await fetchImpl(url.toString(),{signal,credentials:'omit'});
      if(!r.ok)throw new Error('Structured source returned HTTP '+r.status+'.');
      const data=await r.json(); if(data.error)throw new Error('Structured source request failed.');return data;
    };
    const get=async ids=>(await request({action:'wbgetentities',ids:ids.join('|'),props:'labels|aliases|claims|info',languages:'en'})).entities || {};
    const resolve=async (name, accepts=()=>true)=>{
      const found=await request({action:'wbsearchentities',search:name,language:'en',uselang:'en',type:'item',limit:'5'});
      const ids=(found.search || []).map(x=>x.id); if(!ids.length)return null;
      const entities=Object.values(await get(ids));
      const candidates=entities.filter(accepts);
      const canonical=candidates.filter(e=>e.labels?.en?.value && normalize(e.labels.en.value)===normalize(name));
      const exact=canonical.length ? canonical : candidates.filter(e=>(e.aliases?.en || []).some(a=>normalize(a.value)===normalize(name)));
      return exact.length===1 ? exact[0] : null;
    };
    const place=await resolve(parsed.place,e=>(e.claims?.[parsed.property] || []).length>0);
    const entityValues=(e,p)=>(e?.claims?.[p] || []).map(s=>s.mainsnak?.datavalue?.value?.id).filter(Boolean);
    const countries=place ? [place.id,...entityValues(place,'P17')] : [];
    const subject=place ? await resolve(parsed.subject,e=>parsed.property==='P6' ? entityValues(e,'P31').includes('Q5') : entityValues(e,'P17').some(id=>countries.includes(id))) : null;
    const unresolved=reason=>({status:'Insufficient evidence',engine:'structured-wikidata',evidence:[],sourceCount:0,publisherCount:0,correctionPassage:null,assessedAt:now,caution:reason+' No language-model fallback is used for this recognized relation.'});
    if(!place)return unresolved('The place name could not be resolved unambiguously for this relation. Use its full official name.');
    if(!subject)return unresolved('The person or city could not be resolved unambiguously in the place context. Use its full name.');
    if(parsed.relation==='prime minister') {
      const offices=currentStatements(place.claims?.P1313,now);
      if(offices.length!==1)return unresolved('The head-of-government office title could not be established.');
      const id=offices[0].mainsnak.datavalue.value.id;
      const office=(await get([id]))[id];
      if(!/^prime minister(?: of |$)/i.test(office?.labels?.en?.value || ''))return unresolved('The recorded head-of-government office is not clearly a prime minister.');
    }
    const statements=currentStatements(place.claims?.[parsed.property],now);
    const ids=[...new Set(statements.map(s=>s.mainsnak.datavalue.value.id))];
    if(!ids.length)return unresolved('No usable current statements were found for this relation.');
    const values=await get(ids);
    const names=ids.map(id=>values[id]?.labels?.en?.value);
    if(names.some(n=>!n))return unresolved('The recorded values lack usable English labels.');
    const match=ids.includes(subject.id);
    // Multiple capitals/officeholders or incomplete records are not a closed-world proof.
    const conclusive=match || (ids.length===1 && statements.every(s=>(parsed.property==='P36' || s.rank==='preferred') && (s.references || []).length>0));
    const supports=parsed.negated ? !match : match;
    const status=!conclusive?'Insufficient evidence':supports?'Supported by structured source':'Contradicted by structured source';
    const relation=parsed.property==='P36'?'capital':parsed.relation;
    const text=`${place.labels.en.value} — ${relation}: ${names.join('; ')}. This is a rendering of the current selected Wikidata statements, not a quotation.`;
    const source={title:`${place.labels.en.value}: ${relation}`,text,publisher:'Wikidata',kind:'structured-record',url:`https://www.wikidata.org/w/index.php?title=${place.id}&oldid=${place.lastrevid}#${parsed.property}`,liveUrl:`https://www.wikidata.org/wiki/${place.id}#${parsed.property}`,updatedAt:place.modified || null,fetchedAt:now,entityId:place.id,property:parsed.property,statementIds:statements.map(s=>s.id),values:ids,statements};
    return {status,engine:'structured-wikidata',parsed,subjectId:subject.id,evidence:[source],sourceCount:1,publisherCount:1,correctionPassage:conclusive&&!supports?text:null,assessedAt:now,caution:'Compared resolved entity IDs with current structured records. Wikidata is community-maintained; inspect its references and dates. This is one source, not independent corroboration.'};
  }
  return {parse,currentStatements,check};
});
