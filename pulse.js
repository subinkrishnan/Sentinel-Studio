'use strict';
(() => {
  const active=document.body.dataset.runnerSession==='true';
  let connection={status:'LOADING'},view=null,busy=false,checking=false,lastAnswer=null;
  const node=s=>document.querySelector(s);
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const contextKey=data=>data?.data?.run?JSON.stringify([data.mode,data.data.run.run_id,data.data.run.as_of]):null;
  function render(next){
    if(!active)return;
    if(contextKey(next)!==contextKey(view))lastAnswer=null;
    view=next;
    const ready=connection.status==='READY'&&view?.status==='CONNECTED';
    node('.pulse-header h2').textContent='Ask Pulse';
    node('#pulse-context').textContent=busy?'Answering…':connection.status==='READY'?(ready?'Connected to Sentinel Assistant':'Waiting for published Mart'):connection.status;
    node('#pulse-input').disabled=!ready||busy;
    node('.pulse-compose button').disabled=!ready||busy;
    node('.pulse-compose p').textContent='Engine-governed answers · Actions reviewed in Dev';
    node('#pulse-questions').innerHTML=`<button class="question" data-pulse-connect ${checking||busy?'disabled':''}>Verify Pulse connection</button><button class="question" data-pulse-reset ${busy?'disabled':''}>New chat</button>`+(ready?['How many subscribers are high risk?','Summarise the published scoring run.','What are the main recorded reasons?'].map(q=>`<button class="question" data-pulse-question="${escape(q)}" ${busy?'disabled':''}>${escape(q)}</button>`).join(''):'');
    if(lastAnswer){
      node('#pulse-conversation').innerHTML=`<div class="conversation"><p class="asked">${escape(lastAnswer.question)}</p><p class="pulse-answer">${escape(lastAnswer.answer).replace(/\n/g,'<br>')}</p>${lastAnswer.tool_steps?.length?`<details><summary>Engine tool activity</summary>${lastAnswer.tool_steps.map(t=>`<p>${escape(t.name)} · ${escape(t.summary)}</p>`).join('')}</details>`:''}<p class="source">${escape(lastAnswer.context?.relation||'Assistant')} · ${escape(lastAnswer.context?.scoring_run_id||'')}</p></div>`;
    }else node('#pulse-conversation').textContent=busy?'Waiting for the engine answer…':!ready?(connection.reason||'Waiting for the Assistant connection and published Mart results.'):'Ask about the displayed published run. Context guides the engine; your Sentinel permissions govern its access.';
  }
  async function request(path,body){
    const response=await fetch(path,body?{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{credentials:'same-origin'});
    const data=await response.json();
    if(!response.ok)throw Error(data.error||'Pulse request failed');
    return data;
  }
  async function connect(){
    if(!active||checking||busy)return;
    checking=true;render(view);
    try{connection=await request('/api/pulse/status');}
    catch(error){connection={status:'BLOCKED',reason:error.message};}
    finally{checking=false;render(view);}
  }
  async function ask(question){
    if(busy||connection.status!=='READY'||view?.status!=='CONNECTED')return;
    if(!question.trim()||question.length>4000){node('#pulse-conversation').textContent='Enter a question of 1 to 4,000 characters.';return;}
    const requestedContext=contextKey(view);busy=true;lastAnswer=null;render(view);
    try{
      const result=await request('/api/pulse/ask',{question,run:view.data.run.run_id});
      if(contextKey(view)===requestedContext)lastAnswer={question,...result};
    }catch(error){lastAnswer={question,answer:error.message,tool_steps:[]};}
    finally{busy=false;render(view);}
  }
  window.SENTINEL_PULSE={render,connect};
  if(active){
    node('#pulse-input').maxLength=4000;
    document.addEventListener('DOMContentLoaded',connect,{once:true});
    node('#pulse-form').addEventListener('submit',event=>{event.preventDefault();const question=node('#pulse-input').value;node('#pulse-input').value='';ask(question);});
    document.addEventListener('click',async event=>{
      if(event.target.closest('[data-pulse-connect]'))connect();
      const question=event.target.closest('[data-pulse-question]');if(question)ask(question.dataset.pulseQuestion);
      if(event.target.closest('[data-pulse-reset]')&&!busy){try{await request('/api/pulse/reset',{});lastAnswer=null;render(view);}catch(error){node('#pulse-conversation').textContent=error.message;}}
    });
  }
})();
