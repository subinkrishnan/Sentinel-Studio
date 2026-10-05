document.querySelector('#login').onsubmit=async e=>{
 e.preventDefault();const input=document.querySelector('#token'),button=e.target.querySelector('button'),error=document.querySelector('#error');button.disabled=true;error.textContent='';
 try{const r=await fetch('/api/session',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({token:input.value})});input.value='';if(r.ok)location.reload();else error.textContent='Sign-in failed';}
 catch(_){input.value='';error.textContent='Service unavailable. Please try again.';}
 finally{button.disabled=false;}
};
