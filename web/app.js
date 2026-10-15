/* Same-origin API only. This file deliberately contains no keys or synthetic fallbacks. */
const $ = (s) => document.querySelector(s);
const escapeHTML = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let plans = [];
async function api(path, options = {}) {
  const res = await fetch(path, {credentials:'same-origin', ...options});
  if (res.status === 204) return null;
  const body = await res.json();
  if (!res.ok) throw new Error(typeof body.detail === 'string' ? body.detail : 'Please check the form values and try again.');
  return body;
}
const post = (path, body) => api(path, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
async function withForm(form, message, fn) {
  const button = form.querySelector('button'); button.disabled = true; message.textContent = 'Working…';
  try { await fn(); } catch(e) { message.textContent = e.message || 'Could not reach the server. Check your connection.'; }
  finally { button.disabled = false; }
}
function renderPlan(plan) {
  $('#plan-result').innerHTML = `<span class="badge">${plan.source === 'ollama' ? 'MODEL-ASSISTED' : 'RULE TEMPLATE'}</span><h3>${escapeHTML(plan.title)}</h3><p class="subtle">${escapeHTML(plan.summary)}</p>${plan.blocks.map(b => `<div class="plan-block"><strong>${b.minutes}<small class="subtle"> m</small></strong><div>${escapeHTML(b.title)}<p>${escapeHTML(b.instruction)}</p></div></div>`).join('')}<p class="subtle">${escapeHTML(plan.safety)}</p>${plan.notice ? `<p class="message">${escapeHTML(plan.notice)}</p>` : ''}`;
}
async function refreshPlans(selected) {
  plans = (await api('/api/plans')).items;
  $('#plan-count').textContent = plans.length;
  const old = selected || $('#log-plan').value;
  $('#log-plan').innerHTML = plans.length ? plans.map(p=>`<option value="${p.id}">${escapeHTML(p.title)} · ${escapeHTML(p.created_at.slice(0,10))}</option>`).join('') : '<option value="">Create a plan first</option>';
  if (plans.some(p=>p.id===old)) $('#log-plan').value = old;
  $('#plan-history').innerHTML = plans.map(p=>`<div class="entry"><strong>${escapeHTML(p.title)}</strong> · ${escapeHTML(p.profile.level)}<p>${escapeHTML(p.profile.goal)}</p><button data-plan="${p.id}">View plan</button></div>`).join('');
  if (plans.length) renderPlan(plans.find(p=>p.id===selected) || plans[0]);
}
$('#plan-history').addEventListener('click',e=>{const id=e.target.dataset.plan;if(id)renderPlan(plans.find(p=>p.id===id));});
$('#minutes').addEventListener('input',e=>$('#minutes-label').textContent=`${e.target.value} min`);
$('#plan-form').addEventListener('submit',e=>{e.preventDefault();withForm(e.target,$('#plan-message'),async()=>{const p=Object.fromEntries(new FormData(e.target));p.minutes=Number(p.minutes);const plan=await post('/api/plans',p);await refreshPlans(plan.id);$('#plan-message').textContent='Saved to your notebook.';});});
async function refreshLogs(){const d=await api('/api/logs');$('#sessions').textContent=d.sessions;$('#total-minutes').textContent=d.total_minutes;$('#logs').innerHTML=d.items.length?d.items.map(x=>`<article class="entry"><strong>${escapeHTML(x.date)} · ${x.minutes} min · effort ${x.effort}/10</strong><p>${escapeHTML(x.note||'No note added.')}</p></article>`).join(''):'<p class="subtle">No sessions yet.</p>';}
const today=new Date();today.setMinutes(today.getMinutes()-today.getTimezoneOffset());$('#log-form [name=date]').value=today.toISOString().slice(0,10);
$('#log-form').addEventListener('submit',e=>{e.preventDefault();withForm(e.target,$('#log-message'),async()=>{const b=Object.fromEntries(new FormData(e.target));b.minutes=Number(b.minutes);b.effort=Number(b.effort);await post('/api/logs',b);await refreshLogs();$('#log-message').textContent='Reflection saved.';});});
async function refreshVideos(){const d=await api('/api/videos');$('#videos').innerHTML=d.items.length?d.items.map(v=>`<article class="entry"><strong>${escapeHTML(v.filename)}</strong><p>${(v.bytes/1024/1024).toFixed(2)} MB · ${escapeHTML(v.created_at.slice(0,10))}</p><button data-inspect="${v.id}">Inspect file</button><button data-delete="${v.id}" class="secondary">Delete</button><p id="clip-${v.id}" role="status"></p></article>`).join(''):'<p class="subtle">No clips uploaded yet.</p>';}
$('#video-form').addEventListener('submit',e=>{e.preventDefault();withForm(e.target,$('#video-message'),async()=>{const f=e.target.video.files[0];if(!f)throw new Error('Choose a video first.');if(f.size>30*1024*1024)throw new Error('Maximum file size is 30 MB.');await api('/api/videos?filename='+encodeURIComponent(f.name),{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:f});await refreshVideos();$('#video-message').textContent='Uploaded. Use Inspect file to check metadata.';e.target.reset();});});
$('#videos').addEventListener('click',async e=>{const id=e.target.dataset.inspect||e.target.dataset.delete;if(!id)return;e.target.disabled=true;const status=$(`#clip-${id}`);status.textContent='Working…';try{if(e.target.dataset.delete){await api('/api/videos/'+id,{method:'DELETE'});await refreshVideos();}else{const v=await api('/api/videos/'+id+'/inspect',{method:'POST'});status.textContent=`${v.width} × ${v.height} · ${v.fps} fps · ${v.duration_seconds} sec. ${v.notice}`;}}catch(err){status.textContent=err.message;}finally{e.target.disabled=false;}});
function renderSEO(d){const demo=d.source==='synthetic-demo';$('#seo-message').textContent=demo?'SYNTHETIC SAMPLE — these are not real site results.':'Analysis of your imported file. No Google account connected.';$('#seo-results').innerHTML=`<div class="metrics"><div><strong>${d.clicks}</strong><span>CLICKS</span></div><div><strong>${d.impressions}</strong><span>IMPRESSIONS</span></div><div><strong>${(d.ctr*100).toFixed(2)}%</strong><span>CTR</span></div></div><p class="subtle">${escapeHTML(d.method)}</p><div class="table-wrap"><table><thead><tr><th>QUERY</th><th>CLICKS</th><th>IMPRESSIONS</th><th>CTR</th><th>POSITION</th><th>NEXT STEP</th></tr></thead><tbody>${d.queries.slice(0,100).map(q=>`<tr><td>${escapeHTML(q.query)}${q.opportunity?'<br><span class="badge">REVIEW FIRST</span>':''}</td><td>${q.clicks}</td><td>${q.impressions}</td><td>${(q.ctr*100).toFixed(2)}%</td><td>${q.position??'—'}</td><td>${escapeHTML(q.action)}</td></tr>`).join('')}</tbody></table></div><p class="subtle">${escapeHTML(d.limitation)} Displaying up to 100 queries.</p>`;}
$('#sample-seo').addEventListener('click',async e=>{e.target.disabled=true;try{renderSEO(await api('/api/seo/sample'));}catch(err){$('#seo-message').textContent=err.message;}finally{e.target.disabled=false;}});
$('#gsc-file').addEventListener('change',async e=>{const f=e.target.files[0];if(!f)return;$('#seo-results').replaceChildren();try{if(f.size>2000000)throw new Error('CSV must be under 2 MB.');renderSEO(await post('/api/seo/analyze',{csv:await f.text()}));}catch(err){$('#seo-message').textContent=err.message;}});
async function boot(){try{const h=await api('/api/health');$('#connection').textContent='● Notebook connected · '+(h.plan_engine==='rules'?'rule templates':'language model configured');await Promise.all([refreshPlans(),refreshLogs(),refreshVideos()]);}catch(e){$('#connection').textContent='Connection unavailable. Start the Python server and reload.';}}
boot();
