#!/usr/bin/env python3
"""반응형 이미지 변형 생성 + <img>에 srcset/sizes 부여 (재사용 도구, 멱등).

  python3 tools/img_variants.py make     assets/images/*.webp 중 폭 > 600px 원본마다 -480w·-960w 변형 생성(webp q80)
  python3 tools/img_variants.py html     모든 HTML의 <img src=assets/images/X.webp>에 srcset·sizes 추가
  python3 tools/img_variants.py check    변형 누락·srcset 대상 파일 존재 검사(누락 시 종료코드 1)

변형 파일명: X-480w.webp, X-960w.webp  (원본 X.webp는 그대로 두고 src로 유지 → 구형 브라우저 폴백)
원본보다 넓은 변형은 만들지 않는다. 변형끼리는 다시 변형하지 않는다.
"""
import pathlib, re, sys
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent
IMG = ROOT / 'assets' / 'images'
WIDTHS = (480, 960)
VAR_RE = re.compile(r'-(\d+)w\.webp$')


def originals():
    return sorted(p for p in IMG.glob('*.webp') if not VAR_RE.search(p.name))


def variants_for(p):
    w = Image.open(p).width
    return w, [(n, p.with_name(f'{p.stem}-{n}w.webp')) for n in WIDTHS if n < w * 0.85]


def make():
    made = 0
    for p in originals():
        w, vs = variants_for(p)
        for n, out in vs:
            if out.exists() and out.stat().st_mtime >= p.stat().st_mtime:
                continue
            im = Image.open(p)
            im = im.convert('RGBA' if im.mode in ('RGBA', 'LA', 'P') else 'RGB')
            h = round(im.height * n / im.width)
            im.resize((n, h), Image.LANCZOS).save(out, 'WEBP', quality=80, method=6)
            made += 1
    print(f'변형 {made}개 생성')


IMG_TAG = re.compile(r'<img\b[^>]*>', re.I)


def add_srcset(tag, prefix):
    if 'srcset=' in tag:
        return tag
    m = re.search(r'\bsrc="([^"]+)"', tag)
    if not m:
        return tag
    src = m.group(1)
    rel = src[len(prefix):] if src.startswith(prefix) else src
    if not rel.startswith('assets/images/') or not rel.endswith('.webp') or VAR_RE.search(rel):
        return tag
    p = ROOT / rel
    if not p.exists():
        return tag
    w, vs = variants_for(p)
    vs = [(n, v) for n, v in vs if v.exists()]
    if not vs:
        return tag
    base = src[: -len('.webp')]
    srcset = ', '.join(f'{base}-{n}w.webp {n}w' for n, _ in vs) + f', {src} {w}w'
    hero = 'fetchpriority="high"' in tag or 'loading="eager"' in tag
    sizes = '100vw' if hero else '(max-width: 720px) 90vw, 440px'
    return tag[:-1].rstrip('/').rstrip() + f' srcset="{srcset}" sizes="{sizes}">'


def html():
    pages = list(ROOT.glob('*.html')) + list(ROOT.glob('blog/*.html')) + list(ROOT.glob('cases/*.html'))
    changed = 0
    for f in pages:
        prefix = '../' if f.parent != ROOT else ''
        s = f.read_text(encoding='utf-8')
        out = IMG_TAG.sub(lambda m: add_srcset(m.group(0), prefix), s)
        if out != s:
            f.write_text(out, encoding='utf-8'); changed += 1
    print(f'{changed}/{len(pages)} 페이지 srcset 추가')


def check():
    bad = []
    for f in list(ROOT.glob('*.html')) + list(ROOT.glob('blog/*.html')) + list(ROOT.glob('cases/*.html')):
        for ss in re.findall(r'srcset="([^"]+)"', f.read_text(encoding='utf-8')):
            for part in ss.split(','):
                u = part.strip().split(' ')[0]
                if u.startswith(('http', '//')):
                    continue
                if not (f.parent / u).resolve().exists():
                    bad.append(f'{f.relative_to(ROOT)}: {u}')
    for b in bad:
        print('누락', b)
    print('check', 'FAIL' if bad else 'PASS', len(bad))
    return 1 if bad else 0


if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'check'
    sys.exit({'make': make, 'html': html, 'check': check}[cmd]() or 0)
