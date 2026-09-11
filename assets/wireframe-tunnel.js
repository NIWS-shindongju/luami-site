/* 와이어프레임 필름릴 터널 — 홈페이지 전용, 3D 장식 레이어.
   실패해도 무조건 안전: THREE 미로드/canvas 없음/에러 발생 어떤 경우든 즉시 return,
   기존 필름릴(가로 스크럽 컨택트시트)은 이 스크립트 없이도 완전히 정상 동작한다.
   독립 IIFE + 자체 try/catch로 격리 — 다른 인핸스먼트 레이어에 영향 없음. */
(function(){
  try{
    if(typeof THREE==='undefined') return;
    if(!(window.gsap&&window.ScrollTrigger)) return;
    var canvas=document.getElementById('wfTunnel');
    var sec=document.querySelector('.filmreel-sec');
    if(!canvas||!sec) return;
    if(matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    var isMobile=matchMedia('(max-width:640px)').matches;
    var ringCount=isMobile?6:12;

    var renderer=new THREE.WebGLRenderer({canvas:canvas, alpha:true, antialias:true});
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio||1));

    var scene=new THREE.Scene();
    var camera=new THREE.PerspectiveCamera(60, 1, 0.1, 100);
    camera.position.z=0;

    var accentHex=0x8fbc9e;
    try{
      var accentVal=getComputedStyle(document.documentElement).getPropertyValue('--accent-l').trim();
      if(accentVal) accentHex=new THREE.Color(accentVal).getHex();
    }catch(e){}

    var rings=[];
    for(var i=0;i<ringCount;i++){
      var torus=new THREE.TorusGeometry(3.2, 0.02, 6, 40);
      var edges=new THREE.EdgesGeometry(torus, 20);
      var mat=new THREE.LineBasicMaterial({color:accentHex, transparent:true, opacity:0.35});
      var ring=new THREE.LineSegments(edges, mat);
      ring.position.z=-i*4;
      scene.add(ring);
      rings.push(ring);
    }

    function size(){
      var r=canvas.getBoundingClientRect();
      var w=Math.max(1,r.width), h=Math.max(1,r.height);
      renderer.setSize(w,h,false);
      camera.aspect=w/h;
      camera.updateProjectionMatrix();
    }
    size();

    var running=false, rafId=null;
    function frame(){
      rings.forEach(function(r,i){ r.rotation.z += 0.0015*(i%2?1:-1); });
      renderer.render(scene, camera);
      if(running) rafId=requestAnimationFrame(frame);
    }
    function start(){ if(running) return; running=true; rafId=requestAnimationFrame(frame); }
    function stop(){ running=false; if(rafId) cancelAnimationFrame(rafId); rafId=null; }

    if('IntersectionObserver' in window){
      new IntersectionObserver(function(es){
        es.forEach(function(e){ (e.isIntersecting && !document.hidden) ? start() : stop(); });
      },{threshold:0}).observe(sec);
    } else { start(); }
    document.addEventListener('visibilitychange',function(){ document.hidden?stop():start(); });

    var totalDepth=ringCount*4;
    ScrollTrigger.create({
      trigger:sec, start:'top top',
      end:function(){ var frTrack=document.getElementById('frTrack'); return '+=' + Math.max(0, frTrack ? frTrack.scrollWidth - window.innerWidth + 80 : window.innerHeight); },
      scrub:true,
      onUpdate:function(self){ camera.position.z = self.progress * totalDepth; }
    });

    window.addEventListener('resize', size);
  }catch(e){}
})();
