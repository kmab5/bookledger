(() => {
  'use strict';
  // This menu supplements (and does not replace) the existing series editor menu.
  const menu = document.createElement('div');
  menu.className = 'global-context-menu';
  menu.role = 'menu';
  menu.setAttribute('aria-label', 'context actions');
  menu.hidden = true;
  document.body.append(menu);
  let openedFor = null, restoreFocus = null, touchTimer = null;
  let touchStart = null, suppressClickUntil = 0;
  const pathname = location.pathname;
  const csrf = document.querySelector('meta[name="bookledger-csrf"]')?.content;
  const escapeSelector = s => CSS.escape(s);
  const bookFromHref = href => /^\/book\/(\d+)(?:$|[/?#])/.exec(href || '')?.[1];
  const seriesFromHref = href => /^\/series\/(\d+)(?:$|[/?#])/.exec(href || '')?.[1];
  const area = pathname === '/' ? 'library' : pathname.split('/').filter(Boolean)[0] || 'library';
  const canUse = element => !element.closest('input,select,textarea,[contenteditable="true"],.global-context-menu,[data-menu]');

  function close() {
    if (menu.hidden) return;
    menu.hidden = true;
    menu.replaceChildren();
    openedFor = null;
    if (restoreFocus?.isConnected) restoreFocus.focus({ preventScroll: true });
    restoreFocus = null;
  }
  function item(label, callback, opts = {}) {
    const button = document.createElement('button');
    button.type = 'button';
    button.role = 'menuitem';
    button.textContent = label;
    if (opts.danger) button.classList.add('menu-danger');
    button.addEventListener('click', () => { close(); callback(); });
    menu.append(button);
  }
  function separator() {
    const div = document.createElement('div'); div.role = 'separator';
    div.className = 'context-separator'; menu.append(div);
  }
  function visit(url) { location.assign(url); }
  function copy(value) {
    if (navigator.clipboard?.writeText) navigator.clipboard.writeText(value).catch(() => fallbackCopy(value));
    else fallbackCopy(value);
  }
  function fallbackCopy(value) {
    const input = document.createElement('textarea'); input.value = value;
    input.style.position = 'fixed'; input.style.opacity = '0'; document.body.append(input);
    input.select(); document.execCommand('copy'); input.remove();
  }
  function submit(url, fields, message) {
    if (message && !confirm(message)) return;
    if (!csrf) { alert('Missing form token. Reload this page and try again.'); return; }
    const form = document.createElement('form'); form.method = 'post'; form.action = url;
    Object.entries({ ...fields, csrf }).forEach(([name, value]) => {
      const input = document.createElement('input'); input.type = 'hidden';
      input.name = name; input.value = value; form.append(input);
    });
    document.body.append(form); form.submit();
  }
  function targetInfo(node) {
    const bookCard = node.closest('.book-card,[data-book-id]');
    const bookAnchor = node.closest('a[href^="/book/"]') || bookCard?.querySelector('a[href^="/book/"]');
    const bookId = bookCard?.dataset.bookId || bookFromHref(bookAnchor?.getAttribute('href')) || (/^\/book\/(\d+)/.exec(pathname)?.[1]);
    const seriesAnchor = node.closest('a[href^="/series/"]');
    const seriesId = seriesFromHref(seriesAnchor?.getAttribute('href'));
    const card = node.closest('.panel,.stat-chip,.stat-card,.series-card,.qs-card,article,section');
    return { bookId, seriesId, card, link: node.closest('a[href]') };
  }
  function build(node) {
    const { bookId, seriesId, link } = targetInfo(node);
    // Contextual actions always first. Never perform destructive changes without an explicit click.
    const selectable = node.closest('.bulk-item');
    if (selectable && document.querySelector(`[data-bulk-toolbar="${selectable.dataset.bulkKind}"]`)) {
      item('select item', () => window.BookLedgerBulk?.start(selectable));
      separator();
    }
    if (bookId) {
      item('open book details', () => visit('/book/' + bookId));
      item('copy book link', () => copy(location.origin + '/book/' + bookId));
      if (area === 'library' || area === 'book' || area === 'reading' || area === 'review' || area === 'quick-sort') {
        separator();
        item('mark as read', () => submit('/book/' + bookId + '/reading', { status:'finished' }));
        item('mark as not read', () => submit('/book/' + bookId + '/reading', { status:'not_read' }));
        item('mark as reading', () => submit('/book/' + bookId + '/reading', { status:'reading' }));
        separator();
        item('hide book', () => submit('/book/' + bookId + '/visibility', { hidden:'1' }), { danger:true });
        item('restore hidden book', () => submit('/book/' + bookId + '/visibility', { hidden:'0' }));
      }
    } else if (seriesId) {
      item('open series', () => visit('/series/' + seriesId));
      item('edit series', () => visit('/series/' + seriesId + '#series-settings'));
      item('copy series link', () => copy(location.origin + '/series/' + seriesId));
    } else {
      switch (area) {
        case 'library':
          item('quick sort unreviewed books', () => visit('/quick-sort'));
          item('show hidden books', () => visit('/?visibility=hidden'));
          item('show all books', () => visit('/?visibility=all'));
          item('scan a folder', () => visit('/scan'));
          break;
        case 'scan':
          item('scan another folder', () => visit('/scan'));
          item('view library', () => visit('/'));
          item('open enrichment', () => visit('/enrich'));
          break;
        case 'enrich':
          item('open enrichment controls', () => visit('/enrich'));
          item('review suggestions', () => visit('/review'));
          item('scan files', () => visit('/scan'));
          break;
        case 'exports':
          item('open export builder', () => visit('/exports'));
          item('view library statistics', () => visit('/stats'));
          break;
        case 'stats':
          item('open book library', () => visit('/'));
          item('view reading queue', () => visit('/reading'));
          item('view series', () => visit('/series'));
          item('open exports', () => visit('/exports'));
          break;
        case 'series':
          item('browse series', () => visit('/series'));
          item('view unsorted books', () => visit('/?sort=series'));
          item('start quick sort', () => visit('/quick-sort'));
          break;
        case 'quick-sort':
          item('open queue settings', () => document.querySelector('.qs-filters select')?.focus());
          item('open full reading review', () => visit('/reading'));
          item('browse books', () => visit('/'));
          break;
        case 'review':
          item('review reading statuses', () => visit('/reading'));
          item('enrich metadata', () => visit('/enrich'));
          break;
        case 'reading':
          item('start quick sort', () => visit('/quick-sort'));
          item('browse books', () => visit('/'));
          break;
        case 'duplicates':
          item('open book library', () => visit('/'));
          item('review metadata', () => visit('/review'));
          break;
        default:
          item('browse library', () => visit('/'));
      }
      if (link?.href && link.origin === location.origin) {
        separator(); item('open link', () => visit(link.href));
        item('copy link', () => copy(link.href));
      }
    }
    separator();
    item('copy page link', () => copy(location.href));
    item('refresh page', () => location.reload());
  }
  function open(node, x, y) {
    close();
    restoreFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    openedFor = node;
    build(node);
    menu.hidden = false;
    const bounds = menu.getBoundingClientRect();
    menu.style.left = Math.max(8, Math.min(x, innerWidth - bounds.width - 8)) + 'px';
    menu.style.top = Math.max(8, Math.min(y, innerHeight - bounds.height - 8)) + 'px';
    menu.querySelector('button')?.focus({ preventScroll:true });
  }
  document.addEventListener('contextmenu', event => {
    if (!canUse(event.target)) return;
    event.preventDefault(); open(event.target, event.clientX, event.clientY);
  });
  document.addEventListener('keydown', event => {
    if (menu.hidden) {
      if ((event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) && canUse(event.target)) {
        event.preventDefault(); const rect = event.target.getBoundingClientRect(); open(event.target, rect.left + 15, rect.bottom + 5);
      }
      return;
    }
    const buttons = Array.from(menu.querySelectorAll('button'));
    const current = buttons.indexOf(document.activeElement);
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    if (event.key === 'ArrowDown') { event.preventDefault(); buttons[(current+1)%buttons.length]?.focus(); }
    if (event.key === 'ArrowUp') { event.preventDefault(); buttons[(current-1+buttons.length)%buttons.length]?.focus(); }
    if (event.key === 'Home') { event.preventDefault(); buttons[0]?.focus(); }
    if (event.key === 'End') { event.preventDefault(); buttons[buttons.length-1]?.focus(); }
    if (event.key === 'Tab') close();
  });
  document.addEventListener('pointerdown', event => {
    if (!menu.hidden && !menu.contains(event.target)) close();
    if (event.pointerType !== 'touch' || !canUse(event.target)) return;
    const node = event.target, x = event.clientX, y = event.clientY;
    touchStart = { x, y }; clearTimeout(touchTimer);
    touchTimer = setTimeout(() => { suppressClickUntil = Date.now() + 700; open(node, x, y); }, 600);
  });
  document.addEventListener('pointermove', event => {
    if (touchStart && Math.hypot(event.clientX-touchStart.x, event.clientY-touchStart.y) > 12) clearTimeout(touchTimer);
  });
  for (const eventName of ['pointerup','pointercancel','scroll']) document.addEventListener(eventName, () => { clearTimeout(touchTimer); touchStart=null; }, { passive:true, capture:true });
  document.addEventListener('click', event => {
    if (Date.now() < suppressClickUntil && !menu.contains(event.target)) { event.preventDefault(); event.stopPropagation(); suppressClickUntil=0; }
    if (!menu.hidden && !menu.contains(event.target)) close();
  }, true);
  window.addEventListener('resize', close);
})();
