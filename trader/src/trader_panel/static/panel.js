/* panel.js
 * KOPYA/UYARLAMA kaynagi: /home/user/sselimgenc-oss/1l3a-proje/motor/canli/pano.py, JS dizgisi (satir 329-380; 1L3A kullanicinin kendi projesi,
 * 2026-11-16): tema dugmesi (K tema anahtari), yenile dugmesi. Bu depoya ozgu: sekmeler, tum cizimler.
 * Her metin textContent ile basilir; HTML dizgisi yok. Sayilar ve Turkce metinler sunucudan hazir gelir; burada yalniz bicim/yerlesim.
 * Anlik goruntu kipinde veri gomulu (ag yok); canli kipte fetch. Yeniden cizim yok: 5 dk'da bir sayfa yenilenir. Dis URL yok.
 */
(function () {
  'use strict';
  var YENILE_S = 300;                                         // sayfa yenileme: 5 dk
  var SAYFA = 20;                                             // tablo: 20 satir + daha fazla
  var TABS = [['ozet', 'ÖZET'], ['acik', 'AÇIK'], ['kapanan', 'KAPANAN'], ['kz', 'K/Z'], ['ogrenme', 'ÖĞRENME'], ['teknik', 'TEKNİK']];
  var DONEMLER = [['bugun', 'Bugün'], ['7g', '7 gün'], ['30g', '30 gün'], ['tumu', 'Tümü']];
  var BOT = 'learner';
  var S = {tab: 'ozet', pano: null, kapanan: {}, donem: 'bugun', t0: Date.now(), gen: null, sirala: {}};
  var $ = function (i) { return document.getElementById(i); };

  /* ---------- DOM yardimcilari (yalniz textContent) ---------- */
  function el(tag, cls, txt) {
    var e = document.createElement(tag);
    if (cls) e.className = cls;
    if (txt !== undefined && txt !== null) e.textContent = String(txt);
    return e;
  }
  function add(p) {
    for (var i = 1; i < arguments.length; i++) { if (arguments[i]) p.appendChild(arguments[i]); }
    return p;
  }
  function clear(p) { while (p.firstChild) p.removeChild(p.firstChild); return p; }
  var NS = 'http' + '://www.w3.org/2000/svg';            // SVG ad alani kimligi: ag istegi degil
  function sv(tag, attrs) {
    var e = document.createElementNS(NS, tag);
    for (var k in attrs) e.setAttribute(k, attrs[k]);
    return e;
  }

  /* ---------- bicim ---------- */
  function num(x) { return typeof x === 'number' && isFinite(x); }
  function trn(x, d) {                                        // Turkce sayi: 1.428,40
    var s = Math.abs(x).toFixed(d === undefined ? 2 : d), p = s.split('.'), g = p[0].replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    return p.length > 1 ? g + ',' + p[1] : g;
  }
  function f2(x) { return num(x) ? (x < 0 ? '−' : '') + trn(x) : '—'; }
  function sgn(x) { return num(x) ? (x > 0 ? '+' : (x < 0 ? '−' : '')) + trn(x) : '—'; }
  function usd(x) { return num(x) ? f2(x) + ' $' : '—'; }
  function usdS(x) { return num(x) ? sgn(x) + ' $' : '—'; }
  function pc(x) { return num(x) ? (x > 0 ? '+' : (x < 0 ? '−' : '')) + '%' + trn(x) : ''; }
  function px(x) { return !num(x) ? '—' : (x < 0 ? '−' : '') + (Math.abs(x) >= 1 ? trn(x, 2) : trn(x, 3)); }
  /* ek:basla — "12'si", "3'ü": sayinin okunusuna gore iyelik eki (son soylenen sozcuge gore) */
  function ek(n) {
    n = Math.abs(Math.round(n));
    var T = {0: "'ı", 1: "'i", 2: "'si", 3: "'ü", 4: "'ü", 5: "'i", 6: "'sı", 7: "'si", 8: "'i", 9: "'u"};   // bir, iki, üç, dört, beş, altı, yedi, sekiz, dokuz
    var O = {1: "'u", 2: "'si", 3: "'u", 4: "'ı", 5: "'si", 6: "'ı", 7: "'i", 8: "'i", 9: "'ı"};             // on, yirmi, otuz, kırk, elli, altmış, yetmiş, seksen, doksan
    if (n === 0) return T[0];
    if (n % 10) return T[n % 10];
    if (n % 100) return O[(n % 100) / 10];
    if (n % 1000) return "'ü";                                // yüz
    if (n % 1000000) return "'i";                             // bin
    return "'u";                                              // milyon
  }
  /* ek:bitir */
  function cls(x) { return !num(x) ? '' : (Math.abs(x) < 0.005 ? 'notr' : (x > 0 ? 'iyi' : 'kotu')); }
  function ago(s) {
    if (!num(s) || s < 90) return 'az önce';
    if (s < 5400) return Math.round(s / 60) + ' dk önce';
    return trn(s / 3600, 1) + ' sa önce';
  }
  function etiketTsi(iso) {                                   // yalniz gosterim: TSİ (sabit +3)
    var t = Date.parse(iso);
    if (!isFinite(t)) return '—';
    var d = new Date(t + 3 * 3600000).toISOString();
    return d.slice(8, 10) + '.' + d.slice(5, 7) + ' ' + d.slice(11, 16);
  }

  /* ---------- ag ---------- */
  var SNAP = window.__SNAPSHOT__ || null;                      // anlik goruntu kipi: veri gomulu, ag yok
  var SNAP_STALE_S = 600;                                      // gorunumun kendisi 10 dk'dan eskiyse bayat
  function snapBanner() {
    var b = $('snap-bant');
    if (!SNAP || !b) return;
    var age = (Date.now() - Date.parse(SNAP.generated_at)) / 1000;
    if (!isFinite(age) || age > SNAP_STALE_S) {
      b.textContent = 'BAYAT GÖRÜNÜM: bu sayfa ' + (isFinite(age) ? ago(age).replace(' önce', '') : 'bilinmeyen süre') + ' önce üretildi; Yenile ile tekrar yükleyin.';
      b.style.display = '';
    } else { b.style.display = 'none'; }
  }
  function get(path) {
    if (SNAP) {
      var v = SNAP.data[path];
      return Promise.resolve(v === undefined ? {ok: false} : v);
    }
    return fetch(path, {cache: 'no-store'}).then(function (r) { return r.json(); }, function () { return {ok: false, baglanti: true}; });
  }

  /* ---------- parcalar ---------- */
  function kart(baslik, sag, extra) {
    var k = el('div', 'kart' + (extra ? ' ' + extra : ''));
    var h = el('h2');
    add(h, el('span', '', baslik));
    if (sag) add(h, sag);
    add(k, h);
    return k;
  }
  function satir(ad, val, c) { return add(el('div', 'satir'), el('span', '', ad), el('b', c || '', val)); }
  function link(txt, tab) {
    var a = el('button', 'lnk', txt);
    a.type = 'button';
    a.addEventListener('click', function () { sec(tab); });
    return a;
  }
  function rozetRenk(txt, renk) { return el('span', 'rt ' + (renk || ''), txt); }
  function yok(txt) { return el('div', 'yok', txt); }
  function sym(coin, yon, kol) {
    var d = el('div');
    add(d, el('b', 'n', coin), el('span', 'yon ' + yon, yon));
    if (kol) add(d, el('div', 'u', kol));
    return d;
  }
  function kzHucre(kz, yuzde, bekliyor) {
    var d = el('div', 'sg');
    if (bekliyor) { add(d, el('div', 'u', 'fiyat bekleniyor')); return d; }
    add(d, el('div', 'n ' + cls(kz), usdS(kz)));
    if (num(yuzde)) add(d, el('div', 'u ' + cls(yuzde), pc(yuzde)));
    return d;
  }
  function ayrinti(pairs) {
    var d = el('div', 'dl');
    pairs.forEach(function (p) {
      if (p[1] === null || p[1] === undefined || p[1] === '' || p[1] === '—') return;
      var c = el('div', p[2] ? 'g' : '');
      add(c, el('span', '', p[0]), document.createTextNode(String(p[1])));
      add(d, c);
    });
    return d;
  }
  /* Siralama: tek ortak yardimci. Secim bellekte (S.sirala) + try/catch'li localStorage (sayfa yenilemesinde korunur). */
  function siraOku() {
    try { var x = JSON.parse(localStorage.getItem('panel_sirala') || '{}'); if (x && typeof x === 'object') S.sirala = x; } catch (e) { /* yok say */ }
  }
  function siraYaz() { try { localStorage.setItem('panel_sirala', JSON.stringify(S.sirala)); } catch (e) { /* yok say */ } }
  function siraKarsi(a, b, yon) {                             // bos degerler yone bakmadan sona
    var an = a === null || a === undefined || (typeof a === 'number' && !isFinite(a));
    var bn = b === null || b === undefined || (typeof b === 'number' && !isFinite(b));
    if (an || bn) return an && bn ? 0 : (an ? 1 : -1);
    var c = (typeof a === 'number' && typeof b === 'number') ? a - b : String(a).localeCompare(String(b), 'tr');
    return yon === 'asc' ? c : -c;
  }
  function sirala(rows, st) {                                 // st: {col, yon}; r.v[col] ham deger (sayi / epoch sn / metin)
    if (!st || !st.col && st.col !== 0) return rows;
    return rows.map(function (r, i) { return [r, i]; }).sort(function (x, y) {
      return siraKarsi(x[0].v ? x[0].v[st.col] : null, y[0].v ? y[0].v[st.col] : null, st.yon) || x[1] - y[1];
    }).map(function (x) { return x[0]; });
  }
  /* n sutunlu tablo; satira dokununca ayrinti acilir. rows: [{cells: [node], v: [ham deger], detail: [[ad, deger]]}]; id: siralama anahtari */
  function tablo(head, rows, sagCols, id) {
    var w = el('div'), t = el('table', 'n' + head.length), cg = el('colgroup'), th = el('thead'), hr = el('tr'), tb = el('tbody');
    var sirali = rows, ths = [];
    head.forEach(function (h, i) { add(cg, el('col', 'c' + (i + 1))); });
    function basliklar() {
      var st = S.sirala[id];
      ths.forEach(function (h, i) {
        var on = st && st.col === i;
        h.textContent = head[i] + (on ? (st.yon === 'asc' ? ' ▲' : ' ▼') : '');
        h.setAttribute('aria-sort', on ? (st.yon === 'asc' ? 'ascending' : 'descending') : 'none');
      });
    }
    function sirayaGec(i) {
      var st = S.sirala[id];
      S.sirala[id] = {col: i, yon: st && st.col === i && st.yon === 'desc' ? 'asc' : 'desc'};   // ilk tik azalan, sonra artan
      siraYaz();
      yenidenCiz();
    }
    head.forEach(function (h, i) {
      var c = el('th', (sagCols.indexOf(i) >= 0 ? 'sg ' : '') + 'sirali', h);
      c.setAttribute('tabindex', '0');
      c.addEventListener('click', function () { sirayaGec(i); });
      c.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sirayaGec(i); } });
      ths.push(c);
      add(hr, c);
    });
    add(t, cg, add(th, hr), tb);
    var gosterilen = 0, btn = null;
    function yenidenCiz() {
      clear(tb);
      gosterilen = 0;
      sirali = sirala(rows, S.sirala[id]);
      basliklar();
      if (btn) btn.style.display = '';
      ciz();
    }
    function ciz() {
      var son = Math.min(gosterilen + SAYFA, rows.length);
      for (var i = gosterilen; i < son; i++) tb.appendChild(satirYap(sirali[i]));
      gosterilen = son;
      if (btn) { if (gosterilen >= rows.length) btn.style.display = 'none'; else btn.textContent = 'Daha fazla (' + (rows.length - gosterilen) + ')'; }
    }
    function satirYap(r) {
      var tr = el('tr', 'satir-t'), dty = null;
      tr.setAttribute('tabindex', '0');
      tr.setAttribute('aria-expanded', 'false');
      r.cells.forEach(function (c, i) {
        var td = el('td', sagCols.indexOf(i) >= 0 ? 'sg' : '');
        td.appendChild(c);
        tr.appendChild(td);
      });
      function ac() {
        var acik = tr.getAttribute('aria-expanded') === 'true';
        if (acik) { if (dty && dty.parentNode) dty.parentNode.removeChild(dty); tr.setAttribute('aria-expanded', 'false'); return; }
        dty = el('tr', 'dty');
        var td = el('td');
        td.setAttribute('colspan', String(head.length));
        td.appendChild(ayrinti(r.detail));
        dty.appendChild(td);
        tb.insertBefore(dty, tr.nextSibling);
        tr.setAttribute('aria-expanded', 'true');
      }
      tr.addEventListener('click', ac);
      tr.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); ac(); } });
      return tr;
    }
    sirali = sirala(rows, S.sirala[id]);
    basliklar();
    ciz();
    add(w, t);
    if (rows.length > SAYFA) {
      btn = el('button', 'daha', 'Daha fazla (' + (rows.length - gosterilen) + ')');
      btn.type = 'button';
      btn.addEventListener('click', ciz);
      add(w, btn);
    }
    return w;
  }

  /* ---------- grafik (satir ici SVG) ---------- */
  function cizgiGrafik(egri) {
    var ys = egri.map(function (p) { return p[1]; }), W = 1000, H = 300, n = ys.length;
    var mn = Math.min.apply(null, ys), mx = Math.max.apply(null, ys);
    if (mx === mn) { mx += 1; mn -= 1; }
    var X = function (i) { return n < 2 ? W / 2 : i * W / (n - 1); }, Y = function (v) { return H - (v - mn) / (mx - mn) * H; };
    var svg = sv('svg', {viewBox: '0 0 ' + W + ' ' + H, preserveAspectRatio: 'none', role: 'img', 'aria-label': 'Kasa eğrisi, son 30 gün'});
    [0, 0.5, 1].forEach(function (f) { svg.appendChild(sv('line', {x1: 0, x2: W, y1: f * H, y2: f * H, 'class': 'izg'})); });
    var d = ys.map(function (v, i) { return (i ? 'L' : 'M') + X(i).toFixed(1) + ' ' + Y(v).toFixed(1); }).join(' ');
    var neg = ys[n - 1] < ys[0];
    svg.appendChild(sv('path', {d: d + ' L' + X(n - 1).toFixed(1) + ' ' + H + ' L' + X(0).toFixed(1) + ' ' + H + ' Z', 'class': 'alan' + (neg ? ' k' : '')}));
    svg.appendChild(sv('path', {d: d, 'class': 'cizgi' + (neg ? ' k' : '')}));
    var g = el('div', 'gk'), yt = el('div', 'yt'), ek = el('div', 'ek');
    add(yt, el('span', '', trn(mx, 0)), el('span', '', trn(mn, 0)));
    add(ek, el('span', '', egri[0][0]), el('span', '', egri[n - 1][0]));
    return add(g, yt, svg, ek);
  }

  /* ---------- ust serit ---------- */
  function sk(e, big, alt, bigCls, extra) {
    var k = el('div', 'ks' + (extra ? ' ' + extra : ''));
    return add(k, el('div', 'e', e), el('div', 'b ' + (bigCls || ''), big), alt ? el('div', 'a', alt) : null);
  }
  var KASA_IPUCU = 'Kasa = başlangıç + kapanan K/Z + açık K/Z − açık işlemlerin giriş komisyonu';
  function eskiAlt(s, alt) {      // durum dosyasi eski/okunamiyor: canli sayi yok; yasi belirt
    if (s.risk && s.risk.renk === 'gri') return 'eski' + (num(s.durum_yasi_s) ? ' · ' + ago(s.durum_yasi_s) : '');
    return alt;
  }
  function kasaKart(s) {
    var k = sk('Kasa', usd(s.kasa), eskiAlt(s, num(s.baslangic) ? 'başlangıç ' + usd(s.baslangic) : '')), q = el('span', 'ipucu', '?');
    q.title = KASA_IPUCU; q.setAttribute('tabindex', '0'); q.setAttribute('aria-label', KASA_IPUCU);
    k.firstChild.appendChild(q);
    return k;
  }
  function renderTop(p) {
    var b = clear($('bantlar')), z = clear($('serit'));
    if (!p || !p.ok) {
      add(b, el('div', 'uyari' + (p && p.baglanti ? ' bayat-bant' : ' kritik'),
        p && p.baglanti ? 'Panel bağlantısı yok; ekrandaki değerler güncel değil.' : 'Veri şu an okunamıyor. Birazdan yeniden denenecek.'));
      return;
    }
    var s = p.serit, r = s.risk, ro = $('rozet');
    if (p.mod) { ro.hidden = false; ro.textContent = p.mod === 'live' ? 'CANLI' : 'KÂĞIT'; } else ro.hidden = true;
    add(z,
      kasaKart(s),
      sk('Bugün K/Z', usdS(s.bugun), pc(s.bugun_yuzde), cls(s.bugun)),
      sk('Toplam K/Z', usdS(s.toplam), pc(s.toplam_yuzde), cls(s.toplam)),
      sk('Açık poz.', String(s.acik), eskiAlt(s, num(s.acik_kz) ? 'açık K/Z ' + usdS(s.acik_kz) : ''), ''),
      sk('Zirveden düşüş', usdS(s.dusus), pc(s.dusus_yuzde), cls(s.dusus)),
      add(el('div', 'ks risk ' + r.renk), el('div', 'e', 'Risk durumu'),
        add(el('div', 'b'), el('span', 'nokta'), el('span', '', r.metin)), el('div', 'a', r.alt)));
  }

  /* ---------- sekmeler ---------- */
  function sec(t) {
    S.tab = t;
    try { localStorage.setItem('pano_sekme', t); } catch (e) { /* tarayici deposu yoksa sorun degil */ }
    TABS.forEach(function (x) {
      var s = $('sek-' + x[0]), bt = $('tab-' + x[0]);
      if (s) s.className = 'sek' + (x[0] === t ? ' on' : '');
      if (bt) bt.className = x[0] === t ? 'on' : '';
    });
    if (t === 'kapanan') yukleKapanan();
  }
  function kurTabs() {
    var n = clear($('tabs'));
    TABS.forEach(function (x) {
      var b = el('button', '', x[1]);
      b.type = 'button';
      b.id = 'tab-' + x[0];
      b.setAttribute('data-ad', x[1]);
      b.addEventListener('click', function () { sec(x[0]); });
      add(n, b);
    });
  }

  /* sekme rozetleri: yalniz AÇIK (acik pozisyon sayisi) ve KAPANAN (bugun, TR saati); digerlerinde sayi yok */
  function rozetYaz(t, n) {
    var bt = $('tab-' + t);
    if (!bt || n === null || n === undefined || isNaN(n)) return;
    clear(bt);
    add(bt, el('span', '', t === 'acik' ? 'AÇIK' : 'KAPANAN'), el('span', 'hap', String(n)));
  }
  function sekmeSayilari(p) {
    if (p && p.acik) rozetYaz('acik', p.acik.n);
    get('/api/kapanan?bot=' + BOT + '&period=bugun').then(function (v) { if (v && v.ok !== false) rozetYaz('kapanan', v.n); });
  }

  function yokKart(txt) { return add(kart('Veri'), yok(txt)); }

  function kzHatasi(root, p) {
    clear(root);
    add(root, yokKart('Veri şu an okunamıyor.'));
  }

  /* ÖZET */
  function tabOzet(root, p) {
    clear(root);
    var ig = add(el('div', 'ig iki'));
    if (p.isik.renk === 'kirmizi') add(ig, isikKart(p));
    var y = kart('Ne yapmalıyım?');
    add(y, el('div', 'buyuk', p.yapmali));
    add(ig, y);
    var a = p.acik, k = kart('Açık işlemler', link('Tümü', 'acik'));
    if (!a.n) add(k, yok('Şu an açık işlem yok.'));
    else {
      add(k, satir('Adet', String(a.n)), satir('Toplam K/Z', usdS(a.kz), cls(a.kz)));
      if (a.en_iyi) add(k, satir('En iyi', a.en_iyi.coin + ' ' + usdS(a.en_iyi.kz), cls(a.en_iyi.kz)));
      if (a.en_kotu) add(k, satir('En kötü', a.en_kotu.coin + ' ' + usdS(a.en_kotu.kz), cls(a.en_kotu.kz)));
    }
    add(ig, k);
    var s3 = kart('Son kapanan işlemler', link('Tümü', 'kapanan'));
    if (!p.son3.length) add(s3, yok('Henüz kapanan işlem yok.'));
    p.son3.forEach(function (r) {
      var d = el('div', 'satir');
      var sol = add(el('span'), el('b', '', r.coin), el('span', 'yon ' + r.yon, r.yon), el('span', 'u sol', ' ' + r.kapanis));
      add(d, sol, add(el('b'), el('span', cls(r.kz), usdS(r.kz)), el('span', '', ' · ' + r.neden)));
      add(s3, d);
    });
    add(ig, s3);
    var dd = p.ders || {durum: 'Kapalı', renk: 'gri', son: null, degisen_7g: 0, katki: {olculemedi: 'Henüz ölçülemedi'}};
    var d = kart('Ders öğrenmesi', link('Ayrıntı', 'ogrenme'));      // iki öğrenme kartı veri yokken de görünür (zorunlu)
    add(d, add(el('div'), rozetRenk(dd.durum, dd.renk)));
    add(d, dd.son ? satir('Son öğrendiği', dd.son.tarih) : el('div', 'yok', 'Henüz ders yok'));
    if (dd.son) add(d, el('div', 'yok', dd.son.metin));
    add(d, satir('Son 7 günde değiştirdiği işlem', String(dd.degisen_7g)), katkiSatir(dd.katki));
    add(ig, d);
    if (p.ogrenme) add(ig, ogrenmeOzetKart(p.ogrenme));
    if (p.isik.renk !== 'kirmizi') add(ig, isikKart(p));
    add(root, ig);
  }
  function isikKart(p) {
    var k = kart('Durum', null, p.isik.renk === 'kirmizi' ? 'kirmizi' : '');
    return add(k, add(el('div', 'buyuk'), el('span', 'nokta'), document.createTextNode(' ' + p.isik.metin)),
      p.isik.renk === 'kirmizi' ? link('Teknik ayrıntı', 'teknik') : null);
  }

  /* AÇIK */
  function tabAcik(root, p) {
    clear(root);
    var a = p.acik, k = kart('Açık işlemler');
    if (!a.n) { add(k, yok('Şu an açık işlem yok.')); add(root, k); return; }
    add(k, add(el('div', 'ozet-ic'), el('span', '', a.n + ' işlem'), add(el('span'), document.createTextNode('K/Z '), el('b', cls(a.kz), usdS(a.kz))),
      num(a.kasa_yuzde) ? el('span', '', 'kasanın %' + trn(a.kasa_yuzde, 0) + ek(a.kasa_yuzde) + ' kullanımda') : null));
    var rows = a.rows.map(function (r) {
      var gn = add(el('div'), el('div', 'n', px(r.giris)), el('div', 'u', r.fiyat_bekleniyor ? '→ fiyat bekleniyor' : '→ ' + px(r.simdi)));
      return {cells: [sym(r.coin, r.yon, r.kol), gn, kzHucre(r.kz, r.kz_yuzde, r.fiyat_bekleniyor), add(el('div', 'sg'), el('span', 'n', r.sure))],
        // siralama ham degerleri (24.11: acik tabloda v yoktu, siralama calismiyordu); Sure = acilistan bu yana (eski acilis = uzun sure)
        v: [r.coin, num(r.kz_yuzde) ? r.kz_yuzde : null, num(r.kz) ? r.kz : null, num(r.acilis_ts) ? -r.acilis_ts : null],
        detail: [['Stop', px(r.stop)], ['Hedef', px(r.hedef)], ['Büyüklük', usd(r.buyukluk)], ['Kaldıraç', r.kaldirac ? r.kaldirac + 'x' : ''],
          ['Kol', r.kol], ['Açılış', r.acilis], ['Açılış nedeni', r.neden, 1]]};
    });
    add(k, tablo(['Sembol', 'Giriş → şimdi', 'K/Z', 'Süre'], rows, [2, 3], 'acik'));
    add(root, k);
  }

  /* KAPANAN */
  function yukleKapanan() {
    var root = $('sek-kapanan'), d = S.donem;
    function ciz(v) {
      clear(root);
      var k = kart('Kapanan işlemler'), bar = el('div', 'donem');
      DONEMLER.forEach(function (x) {
        var b = el('button', x[0] === S.donem ? 'on' : '', x[1]);
        b.type = 'button';
        b.addEventListener('click', function () { S.donem = x[0]; yukleKapanan(); });
        add(bar, b);
      });
      add(k, bar);
      if (!v || !v.ok) { add(k, yok('Veri şu an okunamıyor.')); add(root, k); return; }
      if (!v.n) { add(k, yok('Bu dönemde kapanan işlem yok.')); add(root, k); return; }
      add(k, add(el('div', 'ozet-ic'), el('span', '', v.n + ' işlem'), el('span', '', 'kazanan %' + trn(v.kazanan_yuzde, 0)),
        add(el('span'), document.createTextNode('net '), el('b', cls(v.net), usdS(v.net)))));
      var rows = v.rows.map(function (r) {
        return {cells: [sym(r.coin, r.yon), el('div', 'n', r.kapanis), kzHucre(r.kz, r.kz_yuzde), el('div', 'n', usd(r.buyukluk)), add(el('div', 'sg'), el('span', 'n', r.neden))],
          v: [r.coin, r.kapanis_ts, r.kz, r.buyukluk, r.neden],
          detail: [['Giriş', px(r.giris)], ['Çıkış', px(r.cikis)], ['Süre', r.sure], ['Büyüklük', usd(r.buyukluk)], ['Kaldıraç', r.kaldirac ? r.kaldirac + 'x' : ''],
            ['Marj', num(r.marj) ? usd(r.marj) : ''], ['Komisyon', usd(r.komisyon)], ['Kol', r.kol],
            ['Açılış', r.acilis], ['Ders', r.ders ? 'Bu işlemde ders etkili oldu' : '', 1]]};
      });
      add(k, tablo(['Sembol', 'Kapanış', 'K/Z', 'Büyüklük', 'Neden'], rows, [2, 3, 4], 'kapanan'));
      if (v.daha_fazla) add(k, el('div', 'yok', 'Daha eski ' + v.daha_fazla + ' işlem listede gösterilmiyor.'));
      add(root, k);
    }
    if (S.kapanan[d]) { ciz(S.kapanan[d]); return; }
    get('/api/kapanan?bot=' + BOT + '&period=' + d).then(function (v) { S.kapanan[d] = v; if (S.donem === d) ciz(v); });
  }

  /* K/Z */
  function tabKz(root, p) {
    clear(root);
    var z = p.kz, ig = el('div', 'ig iki');
    if (z.egri) { var g = kart('Kasa eğrisi · 30 gün'); add(g, cizgiGrafik(z.egri)); add(ig, g); }
    var d = kart('Dönem K/Z'), g4 = el('div', 'd4');
    [['bugun', 'Bugün'], ['7g', '7 gün'], ['30g', '30 gün'], ['tumu', 'Toplam']].forEach(function (x) {
      var v = z.donemler[x[0]];
      add(g4, sk(x[1], usdS(v.kz), pc(v.yuzde), cls(v.kz)));
    });
    add(d, g4); add(ig, d);
    if (z.oran) {
      var o = kart('Kazanma oranı');
      if (z.oran.olculemedi) add(o, yok(z.oran.olculemedi));
      else add(o, satir('Kazanan işlem', '%' + trn(z.oran.kazanma_yuzde, 0) + ' (' + z.oran.n + ' işlem)'),
        satir('Ortalama kazanç', usdS(z.oran.ort_kazanc), 'iyi'), satir('Ortalama kayıp', usdS(z.oran.ort_kayip), 'kotu'));
      add(ig, o);
    }
    if (z.kol.length) {
      var kk = kart('Kaynağa göre K/Z');
      z.kol.forEach(function (r) { add(kk, satir(r.kol + ' · ' + r.n + ' işlem', usdS(r.kz), cls(r.kz))); });
      add(ig, kk);
    }
    if (z.masraf) {
      var m = kart('Masraflar');
      add(m, satir('Komisyon · 30 gün', usd(z.masraf['30g'].komisyon)), satir('Fonlama · 30 gün', usdS(-z.masraf['30g'].fonlama)),
        satir('Komisyon · toplam', usd(z.masraf.tumu.komisyon)), satir('Fonlama · toplam', usdS(-z.masraf.tumu.fonlama)));
      add(ig, m);
    }
    add(root, ig);
  }

  /* ÖĞRENME */
  function katkiSatir(k) {
    if (k.olculemedi) return satir('Katkı', k.olculemedi.replace('Henüz', 'henüz'));
    return satir('Katkı', (k.yaklasik ? '≈ ' : '') + usdS(k.usd) + ' (' + k.n + ' sonucu belli karar)', cls(k.usd));
  }
  /* Öğrenme: kol x zaman dilimi (veri: defter + kademeli küçültme + karantina dosyası) ve model kolları (paket dosyaları) */
  var DURUM_RENK = {acik: 'yesil', kucultulmus: 'sari', karantina: 'kirmizi'}, DURUM_SIRA = {acik: 0, kucultulmus: 1, karantina: 2};
  function kolAd(r) { return r.kol + ' · ' + r.zd; }
  function netR(x) { return num(x) ? sgn(x) + ' R' : '—'; }
  function ogrenmeOzetKart(o) {
    var z = o.ozet, k = kart('Öğrenme', link('Ayrıntı', 'ogrenme'));
    add(k, satir('Açık kol', String(z.acik), z.acik ? 'iyi' : ''), satir('Küçültülmüş kol', String(z.kucultulmus), z.kucultulmus ? 'kotu' : ''),
      satir('Karantinada kol', String(z.karantina), z.karantina ? 'kotu' : ''));
    function liste(ad, rows) {
      if (!rows.length) return;
      add(k, el('div', 'yok', ad));
      rows.forEach(function (r) { add(k, satir(kolAd(r), netR(r.net_r) + ' · ' + r.n + ' işlem', cls(r.net_r))); });
    }
    if (!z.en_iyi.length) add(k, el('div', 'yok', 'Henüz kapanan işlem yok; sıralama sonra görünür.'));
    liste('En iyi 3 (net R)', z.en_iyi);
    liste('En kötü 3 (net R)', z.en_kotu);
    return k;
  }
  function ogrenmeTablolari(root, o) {
    add(root, ogrenmeOzetKart(o));
    var rows = o.kollar.map(function (r) {
      var dr = add(el('div', 'sg'), rozetRenk(r.durum_ad, DURUM_RENK[r.durum]));
      if (r.carpan < 1) add(dr, el('div', 'u', '%' + Math.round(r.carpan * 100) + ' boyut'));
      return {cells: [add(el('div', 'kolad'), el('div', 'n', r.kol), el('div', 'u', r.zd)), el('div', 'n', String(r.n)),
          el('div', 'n ' + cls(r.net_r), netR(r.net_r)), el('div', 'n', num(r.kazanma) ? '%' + trn(r.kazanma, 0) : '—'), dr],
        v: [r.kol + ' ' + r.zd, r.n, num(r.net_r) ? r.net_r : null, num(r.kazanma) ? r.kazanma : null, DURUM_SIRA[r.durum]],
        detail: [['Kol', r.arm], ['Risk çarpanı', '%' + Math.round(r.carpan * 100)], ['Durum', r.durum_ad],
          ['Son ders değişikliği', r.son_ders ? r.son_ders + ' tarihli bir işlemde ders etkili oldu' : 'Henüz yok']]};
    });
    var t = kart('Tüm kollar · zaman dilimine göre');
    add(t, el('div', 'yok', 'Kapanan işlem, net R (R = işlemde riske atılan tutar), kazanma yüzdesi ve kolun işlem riski çarpanı. Satıra dokun: ayrıntı.'));
    var w = tablo(['Kol', 'İşlem', 'Net R', 'Kazanma', 'Durum'], rows, [1, 2, 3, 4], 'og_kol');
    w.className = 'og';
    add(t, w);
    add(root, t);
    if (!o.modeller.length) return;
    var mrows = o.modeller.map(function (r) {
      var bil = r.paket === 'okunamadi' ? 'okunamadı' : 'bilinmiyor';
      return {cells: [add(el('div', 'kolad'), el('div', 'n', r.kol), el('div', 'u', r.zd)), el('div', 'n', r.egitim || bil),
          el('div', 'n', num(r.yas_gun) ? trn(r.yas_gun, 1) + ' gün' : bil), el('div', 'n', String(r.bugun_aday)), el('div', 'n', String(r.bugun_giris))],
        v: [r.kol + ' ' + r.zd, num(r.egitim_ts) ? r.egitim_ts : null, num(r.yas_gun) ? r.yas_gun : null, r.bugun_aday, r.bugun_giris],
        detail: [['Kol', r.arm], ['Model paketi', r.paket === 'var' ? 'var' : (r.paket === 'yok' ? 'yok (bilinmiyor)' : 'okunamadı (bilinmiyor)')],
          ['Son eğitim (TSİ)', r.egitim || 'bilinmiyor']]};
    });
    var m = kart('Model kolları · eğitim ve bugün');
    add(m, el('div', 'yok', 'Son eğitim = paketin hazırlandığı an (TSİ). Bugün aday = bugün karar verilen, giriş = açılan işlem sayısı.'));
    var mw = tablo(['Kol', 'Son eğitim', 'Paket yaşı', 'Bugün aday', 'Bugün giriş'], mrows, [1, 2, 3, 4], 'og_model');
    mw.className = 'og';
    add(m, mw);
    add(root, m);
  }
  function tabOgrenme(root, p) {
    clear(root);
    var ig = el('div', 'ig iki');
    if (p.ders) {
      var d = p.ders, k = kart('Ders kartı');
      add(k, add(el('div'), rozetRenk(d.durum, d.renk)));
      if (d.son) add(k, satir('Son öğrendiği', d.son.tarih), el('div', 'yok', d.son.metin));
      add(k, satir('Son 7 günde etkilediği işlem', String(d.degisen_7g)), katkiSatir(d.katki));
      add(ig, k);
      if (d.son5.length) {
        var l = kart('Son dersler');
        d.son5.forEach(function (s) { add(l, satir(s.tarih, s.metin, s.geri ? 'kotu' : '')); });
        add(ig, l);
      }
    }
    if (p.kucultme) {
      var kk2 = kart('Kademeli küçültme');
      add(kk2, el('div', 'yok', 'Son işlemleri zararda olan kolların işlem riski küçültüldü (kol kapanmaz; kâra dönünce geri yükselir).'));
      p.kucultme.kollar.forEach(function (r) {
        add(kk2, satir(r.kol, '%' + Math.round(r.carpan * 100) + ' boyut · son ' + (num(r.net_10) ? '10' : '5') + ': ' + sgn(num(r.net_10) ? r.net_10 : r.net_5) + ' R', 'kotu'));
      });
      add(ig, kk2);
    }
    if (!p.ders && !p.kucultme && !p.ogrenme) add(ig, yokKart('Henüz öğrenme verisi yok.'));
    add(root, ig);
    if (p.ogrenme) ogrenmeTablolari(root, p.ogrenme);
  }

  /* TEKNİK (katlı) */
  function katli(baslik, renk, bodyFn, ac) {
    var d = el('details'), s = el('summary');
    if (ac) d.setAttribute('open', '');
    add(s, el('span', '', baslik), renk ? el('span', 'nokta ' + renk) : null);
    add(d, s, bodyFn(el('div')));
    return d;
  }
  function bar(ad, kul, lim, pct) {
    var w = el('div', 'lim'), r = el('div', 'r');
    add(r, el('span', '', ad), el('b', '', f2(kul) + ' / ' + f2(lim) + ' $'));
    var c = el('div', 'cub'), i = el('i', pct >= 90 ? 'k' : (pct >= 70 ? 's' : ''));
    i.style.width = Math.min(Math.max(num(pct) ? pct : 0, 0), 100) + '%';
    return add(w, r, add(c, i));
  }
  function tabTeknik(root, p) {
    clear(root);
    var t = p.teknik;
    if (t.saglik) {
      add(root, katli('Sağlık', t.saglik.renk, function (b) {
        add(b, add(el('div'), rozetRenk(t.saglik.durum, t.saglik.renk)));
        t.saglik.uyarilar.forEach(function (u) { add(b, el('div', 'yok', u)); });
        (t.saglik.diger_botlar || []).forEach(function (u) { add(b, el('div', 'yok gri', u)); });
        (t.saglik.senden || []).forEach(function (u) { add(b, el('div', 'yok', 'Senden: ' + u)); });
        if (t.saglik.kontrol_bayat) add(b, el('div', 'yok kotu', 'Sağlık kontrolü bir süredir çalışmamış.'));
        return b;
      }, t.saglik.renk !== 'yesil'));
    }
    if (t.dayaniklilik) add(root, katli('Dayanıklılık', 'sari', function (b) {
      t.dayaniklilik.karantina.forEach(function (u) { add(b, el('div', 'yok kotu', u)); });
      t.dayaniklilik.sembol.forEach(function (u) { add(b, el('div', 'yok kotu', u)); });
      return b;
    }, true));
    if (t.limitler) add(root, katli('Risk limitleri', '', function (b) {
      t.limitler.forEach(function (r) { add(b, bar(r.ad, r.kullanilan, r.limit, r.yuzde)); });
      return b;
    }));
    if (t.kapilar) add(root, katli('Kalite kapıları', '', function (b) {
      t.kapilar.forEach(function (r) { add(b, satir(r.ad, r.not, r.ok ? 'iyi' : 'kotu')); });
      return b;
    }));
    if (t.model) add(root, katli('Model ayrıntısı', '', function (b) {
      t.model.forEach(function (r) { add(b, satir(r.ad + ' · bugünkü çağrı', String(r.cagri_bugun)), satir('Bu ay maliyet', usd(r.maliyet_ay))); });
      return b;
    }));
    if (t.butce) add(root, katli('Bütçe', '', function (b) {
      return add(b, satir('Bu ay kullanılan', usd(t.butce.kullanilan)), satir('Aylık tavan', usd(t.butce.tavan)));
    }));
    if (t.kayitlar) add(root, katli('Kayıtlar', '', function (b) {
      return add(b, satir('Kapanan işlem', String(t.kayitlar.kapanan)), satir('Açık işlem', String(t.kayitlar.acik)), satir('Değerlendirilen fırsat', String(t.kayitlar.karar)));
    }));
    if (t.mutabakat) add(root, katli('İşlem kontrolü', t.mutabakat.uyusmazlik > 0 ? 'sari' : '', function (b) {
      return add(b, el('div', t.mutabakat.uyusmazlik > 0 ? 'yok kotu' : 'yok', 'Son kontrol: ' + t.mutabakat.son + ', ' + t.mutabakat.islem + ' işlem, ' + t.mutabakat.uyusmazlik + ' uyuşmazlık'));
    }));
    if (t.dogrulama) add(root, katli('Backtest / doğrulama', '', function (b) {
      if (num(t.dogrulama.eslesme)) add(b, satir('Kâğıt ile geçmiş test eşleşmesi', '%' + trn(t.dogrulama.eslesme * 100, 0)));
      if (num(t.dogrulama.pbo)) add(b, satir('Aşırı uyum riski (en yüksek)', '%' + trn(t.dogrulama.pbo * 100, 0)));
      if (t.dogrulama.uyari) add(b, el('div', 'yok kotu', 'Doğrulama raporunda uyarı var.'));
      return b;
    }));
    if (!root.firstChild) add(root, yokKart('Teknik veri yok.'));
  }

  function ciz(p) {
    renderTop(p);
    ['ozet', 'acik', 'kz', 'ogrenme', 'teknik'].forEach(function (k) { clear($('sek-' + k)); });
    if (!p || !p.ok) { add($('sek-ozet'), yokKart('Veri şu an okunamıyor.')); return; }
    S.gen = p.generated_at;
    tabOzet($('sek-ozet'), p); tabAcik($('sek-acik'), p); tabKz($('sek-kz'), p); tabOgrenme($('sek-ogrenme'), p); tabTeknik($('sek-teknik'), p);
  }

  /* ---------- baslat ---------- */
  function guncellemeEtiketi() {
    var u = $('uretim'), g = SNAP ? SNAP.generated_at : null;
    var s = g ? (Date.now() - Date.parse(g)) / 1000 : (Date.now() - S.t0) / 1000;
    u.textContent = 'son güncelleme ' + ago(s);
    if ((Date.now() - S.t0) / 1000 >= YENILE_S && location && typeof location.reload === 'function') location.reload();
  }
  function tema(v) {
    document.documentElement.setAttribute('data-theme', v);
    try { localStorage.setItem('pano_tema', v); } catch (e) { /* onemsiz */ }
  }
  function baslat() {
    siraOku();
    var iframe = false;
    try { iframe = window.self !== window.top; } catch (e) { iframe = true; }
    var tb = $('tema');
    if (iframe) {                                           // gomulu: kendi basligi ve Yenile/Tema yok; cihaz ayari izlenir
      document.documentElement.classList.add('gomulu');
      if (tb) tb.hidden = true;
    } else {
      var kay = null;
      try { kay = localStorage.getItem('pano_tema'); } catch (e) { kay = null; }
      if (kay === 'light' || kay === 'dark') document.documentElement.setAttribute('data-theme', kay);   // kayit yoksa: cihaz (CSS media)
      tb.addEventListener('click', function () {
        var d = document.documentElement.getAttribute('data-theme');
        if (d !== 'light' && d !== 'dark') d = (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'light';
        tema(d === 'dark' ? 'light' : 'dark');
      });
    }
    $('yenile').addEventListener('click', function () { location.reload(); });
    if ($('snap-bant')) $('snap-bant').style.display = 'none';
    snapBanner();
    kurTabs();
    var son = null;
    try { son = localStorage.getItem('pano_sekme'); } catch (e) { son = null; }
    sec(TABS.some(function (x) { return x[0] === son; }) ? son : 'ozet');
    if (SNAP) $('damga').style.display = 'none';
    get('/api/pano?bot=' + BOT).then(function (p) { S.pano = p; ciz(p); sekmeSayilari(p); guncellemeEtiketi(); if (S.tab === 'kapanan') yukleKapanan(); });
    setInterval(function () { snapBanner(); guncellemeEtiketi(); }, 30000);     // yalniz etiket; ekran yeniden cizilmez
  }
  baslat();
})();
