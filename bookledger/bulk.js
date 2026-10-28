(()=>{'use strict';
for(const bar of document.querySelectorAll('[data-bulk-toolbar]')){
  const kind=bar.dataset.bulkToolbar;
  const inputs=()=>[...document.querySelectorAll(`.bulk-item[data-bulk-kind="${kind}"] .bulk-select`)];
  const selectAll=bar.querySelector('[data-bulk-all]');const count=bar.querySelector('.bulk-count');
  const submit=bar.querySelector('[type="submit"]');const action=bar.querySelector('[name="action"]');
  const generated=bar.querySelector('[data-bulk-inputs]');
  const refresh=()=>{const items=inputs(),checked=items.filter(x=>x.checked);count.textContent=`${checked.length} selected`;submit.disabled=!checked.length||!action.value;selectAll.checked=!!items.length&&checked.length===items.length;selectAll.indeterminate=checked.length>0&&checked.length<items.length;for(const el of items)el.closest('.bulk-item')?.classList.toggle('is-selected',el.checked)};
  selectAll.addEventListener('change',()=>{inputs().forEach(x=>x.checked=selectAll.checked);refresh()});
  bar.querySelector('[data-bulk-clear]').addEventListener('click',()=>{inputs().forEach(x=>x.checked=false);refresh()});
  document.addEventListener('change',e=>{if(e.target.matches(`.bulk-item[data-bulk-kind="${kind}"] .bulk-select`)||e.target===action)refresh()});
  bar.addEventListener('submit',e=>{generated.replaceChildren();const checked=inputs().filter(x=>x.checked);if(!checked.length||!action.value){e.preventDefault();return}if((kind==='series'||action.value==='unassign_series')&&!confirm(`Apply ${action.value.replace('_',' ')} to ${checked.length} selected items? Books and reading history will be kept.`)){e.preventDefault();return}checked.forEach(x=>{const el=document.createElement('input');el.type='hidden';el.name='ids';el.value=x.value;generated.append(el)})});refresh();
}
})();
