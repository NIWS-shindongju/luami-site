#!/usr/bin/env python3
"""제품 허브·제품 상세·가격 페이지 생성기 (루아미, 2026-10-04 라인업)

입력(전부 data/):
  products.json      제품 정의(순서·이름·배지·하이앵글·표지 규칙·옛 앵커)
  prices.json        가격 단일 출처 + 부가세 표기 스위치(vat.mode)
  copy/<slug>.json   제품 카피 / copy/pricing.json 가격 페이지 카피
  gallery.json       제품별 사례 사진 / wrap.json 4면 랩핑 사진
  content_map.json   제품별 블로그·사례 페이지

출력(정적 HTML — GitHub Pages 가 그대로 서빙):
  products.html               제품 허브(주력 모델 · 7종 그리드 · 커스텀 · 신규 컨셉)
  products/<slug>.html        제품 상세 8장(7종 + 커스텀)
  pricing.html                렌탈·구매 가격
  services.html               스텁(noindex · canonical/refresh → pricing.html · 옛 앵커 JS 매핑)
  index.html · guide.html     <!-- GEN:이름 --> … <!-- /GEN:이름 --> 사이만 갈아 끼움
  cases/*.html                "이 현장에 쓰인 제품" 줄을 content_map 기준으로 갱신
  sitemap.xml                 새 페이지 추가 · services·없어진 페이지 제거 · 본문이 바뀐 페이지 lastmod = 오늘
                              (판정은 site-gate.js --stale-lastmod-json 과 같은 규칙: 메뉴·푸터·버전 쿼리만 바뀐 건 제외)

3D 표지: assets/images/covers/<slug>_<variant>.jpg 가 생기면 다음 빌드부터 자동으로 쓴다.
  표지가 없으면 products.json 의 fallback(제품당 경로 한 줄). fallback 이 렌더인데 이미지 안에 'CAD 3D 렌더'
  글자가 없으면 "baked_label": false 로 두면 큰 자리에서도 화면 위 표기를 얹는다.
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
    """금액 표기 + 가격표 연결 표식(data-price-key). site-gate.js 가 표식이 붙은 글자 금액을 prices.json 의 그 항목과 대조한다."""
    lead = f"{esc(lead)} " if lead else ""
    return f'<span class="amt" data-price-key="{key}">{lead}{esc(amt(key))}</span>{vat_html()}'


def amt_text(key):
    v = vat_label()
    return amt(key) + (f"({v})" if v else "")


def man_text(n):
    v = vat_label()
    return man(n) + (f"({v})" if v else "")


def tmpl(s):
    """{price:key} → '185만원(부가세 별도)', '({vat})' → '(부가세 별도)' 또는 '' (표기 안 함 모드).
    {man:key} → '185만원'(월·+ 접두·부가세 없이 금액만, 계산식 안에서), {total:대수:개월} → 스탠다드 합계 '275만원'."""
    s = re.sub(r"\{price:([a-z0-9_]+)\}", lambda m: amt_text(m.group(1)), s)
    s = re.sub(r"\{man:([a-z0-9_]+)\}", lambda m: man(PR["items"][m.group(1)]["amount"]), s)
    s = re.sub(r"\{total:(\d+):(\d+)\}", lambda m: man(std_total(int(m.group(1)), int(m.group(2)))), s)
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


# ───────────────────────── 포함/별도 2열 · 요인 카드 · 설치 조건 (BRIEF 2-2 #2·#4·#6, 2-3 #2·#3·#5) ─────────────────────────
def inc_li(x):
    """'가격에 포함' 목록 한 줄. data-item = prices.json includes 원문(site-gate 의 포함 목록 대조용)."""
    return f'<li data-item="{esc(x)}"><span class="ie-ck" aria-hidden="true"></span><span>{esc(x)}</span></li>'


def sep_li(s):
    """'별도' 목록 한 줄 — 금액이 있으면 prices.json 항목(key)에서, 없으면 안내 문구."""
    lab = esc(s["label"]) + (f' <small>{esc(s["unit"])}</small>' if s.get("unit") else "")
    if s.get("key"):
        note = f'<span class="ie-n">{esc(s["note"])}</span>' if s.get("note") else ""
        val = amt_html(s["key"])
    else:
        note = ""
        val = f'<span class="ie-ask">{esc(s.get("note", ""))}</span>'
    return f'<li><span class="ie-l">{lab}{note}</span><span class="ie-r">{val}</span></li>'


def package_card(slug):
    """정가 제품 가격 카드: 큰 금액 + 포함 ✓ / 별도 2열(한 목록에 섞지 않음) + (스탠다드) 계산 예시 문장."""
    m = PR["products"][slug]
    base = m["rental_summary"]
    it = PR["items"][base]
    inc = "".join(inc_li(x) for x in it.get("includes", []))
    sep = "".join(sep_li(s) for s in m.get("separate", []))
    # 포함인지 별도(추가 비용)인지 사양서에 없는 조건은 어느 목록에도 넣지 않고 '상담 때 안내' 한 줄로(R11: 확인 안 된 표현 금지)
    ask = "".join(f'<p class="pkg-ask"><b>상담 때 안내</b> {esc(a["label"])} — {esc(a["note"])}</p>' for a in m.get("ask", []))
    calc = ""
    if base == PR["rules"]["std_total"][0]:
        a, b, c = (PR["items"][k]["amount"] for k in PR["rules"]["std_total"])
        v = vat_label()
        calc = (f'<p class="pkg-calc">첫 1대 {man(a)} · 2대째부터 1대마다 +{man(b)} · 두 번째 달부터 부스마다 매달 +{man(c)}. '
                f'2대면 {man(std_total(2, 1))}, 3대면 {man(std_total(3, 1))}' + (f'({esc(v)})' if v else '') + '입니다.</p>')
    unit = " · ".join(x for x in [it.get("unit", ""), "한 달 단위" if it.get("per") == "월" else ""] if x)
    return f"""<div class="pkg" data-package="{slug}">
      <div class="pkg-head"><div class="pkg-name"><span class="pkg-k">{esc(it['label'])}</span><span class="pkg-u">{esc(unit)}</span></div><div class="pkg-v">{amt_html(base)}</div></div>
      <div class="ie-grid">
        <div class="ie ie-in"><b class="ie-t">가격에 포함</b><ul class="ie-list" data-list="included">{inc}</ul></div>
        <div class="ie ie-out"><b class="ie-t">별도</b><ul class="ie-list" data-list="separate">{sep}</ul></div>
      </div>
      {ask}{calc}
    </div>"""


def hero_ie(slug):
    """상세 첫 화면 가격 상자 안 '포함 / 별도' 두 줄 — 얼마·포함·어떻게를 첫 화면에(BRIEF 2-2 #1)."""
    m = PR["products"].get(slug) or {}
    if not m.get("rental_summary"):
        return ('<div class="pb-ie"><span class="pb-k">견적</span><span class="pb-sep">장소·기간·용도·대수를 알려 주시면 '
                '24시간 안에 구성과 견적을 보내 드립니다 · <a href="#price">가격을 정하는 요소</a></span></div>')
    inc = PR["items"][m["rental_summary"]].get("includes", [])
    lis = "".join(f'<li data-item="{esc(x)}">{esc(x)}</li>' for x in inc)
    sep = m.get("hero_separate", "")
    return (f'<div class="pb-ie"><span class="pb-k">포함</span><ul class="pb-inc" data-list="included">{lis}</ul></div>'
            + (f'<div class="pb-ie"><span class="pb-k">별도</span><span class="pb-sep">{esc(sep)}</span></div>' if sep else "")
            + (f'<div class="pb-ie"><span class="pb-k">상담</span><span class="pb-sep">{esc(m["hero_ask"])}</span></div>' if m.get("hero_ask") else ""))


def factor_cards():
    """협의 제품 '가격에 영향을 주는 요소' 카드(범위 금액은 넣지 않음 — 가격 정책은 동주님 결정)."""
    neg = PC["negotiable"]
    cards = "".join(f'<li class="fx"><span class="fx-no">{i + 1:02d}</span><b>{esc(f["title"])}</b><p>{esc(f["body"])}</p></li>'
                    for i, f in enumerate(neg["factors"]))
    return (f'<div class="fx-wrap"><b class="fx-t">{esc(neg["factors_title"])}</b><p class="fx-lead">{esc(neg["factors_lead"])}</p>'
            f'<ul class="fx-grid">{cards}</ul></div>')


def install_table(prod):
    """설치 조건 표 — 아는 값만. 값이 빈 행은 만들지 않고, 행이 하나도 없으면 표 자체를 그리지 않는다."""
    ins = prod.get("install") or {}
    rows = [(lab, (ins.get(k) or "").strip()) for k, lab in SITE.get("install_fields", {}).items() if not k.startswith("_")]
    rows = [(a, b) for a, b in rows if b]
    if not rows:
        return ""
    trs = "".join(f'<tr><th scope="row">{esc(a)}</th><td>{esc(b)}</td></tr>' for a, b in rows)
    note = f'<p class="ins-note">{esc(ins["note"])}</p>' if (ins.get("note") or "").strip() else ""
    return (f'<div class="ins"><b class="ins-t">설치 조건</b><table class="ins-table" data-table="install"><tbody>{trs}</tbody></table>'
            f'{note}<p class="ins-note">표에 없는 조건(전원·설치 시간 등)은 설치 장소를 확인한 뒤 안내해 드립니다.</p></div>')


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


def cover_hidden(slug, variant):
    return variant in (SITE["covers"].get("hide", {}).get(slug) or [])


def cover_path(slug, variant):
    c = SITE["covers"]
    if cover_hidden(slug, variant):
        return None
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
            "w": w, "h": h, "is_cover": False, "baked_label": fb.get("baked_label", True)}


def cover_alt(prod, img):
    if img is None:
        return prod["name"]
    if img.get("is_cover"):
        return f"{prod['name']} — CAD 3D 렌더"
    for it in G.get(prod["slug"], []):
        if img["src"] in (it["src"], it.get("thumb")):
            return it["alt"]
    if img.get("kind") == "render":
        return f"{prod['name']} — CAD 3D 렌더"
    return prod["name"]


def u(rel, depth):
    return "../" * depth + rel


def render_tag(img, large=False):
    """'CAD 3D 렌더' 표기 보장.
    - 3D 표지(covers/)는 이미지 안 표기 여부를 모르므로 화면 위에 표기를 얹는다.
    - 갤러리 렌더(data/gallery.json·wrap.json)는 우하단에 표기가 박혀 있지만 썸네일에선 글자가 작다 →
      contain 으로 통째로 보여 주고(img_tag, 박힌 표기가 잘리지 않게) 왼쪽에 읽히는 크기로 한 번 더 얹는다."""
    if img and img.get("kind") == "mockup":  # 랩핑 디자인 목업(사진 아님) — 화면 위에 표기
        return f'<span class="render-tag">{esc(img.get("label", "디자인 목업"))}</span>'
    if not img or img.get("kind") != "render":
        return ""
    if large and not img.get("is_cover") and img.get("baked_label", True):
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
    """상세 사진 묶음 — 실사(설치·행사 → 디테일) 먼저, 그다음 3D 표지 보조 각도, 그다음 나머지 렌더·출고 전.
    첫 화면 표지가 이미 3D 렌더라 갤러리는 실제 현장 사진으로 시작한다(실사가 없는 제품은 렌더가 맨 앞)."""
    hide = set(SITE.get("gallery_hide_scenes") or [])
    items = []
    for v, vname in (("angle1", "정면"), ("angle2", "다른 방향"), ("angle3", "높은 시점")):
        rel = cover_path(slug, v)
        if rel:
            w, h = dims(rel)
            items.append({"src": rel, "thumb": rel, "w": w, "h": h, "kind": "render", "scene": "render", "is_cover": True,
                          "alt": f"{BYSLUG[slug]['name']} CAD 3D 렌더 — {vname}", "caption": f"CAD 3D 렌더 · {vname}"})
    for ex in SITE["covers"].get("extra", {}).get(slug, []):
        rel = cover_path(slug, ex["variant"])
        if rel:
            w, h = dims(rel)
            items.append({"src": rel, "thumb": rel, "w": w, "h": h, "kind": "render", "scene": "render", "is_cover": True,
                          "alt": ex["alt"], "caption": ex["caption"]})
    items += [x for x in G.get(slug, []) if x.get("scene") not in hide]
    ranked = sorted(enumerate(items), key=lambda t: (SCENE_RANK.get(t[1].get("scene"), 1), not t[1].get("is_cover"), t[0]))
    return [x for _, x in ranked]


def visible_caption(it, tagged):
    cap = it.get("caption", "")
    if tagged:
        cap = re.sub(r"^\s*(CAD 3D 렌더|디자인 목업)\s*(·\s*)?", "", cap)
    return cap


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
    # 줄 단위 마스크(<span class="lm">)·<br> 경계만 띄어 쓰고, 강조(<i>) 같은 나머지 태그는 그냥 지운다
    # (예전: 모든 태그 → 공백 → '바로 위<i>에서</i>' 가 '바로 위 에서' 로 갈라졌다, V2 M6)
    title = re.sub(r"<[^>]+>", "", re.sub(r'<br\s*/?>|<span class="lm">', " ", h1.group(1))) if h1 else ""
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


STYLE_V = "20261012a"


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
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css">
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
{unify_chrome.UTIL}
<header class="nav"></header>

<div class="drawer-scrim" id="drawerScrim" aria-hidden="true"></div>
<div class="stickybar" id="sbar">
  <a href="{pre}index.html" class="logo">Luami<span class="dot"></span></a>
  <a href="{pre}index.html#contact" class="btn-mini">무료 견적</a>
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
    <a href="{KAKAO}" target="_blank" rel="noopener" class="kakao">카톡으로 바로 상담</a><a href="{TEL}">전화 010-3629-7743</a><a href="{pre}index.html#contact">무료 견적 받기</a>
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
  <text x="160" y="20" class="lbl" text-anchor="middle">천장 가운데 카메라</text>"""
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
    num = "맞춤 제작" if is_custom else f"제품 {prod['order']:02d} / {len(LINEUP):02d}"
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
    gword = "사진" if n_photo else "이미지"
    if gal:
        jl.append(f'<a href="#gallery">{gword} {len(gal)}장</a>')
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
      <span class="idxlabel">{num}</span>
      <h1>{esc(prod['name'])}</h1>
      <p class="pd-tagline">{esc(c['tagline'])}</p>
      <div class="pd-chips">{chips}{''.join(count_chips)}</div>
      <p class="pd-lead">{esc(c['hero'])}</p>
      <div class="pricebox">
        {price_rows}
        {hero_ie(slug)}
        <p class="pb-note">{esc(ship + ' · ' if has_fixed_price(slug) and not PR['products'].get(slug, {}).get('hero_separate') else '')}<a href="#price">가격 조건 보기</a> · <a href="{pre}pricing.html">전체 가격표</a></p>
      </div>
      {hero_jump}
      <div class="pd-cta"><a class="btn" href="{pre}index.html#contact">무료 견적 받기 <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14M13 6l6 6-6 6"/></svg></a><a class="btn-ghost" href="{KAKAO}" target="_blank" rel="noopener">카톡으로 바로 상담</a></div>
    </div>
  </div>
</div></section>
""")

    # 끌리는 포인트
    pts = "\n".join(f'    <li><b>{esc(a["title"])}</b><span>{esc(a["body"])}</span></li>' for a in c["appeal"])
    out.append(f"""<section class="pd-points"><div class="wrap">
{sec_head('장점', '이런 점이 좋습니다')}
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
    <span class="idxlabel">촬영 구도</span>
    <h2>{esc(ht['title'])}</h2>
    <p>{esc(ht['body'])}</p>
    <p class="ha-note">구조를 설명하는 그림입니다. 실제 크기와 각도는 부스마다 다릅니다.</p>
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
            tag = render_tag(it)
            vcap = visible_caption(it, bool(tag))
            span = " pg-wide" if i == 0 else (" pg-w2" if i >= len(gal) - k else "")
            cells.append(
                f'    <a class="pg-item{span}" href="{u(it["src"], depth)}" data-w="{it["w"]}" data-h="{it["h"]}" data-caption="{esc(cap)}">'
                f'<img src="{u(it["src"] if i == 0 else (it.get("thumb") or it["src"]), depth)}" width="{it["w"] if i == 0 else tw}" height="{it["h"] if i == 0 else th}" alt="{esc(it["alt"])}" loading="lazy" decoding="async"{contain_style(it)}>'
                f'{tag}' + (f'<span class="pg-cap">{esc(vcap)}</span>' if vcap else '') + '</a>')
        note = f"{gword}을 누르면 크게 볼 수 있습니다." if n_photo else "이미지를 누르면 크게 볼 수 있습니다."
        if n_render and not n_photo:
            note += " 아직 실물 사진이 없어 설계 3D 이미지(CAD 3D 렌더)로 보여 드립니다."
        elif n_render:
            note += " 실제 사진이 아닌 설계 3D 이미지에는 ‘CAD 3D 렌더’라고 표시했습니다."
        out.append(f"""<section class="pd-gallery" id="gallery"><div class="wrap">
{sec_head(f'{gword} {len(gal)}장', f'{gword}으로 보기' if n_photo else '3D 이미지로 보기', note)}
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
    <span class="idxlabel">추천 용도</span>
    <h2>이런 곳에 잘 맞습니다</h2>
    <ul class="fit-list">{fit}</ul>
    {install_table(prod) or f'<div class="spec-note"><b>크기·구조</b><p>{esc(c["specs_note"])}</p></div>'}
  </div>
  <div>
    <span class="idxlabel">진행 순서</span>
    <h2>이렇게 진행됩니다</h2>
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
{sec_head('사례', '이 제품이 쓰인 사례·이야기', ' · '.join(x for x in [f'사례 {n_case}개' if n_case else '', f'블로그 {n_blog}편' if n_blog else ''] if x) + '을 모았습니다.')}
  <div class="st-grid">{''.join(card(x) for x in first)}</div>
  {more}
</div></section>
""")

    # 가격
    out.append(detail_price_section(slug, depth))

    # FAQ
    out.append(f"""<section class="pd-faq" id="faq"><div class="wrap">
{sec_head('궁금한 점', '자주 묻는 질문')}
  <div class="faq ps-faq">
{faq_html(c['faq'])}
  </div>
</div></section>
""")

    out.append(cta_band(depth, f"{esc(prod['name'])}, <i>견적부터 받아 보세요.</i>",
                        "장소·날짜·대수를 알려 주시면 24시간 안에 구성과 견적을 보내 드립니다. 상담·견적은 무료입니다."))

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
    body = ""
    if m.get("rental_summary"):
        body += package_card(slug)
    if m.get("purchase"):
        k = m["purchase"]
        body += (f'<table class="ptable pt-buy"><tbody><tr><th scope="row">구매 · {esc(PR["items"][k]["label"])}'
                 f'<span class="pt-unit">한 번 결제</span></th><td>{amt_html(k)}</td></tr></tbody></table>')
    if not m.get("rental"):
        body += f'<div class="ask-box"><div class="pb-row"><span class="pb-k">렌탈</span><span class="pb-v"><span class="ask">{esc(m["rental_text"])}</span></span></div>'
        if not m.get("purchase"):
            body += f'<div class="pb-row"><span class="pb-k">구매</span><span class="pb-v"><span class="ask">{esc(m["purchase_text"])}</span></span></div>'
        body += "</div>"
    extra = ""
    if slug == "standard-booth":
        ex = "".join(f'<li><span>{esc(e["label"])}</span><span>{amt_html_val(std_total(e["units"], e["months"]), (e["units"], e["months"]))}</span></li>'
                     for e in PR["examples"])
        extra = f'<div class="ex-box"><b>계산 예시</b><ul class="ex-list">{ex}</ul><p>1년 가까이 쓰실 계획이라면 구매를 권해 드립니다. <a href="{pre}pricing.html#examples">계산 기준 보기</a></p></div>'
    elif has_fixed_price(slug):
        extra = (f'<div class="ex-box"><b>렌탈과 구매, 어느 쪽이 나을까요</b><p>한두 달 쓰실 곳이라면 렌탈, 1년 가까이 두고 쓰실 곳이라면 '
                 f'구매를 권해 드립니다. <a href="{pre}pricing.html#purchase">구매가 보기</a></p></div>')
    if not has_fixed_price(slug):
        ask = "".join(f"<li>{esc(x)}</li>" for x in PC["negotiable"]["ask_for"])
        extra += f'<div class="ex-box"><b>이 4가지를 알려 주시면 견적이 빨라집니다</b><ul class="ask-list">{ask}</ul></div>'
    factors = "" if has_fixed_price(slug) else f'\n  {factor_cards()}'
    notes = []
    if PR["products"].get(slug, {}).get("rental"):
        notes.append(PR.get("shipping_note", ""))
    notes.append(vat_sentence())
    return f"""<section class="pd-price" id="price"><div class="wrap">
{sec_head('렌탈·구매', '가격', ' · '.join(x for x in notes if x), f'<a class="ps-link" href="{pre}pricing.html">전체 가격표 →</a>')}
  <div class="price-grid">
    <div>{body}</div>
    <div>{extra}</div>
  </div>{factors}
</div></section>
"""


def vat_sentence():
    mode = PR["vat"]["mode"]
    if mode == "excluded":
        return "표시한 금액은 모두 부가세 별도입니다"
    if mode == "included":
        return "표시한 금액은 모두 부가세 포함입니다"
    return "부가세는 상담 때 안내해 드립니다"


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
{sec_head('4면 랩핑', esc(w['title']) + ' — <i>렌탈에 포함</i>', esc(w['lead']), f'<a class="ps-link" href="{pre}pricing.html#wrap">랩핑 자세히 →</a>')}
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
{sec_head('4면 랩핑', esc(w['title']) + ' — <i>스탠다드 부스 렌탈에 포함</i>', esc(w['lead']))}
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
            "function norm(){var h=location.hash.slice(1);if(/^(p-)?[ab]\\d\\d$/i.test(h)&&!/^p-[ab]\\d\\d$/.test(h))"
            "history.replaceState(null,'','#p-'+h.replace(/^p-/i,'').toLowerCase())}"
            "norm();addEventListener('hashchange',norm);"
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
    sep_line = ""
    if pk.get("rental_summary") and PR["items"][pk["rental_summary"]].get("includes"):
        # 포함 목록에는 포함만(BRIEF R5: 포함과 별도를 한 목록에 섞지 않는다). 별도는 아래 한 줄로 따로.
        hl_html = "".join(f'<li data-item="{esc(x)}">{esc(x)}</li>' for x in PR["items"][pk["rental_summary"]]["includes"])
        hl_title = "렌탈 가격에 포함"
        hl_attr = ' data-list="included"'
        if pk.get("hero_separate"):
            sep_line = f'<p class="fc-sep"><b>별도</b> {esc(pk["hero_separate"])}</p>'
        if pk.get("hero_ask"):
            sep_line += f'<p class="fc-sep"><b>상담</b> {esc(pk["hero_ask"])}</p>'
    else:
        hl_html = "".join(f"<li>{esc(a['title'])}</li>" for a in c["appeal"][:4])
        hl_title = "이런 점이 좋습니다"
        hl_attr = ""
    rows = "".join(f'<div class="pb-row"><span class="pb-k">{a}</span><span class="pb-v">{b}</span></div>' for a, b, _ in price_of(prod["slug"]))
    is_r = img and img.get("kind") == "render"
    fc_cls = "is-render" if is_r else ""
    fc_bg = f' style="--fc-bg:{edge_color(img["src"])}"' if is_r else ""  # 좁은 화면에서 렌더를 통째로 보일 때 여백 색
    return f"""    <article class="fc">
      <a class="fc-im" href="products/{prod['slug']}.html" tabindex="-1" aria-hidden="true"{fc_bg}>{img_tag(img, 0, cover_alt(prod, img), cls=fc_cls)}{render_tag(img, large=True)}</a>
      <div class="fc-body">
        <div class="pc-chips"><span class="badge badge-{prod.get('badge_kind', 'main')}">{esc(prod['badge'])}</span><span class="fc-no">{prod['order']:02d} / {len(LINEUP):02d}</span></div>
        <h3><a href="products/{prod['slug']}.html">{esc(prod['name'])}</a></h3>
        <p class="fc-tag">{esc(c['tagline'])}</p>
        <b class="fc-hl-t">{hl_title}</b>
        <ul class="fc-hl"{hl_attr}>{hl_html}</ul>{sep_line}
        <div class="pricebox fc-price">{rows}</div>
        <div class="fc-cta"><a class="btn" href="products/{prod['slug']}.html">자세히 보기</a><a class="btn-ghost" href="index.html#contact">무료 견적 받기</a></div>
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
        <div class="pc-chips"><span class="badge badge-line">신규 컨셉 · 제작 가능 · 실물 미제작</span>{ha}</div>
        <h3>{esc(cp['name'])}</h3>
        <p class="pc-tag">{esc(tag)}</p>
        <ul class="cc-pts">{pts}</ul>
        <p class="cc-fit"><b>어울리는 곳</b> {' · '.join(esc(x) for x in c['fit'][:3])}</p>
        <p class="cc-price"><span class="ask">{esc(PR['products']['_concept']['rental_text'])}</span></p>
      </div>
    </article>"""


def hub_page():
    h = P["hub"]
    feat = [BYSLUG["standard-booth"], BYSLUG["photo-kiosk"]]
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
    # 옛 허브는 같은 제품에 대문자 별칭 id(#A01·#B04)도 있었다 — JS 없이 와도 목록 위치로 떨어지게 별칭 자리도 둔다
    old_ids = [a for prod in DETAIL for a in prod.get("legacy_anchors", [])] + P["unmapped_anchors"]
    anchors += "".join(f'<span id="{a[2:].upper()}" class="legacy-anchor" aria-hidden="true"></span>' for a in old_ids)
    out.append(f"""
<section class="page-head ph-head"><div class="wrap">
  <span class="idxlabel">제품 {len(LINEUP)}종 + 커스텀</span>
  <h1>포토부스·포토키오스크 전체 제품</h1>
  <p>{esc(h['lead'])}</p>
  <p class="legacy-note" role="status">찾으신 제품은 현재 목록에서 빠졌습니다. 비슷한 구성은 <a href="products/custom.html">커스텀 제작</a>으로 상담해 드립니다.</p>
  <nav class="jump" aria-label="이 페이지 바로가기"><a href="#featured">주력 모델</a><a href="#lineup">제품 {len(LINEUP)}종</a><a href="#custom">커스텀 제작</a><a href="#concepts">신규 컨셉</a><a href="pricing.html">가격표</a></nav>
</div></section>
{anchors}
<section class="ph-featured" id="featured"><div class="wrap">
{sec_head('주력', '주력 제품', '스탠다드 부스와 포토키오스크는 표의 가격 그대로 바로 진행할 수 있습니다. 스탠다드 부스 렌탈에는 촬영 키오스크(부스 안에서 찍고 출력하는 기계)·4면 랩핑(겉면 네 면에 행사 디자인을 인쇄해 붙이는 것)·인화지(사진 출력 용지)·설치·회수(행사 후 철거해 가져감)가 들어 있습니다.')}
  <div class="fc-grid">
{chr(10).join(featured_card(x) for x in feat)}
  </div>
</div></section>

<section class="ph-lineup" id="lineup"><div class="wrap">
{sec_head(f'전체 {len(LINEUP)}종', f'제품 {len(LINEUP)}종', '‘하이앵글’은 카메라가 위에서 내려다보며 찍는 부스입니다. 정해진 가격이 있는 제품만 보려면 ‘정가 제품’을 누르세요.')}
  <div class="filters" role="group" aria-label="제품 골라 보기">
    <button type="button" class="fchip" data-filter="" aria-pressed="true">전체 <b>{counts['all']}</b></button>
    <button type="button" class="fchip" data-filter="price" aria-pressed="false">정가 제품 <b>{counts['price']}</b></button>
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
    <span class="idxlabel">커스텀</span>
    <h2>목록에 없는 모양도 <i>만들어 드립니다</i></h2>
    <p>{esc(cc['hero'])}</p>
    <ul class="cu-list">{scopes}</ul>
    <p class="cu-price"><span class="pb-k">가격</span> <span class="ask">{esc(PR['products']['custom']['rental_text'])}</span></p>
    <div class="fc-cta"><a class="btn" href="products/custom.html">커스텀 제작 자세히 보기</a><a class="btn-ghost on-dark" href="index.html#contact">제작 상담 받기</a></div>
  </div>
  <div class="cu-mosaic" data-gallery="custom-hub">{mos_html}</div>
</div></section>
""")
    out.append(f"""<section class="ph-concepts" id="concepts"><div class="wrap">
{sec_head('신규 컨셉', f'새로 제안하는 부스 {len(CONCEPTS)}종', '아직 실물로 만든 적은 없는 새 부스입니다. 그림은 설계 3D 이미지(CAD 3D 렌더)이고, 크기·구성·기간·가격은 상담 때 함께 정합니다.', '<a class="ps-link" href="blog/new-concepts-story.html">컨셉 이야기 읽기 →</a>')}
  <div class="cc-grid">
{chr(10).join(concept_card(x) for x in CONCEPTS)}
  </div>
</div></section>

<section class="ph-faq" id="faq"><div class="wrap">
{sec_head('궁금한 점', '자주 묻는 질문')}
  <div class="faq ps-faq">
{faq_html(h['faq'])}
  </div>
</div></section>
""")
    out.append(cta_band(0, "어떤 제품이 맞을지 고민이라면, <i>장소·기간·인원만 알려주세요.</i>",
                        "현장에 맞는 제품과 대수를 골라 24시간 안에 견적과 함께 보내 드립니다."))
    out.append(body_close(0))
    return "".join(out)


# ───────────────────────── 가격(pricing.html) ─────────────────────────
def pricing_page():
    pg = PC["page"]
    depth = 0
    lds = [breadcrumb([("홈", ""), ("가격", "pricing.html")]), faq_ld(PC["faq"])]
    desc = tmpl("스탠다드 부스 1개월 미만 렌탈 {price:std_short} — 촬영 키오스크·4면 랩핑·인화지 1,400매·설치·회수 포함(운송비 별도). "
                "포토키오스크만 렌탈 {price:wood_monthly}, 인화지 700매 포함. 구매가 스탠다드 부스 {price:std_buy}, 포토키오스크 {price:wood_buy}. 루아미 렌탈·구매 가격표.")
    og = cover(BYSLUG["standard-booth"], "1x1") or {"src": WRAP["hero"]["src"]}
    out = [head("포토부스 렌탈·구매 가격 | 스탠다드 부스 · 포토키오스크 — 루아미", desc,
                "포토부스 렌탈 가격,포토부스 렌탈 비용,포토부스 대여 비용,포토부스 구매,포토키오스크 가격,포토부스 랩핑,루아미",
                "pricing.html", og["src"], depth, lds), body_open(depth, "pp")]
    it = PR["items"]
    std = BYSLUG["standard-booth"]
    kiosk = BYSLUG["photo-kiosk"]
    buy_min = min(it[k]["amount"] for k in it if it[k]["kind"] == "purchase")
    buy_min_key = [k for k in it if it[k]["kind"] == "purchase" and it[k]["amount"] == buy_min][0]
    out.append(f"""
<section class="page-head pp-head"><div class="wrap">
  <span class="idxlabel">가격</span>
  <h1>{esc(pg['h1'])}</h1>
  <p>{esc(pg['lead'])}</p>
  <div class="sum-grid">
    <a class="sum" href="#rental"><span class="sum-k">스탠다드 부스 렌탈 · 1개월 미만</span><span class="sum-v">{amt_html('std_short')}</span><span class="sum-d">4면 랩핑·인화지 1,400매·설치·회수 포함 · 운송비 별도</span></a>
    <a class="sum" href="#kiosk"><span class="sum-k">포토키오스크 · 키오스크만</span><span class="sum-v">{amt_html('wood_monthly')}</span><span class="sum-d">인화지 700매 포함 · 한 달 단위</span></a>
    <a class="sum" href="#purchase"><span class="sum-k">구매</span><span class="sum-v"><span class="amt" data-price-key="{buy_min_key}">{esc(man(buy_min))}부터</span>{vat_html()}</span><span class="sum-d">{esc(it[buy_min_key]['label'])} 기준 · 제품별 구매가는 아래 표</span></a>
  </div>
  <nav class="jump" aria-label="이 페이지 바로가기"><a href="#rental">렌탈</a><a href="#examples">계산 예시</a><a href="#wrap">4면 랩핑</a><a href="#kiosk">키오스크만</a><a href="#negotiable">협의 제품</a><a href="#purchase">구매</a><a href="#notes">운송비·부가세</a><a href="#faq">자주 묻는 질문</a></nav>
</div></section>
""")
    # 렌탈 — 스탠다드 부스 가격 카드(큰 금액 + 포함/별도 2열 + 계산 예시 문장, BRIEF 2-3 #2)
    r = PC["rental"]
    out.append(f"""<section class="pp-rental" id="rental"><div class="wrap">
{sec_head('렌탈', '스탠다드 부스 렌탈', esc(r['desc']), f'<a class="ps-link" href="products/standard-booth.html">스탠다드 부스 보기 →</a>')}
  <div class="price-grid">
    <div>{package_card('standard-booth')}</div>
    <figure class="pp-fig"><a href="products/standard-booth.html">{img_tag(cover(std, '4x5'), 0, '스탠다드 부스')}{render_tag(cover(std, '4x5'), large=True)}</a><figcaption>스탠다드 부스 · 가로·세로 1.86m, 높이 2.1m</figcaption></figure>
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
        exrows.append(f'<tr><th scope="row">{esc(e["label"])}</th><td class="calc">{" + ".join(parts)}</td><td>{amt_html_val(std_total(U, M), (U, M))}</td></tr>')
    Y = PR["rules"]["year_months"]
    yc = PC["year_compare"]
    buy = it[PR["rules"]["year_buy"]]["amount"]
    out.append(f"""<section class="pp-examples" id="examples"><div class="wrap">
{sec_head('계산 예시', '대수·기간별 금액', f'첫 1대 {man(a)} · 2대째부터 1대마다 +{man(b)} · 두 번째 달부터 부스마다 매달 +{man(c)}' + (f' (모두 {vat_label()})' if vat_label() else ''))}
  <div class="price-grid">
    <div><table class="ptable ex-table"><thead><tr><th scope="col">구성</th><th scope="col">계산</th><th scope="col">합계</th></tr></thead><tbody>{''.join(exrows)}</tbody></table>
    <p class="muted">운송비는 설치 장소에 따라 따로 안내해 드립니다.</p></div>
    <div class="year">
      <b class="year-t">{esc(yc['title'])}</b>
      <p>{esc(yc['lead'])}</p>
      <div class="year-cmp">
        <div class="yc"><span>1년 렌탈 합계</span><b>{amt_html_val(std_total(1, Y), (1, Y))}</b><small>{man(a)} + {man(c)} × {Y - 1}</small></div>
        <div class="yc yc-buy"><span>{esc(yc['purchase']['label'])}</span><b>{amt_html(PR['rules']['year_buy'])}</b><small>한 번 결제</small></div>
      </div>
      <p>{esc(yc['conclusion'])}</p>
      <p class="muted">{esc(yc['footnote'])}</p>
    </div>
  </div>
</div></section>
""")
    out.append(wrap_section(depth))
    # 키오스크만
    wimg = cover(kiosk, "4x5")
    out.append(f"""<section class="pp-kiosk" id="kiosk"><div class="wrap">
{sec_head('키오스크만', '포토키오스크 · 키오스크만 렌탈', '부스 없이 키오스크만 필요하면 포토키오스크를 한 달 단위로 빌릴 수 있습니다.', '<a class="ps-link" href="products/photo-kiosk.html">포토키오스크 보기 →</a>')}
  <div class="price-grid">
    <div>{package_card('photo-kiosk')}</div>
    <figure class="pp-fig pp-fig-sm"><a href="products/photo-kiosk.html">{img_tag(wimg, 0, cover_alt(kiosk, wimg))}{render_tag(wimg, large=True)}</a><figcaption>포토키오스크 · 월넛 원목 헤드 + 원목 삼각대</figcaption></figure>
  </div>
</div></section>
""")
    # 협의 제품
    neg = PC["negotiable"]
    negp = [x for x in DETAIL if not PR["products"][x["slug"]].get("rental_summary")]
    neg_links = "".join(f'<li><a href="products/{x["slug"]}.html">{esc(x["name"])}</a></li>' for x in negp)
    neg_links += f'<li><a href="products.html#concepts">신규 컨셉 {len(CONCEPTS)}종 <small>제작 가능 · 실물 미제작</small></a></li>'
    ask = "".join(f"<li>{esc(v)}</li>" for v in neg["ask_for"])
    out.append(f"""<section class="pp-neg" id="negotiable"><div class="wrap">
{sec_head('협의', esc(neg['title']), esc(neg['body']))}
  <div class="price-grid">
    <div><ul class="neg-list">{neg_links}</ul></div>
    <div class="ex-box"><b>이 4가지를 알려 주시면 견적이 빨라집니다</b><ul class="ask-list">{ask}</ul></div>
  </div>
  {factor_cards()}
</div></section>
""")
    # 구매
    pu = PC["purchase"]
    prow = []
    for row in pu["rows"]:
        k = row["key"]
        if k in it:
            prod = BYSLUG[row["products"][0]]
            prow.append(f'<tr data-product="{prod["slug"]}"><th scope="row"><a href="products/{prod["slug"]}.html">{esc(it[k]["label"])}</a></th><td>{amt_html(k)}</td></tr>')
        else:
            prow.append(f'<tr><th scope="row">{esc(row["item"])}</th><td><span class="ask">{esc(row["price"])}</span></td></tr>')
    out.append(f"""<section class="pp-purchase" id="purchase"><div class="wrap">
{sec_head('구매가', '구매', esc(pu['desc']))}
  <div class="price-grid">
    <div><table class="ptable"><tbody>{''.join(prow)}</tbody></table><p class="muted">{esc(pu['note'])}</p></div>
    <div class="ex-box"><b>렌탈과 구매, 어느 쪽이 나을까요</b><p>한두 달 행사라면 렌탈, 1년 가까이 두고 쓸 곳이라면 구매를 권해 드립니다. <a href="#examples">1년 비교 보기</a></p></div>
  </div>
</div></section>
""")
    sh = PC["shipping"]
    out.append(f"""<section class="pp-notes" id="notes"><div class="wrap">
{sec_head('참고', '운송비 · 부가세')}
  <div class="notes-grid">
    <div class="ex-box"><b>{esc(sh['title'])}</b><p>{esc(sh['body'])}</p></div>
    <div class="ex-box"><b>부가세</b><p>{esc(vat_sentence())}. 견적서에는 공급가와 부가세를 나눠 적어 드립니다.</p></div>
  </div>
</div></section>

<section class="pp-faq" id="faq"><div class="wrap">
{sec_head('궁금한 점', '자주 묻는 질문')}
  <div class="faq ps-faq">
{faq_html(PC['faq'])}
  </div>
</div></section>
""")
    out.append(cta_band(depth, "구성을 아직 못 정하셨어도 <i>견적부터 받아 보세요.</i>",
                        "장소·날짜·대수를 알려 주시면 24시간 안에 구성과 견적을 보내 드립니다."))
    out.append(body_close(depth))
    return "".join(out)


def amt_html_val(n, total=None):
    """계산 합계 금액. total=(대수, 개월)이면 data-price-total 표식 — site-gate 가 prices.json 규칙으로 다시 계산해 대조한다."""
    t = f' data-price-total="{total[0]}:{total[1]}"' if total else ""
    return f'<span class="amt"{t}>{esc(man(n))}</span>{vat_html()}'


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
<title>루아미 서비스 안내가 가격 페이지로 옮겨졌습니다</title>
<meta name="robots" content="noindex, follow">
<link rel="canonical" href="{BASE}/pricing.html">
<script>/* 옛 서비스 페이지 → 새 주소. 앵커가 있으면 대응 페이지로, 없으면 가격 페이지로 */
(function(){{var m={json.dumps(m, separators=(",", ":"))};var h=location.hash.slice(1);location.replace(m[h]||'pricing.html')}})();</script>
<meta http-equiv="refresh" content="0; url=pricing.html">
<link rel="icon" type="image/png" href="/favicon.png">
<style>body{{font-family:"Pretendard Variable",Pretendard,-apple-system,sans-serif;background:#F5F0DE;color:#1F2417;margin:0;padding:48px 24px;line-height:1.7}}a{{color:#2F5C43}}</style>
</head>
<body>
<p>서비스 안내는 <a href="pricing.html">가격 페이지</a>와 <a href="products.html">제품 페이지</a>로 옮겨졌습니다. 잠시 후 자동으로 이동합니다.</p>
</body>
</html>
"""


# ───────────────────────── 홈·가이드 GEN 블록 ─────────────────────────
def tile_img(prod, variant, depth=0, priority=False):
    """홈 타일 문법(BRIEF 1-5 #4): 사진 칸 바탕 = --tile, 렌더는 contain(통째로), 실사는 cover.
    렌더 대체 이미지 중 바탕이 밝은 것(예: L53 설계 시트 크롭)은 is-light → CSS 가 타일 회색에 곱하기로 얹어 같은 가족으로 보이게 한다.
    표지(covers/)가 생기면 cover() 가 그걸 먼저 돌려주므로 이 함수는 손댈 필요 없다."""
    img = cover(prod, variant)
    if img is None:
        return "", None
    cls = "is-render" if img["kind"] == "render" else "is-photo"
    if img["kind"] == "render" and not img.get("is_cover"):
        bg = edge_color(img["src"])
        hexes = re.findall(r"#([0-9a-f]{6})", bg)
        if hexes and min(sum(int(h[i:i + 2], 16) for i in (0, 2, 4)) / 3 for h in hexes) > 200:
            cls += " is-light"
    return img_tag(img, depth, cover_alt(prod, img), cls=cls, priority=priority), img


def lineup_tile(prod):
    m = PR["products"].get(prod["slug"]) or {}
    v = vat_label()
    vs = f" <small>{esc(v)}</small>" if v else ""
    if m.get("rental_summary"):
        k = m["rental_summary"]
        sub = f'{esc(m.get("rental_summary_prefix", ""))} <span class="lu-amt" data-price-key="{k}">{esc(amt(k))}</span>{vs}'.strip()
    else:
        sub = esc(m.get("rental_text", ""))
    tag, img = tile_img(prod, "thumb")
    badge = f'<span class="lu-badge lu-{prod.get("badge_kind", "main")}">{esc(prod["badge"])}</span>' if prod.get("badge") else ""
    return (f'<li><a class="lu-card" href="products/{prod["slug"]}.html"><span class="lu-im tile">{tag}{badge}{render_tag(img)}</span>'
            f'<b>{esc(prod["name"])}</b><em>{sub}</em></a></li>')


def home_lineup():
    """홈 라인업 — '정가로 바로 진행'(가격이 정해진 제품) / '기간·가격 협의'(나머지 + 커스텀) 두 묶음, 같은 타일 문법.
    정가 묶음 아래에 가격 규칙 4줄(예전 '가격 한눈에' 띠)을 붙인다. 금액은 전부 prices.json."""
    fixed = [x for x in DETAIL if has_fixed_price(x["slug"])]
    fixed.sort(key=lambda x: (x.get("badge_kind") != "main", x["order"]))  # 주력(스탠다드) 먼저
    neg = [x for x in DETAIL if not has_fixed_price(x["slug"])]
    it = PR["items"]
    v = vat_label()
    vs = f' <small class="vat">{esc(v)}</small>' if v else ""
    notes = (f'<li><span class="lp-k">2대째부터 1대마다</span><span class="lp-v"><b data-price-key="std_extra_unit">{esc(amt("std_extra_unit"))}</b>{vs}</span>'
             f'<span class="lp-d">4면 랩핑 포함 · 인화지는 700매 {esc(man(it["paper_700"]["amount"]))}씩 추가</span></li>'
             f'<li><span class="lp-k">두 번째 달부터</span><span class="lp-v"><b data-price-key="std_monthly">부스당 {esc(amt("std_monthly"))}</b>{vs}</span>'
             f'<span class="lp-d">1년 가까이 쓰실 곳이면 구매를 권해 드립니다</span></li>'
             f'<li><span class="lp-k">구매</span><span class="lp-v"><b data-price-key="std_buy">{esc(man(it["std_buy"]["amount"]))}부터</b>{vs}</span>'
             f'<span class="lp-d">스탠다드 부스 {esc(man(it["std_buy"]["amount"]))} · 포토키오스크 {esc(man(it["wood_buy"]["amount"]))}</span></li>')
    return f"""<section class="h-lineup2 h-alt" id="lineup" aria-labelledby="luTitle"><div class="wrap">
  <div class="h-head">
    <div><span class="idxlabel">제품 {len(LINEUP)}종 + 커스텀</span><h2 id="luTitle">정가 제품과 <i>협의 제품</i></h2><p>스탠다드 부스·포토키오스크는 아래 가격 그대로 바로 진행합니다. 나머지는 기간·대수·구성을 듣고 견적을 드립니다.</p></div>
    <a class="h-link" href="products.html">제품 전체 보기 →</a>
  </div>
  <div class="lu-groups">
    <div class="lu-group lu-g-fixed" id="prices">
      <div class="lu-gh"><h3>정가로 바로 진행</h3><span>{esc(v) if v else ""}</span></div>
      <ul class="lu-grid lu-grid-2">{''.join(lineup_tile(x) for x in fixed)}</ul>
      <ul class="lu-notes">{notes}</ul>
      <p class="lu-foot">스탠다드 부스 렌탈은 설치·회수 포함, 운송비 별도 · 포토키오스크 운송·설치 조건은 상담 때 안내 · <a href="pricing.html">전체 가격표 보기 →</a></p>
    </div>
    <div class="lu-group lu-g-neg">
      <div class="lu-gh"><h3>기간·가격 협의</h3><span>{len(neg) - 1}종 + 커스텀 제작</span></div>
      <ul class="lu-grid lu-grid-3">{''.join(lineup_tile(x) for x in neg)}</ul>
    </div>
  </div>
</div></section>"""


def home_paths():
    """첫 갈림길 2카드(BRIEF 2-1 #5) — 행사에 빌리기(스탠다드) / 매장에 들여놓기(포토키오스크). 카드마다 사진 1·버튼 1, 금액은 prices.json."""
    std, kio = BYSLUG["standard-booth"], BYSLUG["photo-kiosk"]
    it = PR["items"]
    v = vat_label()
    vs = f' <small class="vat">{esc(v)}</small>' if v else ""
    ev = {"src": "assets/images/event-festival-white.webp", "kind": "photo", "position": "50% 60%", "is_cover": False}
    ev["w"], ev["h"] = dims(ev["src"])
    k_tag, k_img = tile_img(kio, "4x5")
    return f"""<section class="h-paths" id="paths" aria-labelledby="pathTitle"><div class="wrap">
  <div class="h-head"><div><span class="idxlabel">어떻게 쓰시나요</span><h2 id="pathTitle">행사에 빌리거나, <i>매장에 들여놓거나</i></h2></div></div>
  <div class="path-grid">
    <article class="path-card">
      <figure class="path-im">{img_tag(ev, 0, "서울 뷰티 트래블 위크 야외 행사에 설치한 스탠다드 부스")}</figure>
      <div class="path-body">
        <span class="path-k">행사·팝업 · 며칠에서 몇 주</span>
        <h3>행사에 빌리기</h3>
        <p class="path-price">{esc(std["name"])} <b data-price-key="std_short">{esc(man(it["std_short"]["amount"]))}</b>부터{vs}</p>
        <p class="path-d">1대·1개월 미만 기준. 4면 랩핑·인화지 1,400매·설치·회수가 들어 있고 운송비만 별도입니다.</p>
        <a class="btn path-cta" href="products/{std["slug"]}.html">{esc(std["name"])} 자세히 보기 <span aria-hidden="true">→</span></a>
      </div>
    </article>
    <article class="path-card">
      <figure class="path-im tile">{k_tag}{render_tag(k_img)}</figure>
      <div class="path-body">
        <span class="path-k">매장·카페 · 한 달 단위</span>
        <h3>매장에 들여놓기</h3>
        <p class="path-price">{esc(kio["name"])} 키오스크만 <b data-price-key="wood_monthly">{esc(amt("wood_monthly"))}</b> · 구매 <b data-price-key="wood_buy">{esc(man(it["wood_buy"]["amount"]))}</b>{vs}</p>
        <p class="path-d">렌탈은 인화지 700매 포함, 한 달 단위입니다. 1년 가까이 두실 곳이면 구매를 권해 드립니다.</p>
        <a class="btn path-cta" href="products/{kio["slug"]}.html">{esc(kio["name"])} 자세히 보기 <span aria-hidden="true">→</span></a>
      </div>
    </article>
  </div>
</div></section>"""


def home_hero_h1():
    a = man(PR["items"]["std_short"]["amount"])
    return (f'<h1 aria-label="포토부스 렌탈 {esc(a)}, 4면 랩핑 포함"><span class="lm"><span>포토부스 렌탈</span></span>'
            f'<span class="lm"><span data-price-key="std_short">{esc(a)},</span></span><span class="lm"><span><i>4면 랩핑</i> 포함</span></span></h1>')


def home_hero_sub():
    v = vat_label()
    basis = f"스탠다드 부스 1대·1개월 미만 기준({v})입니다." if v else "스탠다드 부스 1대·1개월 미만 기준입니다."
    return (f'<div class="sub fade"><p>{esc(basis)} 부스·촬영 키오스크(찍고 출력하는 기계)·4면 랩핑(겉면 행사 디자인)·'
            f'인화지(사진 용지) 1,400매에 설치·회수(행사 후 철거)까지 포함되고, 운송비만 별도입니다.</p></div>')


def home_pbox():
    return f"""<h3>가격 한눈에</h3>
        <p>스탠다드 부스 1대를 1개월 미만으로 빌리면 {esc(amt_text('std_short'))}이고, 촬영 키오스크·4면 랩핑·인화지 1,400매와 설치·회수가 포함됩니다. 2대째부터는 1대마다 {esc(man_text(PR['items']['std_extra_unit']['amount']))}, 두 번째 달부터는 부스당 {esc(amt_text('std_monthly'))}씩 더해집니다. 테마 부스와 커스텀 제작은 기간·가격을 협의하고, 운송비는 별도입니다. 상담·견적은 무료입니다. <a href="pricing.html">가격 자세히 보기</a></p>"""


def home_faq_cost():
    return (f"스탠다드 부스는 1개월 미만 렌탈 {esc(amt_text('std_short'))}, 포토키오스크는 키오스크만 렌탈 월 "
            f"{esc(man_text(PR['items']['wood_monthly']['amount']))}입니다. 미러·엘리베이터·지하철·원형 하이앵글 부스는 기간과 구성을 듣고 가격을 정합니다. "
            f"자세한 기준은 <a href=\"pricing.html\">가격 페이지</a>에 정리했습니다.")


def home_form_products():
    """견적 폼 '제품' 선택지 — products.json 순서·이름 그대로(기본값 = 주력 스탠다드 부스). 값 = 제품 이름(메일에 그대로 찍힌다)."""
    main = next(x for x in LINEUP if x.get("badge_kind") == "main")
    opts = [main] + [x for x in DETAIL if x is not main]
    out = "".join(f'<option value="{esc(x["name"])}"{" selected" if x is main else ""}>{esc(x["name"])}</option>' for x in opts)
    return out + f'<option value="신규 컨셉">신규 컨셉 {len(CONCEPTS)}종(제작 상담)</option><option value="아직 모르겠어요">아직 모르겠어요 — 추천해 주세요</option>'


def guide_prices():
    it = PR["items"]
    return f"""<aside class="g-price fade" aria-label="루아미 실제 가격 요약">
    <b class="g-price-t">루아미 실제 가격은?</b>
    <ul>
      <li>스탠다드 부스 1개월 미만 렌탈 <strong data-price-key="std_short">{esc(amt_text('std_short'))}</strong> — 촬영 키오스크(찍고 출력하는 기계)·4면 랩핑(겉면 네 면 디자인 인쇄)·인화지(사진 출력 용지) 1,400매·설치·회수(행사 후 철거) 포함, 운송비 별도</li>
      <li>2대째부터 1대마다 <strong data-price-key="std_extra_unit">{esc(amt_text('std_extra_unit'))}</strong> · 두 번째 달부터 부스당 <strong data-price-key="std_monthly">{esc(amt_text('std_monthly'))}</strong></li>
      <li>포토키오스크만 렌탈 <strong data-price-key="wood_monthly">{esc(amt_text('wood_monthly'))}</strong> — 인화지 700매 포함</li>
      <li>구매 스탠다드 부스 <strong data-price-key="std_buy">{esc(amt_text('std_buy'))}</strong> · 포토키오스크 <strong data-price-key="wood_buy">{esc(amt_text('wood_buy'))}</strong></li>
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
    if not names:  # 제품 목록에서 빠진 제품의 사례 — 지금 제품 페이지로 잘못 잇지 않게 줄을 뺀다
        return re.sub(r'\n?\s*<p class="rel-prod fade">.*?</p>', "", src, count=1, flags=re.S)
    links = " · ".join(f'<a href="../products/{p_["slug"]}.html">{esc(p_["name"])}</a>' for p_ in names)
    return re.sub(r'<p class="rel-prod fade">.*?</p>', lambda m: f'<p class="rel-prod fade">이 현장에 쓰인 제품 — {links}</p>', src, count=1, flags=re.S)


# ───────────────────────── sitemap ─────────────────────────
def update_sitemap(xml, changed_pages):
    pages_new = ["products.html", "pricing.html"] + [f"products/{x['slug']}.html" for x in DETAIL]
    xml = re.sub(r"\s*<url><loc>https://luamiphoto\.com/services\.html</loc>.*?</url>", "", xml, flags=re.S)
    # 없어진 페이지(라인업에서 빠진 제품 상세·블로그 등) 제거 — 파일이 없는 .html loc
    # 내려간 페이지를 옛 주소 안내 스텁(robots noindex + refresh)으로 남긴 경우도 제거 — GitHub Pages 는 서버 301 이 없다
    def keep(m):
        f = ROOT / m.group(1)
        return m.group(0) if f.exists() and not re.search(r'<meta name="robots" content="noindex', f.read_text(encoding="utf-8")) else ""
    xml = re.sub(r"\s*<url><loc>https://luamiphoto\.com/([^<]+\.html)</loc>.*?</url>", keep, xml, flags=re.S)
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


def stale_lastmod_locs():
    """site-gate.js 의 lastmod 판정(본문 지문 비교)을 그대로 불러 올려야 할 loc 목록을 받는다. node 가 없으면 None."""
    import subprocess
    try:
        r = subprocess.run(["node", str(ROOT / "tools" / "site-gate.js"), "--stale-lastmod-json"], cwd=ROOT, capture_output=True,
                           text=True, timeout=120, env=dict(os.environ, BUILD_DATE=TODAY))
        return json.loads(r.stdout or "[]") if r.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None


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
        # 렌더 레인의 covers.json(폴더 또는 상위 폴더)이 있으면 status/set_status = superseded 는 복사하지 않는다
        cj = next((p_ / "covers.json" for p_ in (src, src.parent) if (p_ / "covers.json").exists()), None)
        meta = json.loads(cj.read_text(encoding="utf-8")).get("products", {}) if cj else {}
        n, skipped = 0, []
        extra = SITE["covers"].get("extra", {})
        for prod in DETAIL + CONCEPTS:
            m = meta.get(prod["slug"], {})
            if m.get("status") == "superseded":
                skipped.append(prod["slug"])
                continue
            vs = list(SITE["covers"]["variants"])
            if m.get("set_status") != "superseded":
                vs += [ex["variant"] for ex in extra.get(prod["slug"], [])]
            for v in vs:
                f = src / SITE["covers"]["pattern"].format(slug=prod["slug"], variant=v)
                if cover_hidden(prod["slug"], v):  # products.json site.covers.hide — 쓰지 않는 각도는 들이지 않는다
                    continue
                if f.exists():
                    dst.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(f, dst / f.name)
                    n += 1
                    bl = SITE["covers"].get("baked_label_slugs") or {}
                    if prod["slug"] in bl.get("slugs", []) and v in bl.get("variants", []):
                        import strip_baked_label  # 이미지에 박힌 표기 → 지우고 HTML 칩 하나로(BRIEF 1-5 #4)
                        r = strip_baked_label.strip(dst / f.name, "text")
                        if r["residual"]:
                            print(f"  ! 표기 지우기 자국 남음: {f.name} {r}")
        print(f"표지 {n}개 복사 → {dst.relative_to(ROOT)}" + (f" (superseded 건너뜀: {', '.join(skipped)})" if skipped else "")
              + (f" · 기준 {cj}" if cj else " · covers.json 없음(상태 확인 못 함)"))

    outputs = {}
    outputs["products.html"] = chrome("products.html", hub_page())
    for i, prod in enumerate(DETAIL):
        outputs[f"products/{prod['slug']}.html"] = chrome(f"products/{prod['slug']}.html", detail_page(prod, i))
    outputs["pricing.html"] = chrome("pricing.html", pricing_page())
    outputs["services.html"] = chrome("services.html", services_stub())

    idx = (ROOT / "index.html").read_text(encoding="utf-8")
    idx2 = replace_gen(idx, "home-hero-h1", home_hero_h1(), "index.html")
    idx2 = replace_gen(idx2, "home-hero-sub", home_hero_sub(), "index.html")
    idx2 = replace_gen(idx2, "home-paths", home_paths(), "index.html")
    idx2 = replace_gen(idx2, "home-lineup", home_lineup(), "index.html")
    idx2 = replace_gen(idx2, "home-pbox", home_pbox(), "index.html")
    idx2 = replace_gen(idx2, "home-faq-cost", home_faq_cost(), "index.html")
    idx2 = replace_gen(idx2, "home-form-products", home_form_products(), "index.html")
    outputs["index.html"] = sync_faq_jsonld(idx2)
    gd = (ROOT / "guide.html").read_text(encoding="utf-8")
    outputs["guide.html"] = replace_gen(gd, "guide-prices", guide_prices(), "guide.html")

    case_files = sorted(f for f in ROOT.glob("cases/*.html") if 'content="noindex' not in f.read_text(encoding="utf-8"))  # 옛 주소 안내 스텁 제외
    for f in case_files:
        rel = f"cases/{f.name}"
        outputs[rel] = case_relprod(rel, f.read_text(encoding="utf-8"))

    changed = []
    for rel, s in outputs.items():
        f = ROOT / rel
        old = f.read_text(encoding="utf-8") if f.exists() else None
        if old != s:
            changed.append(rel)

    if not a.check:
        for rel in changed:
            f = ROOT / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(outputs[rel], encoding="utf-8")
    # sitemap lastmod = 본문이 마지막으로 바뀐 날(site-gate.js 와 한 규칙). 쓰고 난 작업본을 게이트의 같은 판정으로 잰다 —
    # 메뉴·푸터·CSS/JS 버전만 바뀐 페이지는 올리지 않고, 손으로 고친 블로그·사례도 본문이 바뀌었으면 올린다.
    stale = stale_lastmod_locs()
    if stale is None:  # node 없음 → 예전 규칙(생성 페이지만)으로 대신
        bump = [r for r in changed if r in ("index.html", "guide.html", "products.html", "pricing.html") or r.startswith("products/")]
        print("주의: node 를 못 찾아 lastmod 는 생성 페이지만 갱신(site-gate 의 본문 기준 판정 못 함)")
    else:
        bump = ["index.html" if x == "" else x for x in stale]
    sm = (ROOT / "sitemap.xml").read_text(encoding="utf-8")
    sm2 = update_sitemap(sm, bump)
    if sm2 != sm:
        changed.append("sitemap.xml")
        outputs["sitemap.xml"] = sm2

    if a.check:
        print("바뀔 파일:", ", ".join(changed) if changed else "없음")
        sys.exit(1 if changed else 0)
    if "sitemap.xml" in changed:
        (ROOT / "sitemap.xml").write_text(sm2, encoding="utf-8")
    fb = [p_["slug"] for p_ in DETAIL + CONCEPTS if not cover_path(p_["slug"], "4x5")]
    print(f"갱신 {len(changed)}개: " + (", ".join(changed) if changed else "없음"))
    print(f"3D 표지 없음 → 대체 이미지 사용: {', '.join(fb) if fb else '없음'}")
    missing_cases = [f.name for f in case_files if not any(f"cases/{f.name}" in CM.get(p_['slug'], {}).get('cases', []) for p_ in DETAIL)]
    if missing_cases:
        print("content_map 에 제품이 없는 사례(제품 줄 뺌): " + ", ".join(missing_cases))


if __name__ == "__main__":
    main()
