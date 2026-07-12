/* Luami shared JS */
document.addEventListener('DOMContentLoaded', function(){
  requestAnimationFrame(function(){
    document.querySelectorAll('.hero h1,.hero .sub').forEach(function(e){e.classList.add('in')});
  });
  try{
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{threshold:0.12,rootMargin:'0px 0px -6% 0px'});
    document.querySelectorAll('.fade,.lm,.manifesto h2').forEach(function(el){io.observe(el)});
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
  setTimeout(function(){document.querySelectorAll('.fade,.lm,.hero h1,.hero .sub,.manifesto h2').forEach(revealHard)},2600);
  /* 스티키 헤더 */
  var sbar=document.getElementById('sbar'),prog=document.getElementById('prog');
  addEventListener('scroll',function(){var st=window.pageYOffset||document.documentElement.scrollTop;if(sbar)sbar.classList.toggle('show',st>innerHeight*0.85);if(prog){var d=document.documentElement;prog.style.width=(st/(d.scrollHeight-d.clientHeight)*100)+'%'}},{passive:true});
  /* 모바일 드로어 네비 */
  var drawer=document.getElementById('drawer');
  function dOpen(){if(!drawer)return;drawer.classList.add('open');document.body.classList.add('nav-open');drawer.setAttribute('aria-hidden','false');var t=document.getElementById('navToggle');t&&t.setAttribute('aria-expanded','true');}
  function dClose(){if(!drawer)return;drawer.classList.remove('open');document.body.classList.remove('nav-open');drawer.setAttribute('aria-hidden','true');var t=document.getElementById('navToggle');t&&t.setAttribute('aria-expanded','false');}
  ['navToggle','navToggle2'].forEach(function(id){var b=document.getElementById(id);if(b)b.addEventListener('click',dOpen);});
  var dcl=document.getElementById('drawerClose');if(dcl)dcl.addEventListener('click',dClose);
  if(drawer){drawer.querySelectorAll('a').forEach(function(a){a.addEventListener('click',dClose);});}
  document.addEventListener('keydown',function(e){if(e.key==='Escape')dClose();});
});

/* 강화 레이어(선택): GSAP 스크롤·패럴럭스·마그네틱·핀 갤러리. 실패해도 head 스크립트가 콘텐츠·리빌 보장 */
(function(){
  try{
    if(!(window.gsap&&window.ScrollTrigger)) return;
    gsap.registerPlugin(ScrollTrigger);
    /* 히어로 이미지 미세 패럴럭스 (홈 외 페이지엔 .hero가 없으므로 가드) */
    if(document.querySelector('.hero')){
      gsap.to('.hero-mosaic',{yPercent:-3.5,ease:'none',scrollTrigger:{trigger:'.hero',start:'top top',end:'bottom top',scrub:1}});
    }
    /* 마그네틱 버튼 */
    document.querySelectorAll('.btn,.btn-ghost').forEach(function(b){
      b.addEventListener('mousemove',function(e){var r=b.getBoundingClientRect();gsap.to(b,{x:(e.clientX-r.left-r.width/2)*0.12,y:(e.clientY-r.top-r.height/2)*0.16,duration:0.5,ease:'power2.out'})});
      b.addEventListener('mouseleave',function(){gsap.to(b,{x:0,y:0,duration:0.5,ease:'power2.out'})});
    });
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
