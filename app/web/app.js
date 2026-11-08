'use strict';
const $=id=>document.getElementById(id);
const element=(tag,value)=>{const node=document.createElement(tag);node.textContent=value;return node;};
let workspace='',runId='',key='',timer=null;
let contextEpoch=0,runEpoch=0,sourceEpoch=0,libraryEpoch=0,historyEpoch=0;
const requests=new Set();
class StaleAction extends Error {}
const stale=error=>error instanceof StaleAction||error.name==='AbortError';
function showError(error){if(!stale(error))message(error.message);}
function resetRun(){
 clearTimeout(timer);timer=null;runId='';runEpoch++;sourceEpoch++;
 $('run-panel').hidden=true;$('empty').hidden=false;
 for(const id of ['run-title','run-status','plan-details','report','trace','stages'])$(id).replaceChildren();
 $('subquestions').value='';$('plan-panel').hidden=true;$('active-controls').hidden=true;$('approve').disabled=false;$('cancel').disabled=false;
 if($('source-dialog').open)$('source-dialog').close();
 for(const id of ['source-title','source-meta','source-text'])$(id).replaceChildren();
}
function changeWorkspace(id,force=false){
 if(id!==workspace||force){
  contextEpoch++;for(const controller of requests)controller.abort();requests.clear();resetRun();
  $('history').replaceChildren();$('source-list').replaceChildren();
  for(const form of document.querySelectorAll('form')){form.submission=null;form.querySelector('button').disabled=false;}
  $('research-form').reset();$('upload-form').reset();message('');
 }
 workspace=id;$('delete-workspace').disabled=!id;
}
$('copyright-year').textContent=new Date().getFullYear();
$('menu-toggle').onclick=()=>{const open=$('menu-toggle').getAttribute('aria-expanded')!=='true';$('menu-toggle').setAttribute('aria-expanded',String(open));$('workspace-navigation').classList.toggle('is-open',open);};
const busyStates=['queued','running'];
function message(value){$('message').textContent=value;}
async function api(path,options={},format='json'){
 const epoch=contextEpoch,controller=new AbortController();requests.add(controller);
 try{
  const headers={...options.headers};if(key)headers.Authorization=`Bearer ${key}`;
  if(options.body&&!(options.body instanceof FormData))headers['Content-Type']='application/json';
  const response=await fetch(path,{...options,headers,signal:controller.signal});
  if(epoch!==contextEpoch)throw new StaleAction();
  if(!response.ok){const detail=(await response.text()).slice(0,250);if(epoch!==contextEpoch)throw new StaleAction();throw new Error(`${response.status}: ${detail}`);}
  const value=response.status===204?null:format==='blob'?await response.blob():await response.json();
  if(epoch!==contextEpoch)throw new StaleAction();return value;
 }finally{requests.delete(controller);}
}
function form(id,action,success){$(id).onsubmit=async event=>{
 event.preventDefault();const token=Symbol(),button=$(id).querySelector('button');$(id).submission=token;button.disabled=true;message('Working…');
 try{await action();if($(id).submission===token)message(success);}catch(error){if($(id).submission===token)showError(error);}
 finally{if($(id).submission===token)button.disabled=false;}
};}
function chooseTab(name){document.title=(name==='library'?'Source library':'Research trail')+' · Cognitrail';document.querySelector('meta[name=description]').content=name==='library'?'Import permitted PDF and text sources and inspect evidence in your Cognitrail source library.':'Review research plans, exact source evidence, and cited briefs in your Cognitrail research trail.';document.querySelectorAll('.tab').forEach(tab=>tab.hidden=tab.id!==name);document.querySelectorAll('[data-tab]').forEach(button=>button.classList.toggle('selected',button.dataset.tab===name));}
async function loadWorkspaces(){
 const rows=await api('/api/workspaces'),select=$('workspace');select.replaceChildren();
 for(const row of rows){const option=element('option',row.name);option.value=row.id;select.append(option);}
 const next=rows.some(row=>row.id===workspace)?workspace:select.value;
 changeWorkspace(next);select.value=next;
 $('workspace-usage').textContent=`${rows.length} / 20 workspaces. Delete an unused workspace to free capacity.`;
 if(workspace)await Promise.all([library(),history()]);else $('source-list').textContent='Create a workspace first.';
}
async function library(){
 if(!workspace){$('source-list').replaceChildren();return;}
 const selection=++libraryEpoch,rows=await api(`/api/workspaces/${workspace}/sources`);if(selection!==libraryEpoch)return;$('source-list').replaceChildren();
 for(const source of rows){
  const card=element('article','');card.className='card';
  card.append(element('h3',source.title),element('p',`${source.kind} · imported ${new Date(source.created*1000).toLocaleDateString()} · publication date ${source.published||'unknown'}`),element('p',`SHA-256 ${source.sha256.slice(0,24)}…`));
  const row=element('div','');row.className='row';const preview=element('button','Read source');preview.onclick=()=>showSource(source.id).catch(showError);
  const remove=element('button','Delete source');remove.className='secondary';remove.onclick=async()=>{
   if(!confirm('Permanently delete this source and any reports quoting it?'))return;
   try{await api(`/api/sources/${source.id}`,{method:'DELETE'});resetRun();await Promise.all([library(),history()]);message('Source and related reports deleted.');}catch(error){showError(error);}
  };row.append(preview,remove);card.append(row);$('source-list').append(card);
 }
 if(!rows.length)$('source-list').append(element('p','No sources yet. Upload permitted PDF/TXT files, or add approved public URLs to a research plan.'));
}
async function history(){
 if(!workspace){$('history').replaceChildren();return;}
 const selection=++historyEpoch,rows=await api(`/api/runs?workspace_id=${workspace}`);if(selection!==historyEpoch)return;$('history').replaceChildren();
 for(const row of rows){
  const item=element('div','');item.className='history-row';
  const button=element('button',`${row.question.slice(0,70)}\n${row.status.replaceAll('_',' ')}`);button.className='history-item';button.onclick=()=>openRun(row.id).catch(showError);item.append(button);
  if(!busyStates.includes(row.status)){
   const remove=element('button','Delete');remove.className='secondary';remove.setAttribute('aria-label',`Delete research run: ${row.question.slice(0,70)}`);
   remove.onclick=async()=>{
    if(!confirm('Permanently delete this research plan or saved report?'))return;
    try{await api(`/api/runs/${row.id}`,{method:'DELETE'});if(runId===row.id)resetRun();await history();message('Research run deleted.');}catch(error){showError(error);}
   };item.append(remove);
  }$('history').append(item);
 }
}
async function showSource(id,evidence){
 const selection=++sourceEpoch,source=await api(`/api/sources/${id}`);if(selection!==sourceEpoch)return;
 $('source-title').textContent=source.title;$('source-meta').textContent=`${source.url||'Uploaded source'} · SHA-256 ${source.sha256}`;
 const text=$('source-text');text.replaceChildren();
 if(evidence)text.append(document.createTextNode(source.text.slice(0,evidence.start)),element('mark',source.text.slice(evidence.start,evidence.end)),document.createTextNode(source.text.slice(evidence.end)));
 else text.textContent=source.text;
 if(!$('source-dialog').open)$('source-dialog').showModal();
}
function renderReport(run){const target=$('report');target.replaceChildren();const report=run.report;if(!report.summary){if(report.message)target.append(element('p',report.message));return;}const counts=element('div','');counts.className='ledger';for(const [title,value]of [['Verified source spans',report.evidence.length],['Sources inspected',report.sources.length],['Open questions',report.gaps.length]]){const card=element('div','');card.className='metric';card.append(element('strong',value),element('span',title));counts.append(card);}target.append(counts);const brief=element('section','');brief.className='card';brief.append(element('p','THE RESEARCH BRIEF'),element('h2','What the evidence says'));const summary=element('div',report.summary);summary.className='summary';brief.append(summary);const exports=element('div','');exports.className='row';for(const format of ['json','markdown']){const button=element('button',`Export ${format}`);button.className='secondary';button.onclick=async()=>{try{const blob=await api(`/api/runs/${run.id}/export?format=${format}`,{},'blob');const url=URL.createObjectURL(blob);const link=element('a','');link.href=url;link.download=`cognitrail-${run.id}.${format==='json'?'json':'md'}`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){showError(error);}};exports.append(button);}brief.append(exports);target.append(brief);const ledger=element('section','');ledger.className='card';ledger.append(element('p','THE EVIDENCE LEDGER'),element('h2','Inspect every citation'));for(const evidence of report.evidence){const card=element('article','');card.className='evidence';const source=report.sources.find(s=>s.id===evidence.source_id);card.append(element('strong',`[${evidence.id}] · ${source?.title||evidence.source_id}`),element('blockquote',evidence.quote),element('p',`Exact source span · offsets ${evidence.start}–${evidence.end}`));const button=element('button','View in source ↗');button.onclick=()=>showSource(evidence.source_id,evidence).catch(showError);card.append(button);ledger.append(card);}target.append(ledger);for(const [heading,items]of [['Candidate disagreements',report.conflicts.map(c=>`${c.evidence_ids.join(' ↔ ')}: ${c.reason}. Human review required.`)],['Open questions',report.gaps],['Limitations & warnings',[...report.limitations,...report.warnings]]]){const card=element('section','');card.className='card';card.append(element('h2',heading));if(!items.length)card.append(element('p','None flagged. This is not proof that none exist.'));for(const item of items)card.append(element('p',item));target.append(card);}}
function render(run){$('empty').hidden=true;$('run-panel').hidden=false;$('run-title').textContent=run.question;$('run-status').textContent=run.status.replaceAll('_',' ');$('plan-panel').hidden=run.status!=='awaiting_approval';$('active-controls').hidden=!busyStates.includes(run.status);$('subquestions').value=run.plan.subquestions.join('\n');$('plan-details').replaceChildren(element('p',`Approved network budget: ${run.plan.max_web_sources} source attempts, up to ${run.plan.web_search?2:0} search calls. Model: ${run.plan.provider} / ${run.plan.model}.`),element('p',`Queries: ${run.plan.search_queries.join(' · ')}`),element('p',`Explicit URLs: ${run.plan.urls.join(' · ')||'none'}`));$('trace').replaceChildren();for(const step of run.trace){const node=element('div',`${step.at} · ${step.stage}\n${JSON.stringify(Object.fromEntries(Object.entries(step).filter(([k])=>!['at','stage'].includes(k))))}`);node.className='trace-event';$('trace').append(node);}const done=new Set(run.trace.map(t=>t.stage));$('stages').replaceChildren();for(const stage of ['collect','extract','verify','synthesize','publish']){const node=element('span',stage);node.className='stage'+(done.has(stage)?' done':'');$('stages').append(node);}renderReport(run);}
async function openRun(id,selection=null){
 clearTimeout(timer);
 if(selection===null){resetRun();selection=runEpoch;runId=id;chooseTab('research');}
 const epoch=contextEpoch,run=await api(`/api/runs/${id}`);
 if(epoch!==contextEpoch||selection!==runEpoch||runId!==id)return;
 render(run);
 if(busyStates.includes(run.status)){
  timer=setTimeout(()=>{if(epoch===contextEpoch&&selection===runEpoch&&runId===id)openRun(id,selection).catch(showError);},3000);
 }else await Promise.all([history(),library()]);
}
form('workspace-form',async()=>{
 const row=await api('/api/workspaces',{method:'POST',body:JSON.stringify({name:$('workspace-name').value})});
 changeWorkspace(row.id);$('workspace-name').value='';await loadWorkspaces();message('Workspace created.');
},'Workspace created.');
form('upload-form',async()=>{
 if(!workspace)throw new Error('Create a workspace first.');const file=$('upload').files[0];if(file.size>5*1024*1024)throw new Error('File exceeds 5 MB.');
 const body=new FormData();body.append('file',file);await api(`/api/workspaces/${workspace}/sources`,{method:'POST',body});await library();
},'Source imported.');
form('research-form',async()=>{
 if(!workspace)throw new Error('Create a workspace first.');const urls=$('urls').value.split('\n').map(value=>value.trim()).filter(Boolean);
 const row=await api('/api/runs',{method:'POST',body:JSON.stringify({workspace_id:workspace,question:$('question').value,urls,web_search:$('web-search').checked,max_web_sources:Number($('max-sources').value)})});await openRun(row.id);
},'Research plan created. Review and approve it to continue.');
$('approve').onclick=async()=>{
 const id=runId,selection=runEpoch,epoch=contextEpoch,button=$('approve');if(!id)return;button.disabled=true;
 try{
  const subquestions=$('subquestions').value.split('\n').map(value=>value.trim()).filter(Boolean);
  await api(`/api/runs/${id}/approve`,{method:'POST',body:JSON.stringify({approved:true,subquestions})});
  if(selection!==runEpoch||id!==runId)throw new StaleAction();
  await openRun(id,selection);if(epoch===contextEpoch&&selection===runEpoch)message('Research approved and queued.');
 }catch(error){if(epoch===contextEpoch&&selection===runEpoch)showError(error);}
 finally{if(epoch===contextEpoch&&selection===runEpoch)button.disabled=false;}
};
$('cancel').onclick=async()=>{
 const id=runId,selection=runEpoch,epoch=contextEpoch;if(!id)return;
 try{await api(`/api/runs/${id}/cancel`,{method:'POST'});if(selection!==runEpoch||id!==runId)throw new StaleAction();await openRun(id,selection);if(epoch===contextEpoch&&selection===runEpoch)message('Cancellation requested; the current bounded tool call may need to finish.');}catch(error){if(epoch===contextEpoch&&selection===runEpoch)showError(error);}
};
$('workspace').onchange=async()=>{changeWorkspace($('workspace').value);try{await Promise.all([library(),history()]);}catch(error){showError(error);}};
$('delete-workspace').onclick=async()=>{
 const id=workspace;if(!id||!confirm('Permanently delete this workspace, all its sources, research plans, and reports?'))return;
 $('delete-workspace').disabled=true;
 try{await api(`/api/workspaces/${id}`,{method:'DELETE'});changeWorkspace('');await loadWorkspaces();message('Workspace deleted. Capacity is available again.');}
 catch(error){showError(error);}finally{$('delete-workspace').disabled=!workspace;}
};
$('refresh').onclick=()=>history().catch(showError);
$('close-source').onclick=()=>{sourceEpoch++;$('source-dialog').close();};
$('access').onclick=async()=>{key=prompt('Optional local API access key. Kept in memory only.','')||'';changeWorkspace('',true);try{await loadWorkspaces();}catch(error){showError(error);}};
document.querySelectorAll('[data-tab]').forEach(button=>button.onclick=()=>chooseTab(button.dataset.tab));
async function initialize(){
 const health=await api('/health');
 if(health.scope==='private-single-operator'){$('access').hidden=true;document.querySelector('.local').textContent='● PRIVATE WORKSPACE';document.querySelector('.aside-bottom .small').textContent='Private owner workspace. Evidence is traceable, not automatically true.';}
 $('provider').textContent=health.provider==='extractive'?'Offline · exact-source extraction':`Live · ${health.model}`;
 $('web-search').disabled=!health.web_search_configured;await loadWorkspaces();
}
initialize().catch(showError);
