/* 루아미 견적 폼 2단계(index.html#contact) — 1단계 행사 유형 큰 버튼 1클릭 → 2단계 날짜·지역·연락처.
   JS 가 없으면 두 단계가 한 화면에 모두 보이고 그대로 전송된다(필드 이름·전송 주소는 HTML 그대로).
   키보드: 화살표로 고르는 동안에는 넘어가지 않고, Enter·Space 또는 '다음 단계로' 버튼으로 넘어간다. */
(function () {
  'use strict';
  var f = document.getElementById('quoteForm');
  if (!f) return;
  var s1 = f.querySelector('.qf-s1'), s2 = f.querySelector('.qf-s2');
  var pn = f.querySelector('.qf-pn b'), pt = f.querySelector('.qf-pt');
  var back = f.querySelector('.qf-back'), next = f.querySelector('.qf-next');
  var radios = f.querySelectorAll('input[name="event_type"]');
  var picked = function () { return f.querySelector('input[name="event_type"]:checked'); };
  function go(n, focus) {
    if (n === 2 && !picked()) n = 1;
    f.setAttribute('data-step', String(n));
    s1.hidden = n !== 1;
    s2.hidden = n !== 2;
    pn.textContent = String(n);
    pt.textContent = n === 1 ? '행사 종류' : '날짜·장소·연락처';
    if (next) next.disabled = !picked();
    if (focus) {
      var t = n === 1 ? (picked() || radios[0]) : s2.querySelector('input[name="event_date"]');
      if (t) t.focus({ preventScroll: true });
    }
  }
  f.classList.add('qf-on');
  var viaArrow = false;
  f.addEventListener('keydown', function (e) {
    viaArrow = /^Arrow/.test(e.key);
    if (e.key === 'Enter' && e.target.name === 'event_type') { e.preventDefault(); e.target.checked = true; go(2, true); }
  }, true);
  for (var i = 0; i < radios.length; i++) {
    radios[i].addEventListener('click', function () {
      if (viaArrow) { viaArrow = false; if (next) next.disabled = false; return; }
      go(2, true);
    });
  }
  if (next) next.addEventListener('click', function () { go(2, true); });
  back.addEventListener('click', function () { go(1, true); });
  f.addEventListener('submit', function (e) {
    if (!picked()) { e.preventDefault(); go(1, true); }
  });
  go(picked() ? 2 : 1, false);

  /* 제품 맥락 유지(D01) — 제품 상세에서 견적을 누르고 왔으면 그 제품을 미리 고른다.
     ① ?product=<제품 이름>(build_products.py 가 상세·허브·가격표 견적 링크에 싣는다) — 선택지에 없는 값은 무시
     ② 없으면 같은 사이트 referrer /products/<slug>.html → 선택지의 data-slug (머리·하단 바 '무료 견적'은 제품을 싣지 않는다)
     고른 제품은 폼 맨 위에 '선택한 제품: …' 으로 보이고 '제품·대수' 칸을 펼친다. source_page = 들어온 페이지(같은 사이트일 때). */
  var sel = f.querySelector('select[name="product"]');
  var srcPage = f.querySelector('input[name="source_page"]');
  var ref = null;
  try { var r = new URL(document.referrer); if (r.origin === location.origin) ref = r; } catch (e) { ref = null; }
  if (srcPage && ref && ref.pathname !== location.pathname) srcPage.value = decodeURIComponent(ref.pathname.replace(/^\//, ''));
  if (!sel) return;
  var DEFAULT = '아직 모르겠어요';
  var opt = null, want = null, i;
  try { want = new URLSearchParams(location.search).get('product'); } catch (e) { want = null; }
  if (want) for (i = 0; i < sel.options.length; i++) if (sel.options[i].value === want) { opt = sel.options[i]; break; }
  if (!opt && ref) {
    var m = ref.pathname.match(/\/products\/([a-z0-9-]+?)(?:\.html)?$/);
    if (m) opt = sel.querySelector('option[data-slug="' + m[1] + '"]');
  }
  var line = document.createElement('p');
  line.className = 'qf-picked';
  line.setAttribute('aria-live', 'polite');
  var prog = f.querySelector('.qf-prog');
  if (prog && prog.nextSibling) f.insertBefore(line, prog.nextSibling); else f.appendChild(line);
  function show() {
    var v = sel.value;
    line.hidden = !v || v === DEFAULT;
    line.textContent = '';
    if (line.hidden) return;
    line.appendChild(document.createTextNode('선택한 제품: '));
    var b = document.createElement('b'); b.textContent = v; line.appendChild(b);
  }
  if (opt) {
    sel.value = opt.value;
    var more = f.querySelector('details.qf-more');
    if (more) more.open = true;
  }
  show();
  sel.addEventListener('change', show);
})();
