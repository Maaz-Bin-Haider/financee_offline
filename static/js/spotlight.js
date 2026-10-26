/* Financee Spotlight: bounded server search, revalidated identifiers, no shared data cache. */
(function (root) {
  'use strict';
  function safePath(path) { return typeof path === 'string' && path.startsWith('/') && !path.startsWith('//') && !/[\\\r\n]/.test(path); }
  function remember(list, row) {
    if (!['page','party','item','serial','sale','purchase','payment','receipt','contra','sale_return','purchase_return','draft','draft_return'].includes(row.kind)) return list;
    const token = row.kind + ':' + row.id;
    return [token, ...list.filter(value => value !== token)].slice(0, 10);
  }
  function segments(text, query) {
    text = String(text || '');
    const tokens = String(query || '').toLowerCase().split(/\s+/).filter(Boolean);
    const out = [];
    let start = 0, marked = false;
    for (let i = 0; i < text.length; i++) {
      const hit = tokens.some(token => {
        const index = text.toLowerCase().lastIndexOf(token, i);
        return index >= 0 && index + token.length > i;
      });
      if (hit !== marked) { if (i > start) out.push({text:text.slice(start,i), mark:marked}); start=i; marked=hit; }
    }
    if (start < text.length) out.push({text:text.slice(start), mark:marked});
    return out;
  }
  const core = { safePath, remember, segments };
  if (typeof module !== 'undefined' && module.exports) { module.exports = core; return; }
  const data = document.getElementById('spotlight-config');
  if (!data) return;
  const config = JSON.parse(data.textContent);
  const key = 'financee.spotlight.recents:' + config.storage;
  const sessionKey = 'financee.spotlight.active-session';
  let sessionChanged = false;
  try {root.localStorage.setItem(sessionKey,config.scope);} catch (_) {}
  const layer = document.getElementById('spotlight-layer'), input = document.getElementById('spotlight-query');
  const list = document.getElementById('spotlight-results'), live = document.getElementById('spotlight-live');
  const R = root.FinanceeRecordLink;
  let recent = [], rows = [], active = -1, focusBefore, controller, epoch = 0, timer, groups = [], busy = false;
  let inertBefore = [];
  try { recent = JSON.parse(root.localStorage.getItem(key) || '[]').filter(value => typeof value === 'string').slice(0, 10); } catch (_) {}
  function cancel() { ++epoch; clearTimeout(timer); if (controller) controller.abort(); controller = null; }
  function clearResults() { rows=[]; active=-1; list.replaceChildren(); input.removeAttribute('aria-activedescendant'); }
  function close() {
    cancel(); layer.hidden=true; input.setAttribute('aria-expanded','false');
    document.documentElement.classList.remove('sp-open'); clearResults();
    for (const [element, inert] of inertBefore) element.inert = inert;
    inertBefore=[];
    if (focusBefore && focusBefore.isConnected) focusBefore.focus();
  }
  async function api(endpoint, params, signal) {
    if(sessionChanged)throw new Error('Your session changed. Reload this page.');
    const response = await fetch('/spotlight/' + endpoint + '/?' + new URLSearchParams(params), {
      credentials:'same-origin', cache:'no-store', signal,
      headers:{'X-Requested-With':'XMLHttpRequest','X-Spotlight-Scope':config.scope}
    });
    const body = await response.json();
    if(sessionChanged)throw new Error('Your session changed. Reload this page.');
    if ([401,403,409].includes(response.status)) {
      throw new Error(body.message || 'Search is unavailable. Reload this page.');
    }
    if (!response.ok) throw new Error(body.message || 'Search could not finish. Try again.');
    if (response.headers.get('X-Spotlight-Scope') !== config.scope) throw new Error('Your session changed. Reload this page.');
    return body;
  }
  function element(tag, className, text) {
    const el = document.createElement(tag); el.className=className;
    if (text != null) el.textContent=String(text);
    return el;
  }
  function select(index) {
    if (!rows.length) return;
    active=(index+rows.length)%rows.length;
    rows.forEach((row,i) => row.element.setAttribute('aria-selected', String(i===active)));
    input.setAttribute('aria-activedescendant', rows[active].element.id);
    rows[active].element.scrollIntoView({block:'nearest'});
  }
  function money(value) { return config.currency + ' ' + Number(value).toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}); }
  function render() {
    clearResults();
    for (const group of groups) {
      if (!group.results.length) continue;
      const section=element('div','sp-group'); section.setAttribute('role','group'); section.setAttribute('aria-label',group.title); section.append(element('div','sp-group-title',group.title));
      for (const record of group.results) {
        const row=element('div','sp-row'); row.id='sp-result-'+rows.length;
        row.setAttribute('role','option'); row.setAttribute('aria-selected','false');
        const icon=element('i','sp-icon fa-solid ' + (record.kind==='serial'?'fa-barcode':record.kind==='party'?'fa-user':record.kind==='item'?'fa-box':record.kind==='action'?'fa-bolt':'fa-file'));
        icon.setAttribute('aria-hidden','true'); row.append(icon);
        const text=element('span','sp-text'), label=element('span','sp-label');
        for (const part of segments(record.name,input.value)) label.append(element(part.mark?'mark':'span',part.mark?'sp-mark':'',part.text));
        text.append(label,element('span','sp-meta',record.meta));
        const details=[];
        if (record.bought) details.push('Bought from '+(record.bought.vendor_name||'—')+' · '+money(record.bought.purchase_price));
        if (record.sold && record.sold.customer_name) details.push('Sold to '+record.sold.customer_name+' · '+money(record.sold.sold_price));
        if (record.reserved) details.push('Reserved for '+record.reserved.reserved_for+' · Draft #'+record.reserved.reserved_draft_id);
        if (details.length) text.append(element('span','sp-detail',details.join(' | ')));
        row.append(text);
        let fact=record.state || (record.amount != null ? money(record.amount) : '');
        if(record.balance != null)fact=money(Math.abs(Number(record.balance)))+(Number(record.balance)>0?' receivable':Number(record.balance)<0?' payable':' settled');
        if(record.in_stock != null)fact=record.in_stock+' in stock'+(record.reserved_units!=null?' · '+record.reserved_units+' reserved':'');
        if(fact)row.append(element('span','sp-fact',fact));
        const index=rows.length; rows.push({record,element:row});
        row.addEventListener('pointermove',()=>select(index));
        row.addEventListener('click',()=>activate(record)); section.append(row);
      }
      if (group.next != null) {
        const more=element('div','sp-row sp-more','Show more '+group.title.toLowerCase());
        more.id='sp-result-'+rows.length; more.setAttribute('role','option'); more.setAttribute('aria-selected','false');
        const index=rows.length; rows.push({record:{kind:'more',group:group.key,offset:group.next},element:more});
        more.addEventListener('pointermove',()=>select(index));
        more.addEventListener('click',()=>search(group.key,group.next)); section.append(more);
      }
      list.append(section);
    }
    if (!rows.length) list.append(element('p','sp-empty',input.value.length===1?'Type at least two characters to find records.':'No matches. Try a name, serial or document number.'));
    if (rows.length) select(0);
    live.textContent=rows.length+' results';
  }
  async function search(kind, offset) {
    cancel(); const current=epoch; controller=new AbortController();
    live.textContent='Searching…'; list.setAttribute('aria-busy','true');
    const text=input.value;
    if (!kind) { groups=[]; clearResults(); list.append(element('p','sp-pending','Searching…')); }
    try {
      const body=await api('search',{q:text,kind:kind||'',offset:offset||0,recent:recent.join(',')},controller.signal);
      if (current!==epoch || layer.hidden || input.value!==text) return;
      if (kind) {
        const existing=groups.find(value=>value.key===kind), incoming=body.groups.find(value=>value.key===kind);
        if (existing && incoming) {existing.results.push(...incoming.results); existing.next=incoming.next;}
        else if (existing) existing.next=null;
      } else groups=body.groups;
      render();
      if(kind)input.focus();
    } catch(error) {
      if (error.name==='AbortError' || current!==epoch || layer.hidden) return;
      clearResults(); list.append(element('p','sp-empty',error.message)); live.textContent=error.message;
    } finally {list.setAttribute('aria-busy','false');}
  }
  function open() {
    if(sessionChanged){root.Alerts.notify('Your session changed. Reload this page.');return;}
    if (!layer.hidden) {close();return;}
    focusBefore=document.activeElement;
    inertBefore=Array.from(document.body.children).filter(el=>el!==layer && !['SCRIPT','LINK','STYLE'].includes(el.tagName)).map(el=>[el,el.inert]);
    inertBefore.forEach(([el])=>{el.inert=true;});
    layer.hidden=false; input.value=''; document.documentElement.classList.add('sp-open');
    input.setAttribute('aria-expanded','true'); input.focus(); search();
  }
  async function activate(record) {
    if(record.kind==='more'){search(record.group,record.offset);return;}
    if (busy) return;
    busy=true; const current=epoch;
    try {
      const params={kind:record.kind,id:record.id};
      if (record.kind==='action') {params.action=record.action;params.id=record.id.split(':')[1];}
      const value=await api('resolve',params);
      if(current!==epoch || layer.hidden)return;
      if (!safePath(value.href)) {live.textContent='This serial has no document you can open.';return;}
      recent=remember(recent,record);
      try {root.localStorage.setItem(key,JSON.stringify(recent));} catch (_) {}
      root.location.assign(value.href);
    } catch(error) {if(current!==epoch || layer.hidden)return;clearResults();list.append(element('p','sp-empty',error.message));live.textContent=error.message;}
    finally {busy=false;}
  }
  input.addEventListener('input',()=>{cancel();clearResults();timer=setTimeout(()=>search(),120);});
  document.querySelectorAll('[data-open-spotlight]').forEach(button=>button.addEventListener('click',open));
  document.getElementById('spotlight-close').addEventListener('click',close);
  document.getElementById('spotlight-clear').addEventListener('click',()=>{recent=[];try {root.localStorage.removeItem(key);}catch(_){} search();input.focus();});
  layer.addEventListener('click',event=>{if(event.target===layer)close();});
  document.addEventListener('keydown',event=>{
    const shortcut=(event.metaKey||event.ctrlKey) && event.key.toLowerCase()==='k';
    if (!layer.hidden) {
      event.stopImmediatePropagation();
      if (event.isComposing) return;
      if (shortcut) {event.preventDefault();close();}
      else if (event.key==='Escape') {event.preventDefault();if(input.value){input.value='';search();}else close();}
      else if (event.key==='ArrowDown'||event.key==='ArrowUp') {event.preventDefault();select(active+(event.key==='ArrowDown'?1:-1));}
      else if (event.key==='Enter' && document.activeElement===input) {event.preventDefault();if(rows[active])activate(rows[active].record);}
      else if (event.key==='Tab') {
        const stops=[input,...layer.querySelectorAll('button')].filter(el=>!el.disabled);
        const index=stops.indexOf(document.activeElement);
        event.preventDefault();stops[(index+(event.shiftKey?-1:1)+stops.length)%stops.length].focus();
      }
    } else if (shortcut || (event.key==='/' && !event.ctrlKey && !event.metaKey && !event.altKey &&
               !event.target.closest('input,textarea,select,[contenteditable="true"],[role="textbox"]'))) {
      event.preventDefault();event.stopImmediatePropagation();open();
    }
  },true);
  document.addEventListener('visibilitychange',()=>{if(document.hidden && !layer.hidden)close();});
  root.addEventListener('pagehide',close);
  root.addEventListener('storage',event=>{
    if(event.key===sessionKey && event.newValue!==config.scope){sessionChanged=true;close();}
  });
  document.querySelectorAll('a[href="/authentication/logout/"]').forEach(link=>link.addEventListener('click',()=>{
    try {root.localStorage.removeItem(sessionKey);}catch(_){}
    sessionChanged=true;close();
  }));
  // Consume links after the page's own form initialization, using its existing renderers.
  async function recordLink() {
    const path=root.location.pathname;
    const specs={
      '/sale/sales/':['/sale/get-sale/','sales_invoice_id','renderSaleData'],
      '/purchase/purchasing/':['/purchase/get-purchase/','purchase_invoice_id','renderPurchaseData'],
      '/saleReturn/create-sale-return/':['/saleReturn/get-sale-return/','sales_return_id','renderSaleReturnData'],
      '/purchaseReturn/create-purchase-return/':['/purchaseReturn/get-purchase-return/','purchase_return_id','renderPurchaseReturnData'],
      '/payments/payment/':['/payments/payment/get/','payment_id','populateForm'],
      '/receipts/receipt/':['/receipts/receipt/get/','receipt_id','populateForm'],
      '/contra/contra/':['/contra/contra/get/','contra_id','populateForm']
    };
    const names=['party','item','sp_action','serial'];
    if (specs[path]) names.push('open'); // Drafts already consume their own ?open=.
    const params=R.take(names);
    try {
      if (params.open) {
        const id=R.number(params.open); if(!id)throw new Error('Invalid record link.');
        const [endpoint,field,renderer]=specs[path];
        const summaryKind={'sales_invoice_id':'sale','purchase_invoice_id':'purchase','sales_return_id':'sale_return','purchase_return_id':'purchase_return','payment_id':'payment','receipt_id':'receipt','contra_id':'contra'}[field];
        await api('resolve',{kind:summaryKind,id});
        const response=await fetch(endpoint+'?'+new URLSearchParams({action:'current',current_id:id}),{credentials:'same-origin',cache:'no-store',headers:{'X-Requested-With':'XMLHttpRequest'}});
        let record=await response.json();
        if(typeof record==='string')record=JSON.parse(record);
        if(!record[field] && typeof Object.values(record)[0]==='string') {try {record=JSON.parse(Object.values(record)[0]);} catch(_) {}}
        if(!response.ok || String(record[field])!==id)throw new Error('This record is no longer available.');
        root[renderer](record);
      } else if (params.sp_action) {
        const id=R.number(params.party||params.item);if(!id)throw new Error('Invalid record link.');
        const result=await api('resolve',{kind:'action',action:params.sp_action,id});
        if(new URL(result.href,root.location.origin).pathname!==path)throw new Error('This action is unavailable on this page.');
        const box=document.querySelector(params.item?'#item_name, #item_detail_name':'#search_name');
        if(box){box.value=result.record[params.item?'item_name':'party_name'];box.dispatchEvent(new Event('change',{bubbles:true}));box.focus();}
      } else if (params.party || params.item) {
        const kind=params.party?'party':'item', id=R.number(params[kind]);
        if(!id)throw new Error('Invalid record link.');
        const result=await api('resolve',{kind,id});
        if(new URL(result.href,root.location.origin).pathname!==path)throw new Error('This record is unavailable on this page.');
        if(root.FinanceeOpenMaster)root.FinanceeOpenMaster(result.record);
      }
      if(params.serial) {
        const box=document.getElementById('serial_input');if(box){box.value=params.serial.slice(0,100);box.focus();}
      }
    } catch(error) {root.Alerts.notify(error.message,{title:'Record link'});}
  }
  if(root.jQuery) root.jQuery(recordLink); else document.addEventListener('DOMContentLoaded',recordLink);
})(typeof globalThis !== 'undefined' ? globalThis : this);
