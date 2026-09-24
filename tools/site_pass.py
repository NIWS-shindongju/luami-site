#!/usr/bin/env python3
"""사이트 전역 머리·스크립트 정리 (재사용 도구, 멱등).

  python3 tools/site_pass.py            적용
  python3 tools/site_pass.py --check    변경 필요 여부만 보고(필요하면 종료코드 1)

하는 일
 1) CSS·JS 캐시 버스터를 한 버전으로 통일 (VERSION)
 2) Pretendard 전체 폰트(2MB) → dynamic-subset(필요한 글자 조각만)
 3) GSAP·ScrollTrigger·Lenis는 index.html에만 — 다른 페이지에선 제거(main.js가 없을 때를 가드함)
 4) h2의 인라인 font-size 제거 → CSS 토큰(--h2)으로 통일
 6) Pretendard CDN → 자체 호스팅 서브셋(assets/fonts/luami-sans.woff2, tools/font_subset.py)
    — dynamic-subset(조각 20~40개)도 전체(2MB)도 느린 회선에서 불리함을 A/B로 실측.
      preload는 넣지 않는다: 447KB를 CSS와 동시에 받아 FCP가 0.3~0.5초 늦어짐(A/B 실측) — swap으로 충분
 5) 웹폰트 CSS(Pretendard·Noto Serif KR)를 렌더 차단 없이 로드(media=print→all 스왑 + noscript 폴백)
    — dynamic-subset CSS가 렌더를 막아 FCP가 ~1초 늦어진 것을 실측(검증 에이전트 A/B)해서 도입
"""
import pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERSION = '20260925s'
HEAVY = re.compile(r'\n?<script src="https://(?:unpkg\.com/lenis[^"]*|cdn\.jsdelivr\.net/npm/gsap[^"]*)"[^>]*></script>')
PRETENDARD_FULL = 'pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css'
PRETENDARD_SUB = 'pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css'
H2_STYLE = re.compile(r'(<h2\b[^>]*?)\sstyle="([^"]*)"')


def strip_h2_size(m):
    rules = [r for r in m.group(2).split(';') if r.strip() and not r.strip().startswith('font-size')]
    style = ';'.join(r.strip() for r in rules)
    return m.group(1) + (f' style="{style}"' if style else '')


def fix_h2(tag_html):
    return H2_STYLE.sub(strip_h2_size, tag_html)


FONT_LINKS = [
    re.compile(r'(?<!<noscript>)<link href="(https://fonts\.googleapis\.com/css2\?[^"]+)" rel="stylesheet">'),
    re.compile(r'(?<!<noscript>)<link rel="stylesheet" href="(https://cdn\.jsdelivr\.net/gh/orioncactus/pretendard[^"]+)">'),
]


def async_font(m):
    u = m.group(1)
    return (f'<link rel="stylesheet" href="{u}" media="print" onload="this.media=\'all\'">'
            f'<noscript><link rel="stylesheet" href="{u}"></noscript>')


def process(p):
    s = p.read_text(encoding='utf-8')
    o = re.sub(r'(assets/(?:style|home)\.css|assets/main\.js)\?v=[\w]+', r'\1?v=' + VERSION, s)
    o = o.replace(PRETENDARD_FULL, PRETENDARD_SUB)
    # 6) Pretendard CDN 링크 제거 → 자체 서브셋 preload (style.css의 @font-face가 사용)
    o = re.sub(r'<link rel="stylesheet" href="https://cdn\.jsdelivr\.net/gh/orioncactus/pretendard[^"]+"[^>]*>(?:<noscript><link rel="stylesheet" href="https://cdn\.jsdelivr\.net/gh/orioncactus/pretendard[^"]+"></noscript>)?\n?', '', o)
    o = o.replace('<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>\n', '')
    o = re.sub(r'<link rel="preload" href="(?:\.\./)?assets/fonts/luami-sans\.woff2"[^>]*>\n?', '', o)
    for rx in FONT_LINKS:
        o = rx.sub(async_font, o)
    if 'preconnect" href="https://cdn.jsdelivr.net"' not in o and 'cdn.jsdelivr.net/gh/orioncactus' in o:
        o = o.replace('<link rel="preconnect" href="https://fonts.googleapis.com">',
                      '<link rel="preconnect" href="https://cdn.jsdelivr.net" crossorigin>\n<link rel="preconnect" href="https://fonts.googleapis.com">', 1)
    if p.name != 'index.html' or p.parent != ROOT:
        o = HEAVY.sub('', o)
    o = re.sub(r'<h2\b[^>]*>', lambda m: fix_h2(m.group(0)), o)
    return s, o


def main():
    check = '--check' in sys.argv
    pages = sorted(ROOT.glob('*.html')) + sorted(ROOT.glob('blog/*.html')) + sorted(ROOT.glob('cases/*.html'))
    changed = []
    for p in pages:
        s, o = process(p)
        if o != s:
            changed.append(str(p.relative_to(ROOT)))
            if not check:
                p.write_text(o, encoding='utf-8')
    print(('변경 필요 ' if check else '갱신 ') + f'{len(changed)}/{len(pages)}')
    return 1 if (check and changed) else 0


if __name__ == '__main__':
    sys.exit(main())
