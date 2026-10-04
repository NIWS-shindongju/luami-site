#!/usr/bin/env python3
"""제품 허브·제품 상세·가격 페이지 생성기 (루아미, 2026-10-04 라인업)

입력(전부 data/):
  products.json      제품 정의(순서·이름·배지·하이앵글·표지 규칙·옛 앵커)
  prices.json        가격 단일 출처 + 부가세 표기 스위치(vat.mode)
  copy/<slug>.json   제품 카피 / copy/pricing.json 가격 페이지 카피
  gallery.json       제품별 사례 사진 / wrap.json 4면 랩핑 사진
  content_map.json   제품별 블로그·사례 페이지

출력(정적 HTML — GitHub Pages 가 그대로 서빙):
  products.html               제품 허브(주력 모델 · 8종 그리드 · 커스텀 · 신규 컨셉)
  products/<slug>.html        제품 상세 9장(8종 + 커스텀)
  pricing.html                렌탈·구매 가격
  services.html               스텁(noindex · canonical/refresh → pricing.html · 옛 앵커 JS 매핑)
  index.html · guide.html     <!-- GEN:이름 --> … <!-- /GEN:이름 --> 사이만 갈아 끼움
  cases/*.html                "이 현장에 쓰인 제품" 줄을 content_map 기준으로 갱신
  sitemap.xml                 새 페이지 추가 · services 제거 · 내용이 바뀐 생성 페이지만 lastmod 갱신

3D 표지: assets/images/covers/<slug>_<variant>.jpg 가 생기면 다음 빌드부터 자동으로 쓴다.
  python3 tools/build_products.py --covers-from <dir>   # <dir>/<slug>_<variant>.jpg 를 복사해 넣고 빌드
멱등: 입력이 같으면 출력이 같다(파일·sitemap 모두). 사용: python3 tools/build_products.py [--check]
  --check  파일을 쓰지 않고, 바뀔 파일 목록만 출력(바뀔 게 있으면 종료코드 1)
"""
import argparse
import datetime
import hashlib
import html
import json
import os
import pathlib
import re
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True  # tools/__pycache__ 가 공개 저장소에 남지 않게
sys.path.insert(0, str(ROOT / "tools"))
import unify_chrome  # noqa: E402

try:
    from PIL import Image  # 이미지 크기(width/height 속성) — 없으면 gallery.json 값으로 계산
except Exception:  # pragma: no cover
    Image = None

TODAY = os.environ.get("BUILD_DATE") or datetime.date.today().isoformat()
D = ROOT / "data"


def load(p):
    return json.loads((ROOT / p).read_text(encoding="utf-8"))


P = load("data/products.json")
PR = load("data/prices.json")
G = load("data/gallery.json")
CM = load("data/content_map.json")
WRAP = load("data/wrap.json")
PC = load("data/copy/pricing.json")
SITE = P["site"]
BASE = SITE["base_url"]
LINEUP = sorted(P["lineup"], key=lambda x: x["order"])
CUSTOM = P["custom"]
DETAIL = LINEUP + [CUSTOM]
CONCEPTS = P["concepts"]
COPY = {x["slug"]: load(f"data/copy/{x['slug']}.json") for x in DETAIL + CONCEPTS}
BYSLUG = {x["slug"]: x for x in DETAIL + CONCEPTS}
KAKAO = SITE["kakao"]
TEL = "tel:01036297743"

esc = lambda s: html.escape(str(s), quote=True)  # noqa: E731


# ───────────────────────── 가격 표기 ─────────────────────────
def vat_label():
    return PR["vat"]["labels"].get(PR["vat"]["mode"], "")


def man(n):
    return f"{n:,}만원"


def amt(key):
    it = PR["items"][key]
    return it.get("prefix", "") + (it["per"] + " " if it.get("per") else "") + man(it["amount"])


def vat_html():
    v = vat_label()
    return f' <small class="vat">{esc(v)}</small>' if v else ""


def amt_html(key, lead=""):
    lead = f"{esc(lead)} " if lead else ""
    return f'<span class="amt">{lead}{esc(amt(key))}</span>{vat_html()}'


def amt_text(key):
    v = vat_label()
    return amt(key) + (f"({v})" if v else "")


def man_text(n):
    v = vat_label()
    return man(n) + (f"({v})" if v else "")


def tmpl(s):
    """{price:key} → '185만원(부가세 별도)', '({vat})' → '(부가세 별도)' 또는 '' (표기 안 함 모드)."""
    s = re.sub(r"\{price:([a-z0-9_]+)\}", lambda m: amt_text(m.group(1)), s)
    v = vat_label()
    return s.replace("({vat})", f"({v})" if v else "")


def std_total(units, months):
    a, b, c = (PR["items"][k]["amount"] for k in PR["rules"]["std_total"])
    return a + b * (units - 1) + c * units * (months - 1)


def price_of(slug):
    """제품 가격 요약: [(라벨, html, text)] — 렌탈·구매 두 줄."""
    m = PR["products"].get(slug) or PR["products"]["_concept"]
    rows = []
    if m.get("rental_summary"):
        k = m["rental_summary"]
        rows.append(("렌탈", amt_html(k, m.get("rental_summary_prefix", "")),
                     f"{m.get('rental_summary_prefix', '')} {amt_text(k)}".strip()))
    else:
        rows.append(("렌탈", f'<span class="ask">{esc(m["rental_text"])}</span>', m["rental_text"]))
    if m.get("purchase"):
        rows.append(("구매", amt_html(m["purchase"]), amt_text(m["purchase"])))
    else:
        rows.append(("구매", f'<span class="ask">{esc(m["purchase_text"])}</span>', m["purchase_text"]))
    return rows


def has_fixed_price(slug):
    m = PR["products"].get(slug) or {}
    return bool(m.get("rental_summary") or m.get("purchase"))


# ───────────────────────── 이미지 ─────────────────────────
_dim_cache = {}


def dims(rel, hint=None):
    if rel in _dim_cache:
        return _dim_cache[rel]
    wh = None
    if Image is not None and (ROOT / rel).exists():
        try:
            with Image.open(ROOT / rel) as im:
                wh = im.size
        except Exception:
            wh = None
    if wh is None and hint:
        wh = hint
    _dim_cache[rel] = wh or (1200, 1500)
    return _dim_cache[rel]


def cover_path(slug, variant):
    c = SITE["covers"]
    rel = f"{c['dir']}/{c['pattern'].format(slug=slug, variant=variant)}"
    return rel if (ROOT / rel).exists() else None


def cover(prod, variant="4x5"):
    """{'src','kind','label','position','w','h','is_cover'} — 3D 표지가 있으면 그것, 없으면 fallback."""
    slug = prod["slug"]
    rel = cover_path(slug, variant)
    if rel:
        w, h = dims(rel)
        return {"src": rel, "kind": SITE["covers"]["kind"], "position": "50% 50%", "w": w, "h": h, "is_cover": True}
    fb = prod.get("fallback")
    if not fb:
        return None
    src = fb.get(variant) or fb.get("4x5")
    w, h = dims(src)
    return {"src": src, "kind": fb.get("kind", "photo"), "position": fb.get("position_" + variant) or fb.get("position", "50% 50%"),
            "w": w, "h": h, "is_cover": False}


def cover_alt(prod, img):
    if img is None:
        return prod["name"]
    if img.get("is_cover"):
        return f"{prod['name']} — CAD 3D 렌더"
    for it in G.get(prod["slug"], []):
        if img["src"] in (it["src"], it.get("thumb")):
            return it["alt"]
    return prod["name"]


def u(rel, depth):
    return "../" * depth + rel


def render_tag(img, large=False):
    """'CAD 3D 렌더' 표기 보장.
    - 3D 표지(covers/)는 이미지 안 표기 여부를 모르므로 화면 위에 표기를 얹는다.
    - 갤러리 렌더(data/gallery.json·wrap.json)는 우하단에 표기가 박혀 있지만 썸네일에선 글자가 작다 →
      contain 으로 통째로 보여 주고(img_tag, 박힌 표기가 잘리지 않게) 왼쪽에 읽히는 크기로 한 번 더 얹는다."""
    if not img or img.get("kind") != "render":
        return ""
    if large and not img.get("is_cover"):
        return ""  # 크게 보이는 자리(상세 표지·주력 카드·가격 그림)에선 이미지에 박힌 표기가 충분히 읽힌다
    return f'<span class="render-tag">{esc(SITE["covers"]["label"])}</span>'


_bg_cache = {}


def edge_color(rel):
    """렌더 배경색(위·아래 모서리 평균) — contain 여백을 이미지 가장자리와 같은 색(세로 그라데이션)으로 채운다."""
    if rel in _bg_cache:
        return _bg_cache[rel]
    col = "#d9d6cf"
    if Image is not None and (ROOT / rel).exists():
        try:
            with Image.open(ROOT / rel) as im:
                im = im.convert("RGB")
                w, h = im.size
                hexof = lambda px: "#%02x%02x%02x" % tuple(sum(c[i] for c in px) // len(px) for i in range(3))  # noqa: E731
                top = hexof([im.getpixel((4, 4)), im.getpixel((w - 5, 4))])
                bot = hexof([im.getpixel((4, h - 5)), im.getpixel((w // 2, h - 5))])
                col = top if top == bot else f"linear-gradient({top},{bot})"
        except Exception:
            pass
    _bg_cache[rel] = col
    return col


def img_tag(img, depth, alt, cls="", lazy=True, sizes=None, priority=False):
    attrs = [f'src="{u(img["src"], depth)}"', f'width="{img["w"]}"', f'height="{img["h"]}"', f'alt="{esc(alt)}"']
    if img["kind"] == "render" and not img.get("is_cover"):
        attrs.append(f'style="object-fit:contain;background:{edge_color(img["src"])}"')
    elif img.get("position") and img["position"] != "50% 50%":
        attrs.append(f'style="object-position:{img["position"]}"')
    if priority:
        attrs.append('fetchpriority="high"')
    elif lazy:
        attrs.append('loading="lazy"')
    attrs.append('decoding="async"')
    if cls:
        attrs.append(f'class="{cls}"')
    return "<img " + " ".join(attrs) + ">"


SCENE_RANK = {"install": 0, "event": 0, "detail": 1, "render": 2, "factory": 3}


def gallery(slug):
    hide = set(SITE.get("gallery_hide_scenes") or [])
    items = []
    for v in ("angle1", "angle2", "angle3"):
        rel = cover_path(slug, v)
        if rel:
            w, h = dims(rel)
            items.append({"src": rel, "thumb": rel, "w": w, "h": h, "kind": "render", "scene": "render", "is_cover": True,
                          "alt": f"{BYSLUG[slug]['name']} CAD 3D 렌더 — 다른 각도", "caption": "CAD 3D 렌더"})
    base = [x for x in G.get(slug, []) if x.get("scene") not in hide]
    base = sorted(enumerate(base), key=lambda t: (SCENE_RANK.get(t[1].get("scene"), 1), t[0]))
    items += [x for _, x in base]
    return items


def contain_style(it):
    if it.get("kind") == "render" and not it.get("is_cover"):
        return f' style="object-fit:contain;background:{edge_color(it.get("thumb") or it["src"])}"'
    return ""


def thumb_dims(it):
    w, h = it["w"], it["h"]
    s = min(1.0, 600 / max(w, h))
    return round(w * s), round(h * s)


# ───────────────────────── 콘텐츠(블로그·사례) ─────────────────────────
def page_meta(rel):
    f = ROOT / rel
    if not f.exists():
        return None
    s = f.read_text(encoding="utf-8")
    h1 = re.search(r"<h1[^>]*>(.*?)</h1>", s, re.S)
    title = re.sub(r"<[^>]+>", " ", h1.group(1)) if h1 else ""
    title = re.sub(r"\s+", " ", html.unescape(title)).strip()
    title = re.sub(r"\s+([.,!?·])", r"\1", title)
    if not title:
        t = re.search(r"<title>(.*?)</title>", s, re.S)
        title = html.unescape(t.group(1)).split("|")[0].strip() if t else rel
    d = re.search(r'<meta name="description" content="([^"]*)"', s)
    desc = html.unescape(d.group(1)) if d else ""
    return {"title": title, "desc": desc}


def stories(slug):
    m = CM.get(slug, {"blog": [], "cases": []})
    own = f"blog/{slug}-story.html"
    out = []
    for rel in m.get("cases", []):
        pm = page_meta(rel)
        if pm:
            out.append(dict(pm, href=rel, type="사례"))
    blogs = sorted(m.get("blog", []), key=lambda r: (r != own,))
    for rel in blogs:
        pm = page_meta(rel)
        if pm:
            out.append(dict(pm, href=rel, type="블로그"))
    # 같은 글이 두 번 들어가지 않게
    seen, uniq = set(), []
    for x in out:
        if x["href"] in seen:
            continue
        seen.add(x["href"])
        uniq.append(x)
    return uniq


def clip(s, n):
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


# ───────────────────────── 공통 페이지 골격 ─────────────────────────
def asset_ver(rel):
    return hashlib.md5((ROOT / rel).read_bytes()).hexdigest()[:8]


STYLE_V = "20261004a"


def ld(obj):
    return '<script type="application/ld+json">\n' + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n</script>"


def breadcrumb(items):
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": BASE + "/" + h}
                                for i, (n, h) in enumerate(items)]}


def faq_ld(faq):
    return {"@context": "https://schema.org", "@type": "FAQPage",
            "mainEntity": [{"@type": "Question", "name": q["q"],
                            "acceptedAnswer": {"@type": "Answer", "text": tmpl(q["a"])}} for q in faq]}


def head(title, desc, keywords, path, og_image, depth, lds, og_type="website", robots="index, follow", extra=""):
    pre = "../" * depth
    canon = BASE + "/" + path
    ogi = og_image if og_image.startswith("http") else BASE + "/" + og_image
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<meta name="description" content="{esc(desc)}">
<meta name="theme-color" content="#1F2417">
<meta name="keywords" content="{esc(keywords)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{canon}">
<meta property="og:type" content="{og_type}">
<meta property="og:site_name" content="루아미 (Luami)">
<meta property="og:title" content="{esc(title)}">
<meta property="og:description" content="{esc(desc)}">
<meta property="og:image" content="{ogi}">
<meta property="og:url" content="{canon}">
<meta property="og:locale" content="ko_KR">
<meta name="twitter:card" content="summary_large_image">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="icon" type="image/png" href="/favicon.png">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@400;500;600;700&display=swap" rel="stylesheet">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css">
{chr(10).join(ld(x) for x in lds)}
<link rel="stylesheet" href="{pre}assets/style.css?v={STYLE_V}">
<link rel="stylesheet" href="{pre}assets/products.css?v={asset_ver('assets/products.css')}">
{extra}<script>document.documentElement.className += ' js';</script>
</head>"""


def body_open(depth, body_class):
    pre = "../" * depth
    return f"""<body class="prp {body_class}">
<div class="grain"></div>
<div class="progress" id="prog"></div>
<div class="util"><div class="wrap"><span>Luami — 무인 포토부스 렌탈</span><span>Est. 2026 · Korea</span></div></div>
<header class="nav"></header>

<div class="drawer-scrim" id="drawerScrim" aria-hidden="true"></div>
<div class="stickybar" id="sbar">
  <a href="{pre}index.html" class="logo">Luami<span class="dot"></span></a>
  <a href="{pre}index.html#contact" class="btn-mini">렌탈 문의</a>
  <button class="navtoggle" id="navToggle2" aria-label="메뉴 열기" aria-controls="drawer"><span></span><span></span><span></span></button>
</div>
"""


def body_close(depth):
    pre = "../" * depth
    return f"""<footer></footer>

<div class="mcta"><a href="{KAKAO}" target="_blank" rel="noopener">카톡 상담</a><a href="{TEL}">전화 상담</a><a href="{pre}index.html#contact" class="p">무료 견적</a></div>

<script src="https://unpkg.com/lenis@1/dist/lenis.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/gsap.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/gsap@3.12.5/dist/ScrollTrigger.min.js" defer></script>
<script src="{pre}assets/main.js?v=20260911b" defer></script>
<script src="{pre}assets/products.js?v={asset_ver('assets/products.js')}" defer></script>
</body>
</html>
"""


def sec_head(label, h2, p="", right=""):
    ptag = f"<p>{p}</p>" if p else ""
    return f"""  <div class="ps-head">
    <div><span class="idxlabel">{label}</span><h2>{h2}</h2>{ptag}</div>{right}
  </div>"""


def faq_html(faq):
    return "\n".join(f"    <details><summary>{esc(q['q'])}</summary><p>{esc(tmpl(q['a']))}</p></details>" for q in faq)


def cta_band(depth, h2, p):
    pre = "../" * depth
    return f"""<section class="ps-cta"><div class="wrap"><div class="band">
  <h2>{h2}</h2><p>{p}</p>
  <div class="contacts">
    <a href="{KAKAO}" target="_blank" rel="noopener" class="kakao">카카오톡 상담</a><a href="{TEL}">전화 상담</a><a href="{pre}index.html#contact">무료 견적 요청</a>
  </div>
</div></div></section>
"""


def chips_for(prod, extra=True):
    out = []
    if prod.get("badge"):
        out.append(f'<span class="badge badge-{prod.get("badge_kind", "main")}">{esc(prod["badge"])}</span>')
    if prod.get("highangle"):
        out.append(f'<span class="badge badge-ha">{esc(P["highangle_text"][prod["highangle"]]["chip"])}</span>')
    return "".join(out)


def price_dl(slug, cls="pc-price"):
    rows = price_of(slug)
    inner = "".join(f"<div><dt>{a}</dt><dd>{b}</dd></div>" for a, b, _ in rows)
    return f'<dl class="{cls}">{inner}</dl>'


def tags_of(prod):
    t = [prod.get("type", "")]
    if prod.get("highangle"):
        t.append("highangle")
    if has_fixed_price(prod["slug"]):
        t.append("price")
    return " ".join(x for x in t if x)


# ───────────────────────── 하이앵글 개념도(SVG) ─────────────────────────
def svg_highangle(kind):
    if kind == "ceiling":
        body = """
  <ellipse cx="160" cy="44" rx="104" ry="14" fill="none" stroke="currentColor" stroke-width="2"/>
  <path d="M56 44 V206 M264 44 V206" stroke="currentColor" stroke-width="2" fill="none"/>
  <path d="M56 206 A104 14 0 0 0 264 206" stroke="currentColor" stroke-width="2" fill="none"/>
  <polygon points="160,58 96,206 224,206" class="cone"/>
  <path d="M160 58 L96 206 M160 58 L224 206" class="ray"/>
  <rect x="147" y="44" width="26" height="16" rx="3" class="cam"/>
  <circle cx="160" cy="60" r="5" class="lens"/>
  <g class="ppl"><circle cx="138" cy="160" r="10"/><rect x="127" y="172" width="22" height="34" rx="9"/>
  <circle cx="182" cy="164" r="10"/><rect x="171" y="176" width="22" height="30" rx="9"/></g>
  <text x="182" y="40" class="lbl">천장 가운데 카메라</text>"""
        label = "원형 부스 측면 개념도: 천장 가운데 카메라가 바로 아래 바닥을 향해 찍는다"
    else:
        body = """
  <rect x="56" y="30" width="208" height="176" fill="none" stroke="currentColor" stroke-width="2"/>
  <polygon points="74,46 150,206 262,206 262,132" class="cone"/>
  <path d="M74 46 L150 206 M74 46 L262 132" class="ray"/>
  <g transform="rotate(38 74 46)"><rect x="60" y="38" width="28" height="16" rx="3" class="cam"/></g>
  <circle cx="82" cy="54" r="5" class="lens"/>
  <g class="ppl"><circle cx="190" cy="148" r="10"/><rect x="179" y="160" width="22" height="46" rx="9"/>
  <circle cx="226" cy="152" r="10"/><rect x="215" y="164" width="22" height="42" rx="9"/></g>
  <text x="96" y="26" class="lbl">모서리 위 카메라</text>"""
        label = "부스 측면 개념도: 안쪽 모서리 위 카메라가 아래쪽 사람과 바닥을 비스듬히 내려다보며 찍는다"
    return f"""<svg class="ha-svg" viewBox="0 0 320 232" role="img" aria-label="{label}">{body}
  <path d="M30 206 H290" stroke="currentColor" stroke-width="2"/>
  <text x="290" y="224" class="lbl" text-anchor="end">바닥</text>
</svg>"""


# ───────────────────────── 제품 상세 ─────────────────────────
def detail_page(prod, idx):
    slug = prod["slug"]
    c = COPY[slug]
    depth = 1
    pre = "../"
    is_custom = slug == "custom"
    cov = cover(prod, "4x5")
    gal = gallery(slug)
    n_photo = sum(1 for x in gal if x["kind"] == "photo")
    n_render = sum(1 for x in gal if x["kind"] == "render")
    st = stories(slug)
    seo = prod["seo"]
    desc = tmpl(seo["description"])
    og = cover(prod, "1x1") or cov

    # JSON-LD
    lds = [breadcrumb([("홈", ""), ("제품", "products.html"), (prod["name"], f"products/{slug}.html")]), faq_ld(c["faq"])]
    if has_fixed_price(slug):
        m = PR["products"][slug]
        vat_inc = {"excluded": False, "included": True}.get(PR["vat"]["mode"])
        offers = []

        def offer(key, name, lease=False):
            it = PR["items"][key]
            o = {"@type": "Offer", "name": name, "price": it["amount"] * 10000, "priceCurrency": PR["currency"],
                 "url": f"{BASE}/products/{slug}.html", "seller": {"@id": f"{BASE}/#business"}}
            if lease:
                o["businessFunction"] = "http://purl.org/goodrelations/v1#LeaseOut"
            spec = {"@type": "UnitPriceSpecification" if it.get("per") == "월" else "PriceSpecification",
                    "price": it["amount"] * 10000, "priceCurrency": PR["currency"]}
            if it.get("per") == "월":
                spec["referenceQuantity"] = {"@type": "QuantitativeValue", "value": 1, "unitCode": "MON"}
            if vat_inc is not None:
                spec["valueAddedTaxIncluded"] = vat_inc
            o["priceSpecification"] = spec
            return o

        if m.get("rental_summary"):
            offers.append(offer(m["rental_summary"], "렌탈 · " + PR["items"][m["rental_summary"]]["label"], lease=True))
        if m.get("purchase"):
            offers.append(offer(m["purchase"], "구매"))
        imgs = [BASE + "/" + cov["src"]] + [BASE + "/" + x["src"] for x in gal[:3]]
        lds.append({"@context": "https://schema.org", "@type": "Product", "name": prod["name"],
                    "alternateName": prod["name_en"], "description": c["hero"], "image": list(dict.fromkeys(imgs)),
                    "brand": {"@type": "Brand", "name": "루아미"}, "url": f"{BASE}/products/{slug}.html",
                    "offers": offers})

    out = [head(seo["title"], desc, seo["keywords"], f"products/{slug}.html", og["src"], depth, lds),
           body_open(depth, "pd")]

    # 히어로
    num = "Custom" if is_custom else f"{prod['order']:02d} / {len(LINEUP):02d}"
    chips = chips_for(prod)
    count_chips = []
    if n_photo:
        count_chips.append(f'<span class="badge badge-line">실사 {n_photo}장</span>')
    if n_render:
        count_chips.append(f'<span class="badge badge-line">CAD 3D 렌더 {n_render}장</span>')
    prows = price_of(slug)
    price_rows = "".join(f'<div class="pb-row"><span class="pb-k">{a}</span><span class="pb-v">{b}</span></div>' for a, b, _ in prows)
    ship = PR.get("shipping_note", "")
    jl = []
    if gal:
        jl.append(f'<a href="#gallery">사례 사진 {len(gal)}장</a>')
    if prod.get("highangle"):
        jl.append('<a href="#angle">촬영 구도</a>')
    if st:
        jl.append(f'<a href="#stories">사례·이야기 {len(st)}</a>')
    jl.append('<a href="#faq">자주 묻는 질문</a>')
    hero_jump = '<nav class="pd-jump" aria-label="이 페이지 바로가기">' + "".join(jl) + "</nav>"
    out.append(f"""
<section class="pd-hero"><div class="wrap">
  <nav class="crumb" aria-label="현재 위치"><a href="{pre}index.html">홈</a><span aria-hidden="true">›</span><a href="{pre}products.html">제품</a><span aria-hidden="true">›</span><span aria-current="page">{esc(prod['name'])}</span></nav>
  <div class="pd-grid">
    <figure class="pd-cover">{img_tag(cov, depth, cover_alt(prod, cov), priority=True)}{render_tag(cov, large=True)}</figure>
    <div class="pd-info">
      <span class="idxlabel">{num} · {esc(prod['name_en'])}</span>
      <h1>{esc(prod['name'])}</h1>
      <p class="pd-tagline">{esc(c['tagline'])}</p>
      <div class="pd-chips">{chips}{''.join(count_chips)}</div>
      <p class="pd-lead">{esc(c['hero'])}</p>
      <div class="pricebox">
        {price_rows}
        <p class="pb-note">{esc(ship + ' · ' if has_fixed_price(slug) and slug != 'photo-kiosk' else '')}<a href="#price">가격 조건 보기</a> · <a href="{pre}pricing.html">전체 가격표</a></p>
      </div>
      {hero_jump}
      <div class="pd-cta"><a class="btn" href="{pre}index.html#contact">견적 문의 <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></a><a class="btn-ghost" href="{KAKAO}" target="_blank" rel="noopener">카톡 상담</a></div>
    </div>
  </div>
</div></section>
""")

    # 끌리는 포인트
    pts = "\n".join(f'    <li><b>{esc(a["title"])}</b><span>{esc(a["body"])}</span></li>' for a in c["appeal"])
    out.append(f"""<section class="pd-points"><div class="wrap">
{sec_head('Why', '끌리는 포인트')}
  <ol class="pts">
{pts}
  </ol>
</div></section>
""")

    # 하이앵글 구조
    if prod.get("highangle"):
        ht = P["highangle_text"][prod["highangle"]]
        out.append(f"""<section class="pd-angle" id="angle"><div class="wrap ha-grid">
  <div>
    <span class="idxlabel">High Angle</span>
    <h2>{esc(ht['title'])}</h2>
    <p>{esc(ht['body'])}</p>
    <p class="ha-note">구조 개념도예요. 실제 크기·각도는 부스마다 달라요.</p>
  </div>
  <figure class="ha-fig">{svg_highangle(prod['highangle'])}</figure>
</div></section>
""")

    # 사례 사진 갤러리
    if gal:
        cells = []
        # 첫 장은 2×2, 나머지는 1칸. 4열 격자의 마지막 줄이 비지 않도록 끝에서 k장을 가로 2칸으로 넓힌다.
        k = (4 - (len(gal) + 3) % 4) % 4 if len(gal) > 1 else 0
        k = min(k, len(gal) - 1)
        for i, it in enumerate(gal):
            tw, th = thumb_dims(it)
            cap = it.get("caption", "")
            span = " pg-wide" if i == 0 else (" pg-w2" if i >= len(gal) - k else "")
            cells.append(
                f'    <a class="pg-item{span}" href="{u(it["src"], depth)}" data-w="{it["w"]}" data-h="{it["h"]}" data-caption="{esc(cap)}">'
                f'<img src="{u(it["src"] if i == 0 else (it.get("thumb") or it["src"]), depth)}" width="{it["w"] if i == 0 else tw}" height="{it["h"] if i == 0 else th}" alt="{esc(it["alt"])}" loading="lazy" decoding="async"{contain_style(it)}>'
                f'{render_tag(it)}<span class="pg-cap">{esc(cap)}</span></a>')
        note = "사진을 누르면 크게 볼 수 있어요."
        if n_render and not n_photo:
            note += " 아직 실물 사진이 없어 CAD 3D 렌더로 보여드려요."
        elif n_render:
            note += " 렌더 이미지에는 ‘CAD 3D 렌더’라고 표시했어요."
        out.append(f"""<section class="pd-gallery" id="gallery"><div class="wrap">
{sec_head(f'Gallery · {len(gal)}', '사례 사진', note)}
  <div class="pg-grid" data-gallery="{slug}">
{chr(10).join(cells)}
  </div>
</div></section>
""")

    # 스탠다드 부스 — 4면 랩핑 한눈에
    if slug == "standard-booth":
        out.append(wrap_section(depth, compact=True))

    # 이런 곳 · 진행 · 사양
    fit = "".join(f"<li>{esc(x)}</li>" for x in c["fit"])
    steps = []
    for s_ in c["how"]:
        k, _, v = s_.partition(":")
        steps.append(f"<li><b>{esc(k.strip())}</b><span>{esc(v.strip())}</span></li>" if v else f"<li><span>{esc(s_)}</span></li>")
    out.append(f"""<section class="pd-fit"><div class="wrap fit-grid">
  <div>
    <span class="idxlabel">Fit</span>
    <h2>이런 곳에 잘 맞아요</h2>
    <ul class="fit-list">{fit}</ul>
    <div class="spec-note"><b>사양 메모</b><p>{esc(c['specs_note'])}</p></div>
  </div>
  <div>
    <span class="idxlabel">Process</span>
    <h2>진행은 이렇게</h2>
    <ol class="how">{''.join(steps)}</ol>
  </div>
</div></section>
""")

    # 이 제품 이야기·사례
    if st:
        def card(x):
            return (f'<a class="st-card" href="{pre}{x["href"]}"><span class="st-type">{x["type"]}</span>'
                    f'<b>{esc(x["title"])}</b><span class="st-desc">{esc(clip(x["desc"], 72))}</span></a>')
        first, rest = st[:6], st[6:]
        more = ""
        if rest:
            more = (f'<details class="st-more"><summary>사례·이야기 {len(rest)}개 더 보기</summary>'
                    f'<div class="st-grid">{"".join(card(x) for x in rest)}</div></details>')
        n_case = sum(1 for x in st if x["type"] == "사례")
        n_blog = len(st) - n_case
        out.append(f"""<section class="pd-stories" id="stories"><div class="wrap">
{sec_head('Stories', '이 제품이 쓰인 사례·이야기', ' · '.join(x for x in [f'사례 {n_case}개' if n_case else '', f'블로그 {n_blog}편' if n_blog else ''] if x) + '을 모았어요.')}
  <div class="st-grid">{''.join(card(x) for x in first)}</div>
  {more}
</div></section>
""")

    # 가격
    out.append(detail_price_section(slug, depth))

    # FAQ
    out.append(f"""<section class="pd-faq" id="faq"><div class="wrap">
{sec_head('FAQ', '자주 묻는 질문')}
  <div class="faq ps-faq">
{faq_html(c['faq'])}
  </div>
</div></section>
""")

    out.append(cta_band(depth, f"{esc(prod['name'])}, <i>견적부터 받아 보세요.</i>",
                        "장소·기간·대수를 알려주시면 구성과 견적을 안내해 드려요. 상담만으로 비용이 생기지 않아요."))

    # 이전·다음
    prv = DETAIL[idx - 1]
    nxt = DETAIL[(idx + 1) % len(DETAIL)]
    out.append(f"""<nav class="pd-pn" aria-label="다른 제품"><div class="wrap pn-in">
  <a href="{prv['slug']}.html" class="pn-prev"><span>이전 제품</span><b>{esc(prv['name'])}</b></a>
  <a href="{pre}products.html#lineup" class="pn-all">제품 전체</a>
  <a href="{nxt['slug']}.html" class="pn-next"><span>다음 제품</span><b>{esc(nxt['name'])}</b></a>
</div></nav>
""")
    out.append(body_close(depth))
    return "".join(out)


def detail_price_section(slug, depth):
    pre = "../" * depth
    m = PR["products"].get(slug) or PR["products"]["_concept"]
    rows = []
    for k in m.get("rental", []):
        it = PR["items"][k]
        inc = "".join(f"<li>{esc(x)}</li>" for x in it.get("includes", []))
        inc = f'<ul class="inc">{inc}</ul>' if inc else ""
        note = f'<span class="pt-note">{esc(it["note"])}</span>' if it.get("note") else ""
        rows.append(f'<tr><th scope="row">{esc(it["label"])}<span class="pt-unit">{esc(it.get("unit", ""))}</span>{inc}{note}</th>'
                    f'<td>{amt_html(k)}</td></tr>')
    if m.get("purchase"):
        k = m["purchase"]
        rows.append(f'<tr><th scope="row">구매 · {esc(PR["items"][k]["label"])}</th><td>{amt_html(k)}</td></tr>')
    body = ""
    if rows:
        body += f'<table class="ptable"><tbody>{"".join(rows)}</tbody></table>'
    if not m.get("rental"):
        body += f'<div class="ask-box"><div class="pb-row"><span class="pb-k">렌탈</span><span class="pb-v"><span class="ask">{esc(m["rental_text"])}</span></span></div>'
        if not m.get("purchase"):
            body += f'<div class="pb-row"><span class="pb-k">구매</span><span class="pb-v"><span class="ask">{esc(m["purchase_text"])}</span></span></div>'
        body += "</div>"
    extra = ""
    if slug == "standard-booth":
        ex = "".join(f'<li><span>{esc(e["label"])}</span><span>{amt_html_val(std_total(e["units"], e["months"]))}</span></li>'
                     for e in PR["examples"])
        extra = f'<div class="ex-box"><b>계산 예시</b><ul class="ex-list">{ex}</ul><p>1년 가까이 쓰실 계획이라면 구매를 권해 드려요. <a href="{pre}pricing.html#examples">계산 기준 보기</a></p></div>'
    if not has_fixed_price(slug) or slug == "photo-kiosk":
        ask = "".join(f"<li>{esc(x)}</li>" for x in PC["negotiable"]["ask_for"])
        extra += f'<div class="ex-box"><b>문의할 때 알려주시면 빨라요</b><ul class="ask-list">{ask}</ul></div>'
    notes = []
    if PR["products"].get(slug, {}).get("rental"):
        notes.append(PR.get("shipping_note", ""))
    notes.append(vat_sentence())
    return f"""<section class="pd-price" id="price"><div class="wrap">
{sec_head('Price', '가격', ' · '.join(x for x in notes if x), f'<a class="ps-link" href="{pre}pricing.html">전체 가격표 →</a>')}
  <div class="price-grid">
    <div>{body}</div>
    <div>{extra}</div>
  </div>
</div></section>
"""


def vat_sentence():
    mode = PR["vat"]["mode"]
    if mode == "excluded":
        return "표시한 금액은 모두 부가세 별도예요"
    if mode == "included":
        return "표시한 금액은 모두 부가세 포함이에요"
    return "부가세는 상담 때 안내해 드려요"


# ───────────────────────── 4면 랩핑(가격·스탠다드 상세 공용) ─────────────────────────
def wrap_section(depth, compact=False):
    pre = "../" * depth
    w = PC["wrapping"]
    sets = []
    for ba in WRAP["before_after"]:
        def fig(it, tag):
            tw, th = thumb_dims(it)
            return (f'<a class="pg-item ba-item" href="{u(it["src"], depth)}" data-w="{it["w"]}" data-h="{it["h"]}" data-caption="{esc(it["caption"])}">'
                    f'<img src="{u(it["thumb"], depth)}" width="{tw}" height="{th}" alt="{esc(it["alt"])}" loading="lazy" decoding="async"{contain_style(it)}>'
                    f'{render_tag(it)}<span class="ba-tag">{tag}</span></a>')
        before = "".join(fig(x, "전") for x in ba["before"][:1])
        after = "".join(fig(x, "후") for x in ba["after"][: (2 if compact else 3)])
        sets.append(f"""  <div class="ba">
    <div class="ba-head"><b>{esc(ba['title'])}</b><p>{esc(ba['note'])}</p></div>
    <div class="ba-row" data-gallery="wrap-{ba['id']}">{before}<span class="ba-arrow" aria-hidden="true">→</span>{after}</div>
  </div>""")
    if compact:
        sets = sets[:1]
        return f"""<section class="pd-wrap"><div class="wrap">
{sec_head('Wrapping', esc(w['title']) + ' — <i>렌탈에 포함</i>', esc(w['lead']), f'<a class="ps-link" href="{pre}pricing.html#wrap">랩핑 자세히 →</a>')}
{chr(10).join(sets)}
</div></section>
"""
    steps = "".join(f"<li>{esc(s)}</li>" for s in w["steps"])
    exs = []
    for it in WRAP.get("examples", []) + WRAP.get("details", []):
        tw, th = thumb_dims(it)
        exs.append(f'<a class="pg-item" href="{u(it["src"], depth)}" data-w="{it["w"]}" data-h="{it["h"]}" data-caption="{esc(it["caption"])}">'
                   f'<img src="{u(it["thumb"], depth)}" width="{tw}" height="{th}" alt="{esc(it["alt"])}" loading="lazy" decoding="async">'
                   f'<span class="pg-cap">{esc(it["caption"])}</span></a>')
    links = "".join(f'<li><a href="{pre}{x["href"]}">{esc(x["title"])}</a></li>' for x in w["examples"])
    return f"""<section class="pp-wrap" id="wrap"><div class="wrap">
{sec_head('Wrapping', esc(w['title']) + ' — <i>스탠다드 부스 렌탈에 포함</i>', esc(w['lead']))}
{chr(10).join(sets)}
  <div class="wrap-grid">
    <div class="wrap-txt">
      <p>{esc(w['body'])}</p>
      <ol class="how wrap-steps">{steps}</ol>
      <p class="muted">{esc(w['design_note'])}</p>
    </div>
    <div>
      <div class="pg-grid pg-mini" data-gallery="wrap-more">{''.join(exs)}</div>
      <p class="muted wrap-ex-note">{esc(w['examples_note'])}</p>
      <ul class="link-list">{links}</ul>
    </div>
  </div>
</div></section>
"""


# ───────────────────────── 허브(products.html) ─────────────────────────
def legacy_map_script():
    m = {}
    for prod in DETAIL:
        for a in prod.get("legacy_anchors", []):
            m[a] = f"products/{prod['slug']}.html"
    sec = P["legacy_sections"]
    return ("<script>/* 옛 제품군 앵커(#p-aXX)를 새 제품 상세로 보낸다 — GitHub Pages 라 서버 리다이렉트 불가 */\n"
            "(function(){var m=" + json.dumps(m, separators=(",", ":")) + ",s=" + json.dumps(sec, separators=(",", ":")) +
            ";function go(){var h=location.hash.slice(1);if(m[h]){location.replace(m[h]);return}"
            "if(s[h]){history.replaceState(null,'',s[h]);var t=document.querySelector(s[h]);if(t)t.scrollIntoView();return}"
            "if(/^p-[ab]\\d\\d$/.test(h)){document.documentElement.classList.add('legacy-gone')}}"
            "go();addEventListener('hashchange',go)})();</script>\n")


def hub_card(prod, depth=0):
    pre = "../" * depth
    c = COPY[prod["slug"]]
    img = cover(prod, "4x5")
    badge = (f'<span class="badge badge-{prod.get("badge_kind", "main")} pc-badge">{esc(prod["badge"])}</span>'
             if prod.get("badge") else "")
    ha = (f'<span class="badge badge-ha">{esc(P["highangle_text"][prod["highangle"]]["chip"])}</span>'
          if prod.get("highangle") else "")
    type_chip = '<span class="badge badge-line">키오스크</span>' if prod["type"] == "kiosk" else '<span class="badge badge-line">부스</span>'
    return f"""    <article class="pc" data-tags="{tags_of(prod)}">
      <a href="{pre}products/{prod['slug']}.html">
        <figure class="pc-im">{img_tag(img, depth, cover_alt(prod, img))}<span class="pc-no">{prod['order']:02d}</span>{badge}{render_tag(img)}</figure>
        <div class="pc-body">
          <div class="pc-chips">{type_chip}{ha}</div>
          <h3>{esc(prod['name'])}</h3>
          <p class="pc-tag">{esc(c['tagline'])}</p>
          {price_dl(prod['slug'])}
          <span class="pc-more">자세히 보기 <span aria-hidden="true">→</span></span>
        </div>
      </a>
    </article>"""


def featured_card(prod):
    c = COPY[prod["slug"]]
    img = cover(prod, "4x5")
    pk = PR["products"][prod["slug"]]
    if pk.get("rental_summary") and PR["items"][pk["rental_summary"]].get("includes"):
        hl = PR["items"][pk["rental_summary"]]["includes"] + ([PR["items"][pk["rental_summary"]]["note"]] if PR["items"][pk["rental_summary"]].get("note") else [])
        hl_html = "".join(f"<li>{esc(x)}</li>" for x in hl)
        hl_title = "렌탈에 들어 있는 것"
    else:
        hl_html = "".join(f"<li>{esc(a['title'])}</li>" for a in c["appeal"][:4])
        hl_title = "이런 점이 좋아요"
    rows = "".join(f'<div class="pb-row"><span class="pb-k">{a}</span><span class="pb-v">{b}</span></div>' for a, b, _ in price_of(prod["slug"]))
    return f"""    <article class="fc">
      <a class="fc-im" href="products/{prod['slug']}.html" tabindex="-1" aria-hidden="true">{img_tag(img, 0, cover_alt(prod, img))}{render_tag(img, large=True)}</a>
      <div class="fc-body">
        <div class="pc-chips"><span class="badge badge-{prod.get('badge_kind', 'main')}">{esc(prod['badge'])}</span><span class="fc-no">{prod['order']:02d} / {len(LINEUP):02d}</span></div>
        <h3><a href="products/{prod['slug']}.html">{esc(prod['name'])}</a></h3>
        <p class="fc-tag">{esc(c['tagline'])}</p>
        <b class="fc-hl-t">{hl_title}</b>
        <ul class="fc-hl">{hl_html}</ul>
        <div class="pricebox fc-price">{rows}</div>
        <div class="fc-cta"><a class="btn" href="products/{prod['slug']}.html">자세히 보기</a><a class="btn-ghost" href="index.html#contact">견적 문의</a></div>
      </div>
    </article>"""


def concept_card(cp):
    c = COPY[cp["slug"]]
    img = cover(cp, "4x5")
    tag = re.sub(r"\s*·\s*신규 컨셉\s*$", "", c["tagline"])
    if img:
        fig = f'<figure class="cc-im">{img_tag(img, 0, cp["name"] + " — CAD 3D 렌더")}{render_tag(img)}</figure>'
    else:
        fig = (f'<figure class="cc-im cc-empty" aria-hidden="true"><span class="cc-mark">{esc(cp["name_en"])}</span>'
               f'<span class="cc-pending">CAD 3D 렌더 준비 중</span></figure>')
    fit = "".join(f"<li>{esc(x)}</li>" for x in c["fit"][:3])
    ha = (f'<span class="badge badge-ha">{esc(P["highangle_text"][cp["highangle"]]["chip"])}</span>' if cp.get("highangle") else "")
    pts = "".join(f"<li>{esc(a['title'])}</li>" for a in c["appeal"][:3])
    return f"""    <article class="cc">
      {fig}
      <div class="cc-body">
        <div class="pc-chips"><span class="badge badge-line">신규 컨셉 · 실물 미제작</span>{ha}</div>
        <h3>{esc(cp['name'])}</h3>
        <p class="pc-tag">{esc(tag)}</p>
        <ul class="cc-pts">{pts}</ul>
        <p class="cc-fit"><b>어울리는 곳</b> {' · '.join(esc(x) for x in c['fit'][:3])}</p>
        <p class="cc-price"><span class="ask">{esc(PR['products']['_concept']['rental_text'])}</span></p>
      </div>
    </article>"""


def hub_page():
    h = P["hub"]
    feat = [BYSLUG["standard-booth"], BYSLUG["wood-kiosk"]]
    items = [{"@type": "ListItem", "position": i + 1, "url": f"{BASE}/products/{x['slug']}.html", "name": x["name"]}
             for i, x in enumerate(DETAIL)]
    lds = [breadcrumb([("홈", ""), ("제품", "products.html")]),
           {"@context": "https://schema.org", "@type": "ItemList", "name": "루아미 포토부스 · 포토키오스크 제품",
            "numberOfItems": len(items), "itemListOrder": "https://schema.org/ItemListOrderAscending", "itemListElement": items},
           faq_ld(h["faq"])]
    og = cover(BYSLUG["standard-booth"], "1x1") or cover(BYSLUG["standard-booth"], "4x5")
    out = [head(h["title"], h["description"], h["keywords"], "products.html", og["src"], 0, lds,
                extra=legacy_map_script()), body_open(0, "ph")]
    counts = {
        "all": len(LINEUP),
        "price": sum(1 for x in LINEUP if has_fixed_price(x["slug"])),
        "highangle": sum(1 for x in LINEUP if x.get("highangle")),
        "kiosk": sum(1 for x in LINEUP if x["type"] == "kiosk"),
        "booth": sum(1 for x in LINEUP if x["type"] == "booth"),
    }
    anchors = "".join(f'<span id="{a}" class="legacy-anchor" aria-hidden="true"></span>'
                      for prod in DETAIL for a in prod.get("legacy_anchors", []))
    anchors += "".join(f'<span id="{a}" class="legacy-anchor" aria-hidden="true"></span>' for a in P["unmapped_anchors"])
    out.append(f"""
<section class="page-head ph-head"><div class="wrap">
  <span class="idxlabel">Products · {len(LINEUP)} + Custom</span>
  <h1>포토부스 · 포토키오스크 제품군</h1>
  <p>{esc(h['lead'])}</p>
  <p class="legacy-note" role="status">찾으신 형태는 지금 라인업에서 빠졌어요. 비슷한 구성은 <a href="products/custom.html">커스텀 제작</a>으로 상담해 드려요.</p>
  <nav class="jump" aria-label="이 페이지 바로가기"><a href="#featured">주력 모델</a><a href="#lineup">제품 {len(LINEUP)}종</a><a href="#custom">커스텀 제작</a><a href="#concepts">신규 컨셉</a><a href="pricing.html">가격표</a></nav>
</div></section>
{anchors}
<section class="ph-featured" id="featured"><div class="wrap">
{sec_head('Featured', '주력 모델', '스탠다드 부스가 주력이고, 그다음은 포토키오스크 목재형이에요.')}
  <div class="fc-grid">
{chr(10).join(featured_card(x) for x in feat)}
  </div>
</div></section>

<section class="ph-lineup" id="lineup"><div class="wrap">
{sec_head(f'Lineup · {len(LINEUP)}', f'제품 {len(LINEUP)}종', '번호는 제품 순서예요. ‘하이앵글’은 카메라가 위에서 내려다보며 찍는 부스예요.')}
  <div class="filters" role="group" aria-label="제품 거르기">
    <button type="button" class="fchip" data-filter="" aria-pressed="true">전체 <b>{counts['all']}</b></button>
    <button type="button" class="fchip" data-filter="price" aria-pressed="false">가격 공개 <b>{counts['price']}</b></button>
    <button type="button" class="fchip" data-filter="highangle" aria-pressed="false">하이앵글 <b>{counts['highangle']}</b></button>
    <button type="button" class="fchip" data-filter="kiosk" aria-pressed="false">키오스크 <b>{counts['kiosk']}</b></button>
    <button type="button" class="fchip" data-filter="booth" aria-pressed="false">부스 <b>{counts['booth']}</b></button>
  </div>
  <p class="fcount" id="fcount" aria-live="polite"></p>
  <div class="pc-grid" id="pcGrid">
{chr(10).join(hub_card(x) for x in LINEUP)}
  </div>
</div></section>
""")
    # 커스텀 블록
    cc = COPY["custom"]
    mos = [x for x in G.get("custom", []) if x.get("scene") in ("install", "event")][:4]
    mos_html = "".join(
        f'<a class="pg-item" href="{x["src"]}" data-w="{x["w"]}" data-h="{x["h"]}" data-caption="{esc(x["caption"])}">'
        f'<img src="{x["thumb"]}" width="{thumb_dims(x)[0]}" height="{thumb_dims(x)[1]}" alt="{esc(x["alt"])}" loading="lazy" decoding="async"></a>'
        for x in mos)
    scopes = "".join(f"<li><b>{esc(a['title'])}</b><span>{esc(a['body'])}</span></li>" for a in cc["appeal"][:3])
    out.append(f"""<section class="ph-custom" id="custom"><div class="wrap cu-grid">
  <div class="cu-txt">
    <span class="idxlabel">Custom</span>
    <h2>원하는 디자인, <i>제작해 드려요</i></h2>
    <p>{esc(cc['hero'])}</p>
    <ul class="cu-list">{scopes}</ul>
    <p class="cu-price"><span class="pb-k">가격</span> <span class="ask">{esc(PR['products']['custom']['rental_text'])}</span></p>
    <div class="fc-cta"><a class="btn" href="products/custom.html">커스텀 제작 자세히</a><a class="btn-ghost on-dark" href="index.html#contact">제작 문의</a></div>
  </div>
  <div class="cu-mosaic" data-gallery="custom-hub">{mos_html}</div>
</div></section>
""")
    out.append(f"""<section class="ph-concepts" id="concepts"><div class="wrap">
{sec_head('New Concepts', f'새로 제안하는 컨셉 {len(CONCEPTS)}종', '만들 수 있지만 아직 실물로 만든 적은 없는 컨셉이에요. 이미지는 ‘CAD 3D 렌더’로만 보여드리고, 크기·구성·기간·가격은 상담 때 함께 정해요.', '<a class="ps-link" href="blog/new-concepts-story.html">컨셉 이야기 읽기 →</a>')}
  <div class="cc-grid">
{chr(10).join(concept_card(x) for x in CONCEPTS)}
  </div>
</div></section>

<section class="ph-faq" id="faq"><div class="wrap">
{sec_head('FAQ', '자주 묻는 질문')}
  <div class="faq ps-faq">
{faq_html(h['faq'])}
  </div>
</div></section>
""")
    out.append(cta_band(0, "어떤 제품이 맞을지 고민이라면, <i>장소·기간·인원만 알려주세요.</i>",
                        "현장 조건에 맞는 제품과 대수를 골라 견적과 함께 안내해 드려요."))
    out.append(body_close(0))
    return "".join(out)


# ───────────────────────── 가격(pricing.html) ─────────────────────────
def pricing_page():
    pg = PC["page"]
    depth = 0
    lds = [breadcrumb([("홈", ""), ("가격", "pricing.html")]), faq_ld(PC["faq"])]
    desc = tmpl("스탠다드 부스 1개월 미만 렌탈 {price:std_short} — 촬영 키오스크·4면 랩핑·인화지 1,400매 포함(운임 별도). "
                "목재 키오스크 렌탈 월 {price:wood_monthly}, 구매 {price:std_buy}부터. 루아미 렌탈·구매 가격표.")
    og = cover(BYSLUG["standard-booth"], "1x1") or {"src": WRAP["hero"]["src"]}
    out = [head("포토부스 렌탈·구매 가격 | 스탠다드 부스 · 포토키오스크 — 루아미", desc,
                "포토부스 렌탈 가격,포토부스 렌탈 비용,포토부스 대여 비용,포토부스 구매,포토키오스크 가격,포토부스 랩핑,루아미",
                "pricing.html", og["src"], depth, lds), body_open(depth, "pp")]
    it = PR["items"]
    std = BYSLUG["standard-booth"]
    wood = BYSLUG["wood-kiosk"]
    buy_min = min(it[k]["amount"] for k in it if it[k]["kind"] == "purchase")
    buy_min_key = [k for k in it if it[k]["kind"] == "purchase" and it[k]["amount"] == buy_min][0]
    out.append(f"""
<section class="page-head pp-head"><div class="wrap">
  <span class="idxlabel">Pricing</span>
  <h1>{esc(pg['h1'])}</h1>
  <p>{esc(pg['lead'])}</p>
  <div class="sum-grid">
    <a class="sum" href="#rental"><span class="sum-k">스탠다드 부스 렌탈 · 1개월 미만</span><span class="sum-v">{amt_html('std_short')}</span><span class="sum-d">4면 랩핑 · 인화지 1,400매 포함 · 운임 별도</span></a>
    <a class="sum" href="#kiosk"><span class="sum-k">포토키오스크 목재형 · 키오스크만</span><span class="sum-v">{amt_html('wood_monthly')}</span><span class="sum-d">인화지 700매 제공</span></a>
    <a class="sum" href="#purchase"><span class="sum-k">구매</span><span class="sum-v"><span class="amt">{esc(man(buy_min))}부터</span>{vat_html()}</span><span class="sum-d">{esc(it[buy_min_key]['label'])} 기준 · 포토키오스크·목재형 별도 가격</span></a>
  </div>
  <nav class="jump" aria-label="이 페이지 바로가기"><a href="#rental">렌탈</a><a href="#examples">계산 예시</a><a href="#wrap">4면 랩핑</a><a href="#kiosk">키오스크만</a><a href="#negotiable">협의 제품</a><a href="#purchase">구매</a><a href="#notes">운임·부가세</a><a href="#faq">FAQ</a></nav>
</div></section>
""")
    # 렌탈 표
    r = PC["rental"]
    rows = []
    for row in r["rows"]:
        k = row["key"]
        if k not in it or k == "wood_monthly":
            continue
        x = it[k]
        inc = "".join(f"<li>{esc(v)}</li>" for v in x.get("includes", []))
        inc = f'<ul class="inc">{inc}</ul>' if inc else ""
        note = f'<span class="pt-note">{esc(tmpl(row["note"]))}</span>' if row.get("note") else ""
        rows.append(f'<tr><th scope="row">{esc(x["label"])}<span class="pt-unit">{esc(x.get("unit", ""))}</span>{inc}{note}</th><td>{amt_html(k)}</td></tr>')
    out.append(f"""<section class="pp-rental" id="rental"><div class="wrap">
{sec_head('Rental', '스탠다드 부스 렌탈', esc(r['desc']), f'<a class="ps-link" href="products/standard-booth.html">스탠다드 부스 보기 →</a>')}
  <div class="price-grid">
    <div><table class="ptable"><tbody>{''.join(rows)}</tbody></table></div>
    <figure class="pp-fig"><a href="products/standard-booth.html">{img_tag(cover(std, '4x5'), 0, '스탠다드 부스')}{render_tag(cover(std, '4x5'), large=True)}</a><figcaption>스탠다드 부스 · 1860 × 1860 × 2100mm</figcaption></figure>
  </div>
</div></section>
""")
    # 계산 예시 + 1년 비교
    a, b, c = (it[k]["amount"] for k in PR["rules"]["std_total"])
    exrows = []
    for e in PR["examples"]:
        U, M = e["units"], e["months"]
        parts = [man(a)]
        if U > 1:
            parts.append(f"{man(b)} × {U - 1}" if U > 2 else man(b))
        if M > 1:
            parts.append(f"{man(c)} × {U * (M - 1)}" if U * (M - 1) > 1 else man(c))
        exrows.append(f'<tr><th scope="row">{esc(e["label"])}</th><td class="calc">{" + ".join(parts)}</td><td>{amt_html_val(std_total(U, M))}</td></tr>')
    Y = PR["rules"]["year_months"]
    yc = PC["year_compare"]
    buy = it[PR["rules"]["year_buy"]]["amount"]
    out.append(f"""<section class="pp-examples" id="examples"><div class="wrap">
{sec_head('Examples', '대수·기간 계산 예시', f'스탠다드 부스 합계 = {man(a)} + {man(b)} × (대수 − 1) + {man(c)} × 대수 × (개월 − 1)')}
  <div class="price-grid">
    <div><table class="ptable ex-table"><thead><tr><th scope="col">구성</th><th scope="col">계산</th><th scope="col">합계</th></tr></thead><tbody>{''.join(exrows)}</tbody></table>
    <p class="muted">운임은 설치 장소에 따라 따로 안내해 드려요.</p></div>
    <div class="year">
      <b class="year-t">{esc(yc['title'])}</b>
      <p>{esc(yc['lead'])}</p>
      <div class="year-cmp">
        <div class="yc"><span>1년 렌탈 합계</span><b>{amt_html_val(std_total(1, Y))}</b><small>{man(a)} + {man(c)} × {Y - 1}</small></div>
        <div class="yc yc-buy"><span>{esc(yc['purchase']['label'])}</span><b>{amt_html_val(buy)}</b><small>한 번 결제</small></div>
      </div>
      <p>{esc(yc['conclusion'])}</p>
      <p class="muted">{esc(yc['footnote'])}</p>
    </div>
  </div>
</div></section>
""")
    out.append(wrap_section(depth))
    # 키오스크만
    wimg = cover(wood, "4x5")
    out.append(f"""<section class="pp-kiosk" id="kiosk"><div class="wrap">
{sec_head('Kiosk only', '포토키오스크 목재형 · 키오스크만 렌탈', '부스 없이 키오스크만 빌리고 싶다면 포토키오스크 목재형을 월 단위로 빌릴 수 있어요.', '<a class="ps-link" href="products/wood-kiosk.html">목재형 보기 →</a>')}
  <div class="price-grid">
    <div><table class="ptable"><tbody>
      <tr><th scope="row">{esc(it['wood_monthly']['label'])}<span class="pt-unit">{esc(it['wood_monthly']['unit'])}</span><ul class="inc">{''.join(f'<li>{esc(v)}</li>' for v in it['wood_monthly'].get('includes', []))}</ul></th><td>{amt_html('wood_monthly')}</td></tr>
      <tr><th scope="row">{esc(it['paper_700']['label'])}<span class="pt-unit">{esc(it['paper_700']['unit'])}</span></th><td>{amt_html('paper_700')}</td></tr>
    </tbody></table></div>
    <figure class="pp-fig pp-fig-sm"><a href="products/wood-kiosk.html">{img_tag(wimg, 0, '포토키오스크 목재형 CAD 3D 렌더')}{render_tag(wimg, large=True)}</a><figcaption>포토키오스크 목재형</figcaption></figure>
  </div>
</div></section>
""")
    # 협의 제품
    neg = PC["negotiable"]
    negp = [x for x in DETAIL if not PR["products"][x["slug"]].get("rental_summary") and x["slug"] != "photo-kiosk"]
    neg_links = "".join(f'<li><a href="products/{x["slug"]}.html">{esc(x["name"])}</a></li>' for x in negp)
    neg_links += '<li><a href="products.html#concepts">신규 컨셉 4종</a></li>'
    ask = "".join(f"<li>{esc(v)}</li>" for v in neg["ask_for"])
    out.append(f"""<section class="pp-neg" id="negotiable"><div class="wrap">
{sec_head('By quote', esc(neg['title']), esc(neg['body']))}
  <div class="price-grid">
    <div><ul class="neg-list">{neg_links}</ul><p class="muted">포토키오스크(일반) 단독 렌탈도 문의로 안내해 드려요.</p></div>
    <div class="ex-box"><b>문의할 때 알려주시면 빨라요</b><ul class="ask-list">{ask}</ul></div>
  </div>
</div></section>
""")
    # 구매
    pu = PC["purchase"]
    prow = []
    for row in pu["rows"]:
        k = row["key"]
        if k in it:
            prod = BYSLUG[row["products"][0]]
            prow.append(f'<tr><th scope="row"><a href="products/{prod["slug"]}.html">{esc(it[k]["label"])}</a></th><td>{amt_html(k)}</td></tr>')
        else:
            prow.append(f'<tr><th scope="row">{esc(row["item"])}</th><td><span class="ask">{esc(row["price"])}</span></td></tr>')
    out.append(f"""<section class="pp-purchase" id="purchase"><div class="wrap">
{sec_head('Purchase', '구매', esc(pu['desc']))}
  <div class="price-grid">
    <div><table class="ptable"><tbody>{''.join(prow)}</tbody></table><p class="muted">{esc(pu['note'])}</p></div>
    <div class="ex-box"><b>렌탈과 구매, 언제 무엇이 나을까</b><p>한두 달 행사라면 렌탈, 1년 가까이 두고 쓸 곳이라면 구매가 나아요. <a href="#examples">1년 비교 보기</a></p></div>
  </div>
</div></section>
""")
    sh = PC["shipping"]
    out.append(f"""<section class="pp-notes" id="notes"><div class="wrap">
{sec_head('Notes', '운임 · 부가세')}
  <div class="notes-grid">
    <div class="ex-box"><b>{esc(sh['title'])}</b><p>{esc(sh['body'])}</p></div>
    <div class="ex-box"><b>부가세</b><p>{esc(vat_sentence())}. 견적서에는 공급가와 부가세를 나눠 적어 드려요.</p></div>
  </div>
</div></section>

<section class="pp-faq" id="faq"><div class="wrap">
{sec_head('FAQ', '자주 묻는 질문')}
  <div class="faq ps-faq">
{faq_html(PC['faq'])}
  </div>
</div></section>
""")
    out.append(cta_band(depth, "구성이 정해지지 않았어도 괜찮아요. <i>견적부터 받아 보세요.</i>",
                        "장소·기간·대수를 알려주시면 24시간 안에 구성과 견적을 회신해 드려요."))
    out.append(body_close(depth))
    return "".join(out)


def amt_html_val(n):
    return f'<span class="amt">{esc(man(n))}</span>{vat_html()}'


# ───────────────────────── services 스텁 ─────────────────────────
def services_stub():
    m = {"kiosk": "products/photo-kiosk.html", "booth": "products/standard-booth.html", "theme": "products.html#lineup",
         "custom": "products/custom.html", "price": "pricing.html", "pricing": "pricing.html", "cost": "pricing.html",
         "process": "index.html#process", "contact": "index.html#contact"}
    return f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>루아미 서비스 안내가 가격 페이지로 옮겨졌어요</title>
<meta name="robots" content="noindex, follow">
<link rel="canonical" href="{BASE}/pricing.html">
<script>/* 옛 서비스 페이지 → 새 주소. 앵커가 있으면 대응 페이지로, 없으면 가격 페이지로 */
(function(){{var m={json.dumps(m, separators=(",", ":"))};var h=location.hash.slice(1);location.replace(m[h]||'pricing.html')}})();</script>
<meta http-equiv="refresh" content="0; url=pricing.html">
<link rel="icon" type="image/png" href="/favicon.png">
<style>body{{font-family:"Pretendard Variable",Pretendard,-apple-system,sans-serif;background:#F5F0DE;color:#1F2417;margin:0;padding:48px 24px;line-height:1.7}}a{{color:#2F5C43}}</style>
</head>
<body>
<p>서비스 안내는 <a href="pricing.html">가격 페이지</a>와 <a href="products.html">제품 페이지</a>로 옮겨졌어요. 잠시 후 자동으로 이동해요.</p>
</body>
</html>
"""


# ───────────────────────── 홈·가이드 GEN 블록 ─────────────────────────
def home_lineup():
    def sub(slug):
        m = PR["products"].get(slug) or {}
        v = vat_label()
        vs = f" <small>{esc(v)}</small>" if v else ""
        if m.get("rental_summary"):
            k = m["rental_summary"]
            return f"{esc(m.get('rental_summary_prefix', ''))} {esc(amt(k))}{vs}".strip()
        if m.get("purchase"):
            return f"구매 {esc(amt(m['purchase']))}{vs}"
        return esc(m.get("rental_text", ""))
    lis = []
    for prod in DETAIL:
        img = cover(prod, "thumb")
        badge = f'<span class="hl-badge hl-{prod.get("badge_kind", "main")}">{esc(prod["badge"])}</span>' if prod.get("badge") else ""
        no = "+" if prod["slug"] == "custom" else f"{prod['order']:02d}"
        lis.append(f'<li><a href="products/{prod["slug"]}.html"><span class="hl-im">{img_tag(img, 0, "")}{badge}{render_tag(img)}</span>'
                   f'<span class="hl-no">{no}</span><b>{esc(prod["name"])}</b><em>{sub(prod["slug"])}</em></a></li>')
    return f"""<div class="h-lineup" aria-labelledby="hlTitle">
    <div class="h-lineup-head"><h2 id="hlTitle" class="h-lineup-t">제품 {len(LINEUP)}종 <span>+ 커스텀 제작</span></h2><a href="products.html">제품 전체 보기 →</a></div>
    <ul class="h-lineup-list">{''.join(lis)}</ul>
  </div>"""


def home_prices():
    it = PR["items"]
    return f"""<section class="h-prices" id="prices" aria-labelledby="hpTitle"><div class="wrap">
  <div class="hp-in">
    <div class="hp-head"><span class="idxlabel">가격 한눈에</span><h2 id="hpTitle">정해진 가격, <i>바로 확인하세요</i></h2></div>
    <ul class="hp-list">
      <li><span class="hp-k">스탠다드 부스 렌탈 · 1개월 미만</span><span class="hp-v">{amt_html('std_short')}</span><span class="hp-d">4면 랩핑 · 인화지 1,400매 포함</span></li>
      <li><span class="hp-k">대수·기간 추가</span><span class="hp-v"><span class="amt">{esc(amt('std_extra_unit'))}</span><span class="hp-unit">/대</span></span><span class="hp-d">2개월차부터 부스당 {esc(amt('std_monthly'))}</span></li>
      <li><span class="hp-k">목재 키오스크만 렌탈</span><span class="hp-v">{amt_html('wood_monthly')}</span><span class="hp-d">인화지 700매 제공</span></li>
      <li><span class="hp-k">구매</span><span class="hp-v"><span class="amt">{esc(man(it['std_buy']['amount']))}부터</span>{vat_html()}</span><span class="hp-d">스탠다드 {esc(man(it['std_buy']['amount']))} · 목재형 {esc(man(it['wood_buy']['amount']))} · 포토키오스크 {esc(man(it['kiosk_buy']['amount']))}</span></li>
    </ul>
    <p class="hp-foot">미러·엘리베이터·지하철·원형 하이앵글 부스와 커스텀 제작은 기간·가격 협의 · 운임 별도 <a href="pricing.html">가격 자세히 →</a></p>
  </div>
</div></section>"""


def home_pbox():
    return f"""<h3>가격 한눈에</h3>
        <p>스탠다드 부스 1개월 미만 렌탈은 {esc(amt_text('std_short'))}이고, 촬영 키오스크·4면 랩핑·인화지 1,400매가 들어 있습니다. 대수와 기간이 늘면 정해진 기준으로 더해지고, 테마 부스와 커스텀 제작은 기간·가격을 협의합니다. 운임은 별도이며 상담만으로 비용이 발생하지 않습니다. <a href="pricing.html">가격 자세히 보기</a></p>"""


def home_faq_cost():
    return (f"스탠다드 부스는 1개월 미만 렌탈 {esc(amt_text('std_short'))}, 포토키오스크 목재형은 키오스크만 렌탈 월 "
            f"{esc(man_text(PR['items']['wood_monthly']['amount']))}입니다. 미러·엘리베이터·지하철·원형 하이앵글 부스는 기간과 구성에 따라 협의하며, "
            f"자세한 기준은 <a href=\"pricing.html\">가격 페이지</a>에 정리했습니다.")


def guide_prices():
    it = PR["items"]
    return f"""<aside class="g-price fade" aria-label="루아미 실제 가격 요약">
    <b class="g-price-t">루아미 실제 가격은?</b>
    <ul>
      <li>스탠다드 부스 1개월 미만 렌탈 <strong>{esc(amt_text('std_short'))}</strong> — 촬영 키오스크·4면 랩핑·인화지 1,400매 포함, 운임 별도</li>
      <li>2대째부터 1대마다 <strong>{esc(amt('std_extra_unit'))}</strong> · 2개월차부터 부스당 <strong>{esc(amt('std_monthly'))}</strong></li>
      <li>목재 키오스크만 렌탈 <strong>{esc(amt_text('wood_monthly'))}</strong> · 구매 <strong>{esc(man(it['std_buy']['amount']))}부터</strong></li>
    </ul>
    <a href="pricing.html" class="h-link-g">가격표 전체 보기 →</a>
  </aside>"""


def replace_gen(src, name, content, path):
    pat = re.compile(r"(<!-- GEN:%s -->)(.*?)(<!-- /GEN:%s -->)" % (re.escape(name), re.escape(name)), re.S)
    if not pat.search(src):
        raise SystemExit(f"{path}: GEN 마커 없음 — {name}")
    return pat.sub(lambda m: m.group(1) + content + m.group(3), src, count=1)


def sync_faq_jsonld(src):
    """홈 FAQ JSON-LD 를 화면의 FAQ(<details>)에서 다시 만든다 — 화면과 구조화 데이터가 갈라지지 않게."""
    block = re.search(r'<div class="faq h-faq">(.*?)</div>', src, re.S)
    if not block:
        return src
    qa = []
    for m in re.finditer(r"<details><summary>(.*?)</summary><p>(.*?)</p></details>", block.group(1), re.S):
        clean = lambda t: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", re.sub(r"<!--.*?-->", "", t, flags=re.S)))).strip()  # noqa: E731
        qa.append({"q": clean(m.group(1)), "a": clean(m.group(2))})
    obj = {"@context": "https://schema.org", "@type": "FAQPage",
           "mainEntity": [{"@type": "Question", "name": x["q"], "acceptedAnswer": {"@type": "Answer", "text": x["a"]}} for x in qa]}
    new = '<script type="application/ld+json">\n' + json.dumps(obj, ensure_ascii=False) + "\n</script>"
    return re.sub(r'<script type="application/ld\+json">\s*\{"@context": ?"https://schema.org", ?"@type": ?"FAQPage".*?</script>',
                  lambda m: new, src, count=1, flags=re.S)


def case_relprod(rel, src):
    names = []
    for prod in DETAIL:
        if rel in CM.get(prod["slug"], {}).get("cases", []):
            names.append(prod)
    if not names:
        return src
    links = " · ".join(f'<a href="../products/{p_["slug"]}.html">{esc(p_["name"])}</a>' for p_ in names)
    return re.sub(r'<p class="rel-prod fade">.*?</p>', lambda m: f'<p class="rel-prod fade">이 현장에 쓰인 제품 — {links}</p>', src, count=1, flags=re.S)


# ───────────────────────── sitemap ─────────────────────────
def update_sitemap(xml, changed_pages):
    pages_new = ["products.html", "pricing.html"] + [f"products/{x['slug']}.html" for x in DETAIL]
    xml = re.sub(r"\s*<url><loc>https://luamiphoto\.com/services\.html</loc>.*?</url>", "", xml, flags=re.S)
    for pg in pages_new:
        loc = f"https://luamiphoto.com/{pg}"
        pri = "0.9" if pg in ("products.html", "pricing.html") else "0.8"
        if f"<loc>{loc}</loc>" not in xml:
            line = f"  <url><loc>{loc}</loc><lastmod>{TODAY}</lastmod><changefreq>monthly</changefreq><priority>{pri}</priority></url>\n"
            xml = xml.replace("</urlset>", line + "</urlset>")
    for pg in changed_pages:
        loc = "https://luamiphoto.com/" + ("" if pg == "index.html" else pg)
        xml = re.sub(r"(<loc>%s</loc><lastmod>)[^<]*(</lastmod>)" % re.escape(loc), lambda m: m.group(1) + TODAY + m.group(2), xml)
    return xml


# ───────────────────────── 실행 ─────────────────────────
def chrome(rel, s):
    return unify_chrome.transform(pathlib.PurePosixPath(rel), s)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="쓰지 않고 바뀔 파일만 보고")
    ap.add_argument("--covers-from", help="3D 표지 폴더(<slug>_<variant>.jpg) → assets/images/covers/ 로 복사")
    a = ap.parse_args()

    if a.covers_from:
        src = pathlib.Path(a.covers_from)
        dst = ROOT / SITE["covers"]["dir"]
        n = 0
        for prod in DETAIL + CONCEPTS:
            for v in SITE["covers"]["variants"]:
                f = src / SITE["covers"]["pattern"].format(slug=prod["slug"], variant=v)
                if f.exists():
                    dst.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst / f.name)
                    n += 1
        print(f"표지 {n}개 복사 → {dst.relative_to(ROOT)}")

    outputs = {}
    outputs["products.html"] = chrome("products.html", hub_page())
    for i, prod in enumerate(DETAIL):
        outputs[f"products/{prod['slug']}.html"] = chrome(f"products/{prod['slug']}.html", detail_page(prod, i))
    outputs["pricing.html"] = chrome("pricing.html", pricing_page())
    outputs["services.html"] = chrome("services.html", services_stub())

    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    idx2 = replace_gen(idx, "home-lineup", home_lineup(), "index.html")
    idx2 = replace_gen(idx2, "home-prices", home_prices(), "index.html")
    idx2 = replace_gen(idx2, "home-pbox", home_pbox(), "index.html")
    idx2 = replace_gen(idx2, "home-faq-cost", home_faq_cost(), "index.html")
    outputs["index.html"] = sync_faq_jsonld(idx2)
    gd = (ROOT / "guide.html").read_text(encoding="utf-8")
    outputs["guide.html"] = replace_gen(gd, "guide-prices", guide_prices(), "guide.html")

    case_files = sorted(ROOT.glob("cases/*.html"))
    for f in case_files:
        rel = f"cases/{f.name}"
        outputs[rel] = case_relprod(rel, f.read_text(encoding="utf-8"))

    changed = []
    for rel, s in outputs.items():
        f = ROOT / rel
        old = f.read_text(encoding="utf-8") if f.exists() else None
        if old != s:
            changed.append(rel)
    # 생성 페이지·홈·가이드만 lastmod 갱신(사례 페이지는 제품 링크 줄만 바뀌므로 올리지 않는다 — 재크롤 flux 방지)
    bump = [r for r in changed if r in ("index.html", "guide.html", "products.html", "pricing.html") or r.startswith("products/")]
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    sm2 = update_sitemap(sm, bump)
    if sm2 != sm:
        changed.append("sitemap.xml")
        outputs["sitemap.xml"] = sm2

    if a.check:
        print("바뀔 파일:", ", ".join(changed) if changed else "없음")
        sys.exit(1 if changed else 0)
    for rel in changed:
        f = ROOT / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(outputs[rel], encoding="utf-8")
    fb = [p_["slug"] for p_ in DETAIL + CONCEPTS if not cover_path(p_["slug"], "4x5")]
    print(f"갱신 {len(changed)}개: " + (", ".join(changed) if changed else "없음"))
    print(f"3D 표지 없음 → 대체 이미지 사용: {', '.join(fb) if fb else '없음'}")
    missing_cases = [f.name for f in case_files if not any(f"cases/{f.name}" in CM.get(p_['slug'], {}).get('cases', []) for p_ in DETAIL)]
    if missing_cases:
        print("content_map 에 제품이 없는 사례(제품 줄 그대로 둠): " + ", ".join(missing_cases))


if __name__ == "__main__":
    main()
