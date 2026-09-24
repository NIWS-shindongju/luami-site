#!/usr/bin/env python3
"""모든 페이지의 머리(메뉴)·서랍 메뉴·푸터를 한 벌로 통일하고 장식 요소를 걷어낸다.

- 메뉴 5개 고정: 서비스 · 제품군 · 설치 사례 · 렌탈 가이드 · 블로그 (+ 렌탈 문의 버튼)
- 현재 페이지 메뉴에 aria-current="page"
- 장식 제거: 스프로킷 띠(.sprocket), 이미지 띠(.strip-sec), 푸터 대형 워드마크(.bigmark)
재실행해도 결과가 같다(멱등). 사용: python3 tools/unify_chrome.py
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
MENU = [
    ("services.html", "서비스"),
    ("products.html", "제품군"),
    ("portfolio.html", "설치 사례"),
    ("guide.html", "렌탈 가이드"),
    ("blog.html", "블로그"),
]
USES = [
    ("wedding-photobooth-rental.html", "웨딩"),
    ("corporate-event-photobooth.html", "기업행사"),
    ("popup-store-photobooth.html", "팝업스토어"),
    ("store-photobooth-rental.html", "매장 상설"),
    ("festival-outdoor-photobooth.html", "축제·야외"),
    ("university-graduation-photobooth.html", "졸업식"),
    ("brand-wrap-photobooth.html", "브랜드 래핑"),
    ("theme-photobooth.html", "테마 부스"),
    ("character-collab-photobooth.html", "캐릭터 콜라보"),
    ("photo-kiosk-rental.html", "포토키오스크"),
]
SECTION_OF = {"blog": "blog.html", "cases": "portfolio.html"}


def chrome(prefix, current):
    def link(href, label, extra=""):
        cur = ' aria-current="page"' if href == current else ""
        return f'<a href="{prefix}{href}"{cur}{extra}>{label}</a>'

    top = "".join(link(h, l) for h, l in MENU)
    drawer = "\n".join("    " + link(h, l) for h, l in MENU)
    header = f'''<header class="nav"><div class="wrap nav-in">
  <a href="{prefix}index.html" class="logo">Luami<span class="dot"></span></a>
  <nav class="nav-links">{top}</nav>
  <a href="{prefix}index.html#contact" class="nav-cta">렌탈 문의</a>
  <button class="navtoggle" id="navToggle" aria-label="메뉴 열기" aria-expanded="false" aria-controls="drawer"><span></span><span></span><span></span></button>
</div></header>'''
    drawer_html = f'''<div class="drawer-scrim" id="drawerScrim" aria-hidden="true"></div>
<div class="drawer" id="drawer" aria-hidden="true" role="dialog" aria-modal="true" aria-label="메뉴">
  <div class="drawer-grab" aria-hidden="true"></div>
  <div class="drawer-top">
    <a href="{prefix}index.html" class="logo dlogo">Luami<span class="dot"></span></a>
    <button class="drawer-close" id="drawerClose" aria-label="메뉴 닫기">✕</button>
  </div>
  <nav class="drawer-links">
{drawer}
  </nav>
  <div class="drawer-foot">
    <a href="{prefix}index.html#contact" class="btn drawer-cta">무료 견적 문의</a>
    <div class="drawer-contact">
      <a href="tel:01036297743">010-3629-7743</a>
      <a href="mailto:luami@luamiphoto.com">luami@luamiphoto.com</a>
      <a href="https://pf.kakao.com/_YRxoPX/chat" target="_blank" rel="noopener">카카오톡 채널 상담</a>
    </div>
  </div>
</div>

'''
    quick = " · ".join(f'<a href="{prefix}{h}">{l}</a>' for h, l in MENU)
    uses = "".join(f'<a href="{prefix}{h}">{l}</a>' for h, l in USES)
    footer = f'''<footer><div class="wrap">
  <div class="foot-grid">
    <div class="col"><b>루아미 (Luami)</b>무인 포토부스 렌탈 · 설치 · 운영<br>전국 상담 가능</div>
    <address class="col"><b>문의</b><a href="tel:01036297743">전화 010-3629-7743</a><br><a href="mailto:luami@luamiphoto.com">이메일 luami@luamiphoto.com</a><br>카카오톡 채널 <a href="https://pf.kakao.com/_YRxoPX" target="_blank" rel="noopener">@루아미</a><br><a href="https://instagram.com/luami_photo" target="_blank" rel="noopener">인스타그램</a> · <a href="https://youtube.com/@luami_photo" target="_blank" rel="noopener">유튜브</a> · <a href="https://blog.naver.com/luami_photo" target="_blank" rel="noopener">네이버 블로그</a> @luami_photo</address>
    <div class="col"><b>바로가기</b>{quick}<br><a href="{prefix}index.html#faq">자주 묻는 질문</a></div>
    <div class="col col-uses"><b>용도별 렌탈</b>{uses}</div>
  </div>
  <p class="note">© 2026 루아미(LUAMI). All rights reserved. · 무인 포토부스 렌탈 · 설치 · 운영</p>
</div></footer>'''
    return header, drawer_html, footer


def process(path):
    rel = path.relative_to(ROOT)
    depth = len(rel.parts) - 1
    prefix = "../" * depth
    current = SECTION_OF.get(rel.parts[0], rel.name) if depth else rel.name
    src = path.read_text(encoding="utf-8")
    if '<header class="nav"' not in src:
        return False
    header, drawer, footer = chrome(prefix, current)
    out = re.sub(r'<header class="nav".*?</header>', header, src, count=1, flags=re.S)
    out = re.sub(r'<div class="drawer-scrim".*?(?=<div class="stickybar")', drawer, out, count=1, flags=re.S)
    out = re.sub(r'<footer>.*?</footer>', footer, out, count=1, flags=re.S)
    out = re.sub(r'\n?<div class="sprocket[^"]*"></div>', "", out)
    out = re.sub(r'\n?<div class="strip-sec"><div class="strip">.*?</div></div>\n', "\n", out, flags=re.S)
    if 'class="skip-link"' not in out:
        out = re.sub(r'(<body[^>]*>)', r'\1\n<a class="skip-link" href="#main">본문 바로가기</a>', out, count=1)
    if '<main' not in out and '<div class="stickybar"' in out:
        out = re.sub(r'(<div class="stickybar"[^>]*>.*?</div>\n)', r'\1<main id="main">\n', out, count=1, flags=re.S)
        out = out.replace('<footer>', '</main>\n<footer>', 1)
    out = out.replace('<main id="main">', '<main id="main" tabindex="-1">')
    out = out.replace('<div class="util">', '<div class="util" aria-hidden="true">')
    out = out.replace('<div class="stickybar" id="sbar">', '<div class="stickybar" id="sbar" role="navigation" aria-label="빠른 메뉴">')
    if out != src:
        path.write_text(out, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    pages = sorted(ROOT.glob("*.html")) + sorted(ROOT.glob("blog/*.html")) + sorted(ROOT.glob("cases/*.html"))
    changed = [str(p.relative_to(ROOT)) for p in pages if process(p)]
    print(f"{len(changed)}/{len(pages)} 페이지 갱신")
