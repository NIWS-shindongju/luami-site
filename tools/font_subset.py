#!/usr/bin/env python3
"""Pretendard 가변 폰트를 사이트 전용 1파일 서브셋으로 만든다 (재사용 도구).

  python3 tools/font_subset.py <PretendardVariable.woff2 원본 경로>
     → assets/fonts/luami-sans.woff2 (내부 글꼴명 LuamiSans) + assets/fonts/OFL.txt
  python3 tools/font_subset.py --check     사이트 HTML의 모든 글자가 서브셋에 있는지 검사(누락 시 종료코드 1)

글자 범위 = 사이트 70여 페이지에 실제로 쓰인 모든 글자
          ∪ KS X 1001 완성형 한글 2,350자(앞으로 쓸 문구 대비)
          ∪ 기본 라틴·숫자·문장부호·자주 쓰는 기호.
왜: CDN dynamic-subset은 페이지마다 조각 파일 20~40개를 따로 받아 느린 회선에서 첫 화면이 ~1초 늦었고
    (실측 A/B), 전체 가변폰트는 2MB라 무겁다. 같은 도메인 1파일 + preload가 둘의 장점을 합친다.
Pretendard 는 SIL OFL 1.1 — 서브셋·자체 호스팅 허용(이름 변경 파일, 라이선스 동봉).
"""
import pathlib, re, sys, html as H

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / 'assets' / 'fonts' / 'luami-sans.woff2'
FAMILY = 'LuamiSans'  # OFL 예약 글꼴명(Pretendard) 회피 — 서브셋은 수정본이라 다른 이름 필수
EXTRA = ''.join(chr(c) for c in range(0x20, 0x7F)) + '·—–‘’“”…→←↑↓↗×※○●◆■□★☆♥️~%‰℃①②③④⑤⑥⑦⑧⑨⑩《》〈〉「」『』【】ㆍ'


def ksx1001_hangul():
    out = []
    for hi in range(0xB0, 0xC9):
        for lo in range(0xA1, 0xFF):
            try:
                out.append(bytes([hi, lo]).decode('euc-kr'))
            except UnicodeDecodeError:
                pass
    return ''.join(out)


def site_chars():
    chars = set()
    pages = list(ROOT.glob('*.html')) + list(ROOT.glob('blog/*.html')) + list(ROOT.glob('cases/*.html'))
    for f in pages:
        t = f.read_text(encoding='utf-8')
        t = re.sub(r'<script[\s\S]*?</script>|<style[\s\S]*?</style>', ' ', t)
        chars |= set(H.unescape(re.sub(r'<[^>]+>', ' ', t)))
        chars |= set(H.unescape(' '.join(re.findall(r'(?:alt|title|aria-label|placeholder|content)="([^"]*)"', t))))
    for f in (ROOT / 'assets').glob('*.js'):  # JS가 넣는 문구(티커 등)
        chars |= set(re.findall(r'[가-힣]', f.read_text(encoding='utf-8')))
    return {c for c in chars if c.isprintable() and not c.isspace()}


def rename(font):
    name = font['name']
    for rec in list(name.names):
        if rec.nameID in (1, 3, 4, 6, 16, 21, 25):
            old = rec.toUnicode()
            new = FAMILY + ('-' + old.split('-', 1)[1] if rec.nameID in (3, 6) and '-' in old else '')
            if rec.nameID == 25:
                new = FAMILY + 'Variable'
            elif rec.nameID == 4:
                new = FAMILY + old[len('Pretendard'):] if old.startswith('Pretendard') else FAMILY
            name.setName(new.replace(' ', '') if rec.nameID == 6 else new, rec.nameID, rec.platformID, rec.platEncID, rec.langID)
    if 'fvar' in font:  # 인스턴스 이름의 PostScript 접두어도 교체
        for inst in font['fvar'].instances:
            if inst.postscriptNameID not in (0xFFFF, None):
                old = name.getDebugName(inst.postscriptNameID) or ''
                if old.startswith('Pretendard'):
                    for rec in name.names:
                        if rec.nameID == inst.postscriptNameID:
                            name.setName(FAMILY + old[len('Pretendard'):], rec.nameID, rec.platformID, rec.platEncID, rec.langID)


def build(src):
    from fontTools import subset
    text = ''.join(sorted(site_chars() | set(ksx1001_hangul()) | set(EXTRA)))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    opts = subset.Options()
    opts.flavor = 'woff2'
    opts.layout_features = ['*']
    opts.name_IDs = ['*']
    opts.notdef_outline = True
    font = subset.load_font(src, opts)
    s = subset.Subsetter(opts)
    s.populate(text=text)
    s.subset(font)
    rename(font)
    subset.save_font(font, str(OUT), opts)
    print(f'{len(text)}자 → {OUT.relative_to(ROOT)} {OUT.stat().st_size/1024:.0f}KB')


def check():
    from fontTools.ttLib import TTFont
    cmap = TTFont(str(OUT)).getBestCmap()
    missing = sorted(c for c in site_chars() if ord(c) not in cmap and ord(c) > 0x20)
    print('누락', len(missing), ''.join(missing[:80]))
    ALLOW = set('✕')  # 원본 Pretendard에 없는 기호 — 시스템 글꼴 대체 확인(서랍 닫기 버튼)
    bad = [c for c in missing if c not in ALLOW]
    print('허용 예외', ''.join(c for c in missing if c in ALLOW), '/ 실패', ''.join(bad))
    return 1 if bad else 0


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--check':
        sys.exit(check())
    build(sys.argv[1])
