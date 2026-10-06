'use strict';
// Authenticated Studio uses the configured Mart. Static demos keep their fixtures.
(() => {
  const active=document.body.dataset.runnerSession==='true';
  let snapshot={status:'LOADING',data:null}, pending=false;
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const number=v=>new Intl.NumberFormat('en-GB').format(v);
  const date=v=>new Intl.DateTimeFormat('en-GB',{dateStyle:'medium',timeStyle:'short',timeZone:'UTC'}).format(new Date(v))+' UTC';
  const table=(heads,rows)=>`<div class="panel table-wrap"><table><thead><tr>${heads.map(v=>`<th>${escape(v)}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${escape(v)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  function trendChart(rows){
    if(!rows.length)return '';
    const maximum=Math.max(1,...rows.map(r=>r.high_risk)), x=i=>55+i*850/Math.max(1,rows.length-1), y=v=>190-v/maximum*150;
    const labels=rows.filter((_,i)=>i===0||i===rows.length-1);
    return `<div class="panel chart-panel"><svg class="trend" viewBox="0 0 960 240" role="img" aria-label="High-risk subscriber counts across ${rows.length} published runs"><path class="grid" d="M55 40H905 M55 115H905 M55 190H905"/><text x="45" y="45" text-anchor="end">${number(maximum)}</text><text x="45" y="195" text-anchor="end">0</text><polyline class="line" points="${rows.map((r,i)=>`${x(i)},${y(r.high_risk)}`).join(' ')}"/>${rows.map((r,i)=>`<circle class="dot" cx="${x(i)}" cy="${y(r.high_risk)}" r="4"><title>${escape(date(r.as_of))}: ${number(r.high_risk)} high risk</title></circle>`).join('')}${labels.map(r=>`<text x="${x(rows.indexOf(r))}" y="222" text-anchor="${rows.indexOf(r)===0?'start':'end'}">${escape(date(r.as_of))}</text>`).join('')}</svg></div>`;
  }
  function render(){
    if(!active)return;
    const page=location.hash.startsWith('#reports')?'reports':location.hash.startsWith('#decisions')?'decisions':'brief';
    document.querySelectorAll('[data-page]').forEach(a=>a.classList.toggle('active',a.dataset.page===page));
    document.title=`${page==='brief'?'Executive Brief':page==='reports'?'Reports':'My Decisions'} · Sentinel Studio`;
    const badge=document.querySelector('.synthetic');badge.textContent=snapshot.synthetic?'SYNTHETIC DEV MART':snapshot.mode==='canonical'?'CANONICAL MART':'MART WORKSPACE';badge.title='Results come from the configured Mart; training and publication have separate gates.';
    document.querySelector('.pulse-header h2').textContent='Ask Pulse';
    document.querySelector('#pulse-context').textContent='Engine connection pending';
    document.querySelector('#pulse-questions').innerHTML='';
    document.querySelector('#pulse-input').disabled=true;
    document.querySelector('.pulse-compose button').disabled=true;
    document.querySelector('.pulse-compose p').textContent='Pulse engine integration is pending.';
    document.querySelector('#pulse-conversation').textContent='Mart results appear in the workspace when available. Ask Pulse is not connected to the Dev engine yet.';
    const heading=page==='brief'?'Executive Brief':page==='reports'?'Reports':'My Decisions';
    let html=`<h1>${heading}</h1><p class="page-sub">COM01 · ${escape(snapshot.business_line||'Postpaid')} · Configured Mart results</p><div class="toolbar"><span>${escape(snapshot.status)}</span><button class="button" data-mart-refresh ${pending?'disabled':''}>Refresh Mart</button></div>`;
    if(page==='decisions')html+='<section class="panel empty"><h2>Decision workflow pending</h2><p>Live campaign recommendations and approvals are not connected.</p></section>';
    else if(!snapshot.data)html+=`<section class="panel empty"><h2>${snapshot.status==='LOADING'?'Loading Mart status':'No Mart results available'}</h2><p>${escape(snapshot.reason||'Waiting for the configured Mart connection.')}</p><p>Bronze upload, Silver validation and model scoring must finish before published results appear.</p></section>`;
    else {
      const {run,trend,segments,reasons}=snapshot.data;
      if(snapshot.fallback)html+='<div class="fallback">The latest attempt is not eligible for display. Showing the last complete PASS/PUBLISHED run.</div>';
      html+=`<p class="section-sub">${escape(run.run_id)} · ${escape(date(run.as_of))} · Model ${escape(run.model_version)}</p>`;
      if(page==='brief'){
        const stats=[['Subscribers scored',number(run.scored)],['High-risk subscribers',number(run.high_risk)],['High-risk share',(100*run.high_risk/run.scored).toFixed(2)+'%'],['Mean churn probability',(100*run.mean_probability).toFixed(2)+'%']];
        html+=`<div class="kpis">${stats.map(([label,value])=>`<div class="kpi"><div class="label">${escape(label)}</div><div class="value">${escape(value)}</div></div>`).join('')}</div><section class="section"><h2>High-risk trend</h2><p class="section-sub">Last ${trend.length} complete published runs</p>${trendChart(trend)}</section><section class="section"><h2>Risk bands</h2>${table(['Band','Subscribers'],[['High',number(run.high_risk)],['Medium',number(run.medium_risk)],['Low',number(run.low_risk)]])}</section><section class="section"><h2>Risk by segment</h2>${table(['Segment','Scored','High risk'],segments.map(s=>[s.name,number(s.scored),number(s.high_risk)]))}</section><section class="section"><h2>Recorded reasons among high-risk subscribers</h2>${table(['Reason','Subscribers'],reasons.map(r=>[r.name,number(r.subscribers)]))}</section>`;
      }else html+=`<h2>Published scoring history</h2>${table(['Run','Data as of','Scored','High risk'],trend.map(r=>[r.run_id,date(r.as_of),number(r.scored),number(r.high_risk)]))}`;
      html+='<p class="metric-note">Predicted risk is not observed churn. Retention outcomes, revenue and causal uplift are not supplied by this connection.</p>';
    }
    document.querySelector('#main').innerHTML=html;
    window.SENTINEL_PULSE?.render(snapshot);
  }
  async function refresh(){
    if(!active||pending)return;
    pending=true;render();
    try{
      const response=await fetch('/api/mart/summary',{credentials:'same-origin'});
      if(!response.ok)throw Error('Mart service unavailable. Sign in again if the Studio session expired.');
      const next=await response.json();
      if(!next.status)throw Error('Unexpected Mart response');
      snapshot=next;
    }catch(error){snapshot={status:'BLOCKED',reason:error.message,data:null};}
    finally{pending=false;render();}
  }
  window.SENTINEL_MART={active,render,refresh};
  if(active){
    document.addEventListener('click',e=>{if(e.target.closest('[data-mart-refresh]'))refresh();});
    document.addEventListener('DOMContentLoaded',refresh,{once:true});
  }
})();
