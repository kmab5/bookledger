(()=>{'use strict';
const bars=[...document.querySelectorAll('[data-bulk-toolbar]')];
if(!bars.length)return;
let activeBar=null;
const checks=bar=>[...document.querySelectorAll(`.bulk-item[data-bulk-kind="${bar.dataset.bulkToolbar}"] .bulk-select`)];
const refresh=bar=>{
 const all=checks(bar),selected=all.filter(x=>x.checked),selectAll=bar.querySelector('[data-bulk-all]');
 bar.querySelector('.bulk-count').textContent=`${selected.length} selected`;
 bar.querySelector('[type="submit"]').disabled=!selected.length||!bar.querySelector('[name="action"]').value;
 selectAll.checked=!!all.length&&selected.length===all.length;
 selectAll.indeterminate=selected.length>0&&selected.length<all.length;
 all.forEach(x=>x.closest('.bulk-item')?.classList.toggle('is-selected',x.checked));
};
function exit(){
 bars.forEach(bar=>{checks(bar).forEach(x=>{x.checked=false;x.closest('.bulk-item')?.classList.remove('is-selected')});bar.hidden=true;bar.querySelector('[name="action"]').value='';refresh(bar)});
 document.body.classList.remove('bulk-mode');activeBar=null;
}
function start(element){
 const container=element?.closest('.bulk-item');if(!container)return false;
 const kind=container.dataset.bulkKind, checkbox=container.querySelector('.bulk-select');
 const bar=bars.find(x=>x.dataset.bulkToolbar===kind);if(!bar||!checkbox)return false;
 if(activeBar!==bar){exit();activeBar=bar;bar.hidden=false;document.body.classList.add('bulk-mode')}
 checkbox.checked=true;refresh(bar);return true;
}
window.BookLedgerBulk={start,exit};
for(const bar of bars){
 bar.hidden=true;
 const selectAll=bar.querySelector('[data-bulk-all]');
 const action=bar.querySelector('[name="action"]');
 selectAll.addEventListener('change',()=>{checks(bar).forEach(x=>x.checked=selectAll.checked);refresh(bar)});
 bar.querySelector('[data-bulk-clear]').addEventListener('click',exit);
 action.addEventListener('change',()=>refresh(bar));
 bar.addEventListener('submit',e=>{
  const selected=checks(bar).filter(x=>x.checked),generated=bar.querySelector('[data-bulk-inputs]');generated.replaceChildren();
  if(!selected.length||!action.value){e.preventDefault();return}
  if((bar.dataset.bulkToolbar==='series'||action.value==='unassign_series')&&!confirm(`Apply ${action.value.replaceAll('_',' ')} to ${selected.length} selected items? Books and reading history will be kept.`)){e.preventDefault();return}
  selected.forEach(x=>{const input=document.createElement('input');input.type='hidden';input.name='ids';input.value=x.value;generated.append(input)});
 });
}
document.addEventListener('change',e=>{if(e.target.matches('.bulk-item .bulk-select')&&activeBar)refresh(activeBar)});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&activeBar&&!e.target.closest('select'))exit()});
})();
