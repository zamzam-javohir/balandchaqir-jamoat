const tg = window.Telegram && Telegram.WebApp;
if (tg) { try { tg.ready(); tg.expand(); tg.setHeaderColor('#0b3d2e'); tg.setBackgroundColor('#f3f1e8'); } catch (e) {} }
const $ = (s, r = document) => r.querySelector(s);
const view = $('#view');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const PRAYERS = [['bomdod', 'Bomdod'], ['peshin', 'Peshin'], ['asr', 'Asr'], ['shom', 'Shom'], ['xufton', 'Xufton']];
const state = { me: null, tab: localStorage.getItem('tab') || 'namoz', sub: 'vaqt', prayer: 'bomdod', cdTimer: null, prayerData: null, offline: !tg || !tg.initData };

// ---------- yordamchilar ----------
function toast(msg, err) {
  const t = $('#toast'); t.textContent = msg; t.className = 'toast' + (err ? ' err' : '');
  clearTimeout(toast._t); toast._t = setTimeout(() => t.classList.add('hidden'), 3200);
}
async function api(path, method = 'GET', body) {
  const r = await fetch(path, { method, headers: { 'Content-Type': 'application/json', 'X-Init-Data': (tg && tg.initData) || '' }, body: body ? JSON.stringify(body) : undefined });
  let data = null; try { data = await r.json(); } catch (e) {}
  if (!r.ok) { const m = (data && (data.detail && (typeof data.detail === 'string' ? data.detail : 'Xato ma\'lumot'))) || 'Xatolik yuz berdi'; const er = new Error(m); er.status = r.status; throw er; }
  return data;
}
const haptic = (t = 'light') => { try { tg.HapticFeedback.impactOccurred(t); } catch (e) {} };
function openSheet(html) { $('#sheetBox').innerHTML = html; $('#sheet').classList.remove('hidden'); }
function closeSheet() { $('#sheet').classList.add('hidden'); }
$('.sheet-bg').onclick = closeSheet;
const pad = n => String(n).padStart(2, '0');
const fmtCd = s => { s = Math.max(0, s); return `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s % 3600 / 60))}:${pad(s % 60)}`; };
const prayerName = k => (PRAYERS.find(p => p[0] === k) || [k, k])[1];
function minusMin(hhmm, m) { if (!hhmm) return ''; const [h, mi] = hhmm.split(':').map(Number); let t = (h * 60 + mi - m + 1440) % 1440; return `${pad(Math.floor(t / 60))}:${pad(t % 60)}`; }
function tgLink(c) {
  if (c.username) return `<a href="https://t.me/${esc(c.username)}" data-tgl="https://t.me/${esc(c.username)}">@${esc(c.username)}</a>`;
  return `<a href="tg://user?id=${c.id}">${esc(c.name)}</a>`;
}
document.addEventListener('click', e => {
  const a = e.target.closest('a[data-tgl]'); if (a && tg && tg.openTelegramLink) { e.preventDefault(); tg.openTelegramLink(a.dataset.tgl); }
});

// ---------- navigatsiya ----------
document.querySelectorAll('#tabs button').forEach(b => b.onclick = () => go(b.dataset.tab));
function go(tab) {
  state.tab = tab; localStorage.setItem('tab', tab);
  document.querySelectorAll('#tabs button').forEach(b => b.classList.toggle('on', b.dataset.tab === tab));
  clearInterval(state.cdTimer); stopCompass();
  render();
}
async function render() {
  if (state.offline) { view.innerHTML = `<div class="card lock"><div class="ic">📱</div><h2>Telegram ichida oching</h2><p class="muted">Bu ilova faqat Telegram bot orqali ishlaydi. Botni oching va «Jamoat» tugmasini bosing.</p></div>`; return; }
  try {
    if (!state.me) state.me = await api('/api/me');
    const t = state.tab;
    if (t === 'namoz') return renderNamoz();
    if (t === 'profil') return renderProfil();
    if (state.me.status !== 'approved') return renderGate();
    if (t === 'jamoat') return renderJamoat();
    if (t === 'birga') return renderBirga();
    if (t === 'futbol') return renderFutbol();
    if (t === 'hashar') return renderHashar();
  } catch (e) { view.innerHTML = `<div class="card empty"><div class="ic">⚠️</div>${esc(e.message)}<div class="mt"><button class="btn ghost" onclick="render()">Qayta urinish</button></div></div>`; }
}

// ---------- ro'yxatdan o'tish (gate) ----------
function renderGate() {
  const m = state.me;
  if (m.status === 'pending') return view.innerHTML = `<div class="card lock"><div class="ic">⏳</div><h2>Arizangiz ko'rib chiqilmoqda</h2><p class="muted">Admin tasdiqlagach, bot sizga xabar yuboradi va barcha bo'limlar ochiladi.</p><button class="btn ghost" onclick="refreshMe()">Holatni yangilash</button></div>`;
  if (m.status === 'rejected') return view.innerHTML = `<div class="card lock"><div class="ic">❌</div><h2>Ariza rad etilgan</h2><p class="muted">Jamoat adminiga murojaat qiling yoki ma'lumotlarni to'g'rilab qayta yuboring.</p></div>` + regForm();
  view.innerHTML = `<div class="card lock"><div class="ic">🤝</div><h2>Jamoatga xush kelibsiz</h2><p class="muted">Ilovadan foydalanish uchun ro'yxatdan o'ting. Admin tasdiqlagach, jamoat bo'limlari ochiladi. Namoz vaqtlari hammaga ochiq.</p></div>` + regForm();
}
function regForm() {
  const m = state.me;
  return `<div class="card"><h2>Ro'yxatdan o'tish</h2>
  <label>Ism-familiya</label><input type="text" id="rName" maxlength="60" placeholder="Masalan: Alisher Karimov" value="${esc(m.name || m.first_name)}">
  <label>Telefon raqam</label><input type="tel" id="rPhone" placeholder="+998 90 123 45 67" value="${esc(m.phone)}">
  <button class="btn ghost mt" onclick="shareContact()">📱 Telegram raqamimni ulashish</button>
  <button class="btn mt" onclick="doRegister()">Ariza yuborish</button></div>`;
}
function shareContact() {
  if (tg && tg.requestContact) {
    tg.requestContact(async ok => {
      if (ok) { toast('Raqam yuborildi ✅'); setTimeout(refreshMe, 1500); setTimeout(refreshMe, 4000); } else toast('Raqam ulashilmadi', true);
    });
  } else toast("Raqamni qo'lda kiriting yoki botdagi «Telefon raqamni yuborish» tugmasidan foydalaning", true);
}
async function refreshMe() { try { state.me = await api('/api/me'); render(); } catch (e) { toast(e.message, true); } }
async function doRegister() {
  try { state.me = await api('/api/register', 'POST', { name: $('#rName').value, phone: $('#rPhone').value }); toast('Ariza yuborildi ✅'); render(); } catch (e) { toast(e.message, true); }
}

// ---------- 1. NAMOZ ----------
async function renderNamoz() {
  const subs = [['vaqt', 'Vaqtlar'], ['qibla', 'Qibla'], ['tasbeh', 'Tasbeh'], ['dua', 'Duolar']];
  view.innerHTML = `<div class="seg">${subs.map(s => `<button data-s="${s[0]}" class="${state.sub === s[0] ? 'on' : ''}">${s[1]}</button>`).join('')}</div><div id="sub"></div>`;
  view.querySelectorAll('.seg button').forEach(b => b.onclick = () => { state.sub = b.dataset.s; clearInterval(state.cdTimer); stopCompass(); renderNamoz(); });
  const box = $('#sub');
  if (state.sub === 'vaqt') return namozVaqt(box);
  if (state.sub === 'qibla') return qibla(box);
  if (state.sub === 'tasbeh') return tasbeh(box);
  return duolar(box);
}
async function namozVaqt(box) {
  box.innerHTML = '<div class="empty">Yuklanmoqda…</div>';
  const d = await api('/api/prayer'); state.prayerData = d;
  $('#topSub').textContent = d.place;
  const ends = Date.now() + d.next.seconds * 1000;
  const draw = () => {
    const left = Math.round((ends - Date.now()) / 1000);
    if (left <= -1) { namozVaqt(box); return; }
    $('#cd') && ($('#cd').textContent = fmtCd(left));
  };
  const dt = new Date(d.date + 'T00:00:00');
  const months = ['yanvar', 'fevral', 'mart', 'aprel', 'may', 'iyun', 'iyul', 'avgust', 'sentabr', 'oktabr', 'noyabr', 'dekabr'];
  box.innerHTML = `<div class="card hero"><div class="lbl">Keyingi namoz</div><div class="nm">${esc(d.next.name)}</div><div class="cd" id="cd">--:--:--</div><div class="at">${d.times.find(t => t.key === d.next.key).time} da</div></div>
  <div class="card times"><h2>${dt.getDate()}-${months[dt.getMonth()]}, ${dt.getFullYear()}</h2>${d.times.map(t => `<div class="row ${t.key === d.next.key ? 'next' : ''} ${t.key === 'quyosh' ? 'sun' : ''}"><span>${t.key === 'quyosh' ? '☀️ ' : ''}${t.name}</span><span class="t">${t.time}</span></div>`).join('')}
  <div class="muted mt">Hisoblash: ${esc(d.method)}. Vaqtlar mahalliy hisoblangan, masjid taqvimidan bir necha daqiqa farq qilishi mumkin.</div></div>`;
  draw(); state.cdTimer = setInterval(draw, 1000);
}
// Qibla
let compassHandler = null;
function stopCompass() { if (compassHandler) { window.removeEventListener('deviceorientationabsolute', compassHandler, true); window.removeEventListener('deviceorientation', compassHandler, true); compassHandler = null; } }
async function qibla(box) {
  box.innerHTML = '<div class="empty">Yuklanmoqda…</div>';
  const d = state.prayerData || await api('/api/prayer'); state.prayerData = d;
  const q = d.qibla;
  const dirs = ['shimol', 'shimoli-sharq', 'sharq', 'janubi-sharq', 'janub', 'janubi-g\'arb', 'g\'arb', 'shimoli-g\'arb'];
  const word = dirs[Math.round(q / 45) % 8];
  const ticks = Array.from({ length: 36 }, (_, i) => `<line x1="130" y1="12" x2="130" y2="${i % 9 === 0 ? 28 : 21}" stroke="#14684a" stroke-width="${i % 9 === 0 ? 3 : 1.5}" transform="rotate(${i * 10} 130 130)"/>`).join('');
  box.innerHTML = `<div class="card center"><h2>Qibla yo'nalishi</h2><div class="qdeg" id="qdeg">${q}°</div><div class="muted">Shimoldan soat strelkasi bo'yicha — ${word}</div>
  <div class="compass"><svg viewBox="0 0 260 260"><g id="dial"><circle cx="130" cy="130" r="122" fill="#fff" stroke="#c9a227" stroke-width="4"/>${ticks}
   <text x="130" y="48" text-anchor="middle" font-size="16" font-weight="700" fill="#c0392b">N</text><text x="130" y="224" text-anchor="middle" font-size="14" fill="#6b7a72">J</text><text x="226" y="136" text-anchor="middle" font-size="14" fill="#6b7a72">Sh</text><text x="34" y="136" text-anchor="middle" font-size="14" fill="#6b7a72">G'</text>
   <g transform="rotate(${q} 130 130)"><path d="M130 44 L139 130 L121 130 Z" fill="#14684a"/><path d="M139 130 L130 196 L121 130 Z" fill="#c9a22766"/><circle cx="130" cy="130" r="7" fill="#c9a227"/><text x="130" y="32" text-anchor="middle" font-size="20">🕋</text></g></g></svg></div>
  <div id="qinfo" class="muted">Kompas o'chiq. Telefonni tekis ushlab, tugmani bosing.</div>
  <button class="btn mt" id="qbtn">🧭 Kompasni yoqish</button></div>
  <div class="card"><div class="muted">Agar kompas ishlamasa: shimolni (N) telefon kompasi bilan toping va undan ${q}° soat strelkasi yo'nalishida buriling. Aniqlik uchun metall buyumlardan uzoqroq turing.</div></div>`;
  $('#qbtn').onclick = async () => {
    try {
      if (window.DeviceOrientationEvent && typeof DeviceOrientationEvent.requestPermission === 'function') {
        const p = await DeviceOrientationEvent.requestPermission(); if (p !== 'granted') throw 0;
      }
    } catch (e) { $('#qinfo').textContent = "Kompas ruxsati berilmadi. Yuqoridagi gradusdan foydalaning."; return; }
    let got = false;
    compassHandler = ev => {
      let h = null;
      if (typeof ev.webkitCompassHeading === 'number') h = ev.webkitCompassHeading;
      else if (ev.absolute && typeof ev.alpha === 'number') h = (360 - ev.alpha) % 360;
      else if (ev.type === 'deviceorientationabsolute' && typeof ev.alpha === 'number') h = (360 - ev.alpha) % 360;
      if (h === null) return;
      got = true;
      const dial = $('#dial'); if (!dial) return;
      dial.setAttribute('transform', `rotate(${-h} 130 130)`);
      const diff = Math.abs(((q - h + 540) % 360) - 180);
      $('#qinfo').innerHTML = diff < 5 ? '✅ <b>Qiblaga qaragansiz!</b>' : `Telefonni buring: qibla ${Math.round((q - h + 360) % 360)}° da (strelka 🕋 tomonda)`;
    };
    window.addEventListener('deviceorientationabsolute', compassHandler, true);
    window.addEventListener('deviceorientation', compassHandler, true);
    $('#qbtn').style.display = 'none';
    setTimeout(() => { if (!got && $('#qinfo')) $('#qinfo').textContent = `Bu qurilmada kompas ma'lumoti yo'q. Qibla: shimoldan ${q}° (${word}).`; }, 2500);
  };
}
// Tasbeh
function tasbeh(box) {
  let cnt = +localStorage.getItem('tsb') || 0, tgt = +localStorage.getItem('tsbT') || 33, total = +localStorage.getItem('tsbTot') || 0;
  const zikr = ['سُبْحَانَ اللَّهِ', 'الْحَمْدُ لِلَّهِ', 'اللَّهُ أَكْبَرُ'];
  const names = ['Subhanalloh', 'Alhamdulillah', 'Allohu akbar'];
  let zi = +localStorage.getItem('tsbZ') || 0;
  const paint = () => {
    box.innerHTML = `<div class="card tasbeh"><h2>Tasbeh</h2>
    <div class="seg">${[33, 99, 100, 0].map(n => `<button data-t="${n}" class="${tgt === n ? 'on' : ''}">${n || '∞'}</button>`).join('')}</div>
    <div class="ar" style="text-align:center;font-size:28px;margin:0">${zikr[zi]}</div><div class="muted">${names[zi]}</div>
    <div class="tbtn" id="tb">${cnt}</div>
    <div class="muted">Maqsad: ${tgt || 'cheksiz'} • Jami: ${total}</div>
    <div class="btns mt"><button class="btn ghost" id="tz">Zikrni almashtirish</button><button class="btn red" id="tr0">Nolga</button></div></div>`;
    box.querySelectorAll('.seg button').forEach(b => b.onclick = () => { tgt = +b.dataset.t; localStorage.setItem('tsbT', tgt); paint(); });
    $('#tz').onclick = () => { zi = (zi + 1) % 3; localStorage.setItem('tsbZ', zi); cnt = 0; localStorage.setItem('tsb', 0); paint(); };
    $('#tr0').onclick = () => { cnt = 0; localStorage.setItem('tsb', 0); paint(); };
    $('#tb').onclick = () => {
      cnt++; total++; localStorage.setItem('tsb', cnt); localStorage.setItem('tsbTot', total);
      if (tgt && cnt >= tgt) { haptic('heavy'); toast('✅ ' + tgt + ' ta bajarildi'); cnt = 0; localStorage.setItem('tsb', 0); } else haptic('light');
      paint();
    };
  };
  paint();
}
function duolar(box) {
  box.innerHTML = `<div class="card"><h2>Duolar</h2>${DUOLAR.map(d => `<details class="dua"><summary>${esc(d.t)}</summary><div class="ar">${d.ar}</div>${d.tr ? `<div class="tr">${esc(d.tr)}</div>` : ''}<div class="mn">${esc(d.mn)}</div><div class="src">Manba: ${esc(d.src)}</div></details>`).join('')}
  <div class="muted mt">Matnlarni ishonchli manbalar (Qur'on, sahih hadis to'plamlari) bilan solishtirib o'qing. Tarjimalar ma'noviy.</div></div>`;
}

// ---------- 2. JAMOAT VAQTLARI ----------
async function renderJamoat() {
  view.innerHTML = '<div class="empty">Yuklanmoqda…</div>';
  const j = await api('/api/jamoat');
  const rows = PRAYERS.map(([k, n]) => `<div class="row"><span>${n}</span><span class="t">${esc(j.times[k]) || '—'}</span></div>`).join('');
  view.innerHTML = `<div class="card times"><h2>🕋 Masjidda jamoat vaqtlari</h2>${rows}
  <div class="row" style="background:#fff8e1;border-radius:10px"><span>🕌 Juma namozi</span><span class="t">${esc(j.juma_time) || '—'}</span></div>
  ${j.note ? `<div class="muted mt">📝 ${esc(j.note)}</div>` : ''}
  ${Object.values(j.times).every(v => !v) ? '<div class="muted mt">Vaqtlar hali kiritilmagan. Admin kiritgach shu yerda ko\'rinadi.</div>' : ''}</div>
  ${j.is_admin ? '<button class="btn gold" id="editJ">✏️ Vaqtlarni tahrirlash (admin)</button>' : ''}`;
  if (j.is_admin) $('#editJ').onclick = () => jamoatForm(j);
}
function jamoatForm(j) {
  openSheet(`<h2>Jamoat vaqtlarini tahrirlash</h2>
  <div class="grid2">${PRAYERS.map(([k, n]) => `<div><label>${n}</label><input type="time" id="jt_${k}" value="${esc(j.times[k])}"></div>`).join('')}<div><label>Juma</label><input type="time" id="jt_juma" value="${esc(j.juma_time)}"></div></div>
  <label>Izoh (ixtiyoriy)</label><input type="text" id="jt_note" maxlength="300" value="${esc(j.note)}" placeholder="Masalan: Ramazonda vaqtlar o'zgaradi">
  <details class="mt"><summary class="muted">⚙️ Namoz vaqtlarini tuzatish (daqiqa, −30…+30)</summary>
  <div class="muted">Hisoblangan vaqt masjid taqvimidan farq qilsa, shu yerda to'g'rilang.</div>
  <div class="grid3">${[['bomdod', 'Bomdod'], ['quyosh', 'Quyosh'], ['peshin', 'Peshin'], ['asr', 'Asr'], ['shom', 'Shom'], ['xufton', 'Xufton']].map(([k, n]) => `<div><label>${n}</label><input type="number" id="of_${k}" value="${j.offsets[k] || 0}" min="-30" max="30"></div>`).join('')}</div></details>
  <div class="btns mt"><button class="btn ghost" onclick="closeSheet()">Bekor</button><button class="btn" id="saveJ">Saqlash</button></div>`);
  $('#saveJ').onclick = async () => {
    const times = {}; PRAYERS.forEach(([k]) => times[k] = $('#jt_' + k).value);
    const offsets = {}; ['bomdod', 'quyosh', 'peshin', 'asr', 'shom', 'xufton'].forEach(k => offsets[k] = parseInt($('#of_' + k).value) || 0);
    try { await api('/api/admin/jamoat', 'PUT', { times, juma_time: $('#jt_juma').value, note: $('#jt_note').value, offsets }); closeSheet(); toast('Saqlandi ✅'); state.prayerData = null; renderJamoat(); } catch (e) { toast(e.message, true); }
  };
}

// ---------- 3. BIRGA BORISH ----------
async function renderBirga() {
  view.innerHTML = '<div class="empty">Yuklanmoqda…</div>';
  if (!state.prayerInit) { state.prayerInit = true; try { state.prayer = (await api('/api/jamoat')).next_prayer || state.prayer; } catch (e) {} }
  const d = await api('/api/rides?prayer=' + state.prayer);
  const chips = `<div class="chips">${PRAYERS.map(([k, n]) => `<button class="chip ${state.prayer === k ? 'on' : ''}" data-p="${k}">${n}</button>`).join('')}</div>`;
  const items = d.rides.map(r => rideCard(r)).join('') || `<div class="card empty"><div class="ic">🚗</div>Hozircha e'lon yo'q.<br>Birinchi bo'ling!</div>`;
  view.innerHTML = `<h2 style="margin:4px 4px 10px;color:var(--g1)">${prayerName(state.prayer)}ga kim boradi?</h2>${chips}
  <div class="btns" style="margin-bottom:12px"><button class="btn" id="bDrv">🚗 Mashinada chiqaman</button><button class="btn gold" id="bReq">🙋 Mashinam yo'q</button></div>${items}`;
  view.querySelectorAll('.chip').forEach(c => c.onclick = () => { state.prayer = c.dataset.p; renderBirga(); });
  $('#bDrv').onclick = () => rideForm('driver'); $('#bReq').onclick = () => rideForm('request');
  view.querySelectorAll('[data-join]').forEach(b => b.onclick = () => joinRide(+b.dataset.join));
  view.querySelectorAll('.loclink').forEach(a => a.onclick = (ev) => { ev.preventDefault(); openMap(a.dataset.lat, a.dataset.lon); });
  view.querySelectorAll('[data-leave]').forEach(b => b.onclick = async () => { try { await api(`/api/rides/${b.dataset.leave}/join`, 'DELETE'); renderBirga(); } catch (e) { toast(e.message, true); } });
  view.querySelectorAll('[data-del]').forEach(b => b.onclick = async () => { if (!confirm("E'lonni o'chirasizmi?")) return; try { await api('/api/rides/' + b.dataset.del, 'DELETE'); toast("O'chirildi"); renderBirga(); } catch (e) { toast(e.message, true); } });
}
function openMap(lat, lon) {
  const url = `https://maps.google.com/?q=${lat},${lon}`;
  if (tg && tg.openLink) tg.openLink(url); else window.open(url, '_blank');
}
// Qurilma joylashuvi: avval Telegram LocationManager, bo'lmasa navigator.geolocation
function getDeviceLocation() {
  return new Promise((resolve, reject) => {
    const denied = () => reject(new Error("Joylashuvga ruxsat berilmadi. Telefon yoki Telegram sozlamalaridan ruxsat bering"));
    const viaBrowser = () => {
      if (!navigator.geolocation) return reject(new Error("Qurilmangiz joylashuvni aniqlay olmadi"));
      navigator.geolocation.getCurrentPosition(p => resolve({ lat: p.coords.latitude, lon: p.coords.longitude }),
        e => e && e.code === 1 ? denied() : reject(new Error("Joylashuvni aniqlab bo'lmadi. Qayta urinib ko'ring")),
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
    };
    const lm = tg && tg.LocationManager;
    if (!lm) return viaBrowser();
    const ask = () => lm.getLocation(d => {
      if (d && typeof d.latitude === 'number') return resolve({ lat: d.latitude, lon: d.longitude });
      try { if (lm.isAccessRequested && !lm.isAccessGranted) { if (lm.openSettings) lm.openSettings(); return denied(); } } catch (e) {}
      viaBrowser();
    });
    try { if (lm.isInited) ask(); else lm.init(ask); } catch (e) { viaBrowser(); }
  });
}
function rideCard(r) {
  const drv = r.kind === 'driver';
  const day = r.date === new Date(Date.now() + 5 * 3600e3).toISOString().slice(0, 10) ? 'Bugun' : 'Ertaga';
  const phone = r.author.phone ? `<span>📞 <a href="tel:${esc(r.author.phone)}">${esc(r.author.phone)}</a></span>` : '';
  let action = '';
  if (r.mine) action = `<button class="btn red sm" data-del="${r.id}">🗑 O'chirish</button>`;
  else if (r.joined) action = `<div class="btns"><div class="btn ghost" style="text-align:center">✅ Qo'shildingiz</div><button class="btn red sm" style="flex:0 0 auto" data-leave="${r.id}">Bekor</button></div>`;
  else if (drv && r.free === 0) action = `<div class="btn ghost" style="text-align:center;opacity:.6">Joy qolmadi</div>`;
  else action = `<button class="btn" data-join="${r.id}">${drv ? '🙋 Men ham boraman' : '🚗 Men olib ketaman'}</button>`;
  const joiners = r.mine && r.joiners.length ? `<div class="joiners"><b>${drv ? 'Boradiganlar' : 'Olib ketadiganlar'}:</b><br>${r.joiners.map(c => `${esc(c.name)} ${c.username ? tgLink(c) : ''} ${c.phone ? '📞 ' + esc(c.phone) : ''}`).join('<br>')}</div>` : '';
  const contact = r.joined ? `<div class="joiners">Bog'lanish: ${tgLink({ id: r.author.id, name: r.author.name, username: r.author.username })} ${r.author.phone ? '📞 ' + esc(r.author.phone) : ''}</div>` : '';
  return `<div class="card ride"><div class="head"><span class="pill ${drv ? 'drv' : 'req'}">${drv ? 'Mashinada chiqaman' : 'Mashinam yo\'q, olib keting'}</span><span class="big">${esc(r.depart_time)}</span></div>
  <div class="who">${esc(r.author.name)}${r.mine ? ' (siz)' : ''}</div>
  <div class="meta"><span>📅 ${day}</span>${drv ? `<span>💺 ${r.free}/${r.seats} joy bo'sh</span>` : `<span>🙋 ${r.join_count} ta taklif</span>`}${phone}</div>
  ${r.note ? `<div class="muted" style="margin-bottom:8px">💬 ${esc(r.note)}</div>` : ''}${r.has_location ? `<div style="margin-bottom:8px"><a href="#" class="loclink" data-lat="${+r.lat}" data-lon="${+r.lon}">📍 Joylashuv</a></div>` : ''}${joiners}${contact}${action}</div>`;
}
async function joinRide(id) {
  try {
    const res = await api(`/api/rides/${id}/join`, 'POST'); haptic('medium');
    toast("Qo'shildingiz ✅ E'lon egasiga xabar yuborildi");
    await renderBirga();
  } catch (e) { toast(e.message, true); }
}
async function rideForm(kind) {
  let J = { times: {}, passed: {}, next_prayer: state.prayer, next_day: 'today' }; try { J = await api('/api/jamoat'); } catch (e) {}
  const drv = kind === 'driver';
  const p0 = J.next_prayer || state.prayer;
  openSheet(`<h2>${drv ? '🚗 Mashinada chiqaman' : '🙋 Mashinam yo\'q, olib keting'}</h2>
  <label>Namoz</label><select id="rPrayer">${PRAYERS.map(([k, n]) => `<option value="${k}" ${k === p0 ? 'selected' : ''}>${n}</option>`).join('')}</select>
  <div class="muted" style="margin:-4px 0 8px">Eng yaqin jamoat namozi avtomatik tanlandi. E'lon shu namozning jamoat vaqtigacha amal qiladi.</div>
  <div class="grid2"><div><label>Kun</label><select id="rDay"><option value="today" ${J.next_day === 'today' ? 'selected' : ''}>Bugun</option><option value="tomorrow" ${J.next_day === 'tomorrow' ? 'selected' : ''}>Ertaga</option></select></div>
  <div><label>Chiqish vaqti</label><input type="time" id="rTime" value="${minusMin(J.times[p0], 20)}"></div></div>
  ${drv ? `<label>Bo'sh joylar soni</label><input type="number" id="rSeats" min="1" max="8" value="3">` : ''}
  <label>Izoh (ixtiyoriy)</label><input type="text" id="rNote" maxlength="200" placeholder="${drv ? 'Masalan: Markaz ko\'chasidan olaman' : 'Masalan: Maktab oldida turaman'}">
  <label class="chk"><input type="checkbox" id="rPhone"> Telefon raqamimni e'londa ko'rsatish</label>
  <div class="btns" style="margin:8px 0"><button class="btn ghost" id="rLoc" type="button">📍 Joylashuvni qo'shish</button></div><div class="muted" id="rLocInfo" style="margin-bottom:8px"></div>
  <div class="btns"><button class="btn ghost" onclick="closeSheet()">Bekor</button><button class="btn" id="rSave">E'lon qilish</button></div>`);
  $('#rPrayer').onchange = () => { const p = $('#rPrayer').value; $('#rDay').value = J.passed[p] ? 'tomorrow' : 'today'; $('#rTime').value = minusMin(J.times[p], 20); };
  let loc = null;
  $('#rLoc').onclick = async () => {
    const btn = $('#rLoc'); btn.disabled = true; $('#rLocInfo').textContent = 'Joylashuv aniqlanmoqda…';
    try { loc = await getDeviceLocation(); btn.textContent = '📍 Joylashuv qo\'shildi ✅ (qayta aniqlash)'; $('#rLocInfo').textContent = `${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}`; }
    catch (e) { loc = null; $('#rLocInfo').textContent = ''; toast(e.message, true); }
    btn.disabled = false;
  };
  $('#rSave').onclick = async () => {
    try {
      await api('/api/rides', 'POST', { lat: loc ? loc.lat : null, lon: loc ? loc.lon : null, kind, prayer: $('#rPrayer').value, day: $('#rDay').value, depart_time: $('#rTime').value, seats: drv ? +$('#rSeats').value : 0, note: $('#rNote').value, share_phone: $('#rPhone').checked });
      state.prayer = $('#rPrayer').value; closeSheet(); toast("E'lon joylandi ✅ A'zolarga xabar yuborildi"); renderBirga();
    } catch (e) { toast(e.message, true); }
  };
}

// ---------- 4. FUTBOL ----------
async function renderFutbol() {
  view.innerHTML = '<div class="empty">Yuklanmoqda…</div>';
  const f = await api('/api/football');
  let html = '';
  if (!f.poll) {
    html = `<div class="card empty"><div class="ic">⚽</div>Hozir ochiq so'rovnoma yo'q.<br><span class="muted">Admin yangi so'rovnoma ochgach xabar beramiz.</span></div>`;
  } else {
    const pct = Math.min(100, Math.round(f.yes_count / f.min * 100));
    html = `<div class="card poll"><div class="big">⚽ Bugun futbolga kim keladi?</div>
    ${f.enough ? `<div class="on-banner">🎉 O'yin bo'ladi!</div>` : ''}
    <div class="vote"><button class="yes ${f.my === 'yes' ? 'on' : ''}" data-v="yes">✅ Ha (${f.yes_count})</button><button class="no ${f.my === 'no' ? 'on' : ''}" data-v="no">❌ Yo'q (${f.no_count})</button></div>
    <div class="bar"><i style="width:${pct}%"></i></div><div class="muted">${f.yes_count} / ${f.min} kishi kerak${f.enough ? '' : ` — yana ${f.min - f.yes_count} kishi yetishmayapti`}</div>
    ${(f.game.time || f.game.place) ? `<div class="game">🕒 <b>${esc(f.game.time) || '—'}</b> &nbsp; 📍 <b>${esc(f.game.place) || '—'}</b></div>` : ''}</div>
    <div class="card"><h3>✅ Keladiganlar (${f.yes_count})</h3><div class="names">${f.yes.map(u => `<span>${esc(u.name)}</span>`).join('') || '<span class="muted" style="background:none">Hali hech kim</span>'}</div>
    <h3 class="mt">❌ Kelmaydiganlar (${f.no_count})</h3><div class="names no">${f.no.map(u => `<span>${esc(u.name)}</span>`).join('') || '<span class="muted" style="background:none">—</span>'}</div></div>`;
  }
  if (f.is_admin) {
    const s = f.settings;
    html += `<div class="card"><h2>⚙️ Admin: futbol</h2>
    <div class="grid2"><div><label>Kamida o'yinchi</label><input type="number" id="fMin" min="2" max="40" value="${s.min_players}"></div><div><label>O'yin vaqti</label><input type="text" id="fTime" maxlength="60" value="${esc(s.game_time)}" placeholder="20:00"></div></div>
    <label>Joy</label><input type="text" id="fPlace" maxlength="100" value="${esc(s.game_place)}" placeholder="Masalan: Markaziy minifutzal maydon">
    <label class="chk"><input type="checkbox" id="fAuto" ${s.daily_poll_enabled ? 'checked' : ''}> Har kuni so'rovnomani o'zi ochsin</label>
    <label>Kunlik so'rovnoma vaqti</label><input type="time" id="fAutoT" value="${esc(s.daily_poll_time)}">
    <div class="btns mt"><button class="btn" id="fSave">Saqlash</button><button class="btn gold" id="fNew">🆕 Yangi so'rovnoma</button></div>
    <button class="btn red mt" id="fCancel">❌ O'yinni bekor qilish</button></div>`;
  }
  view.innerHTML = html;
  view.querySelectorAll('[data-v]').forEach(b => b.onclick = async () => { try { await api('/api/football/vote', 'POST', { answer: b.dataset.v }); haptic('medium'); renderFutbol(); } catch (e) { toast(e.message, true); } });
  if (f.is_admin) {
    $('#fSave').onclick = async () => { try { await api('/api/admin/football', 'PUT', { min_players: +$('#fMin').value, game_time: $('#fTime').value, game_place: $('#fPlace').value, daily_poll_enabled: $('#fAuto').checked, daily_poll_time: $('#fAutoT').value }); toast('Saqlandi ✅'); renderFutbol(); } catch (e) { toast(e.message, true); } };
    $('#fCancel').onclick = async () => { if (!confirm("O'yin bekor qilinsin va barcha a'zolarga xabar yuborilsinmi?")) return; try { await api('/api/admin/football/cancel', 'POST'); toast("O'yin bekor qilindi"); renderFutbol(); } catch (e) { toast(e.message, true); } };
    $('#fNew').onclick = async () => { if (!confirm("Yangi so'rovnoma ochilsin va barcha a'zolarga xabar yuborilsinmi?")) return; try { await api('/api/admin/football/new-poll', 'POST'); toast("So'rovnoma ochildi ✅"); renderFutbol(); } catch (e) { toast(e.message, true); } };
  }
}

// ---------- 6. HASHAR ----------
async function renderHashar() {
  view.innerHTML = '<div class="empty">Yuklanmoqda…</div>';
  const d = await api('/api/hashars');
  const cards = d.hashars.map(h => `<div class="card ride hashar"><div class="head"><span class="pill drv">🤝 Hashar</span><span class="big" style="font-size:16px">${esc(h.when_label)}</span></div>
    <div class="who">📅 ${esc(h.date_label.charAt(0).toUpperCase() + h.date_label.slice(1))} <span class="muted">(${esc(h.date)})</span></div>
    <div class="meta"><span>📍 ${esc(h.place)}</span></div>
    ${h.description ? `<div class="muted" style="margin-bottom:8px">📝 ${esc(h.description)}</div>` : ''}
    ${h.has_location ? `<div style="margin-bottom:8px"><a href="#" class="loclink" data-lat="${+h.lat}" data-lon="${+h.lon}">📍 Joylashuv</a></div>` : ''}
    <div class="joiners"><b>Boradiganlar (${h.going_count}):</b><br>${h.going.map(g => esc(g.name)).join(', ') || '<span class="muted">Hali hech kim</span>'}</div>
    ${h.joined ? `<div class="btns"><div class="btn ghost" style="text-align:center">✅ Boraman</div><button class="btn red sm" style="flex:0 0 auto" data-hleave="${h.id}">Bekor</button></div>` : `<button class="btn" data-hjoin="${h.id}">🙋 Men boraman</button>`}
    ${h.can_edit ? `<div class="btns mt"><button class="btn ghost sm" data-hedit="${h.id}">✏️ Tahrirlash</button><button class="btn red sm" data-hcancel="${h.id}">🗑 Bekor qilish</button></div>` : ''}</div>`).join('') || `<div class="card empty"><div class="ic">🤝</div>Hozircha hashar yo'q.</div>`;
  view.innerHTML = `<h2 style="margin:4px 4px 10px;color:var(--g1)">🤝 Hashar</h2>${d.can_create ? '<button class="btn gold" id="hNew" style="margin-bottom:12px">➕ Hashar e\'lon qilish</button>' : ''}${cards}`;
  if (d.can_create) $('#hNew').onclick = () => hasharForm(null);
  view.querySelectorAll('.loclink').forEach(a => a.onclick = ev => { ev.preventDefault(); openMap(a.dataset.lat, a.dataset.lon); });
  view.querySelectorAll('[data-hjoin]').forEach(b => b.onclick = async () => { try { await api(`/api/hashars/${b.dataset.hjoin}/join`, 'POST'); haptic('medium'); toast('Rahmat! Yozildingiz ✅'); renderHashar(); } catch (e) { toast(e.message, true); } });
  view.querySelectorAll('[data-hleave]').forEach(b => b.onclick = async () => { try { await api(`/api/hashars/${b.dataset.hleave}/join`, 'DELETE'); renderHashar(); } catch (e) { toast(e.message, true); } });
  view.querySelectorAll('[data-hcancel]').forEach(b => b.onclick = async () => { if (!confirm("Hashar bekor qilinsin va barcha a'zolarga xabar yuborilsinmi?")) return; try { await api('/api/admin/hashars/' + b.dataset.hcancel, 'DELETE'); toast('Hashar bekor qilindi'); renderHashar(); } catch (e) { toast(e.message, true); } });
  view.querySelectorAll('[data-hedit]').forEach(b => b.onclick = () => hasharForm(d.hashars.find(x => x.id === +b.dataset.hedit)));
}
function hasharForm(h) {
  const today = new Date(Date.now() + 5 * 3600e3).toISOString().slice(0, 10);
  const kind = h ? h.when_kind : 'bomdod_after';
  openSheet(`<h2>${h ? '✏️ Hasharni tahrirlash' : '🤝 Yangi hashar'}</h2>
  <div class="grid2"><div><label>Qachon</label><select id="hKind"><option value="bomdod_after" ${kind === 'bomdod_after' ? 'selected' : ''}>Bomdoddan keyin</option><option value="xufton_after" ${kind === 'xufton_after' ? 'selected' : ''}>Xuftondan keyin</option><option value="custom" ${kind === 'custom' ? 'selected' : ''}>Boshqa vaqt</option></select></div>
  <div><label>Sana</label><input type="date" id="hDate" min="${today}" value="${h ? esc(h.date) : today}"></div></div>
  <div id="hTimeBox" style="${kind === 'custom' ? '' : 'display:none'}"><label>Vaqt</label><input type="time" id="hTime" value="${h ? esc(h.when_time) : ''}"></div>
  <label>Joy</label><input type="text" id="hPlace" maxlength="100" value="${h ? esc(h.place) : ''}" placeholder="Masalan: Masjid oldi, maktab yo'li">
  <label>Tavsif</label><textarea id="hDesc" maxlength="500" rows="3" placeholder="Nima ish qilinadi, nima olib kelish kerak…">${h ? esc(h.description) : ''}</textarea>
  <div class="btns" style="margin:8px 0"><button class="btn ghost" id="hLoc" type="button">📍 ${h && h.has_location ? 'Joylashuvni yangilash' : "Joylashuvni qo'shish"}</button></div><div class="muted" id="hLocInfo" style="margin-bottom:8px">${h && h.has_location ? `${(+h.lat).toFixed(5)}, ${(+h.lon).toFixed(5)}` : ''}</div>
  <div class="btns"><button class="btn ghost" onclick="closeSheet()">Bekor</button><button class="btn" id="hSave">${h ? 'Saqlash' : "E'lon qilish"}</button></div>`);
  let loc = h && h.has_location ? { lat: h.lat, lon: h.lon } : null;
  $('#hKind').onchange = () => { $('#hTimeBox').style.display = $('#hKind').value === 'custom' ? '' : 'none'; };
  $('#hLoc').onclick = async () => {
    const btn = $('#hLoc'); btn.disabled = true; $('#hLocInfo').textContent = 'Joylashuv aniqlanmoqda…';
    try { loc = await getDeviceLocation(); btn.textContent = '📍 Joylashuv qo\'shildi ✅'; $('#hLocInfo').textContent = `${loc.lat.toFixed(5)}, ${loc.lon.toFixed(5)}`; }
    catch (e) { $('#hLocInfo').textContent = loc ? `${(+loc.lat).toFixed(5)}, ${(+loc.lon).toFixed(5)}` : ''; toast(e.message, true); }
    btn.disabled = false;
  };
  $('#hSave').onclick = async () => {
    const body = { when_kind: $('#hKind').value, when_time: $('#hTime').value, date: $('#hDate').value, place: $('#hPlace').value, description: $('#hDesc').value, lat: loc ? loc.lat : null, lon: loc ? loc.lon : null };
    try {
      await api(h ? '/api/admin/hashars/' + h.id : '/api/admin/hashars', h ? 'PUT' : 'POST', body);
      closeSheet(); toast(h ? "Saqlandi ✅ A'zolarga xabar yuborildi" : "Hashar e'lon qilindi ✅ A'zolarga xabar yuborildi"); renderHashar();
    } catch (e) { toast(e.message, true); }
  };
}

// ---------- 5. PROFIL / A'ZOLAR ----------
const STATUS = { pending: 'Kutilmoqda', approved: 'Tasdiqlangan', rejected: 'Rad etilgan', new: 'Ro\'yxatdan o\'tmagan' };
async function renderProfil() {
  const m = state.me;
  let html = `<div class="card"><h2>👤 Profil</h2><div class="user"><div><b>${esc(m.name || m.first_name)}</b><div class="muted">${m.username ? '@' + esc(m.username) + ' · ' : ''}${esc(m.phone) || 'telefon yo\'q'}</div></div><span class="pill ${m.status}">${STATUS[m.status]}${m.is_admin ? ' · admin' : ''}</span></div></div>`;
  if (m.status === 'new' || m.status === 'rejected') html += regForm();
  if (m.status === 'pending') html += `<div class="card muted center">⏳ Arizangiz admin tasdig'ini kutmoqda.</div>`;
  view.innerHTML = html;
  if (m.is_admin && m.status === 'approved') await adminUsers('pending');
}
async function adminUsers(filter) {
  const d = await api('/api/admin/users?status=' + filter);
  const c = d.counts || {};
  const tabs = [['pending', 'Kutayotgan'], ['approved', 'A\'zolar'], ['admins', 'Adminlar'], ['rejected', 'Rad etilgan']];
  const box = document.createElement('div'); box.className = 'card';
  box.innerHTML = `<h2>🛡 A'zolarni boshqarish</h2><div class="seg">${tabs.map(t => `<button data-f="${t[0]}" class="${filter === t[0] ? 'on' : ''}">${t[1]} (${c[t[0]] || 0})</button>`).join('')}</div>
  ${d.users.map(u => `<div class="user"><div><b>${esc(u.name)}</b>${u.is_admin ? ' 🛡' : ''}<div class="muted">${u.username ? '@' + esc(u.username) + ' · ' : ''}${esc(u.phone) || '—'}</div></div><div class="btns" style="flex:0 0 auto">
   ${u.status !== 'approved' ? `<button class="btn sm" data-set="approved" data-id="${u.id}">✅</button>` : ''}${u.status !== 'rejected' && !u.is_admin ? `<button class="btn red sm" data-set="rejected" data-id="${u.id}">❌</button>` : ''}
   ${u.status === 'approved' && !u.is_self && !u.is_admin ? `<button class="btn sm" data-adm="1" data-id="${u.id}">🛡 Admin qilish</button>` : ''}${u.is_admin && !u.is_super && !u.is_self ? `<button class="btn red sm" data-adm="0" data-id="${u.id}">✖ Adminlikdan olish</button>` : ''}</div></div>`).join('') || '<div class="empty muted">Bo\'sh</div>'}`;
  view.appendChild(box);
  box.querySelectorAll('[data-f]').forEach(b => b.onclick = () => { box.remove(); adminUsers(b.dataset.f); });
  box.querySelectorAll('[data-adm]').forEach(b => b.onclick = async () => { const on = b.dataset.adm === '1'; if (!confirm(on ? 'Bu a\'zo admin qilinsinmi?' : 'Adminlik huquqi olib tashlansinmi?')) return; try { await api(`/api/admin/users/${b.dataset.id}/admin`, 'POST', { is_admin: on }); toast(on ? 'Admin qilindi ✅' : 'Adminlikdan olindi ✅'); box.remove(); adminUsers(filter); } catch (e) { toast(e.message, true); } });
  box.querySelectorAll('[data-set]').forEach(b => b.onclick = async () => { try { await api(`/api/admin/users/${b.dataset.id}/status`, 'POST', { status: b.dataset.set }); toast('Bajarildi ✅'); box.remove(); adminUsers(filter); } catch (e) { toast(e.message, true); } });
}

go(state.tab);
