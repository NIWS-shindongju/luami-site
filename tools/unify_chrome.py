#!/usr/bin/env python3
"""모든 페이지의 머리(메뉴)·서랍 메뉴·푸터를 한 벌로 통일하고 장식 요소를 걷어낸다.

- 메뉴 5개 고정(2026-10-04~): 제품 · 가격 · 사례 · 블로그 · 문의(버튼)
- 머리 오른쪽(2026-10-04 r4, BRIEF 2-1 #2): 전화번호 글자 · 카톡 상담(공식 노랑) · 무료 견적 받기(채움 버튼).
  880px 이하에선 숨기고 하단 바(.mcta: 카톡·전화·무료 견적)가 대신한다.
  렌탈 가이드는 상단 메뉴에서 빠지고 푸터 바로가기에 남는다(사이트 전역 내부 링크 유지).
- 현재 페이지 메뉴에 aria-current="page"
- 맨 위 띠(.util)의 '상담 010-…' 은 tel: 링크(UTIL)
- 푸터 최하단 사업자 정보 한 줄(BIZ) — 메뉴 없는 단독 페이지(404·thanks)엔 얇은 푸터로
- 장식 제거: 스프로킷 띠(.sprocket), 이미지 띠(.strip-sec), 푸터 대형 워드마크(.bigmark)
재실행해도 결과가 같다(멱등). 사용: python3 tools/unify_chrome.py
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
MENU = [
    ("products.html", "제품"),
    ("pricing.html", "가격"),
    ("portfolio.html", "사례"),
    ("blog.html", "블로그"),
]
CONTACT = ("index.html#contact", "무료 견적")
TEL = ("tel:01036297743", "010-3629-7743")
KAKAO = "https://pf.kakao.com/_YRxoPX/chat"
# 푸터 바로가기 — 메뉴 + 렌탈 가이드(상단 메뉴에서 빠진 순위 페이지로 가는 전역 링크)
QUICK = MENU + [("guide.html", "렌탈 가이드"), CONTACT]
SECTION_OF = {"blog": "blog.html", "cases": "portfolio.html", "products": "products.html"}
# 사업자 정보 — 모든 페이지 최하단 한 줄. 통신판매업 신고번호는 없으므로 넣지 않는다.
BIZ = ('<p class="biz">주식회사 니우스 · 대표 신동주 · 사업자등록번호 805-81-04322 · '
       '인천광역시 서해구 청라한울로 17 · '
       '문의 <a href="mailto:luami@luamiphoto.com">luami@luamiphoto.com</a></p>')
MINI_FOOTER = f'<footer class="foot-min"><div class="wrap">\n  {BIZ}\n</div></footer>'
# 맨 위 띠 — 전화번호는 눌러서 바로 걸 수 있게(모바일 탭 높이 44px 는 style.css .util a)
UTIL = (f'<div class="util"><div class="wrap"><span>포토부스 렌탈 · 전국 설치</span>'
        f'<a href="{TEL[0]}" aria-label="전화 상담 {TEL[1]}">상담 {TEL[1]}</a></div></div>')


def chrome(prefix, current):
    def link(href, label, extra=""):
        cur = ' aria-current="page"' if href == current else ""
        return f'<a href="{prefix}{href}"{cur}{extra}>{label}</a>'

    top = "".join(link(h, l) for h, l in MENU)
    # 서랍 메뉴 = 메뉴 4개(견적은 아래 '무료 견적 받기' 버튼 하나 — 같은 목적지 두 번 금지, D18 F15)
    drawer = "\n".join("    " + link(h, l) for h, l in MENU)
    header = f'''<header class="nav"><div class="wrap nav-in">
  <a href="{prefix}index.html" class="logo">Luami<span class="dot"></span></a>
  <nav class="nav-links">{top}</nav>
  <div class="nav-act">
    <a href="{TEL[0]}" class="hdr-tel" aria-label="전화 상담 {TEL[1]}"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/></svg>{TEL[1]}</a>
    <a href="{KAKAO}" class="hdr-kakao kakao" target="_blank" rel="noopener">카톡 상담</a>
    <a href="{prefix}{CONTACT[0]}" class="nav-cta">{CONTACT[1]} 받기</a>
  </div>
  <button class="navtoggle" id="navToggle" aria-label="메뉴 열기" aria-expanded="false" aria-controls="drawer"><span></span><span></span><span></span></button>
</div></header>'''
    drawer_html = f'''<div class="drawer-scrim" id="drawerScrim" aria-hidden="true"></div>
<div class="drawer" id="drawer" aria-hidden="true">
  <div class="drawer-grab" aria-hidden="true"></div>
  <div class="drawer-top">
    <a href="{prefix}index.html" class="logo dlogo">Luami<span class="dot"></span></a>
    <button class="drawer-close" id="drawerClose" aria-label="메뉴 닫기">✕</button>
  </div>
  <nav class="drawer-links">
{drawer}
  </nav>
  <div class="drawer-foot">
    <a href="{prefix}index.html#contact" class="btn drawer-cta">무료 견적 받기</a>
    <div class="drawer-contact">
      <a href="tel:01036297743">010-3629-7743</a>
      <a href="mailto:luami@luamiphoto.com">luami@luamiphoto.com</a>
      <a href="https://pf.kakao.com/_YRxoPX/chat" target="_blank" rel="noopener">카톡으로 바로 상담</a>
    </div>
  </div>
</div>

'''
    quick = " · ".join(f'<a href="{prefix}{h}">{l}</a>' for h, l in QUICK)
    footer = f'''<footer><div class="wrap">
  <div class="foot-grid">
    <div class="col"><b>루아미 (Luami)</b>무인 포토부스 렌탈 · 설치 · 운영<br>전국 상담 가능</div>
    <address class="col"><b>문의</b><a href="tel:01036297743">전화 010-3629-7743</a><br><a href="mailto:luami@luamiphoto.com">이메일 luami@luamiphoto.com</a><br>카카오톡 채널 <a href="https://pf.kakao.com/_YRxoPX" target="_blank" rel="noopener">@루아미</a><br><a href="https://instagram.com/luami_photo" target="_blank" rel="noopener">인스타그램</a> · <a href="https://www.youtube.com/@luamiphoto" target="_blank" rel="noopener">유튜브</a> · <a href="https://blog.naver.com/luami_photo" target="_blank" rel="noopener">네이버 블로그</a> @luami_photo</address>
    <div class="col"><b>바로가기</b>{quick}<br><a href="{prefix}index.html#faq">자주 묻는 질문</a></div>
  </div>
  {BIZ}
  <p class="note">© 2026 루아미(LUAMI). All rights reserved. · 무인 포토부스 렌탈 · 설치 · 운영</p>
</div></footer>'''
    return header, drawer_html, footer


def transform(rel, src):
    """rel = ROOT 기준 상대경로(pathlib.PurePath). 크롬을 입힌 문자열을 돌려준다(쓰기는 안 함).
    tools/build_products.py 가 생성 페이지에 같은 크롬을 입힐 때 이 함수를 쓴다."""
    depth = len(rel.parts) - 1
    prefix = "../" * depth
    current = SECTION_OF.get(rel.parts[0], rel.name) if depth else rel.name
    if '<header class="nav"' not in src:
        # 404·thanks 처럼 메뉴가 없는 단독 페이지: 사업자 정보만 담은 얇은 푸터
        if "</body>" not in src:
            return src
        out = re.sub(r'<footer class="foot-min">.*?</footer>\n', "", src, flags=re.S)
        if "<footer>" in out:
            # unsubscribe 처럼 자체 스타일·자체 푸터를 가진 단독 페이지: 사업자 정보가 두 번 찍히지 않게 손대지 않는다
            return out
        return out.replace("</body>", MINI_FOOTER + "\n</body>", 1)
    header, drawer, footer = chrome(prefix, current)
    out = re.sub(r'<header class="nav".*?</header>', header, src, count=1, flags=re.S)
    out = re.sub(r'<div class="util"><div class="wrap">.*?</div></div>', lambda m: UTIL, out, count=1, flags=re.S)
    out = re.sub(r'<div class="drawer-scrim".*?(?=<div class="stickybar")', drawer, out, count=1, flags=re.S)
    out = re.sub(r'<footer>.*?</footer>', footer, out, count=1, flags=re.S)
    out = re.sub(r'\n?<div class="sprocket[^"]*"></div>', "", out)
    out = re.sub(r'\n?<div class="strip-sec"><div class="strip">.*?</div></div>\n', "\n", out, flags=re.S)
    return out


def process(path):
    rel = path.relative_to(ROOT)
    src = path.read_text(encoding="utf-8")
    out = transform(rel, src)
    if out != src:
        path.write_text(out, encoding="utf-8")
        return True
    return False


if __name__ == "__main__":
    pages = (sorted(ROOT.glob("*.html")) + sorted(ROOT.glob("blog/*.html")) + sorted(ROOT.glob("cases/*.html"))
             + sorted(ROOT.glob("products/*.html")))
    changed = [str(p.relative_to(ROOT)) for p in pages if process(p)]
    print(f"{len(changed)}/{len(pages)} 페이지 갱신")
