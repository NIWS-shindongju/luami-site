/* 루아미 제품 허브·상세·가격 페이지 전용 JS (tools/build_products.py 생성 페이지)
   1) 허브 필터 칩  2) 사진 라이트박스(키보드 ←/→/Esc · 모바일 스와이프 · 이웃 사진 미리 읽기)
   JS 가 없어도 모든 사진 링크는 원본 이미지로 열리고, 필터 없이 전 제품이 다 보인다. */
(function () {
  'use strict';

  /* 1) 허브 필터 */
  var grid = document.getElementById('pcGrid');
  if (grid) {
    var chips = document.querySelectorAll('.fchip');
    var count = document.getElementById('fcount');
    var cards = grid.querySelectorAll('.pc');
    var apply = function (f) {
      var n = 0;
      cards.forEach(function (c) {
        var on = !f || (' ' + c.getAttribute('data-tags') + ' ').indexOf(' ' + f + ' ') > -1;
        c.hidden = !on;
        if (on) n++;
      });
      chips.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-filter') === f)); });
      if (count) count.textContent = f ? n + '개 제품을 보고 있어요.' : '';
    };
    chips.forEach(function (b) {
      b.addEventListener('click', function () { apply(b.getAttribute('data-filter')); });
    });
  }

  /* 2) 라이트박스 */
  var groups = document.querySelectorAll('[data-gallery]');
  if (!groups.length) return;
  var lb, img, cap, cnt, btnPrev, btnNext, btnClose, items = [], idx = 0, last = null;

  function build() {
    lb = document.createElement('div');
    lb.className = 'lb';
    lb.hidden = true;
    lb.setAttribute('role', 'dialog');
    lb.setAttribute('aria-modal', 'true');
    lb.setAttribute('aria-label', '사진 크게 보기');
    lb.setAttribute('data-lenis-prevent', '');
    lb.innerHTML =
      '<div class="lb-top"><span class="lb-count" aria-live="polite"></span>' +
      '<button type="button" class="lb-close" aria-label="닫기 (Esc)">✕</button></div>' +
      '<button type="button" class="lb-prev" aria-label="이전 사진">‹</button>' +
      '<figure class="lb-fig"><img alt=""><figcaption class="lb-cap"></figcaption></figure>' +
      '<button type="button" class="lb-next" aria-label="다음 사진">›</button>';
    document.body.appendChild(lb);
    img = lb.querySelector('img');
    cap = lb.querySelector('.lb-cap');
    cnt = lb.querySelector('.lb-count');
    btnPrev = lb.querySelector('.lb-prev');
    btnNext = lb.querySelector('.lb-next');
    btnClose = lb.querySelector('.lb-close');
    btnPrev.addEventListener('click', function () { show(idx - 1); });
    btnNext.addEventListener('click', function () { show(idx + 1); });
    btnClose.addEventListener('click', close);
    lb.addEventListener('click', function (e) { if (e.target === lb || e.target.classList.contains('lb-fig')) close(); });
    img.addEventListener('load', function () { img.classList.remove('loading'); });
    lb.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); close(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); show(idx - 1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); show(idx + 1); }
      else if (e.key === 'Tab') { /* 포커스를 대화상자 안에 가둔다 */
        var f = [btnClose, btnPrev, btnNext].filter(function (b) { return !b.hidden; });
        var i = f.indexOf(document.activeElement);
        e.preventDefault();
        f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
      }
    });
    /* 스와이프: 가로 50px 이상이면 넘김, 아래로 90px 이상이면 닫기.
       .lb 는 touch-action:pinch-zoom — 한 손가락 끌기를 브라우저 스크롤(pan-y)에 넘기지 않아야 세로 스와이프가
       pointercancel 로 끊기지 않는다(예전 pan-y 에선 아래로 쓸어도 닫히지 않았음, r2 S1 실측). 두 손가락 확대는 그대로 된다. */
    var sx = 0, sy = 0, tracking = false;
    lb.addEventListener('pointerdown', function (e) { if (e.pointerType === 'mouse') return; tracking = true; sx = e.clientX; sy = e.clientY; });
    lb.addEventListener('pointerup', function (e) {
      if (!tracking) return;
      tracking = false;
      var dx = e.clientX - sx, dy = e.clientY - sy;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy)) show(idx + (dx < 0 ? 1 : -1));
      else if (dy > 90 && Math.abs(dy) > Math.abs(dx)) close();
    });
    lb.addEventListener('pointercancel', function () { tracking = false; });
  }

  function preload(i) {
    var it = items[(i + items.length) % items.length];
    if (it && !it.pre) { it.pre = new Image(); it.pre.src = it.href; }
  }

  function show(i) {
    idx = (i + items.length) % items.length;
    var it = items[idx];
    img.classList.add('loading');
    img.src = it.href;
    img.alt = it.alt;
    if (it.w && it.h) { img.width = it.w; img.height = it.h; }
    cap.textContent = it.caption || '';
    cnt.textContent = (idx + 1) + ' / ' + items.length;
    var multi = items.length > 1;
    btnPrev.hidden = !multi;
    btnNext.hidden = !multi;
    preload(idx + 1);
    preload(idx - 1);
  }

  function open(list, i, trigger) {
    if (!lb) build();
    items = list;
    last = trigger;
    lb.hidden = false;
    document.documentElement.classList.add('lb-open');
    if (window.__lenis) window.__lenis.stop();
    show(i);
    btnClose.focus();
  }

  function close() {
    lb.hidden = true;
    document.documentElement.classList.remove('lb-open');
    if (window.__lenis) window.__lenis.start();
    if (last) last.focus();
  }

  groups.forEach(function (g) {
    var links = Array.prototype.slice.call(g.querySelectorAll('a.pg-item'));
    var list = links.map(function (a) {
      var im = a.querySelector('img');
      return { href: a.getAttribute('href'), alt: im ? im.alt : '', caption: a.getAttribute('data-caption') || '',
        w: +a.getAttribute('data-w') || 0, h: +a.getAttribute('data-h') || 0 };
    });
    links.forEach(function (a, i) {
      a.setAttribute('aria-label', (list[i].alt || '사진') + ' — 크게 보기');
      a.addEventListener('click', function (e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button === 1) return;
        e.preventDefault();
        open(list, i, a);
      });
    });
  });
})();
