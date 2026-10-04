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
})();
