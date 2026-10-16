(() => {
  const params=new URLSearchParams(location.hash.slice(1));
  const token=params.get('token')||sessionStorage.getItem('seller-link-token');
  if(token){sessionStorage.setItem('seller-link-token',token);history.replaceState(null,'',location.pathname);}
  const form=document.getElementById('approve-form'),feedback=document.getElementById('link-feedback');
  const show=text=>{feedback.hidden=false;feedback.textContent=text;};
  if(!token){show('Open the link generated in your own Mini Program session.');if(form)form.hidden=true;return;}
  if(form)form.addEventListener('submit',async e=>{e.preventDefault();const button=e.submitter;button.disabled=true;
    try{const name=document.body.dataset.csrfCookie;const csrf=document.cookie.split('; ').find(c=>c.startsWith(name+'='))?.slice(name.length+1)||'';
      const r=await fetch('/api/seller-agent/v1/link/approve/',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRFToken':decodeURIComponent(csrf)},body:JSON.stringify({token,confirmed:document.getElementById('approve-check').checked,verification_code:document.getElementById('verification-code').value.trim()})});
      const data=await r.json();if(!r.ok)throw new Error(typeof data.detail==='string'?data.detail:JSON.stringify(data));
      sessionStorage.removeItem('seller-link-token');form.hidden=true;show('Linked to '+data.account+'. Return to your Mini Program and select Refresh.');
    }catch(err){show(err.message);}finally{button.disabled=false;}
  });
})();
