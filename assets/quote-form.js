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
  /* 휴대폰 칸 — 형식이 틀리면 한국어로 안내(CV-04 · pattern 은 HTML 에 있어 JS 가 없어도 브라우저가 막는다) */
  var phone = f.querySelector('input[name="phone"]');
  if (phone) {
    phone.addEventListener('invalid', function () {
      phone.setCustomValidity(phone.validity.valueMissing ? '연락받으실 휴대폰 번호를 적어 주세요.' : '휴대폰 번호를 010-1234-5678 처럼 적어 주세요.');
    });
    phone.addEventListener('input', function () { phone.setCustomValidity(''); });
  }
  /* 두 번 전송 막기(CV-07) — 전송이 시작되면 버튼을 잠그고 '보내는 중…'. 뒤로 가기(bfcache)로 돌아오면 되돌린다 */
  var sub = f.querySelector('button[type="submit"]');
  var subT = sub && sub.querySelector('.cbtn-t');
  var subLabel = subT ? subT.textContent : '';
  function unlock() { if (sub) { sub.disabled = false; sub.removeAttribute('aria-busy'); if (subT) subT.textContent = subLabel; } }
  f.addEventListener('submit', function (e) {
    if (!picked()) { e.preventDefault(); go(1, true); return; }
    if (e.defaultPrevented || !sub) return;
    if (sub.disabled) { e.preventDefault(); return; }
    /* 잠그는 건 이번 전송이 시작된 다음 틱 — 같은 틱에 disabled 를 걸면 일부 브라우저가 전송 자체를 취소한다 */
    setTimeout(function () { sub.disabled = true; sub.setAttribute('aria-busy', 'true'); if (subT) subT.textContent = '보내는 중…'; }, 0);
  });
  window.addEventListener('pageshow', function (e) { if (e.persisted) unlock(); });
  /* 입력 중에는 모바일 하단 바를 내려 입력칸·키보드 위를 가리지 않는다(A11Y-02) */
  var root = document.documentElement, hideT = null;
  f.addEventListener('focusin', function (e) {
    if (!/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
    clearTimeout(hideT); root.classList.add('mcta-hide');
  });
  f.addEventListener('focusout', function () {
    clearTimeout(hideT);
    hideT = setTimeout(function () { if (!f.contains(document.activeElement) || !/^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement.tagName)) root.classList.remove('mcta-hide'); }, 150);
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
  /* '/' 와 '/index.html' 은 같은 페이지(콜드메일·검색은 루트로 들어온다) — 같으면 정적값 index.html 을 둔다.
     깨진 %인코딩 referrer 는 디코딩하지 않고 그대로 쓴다(예외로 아래 제품 미리선택까지 멈추지 않게). */
  function pagePath(p) { var s = p.replace(/^\//, ''); try { s = decodeURIComponent(s); } catch (e) { /* 원문 유지 */ } return s || 'index.html'; }
  if (srcPage && ref && pagePath(ref.pathname) !== pagePath(location.pathname)) srcPage.value = pagePath(ref.pathname);
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
  /* 홈 안에서 고르는 견적(2026-10-20) — <a href="#contact" data-pick-product="포토키오스크"> 를 누르면 새로고침 없이
     그 제품을 미리 고른다(?product= 링크는 페이지를 다시 불러온다, CV-06). 선택지에 없는 값은 무시. */
  document.addEventListener('click', function (e) {
    var a = e.target && e.target.closest ? e.target.closest('[data-pick-product]') : null;
    if (!a) return;
    var v = a.getAttribute('data-pick-product');
    for (var j = 0; j < sel.options.length; j++) if (sel.options[j].value === v) {
      sel.value = v;
      var more = f.querySelector('details.qf-more');
      if (more) more.open = true;
      show();
      break;
    }
  });
})();
