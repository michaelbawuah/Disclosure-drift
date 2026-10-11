"""Render a self-contained editor for explicit, source-bound filing reviews.

The packet builder validates source provenance. This page records decisions; the
existing offline audit remains responsible for rechecking exported reviews.
"""

import base64
import hashlib
import json
from html import escape


_STYLE = """
:root{color-scheme:light;--ink:#173146;--muted:#526777;--line:#d6e0e6;--blue:#14628a}
*{box-sizing:border-box}body{margin:0;background:#f5f8fa;color:var(--ink);font:16px/1.5 system-ui,-apple-system,sans-serif}
button,input,select,textarea{font:inherit}button{cursor:pointer;border:1px solid var(--line);border-radius:7px;background:white;color:var(--ink);padding:9px 13px}
button:hover{background:#edf4f8}button:disabled{opacity:.5;cursor:default}button.primary{background:var(--blue);color:white;border-color:var(--blue)}
button[aria-current=true],button[aria-selected=true]{background:#dfedf6;border-color:var(--blue)}:focus-visible{outline:3px solid #cc8700;outline-offset:2px}
header{padding:22px 28px;background:white;border-bottom:1px solid var(--line)}h1{font-size:26px;margin:0 0 6px}h2{font-size:21px;margin:0 0 12px}h3{font-size:17px;margin:0 0 10px}
p{margin:7px 0 12px}.muted,.small{color:var(--muted)}.small{font-size:13px}.toolbar{display:flex;gap:9px;flex-wrap:wrap;align-items:center;margin:15px 0 7px}
.shell{display:grid;grid-template-columns:275px minmax(0,1fr)}aside{padding:18px 14px;background:#edf3f6;border-right:1px solid var(--line)}
.queue{position:sticky;top:12px;max-height:calc(100vh - 24px);overflow:auto}.queue h3{margin:16px 5px 8px}.queue button{display:block;width:100%;text-align:left;margin:6px 0;font-size:14px}
.queue button span{display:block;font-size:12px;color:var(--muted);margin-top:3px}main{min-width:0;padding:22px}.tabs{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}
.workspace{display:grid;grid-template-columns:minmax(0,1fr) 335px;gap:18px}.card{background:white;border:1px solid var(--line);border-radius:9px;padding:18px;margin-bottom:16px;min-width:0}
.review-card{align-self:start;position:sticky;top:14px}.links{display:flex;gap:14px;flex-wrap:wrap}a{color:var(--blue)}details{margin:14px 0}summary{cursor:pointer;font-weight:650}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 ui-monospace,SFMono-Regular,monospace;margin:10px 0}.risk-text{font:15px/1.75 system-ui,-apple-system,sans-serif}
dl{display:grid;grid-template-columns:minmax(105px,auto) 1fr;gap:6px 12px;font-size:13px}dt{color:var(--muted)}dd{margin:0;overflow-wrap:anywhere}
label{display:block;margin:12px 0 5px;font-size:14px;font-weight:600}input[type=text],select,textarea{width:100%;border:1px solid #aabdc9;border-radius:5px;padding:9px;background:white;color:var(--ink)}
textarea{min-height:140px;resize:vertical}.check{display:flex;gap:9px;align-items:flex-start;font-weight:400}.check input{margin-top:5px;flex-shrink:0}
.notice{padding:10px 12px;border-left:3px solid #b58024;background:#fff7e7;font-size:14px;overflow-wrap:anywhere}.error{color:#9b271d}.ok{color:#226044}.hidden{display:none!important}
#review-status{min-height:3em;margin:12px 0;font-size:14px}#message{min-height:1.5em}.scope{font-size:13px;color:var(--muted)}code{overflow-wrap:anywhere}.full-width{width:100%}
@media(max-width:1120px){.workspace{grid-template-columns:minmax(0,1fr)}.review-card{position:static;grid-row:1}}
@media(max-width:700px){header{padding:17px}.shell{display:block}aside{border-right:0;border-bottom:1px solid var(--line)}.queue{position:static;max-height:245px}main{padding:14px}.card{padding:14px}h1{font-size:23px}}
"""


_MARKUP = """
<header>
  <h1 id="page-title"></h1><p id="scope-description" class="muted"></p>
  <p id="packet-summary" class="small"></p>
  <div class="toolbar">
    <button id="download-draft" type="button">Download draft</button>
    <button id="import-draft" type="button">Import draft</button>
    <input id="draft-file" type="file" accept=".json,application/json" hidden>
    <button id="export-reviews" type="button" class="primary" disabled>Export recorded reviews</button>
    <span id="progress" class="small"></span>
  </div>
  <p id="save-status" class="small" aria-live="polite">Download a draft to keep a portable copy of your work.</p>
  <p id="message" role="status" aria-live="polite"></p>
  <p class="small">This page records filing judgments. Source and historical-identity approvals remain separate.
  The completed 20/20 arithmetic review keeps its credit. Final 2022–2025 data remains unopened.</p>
</header>
<div class="shell">
  <aside aria-label="Review queue"><nav id="queue" class="queue"></nav></aside>
  <main>
    <div id="pair-nav" class="tabs" role="tablist" aria-label="Filing in selected pair"></div>
    <h2 id="filing-title"></h2><p id="filing-scope" class="scope"></p>
    <div class="workspace">
      <section class="card" aria-label="Filing evidence">
        <h3>Read the original sources</h3><p id="source-links" class="links"></p>
        <p class="small">The extracted text below helps you navigate. Inspect the complete linked sources before recording a judgment.</p>
        <div id="source-notices"></div><dl id="timing"></dl>
        <details><summary>Boundary context</summary><pre id="boundary-context"></pre></details>
        <details><summary>Evidence IDs and source bindings</summary><pre id="evidence-details"></pre></details>
        <details open><summary>Complete extracted risk section</summary><pre id="risk-text" class="risk-text"></pre></details>
      </section>
      <section class="card review-card" aria-label="Record this filing review">
        <h3>Your review of this filing</h3>
        <p class="small">Choose only judgments you have made. A pending field stays unresolved. Shared filings need one record.</p>
        <label for="reviewer">Reviewer name</label><input id="reviewer" type="text" maxlength="200" autocomplete="name">
        <label for="reviewer-type">Reviewer role</label><select id="reviewer-type"><option value="">Choose a role</option><option value="human">Human</option><option value="assistant">Assistant</option></select>
        <label for="boundary-verdict">Boundary and completeness judgment</label><select id="boundary-verdict"><option value="pending">Pending</option><option value="pass">Pass</option><option value="fail">Fail</option></select>
        <label for="timing-verdict">Timing judgment</label><select id="timing-verdict"><option value="pending">Pending</option><option value="pass">Pass</option><option value="fail">Fail</option></select>
        <p class="small">Timing concerns the SEC header and declared exchange-session proxy; a pass does not verify public dissemination.</p>
        <label for="review-notes">Notes and limitations</label><textarea id="review-notes" maxlength="100000" placeholder="Describe the source, boundaries or timing you checked, any limitation, and any assistant help."></textarea>
        <label class="check" for="source-inspected"><input id="source-inspected" type="checkbox"><span>I inspected the original filing/risk source and SEC header for the judgments I am recording.</span></label>
        <p id="review-status" aria-live="polite"></p>
        <button id="record-review" type="button" class="primary full-width">Record this review</button>
      </section>
    </div>
  </main>
</div>
<noscript><p class="notice">Enable JavaScript to use this local review editor. The existing reading packets remain available separately.</p></noscript>
"""


_SCRIPT = r"""
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const packet = JSON.parse($('packet-data').textContent);
  const files = new Map(packet.filings.map(f => [f.accession, f]));
  const paired = new Set(packet.pairs.flatMap(p => [p.previous_accession, p.accession]));
  const references = packet.filings.filter(f => f.scope_tags.includes('reference'));
  const extras = references.filter(f => !paired.has(f.accession));
  const fields = ['accession', 'evidence_id', 'reviewer', 'reviewer_type', 'reviewed_at', 'boundary_verdict', 'timing_verdict', 'notes'];
  const controls = {reviewer:'reviewer', reviewer_type:'reviewer-type', boundary_verdict:'boundary-verdict', timing_verdict:'timing-verdict', notes:'review-notes'};
  const storageKey = 'disclosure-filing-review-v1:' + packet.packet_id;
  let state = {schema_version:1, packet_id:packet.packet_id, profile:{reviewer:'', reviewer_type:''}, drafts:{}, recorded:{}};
  let active = null, activePair = null, portableDirty = false, storageAvailable = true;
  const own = (object, key) => Object.prototype.hasOwnProperty.call(object, key);
  const object = x => x !== null && typeof x === 'object' && !Array.isArray(x);
  function need(ok, message) { if (!ok) throw new Error(message); }
  function exactKeys(value, keys, label) {
    need(object(value) && Object.keys(value).length === keys.length && keys.every(k => own(value,k)), 'Invalid ' + label + ' fields.');
  }
  function element(tag, text, className) {
    const node = document.createElement(tag); if (text !== undefined) node.textContent = text;
    if (className) node.className = className; return node;
  }
  function message(text, error=false) { $('message').textContent=text; $('message').className=error?'error':'ok'; }
  function validTime(value) {
    if (typeof value !== 'string') return false;
    const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d{1,6}))?(Z|[+-]\d{2}:\d{2})$/.exec(value);
    if (!m) return false;
    const [y,mo,d,h,mi,s] = m.slice(1,7).map(Number);
    const leap = y%4===0 && (y%100!==0 || y%400===0);
    const days = [31,leap?29:28,31,30,31,30,31,31,30,31,30,31];
    if (y<1 || mo<1 || mo>12 || d<1 || d>days[mo-1] || h>23 || mi>59 || s>59) return false;
    if (m[8]!=='Z' && (Number(m[8].slice(1,3))>23 || Number(m[8].slice(4,6))>59)) return false;
    const instant = Date.parse(value.replace(' ','T'));
    return Number.isFinite(instant) && instant<=Date.now();
  }
  function validFields(row, accession, draft) {
    exactKeys(row, draft?[...fields,'original_source_inspected']:fields, 'review');
    need(files.has(accession) && row.accession===accession, 'Unknown or mismatched accession.');
    need(row.evidence_id===files.get(accession).evidence_id, 'Stale or changed filing evidence ID.');
    need(typeof row.reviewer==='string' && row.reviewer.length<=200, 'Invalid reviewer name.');
    need(typeof row.notes==='string' && row.notes.length<=100000, 'Invalid review notes.');
    need((draft?['','human','assistant']:['human','assistant']).includes(row.reviewer_type), 'Invalid reviewer role.');
    for (const key of ['boundary_verdict','timing_verdict']) need(['pending','pass','fail'].includes(row[key]), 'Invalid verdict.');
    need(typeof row.reviewed_at==='string', 'Invalid review timestamp.');
    if (row.reviewed_at!=='') need(validTime(row.reviewed_at), 'Review timestamp must be valid, timezone-aware and not in the future.');
    if (draft) need(typeof row.original_source_inspected==='boolean', 'Invalid source-inspection declaration.');
    else {
      need(row.reviewer.trim() && row.notes.trim(), 'A recorded review needs your name and substantive notes.');
      need(row.boundary_verdict!=='pending' || row.timing_verdict!=='pending', 'Choose at least one completed judgment.');
      need(validTime(row.reviewed_at), 'A recorded review needs a valid actual timestamp.');
    }
  }
  function reviewFrom(draft) { return Object.fromEntries(fields.map(key => [key,draft[key]])); }
  function validateState(value) {
    exactKeys(value,['schema_version','packet_id','profile','drafts','recorded'],'draft document');
    need(value.schema_version===1 && value.packet_id===packet.packet_id, 'This draft belongs to a different packet.');
    exactKeys(value.profile,['reviewer','reviewer_type'],'reviewer profile');
    need(typeof value.profile.reviewer==='string' && value.profile.reviewer.length<=200 && ['', 'human','assistant'].includes(value.profile.reviewer_type), 'Invalid reviewer profile.');
    need(object(value.drafts) && object(value.recorded), 'Drafts and recorded reviews must be maps.');
    need(Object.keys(value.drafts).length<=files.size && Object.keys(value.recorded).length<=files.size, 'Too many review records.');
    for (const [key,row] of Object.entries(value.drafts)) {
      validFields(row,key,true);
      need(row.reviewed_at==='' || own(value.recorded,key), 'A draft timestamp has no matching recorded review.');
    }
    for (const [key,row] of Object.entries(value.recorded)) {
      validFields(row,key,false);
      need(own(value.drafts,key) && value.drafts[key].original_source_inspected, 'A recorded review requires its inspected-source draft.');
      need(fields.every(field => row[field]===value.drafts[key][field]), 'Recorded review and draft differ; record the changed review again.');
    }
    return value;
  }
  // JSON.parse alone silently accepts duplicate map keys. Reject them at every level.
  function parseUniqueJSON(text) {
    let position=0, nodes=0;
    const white = () => { while (/[ \t\r\n]/.test(text[position] || '') && position<text.length) position++; };
    function string() {
      const start=position++; let escaped=false;
      while (position<text.length) {
        const c=text[position++];
        if (!escaped && c==='"') return JSON.parse(text.slice(start,position));
        if (!escaped && c==='\\') escaped=true; else escaped=false;
      }
      throw new Error('Unterminated JSON string.');
    }
    function value(depth=0) {
      need(depth<20 && ++nodes<100000, 'Draft structure is too large or deeply nested.'); white();
      const c=text[position];
      if (c==='"') return string();
      if (c==='{' || c==='[') {
        const map=c==='{', result=map?Object.create(null):[], seen=new Set(), end=map?'}':']';
        position++; white(); if (text[position]===end) { position++; return result; }
        while (position<text.length) {
          let key;
          if (map) {
            need(text[position]==='"','Invalid JSON object key.'); key=string();
            need(!seen.has(key),'Duplicate JSON key: ' + key.slice(0,80)); seen.add(key); white();
            need(text[position++]===':','Missing JSON colon.');
          }
          const item=value(depth+1); if (map) result[key]=item; else result.push(item); white();
          if (text[position]===end) { position++; return result; }
          need(text[position++]===',','Invalid JSON separator.'); white();
        }
        throw new Error('Unterminated JSON collection.');
      }
      const match=/^(?:true|false|null|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?)/.exec(text.slice(position));
      need(match,'Invalid JSON value.'); position+=match[0].length; return JSON.parse(match[0]);
    }
    const result=value(); white(); need(position===text.length,'Unexpected trailing JSON content.'); return result;
  }
  function saveLocal() {
    try { localStorage.setItem(storageKey,JSON.stringify(state)); storageAvailable=true; }
    catch (_) { storageAvailable=false; }
    $('save-status').textContent = storageAvailable
      ? 'Changes kept in this browser. Download a draft for a portable backup.'
      : 'Automatic browser saving is unavailable. Download a draft before leaving.';
  }
  function getDraft(accession) {
    if (!own(state.drafts,accession)) state.drafts[accession] = {
      accession, evidence_id:files.get(accession).evidence_id, ...state.profile,
      reviewed_at:'', boundary_verdict:'pending', timing_verdict:'pending', notes:'', original_source_inspected:false
    };
    return state.drafts[accession];
  }
  function statusFor(accession) {
    const r=state.recorded[accession];
    if (!r) return 'Pending / not recorded';
    if (r.boundary_verdict==='fail' || r.timing_verdict==='fail') return 'Failure recorded';
    return r.boundary_verdict==='pass' && r.timing_verdict==='pass'
      ? (r.reviewer_type==='human'?'Human':'Assistant') + ' judgments recorded'
      : 'Partial judgment recorded';
  }
  function progress() {
    const count=Object.keys(state.recorded).length;
    $('progress').textContent=count + ' / ' + files.size + ' filings have a recorded judgment';
    $('export-reviews').disabled=count===0;
  }
  function renderQueue() {
    const queue=$('queue'); queue.replaceChildren(element('h3','Fixed pair queue'));
    for (const [index,pair] of packet.pairs.entries()) {
      const button=element('button',String(pair.number).padStart(2,'0') + ' · ' + pair.name);
      button.type='button'; button.id='pair-' + pair.number; button.setAttribute('aria-current',String(activePair===index));
      const count=[pair.previous_accession,pair.accession].filter(a => own(state.recorded,a)).length;
      button.append(element('span',pair.acceptance_date + ' · ' + count + '/2 filings recorded'));
      button.addEventListener('click',() => showPair(index)); queue.append(button);
    }
    queue.append(element('h3','Additional reference filings'));
    queue.append(element('p',references.length + ' reference filings; ' + (references.length-extras.length) + ' also occur in the fixed pairs.','small'));
    for (const filing of extras) {
      const button=element('button',filing.name + ' · ' + filing.acceptance_date);
      button.type='button'; button.id='reference-' + filing.accession;
      button.setAttribute('aria-current',String(activePair===null && active===filing.accession));
      button.append(element('span',statusFor(filing.accession)));
      button.addEventListener('click',() => showFiling(filing.accession,null)); queue.append(button);
    }
    progress();
  }
  function sourceLink(url,label) {
    try {
      const parsed=new URL(url);
      if (parsed.protocol==='https:' && ['www.sec.gov','data.sec.gov'].includes(parsed.hostname) && !parsed.username && !parsed.password && (!parsed.port || parsed.port==='443')) {
        const link=element('a',label); link.href=parsed.href; link.target='_blank'; link.rel='noopener noreferrer'; return link;
      }
    } catch (_) { /* Untrusted or missing URLs are rendered as text only. */ }
    return element('span',label + ' (verified link unavailable)','small');
  }
  function renderReviewStatus() {
    const draft=getDraft(active), recorded=state.recorded[active];
    $('review-status').textContent=recorded
      ? statusFor(active) + ' at ' + recorded.reviewed_at + '. Editing any field requires recording again.'
      : draft.reviewed_at==='' ? 'Not recorded. Record your actual judgments when ready.' : 'Changes need recording.';
    $('record-review').textContent=recorded?'Record this review again':'Record this review';
  }
  function showPair(index) { showFiling(packet.pairs[index].previous_accession,index); }
  function showFiling(accession,pairIndex) {
    active=accession; activePair=pairIndex;
    const filing=files.get(accession), draft=getDraft(accession), nav=$('pair-nav'); nav.replaceChildren();
    if (pairIndex!==null) {
      const pair=packet.pairs[pairIndex];
      for (const [label,key] of [['Previous filing','previous_accession'],['Current filing','accession']]) {
        const button=element('button',label + ' · ' + pair[key]); button.type='button';
        button.id=key==='accession'?'show-current':'show-previous'; button.setAttribute('role','tab');
        button.setAttribute('aria-selected',String(accession===pair[key]));
        button.addEventListener('click',() => showFiling(pair[key],pairIndex)); nav.append(button);
      }
    }
    $('filing-title').textContent=filing.name + ' · ' + filing.acceptance_date;
    $('filing-scope').textContent=filing.accession + ' · ' + filing.scope_tags.join(' / ') + ' · Report date: ' + filing.report_date;
    $('source-links').replaceChildren(sourceLink(filing.source_url,'Complete filing'),sourceLink(filing.risk_source_url,'Risk source'),sourceLink(filing.header_url,'SEC header'));
    const notices=$('source-notices'); notices.replaceChildren();
    if (filing.blocking_issues.length) notices.append(element('p','Source checks remain unresolved: ' + filing.blocking_issues.join('; ') + '. Recording a review does not resolve these checks.','notice'));
    if (filing.cautions.length) notices.append(element('p','Cautions: ' + filing.cautions.join('; '),'notice'));
    const timing=$('timing'); timing.replaceChildren();
    for (const [label,key] of [['SEC acceptance','acceptance_timestamp'],['API timestamp','api_timestamp'],['Controls through','controls_through'],['Reference session','reference_session'],['Label end','label_end'],['Resolution method','resolution_method']]) timing.append(element('dt',label),element('dd',String(filing[key] ?? '')));
    $('boundary-context').textContent=['Before: '+filing.start_context,'Section begins: '+filing.section_start,'Section ends: '+filing.section_end,'After: '+filing.end_context].join('\n\n');
    $('evidence-details').textContent=JSON.stringify({accession:filing.accession,evidence_id:filing.evidence_id,packet_id:packet.packet_id,resolution_rule_id:filing.resolution_rule_id,source_bindings:packet.source_bindings},null,2);
    $('risk-text').textContent=filing.risk_text;
    for (const [key,id] of Object.entries(controls)) $(id).value=draft[key];
    $('source-inspected').checked=draft.original_source_inspected;
    renderReviewStatus(); renderQueue();
  }
  function changed() {
    if (!active) return;
    const draft=getDraft(active), hadRecord=own(state.recorded,active);
    for (const [key,id] of Object.entries(controls)) draft[key]=$(id).value;
    draft.original_source_inspected=$('source-inspected').checked;
    draft.reviewed_at=''; delete state.recorded[active];
    state.profile={reviewer:draft.reviewer,reviewer_type:draft.reviewer_type};
    portableDirty=true; saveLocal(); renderReviewStatus(); progress(); if (hadRecord) renderQueue();
    $('review-status').textContent='Changes are not recorded. Record this filing again when ready.';
  }
  for (const id of Object.values(controls)) $(id).addEventListener('input',changed);
  $('source-inspected').addEventListener('change',changed);
  $('record-review').addEventListener('click',() => {
    try {
      const draft=getDraft(active);
      need(draft.original_source_inspected,'Inspect the original sources and check the declaration before recording.');
      const candidate={...reviewFrom(draft),reviewed_at:new Date().toISOString()}; validFields(candidate,active,false);
      state.recorded[active]=candidate; draft.reviewed_at=candidate.reviewed_at;
      portableDirty=true; saveLocal(); renderReviewStatus(); renderQueue();
      message('Recorded this filing judgment. Export recorded reviews for the offline source audit.');
    } catch (error) { message(error.message,true); }
  });
  function download(content,name,type) {
    const url=URL.createObjectURL(new Blob([content],{type})), link=element('a');
    link.href=url; link.download=name; document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url),1000);
  }
  $('download-draft').addEventListener('click',() => {
    try {
      validateState(state); download(JSON.stringify(state,null,2)+'\n','filing-review-draft-'+packet.packet_id.slice(0,12)+'.json','application/json');
      portableDirty=false; $('save-status').textContent='Draft download requested. Keep that file to resume on this or another browser.';
      message('The draft includes pending work and preserved review timestamps. It is separate from the audit JSONL export.');
    } catch (error) { message(error.message,true); }
  });
  $('export-reviews').addEventListener('click',() => {
    try {
      validateState(state); const rows=Object.keys(state.recorded).sort().map(key => state.recorded[key]);
      need(rows.length>0,'Record a review before exporting.');
      download(rows.map(row => JSON.stringify(row)).join('\n')+'\n','filing-reviews-'+packet.packet_id.slice(0,12)+'.jsonl','application/x-ndjson');
      message('Export requested for '+rows.length+' explicitly recorded reviews. Run the existing offline audit to recheck source fingerprints.');
    } catch (error) { message(error.message,true); }
  });
  $('import-draft').addEventListener('click',() => $('draft-file').click());
  $('draft-file').addEventListener('change',async event => {
    const file=event.target.files[0]; if (!file) return;
    try {
      need(file.size<=32*1024*1024,'Draft file exceeds the 32 MiB limit.');
      const imported=validateState(parseUniqueJSON(await file.text()));
      if (portableDirty && !window.confirm('Replace the current working draft? Download it first if you need to keep it.')) return;
      state=imported; portableDirty=true; saveLocal();
      if (active) showFiling(active,activePair); else if (packet.pairs.length) showPair(0); else showFiling(packet.filings[0].accession,null);
      message('Draft imported. Existing recorded timestamps were preserved; no reviews were created or retimed.');
    } catch (error) { message('Draft was not imported: '+error.message,true); }
    finally { event.target.value=''; }
  });
  window.addEventListener('beforeunload',event => { if (portableDirty) { event.preventDefault(); event.returnValue=''; } });
  $('page-title').textContent=packet.title; document.title=packet.title;
  $('scope-description').textContent=packet.scope_description;
  $('packet-summary').textContent=packet.summary.selected_pairs+' fixed pairs · '+packet.summary.selected_filings+' selected filings · '+packet.summary.reference_filings+' reference filings · '+packet.summary.distinct_filings+' distinct filings in this packet';
  try {
    const saved=localStorage.getItem(storageKey);
    if (saved) { state=validateState(parseUniqueJSON(saved)); portableDirty=true; message('Recovered a matching browser draft. Download a portable backup.'); }
  } catch (_) { message('A browser draft could not be used. Import a downloaded draft to resume safely.',true); }
  if (packet.pairs.length) showPair(0); else if (packet.filings.length) showFiling(packet.filings[0].accession,null);
})();
"""


def render_review_page(packet: dict) -> str:
    """Embed an already validated packet without trusting any source text as HTML."""
    payload = json.dumps(packet, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")

    def csp_hash(value: str) -> str:
        digest = hashlib.sha256(value.encode("utf-8")).digest()
        return "'sha256-" + base64.b64encode(digest).decode("ascii") + "'"

    policy = (
        "default-src 'none'; script-src " + csp_hash(_SCRIPT) + " " + csp_hash(payload)
        + "; style-src " + csp_hash(_STYLE)
        + "; connect-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'"
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f'<meta http-equiv="Content-Security-Policy" content="{escape(policy, quote=True)}">'
        f'<title>{escape(str(packet["title"]))}</title><style>{_STYLE}</style></head><body>'
        + _MARKUP + f'<script id="packet-data" type="application/json">{payload}</script>'
        + f'<script>{_SCRIPT}</script></body></html>'
    )
