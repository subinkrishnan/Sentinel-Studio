'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../pulse.js'),'utf8');
function setup(active=true){
 const nodes=new Map(),listeners=new Map();let calls=[];
 const node=s=>{if(!nodes.has(s))nodes.set(s,{value:'',textContent:'',innerHTML:'',disabled:false,addEventListener:(event,fn)=>listeners.set(s+':'+event,fn)});return nodes.get(s);};
 const document={body:{dataset:{runnerSession:String(active)}},querySelector:node,addEventListener:(event,fn)=>listeners.set(event,fn)};
 const fetch=async (url,options)=>{calls.push({url,options});return {ok:true,json:async()=>url==='/api/pulse/status'?{status:'READY'}:{status:'ANSWERED',answer:'<script>untrusted</script>\n20 high risk',tool_steps:[{name:'query',summary:'Mart read'}],context:{relation:'public.mart__test',scoring_run_id:'run-1'}}};};
 const context={document,window:{},fetch,JSON};vm.runInNewContext(source,context);
 return {api:context.window.SENTINEL_PULSE,node,listeners,calls};
}
const view={status:'CONNECTED',mode:'dev_experiment',data:{run:{run_id:'run-1',as_of:'2026-07-02T00:00:00Z'}}};
(async()=>{
 let t=setup(false);await t.api.connect();assert.equal(t.calls.length,0);
 t=setup();t.api.render({status:'NOT_CONFIGURED',data:null});await t.api.connect();assert.equal(t.node('#pulse-input').disabled,true);
 t.api.render(view);assert.equal(t.node('#pulse-input').disabled,false);assert.match(t.node('#pulse-questions').innerHTML,/data-pulse-question/);
 t.node('#pulse-input').value='How many are high risk?';t.listeners.get('#pulse-form:submit')({preventDefault(){}});
 assert.equal(t.node('#pulse-input').disabled,true);
 await new Promise(resolve=>setImmediate(resolve));
 const call=t.calls.find(c=>c.url==='/api/pulse/ask');assert.deepEqual(JSON.parse(call.options.body),{question:'How many are high risk?',run:'run-1'});
 assert.match(t.node('#pulse-conversation').innerHTML,/&lt;script&gt;/);assert.doesNotMatch(t.node('#pulse-conversation').innerHTML,/<script>/);assert.equal(t.node('#pulse-input').disabled,false);
 t.api.render({...view,data:{run:{run_id:'run-2',as_of:'2026-08-02T00:00:00Z'}}});assert.match(t.node('#pulse-conversation').textContent,/Ask about the displayed published run/);
 console.log('Pulse UI checks PASS: static isolation, Mart readiness gate, engine request context, busy state, escaped answer and stale-conversation clearing.');
})().catch(e=>{console.error(e);process.exitCode=1;});
