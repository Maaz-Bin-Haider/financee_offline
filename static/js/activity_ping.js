/* Browser-created exports are self-reported; server receipts bind source/session. */
(function(root,factory){
  const api=factory(root);
  if(typeof module!=="undefined"&&module.exports) module.exports=api;
  if(root) root.FinanceeActivity=api;
  if(root&&root.document) api.start(root.document);
})(typeof globalThis!=="undefined"?globalThis:this,function(root){
  "use strict";
  let token="",config=null,stale=false;
  function csrf(doc){
    for(const pair of String(doc&&doc.cookie||"").split(";")){
      const parts=pair.trim().split("=");if(parts.shift()==="csrftoken")return decodeURIComponent(parts.join("="));
    }return "";
  }
  function exported(format,title,options){
    const o=options||{},kind=String(format||"").toLowerCase();
    const receipt=o.token||token;
    if(!["pdf","csv","xlsx"].includes(kind)||!receipt||stale||(!o.token&&(!config||!config.recording)))return false;
    try{
      const send=o.fetch||root.fetch;
      if(typeof send!=="function")return false;
      const done=send.call(root,"/activity/record/",{method:"POST",credentials:"same-origin",keepalive:true,
        headers:{"Content-Type":"application/json","X-CSRFToken":csrf(o.document||root.document)},
        body:JSON.stringify({format:kind,token:receipt})});
      if(done&&done.catch)done.catch(()=>{});
      return true;
    }catch(_){return false;}
  }
  function invalidate(){
    if(stale)return;stale=true;token="";
    if(root.dispatchEvent)root.dispatchEvent(new root.CustomEvent("financee:activity-session-changed"));
  }
  function observe(response){
    if(!response||!response.headers)return;
    const scope=response.headers.get("X-Activity-Scope");
    if(config&&scope&&scope!==config.scope){invalidate();return;}
    if(config&&response.redirected&&/\/authentication\/login\//.test(response.url||"")){invalidate();return;}
    const receipt=response.headers.get("X-Activity-Export");
    if(!stale&&receipt)token=receipt;
  }
  function start(doc){
    const node=doc.getElementById("activity-config");if(!node)return;
    try{config=JSON.parse(node.textContent);}catch(_){return;}
    token=config.token||"";
    const key="financee.activity.session";
    try{root.localStorage.setItem(key,config.scope);}catch(_){}
    root.addEventListener("storage",e=>{if(e.key===key&&e.newValue!==config.scope)invalidate();});
    doc.addEventListener("visibilitychange",()=>{if(!doc.hidden){try{if(root.localStorage.getItem(key)!==config.scope)invalidate();}catch(_){}}});
    const original=root.fetch;
    if(typeof original==="function")root.fetch=function(){return original.apply(this,arguments).then(r=>{observe(r);return r;});};
    doc.addEventListener("DOMContentLoaded",()=>{
      if(root.jQuery)root.jQuery(doc).ajaxComplete((_,xhr)=>observe({headers:{get:name=>xhr.getResponseHeader(name)}}));
    });
    doc.addEventListener("click",e=>{
      if(e.target.closest&&e.target.closest('a[href*="/authentication/logout/"]')){
        try{root.localStorage.removeItem(key);}catch(_){}invalidate();
      }
    });
  }
  return {exported,csrf,start,observe};
});
