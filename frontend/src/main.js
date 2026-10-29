import './style.css';
import {getAdvanced, mountAdvanced} from './advanced.js';
const app=document.querySelector('#app');
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const request=async(path,options={})=>{const r=await fetch('/api'+path,{headers:{'Content-Type':'application/json'},...options});if(!r.ok){let m;try{m=(await r.json()).detail}catch{}throw Error(typeof m==='string'?m:`Request failed (${r.status})`)}return r.headers.get('content-type')?.includes('json')?r.json():r};
const post=(url,data,method='POST')=>request(url,{method,body:JSON.stringify(data)});
let preferences=null;
async function getPreferences(){if(!preferences){preferences=(await request('/settings')).values}return preferences}
const state={selection:new Set(),mode:false,kind:'books',route:'',queue:[],index:0};
const nav=[
 {path:'/',label:'library',icon:'library',group:'collection'},
 {path:'/series',label:'series',icon:'layers',group:'collection'},
 {path:'/reading',label:'reading review',icon:'book-open',group:'reading'},
 {path:'/quick-sort',label:'quick sort',icon:'zap',group:'reading'},
 {path:'/stats',label:'statistics',icon:'chart',group:'insights'},
 {path:'/review',label:'metadata review',icon:'clipboard',group:'insights'},
 {path:'/scan',label:'scan folders',icon:'folder',group:'tools'},
 {path:'/enrich',label:'enrichment',icon:'refresh',group:'tools'},
 {path:'/exports',label:'exports',icon:'download',group:'tools'},
 {path:'/settings',label:'settings',icon:'settings',group:'system'}
];
const glyphs={
 'library':'<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4H20v15H6.5A2.5 2.5 0 0 1 4 16.5z"/><path d="M4 16.5A2.5 2.5 0 0 1 6.5 14H20"/><path d="M8 8h8"/>',
 'layers':'<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M8 5v14M11 9h6M11 13h5"/>',
 'book-open':'<path d="M12 7C9 5 6 5 3 6v13c3-1 6-1 9 1 3-2 6-2 9-1V6c-3-1-6-1-9 1zM12 7v13"/>',
 'zap':'<path d="m13 2-9 12h7l-1 8 10-12h-7l0-8z"/>',
 'chart':'<path d="M4 20V10m6 10V5m5 15v-7m5 7V3M2 20h20"/>',
 'clipboard':'<rect x="5" y="5" width="14" height="17" rx="2"/><path d="M9 5V3h6v2M9 11h6M9 15h6"/>',
 'folder':'<path d="M3 6h7l2 2h9v11H3z"/>',
 'refresh':'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.5 9a7.5 7.5 0 0 1 12.7-2L20 12M4 12l1.8 5A7.5 7.5 0 0 0 18.5 15"/>',
 'download':'<path d="M12 3v12m-4-4 4 4 4-4M4 18v3h16v-3"/>',
 'settings':'<path d="M12 2.5v2m0 15v2M4.3 4.3l1.4 1.4m12.6 12.6 1.4 1.4M2.5 12h2m15 0h2M4.3 19.7l1.4-1.4M18.3 5.7l1.4-1.4"/><circle cx="12" cy="12" r="4"/>',
 'search':'<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
 'chevron':'<path d="m9 18 6-6-6-6"/>',
 'arrow-left':'<path d="m15 18-6-6 6-6M9 12h12"/>',
 'arrow-right':'<path d="m9 18 6-6-6-6M15 12H3"/>',
 'more':'<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
 'check':'<path d="m4 12 5 5L20 6"/>',
 'eye-off':'<path d="M3 3 21 21M10 5.4A10.5 10.5 0 0 1 21 12a12 12 0 0 1-3.1 3.9M6 6.5A12 12 0 0 0 3 12a10.8 10.8 0 0 0 13 6.7"/>',
 'filter':'<path d="M3 5h18M7 12h10M10 19h4"/>',
 'menu':'<path d="M4 7h16M4 12h16M4 17h16"/>',
 'close':'<path d="M5 5l14 14M19 5 5 19"/>',
 'plus':'<path d="M12 4v16M4 12h16"/>',
 'clock':'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',
 'external':'<path d="M12 4h8v8M20 4l-9 9M20 14v6H4V4h6"/>',
 'grid':'<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
 'list':'<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="4" cy="6" r=".75"/><circle cx="4" cy="12" r=".75"/><circle cx="4" cy="18" r=".75"/>'
};
const icon=(name,extra='')=>`<svg class="icon ${extra}" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${glyphs[name]||glyphs.library}</svg>`;
const navItem=n=>`<a class="nav-item ${location.pathname===n.path?'active':''}" href="${n.path}" data-link aria-label="${n.label}" ${location.pathname===n.path?'aria-current="page"':''}>${icon(n.icon)}<span>${n.label}</span>${location.pathname===n.path?'<span class="nav-active-dot"></span>':''}</a>`;
function shell(){
 const groups=['collection','reading','insights','tools','system'];
 app.innerHTML=`<div class="app"><aside class="sidebar" id="sidebar">
   <a class="logo" href="/" data-link aria-label="BookLedger home"><span class="brand-mark">${icon('book-open')}</span><span>bookledger<span class="brand-period">.</span></span></a>
   <div class="side-scroll"><nav class="nav" aria-label="main navigation">${groups.map(group=>`<div class="nav-group"><div class="nav-heading">${group}</div>${nav.filter(n=>n.group===group).map(navItem).join('')}</div>`).join('')}</nav></div>
   <div class="side-foot"><span class="local-indicator"></span><div><strong>local library</strong><small>all changes stay yours</small></div><span class="build-mark">v2</span></div>
 </aside><div class="workspace"><header class="appbar"><div class="appbar-left"><button type="button" class="icon-button mobile-menu" id="open-nav" aria-label="open navigation" aria-expanded="false">${icon('menu')}</button><span class="breadcrumb-label">workspace</span><span class="breadcrumb-divider">/</span><strong class="breadcrumb-current">${esc(nav.find(n=>n.path===location.pathname)?.label||'book details')}</strong></div><div class="appbar-right"><span class="appbar-pill"><span class="local-indicator"></span> local · private</span><button type="button" class="icon-button" title="Go to settings" aria-label="Go to settings" id="toolbar-settings">${icon('settings')}</button></div></header><main id="content" class="main" tabindex="-1"><div class="loading-state"><span class="loading-pulse"></span>loading collection…</div></main></div><button type="button" class="mobile-scrim" id="nav-scrim" aria-label="close navigation" hidden></button></div>`;
 const sidebar=document.querySelector('#sidebar'),scrim=document.querySelector('#nav-scrim'),toggle=document.querySelector('#open-nav');
 const close=()=>{sidebar.classList.remove('open');scrim.hidden=true;toggle.setAttribute('aria-expanded','false')};
 toggle.onclick=()=>{const open=!sidebar.classList.contains('open');sidebar.classList.toggle('open',open);scrim.hidden=!open;toggle.setAttribute('aria-expanded',String(open));if(open)sidebar.querySelector('.nav-item')?.focus()};scrim.onclick=()=>{close();toggle.focus()};sidebar.addEventListener('keydown',e=>{if(e.key==='Escape'){close();toggle.focus()}});
 document.querySelector('#toolbar-settings').onclick=()=>navigate('/settings');
}
const content=()=>document.querySelector('#content');
const title=(eye,heading,desc='')=>`<header class="page-heading"><div class="page-eyebrow"><span class="eyebrow-dot"></span>${esc(eye)}</div><h1>${esc(heading)}</h1>${desc?`<p class="page-description">${esc(desc)}</p>`:''}</header>`;
const emptyState=(heading,description,iconName='library')=>`<div class="empty-state">${icon(iconName)}<h3>${esc(heading)}</h3><p>${esc(description)}</p></div>`;

function toast(message){document.querySelector('.toast')?.remove();const div=document.createElement('div');div.className='toast';div.role='status';div.textContent=message;document.body.append(div);setTimeout(()=>div.remove(),3200)}
function navigate(path){history.pushState(null,'',path);render()}
window.addEventListener('popstate',()=>render());document.addEventListener('click',e=>{const a=e.target.closest('[data-link]');if(a){e.preventDefault();navigate(a.getAttribute('href'))}});
function cover(b,cls=''){
 if(preferences?.['library.show_covers']===false)return `<span class="cover-placeholder" aria-label="covers disabled">${icon('book-open')}</span>`;
 return b.cover_path?`<img class="${cls}" src="/api/cover/${b.id}" loading="lazy" alt="Cover of ${esc(b.title)}" onerror="this.replaceWith(document.createTextNode('▤'))">`:`<span class="cover-placeholder" role="img" aria-label="No cover available">${icon('book-open')}</span>`;
}
function selectBox(id,kind='books'){return `<label class="checkbox-float" ${state.mode?'':'hidden'}><input aria-label="select item" type="checkbox" data-select="${id}" data-kind="${kind}" ${state.selection.has(id)?'checked':''}></label>`}
function statusLabel(s){return ({finished:'read',reading:'reading',want_to_read:'want to read',not_read:'not read',on_hold:'paused',abandoned:'abandoned',rereading:'rereading',unanswered:'unclassified'})[s]||String(s||'unclassified').replaceAll('_',' ')}
function bookCard(b){const status=b.reading_status||'unanswered';return `<article class="book selectable" data-book="${b.id}" tabindex="0" aria-label="Open ${esc(b.title)}">${selectBox(b.id)}<div class="book-cover">${cover(b)}</div><div class="book-info"><div class="book-title-row"><h3 title="${esc(b.title)}">${esc(b.title)}</h3><button type="button" class="card-menu" data-menu aria-label="More actions for ${esc(b.title)}">${icon('more')}</button></div><p class="book-author">${esc((b.authors||[]).join(', ')||'unknown author')}</p><div class="book-footer">${preferences?.['library.show_status_badges']===false?'':`<span class="tag status-${status}"><span class="tag-dot"></span>${esc(statusLabel(status))}</span>`}${b.series?`<span class="book-series" title="${esc(b.series)}">${esc(b.series)}</span>`:''}</div></div></article>`}

function updateSelection(){
 document.querySelectorAll('.checkbox-float').forEach(x=>x.hidden=!state.mode);
 document.querySelectorAll('[data-select]').forEach(x=>x.checked=state.selection.has(Number(x.dataset.select)));
 document.querySelector('#bulkbar')?.remove();if(!state.mode)return;
 const bar=document.createElement('div');bar.id='bulkbar';bar.className='toolbar';
 const opts=state.kind==='series'?['delete']:['finished','reading','not_read','want_to_read','on_hold','abandoned','hide','unhide','unassign_series','assign_series'];
 bar.innerHTML=`<span class="bulk-counter">${icon('check')} <strong>${state.selection.size}</strong> selected</span><button class="btn btn-subtle" data-all>select all shown</button><label class="bulk-choice"><span class="sr-only">bulk action</span><select aria-label="bulk action" id="bulk-action">${opts.map(o=>`<option value="${o}">${o.replaceAll('_',' ')}</option>`).join('')}</select></label><button class="btn primary" data-apply ${state.selection.size?'':'disabled'}>apply</button><button class="icon-button" aria-label="exit selection" title="exit selection" data-done>${icon('close')}</button>`;
 document.body.append(bar)
}

function exitSelection(){state.selection.clear();state.mode=false;updateSelection()}
async function applyBulk(){const action=document.querySelector('#bulk-action').value;if(!state.selection.size)return;if((action==='delete'||action==='unassign_series')&&!confirm(`Apply ${action} to ${state.selection.size} items?`))return;if(state.kind==='series'){for(const id of state.selection)await request(`/series/${id}`,{method:'DELETE'})}else {let series_name=null;if(action==='assign_series'){const names=(await request('/series')).items.map(s=>s.name);series_name=prompt('Assign to series (existing or new):\n'+names.slice(0,30).join(' · '));if(!series_name?.trim())return}await post('/books/bulk',{ids:[...state.selection],action,series_name})}exitSelection();toast('Changes saved');render()}
let menu;function openMenu(x,y,items){
 menu?.remove();const previous=document.activeElement;menu=document.createElement('div');menu.className='context';menu.setAttribute('role','menu');items.forEach(([name,action])=>{const b=document.createElement('button');b.textContent=name;b.setAttribute('role','menuitem');b.onclick=()=>{menu?.remove();menu=null;action()};menu.append(b)});document.body.append(menu);menu.style.left=Math.max(8,Math.min(x,innerWidth-menu.offsetWidth-10))+'px';menu.style.top=Math.max(8,Math.min(y,innerHeight-menu.offsetHeight-10))+'px';menu.querySelector('button')?.focus();
 menu.addEventListener('keydown',e=>{const buttons=[...menu.querySelectorAll('button')];const index=buttons.indexOf(document.activeElement);if(e.key==='Escape'){e.preventDefault();menu.remove();menu=null;previous?.focus?.()}else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?buttons.length-1:(index+(e.key==='ArrowDown'?1:-1)+buttons.length)%buttons.length;buttons[next]?.focus()}});
}
document.addEventListener('click',e=>{if(menu&&!menu.contains(e.target)){menu.remove();menu=null}if(e.target.closest('[data-all]')){document.querySelectorAll('[data-select]').forEach(el=>state.selection.add(Number(el.dataset.select)));updateSelection()}if(e.target.closest('[data-done]'))exitSelection();if(e.target.closest('[data-apply]'))applyBulk();const trigger=e.target.closest('[data-menu]');if(trigger){e.preventDefault();e.stopPropagation();const rect=trigger.getBoundingClientRect();openMenu(rect.right,rect.bottom+5,menuItems(trigger));return}const box=e.target.closest('[data-select]');if(box){e.stopPropagation();return}const card=e.target.closest('[data-book]');if(card&&!state.mode&&!e.target.closest('button,a,input'))navigate('/book/'+card.dataset.book);if(card&&state.mode&&!e.target.closest('button,a,input')){const id=Number(card.dataset.book);state.selection.has(id)?state.selection.delete(id):state.selection.add(id);updateSelection()}});
document.addEventListener('change',e=>{if(e.target.matches('[data-select]')){const id=Number(e.target.dataset.select);e.target.checked?state.selection.add(id):state.selection.delete(id);updateSelection()}});
function menuItems(target){const card=target.closest('[data-book]');const ser=target.closest('[data-series]');const items=[];if(card){const id=Number(card.dataset.book);items.push(['open book',()=>navigate('/book/'+id)],['select item',()=>{state.kind='books';state.mode=true;state.selection.add(id);updateSelection()}],['mark read',async()=>{await post(`/books/${id}`,{status:'finished'},'PATCH');render()}],['not read',async()=>{await post(`/books/${id}`,{status:'not_read'},'PATCH');render()}],['hide book',async()=>{await post(`/books/${id}`,{hidden:true},'PATCH');render()}])}else if(ser){const id=Number(ser.dataset.series);items.push(['open series',()=>navigate('/series/'+id)],['select series',()=>{state.kind='series';state.mode=true;state.selection.add(id);updateSelection()}],['delete series',async()=>{if(confirm('Delete series? Books will remain.')){await request('/series/'+id,{method:'DELETE'});render()}}])}else items.push(['library',()=>navigate('/')],['reading review',()=>navigate('/reading')],['quick sort',()=>navigate('/quick-sort')],['statistics',()=>navigate('/stats')]);return items}
document.addEventListener('contextmenu',e=>{if(e.target.closest('input,textarea,select'))return;e.preventDefault();openMenu(e.clientX,e.clientY,menuItems(e.target))});document.addEventListener('keydown',e=>{if(e.key==='Escape'&&menu){menu.remove();menu=null}if(e.key==='F10'&&e.shiftKey){e.preventDefault();const t=document.activeElement;const r=t.getBoundingClientRect();openMenu(r.left,r.bottom,menuItems(t))}if((e.key==='Enter'||e.key===' ')&&document.activeElement?.matches('[data-book]')){e.preventDefault();navigate('/book/'+document.activeElement.dataset.book)}});let press;document.addEventListener('pointerdown',e=>{if(e.pointerType!=='touch'||e.target.closest('input,textarea,select,button'))return;const t=e.target;press=setTimeout(()=>openMenu(e.clientX,e.clientY,menuItems(t)),600)});['pointerup','pointercancel','pointermove'].forEach(k=>document.addEventListener(k,()=>clearTimeout(press)));
async function library(){
 await getPreferences();document.documentElement.dataset.density=preferences['library.card_density'];
 const qs=new URLSearchParams(location.search),page=Math.max(1,Number(qs.get('page')||1));
 const advanced=getAdvanced('books')||{};
 const defaultSort={title:[{field:'title',direction:'asc'}],author:[{field:'authors',direction:'asc'}],recent:[{field:'updated',direction:'desc'}],series:[{field:'series',direction:'asc'},{field:'series_index',direction:'asc'}]};
 const query={filters:advanced.filters||{match:'all',rules:[]},sort:advanced.sort?.length?advanced.sort:defaultSort[preferences['library.default_sort']]||[],search:advanced.search||'',visibility:advanced.visibility||preferences['library.default_visibility'],per_page:Number(qs.get('per_page')||preferences['library.page_size']),page};
 const [data,metadata]=await Promise.all([post('/query/books',query),request('/query/metadata')]);
 content().innerHTML=title('collection / catalog','your library.',`${data.total.toLocaleString()} books match this view. Filter by metadata, reading history, file details, and more.`)+`
 <section class="query-controls"><div id="library-query"></div><div class="query-extras"><label>visibility<select id="library-visibility"><option value="visible" ${query.visibility==='visible'?'selected':''}>visible</option><option value="hidden" ${query.visibility==='hidden'?'selected':''}>hidden only</option><option value="all" ${query.visibility==='all'?'selected':''}>all</option></select></label><label>per page<select id="library-page-size">${[24,48,96,200].map(n=>`<option value="${n}" ${query.per_page===n?'selected':''}>${n}</option>`).join('')}</select></label></div></section>
 <div class="section-heading"><div><span class="section-kicker">catalog</span><h2>matching books <span class="count-chip">${data.total.toLocaleString()}</span></h2></div><div class="section-controls"><button class="icon-button view-control ${localStorage.getItem('bl-view')==='list'?'':'selected'}" id="view-grid" aria-label="Grid view" title="Grid view">${icon('grid')}</button><button class="icon-button view-control ${localStorage.getItem('bl-view')==='list'?'selected':''}" id="view-list" aria-label="List view" title="List view">${icon('list')}</button></div></div>
 <div class="grid ${localStorage.getItem('bl-view')==='list'?'library-list':''}" id="book-grid">${data.items.map(bookCard).join('')||emptyState('no books found','Try a different filter combination.','search')}</div>
 <div class="pagination"><span class="muted">showing ${data.total?((data.page-1)*data.per_page+1).toLocaleString():0}–${Math.min(data.page*data.per_page,data.total).toLocaleString()} of ${data.total.toLocaleString()}</span><div class="pagination-actions"><button class="btn" id="previous" ${data.page<=1?'disabled':''}>${icon('arrow-left')} previous</button><span class="page-number">${data.page} / ${data.pages}</span><button class="btn" id="next" ${data.page>=data.pages?'disabled':''}>next ${icon('chevron')}</button></div></div>`;
 await mountAdvanced({scope:'books',container:content().querySelector('#library-query'),request,metadata,onApply:()=>navigate('/')});
 content().querySelector('#library-visibility').onchange=e=>{const q=getAdvanced('books')||{};q.visibility=e.target.value;sessionStorage.setItem('bookledger.advanced.books',JSON.stringify(q));navigate('/')};
 content().querySelector('#library-page-size').onchange=e=>{const p=new URLSearchParams({per_page:e.target.value});navigate('/?'+p)};
 for(const [k,delta] of [['previous',-1],['next',1]])content().querySelector('#'+k).onclick=()=>{qs.set('page',String(data.page+delta));navigate('/?'+qs)};
 for(const view of ['grid','list'])content().querySelector('#view-'+view).onclick=()=>{localStorage.setItem('bl-view',view);content().querySelector('#book-grid').classList.toggle('library-list',view==='list');content().querySelectorAll('.view-control').forEach(x=>x.classList.toggle('selected',x.id==='view-'+view))};
 updateSelection();
}

async function detail(id){const d=await request('/books/'+id),b=d.book,r=d.reading||{};const status=['unanswered','not_read','want_to_read','reading','finished','on_hold','abandoned','rereading'];content().innerHTML=`<a class="muted" href="/" data-link>← library</a><div class="detail-head" style="margin:25px 0"><div style="width:200px;flex-shrink:0"><div class="book-cover">${cover(b)}</div></div><div class="grow">${title(b.series||'book details',b.title,(b.authors||[]).join(', '))}<div class="row">${status.map(s=>`<button class="btn ${r.status===s?'primary':''}" data-status="${s}">${s.replaceAll('_',' ')}</button>`).join('')}</div><div class="row" style="margin-top:16px"><button class="btn" id="hide">${b.hidden?'restore book':'hide book'}</button>${b.series?`<a class="btn" href="/series" data-link>view series</a>`:''}</div></div></div><div class="split"><div class="stack"><section class="panel"><h2>metadata.</h2><div class="detail-meta">${['isbn13','isbn10','publisher','published','language','page_count','word_count','series','series_index','cover_url'].map(k=>`<div><b>${k.replaceAll('_',' ')}</b>${esc(b[k]??'—')}</div>`).join('')}</div><p style="margin-top:20px">${esc(b.description||'No description available.')}</p></section><section class="panel"><h2>associated records.</h2><p>files: ${d.files.length} · possible editions: ${d.links.length} · unresolved suggestions: ${d.reviews.length}</p>${d.links.map(l=>`<a class="btn" href="/book/${l.book_id===b.id?l.candidate_id:l.book_id}" data-link>${esc(l.candidate_title)} (${Math.round(l.confidence*100)}%)</a>`).join(' ')}<h3 style="margin-top:18px">source folders</h3>${d.folders.map(f=>`<p>${esc(f.folder_path)}</p>`).join('')||'<p>None recorded</p>'}<h3>file locations</h3>${d.files.map(f=>`<div class="file-location"><span>${esc(f.extension||'file')}</span><code title="${esc(f.path)}">${esc(f.path)}</code>${f.missing?'<small>missing from disk</small>':''}</div>`).join('')||'<p>None recorded</p>'}</section></div><div class="stack"><form class="panel" id="readingform"><h2>reading record.</h2>${[['started','start date','date'],['finished','finish date','date'],['minutes_read','minutes read','number'],['current_page','current page','number'],['rating','rating (0–5)','number']].map(([k,n,t])=>`<label style="margin-bottom:13px">${n}<input type="${t}" name="${k}" value="${esc(r[k]??'')}" ${k==='rating'?'min="0" max="5" step="0.5"':''}></label>`).join('')}<label>notes<textarea name="notes" rows="5">${esc(r.notes||'')}</textarea></label><button class="btn primary" style="margin-top:14px">save reading record</button></form><section class="panel"><h2>reading sessions.</h2>${d.sessions.map(s=>`<p>${esc(s.started||'—')} · ${esc(s.minutes_read||0)} minutes · ${esc(s.note||'')}</p>`).join('')||'<p>No sessions yet.</p>'}</section></div></div>`;content().querySelectorAll('[data-status]').forEach(btn=>btn.onclick=async()=>{await post(`/books/${id}`,{status:btn.dataset.status},'PATCH');toast('Reading status saved');detail(id)});content().querySelector('#hide').onclick=async()=>{await post(`/books/${id}`,{hidden:!b.hidden},'PATCH');detail(id)};content().querySelector('#readingform').onsubmit=async e=>{e.preventDefault();const obj=Object.fromEntries(new FormData(e.target));for(const k of ['minutes_read','current_page','rating'])obj[k]=obj[k]===''?null:Number(obj[k]);for(const k of ['started','finished'])obj[k]=obj[k]||null;await post(`/books/${id}`,obj,'PATCH');toast('Reading record saved')}}
async function reading(){
 await getPreferences();
 const params=new URLSearchParams(location.search);
 const current=params.get('status')??preferences['reading.default_queue'];
 const page=Number(params.get('page')||1),perPage=35;
 const adv=getAdvanced('reading')||{};
 const restrictions=[];if(adv.filters?.rules?.length)restrictions.push(adv.filters);
 if(current!=='all')restrictions.push({field:'reading_status',op:'eq',value:current});
 const [data,meta]=await Promise.all([post('/query/books',{filters:{match:'all',rules:restrictions},sort:adv.sort||[],search:adv.search||'',visibility:'visible',per_page:perPage,page:Math.max(1,page)}),request('/query/metadata')]);
 const tabs=[['unanswered','unclassified'],['all','all books'],['reading','in progress'],['finished','read'],['want_to_read','to read']];
 content().innerHTML=title('reading / review','have you read it?','Classify books without opening them. Every choice saves immediately.')+`
 <div class="reading-toolbar"><div class="reading-tabs" role="group" aria-label="filter reading queue">${tabs.map(([s,label])=>`<a href="/reading?status=${s}" data-link class="tab-link ${current===s?'active':''}" ${current===s?'aria-current="page"':''}>${label}</a>`).join('')}</div><a class="btn primary" href="/quick-sort" data-link>${icon('zap')} quick sort</a></div>
 <div id="reading-query"></div>
 <div class="section-heading"><div><span class="section-kicker">reading queue</span><h2>${current==='all'?'every book':statusLabel(current)} <span class="count-chip">${data.total.toLocaleString()}</span></h2></div></div>
 <div class="list reading-list">${data.items.map(b=>`<article class="list-item reading-item selectable" data-book="${b.id}">${selectBox(b.id)}<div class="thumb book-cover">${cover(b)}</div><div class="grow"><strong>${esc(b.title)}</strong><small>${esc((b.authors||[]).join(', ')||'unknown author')}${b.series?' · '+esc(b.series):''}</small><span class="tag status-${b.reading_status||'unanswered'}"><span class="tag-dot"></span>${esc(statusLabel(b.reading_status))}</span></div><div class="actions row">${[['finished','read'],['reading','reading'],['want_to_read','tbr'],['not_read','not read'],['on_hold','pause'],['abandoned','abandon']].map(([v,l])=>`<button class="btn ${b.reading_status===v?'reading-selected':''}" data-quick="${v}" data-id="${b.id}" aria-label="Mark ${esc(b.title)} as ${esc(l)}">${l}</button>`).join('')}</div><button class="icon-button reading-more" data-menu aria-label="More actions for ${esc(b.title)}">${icon('more')}</button></article>`).join('')||emptyState('all caught up','No books match this reading queue.','check')}</div>
 <div class="pagination"><span class="muted">${data.total?((data.page-1)*data.per_page+1):0}–${Math.min(data.page*data.per_page,data.total)} of ${data.total.toLocaleString()}</span><div class="pagination-actions"><button class="btn" id="read-prev" ${data.page<=1?'disabled':''}>previous</button><span class="page-number">${data.page} / ${Math.max(1,Math.ceil(data.total/data.per_page))}</span><button class="btn" id="read-next" ${data.page*data.per_page>=data.total?'disabled':''}>next ${icon('chevron')}</button></div></div>`;
 await mountAdvanced({scope:'reading',container:content().querySelector('#reading-query'),request,metadata:meta,onApply:()=>navigate('/reading?status='+encodeURIComponent(current))});
 for(const [k,delta] of [['read-prev',-1],['read-next',1]])content().querySelector('#'+k).onclick=()=>navigate('/reading?'+new URLSearchParams({status:current,page:String(data.page+delta)}));
 content().querySelectorAll('[data-quick]').forEach(btn=>btn.onclick=async e=>{e.stopPropagation();btn.disabled=true;try{await post(`/books/${btn.dataset.id}`,{status:btn.dataset.quick},'PATCH');toast('marked '+statusLabel(btn.dataset.quick));await reading()}catch(ex){toast(ex.message);btn.disabled=false}});
 updateSelection();
}

async function quick(){await getPreferences();const opt=await request('/options');const ser=(await request('/series')).items.map(s=>s.name);const authors=(await request('/quick-sort/authors')).items;
  const params=new URLSearchParams(location.search);const scope=params.get('scope')||'all';const value=params.get('value')||'';const order=params.get('order')||'title';const size=Number(params.get('size')||50);const offset=Number(params.get('offset')||0);
  const choices=(entries,selected)=>entries.map(([v,l])=>`<option value="${esc(v)}" ${selected===v?'selected':''}>${esc(l)}</option>`).join('');
  const form=`<form id="queue-builder" class="panel queue-builder"><h2>build your queue.</h2><div class="queue-grid"><label>group by<select name="scope">${choices([['all','all books'],['series','series'],['folder','folder'],['author','author']],scope)}</select></label><label>selection<select name="value" id="queue-value"></select></label><label>ordering<select name="order">${choices([['title','a to z'],['reverse','z to a'],['random','random'],['series','volume order'],['author','author']],order)}</select></label><label>batch size<input type="number" name="size" min="1" max="1000" value="${Number.isFinite(size)?size:50}"></label><label>batch offset<input type="number" name="offset" min="0" value="${Number.isFinite(offset)?offset:0}"></label><label class="queue-check"><input name="classified" type="checkbox" ${(params.get('include_classified')??String(preferences['quick_sort.include_classified']))==='true'?'checked':''}> include classified</label><label class="queue-check"><input name="nested" type="checkbox" ${(params.get('include_subfolders')??String(preferences['library.include_subfolders']))==='true'?'checked':''}> include subfolders</label></div><div class="row"><button class="btn primary" type="submit">start batch</button><button class="btn" id="queue-reset" type="button">reset</button></div></form>`;
  const options={all:[['','all books']],series:ser.map(s=>[s,s]),folder:opt.folders.map(s=>[s,s]),author:authors.map(s=>[s,s])};
  content().innerHTML=title('reading / quick sort','choose a batch.','Review individual books, a specific series, or an entire source folder.')+form+'<section class="queue-advanced panel"><h3>refine this batch</h3><div id="quick-query"></div></section><div id="queue-result"></div>';
  const qmeta=await request('/query/metadata');await mountAdvanced({scope:'quick',container:content().querySelector('#quick-query'),request,metadata:qmeta,onApply:()=>toast('Advanced batch filters updated. Start batch to apply.')});
  const builder=content().querySelector('#queue-builder');function updateValues(){const el=builder.querySelector('#queue-value');const list=options[builder.elements.namedItem('scope').value]||[];el.innerHTML=choices(list,value);if(!list.some(([v])=>v===value))el.selectedIndex=0;el.disabled=builder.elements.namedItem('scope').value==='all'}
  builder.scope.onchange=updateValues;updateValues();builder.querySelector('#queue-reset').onclick=()=>navigate('/quick-sort');
  builder.onsubmit=async e=>{e.preventDefault();const fd=new FormData(builder);const p=new URLSearchParams({scope:fd.get('scope'),value:fd.get('value')||'',order:fd.get('order'),size:fd.get('size'),offset:fd.get('offset')});p.set('include_classified',String(fd.has('classified')));p.set('include_subfolders',String(fd.has('nested')));const query=new URLSearchParams(p);try{const adv=getAdvanced('quick')||{};
     const ruleList=[];
     if(adv.filters?.rules?.length)ruleList.push(adv.filters);
     if(fd.get('scope')!=='all'&&fd.get('value')){
       const field={series:'series',folder:'folder',author:'authors'}[fd.get('scope')];
       ruleList.push({field,op:field==='authors'?'contains':'eq',value:fd.get('value'),...(field==='folder'?{subfolders:fd.has('nested')}: {})});
     }
     if(!fd.has('classified'))ruleList.push({field:'reading_status',op:'eq',value:'unanswered'});
     const order=fd.get('order');const defaultSort={title:[{field:'title',direction:'asc'}],reverse:[{field:'title',direction:'desc'}],series:[{field:'series_index',direction:'asc'},{field:'title',direction:'asc'}],author:[{field:'authors',direction:'asc'}]};
     const batch={filters:{match:'all',rules:ruleList},sort:adv.sort?.length?adv.sort:(defaultSort[order]||[]),search:adv.search||'',visibility:'visible',per_page:Math.max(1,Math.min(1000,Number(fd.get('size')||50))),page:1,offset:Math.max(0,Number(fd.get('offset')||0)),random:order==='random'&&!adv.sort?.length};
     const d=await post('/query/quick-sort',batch);state.queue=d.items;state.index=0;state.queueTotal=d.total;history.replaceState(null,'','/quick-sort?'+p);if(!d.items.length){content().querySelector('#queue-result').innerHTML='<p class="panel">No books match this batch.</p>';return}await drawQuick()}catch(error){toast(error.message)}};
  if(params.has('scope'))builder.requestSubmit();
}
async function sortWholeGroup(){
 const query=new URLSearchParams(location.search),scope=query.get('scope'),value=query.get('value');if(!['series','folder','author'].includes(scope)||!value)return;
 const choice=prompt('Apply to all matching books in this group? Enter: read, not read, or hide.\nThis affects the full group, not just the current batch.');
 const actions={'read':'finished','not read':'not_read','hide':'hide'};const action=actions[choice?.trim().toLowerCase()];if(!action)return;
 const ids=[];let offset=0,total=0;
 try{do{const q=new URLSearchParams({scope,value,order:'title',size:'1000',offset:String(offset),include_classified:'true',include_subfolders:query.get('include_subfolders')||'true'});const d=await request('/quick-sort/queue?'+q);total=d.total;ids.push(...d.items.map(b=>b.id));offset+=d.items.length;if(!d.items.length)break}while(offset<total);
 if(!ids.length){toast('No books in group');return}
 if(!confirm(`Apply ${choice} to ${ids.length} books in ${value}?`))return;
 for(let i=0;i<ids.length;i+=1000)await post('/books/bulk',{ids:ids.slice(i,i+1000),action});toast(`Updated ${ids.length} books`);navigate('/quick-sort')
 }catch(e){toast('Group action failed: '+e.message)}
}
let quickBusy=false;
async function drawQuick(){
  const b=state.queue[state.index];
  if(!b){content().innerHTML=title('reading / quick sort','quick sort.','Your current queue is complete.')+'<a class="btn" href="/reading" data-link>reading review</a>';return}
  const token=state.index;
  content().innerHTML=title('reading / quick sort','quick sort.',`${state.index+1} of ${state.queue.length} · use arrow keys or swipe outside the editor.`)+'<div class="panel quick-loading" role="status">loading metadata…</div>';
  try{
    const d=await request('/books/'+b.id);
    if(state.index!==token||location.pathname!=='/quick-sort')return;
    const full=d.book, r=d.reading||{};
    const field=(key,label,type='text')=>`<label>${label}<input name="${key}" type="${type}" value="${esc(full[key]??'')}" ${type==='number'?'min="0"':''}></label>`;
    content().innerHTML=title('reading / quick sort','quick sort.',`${state.index+1} of ${state.queue.length} · swipe on the cover or use arrow keys outside fields.`)+`<div class="quick-progress"><span>${state.index+1} / ${state.queue.length} books</span><div class="meter"><div style="width:${100*(state.index+1)/state.queue.length}%"></div></div></div><div class="quick-layout">
      <section class="panel quick-card" aria-label="quick sort book" data-book="${b.id}">
        <div class="book-cover quick-swipe-target">${cover(full)}</div>
        <h2>${esc(full.title)}</h2><p>${esc((full.authors||[]).join(', '))} ${full.series?'· '+esc(full.series):''}</p>
        <span class="tag">${esc(r.status||'unanswered').replaceAll('_',' ')}</span>
        <div class="row quick-group-actions"><button class="btn" id="change-queue">change batch</button>${new URLSearchParams(location.search).get('scope')!=='all'?'<button class="btn" id="whole-group">sort entire group…</button>':''}</div>
        <div class="quick-actions" style="margin-top:17px"><button class="btn" data-quickaction="not_read">← not read</button><button class="btn primary" data-quickaction="finished">read →</button><button class="btn" data-quickaction="skip">↑ skip</button><button class="btn danger" data-quickaction="hide">↓ hide</button></div>
      </section>
      <form class="panel quick-editor" id="quick-metadata"><div class="quick-editor-head"><div><span class="eyebrow">book / metadata</span><h2>book details.</h2></div><span id="quick-save-status" class="muted" role="status" aria-live="polite"></span></div>
        <section class="quick-locations" aria-label="indexed file locations">${d.files.map(f=>`<div class="file-location"><code title="${esc(f.path)}">${esc(f.path)}</code>${f.missing?'<small>missing from disk</small>':''}</div>`).join('')||'<p class="muted">No source location recorded.</p>'}</section>
        <div class="quick-fields">${field('title','title')}${field('subtitle','subtitle')}<label class="wide">authors (comma separated)<input name="authors" value="${esc((full.authors||[]).join(', '))}"></label>${field('series','series')}${field('series_index','volume number','number')}${field('isbn13','isbn-13')}${field('isbn10','isbn-10')}${field('publisher','publisher')}${field('published','publication date')}${field('language','language')}${field('page_count','pages','number')}${field('word_count','word count','number')}${field('cover_url','cover URL')}</div>
        <label class="quick-description">description<textarea name="description" rows="4">${esc(full.description||'')}</textarea></label>
        <details class="quick-read-details"><summary>reading details</summary><div class="quick-fields">${[['started','start date','date'],['finished','finish date','date'],['minutes_read','minutes read','number'],['current_page','current page','number'],['rating','rating','number']].map(([key,label,type])=>`<label>${label}<input name="${key}" type="${type}" value="${esc(r[key]??'')}" ${type==='number'?'min="0"':''}></label>`).join('')}</div><label>reading notes<textarea name="notes" rows="3">${esc(r.notes||'')}</textarea></label></details>
        <div class="quick-editor-actions"><button class="btn primary" type="submit">save changes</button><span class="muted">changes are saved to your library, not to the ebook file.</span></div>
      </form></div>`;
    window.scrollTo({top:0,behavior:"instant"});
    content().querySelector('#change-queue')?.addEventListener('click',()=>navigate('/quick-sort'));content().querySelector('#whole-group')?.addEventListener('click',sortWholeGroup);
    content().querySelectorAll('[data-quickaction]').forEach(el=>el.onclick=()=>quickAction(el.dataset.quickaction));
    const form=content().querySelector('#quick-metadata');
    if(preferences['quick_sort.show_metadata']===false){form.hidden=true;content().querySelector('.quick-layout').classList.add('quick-layout-no-editor')}
    form.onsubmit=async e=>{e.preventDefault();const button=form.querySelector('button[type=submit]'),out=form.querySelector('#quick-save-status');button.disabled=true;out.textContent='saving…';try{
      const raw=Object.fromEntries(new FormData(form));raw.authors=raw.authors.split(',').map(x=>x.trim()).filter(Boolean);
      for(const key of ['page_count','word_count','series_index','minutes_read','current_page','rating'])raw[key]=raw[key]===''?null:Number(raw[key]);
      for(const key of ['started','finished'])raw[key]=raw[key]||null;
      if(!raw.title.trim())throw Error('A title is required');
      await post(`/books/${b.id}`,raw,'PATCH');
      Object.assign(b,raw);out.textContent='saved';toast('Book details saved');
      content().querySelector('.quick-card h2').textContent=raw.title;
      content().querySelector('.quick-card p').textContent=raw.authors.join(', ')+(raw.series?' · '+raw.series:'');
    }catch(ex){out.textContent=ex.message;toast('Unable to save: '+ex.message)}finally{button.disabled=false}};
    let sx=0,sy=0;
    const swipe=content().querySelector('.quick-swipe-target');
    swipe.onpointerdown=e=>{sx=e.clientX;sy=e.clientY};
    swipe.onpointerup=e=>{const dx=e.clientX-sx,dy=e.clientY-sy;if(Math.max(Math.abs(dx),Math.abs(dy))<75)return;quickAction(Math.abs(dx)>Math.abs(dy)?(dx>0?'finished':'not_read'):(dy<0?'skip':'hide'))};
  }catch(ex){content().innerHTML=title('reading / quick sort','metadata unavailable.')+`<div class="panel"><p>${esc(ex.message)}</p><button class="btn" id="next-quick">skip book</button></div>`;content().querySelector('#next-quick').onclick=()=>quickAction('skip')}
}
async function quickAction(action){const b=state.queue[state.index];if(!b||quickBusy)return;quickBusy=true;try{if(action==='hide')await post(`/books/${b.id}`,{hidden:true},'PATCH');else if(action!=='skip')await post(`/books/${b.id}`,{status:action},'PATCH');state.index++;await drawQuick()}catch(ex){toast('Unable to classify: '+ex.message)}finally{quickBusy=false}}
window.addEventListener('keydown',e=>{if(location.pathname!=='/quick-sort'||/^(INPUT|TEXTAREA|SELECT|BUTTON)$/.test(document.activeElement.tagName))return;const a={ArrowLeft:'not_read',ArrowRight:'finished',ArrowUp:'skip',ArrowDown:'hide'}[e.key];if(a){e.preventDefault();quickAction(a)}});
async function seriesPage(){
 const query=getAdvanced('series')||{};const page=Math.max(1,Number(new URLSearchParams(location.search).get('page')||1));
 const [d,meta]=await Promise.all([post('/query/series',{filters:query.filters||{match:'all',rules:[]},sort:query.sort||[],search:query.search||'',page,per_page:60}),request('/query/metadata')]);
 const items=d.items;
 content().innerHTML=title('collection / series','your series.','Combine progress, ordering, size, and name filters. Save frequently used views.')+`
 <div id="series-query"></div>
 <div class="header-row series-controls"><p class="muted">${d.total.toLocaleString()} matching series</p><button id="new-series" class="btn primary">${icon('plus')} new series</button></div>
 <div class="series-grid" id="series-grid"></div><div class="pagination"><span>${d.total.toLocaleString()} series · page ${d.page} of ${d.pages}</span><div class="pagination-actions"><button class="btn" id="series-prev" ${d.page<=1?'disabled':''}>previous</button><button class="btn" id="series-next" ${d.page>=d.pages?'disabled':''}>next</button></div></div>`;
 const grid=content().querySelector('#series-grid');
 const card=s=>`<article class="series-card selectable" data-series="${s.id}" tabindex="0" aria-label="Open series ${esc(s.name)}">${selectBox(s.id,'series')}<div class="series-art">${s.cover_id?`<img loading="lazy" src="/api/cover/${s.cover_id}" alt="Cover from ${esc(s.name)}" onerror="this.style.visibility='hidden'">`:`<span class="series-placeholder">${icon('layers')}</span>`}<button type="button" data-menu class="series-menu icon-button" aria-label="More actions for ${esc(s.name)}">${icon('more')}</button></div><div class="series-body"><h3>${esc(s.name)}</h3><p>${s.book_count} books · ${s.finished_count||0} read</p><div class="meter" role="progressbar" aria-label="Reading completion" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${s.book_count?Math.round(100*(s.finished_count||0)/s.book_count):0}"><div style="width:${s.book_count?100*(s.finished_count||0)/s.book_count:0}%"></div></div>${s.unordered_count?`<small>${s.unordered_count} missing volume numbers</small>`:''}</div></article>`;
 grid.innerHTML=items.map(card).join('')||emptyState('no matching series','Change your filters to broaden the results.','layers');
 grid.querySelectorAll('[data-series]').forEach(el=>el.onclick=e=>{if(e.target.closest('input,button'))return;const id=Number(el.dataset.series);if(state.mode){state.selection.has(id)?state.selection.delete(id):state.selection.add(id);updateSelection()}else navigate('/series/'+id)});
 await mountAdvanced({scope:'series',container:content().querySelector('#series-query'),request,metadata:meta,onApply:()=>navigate('/series')});
 for(const [id,n] of [['series-prev',-1],['series-next',1]])content().querySelector('#'+id).onclick=()=>navigate('/series?page='+(page+n));
 content().querySelector('#new-series').onclick=async()=>{const name=prompt('Name of the new series');if(name?.trim()){try{await post('/series',{name});seriesPage()}catch(ex){toast(ex.message)}}};
 updateSelection();
}

async function seriesDetail(id){const d=await request('/series/'+id),s=d.series;
 const adv=getAdvanced('series_members')||{};
 const page=Math.max(1,Number(new URLSearchParams(location.search).get('page')||1));
 const ruleList=[{field:'series',op:'eq',value:s.name}];
 if(adv.filters?.rules?.length)ruleList.push(adv.filters);
 const [memberPage,meta]=await Promise.all([post('/query/books',{filters:{match:'all',rules:ruleList},sort:adv.sort?.length?adv.sort:[{field:'series_index',direction:'asc'},{field:'title',direction:'asc'}],search:adv.search||'',visibility:'all',page,per_page:200}),request('/query/metadata')]);
 const members=memberPage.items;
 content().innerHTML=title('series / workspace',s.name,`${d.members.length} books · edit reading order and membership.`)+`<div id="membership-query"></div><div class="header-row"><a href="/series" data-link class="btn">← all series</a><div class="row"><button class="btn" id="rename">edit series</button><button class="btn danger" id="delete">delete</button></div></div><div class="panel"><h2>reading order.</h2><div class="list">${members.map(b=>`<article class="list-item selectable" data-book="${b.id}">${selectBox(b.id)}<img class="thumb" src="/api/cover/${b.id}" onerror="this.style.visibility='hidden'" alt=""><div class="grow"><strong>${esc(b.title)}</strong><small>${esc(b.reading_status)}</small></div><label style="width:90px">volume<input type="number" step="0.1" data-index="${b.id}" value="${b.series_index??''}"></label><button class="btn" data-remove="${b.id}">remove</button></article>`).join('')||'<p>No books assigned yet.</p>'}</div><div class="pagination"><span>${members.length} of ${memberPage.total} matching books · page ${memberPage.page}/${memberPage.pages}</span><div class="pagination-actions"><button class="btn" id="member-prev" ${memberPage.page<=1?'disabled':''}>previous</button><button class="btn" id="member-next" ${memberPage.page>=memberPage.pages?'disabled':''}>next</button></div></div></div><section class="panel" style="margin-top:20px"><h2>add a book.</h2><div class="row"><input id="add-search" placeholder="search the library" class="grow"><button class="btn" id="search-books">search</button></div><div id="candidates" class="list" style="margin-top:15px"></div></section>`;await mountAdvanced({scope:'series_members',container:content().querySelector('#membership-query'),request,metadata:meta,onApply:()=>navigate('/series/'+id)});for(const [k,n] of [['member-prev',-1],['member-next',1]])content().querySelector('#'+k).onclick=()=>navigate('/series/'+id+'?page='+(page+n));content().querySelector('#rename').onclick=async()=>{const name=prompt('Series name',s.name);if(name?.trim()){await post('/series/'+id,{name},'PATCH');seriesDetail(id)}};content().querySelector('#delete').onclick=async()=>{if(confirm('Delete the series? Books and reading history will remain.')){await request('/series/'+id,{method:'DELETE'});navigate('/series')}};content().querySelectorAll('[data-index]').forEach(el=>el.onchange=async()=>{await post(`/series/${id}/members`,{book_id:Number(el.dataset.index),index:el.value===''?null:Number(el.value)},'PUT');toast('Volume saved')});content().querySelectorAll('[data-remove]').forEach(el=>el.onclick=async()=>{await request(`/series/${id}/members/${el.dataset.remove}`,{method:'DELETE'});seriesDetail(id)});content().querySelector('#search-books').onclick=async()=>{const q=content().querySelector('#add-search').value;const data=await request('/books?visibility=all&per_page=30&q='+encodeURIComponent(q));content().querySelector('#candidates').innerHTML=data.items.filter(b=>b.series!==s.name).map(b=>`<div class="list-item"><span class="grow">${esc(b.title)}</span><button class="btn" data-add="${b.id}">add</button></div>`).join('');content().querySelectorAll('[data-add]').forEach(el=>el.onclick=async()=>{await post(`/series/${id}/members`,{book_id:Number(el.dataset.add)},'PUT');seriesDetail(id)})};updateSelection()}
async function stats(){const d=await request('/stats'),c=d.counts;content().innerHTML=title('library / insights','the numbers.','Your library health and reading progress, computed locally.')+`<div class="metrics">${[['books',c.books],['series',c.series],['finished',d.statuses.find(x=>x.name==='finished')?.count||0],['reading hours',Math.round(c.minutes_read/60)],['cached covers',c.covers],['pending reviews',c.reviews]].map(([k,v])=>`<div class="metric"><strong>${Number(v).toLocaleString()}</strong><span>${k}</span></div>`).join('')}</div><div class="split"><section class="panel"><h2>reading status.</h2>${bars(d.statuses)}</section><section class="panel"><h2>file formats.</h2>${bars(d.formats)}</section></div><section class="panel" style="margin-top:20px"><h2>completion by month.</h2>${bars(d.months.map(x=>({name:x.month,count:x.count})))}</section>`}
function bars(arr){const max=Math.max(1,...arr.map(x=>x.count));return arr.map(x=>`<div class="bar-row"><span class="muted">${esc(x.name)}</span><div class="bar"><i style="width:${100*x.count/max}%"></i></div><strong>${x.count}</strong></div>`).join('')||'<p>No data yet.</p>'}
async function reviews(){
 const adv=getAdvanced('review')||{};const page=Math.max(1,Number(new URLSearchParams(location.search).get('page')||1));
 const [d,meta]=await Promise.all([post('/query/reviews',{filters:adv.filters||{match:'all',rules:[]},sort:adv.sort||[{field:'confidence',direction:'asc'}],search:adv.search||'',page,per_page:75}),request('/query/metadata')]);
 content().innerHTML=title('metadata / confirmation','review suggestions.','Filter by confidence, field, author, series, or metadata issue. Confirm or reject each suggestion.')+`
 <div id="review-query"></div><div class="section-heading"><div><span class="section-kicker">needs your attention</span><h2>pending suggestions <span class="count-chip">${d.total}</span></h2></div><a class="btn" href="/enrich" data-link>${icon('refresh')} enrichment</a></div>
 <div class="list review-list">${d.items.map(x=>`<article class="list-item review-item" data-book="${x.book_id}"><div class="grow"><span class="review-field">${esc(x.field)} · ${Math.round(x.confidence*100)}% confidence</span><strong>${esc(x.title)}</strong><p class="review-suggestion">${esc(x.suggested)}</p><small>${esc(x.reason)}</small></div><div class="actions row"><button class="btn primary" data-accept="${x.id}">${icon('check')} accept</button><button class="btn" data-reject="${x.id}">reject</button></div></article>`).join('')||emptyState('nothing to review','No unresolved suggestions match this view.','check')}</div><div class="pagination"><span>${d.total} suggestions · page ${d.page} of ${d.pages}</span><div class="pagination-actions"><button id="review-prev" class="btn" ${d.page<=1?'disabled':''}>previous</button><button id="review-next" class="btn" ${d.page>=d.pages?'disabled':''}>next</button></div></div>`;
 await mountAdvanced({scope:'review',container:content().querySelector('#review-query'),request,metadata:meta,onApply:()=>navigate('/review')});
 for(const [id,n] of [['review-prev',-1],['review-next',1]])content().querySelector('#'+id).onclick=()=>navigate('/review?page='+(page+n));
 for(const kind of ['accept','reject'])content().querySelectorAll(`[data-${kind}]`).forEach(el=>el.onclick=async()=>{try{await post(`/reviews/${el.dataset[kind]}?accept=${kind==='accept'}`,{});reviews()}catch(ex){toast(ex.message)}})
}

let monitor;
async function jobPage(kind){
 await getPreferences();clearInterval(monitor);const scanMode=kind==='scan';
 content().innerHTML=title(`tools / ${kind}`,scanMode?'scan folders.':'online enrichment.',scanMode?'Import metadata from a folder on this machine. Files remain untouched.':'Update existing entries from online catalogs in controlled batches.')+`
 <div class="split job-layout"><form class="panel" id="jobform"><div class="panel-eyebrow">${scanMode?'01 / source':'01 / options'}</div><h2>${scanMode?'start a scan':'run enrichment'}</h2><p class="panel-desc">${scanMode?'Add or update library records from files on disk.':'Your current metadata stays intact unless you explicitly change it.'}</p>${scanMode?`<label>absolute folder path<input name="folder" placeholder="D:/eBooks" required autocomplete="off"></label><label class="inline-check"><input type="checkbox" name="online" ${preferences['scan.online_by_default']?'checked':''}> enrich online during scan</label>`:`<div class="form-stack"><label>enrichment mode<select name="mode">${['missing','covers','all'].map(v=>`<option value="${v}" ${preferences['enrich.default_mode']===v?'selected':''}>${v}</option>`).join('')}</select></label><label>batch size<input name="limit" type="number" value="${preferences['enrich.batch_size']}" min="1" max="10000"></label><label>start after book ID<input name="start_after" type="number" value="0" min="0"></label></div>`}<div class="row job-actions"><button class="btn primary" type="submit">${icon(scanMode?'folder':'refresh')} start ${scanMode?'scan':'enrichment'}</button>${!scanMode?'<button class="btn" type="button" id="cancel">stop after current book</button>':''}</div></form>
 <section class="panel job-panel"><div class="panel-eyebrow">02 / activity</div><h2>job activity.</h2><div class="job-status-line"><span class="job-state-dot"></span><span id="job-status" aria-live="polite">checking for active jobs…</span></div><div class="job-meter"><span id="job-meter-fill"></span></div><div class="job-terminal-title"><span>event log</span><span>live</span></div><pre id="job-log" class="activity" role="log" aria-label="job events"></pre></section></div>`;
 const root=content(),form=root.querySelector('#jobform');
 form.onsubmit=async e=>{e.preventDefault();const data=Object.fromEntries(new FormData(e.target));if(scanMode)data.online=Boolean(data.online);else{data.limit=Number(data.limit);data.start_after=Number(data.start_after)};try{await post(`/jobs/${kind}`,data);poll()}catch(ex){toast(ex.message)}};
 root.querySelector('#cancel')?.addEventListener('click',()=>post('/jobs/enrich/cancel',{}).then(()=>toast('Stop requested')));
 async function poll(){try{const d=await request('/jobs/'+kind);if(!root.querySelector('#job-status'))return;root.querySelector('#job-status').textContent=`${d.status} · ${d.processed||0}${d.total?' / '+d.total:''}${d.current?' · '+d.current:''}${d.error?' · '+d.error:''}`;root.querySelector('.job-state-dot').dataset.state=d.status;root.querySelector('#job-meter-fill').style.width=d.total?`${Math.min(100,Math.max(0,(d.processed||0)*100/d.total))}%`:'0%';const log=root.querySelector('#job-log');const nearBottom=log.scrollHeight-log.scrollTop-log.clientHeight<75;log.textContent=(d.events||[]).slice(-150).join('\n');if(nearBottom||d.status==='running')log.scrollTop=log.scrollHeight}catch(e){}}
 poll();monitor=setInterval(poll,1400);
}

async function exportsPage(){
 await getPreferences();const options=await request('/options');
 const presets=[['json','complete backup','Preserve all indexed metadata and reading history.'],['goodreads','goodreads csv','Common reading-library import format.'],['storygraph','storygraph csv','Goodreads-shaped import compatible with StoryGraph.']];
 content().innerHTML=title('data / portability','export your library.','Your data remains portable. Download an archive or choose exactly which fields to include.')+`
 <div class="section-heading"><div><span class="section-kicker">ready to go</span><h2>export templates</h2></div></div><div class="export-grid">${presets.map(([key,label,desc])=>`<a class="export-preset" href="/api/exports/preset/${key}" download><span class="export-icon">${icon('download')}</span><strong>${label}</strong><p>${desc}</p><span class="preset-action">download ${icon('arrow-right')}</span></a>`).join('')}</div>
 <div class="section-heading"><div><span class="section-kicker">build your own</span><h2>custom export</h2></div></div>
 <div id="export-query"></div>
 <form id="exportform" class="panel custom-export"><div class="export-filter-row"><label>filter by title / author<input name="search" placeholder="optional search…"></label><label>reading status<select name="status"><option value="">all statuses</option>${options.statuses.map(s=>`<option value="${esc(s)}">${esc(statusLabel(s))}</option>`).join('')}</select></label></div><div class="export-field-title"><h3>columns to include</h3><span class="muted">choose at least one</span></div><div class="export-fields">${options.fields.map(f=>`<label class="field-choice"><input type="checkbox" name="fields" value="${esc(f)}" ${['title','authors','isbn13','status','started','finished'].includes(f)?'checked':''}><span>${esc(f.replaceAll('_',' '))}</span></label>`).join('')}</div><div class="export-actions"><button type="button" class="btn" id="fields-all">select all</button><button type="button" class="btn btn-subtle" id="fields-clear">clear</button><button class="btn primary" type="submit">${icon('download')} download csv</button></div></form>`;
 const meta=await request('/query/metadata');await mountAdvanced({scope:'exports',container:content().querySelector('#export-query'),request,metadata:meta,onApply:()=>toast('Export filters updated. Choose columns and download.')});
 const form=content().querySelector('#exportform');content().querySelector('#fields-all').onclick=()=>form.querySelectorAll('[name=fields]').forEach(x=>x.checked=true);content().querySelector('#fields-clear').onclick=()=>form.querySelectorAll('[name=fields]').forEach(x=>x.checked=false);
 form.onsubmit=async e=>{e.preventDefault();const data=new FormData(e.target);const payload={fields:data.getAll('fields'),status:data.get('status')||'',search:data.get('search')||'',advanced_query:getAdvanced('exports')};if(!payload.fields.length)return toast('Select at least one field');try{const r=await fetch('/api/exports/custom',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});if(!r.ok)throw Error('Export failed');const blob=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='bookledger-custom.csv';a.click();setTimeout(()=>URL.revokeObjectURL(a.href),3000)}catch(ex){toast(ex.message)}};
}

const settingsGroups=[
 ['library','library & folders','Choose which files appear and how the collection is displayed.',[
 ['library.include_subfolders','include books in nested folders','checkbox','When filtering by a source folder, include books in its subfolders.'],
 ['library.default_visibility','default visibility','select',['visible','hidden','all']],
 ['library.default_sort','default sorting','select',['title','author','recent','series']],
 ['library.page_size','books per page','number',[12,200]],
 ['library.card_density','card density','select',['compact','comfortable','spacious']],
 ['library.show_covers','show cover art','checkbox','Use the book covers in the library grid.'],
 ['library.show_status_badges','show reading labels','checkbox','Display reading status on catalog cards.']]],
 ['reading','reading & quick sort','Control the review queue and reading presentation.',[
 ['reading.default_queue','default review queue','select',['unanswered','all']],
 ['reading.show_covers','show covers in reading review','checkbox','Show cover thumbnails while reviewing.'],
 ['quick_sort.include_classified','include already classified books','checkbox','Include books with an existing reading status.'],
 ['quick_sort.show_metadata','show quick sort metadata editor','checkbox','Display book details beside the sorting card.']]],
 ['processing','scanning & enrichment','Defaults for new jobs. Changes never launch a scan automatically.',[
 ['scan.online_by_default','online metadata during scans','checkbox','Connect to metadata catalogs when beginning a new scan.'],
 ['enrich.default_mode','default enrichment mode','select',['missing','covers','all']],
 ['enrich.batch_size','default enrichment batch size','number',[1,10000]]]],
 ['exports','exports','Choose your preferred export starting point.',[
 ['exports.default_format','preferred export format','select',['json','goodreads','storygraph']]]]
];
async function settingsPage(){
 const response=await request('/settings');preferences=response.values;
 const field=(entry)=>{const [key,label,type,meta]=entry;const value=preferences[key];const control=type==='checkbox'?`<input type="checkbox" name="${key}" ${value?'checked':''}>`:type==='select'?`<select name="${key}">${meta.map(v=>`<option value="${esc(v)}" ${value===v?'selected':''}>${esc(v.replaceAll('_',' '))}</option>`).join('')}</select>`:`<input name="${key}" type="number" min="${meta[0]}" max="${meta[1]}" step="1" value="${value}">`;return `<label class="setting-field ${type==='checkbox'?'setting-toggle':''}"><span class="setting-label"><strong>${esc(label)}</strong>${type==='checkbox'?`<small>${esc(meta)}</small>`:''}</span>${control}</label>`}
 content().innerHTML=title('preferences / control center','settings.','Changes are stored in your local SQLite database. They apply across browsers using this server.')+`<div class="settings-layout"><aside class="settings-index" aria-label="settings sections">${settingsGroups.map(([id,name])=>`<a href="#settings-${id}">${name}</a>`).join('')}</aside><form id="settings-form" class="settings-form">${settingsGroups.map(([id,name,description,fields])=>`<section class="panel settings-section" id="settings-${id}"><div class="settings-section-header"><h2>${name}</h2><p>${description}</p></div><div class="settings-fields">${fields.map(field).join('')}</div></section>`).join('')}<div class="settings-actions"><span class="muted" id="settings-state" role="status">unsaved changes will be kept until you save</span><button type="button" class="btn" id="reset-settings">restore defaults</button><button class="btn primary" type="submit">save settings</button></div></form></div>`;
 const form=content().querySelector('#settings-form');const notice=content().querySelector('#settings-state');
 form.addEventListener('input',()=>notice.textContent='unsaved changes');
 form.onsubmit=async event=>{event.preventDefault();const values={};for(const [, , ,fields] of settingsGroups)for(const [key,,type] of fields){const control=form.elements.namedItem(key);values[key]=type==='checkbox'?control.checked:type==='number'?Number(control.value):control.value}try{const result=await post('/settings',values,'PATCH');preferences=result.values;notice.textContent='all preferences saved';toast('Settings saved')}catch(error){notice.textContent=error.message;toast(error.message)}};
 content().querySelector('#reset-settings').onclick=async()=>{if(!confirm('Restore default settings? Your books and reading history will not change.'))return;try{const result=await post('/settings/reset',{});preferences=result.values;settingsPage();toast('Defaults restored')}catch(error){toast(error.message)}}
}
async function render(){clearInterval(monitor);exitSelection();shell();const path=decodeURI(location.pathname);try{if(path==='/')await library();else if(/^\/book\/\d+$/.test(path))await detail(Number(path.split('/')[2]));else if(path==='/reading')await reading();else if(path==='/quick-sort')await quick();else if(path==='/series')await seriesPage();else if(/^\/series\/\d+$/.test(path))await seriesDetail(Number(path.split('/')[2]));else if(path==='/stats')await stats();else if(path==='/review')await reviews();else if(path==='/scan'||path==='/enrich')await jobPage(path.slice(1));else if(path==='/exports')await exportsPage();else if(path==='/settings')await settingsPage();else content().innerHTML=title('404','page not found.')}catch(ex){content().innerHTML=title('error','something went wrong.')+`<div class="panel"><p>${esc(ex.message)}</p><button class="btn" onclick="location.reload()">retry</button></div>`}}render();
