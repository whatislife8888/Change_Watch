/*
 * picker.js — runs INSIDE the sandboxed picker iframe (injected inline with a CSP nonce by frame.py).
 *
 * What it does: outlines the element under the pointer, shows a stable CSS selector for it, and on click
 * sends that selector to the parent page with postMessage. It also draws persistent outlines for every
 * region already picked (watch = lume, ignore = ruby, number = blued).
 *
 * Messages
 *   parent -> frame: {type:'mode', mode}  {type:'highlight', selectors:{watch:[], ignore:[], number:[]}}
 *   parent -> frame (touch screens): {type:'parent'}  {type:'confirm'}  {type:'cancel'}
 *   frame -> parent: {type:'ready'}  {type:'hover', selector}  {type:'pick', selector, textPreview, mode}
 *                    {type:'candidate', selector, textPreview, atTop}   (touch: a tapped element waiting for confirmation)
 * Keys: ArrowUp selects the parent element, Enter picks, Esc cancels.
 * Touch: there is no hover and no arrow key, so a tap only SELECTS an element (a candidate); the parent page
 * shows "Select parent / Add / Cancel" buttons that send the messages above.
 *
 * The iframe has sandbox="allow-scripts" WITHOUT allow-same-origin, so this script (and anything else in
 * the page) runs in an opaque origin: it cannot read our cookies or touch the parent page's DOM.
 */
(function () {
  var mode = 'watch';
  var current = null;
  var lastPointer = 'mouse';
  var picked = { watch: [], ignore: [], number: [] };
  var COLORS = { watch: '#1D8A5B', ignore: '#B8163F', number: '#2340C8' };

  var hover = document.createElement('div');
  hover.id = '__cw_hover';
  var label = document.createElement('div');
  label.id = '__cw_label';
  var layer = document.createElement('div');
  layer.id = '__cw_layer';
  document.documentElement.appendChild(layer);
  document.documentElement.appendChild(hover);
  document.documentElement.appendChild(label);

  function isOurs(el) {
    return el && (el.id === '__cw_hover' || el.id === '__cw_label' || el.id === '__cw_layer' || (layer.contains && layer.contains(el)));
  }

  /* ---------- selector algorithm: prefer stable over short ---------- */
  function looksRandom(s) {
    if (!s) return true;
    return /\d{4,}/.test(s) ||                       // long digit runs: item-83721
      /^[a-f0-9]{6,}$/i.test(s) ||                    // hash-like: 3fa9c2
      /^(css|sc|jsx|emotion|styled|chakra|mui)-/i.test(s) || // CSS-in-JS generated
      /[a-z][A-Z0-9]{4,}[a-z]?$/.test(s) && /[0-9]/.test(s) || // camelHash0x9
      /__[A-Za-z0-9_-]{5,}$/.test(s) ||                // CSS modules: title__x7Hk2
      s.length > 40;
  }
  function esc(s) { return window.CSS && CSS.escape ? CSS.escape(s) : s.replace(/[^a-zA-Z0-9_-]/g, '\\$&'); }
  function count(sel) {
    try { return Array.prototype.filter.call(document.querySelectorAll(sel), function (n) { return !isOurs(n); }).length; }
    catch (e) { return 0; }
  }
  function unique(sel) { return count(sel) === 1; }

  function selectorFor(el) {
    var tag = el.tagName.toLowerCase();
    if (el.id && !looksRandom(el.id) && unique('#' + esc(el.id))) return '#' + esc(el.id);
    var attrs = ['data-testid', 'data-test', 'itemprop', 'aria-label', 'name'];
    for (var i = 0; i < attrs.length; i++) {
      var v = el.getAttribute(attrs[i]);
      if (v && v.length < 60 && !looksRandom(v)) {
        var s = tag + '[' + attrs[i] + '="' + v.replace(/"/g, '\\"') + '"]';
        if (unique(s)) return s;
      }
    }
    var parts = [];
    var node = el;
    var depth = 0;
    while (node && node.nodeType === 1 && node !== document.body && node !== document.documentElement && depth < 6) {
      if (node !== el && node.id && !looksRandom(node.id)) {
        parts.unshift('#' + esc(node.id));
        var withId = parts.join(' > ');
        if (unique(withId)) return withId;
        break;
      }
      var step = node.tagName.toLowerCase();
      var classes = Array.prototype.filter.call(node.classList, function (c) { return !looksRandom(c); }).slice(0, 2);
      if (classes.length) step += classes.map(function (c) { return '.' + esc(c); }).join('');
      var parent = node.parentElement;
      if (parent) {
        var sameStep = Array.prototype.filter.call(parent.children, function (c) { try { return c.matches(step); } catch (e) { return false; } });
        if (sameStep.length > 1) {
          var sameTag = Array.prototype.filter.call(parent.children, function (c) { return c.tagName === node.tagName; });
          step += ':nth-of-type(' + (sameTag.indexOf(node) + 1) + ')';
        }
      }
      parts.unshift(step);
      var sel = parts.join(' > ');
      if (unique(sel)) return sel;
      node = parent;
      depth++;
    }
    return parts.join(' > ');
  }

  /* ---------- drawing ---------- */
  function box(el) {
    var r = el.getBoundingClientRect();
    return { x: r.left + window.scrollX, y: r.top + window.scrollY, w: r.width, h: r.height };
  }
  function place(div, b) {
    div.style.left = b.x + 'px'; div.style.top = b.y + 'px'; div.style.width = b.w + 'px'; div.style.height = b.h + 'px';
  }
  function showHover(el) {
    if (!el) { hover.style.display = 'none'; label.style.display = 'none'; return; }
    var b = box(el);
    hover.style.display = 'block';
    hover.style.borderColor = COLORS[mode];
    hover.style.background = COLORS[mode] + '1f';
    place(hover, b);
    var sel = selectorFor(el);
    label.textContent = sel;
    label.style.display = 'block';
    label.style.background = COLORS[mode];
    label.style.left = b.x + 'px';
    label.style.top = Math.max(0, b.y - 24) + 'px';
    parent.postMessage({ type: 'hover', selector: sel }, '*');
  }
  function redraw() {
    while (layer.firstChild) layer.removeChild(layer.firstChild);
    ['watch', 'ignore', 'number'].forEach(function (kind) {
      (picked[kind] || []).forEach(function (sel) {
        var nodes;
        try { nodes = document.querySelectorAll(sel); } catch (e) { return; }
        Array.prototype.forEach.call(nodes, function (n) {
          if (isOurs(n)) return;
          var d = document.createElement('div');
          d.className = '__cw_pick __cw_' + kind;
          place(d, box(n));
          layer.appendChild(d);
        });
      });
    });
  }

  /* ---------- events ---------- */
  document.addEventListener('mouseover', function (e) {
    if (isOurs(e.target)) return;
    current = e.target;
    showHover(current);
  }, true);
  document.addEventListener('pointerdown', function (e) { lastPointer = e.pointerType || 'mouse'; }, true);
  document.addEventListener('click', function (e) {
    e.preventDefault();
    e.stopPropagation();
    if (isOurs(e.target)) return;
    if (lastPointer === 'touch' || lastPointer === 'pen') {
      // Touch: select a candidate; the parent page confirms it (or widens it to the parent element).
      current = e.target;
      showHover(current);
      sendCandidate();
      return;
    }
    pick(current || e.target);
  }, true);
  document.addEventListener('submit', function (e) { e.preventDefault(); }, true);
  document.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowUp' && current && current.parentElement && current.parentElement !== document.documentElement) {
      e.preventDefault();
      current = current.parentElement;
      showHover(current);
    } else if (e.key === 'Enter' && current) {
      e.preventDefault();
      pick(current);
    } else if (e.key === 'Escape') {
      current = null;
      showHover(null);
    }
  }, true);
  window.addEventListener('resize', redraw);

  function sendCandidate() {
    if (!current) { parent.postMessage({ type: 'candidate', selector: null }, '*'); return; }
    var text = (current.innerText || current.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 160);
    // atTop: the element's parent is <body>, so widening further would just mean "the whole page".
    var up = current.parentElement;
    var atTop = !up || up === document.body || up === document.documentElement;
    parent.postMessage({ type: 'candidate', selector: selectorFor(current), textPreview: text, atTop: atTop }, '*');
  }

  function pick(el) {
    if (!el) return;
    var sel = selectorFor(el);
    var text = (el.innerText || el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 300);
    parent.postMessage({ type: 'pick', selector: sel, textPreview: text, mode: mode }, '*');
  }

  window.addEventListener('message', function (e) {
    if (e.source !== parent) return;
    var data = e.data || {};
    if (data.type === 'mode' && COLORS[data.mode]) { mode = data.mode; if (current) showHover(current); }
    if (data.type === 'highlight' && data.selectors) { picked = data.selectors; redraw(); }
    if (data.type === 'parent' && current && current.parentElement && current.parentElement !== document.body
        && current.parentElement !== document.documentElement) {
      current = current.parentElement;
      showHover(current);
      sendCandidate();
    }
    if (data.type === 'confirm' && current) { pick(current); current = null; showHover(null); sendCandidate(); }
    if (data.type === 'cancel') { current = null; showHover(null); sendCandidate(); }
  });

  window.addEventListener('load', redraw);
  parent.postMessage({ type: 'ready' }, '*');
})();
