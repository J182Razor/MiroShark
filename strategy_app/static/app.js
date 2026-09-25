const $ = id => document.getElementById(id);
const state = {token:'',config:null,evidence:[],run:null,tab:'summary',timer:null,sequence:0,pending:null};
function requestID(){
  if(typeof crypto.randomUUID==='function')return crypto.randomUUID();
  return Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');
}
const terminal = new Set(['completed','needs_review','failed','cancelled','interrupted']);
const pretty = value => String(value ?? '').replaceAll('_',' ');
const el = (tag, text='', className='') => { const node=document.createElement(tag); node.textContent=text; if(className) node.className=className; return node; };
const setVisible = (id, visible) => { $(id).hidden=!visible; };
function notify(message='',error=false){ const box=$('notice'); box.textContent=message; box.className='global-notice'+(error?' error':''); box.hidden=!message; }

async function api(path, options={}){
  const response=await fetch(path,{...options,headers:{'Authorization':`Bearer ${state.token}`,...(options.body?{'Content-Type':'application/json'}:{}),...(options.headers||{})}});
  let result; try{result=await response.json();}catch{throw new Error('The server returned an unreadable response. Check the connection before retrying.');}
  if(!response.ok) throw new Error(result.error||`Request failed (${response.status})`);
  return result;
}
const post=(path,data={},headers={})=>api(path,{method:'POST',body:JSON.stringify(data),headers});

function stopPolling(){ clearTimeout(state.timer); state.sequence++; }
function showComposer(){stopPolling();state.run=null;setVisible('run-view',false);setVisible('composer',!!state.token);setVisible('access',!state.token);$('breadcrumb').textContent='New analysis';notify();}
function lock(){ stopPolling();state.token='';state.config=null;state.run=null;state.evidence=[];state.pending=null;$('access-token').value='';$('history').replaceChildren(el('p','Unlock your workspace to view saved analyses.','empty-history'));$('analysis-form').reset();$('evidence-list').replaceChildren();$('tab-content').replaceChildren();$('connection').textContent='Workspace locked';setVisible('lock',false);setVisible('access',true);setVisible('composer',false);setVisible('run-view',false);notify(); }

async function history(){
  const result=await api('/api/runs'); const host=$('history');host.replaceChildren();
  if(!result.runs.length){host.append(el('p','Your saved analyses will appear here.','empty-history'));return;}
  for(const run of result.runs){
    const button=el('button','','history-item'+(state.run?.id===run.id?' selected':''));
    button.append(el('span',run.question,'history-title'),el('span',(run.demo?'Synthetic · ':'')+pretty(run.status),'history-meta'));
    button.onclick=()=>openRun(run.id).catch(e=>notify(e.message,true));host.append(button);
  }
}

$('access-form').onsubmit=async event=>{
  event.preventDefault();state.token=$('access-token').value.trim();notify();
  try{
    state.config=await api('/api/config');$('access-token').value='';$('connection').textContent='Unlocked · configuration loaded';setVisible('lock',true);showComposer();
    const ready=state.config.live_enabled&&!state.config.missing.length;
    $('run-live').disabled=!ready;$('run-demo').hidden=!state.config.demo_enabled;
    $('setup-message').textContent=ready?'Provider settings are present. Connectivity and live model behavior have not been verified by this screen.':`Live analysis is not enabled or configured. Required server settings: ${state.config.missing.join(', ')||'STRATEGY_LIVE_ENABLED=true'}. The synthetic example is separate from live analysis.`;
    setVisible('setup-message',true);await history();
  }catch(error){state.token='';notify(error.message,true);}
};
$('lock').onclick=lock;$('new-analysis').onclick=showComposer;
$('toggle-history').onclick=()=>{const open=document.querySelector('.sidebar').classList.toggle('history-open');$('toggle-history').setAttribute('aria-expanded',String(open));};
$('mode').onchange=()=>{
  const mode=$('mode').value;setVisible('rounds-field',mode==='new');setVisible('simulation-permission',mode==='new');setVisible('existing-field',mode==='existing');
};
function evidenceList(){
  $('evidence-count').textContent=`${state.evidence.length} records`;$('evidence-list').replaceChildren();
  state.evidence.forEach((record,index)=>{const li=el('li');li.append(el('span',`${record.title} · ${record.text.length.toLocaleString()} characters`));const remove=el('button','Remove','link-button');remove.type='button';remove.onclick=()=>{state.evidence.splice(index,1);evidenceList();};li.append(remove);$('evidence-list').append(li);});
}
function addEvidence(record){if(state.evidence.length>=8)throw new Error('Maximum eight source records.');state.evidence.push(record);evidenceList();}
$('add-evidence').onclick=()=>{
  try{const title=$('source-title').value.trim(),text=$('source-text').value.trim();if(!title||!text)throw new Error('Provide a source title and extract.');addEvidence({title,text});$('source-title').value='';$('source-text').value='';notify();}catch(e){notify(e.message,true);}
};
$('source-file').onchange=async()=>{
  const file=$('source-file').files[0];if(!file)return;
  try{if(file.size>1000000)throw new Error('Upload documents of 1 MB or less.');const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));const record=await post('/api/documents',{name:file.name,base64:btoa(binary)});addEvidence(record);notify();}catch(e){notify(e.message,true);}finally{$('source-file').value='';}
};

async function submit(demo=false){
  const input={question:$('question').value,context:$('context').value,constraints:$('constraints').value,evidence:state.evidence,
    mode:$('mode').value,simulation_id:$('simulation-id').value,authorize_simulation:$('authorize-simulation').checked,
    rounds:Number($('rounds').value),threshold:Number($('threshold').value),max_iterations:Number($('iterations').value),demo};
  const signature=JSON.stringify(input);
  if(state.pending?.signature!==signature)state.pending={signature,key:requestID()};
  $('run-live').disabled=true;$('run-demo').disabled=true;notify();
  try{const run=await post('/api/runs',input,{'Idempotency-Key':state.pending.key});state.pending=null;await openRun(run.id);await history();}
  catch(e){notify(e.message,true);}
  finally{$('run-live').disabled=!(state.config?.live_enabled&&!state.config.missing.length);$('run-demo').disabled=false;}
}
$('analysis-form').onsubmit=e=>{e.preventDefault();submit(false);};$('run-demo').onclick=()=>submit(true);

async function openRun(id){
  document.querySelector('.sidebar').classList.remove('history-open');$('toggle-history').setAttribute('aria-expanded','false');
  stopPolling();const seq=state.sequence;const run=await api(`/api/runs/${id}`);if(seq!==state.sequence)return;
  state.run=run;state.tab=run.status==='awaiting_approval'?'plan':'summary';setVisible('composer',false);setVisible('access',false);setVisible('run-view',true);notify();renderRun();poll(id,seq);history().catch(()=>{});
}
function poll(id,seq){
  if(seq!==state.sequence||terminal.has(state.run?.status)||state.run?.status==='awaiting_approval')return;
  state.timer=setTimeout(async()=>{
    try{const run=await api(`/api/runs/${id}`);if(seq!==state.sequence)return;const old=state.run?.status;state.run=run;if(run.status!==old&&run.status==='awaiting_approval')state.tab='plan';if(run.status!==old&&run.status==='completed')state.tab='summary';renderRun();if(terminal.has(run.status)||run.status==='awaiting_approval')await history();poll(id,seq);}
    catch(e){notify('Status check failed. Your saved run has not been restarted. '+e.message,true);}
  },1300);
}
function activate(tab){state.tab=tab;renderTab();}
const tabs=[...document.querySelectorAll('[data-tab]')];
tabs.forEach((button,index)=>{button.id=`tab-${button.dataset.tab}`;button.onclick=()=>activate(button.dataset.tab);button.onkeydown=e=>{if(!['ArrowLeft','ArrowRight'].includes(e.key))return;e.preventDefault();const next=tabs[(index+(e.key==='ArrowRight'?1:-1)+tabs.length)%tabs.length];next.focus();activate(next.dataset.tab);};});

function renderRun(){
  const run=state.run;$('breadcrumb').textContent='Analysis / '+run.id.slice(-8);$('run-title').textContent=run.report?.title||run.input.question;
  $('run-created').textContent=`Created ${new Date(run.created_at).toLocaleString()} · ${run.input.mode==='none'?'No simulation requested':run.input.mode==='existing'?'Attached MiroShark simulation':'New MiroShark simulation'}`;
  setVisible('demo-banner',run.demo);$('run-status-label').textContent=pretty(run.status);$('run-progress').textContent=`${run.progress}%`;$('progress').value=run.progress;
  $('run-message').textContent=run.message||'Waiting for a worker.';
  $('remote-ids').textContent=[run.project_id?`MiroShark project: ${run.project_id}`:'',run.simulation_id?`Simulation: ${run.simulation_id}`:''].filter(Boolean).join(' · ');
  setVisible('cancel',!terminal.has(run.status));setVisible('approval-panel',run.status==='awaiting_approval');setVisible('human-review',terminal.has(run.status));
  $('review-result').textContent=run.review?`Saved: ${pretty(run.review.verdict)}`:'';renderTab();
}
function section(title,host=$('tab-content')){const block=el('section','','report-section');block.append(el('h2',title));host.append(block);return block;}
function list(values,host){const ul=el('ul','','plain-list');for(const value of values||[])ul.append(el('li',value));if(!values?.length)ul.append(el('li','None reported.'));host.append(ul);}
function table(headers,rows,host){const wrap=el('div','','data-table-wrap'),t=el('table','','data-table'),head=el('thead'),hrow=el('tr'),body=el('tbody');headers.forEach(v=>{const th=el('th',v);th.scope='col';hrow.append(th);});head.append(hrow);t.append(head);for(const row of rows){const tr=el('tr');row.forEach(value=>{const td=el('td');td.append(value instanceof Node?value:document.createTextNode(String(value??'')));tr.append(td);});body.append(tr);}t.append(body);wrap.append(t);host.append(wrap);}
function renderTab(){
  if(!state.run)return;const host=$('tab-content');host.replaceChildren();host.setAttribute('aria-labelledby',`tab-${state.tab}`);
  tabs.forEach(button=>{const selected=button.dataset.tab===state.tab;button.setAttribute('aria-selected',String(selected));button.tabIndex=selected?0:-1;});
  ({summary:renderSummary,plan:renderPlan,evidence:renderEvidence,validation:renderValidation,activity:renderActivity}[state.tab]||renderSummary)();
}
function renderSummary(){
  const run=state.run,report=run.report;
  if(!report){const block=section('No final analysis yet');block.classList.add('empty-result');block.append(el('p',run.status==='awaiting_approval'?'The analysis plan is ready for your review. Inspect the Plan tab and approve the Outcome Contract to continue.':run.message||'The worker is preparing the analysis.'));if(run.plan){const button=el('button','Inspect the analysis plan','secondary');button.onclick=()=>activate('plan');block.append(button);}return;}
  section('Executive answer').append(el('p',report.summary,'report-lead'));
  const recommendation=section('Recommendation');recommendation.classList.add('recommendation');recommendation.append(el('p',report.recommendation));
  const alternatives=section('Alternatives');table(['Path','Why consider it','Trade-off','Choose it when'],report.options.map(o=>[o.name+(o.is_status_quo?' · status quo':''),o.case_for,o.case_against,o.conditions]),alternatives);
  list(report.assumptions,section('Assumptions'));list(report.evidence_gaps,section('Evidence still needed'));
  table(['Risk','Mitigation'],report.risks.map(r=>[r.risk,r.mitigation]),section('Risks and protections'));
  table(['Next action','Owner','Success check','Stop rule'],report.next_steps.map(s=>[s.action,s.owner,s.success_check,s.stop_rule]),section('Next steps'));
  list(report.decision_triggers,section('What would change this recommendation'));
  const claims=section('Claims and provenance');
  for(const claim of report.claims){const row=el('div','','claim');row.append(el('span',pretty(claim.kind),'claim-kind'),document.createTextNode(claim.statement));for(const id of claim.evidence_ids){const link=el('button',`[${id}]`,'link-button source-link');link.onclick=()=>{activate('evidence');const source=document.getElementById(`source-${id}`);if(source){source.open=true;source.scrollIntoView({block:'center'});}};row.append(link);}claims.append(row);}
  if(!report.claims.length)claims.append(el('p','No source-backed factual claims were listed.','helper'));
  const swot=section('SWOTMM'),grid=el('div','','swot-grid');
  for(const name of ['strengths','weaknesses','opportunities','threats','moats','monetization']){const item=el('div','','swot-section');item.append(el('h3',name));list(report.swotmm[name],item);grid.append(item);}swot.append(grid);
}
function renderPlan(){
  const run=state.run;if(!run.plan){section('Plan not available yet').append(el('p','The planner has not produced a stored Outcome Contract.','helper'));return;}
  const block=section('Outcome Contract'),dl=el('dl','','detail-grid');
  for(const [key,value] of Object.entries(run.plan.outcome_contract)){dl.append(el('dt',pretty(key)),el('dd',Array.isArray(value)?value.join('\n'):String(value)));}block.append(dl,el('p',`Version ${run.revisions.length} · Plan SHA-256 ${run.plan_hash}`,'helper'));
  const atoms=section('Atomic analysis plan');
  table(['Component','Executor / evidence','Dependencies','Observable pass rule'],run.plan.atoms.map(a=>{
    const title=el('div',`${a.id} · ${a.action}`);title.append(el('span',a.object,'table-secondary'));
    const executor=el('div',pretty(a.executor));executor.append(el('span',a.evidence_ids.join(', ')||'No source named','table-secondary'));
    const pass=el('div',a.postcondition);pass.append(el('span','On failure: '+a.failure_path,'table-secondary'));
    return [title,executor,a.dependencies.join(', ')||'None',pass];}),atoms);
  list(run.plan.assumptions,section('Planning assumptions'));list(run.plan.questions,section('Clarifications and missing inputs'));
  const details=el('details');details.append(el('summary','Inspect the full typed plan'),el('pre',JSON.stringify(run.plan,null,2),'json-detail'));atoms.append(details);
}
function renderEvidence(){
  const block=section('Evidence register');block.append(el('p','These are the actual supplied records and captured simulation observations. User-supplied material is not independently verified. Simulations remain hypothetical.','helper'));
  for(const source of state.run.evidence||[]){const details=el('details','','source-card');details.id=`source-${source.id}`;details.append(el('summary',`[${source.id}] ${source.title}`),el('p',`${pretty(source.kind)} · Captured ${source.captured_at} · SHA-256 ${source.content_hash}`,'source-meta'));
    if(source.coverage)details.append(el('p',source.coverage+(source.truncated?' Text also truncated at 24,000 characters.':''),'source-meta'));details.append(el('pre',source.text));block.append(details);}
  if(!state.run.evidence?.length)block.append(el('p','No evidence records have been captured yet.','helper'));
}
function renderValidation(){
  const run=state.run;const host=$('tab-content');host.append(el('div','Uncalibrated scores. The minimum critical dimension controls acceptance; scores are not averaged or multiplied. Passing 0.95 does not establish 95% correctness or predict real-world success.','audit-note'));
  if(run.models){table(['Role / version','Configuration'],Object.entries(run.models).map(([k,v])=>[pretty(k),v]),section('Model and contract versions'));}
  for(const revision of run.revisions||[]){const block=section(`Plan iteration ${revision.iteration}`);for(const [id,assessment] of Object.entries(revision.gates)){const details=el('details');details.open=revision.iteration===run.revisions.length;details.append(el('summary',`${id} · ${assessment.passed?'Threshold passed':'Review required'} · minimum ${assessment.acceptance_score.toFixed(3)}`));table(['Dimension','Raw score','Gate'],Object.entries(assessment.dimensions).map(([name,value])=>[pretty(name),value.toFixed(3),el('span',value>=assessment.threshold?'Pass':'Review',value>=assessment.threshold?'status-pass':'status-review')]),details);block.append(details);}}
  for(const [id,output] of Object.entries(run.outputs||{})){const block=section(`Output ${id}`);if(output.gate.dimensions)table(['Check','Raw score'],Object.entries(output.gate.dimensions).map(([k,v])=>[pretty(k),v.toFixed(3)]),block);else block.append(el('p',output.gate.method,'helper'));}
  if(run.final_gate){table(['Final report check','Raw score'],Object.entries(run.final_gate.dimensions).map(([k,v])=>[pretty(k),v.toFixed(3)]),section('Final report verification'));}
  section('Evaluation status').append(el('p','This release does not apply a learned calibration profile. Human review notes and raw decision events can support a later held-out evaluation; they do not automatically certify calibration.','helper'));
}
function renderActivity(){
  const block=section('Run activity');block.append(el('p','Execution events and bounded decisions, not hidden model reasoning. Provider usage is recorded when returned; MiroShark’s internal simulation-model spend is not included in these token totals.','helper'));
  for(const event of state.run.events?.items||[]){const row=el('div','','event'),detail=el('div');row.append(el('time',new Date(event.time).toLocaleTimeString()));detail.append(el('strong',pretty(event.kind)));if(event.data.message)detail.append(el('p',event.data.message));const more=el('details');more.append(el('summary','Event data'),el('pre',JSON.stringify(event.data,null,2),'json-detail'));detail.append(more);row.append(detail);block.append(row);}
  if(state.run.events?.truncated)block.append(el('p',`Showing the most recent 200 of ${state.run.events.total} events. JSON export includes up to 10,000.`,'helper'));
}
$('approve').onclick=async()=>{const run=state.run;$('approve').disabled=true;try{await post(`/api/runs/${run.id}/approve`,{plan_hash:run.plan_hash});await openRun(run.id);}catch(e){notify(e.message,true);}finally{$('approve').disabled=false;}};
$('cancel').onclick=async()=>{try{const run=await post(`/api/runs/${state.run.id}/cancel`);stopPolling();state.run={...state.run,...run};renderRun();await history();}catch(e){notify(e.message,true);}};
$('revise').onclick=()=>{const input=state.run.input;$('question').value=input.question;$('context').value=input.context;$('constraints').value=input.constraints;$('mode').value='none';$('authorize-simulation').checked=false;state.evidence=structuredClone(input.evidence);evidenceList();$('mode').onchange();showComposer();notify('Revise the question or evidence and create a new analysis. The previous run remains unchanged.');};
async function download(format){try{const response=await fetch(`/api/runs/${state.run.id}/export?format=${format}`,{headers:{Authorization:`Bearer ${state.token}`}});if(!response.ok)throw new Error('Export failed; unlock or reload the run and try again.');const url=URL.createObjectURL(await response.blob()),a=el('a');a.href=url;a.download=`${state.run.id}.${format}`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(e){notify(e.message,true);}}
$('download-md').onclick=()=>download('md');$('download-json').onclick=()=>download('json');
async function review(verdict){try{const saved=await post(`/api/runs/${state.run.id}/review`,{verdict,note:$('review-note').value});state.run={...state.run,...saved};$('review-result').textContent=`Saved: ${pretty(verdict)}`;notify('Your review was saved separately from the model scores.');}catch(e){notify(e.message,true);}}
$('review-useful').onclick=()=>review('useful');$('review-revise').onclick=()=>review('needs_revision');
window.addEventListener('beforeunload',()=>clearTimeout(state.timer));
