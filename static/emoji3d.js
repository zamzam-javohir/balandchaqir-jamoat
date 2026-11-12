// 3D ikonkalar: Microsoft Fluent Emoji 3D (MIT litsenziya), o'zimizning serverda. Matndagi emoji -> 3D rasm.
(function () {
  const MAP = {"📱": "mobile_phone.png", "⚠": "warning.png", "⏳": "hourglass_not_done.png", "❌": "cross_mark.png", "🤝": "handshake.png", "✅": "check_mark_button.png", "☀": "sun.png", "🕋": "kaaba.png", "🧭": "compass.png", "🕌": "mosque.png", "📝": "memo.png", "✏": "pencil.png", "⚙": "gear.png", "🚗": "automobile.png", "🙋": "person_raising_hand.png", "📞": "telephone_receiver.png", "🗑": "wastebasket.png", "📅": "calendar.png", "💺": "seat.png", "💬": "speech_balloon.png", "📍": "round_pushpin.png", "⚽": "soccer_ball.png", "🎉": "party_popper.png", "➕": "plus.png", "👤": "person.png", "🛡": "shield.png", "✖": "multiply.png", "🌄": "sunrise_over_mountains.png", "🌤": "sun_behind_small_cloud.png", "⛅": "sun_behind_cloud.png", "🌇": "sunset.png", "🌙": "crescent_moon.png", "🚶": "person_walking.png", "📖": "open_book.png", "📿": "prayer_beads.png", "👥": "busts_in_silhouette.png", "⏰": "alarm_clock.png", "🕒": "three_oclock.png"};
  const keys = Object.keys(MAP).sort((a, b) => b.length - a.length);
  const reAll = new RegExp('(' + keys.join('|') + ')\\uFE0F?', 'gu');
  const reHas = new RegExp('(' + keys.join('|') + ')', 'u');
  const SKIP = /^(SCRIPT|STYLE|TEXTAREA|INPUT|OPTION|SELECT|TITLE)$/;
  function img(ch) {
    const i = document.createElement('img');
    i.className = 'e3'; i.src = '/static/icons/' + MAP[ch]; i.alt = ch; i.draggable = false; i.decoding = 'async';
    return i;
  }
  function iconize(root) {
    if (!root) return;
    const nodes = [];
    const w = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, { acceptNode(n) {
      if (!n.nodeValue || !reHas.test(n.nodeValue)) return NodeFilter.FILTER_REJECT;
      for (let p = n.parentNode; p && p !== root.parentNode; p = p.parentNode) { if (SKIP.test(p.nodeName) || (p.nodeName || '').toLowerCase() === 'svg') return NodeFilter.FILTER_REJECT; }
      return NodeFilter.FILTER_ACCEPT; } });
    while (w.nextNode()) nodes.push(w.currentNode);
    nodes.forEach(n => {
      const frag = document.createDocumentFragment(); const s = n.nodeValue; let last = 0;
      for (const m of s.matchAll(reAll)) {
        if (m.index > last) frag.appendChild(document.createTextNode(s.slice(last, m.index)));
        frag.appendChild(img(m[1])); last = m.index + m[0].length;
      }
      if (last < s.length) frag.appendChild(document.createTextNode(s.slice(last)));
      n.parentNode.replaceChild(frag, n);
    });
  }
  window.iconize = iconize;
  function watch(sel) {
    const el = document.querySelector(sel); if (!el) return;
    new MutationObserver(() => iconize(el)).observe(el, { childList: true, subtree: true });
    iconize(el);
  }
  document.addEventListener('DOMContentLoaded', () => ['#view', '#sheetBox', '#toast'].forEach(watch));
  if (document.readyState !== 'loading') ['#view', '#sheetBox', '#toast'].forEach(watch);
})();
