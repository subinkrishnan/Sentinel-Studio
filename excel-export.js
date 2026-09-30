// Standard XLSX exports, using the vendored SheetJS Community Edition 0.20.3.
function createReportWorkbook(){
 const data=reportData();
 if(state.line!=='Prepaid'||!data.rows.length)throw new Error('No report data for the selected period');
 const workbook=XLSX.utils.book_new();
 const sheet=XLSX.utils.aoa_to_sheet([data.headers,...data.rows]);
 data.rows.forEach((row,rowIndex)=>row.forEach((value,columnIndex)=>{
  if(typeof value!=='string')return;
  const address=XLSX.utils.encode_cell({r:rowIndex+1,c:columnIndex});
  if(/^[+-]?\d+(?:\.\d+)?%$/.test(value)){
   const signed=/^(WoW|MoM)$/.test(data.headers[columnIndex]);
   sheet[address]={t:'n',v:Number(value.slice(0,-1))/100,z:signed?'+0.0%;-0.0%;0.0%':'0.0%'};
  }else if(/^-?\d+(?:,\d{3})*(?:\.\d+)?$/.test(value)){
   sheet[address]={t:'n',v:Number(value.replace(/,/g,'')),z:value.includes('.')?'#,##0.0':'#,##0'};
  }
 }));
 sheet['!cols']=data.headers.map((header,i)=>({wch:Math.min(65,Math.max(14,String(header).length+2,...data.rows.map(row=>String(row[i]??'').length+2)))}));
 sheet['!autofilter']={ref:sheet['!ref']};
 XLSX.utils.book_append_sheet(workbook,sheet,'Report');
 const business=state.report==='business';
 const snapshot=business?null:reportSnapshot();
 const metadata=[['Field','Value'],['Report',reportNames[state.report]],['Operator','Atoma'],['Business line',state.line],['Data','Synthetic demonstration'],['Data as of',business?BUSINESS_REPORT.dataAsOf:state.report==='campaigns'?'Campaign activity dates':snapshot?.dataAsOfTs||'No matching snapshot'],['Source snapshot',business?BUSINESS_REPORT.id:state.report==='campaigns'?'Simulated campaign records':snapshot?.scoringRunId||'No matching snapshot'],['Source',business?'Standalone business dataset':'Published COM01 fixture']];
 metadata.push(['From date',state.reportFrom||'Default view'],['To date',state.reportTo||'Default view'],['Period basis',state.report==='campaigns'?'Latest campaign activity date':'Full overlapping Monday–Sunday weeks']);
 if(!business&&state.report!=='campaigns')metadata.push(['Included snapshot weeks',reportRuns().map(r=>{const w=reportWeek(r.scoredAtTs);return reportPeriodLabel(w.start,w.end)}).join('; ')]);
 if(business)metadata.push(['WoW','Latest displayed week compared with its previous calendar week; may be outside selected range'],['MoM',hasReportDates()?'Unavailable for a custom weekly range':'Equivalent month-to-date periods; base metrics compare with prior month-end snapshot'],['Trend',biTrendLabel()],['Displayed weeks',biPeriodLabel()]);
 const notes=XLSX.utils.aoa_to_sheet(metadata);notes['!cols']=[{wch:20},{wch:95}];
 XLSX.utils.book_append_sheet(workbook,notes,'Report details');
 workbook.Props={Title:reportNames[state.report],Author:'Sentinel Studio',Subject:'Synthetic client demonstration'};
 return workbook;
}
function downloadReportXlsx(){
 try{
  const bytes=XLSX.write(createReportWorkbook(),{bookType:'xlsx',type:'array',compression:true});
  const url=URL.createObjectURL(new Blob([bytes],{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}));
  const link=document.createElement('a');link.href=url;link.download=`sentinel-${state.report}-report.xlsx`;
  document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }catch(error){
  $('#notice').textContent='The Excel download could not be created. Refresh the page and try again.';$('#notice').hidden=false;
 }
}
