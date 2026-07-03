/* Luami shared JS */
document.addEventListener('DOMContentLoaded', function(){
  requestAnimationFrame(function(){
    document.querySelectorAll('.hero h1,.hero .sub').forEach(function(e){e.classList.add('in')});
  });
  try{
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target)}})},{threshold:0.12,rootMargin:'0px 0px -6% 0px'});
    document.querySelectorAll('.fade,.lm,.manifesto h2').forEach(function(el){io.observe(el)});
  }catch(e){document.querySelectorAll('.fade,.lm').forEach(function(e){e.classList.add('in')})}
  /* 실패세이프: 무슨 일이 있어도 2.6초 뒤 전부 노출 */
  setTimeout(function(){document.querySelectorAll('.fade,.lm,.hero h1,.hero .sub,.manifesto h2').forEach(function(e){e.classList.add('in')})},2600);
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
    /* 히어로 이미지 미세 패럴럭스 */
    gsap.to('.hero-figure',{yPercent:-3.5,ease:'none',scrollTrigger:{trigger:'.hero',start:'top top',end:'bottom top',scrub:1}});
    /* 마그네틱 버튼 */
    document.querySelectorAll('.btn,.btn-ghost').forEach(function(b){
      b.addEventListener('mousemove',function(e){var r=b.getBoundingClientRect();gsap.to(b,{x:(e.clientX-r.left-r.width/2)*0.12,y:(e.clientY-r.top-r.height/2)*0.16,duration:0.5,ease:'power2.out'})});
      b.addEventListener('mouseleave',function(){gsap.to(b,{x:0,y:0,duration:0.5,ease:'power2.out'})});
    });
    var hg=document.querySelector('.hgallery'),gtrack=document.querySelector('.hgallery-track');
    if(hg&&gtrack&&matchMedia('(min-width:881px)').matches){
      hg.classList.add('pinned');
      var gdist=function(){return Math.max(0,gtrack.scrollWidth-window.innerWidth+56);};
      gsap.to(gtrack,{x:function(){return -gdist();},ease:'none',
        scrollTrigger:{trigger:hg,start:'top top',end:function(){return '+='+gdist();},pin:true,scrub:1,anticipatePin:1,invalidateOnRefresh:true}});
    }
    window.addEventListener('load',function(){ScrollTrigger.refresh();});
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
