'use strict';
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../mart.js'),'utf8');
function setup(active=true){
 const elements=new Map(),listeners=new Map();let response={status:'NOT_CONFIGURED',reason:'Waiting for Mart',data:null},calls=0;
 const node=selector=>{if(!elements.has(selector))elements.set(selector,{textContent:'',innerHTML:'',disabled:false,classList:{toggle(){}}});return elements.get(selector);};
 const document={body:{dataset:{runnerSession:String(active)}},querySelector:node,querySelectorAll:()=>[],addEventListener:(name,fn)=>listeners.set(name,fn)};
 const context={document,window:{},location:{hash:'#brief'},Intl,Date,fetch:async()=>{calls++;return {ok:true,json:async()=>response};}};
 vm.runInNewContext(source,context);
 return {api:context.window.SENTINEL_MART,node,set:data=>response=data,calls:()=>calls,context};
}
(async()=>{
 let test=setup(false);await test.api.refresh();assert.equal(test.calls(),0);
 test=setup();await test.api.refresh();assert.match(test.node('#main').innerHTML,/No Mart results/);assert.doesNotMatch(test.node('#main').innerHTML,/Saved by Sentinel|53.8%/);
 test.set({status:'CONNECTED',synthetic:true,business_line:'Postpaid',fallback:true,data:{run:{run_id:'real-run',as_of:'2026-07-02T00:00:00Z',model_version:'v0.5.0',scored:200,high_risk:20,medium_risk:30,low_risk:150,mean_probability:.15},trend:[{run_id:'real-run',as_of:'2026-07-02T00:00:00Z',scored:200,high_risk:20}],segments:[{name:'<img src=x onerror=alert(1)>',scored:200,high_risk:20}],reasons:[]}});
 await test.api.refresh();let html=test.node('#main').innerHTML;
 assert.match(html,/10.00%/);assert.match(html,/last complete PASS\/PUBLISHED/);assert.match(html,/&lt;img/);assert.doesNotMatch(html,/<img src=x/);assert.equal(test.node('#pulse-input').disabled,true);
 test.context.location.hash='#reports';test.api.render();assert.match(test.node('#main').innerHTML,/Published scoring history/);
 test.set({status:'BLOCKED',reason:'Read failed',data:null});await test.api.refresh();assert.doesNotMatch(test.node('#main').innerHTML,/real-run|10.00%/);
 console.log('Mart UI checks PASS: static isolation, pending state, live metrics, fallback, escaped labels, Pulse disabled, reports and stale-result clearing.');
})().catch(e=>{console.error(e);process.exitCode=1;});
