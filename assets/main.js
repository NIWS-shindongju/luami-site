/* Luami shared JS */
document.addEventListener('DOMContentLoaded', function(){
  requestAnimationFrame(function(){
    document.querySelectorAll('.hero h1,.hero .sub').forEach(function(e){e.classList.add('in')});
  });
  try{
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{threshold:0.12,rootMargin:'0px 0px -6% 0px'});
    document.querySelectorAll('.fade,.lm').forEach(function(el){io.observe(el)});
  }catch(e){document.querySelectorAll('.fade,.lm').forEach(function(e){e.classList.add('in')})}
  /* 실패세이프: 무슨 일이 있어도 2.6초 뒤 전부 노출.
     transition에 기대지 않고 즉시 최종 상태로 스냅 — 백그라운드 탭 등에서
     transition이 progress:0에 멈춰 텍스트가 영구히 안 보이는 경우 방지. */
  function revealHard(el){
    var t = el.classList.contains('lm') ? el.querySelector(':scope>span') : el;
    var prev = t ? t.style.transition : '';
    if(t) t.style.transition='none';
    el.classList.add('in');
    if(t){ void t.offsetHeight; t.style.transition=prev; }
  }
  setTimeout(function(){document.querySelectorAll('.fade,.lm,.hero h1,.hero .sub').forEach(revealHard)},2600);
  /* 스티키 헤더 */
  var sbar=document.getElementById('sbar'),prog=document.getElementById('prog'),sbarFailsafeArmed=false;
  addEventListener('scroll',function(){
    var st=window.pageYOffset||document.documentElement.scrollTop;
    if(sbar){
      var shouldShow=st>innerHeight*0.85;
      sbar.classList.toggle('show',shouldShow);
      /* 실패세이프: transition이 멈춰 스티키바가 완전히 나타나지 않는 경우 방지 */
      if(shouldShow && !sbarFailsafeArmed){
        sbarFailsafeArmed=true;
        setTimeout(function(){
          if(sbar.classList.contains('show') && getComputedStyle(sbar).transform!=='none'){
            sbar.style.transition='none';sbar.style.transform='none';
            void sbar.offsetHeight;
            sbar.style.transition='';sbar.style.transform='';
          }
          sbarFailsafeArmed=false;
        },700);
      }
    }
    if(prog){var d=document.documentElement;prog.style.width=(st/(d.scrollHeight-d.clientHeight)*100)+'%'}
  },{passive:true});
  /* 모바일 바텀시트 네비 */
  var drawer=document.getElementById('drawer'), scrim=document.getElementById('drawerScrim');
  function dOpen(){
    if(!drawer)return;
    drawer.classList.add('open');scrim&&scrim.classList.add('open');document.body.classList.add('nav-open');drawer.setAttribute('aria-hidden','false');
    var t=document.getElementById('navToggle');t&&t.setAttribute('aria-expanded','true');
    /* 실패세이프: transition이 progress:0에 멈춰 드로어가 열린 것처럼 보이지 않는 경우 방지 */
    setTimeout(function(){
      if(drawer.classList.contains('open') && getComputedStyle(drawer).visibility!=='visible'){
        drawer.style.transition='none';drawer.style.transform='none';drawer.style.visibility='visible';
        void drawer.offsetHeight;
        drawer.style.transition='';drawer.style.transform='';drawer.style.visibility='';
      }
    },700);
  }
  function dClose(){if(!drawer)return;drawer.classList.remove('open');scrim&&scrim.classList.remove('open');document.body.classList.remove('nav-open');drawer.setAttribute('aria-hidden','true');var t=document.getElementById('navToggle');t&&t.setAttribute('aria-expanded','false');}
  ['navToggle','navToggle2'].forEach(function(id){var b=document.getElementById(id);if(b)b.addEventListener('click',dOpen);});
  var dcl=document.getElementById('drawerClose');if(dcl)dcl.addEventListener('click',dClose);
  if(scrim)scrim.addEventListener('click',dClose);
  if(drawer){drawer.querySelectorAll('a').forEach(function(a){a.addEventListener('click',dClose);});}
  document.addEventListener('keydown',function(e){if(e.key==='Escape')dClose();});

  /* 모바일 전용 — 롱프레스 셔터: 클릭이 아니라 "누르고 있는 시간"으로 히어로 사진을 인화시킨다 */
  (function(){
    var btn=document.getElementById('shutterBtn');
    if(!btn) return;
    /* 진행 링은 순수 CSS transition(컴포지터 구동)이 채운다 — JS는 완료 판정(setTimeout)만
       맡는다. rAF 스텝 루프에 기대지 않아 저사양 기기·백그라운드 리페인트 지연에도 안정적. */
    var HOLD_MS=850, timer=null, done=false;
    function develop(){
      done=true; btn.classList.remove('pressing'); btn.classList.add('done');
      var label=btn.querySelector('.shutter-label'); if(label) label.innerHTML='DONE<br>인화됨';
      var imgs=document.querySelectorAll('.hero-mosaic .hm img');
      if(window.gsap && !matchMedia('(prefers-reduced-motion: reduce)').matches){
        gsap.fromTo(imgs,{filter:'grayscale(0.85) contrast(.75) brightness(.55) sepia(.15)'},{filter:'none',duration:1.1,ease:'power2.out',stagger:0.06});
        gsap.fromTo('.hero-mosaic',{scale:0.985},{scale:1,duration:1.1,ease:'power2.out'});
      }
      if(navigator.vibrate) try{navigator.vibrate(12)}catch(e){}
    }
    function start(e){
      if(done) return;
      btn.classList.add('pressing');
      timer=setTimeout(develop,HOLD_MS);
    }
    function cancel(){
      if(done) return;
      btn.classList.remove('pressing');
      if(timer) clearTimeout(timer); timer=null;
    }
    btn.addEventListener('pointerdown',start);
    btn.addEventListener('pointerup',cancel);
    btn.addEventListener('pointerleave',cancel);
    btn.addEventListener('pointercancel',cancel);
    btn.addEventListener('contextmenu',function(e){e.preventDefault()});
  })();

  /* 모바일 전용 — wall 피드의 "지금 촬영 중" 카운터: 그리드가 아니라 스와이프 피드이므로 현재 보이는 컷을 센다 */
  (function(){
    var wall=document.querySelector('.wall'), counter=document.getElementById('wfCount');
    if(!wall||!counter) return;
    var items=wall.querySelectorAll('.w');
    if(!items.length) return;
    function pad(n){return n<10?'0'+n:''+n}
    function render(i){counter.textContent=pad(i+1)+' / '+pad(items.length)}
    render(0);
    if(!('IntersectionObserver' in window)) return;
    var current=0;
    var io=new IntersectionObserver(function(entries){
      entries.forEach(function(en){
        if(en.isIntersecting && en.intersectionRatio>0.55){
          var idx=Array.prototype.indexOf.call(items,en.target);
          if(idx>-1 && idx!==current){current=idx;render(idx)}
        }
      });
    },{root:wall,threshold:[0.55]});
    items.forEach(function(el){io.observe(el)});
  })();
});

/* 시그니처: Lenis 관성 스무스 스크롤 — 실패해도 브라우저 기본 스크롤로 정상 동작 */
(function(){
  try{
    if(matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    if(typeof Lenis==='undefined') return;
    var lenis=new Lenis({duration:1.1,easing:function(t){return t===1?1:1-Math.pow(2,-10*t)}});
    window.__lenis=lenis;
    if(window.gsap&&window.ScrollTrigger){
      lenis.on('scroll',ScrollTrigger.update);
      gsap.ticker.add(function(time){lenis.raf(time*1000)});
      gsap.ticker.lagSmoothing(0);
    } else {
      requestAnimationFrame(function raf(time){lenis.raf(time);requestAnimationFrame(raf)});
    }
  }catch(e){}
})();

/* 강화 레이어(선택): GSAP 스크롤·패럴럭스·마그네틱·핀 갤러리. 실패해도 head 스크립트가 콘텐츠·리빌 보장 */
(function(){
  try{
    if(!(window.gsap&&window.ScrollTrigger)) return;
    gsap.registerPlugin(ScrollTrigger);
    /* 히어로 이미지 미세 패럴럭스 (홈 외 페이지엔 .hero가 없으므로 가드) */
    if(document.querySelector('.hero')){
      gsap.to('.hero-mosaic',{yPercent:-3.5,ease:'none',scrollTrigger:{trigger:'.hero',start:'top top',end:'bottom top',scrub:1}});
      /* 필름 인화 이미지 시퀀스 — 히어로를 지나는 동안 hm-a 사진 5장을 스크럽 진행률로 크로스디졸브 */
      var hmSeq=document.getElementById('hmSeq'), hmChip=document.getElementById('hmChip');
      if(hmSeq && !matchMedia('(prefers-reduced-motion: reduce)').matches){
        var hmImgs=hmSeq.querySelectorAll('img');
        if(hmImgs.length>1){
          var hmCurrent=0;
          ScrollTrigger.create({
            trigger:'.hero', start:'top top', end:'bottom top', scrub:true,
            onUpdate:function(self){
              var idx=Math.min(hmImgs.length-1, Math.floor(self.progress*hmImgs.length));
              if(idx!==hmCurrent){
                hmImgs[hmCurrent].classList.remove('hm-on');
                hmImgs[idx].classList.add('hm-on');
                hmCurrent=idx;
                if(hmChip) hmChip.textContent=hmImgs[idx].getAttribute('data-caption')||'';
              }
            }
          });
        }
      }
    }
    /* 마그네틱 버튼 */
    document.querySelectorAll('.btn,.btn-ghost').forEach(function(b){
      b.addEventListener('mousemove',function(e){var r=b.getBoundingClientRect();gsap.to(b,{x:(e.clientX-r.left-r.width/2)*0.12,y:(e.clientY-r.top-r.height/2)*0.16,duration:0.5,ease:'power2.out'})});
      b.addEventListener('mouseleave',function(){gsap.to(b,{x:0,y:0,duration:0.5,ease:'power2.out'})});
    });
    /* 시그니처: 필름 릴 — 세로 스크롤로 가로 컨택트 시트를 넘긴다.
       ★GSAP pin:true는 핀 유지용 width를 캡처하다가 flex-basis를 전부 0px로
       붕괴시키는 결함이 실측으로 재현됐다(로드 타이밍과 무관). 그래서 pin은 안 쓴다 —
       고정은 순수 CSS position:sticky(.filmreel)가 담당하고, 여기선 스크롤 진행률에 맞춰
       .filmreel-sec의 높이(스크롤 여유)를 잡고 x축 이동만 스크럽한다. */
    function initFilmReel(){
      var sec=document.querySelector('.filmreel-sec'), frTrack=document.getElementById('frTrack');
      if(!sec || !frTrack || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      function distance(){return Math.max(0, frTrack.scrollWidth - window.innerWidth + 80);}
      function sizeSection(){sec.style.height=(window.innerHeight + distance())+'px';}
      sizeSection();
      /* 필름 컷 카운터 — 스크럽 진행률을 프레임 번호로 표시(브랜드의 필름 모티프 강화) */
      var counter=document.getElementById('frCounter');
      var total=frTrack.querySelectorAll('.fr-cell').length || 8;
      function pad2(n){return n<10?'0'+n:''+n}
      function updateCounter(p){
        if(!counter) return;
        var idx=Math.max(0,Math.min(total-1, Math.floor(p*total)));
        counter.textContent='CUT '+pad2(idx+1)+'/'+pad2(total);
      }
      var trig=gsap.to(frTrack,{
        x:function(){return -distance();},
        ease:'none',
        scrollTrigger:{
          trigger:sec,
          start:'top top',
          end:function(){return '+=' + distance();},
          scrub:0.6,
          invalidateOnRefresh:true,
          onUpdate:function(self){updateCounter(self.progress)}
        }
      });
      window.addEventListener('resize',function(){sizeSection();ScrollTrigger.refresh();});
    }
    /* ★CLS 실측 결함 수정: 예전엔 window 'load'(모든 이미지 로드 완료, 페이지 맨 끝)까지 기다렸다가
       .filmreel-sec 높이를 인라인으로 주입해 그 순간 아래 섹션 전체가 수천 px 밀리는 대형 레이아웃
       시프트가 있었다. .fr-track 너비는 이미지 크기가 아니라 CSS flex-basis(clamp)로만 정해지므로
       이미지 로드를 기다릴 필요가 없다 — defer 스크립트 실행 시점(DOM+CSS 적용 직후)에 한 번만
       호출한다(resize 대응은 함수 내부의 리스너가 이미 담당 — 여기서 또 부르면 트윈이 중복 생성됨). */
    initFilmReel();
    /* 3D 틸트 카드 — 커서 위치에 따라 살짝 기울어짐(모델링 느낌의 깊이감) */
    if(matchMedia('(hover:hover)').matches && !matchMedia('(prefers-reduced-motion: reduce)').matches){
      document.querySelectorAll('.gpanel,.explore-card,.wall .w,.case').forEach(function(card){
        card.addEventListener('mousemove',function(e){
          var r=card.getBoundingClientRect();
          var px=(e.clientX-r.left)/r.width-0.5, py=(e.clientY-r.top)/r.height-0.5;
          gsap.to(card,{rotateY:px*10,rotateX:py*-10,duration:0.4,ease:'power2.out',transformPerspective:800});
        });
        card.addEventListener('mouseleave',function(){gsap.to(card,{rotateY:0,rotateX:0,duration:0.6,ease:'power3.out'})});
      });
    }
    /* 히어로 모자이크 — 커서를 따라 레이어마다 다른 깊이로 움직임 */
    var heroEl=document.querySelector('.hero');
    var hm=document.querySelectorAll('.hero-mosaic .hm');
    if(heroEl && hm.length && matchMedia('(hover:hover)').matches && !matchMedia('(prefers-reduced-motion: reduce)').matches){
      var qx=[],qy=[];
      hm.forEach(function(el,i){qx[i]=gsap.quickTo(el,'x',{duration:0.7,ease:'power3.out'});qy[i]=gsap.quickTo(el,'y',{duration:0.7,ease:'power3.out'});});
      var spotlight=document.querySelector('.hero-spotlight');
      heroEl.addEventListener('mousemove',function(e){
        var r=heroEl.getBoundingClientRect();
        var px=(e.clientX-r.left)/r.width-0.5, py=(e.clientY-r.top)/r.height-0.5;
        hm.forEach(function(el,i){var depth=(i+1)*7;qx[i](px*depth);qy[i](py*depth*0.6);});
        if(spotlight){spotlight.style.setProperty('--mx',((px+0.5)*100)+'%');spotlight.style.setProperty('--my',((py+0.5)*100)+'%');}
      });
      heroEl.addEventListener('mouseleave',function(){hm.forEach(function(el,i){qx[i](0);qy[i](0);});});
    }
    window.addEventListener('load',function(){ScrollTrigger.refresh();});
  }catch(e){}
})();

/* 시그니처: 히어로 사인파 리플 배경 (습득자산 SKILLS_ACQUIRED#3 재사용 — antenucci 기법, 루아미 그린 톤) */
(function(){
  try{
    var svg=document.querySelector('.hero-ripple');
    if(!svg) return;
    if(matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    var W=1200,H=700,LINES=11,PTS=48,paths=[];
    for(var i=0;i<LINES;i++){
      var p=document.createElementNS('http://www.w3.org/2000/svg','path');
      var t=i/(LINES-1);
      var r=Math.round(76+(245-76)*t), g=Math.round(133+(240-133)*t), b=Math.round(103+(222-103)*t);
      p.setAttribute('stroke','rgba('+r+','+g+','+b+','+(0.05+0.09*(1-Math.abs(t-0.5)*2)).toFixed(3)+')');
      p.setAttribute('fill','none');
      p.setAttribute('stroke-width','1.2');
      svg.appendChild(p);
      paths.push(p);
    }
    var running=false,rafId=null;
    function frame(ts){
      for(var i=0;i<LINES;i++){
        var baseY=60+(H-120)*(i/(LINES-1));
        var phase=ts/1600+i*0.32;
        var d='';
        for(var j=0;j<=PTS;j++){
          var x=(W/PTS)*j;
          var y=baseY+Math.sin(j/7+phase)*20+Math.sin(j/2.6-phase*1.6)*6;
          d+=(j?' L':'M')+x.toFixed(1)+' '+y.toFixed(1);
        }
        paths[i].setAttribute('d',d);
      }
      if(running) rafId=requestAnimationFrame(frame);
    }
    function start(){if(running)return;running=true;rafId=requestAnimationFrame(frame);}
    function stop(){running=false;if(rafId)cancelAnimationFrame(rafId);rafId=null;}
    /* 화면 밖이거나 탭이 백그라운드면 정지 — 불필요한 CPU/배터리 소모 방지 */
    if('IntersectionObserver' in window){
      new IntersectionObserver(function(es){es.forEach(function(e){e.isIntersecting&&!document.hidden?start():stop()})},{threshold:0}).observe(svg);
    } else { start(); }
    document.addEventListener('visibilitychange',function(){document.hidden?stop():(svg.getBoundingClientRect().bottom>0&&start())});
  }catch(e){}
})();

/* 해시 앵커 — 핀 갤러리 레이아웃 반영 후 재정렬 */
window.addEventListener('load',function(){
  if(location.hash){setTimeout(function(){var el=document.querySelector(location.hash);if(el)el.scrollIntoView({block:'start'});},450);}
});
document.addEventListener('click',function(e){
  var a=e.target.closest('a[href^="#"]');if(!a)return;var el=document.querySelector(a.getAttribute('href'));
  if(el){setTimeout(function(){el.scrollIntoView({behavior:'smooth',block:'start'});},60);}
});
