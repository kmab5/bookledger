/** One accessible, dependency-free filter builder for all collection views. */
const encode = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const STORAGE = 'bookledger.advanced.';
export function getAdvanced(scope) {
  try { return JSON.parse(sessionStorage.getItem(STORAGE + scope) || 'null'); } catch { return null; }
}
export function setAdvanced(scope, query) {
  if (query) sessionStorage.setItem(STORAGE + scope, JSON.stringify(query));
  else sessionStorage.removeItem(STORAGE + scope);
}
const names = {reading_status:'reading status',file_size:'largest file (bytes)',file_count:'file count',needs_review:'needs review',has_duplicates:'possible duplicates',has_cover:'cached cover',has_isbn:'ISBN present',has_series:'in a series',series_index:'volume number',time_read:'minutes read',current_page:'current page',read_count:'read count',missing_file:'missing source file',unordered_count:'unordered books',finished_count:'books finished',book_count:'books in series',has_series:'series assigned'};
const label = k => names[k] || k.replaceAll('_', ' ');
const opts = (items,selected) => items.map(v=>`<option value="${encode(v)}" ${v===selected?'selected':''}>${encode(label(v))}</option>`).join('');
const emptyGroup=()=>({match:'all',rules:[]});
const emptyRule=()=>({field:'title',op:'contains',value:''});
function valueOf(row,type,op){
 if (op==='is_empty'||op==='is_not_empty'||op==='is_true'||op==='is_false')return undefined;
 const v=row.querySelector('.adv-value')?.value??'';
 if(op==='in'||op==='not_in')return v.split(',').map(x=>x.trim()).filter(Boolean);
 if(op==='between')return [row.querySelector('.adv-value')?.value||'',row.querySelector('.adv-value-two')?.value||''];
 return v;
}
function displayValue(value){return Array.isArray(value)?value.join(', '):String(value??'')}
let nextDatalist=0;
function renderRule(fields, rule={}, choices={}){
 const keys=Object.keys(fields);const field=keys.includes(rule.field)?rule.field:keys[0];const type=fields[field].type;const op=fields[field].operators.includes(rule.op)?rule.op:fields[field].operators[0];
 const root=document.createElement('div');root.className='adv-rule';root.dataset.role='rule';
 root.innerHTML=`<label class="adv-field-wrap"><span class="sr-only">filter field</span><select class="adv-field" aria-label="Filter field">${opts(keys,field)}</select></label><label><span class="sr-only">comparison</span><select class="adv-op" aria-label="Comparison">${opts(fields[field].operators,op)}</select></label><div class="adv-value-wrap"></div><button type="button" class="icon-button adv-remove" aria-label="Remove filter">×</button>`;
 const fieldSel=root.querySelector('.adv-field'),opSel=root.querySelector('.adv-op'),slot=root.querySelector('.adv-value-wrap');
 const renderValue=(current)=>{
  const entry=fields[fieldSel.value];const operation=opSel.value;
  if(['is_empty','is_not_empty','is_true','is_false'].includes(operation)){slot.innerHTML='<span class="adv-no-value">no value</span>';return;}
  const inputType=entry.type==='number'?'number':entry.type==='date'?'date':'text';
  const first=Array.isArray(current)?current[0]:current;const second=Array.isArray(current)?current[1]:'';
  const preset=fieldSel.value==='reading_status'?['unanswered','not_read','want_to_read','reading','finished','on_hold','abandoned','rereading']:null;
  const single=operation!=='between' && operation!=='in' && operation!=='not_in' && preset;
  slot.innerHTML=single?`<select class="adv-value" aria-label="Filter value">${opts(preset,String(first??'unanswered'))}</select>`:
    `<input class="adv-value" aria-label="Filter value" type="${inputType}" ${inputType==='number'?'step="any"':''} value="${encode(displayValue(operation==='in'||operation==='not_in'?current:first))}" placeholder="${['in','not_in'].includes(operation)?'comma-separated values':'value'}">`;
  if(operation==='between')slot.insertAdjacentHTML('beforeend',`<span class="adv-between">to</span><input class="adv-value-two" aria-label="Upper bound" type="${inputType}" ${inputType==='number'?'step="any"':''} value="${encode(second)}">`);
  if(['folder','category','format','series','language','publisher'].includes(fieldSel.value) && !single && (choices[fieldSel.value]||[]).length){const id='adv-choice-'+(++nextDatalist);slot.querySelector('.adv-value')?.setAttribute('list',id);slot.insertAdjacentHTML('beforeend',`<datalist id="${id}">${choices[fieldSel.value].map(x=>`<option value="${encode(x)}"></option>`).join('')}</datalist>`)}
  if(entry.type==='folder' && operation==='eq')slot.insertAdjacentHTML('beforeend',`<label class="adv-folder-nested"><input class="adv-subfolders" type="checkbox" ${rule.subfolders!==false?'checked':''}> nested</label>`);
 };
 fieldSel.addEventListener('change',()=>{opSel.innerHTML=opts(fields[fieldSel.value].operators,fields[fieldSel.value].operators[0]);renderValue('')});
 opSel.addEventListener('change',()=>renderValue(''));
 renderValue(rule.value);root.querySelector('.adv-remove').onclick=()=>root.remove();return root;
}
function renderGroup(fields, obj=emptyGroup(),depth=0,choices={}){
 const root=document.createElement('section');root.className='adv-group';root.dataset.role='group';
 root.innerHTML=`<div class="adv-group-head"><label>match <select class="adv-match" aria-label="Match rules"><option value="all">all (AND)</option><option value="any">any (OR)</option></select></label><button type="button" class="adv-small adv-add-rule">+ rule</button>${depth<2?'<button type="button" class="adv-small adv-add-group">+ group</button>':''}${depth?'<button type="button" class="adv-small adv-remove-group">remove group</button>':''}</div><div class="adv-rules"></div>`;
 root.querySelector('.adv-match').value=obj.match==='any'?'any':'all';const items=root.querySelector('.adv-rules');
 for(const rule of obj.rules||[])items.append(rule&&Array.isArray(rule.rules)?renderGroup(fields,rule,depth+1,choices):renderRule(fields,rule,choices));
 root.querySelector('.adv-add-rule').onclick=()=>items.append(renderRule(fields,{},choices));
 root.querySelector('.adv-add-group')?.addEventListener('click',()=>items.append(renderGroup(fields,{match:'any',rules:[emptyRule()]},depth+1,choices)));
 root.querySelector('.adv-remove-group')?.addEventListener('click',()=>root.remove());return root;
}
function collectGroup(node,fields){
 const children=[...node.querySelector(':scope > .adv-rules').children];const rules=[];
 for(const el of children){
  if(el.dataset.role==='group'){const nested=collectGroup(el,fields);if(nested.rules.length)rules.push(nested);continue;}
  const field=el.querySelector('.adv-field').value,op=el.querySelector('.adv-op').value,type=fields[field].type;
  const raw=valueOf(el,type,op);
  if(!['is_empty','is_not_empty','is_true','is_false'].includes(op) && (raw===''||Array.isArray(raw)&&raw.some(v=>v==='')))continue;
  const out={field,op};if(raw!==undefined)out.value=raw;
  if(type==='folder'&&op==='eq')out.subfolders=el.querySelector('.adv-subfolders')?.checked!==false;
  rules.push(out);
 }
 return {match:node.querySelector(':scope > .adv-group-head > label > .adv-match').value,rules};
}
export async function mountAdvanced({scope,container,request,onApply,metadata,placeholder='Search titles, authors, ISBN…'}) {
 const fields=metadata[scope==='series'?'series':scope==='review'?'review':'books'];const choices=metadata.choices||{};
 const current=getAdvanced(scope);
 container.innerHTML=`<div class="query-toolbar"><div class="query-search"><label class="sr-only" for="advanced-search-${scope}">Search</label><input id="advanced-search-${scope}" type="search" placeholder="${encode(placeholder)}" value="${encode(current?.search||'')}"></div><button type="button" class="btn query-launch">advanced filters <span class="query-count"></span></button><button type="button" class="btn query-clear" ${!current?'hidden':''}>clear</button></div><div class="query-summary" aria-live="polite"></div>`;
 const open=container.querySelector('.query-launch'),clear=container.querySelector('.query-clear'),input=container.querySelector('.query-search input');
 function refresh(){const q=getAdvanced(scope);const count=(function count(g){return (g?.rules||[]).reduce((n,r)=>n+(r.rules?count(r):1),0)})(q?.filters)+(q?.sort?.length||0);container.querySelector('.query-count').textContent=count?String(count):'';clear.hidden=!q;container.querySelector('.query-summary').innerHTML=q&&count?`<span>${count} active rule${count===1?'':'s'} / sorting levels</span><span>${(q.sort||[]).map(x=>`${encode(label(x.field))} ${x.direction==='desc'?'↓':'↑'}`).join(' · ')}</span>`:'';}
 refresh();
 clear.onclick=()=>{setAdvanced(scope,null);input.value='';refresh();onApply(null)};
 let inputTimeout;input.addEventListener('input',()=>{clearTimeout(inputTimeout);inputTimeout=setTimeout(()=>{const current=getAdvanced(scope)||{};const q={...current,search:input.value};setAdvanced(scope,q);refresh();onApply(q)},350)});
 open.onclick=async()=>{
  const q=getAdvanced(scope)||{};const dialog=document.createElement('dialog');dialog.className='advanced-dialog';dialog.setAttribute('aria-label','Advanced filtering and sorting');
  dialog.innerHTML=`<form method="dialog" class="adv-header"><div><span class="section-kicker">${encode(scope)} / query builder</span><h2>filters & sorting.</h2><p>Combine rules, group conditions, sort by up to four fields, or save a view.</p></div><button class="icon-button" aria-label="Close advanced filters" value="cancel">×</button></form><div class="adv-body"><div class="adv-saved"><label>saved views<select class="adv-view-list"><option value="">choose a saved view…</option></select></label><button type="button" class="adv-small adv-save-view">save view</button><button type="button" class="adv-small adv-delete-view">delete</button></div><div class="adv-section-head"><h3>filter rules</h3><span>Combine any field with AND / OR groups.</span></div><div id="adv-root-group"></div><div class="adv-section-head"><h3>sort priority</h3><span>Top criterion takes precedence. Null values go last.</span></div><div class="adv-sorts"></div><button type="button" class="adv-small adv-add-sort">+ add sort level</button></div><div class="adv-footer"><button type="button" class="btn adv-reset">reset</button><span class="grow"></span><button type="button" class="btn adv-cancel">cancel</button><button type="button" class="btn primary adv-apply">apply filters</button></div>`;
  document.body.append(dialog);const fieldsSortable=Object.keys(fields).filter(k=>fields[k].sortable);const root=dialog.querySelector('#adv-root-group');const sorts=dialog.querySelector('.adv-sorts');
  const setGroup=g=>{root.replaceChildren(renderGroup(fields,g?.rules?.length?g:{match:'all',rules:[emptyRule()]},0,choices))};
  const addSort=(s={})=>{if(sorts.children.length>=4)return;const div=document.createElement('div');div.className='adv-sort-row';div.innerHTML=`<span class="adv-sort-number">${sorts.children.length+1}</span><select class="adv-sort-field" aria-label="Sort field">${opts(fieldsSortable,s.field||fieldsSortable[0])}</select><select class="adv-sort-direction" aria-label="Sort direction"><option value="asc">ascending</option><option value="desc">descending</option></select><button type="button" class="icon-button" aria-label="Remove sort level">×</button>`;div.querySelector('.adv-sort-direction').value=s.direction==='desc'?'desc':'asc';div.querySelector('button').onclick=()=>{div.remove();[...sorts.children].forEach((c,i)=>c.querySelector('span').textContent=String(i+1))};sorts.append(div)};
  const setSorts=arr=>{sorts.replaceChildren();(arr||[]).forEach(addSort)};
  function collect(){return {filters:collectGroup(root.firstElementChild,fields),sort:[...sorts.children].map(n=>({field:n.querySelector('.adv-sort-field').value,direction:n.querySelector('.adv-sort-direction').value})),search:input.value.trim(),visibility:q.visibility||'visible'}}
  setGroup(q.filters);setSorts(q.sort);dialog.querySelector('.adv-add-sort').onclick=()=>addSort();
  const views=await request('/query/views?scope='+scope).catch(()=>({items:[]}));let all=views.items;
  const list=dialog.querySelector('.adv-view-list');const populate=()=>{list.innerHTML='<option value="">choose a saved view…</option>'+all.map(v=>`<option value="${v.id}">${encode(v.name)}</option>`).join('')};populate();
  list.onchange=()=>{const v=all.find(x=>String(x.id)===list.value);if(!v)return;setGroup(v.query.filters);setSorts(v.query.sort);input.value=v.query.search||''};
  dialog.querySelector('.adv-save-view').onclick=async()=>{const name=prompt('Name this filter and sort view');if(!name?.trim())return;try{const saved=await request('/query/views',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scope,name:name.trim(),query:collect()})});all.push({id:saved.id,name:name.trim(),query:collect()});populate();list.value=String(saved.id)}catch(e){alert(e.message)}};
  dialog.querySelector('.adv-delete-view').onclick=async()=>{if(!list.value)return;const id=Number(list.value);if(!confirm('Delete this saved view?'))return;await request('/query/views/'+id,{method:'DELETE'});all=all.filter(x=>x.id!==id);populate()};
  dialog.querySelector('.adv-reset').onclick=()=>{setGroup(emptyGroup());setSorts([]);input.value=''};
  dialog.querySelector('.adv-cancel').onclick=()=>dialog.close();
  dialog.querySelector('.adv-apply').onclick=()=>{const data=collect();setAdvanced(scope,data);dialog.close();refresh();onApply(data)};
  dialog.addEventListener('close',()=>{input.value=getAdvanced(scope)?.search||'';dialog.remove()},{once:true});dialog.showModal();
 };
}
