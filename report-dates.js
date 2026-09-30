// Report dates are inclusive. Weekly fixtures use complete Monday–Sunday weeks.
function hasReportDates(){return Boolean(state.reportFrom||state.reportTo);}
function overlapsReportDates(start,end){return (!state.reportFrom||end>=state.reportFrom)&&(!state.reportTo||start<=state.reportTo);}
function reportWeek(timestamp){
 const day=new Date(timestamp.slice(0,10)+'T12:00:00Z');
 day.setUTCDate(day.getUTCDate()-(day.getUTCDay()+6)%7);
 const start=day.toISOString().slice(0,10);day.setUTCDate(day.getUTCDate()+6);
 return {start,end:day.toISOString().slice(0,10)};
}
function reportDateLabel(value){return new Intl.DateTimeFormat('en-GB',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(value+'T12:00:00Z'));}
function reportPeriodLabel(start,end){return `${reportDateLabel(start)} – ${reportDateLabel(end)}`;}
function reportRuns(){return published.filter(r=>{const w=reportWeek(r.scoredAtTs);return overlapsReportDates(w.start,w.end);});}
function reportSnapshot(){return hasReportDates()?reportRuns().at(-1):run;}
function reportCampaigns(){return campaigns.filter(c=>overlapsReportDates(c.reportDate,c.reportDate));}
function reportDateControls(){return `<form id="report-date-form" class="report-dates"><label class="field" for="report-from">From date<input type="date" id="report-from" value="${esc(state.reportFrom||'')}" aria-describedby="report-date-error"></label><label class="field" for="report-to">To date<input type="date" id="report-to" value="${esc(state.reportTo||'')}" aria-describedby="report-date-error"></label><button type="submit" class="button primary">Apply</button><button type="button" class="button" data-clear-dates>Clear dates</button><p id="report-date-error" class="report-date-error" role="alert" hidden></p></form>`;}
function reportRangeNote(){if(!hasReportDates())return '';return `<p class="report-range-note">Selected period: ${state.reportFrom?esc(reportDateLabel(state.reportFrom)):'Any start date'} to ${state.reportTo?esc(reportDateLabel(state.reportTo)):'Latest available date'}. ${state.report==='campaigns'?'Campaigns use their latest activity date.':'Weekly figures include complete weeks that overlap this range.'}</p>`;}
function reportNoData(){return `<div class="panel empty"><h2>No data available for this period</h2><p>Choose another date range or clear dates to return to the default report.</p></div>`;}
function reportSnapshotNote(){const r=reportSnapshot();if(!r)return '';const w=reportWeek(r.scoredAtTs);return `Snapshot: ${date(r.dataAsOfTs)}${hasReportDates()?` · Full week: ${reportPeriodLabel(w.start,w.end)}`:''}`;}
function reportObservation(){if(state.report==='campaigns')return 'Campaign approval and delivery are separate steps. This prototype records review actions, with execution, spend and uplift left unmeasured.';const r=reportSnapshot();if(!r)return '';const h=r.predictions.filter(p=>p.riskBand==='HIGH');return `The ${hasReportDates()?'latest published run in this period':'latest published run'} has ${h.length} high-risk subscribers out of ${r.predictions.length} scored. Segment and subscriber reports use this snapshot.`;}
function reportPulseAnswer(){const data=reportData();if(state.line!=='Prepaid')return `${state.line} is not configured in this demo.`;if(!data.rows.length)return 'No data is available for the selected period. Choose another range or clear dates.';return `${reportNames[state.report]} shows ${data.rows.length} ${state.report==='churn'?'published weekly snapshots':state.report==='campaigns'?'campaigns':'records'}. ${state.report==='campaigns'?'Campaigns are filtered by their latest activity date.':reportSnapshotNote()+'.'} ${hasReportDates()?'The applied date range is reflected in the report and Excel download.':'No date filter is applied.'}`;}
document.addEventListener('submit',event=>{
 if(event.target.id!=='report-date-form')return;
 event.preventDefault();const from=document.getElementById('report-from').value,to=document.getElementById('report-to').value,error=document.getElementById('report-date-error');
 if(from&&to&&from>to){error.textContent='From date must be on or before To date.';error.hidden=false;return;}
 state.reportFrom=from;state.reportTo=to;render();
});
document.addEventListener('click',event=>{if(event.target.closest('[data-clear-dates]')){state.reportFrom='';state.reportTo='';render();}});
