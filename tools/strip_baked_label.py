#!/usr/bin/env python3
"""렌더 이미지에 박힌 'CAD 3D 렌더' 글자 지우기 — 페이지의 HTML 칩 하나로만 표기(BRIEF 1-5 #4, r4 V1 #4).

두 종류만 다룬다(둘 다 렌더의 무늬 없는 바닥·배경 위, 오른쪽 아래 구석):
  chip  옛 렌더(.webp)의 어두운 둥근 상자 + 흰 글자 'CAD 3D 렌더'
  text  표지 렌더(lineup-3d/_cover/cover_run.py)의 회색 글자 'CAD 기반 3D 렌더 (실물 사진 아님)'
        — 위치·크기가 코드로 정해져 있다: 글자 크기 max(14, W//90), 오른쪽 여백 0.02W, 아래 여백 0.028H
        ★글자가 박힌 레인의 파일에만 쓴다(products.json site.covers.baked_label_slugs). 다른 표지에 돌리면 그림자를 글자로 볼 수 있다

방법: 오른쪽 아래 구석에서 '그 줄의 배경(줄 중앙값)과 크게 다른 픽셀'을 찾아 상자를 잡고,
      상자 안을 줄마다 왼쪽 바깥 색 → 오른쪽 바깥 색 직선 보간으로 채운다(배경이 완만한 그라데이션이라 자국이 안 남는다).
      글자가 없으면 아무것도 바꾸지 않는다(두 번 돌려도 같음).

  python3 tools/strip_baked_label.py chip  a.webp b.webp ...
  python3 tools/strip_baked_label.py text  c.jpg ...
  python3 tools/strip_baked_label.py --selftest      양방향: 글자를 심은 합성 이미지는 지워지고, 깨끗한 이미지는 그대로
종료코드: 지운 뒤에도 상자 안에 글자 자국(배경과 차이 > 기준)이 남으면 1
"""
import sys
from statistics import median

from PIL import Image, ImageDraw, ImageFont

FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"


def _lum(p):
    return 0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2]


def find_box(im, mode):
    """(x0, y0, x1, y1) 또는 None. 오른쪽 아래 구석만 본다."""
    W, H = im.size
    px = im.load()
    if mode == "chip":
        # 어두운 무채색 상자(밝기 < 100, 채널 차 < 25)만 — '줄 배경보다 어두움'으로 잡으면 밝은 벽 옆 바닥을 상자로 본다
        # (실측: 미러 07 렌더에서 벽·바닥 경계까지 상자로 잡아 지운 자국이 났다)
        rx0, ry0, rx1, ry1 = int(W * 0.55), int(H * 0.80), W, H
        hits = []
        for y in range(ry0, ry1):
            for x in range(rx0, rx1):
                p = px[x, y]
                if _lum(p) < 100 and max(p) - min(p) < 25:
                    hits.append((x, y))
        if len(hits) < 40:
            return None
        xs = sorted(h[0] for h in hits)
        ys = sorted(h[1] for h in hits)
        k = max(1, len(xs) // 100)
        x0, x1, y0, y1 = xs[k], xs[-k - 1], ys[k], ys[-k - 1]
        bw, bh = x1 - x0 + 1, y1 - y0 + 1
        # 글자 상자 모양 검사: 가로로 긴 작은 상자 + 안이 대부분 어두움. 아니면 손대지 않는다
        dense = len(hits) / float(bw * bh)
        if not (bw > 1.8 * bh and bw * bh < 0.06 * W * H and dense > 0.45):
            return None
        return max(0, x0 - 4), max(0, y0 - 4), min(W - 1, x1 + 4), min(H - 1, y1 + 4)
    else:
        fs = max(14, W // 90)
        ry1 = min(H, int(H - H * 0.028 + fs * 0.6))
        ry0 = max(0, int(H - H * 0.028 - fs * 1.6))
        # 글자 폭은 약 0.15W(1600px 에서 242px) — 그 자리만 본다. 넓게 보면 바닥 그림자 끝을 글자로 잡는다(실측: 표지 21장 오탐)
        rx0, rx1 = int(W * 0.78), int(W - W * 0.008)
        thr = 9  # 회색 글자: 배경과 밝기 차가 작다
    hits = []
    for y in range(ry0, ry1):
        row = [_lum(px[x, y]) for x in range(rx0, rx1)]
        m = median(row)
        for i, v in enumerate(row):
            if (m - v) > thr if mode == "chip" else abs(v - m) > thr:
                hits.append((rx0 + i, y))
    if len(hits) < (40 if mode == "chip" else 25):
        return None
    xs = sorted(h[0] for h in hits)
    ys = sorted(h[1] for h in hits)
    # 바깥 1%씩 버려 우연한 픽셀(그림자 끝 등)에 상자가 끌려가지 않게
    k = max(1, len(xs) // 100)
    x0, x1, y0, y1 = xs[k], xs[-k - 1], ys[k], ys[-k - 1]
    pad = 4 if mode == "chip" else 3
    return max(0, x0 - pad), max(0, y0 - pad), min(W - 1, x1 + pad), min(H - 1, y1 + pad)


def fill_box(im, box):
    px = im.load()
    W, H = im.size
    x0, y0, x1, y1 = box
    for y in range(y0, y1 + 1):
        lc = [px[x, y] for x in range(max(0, x0 - 6), max(1, x0 - 1))] or [px[max(0, x0 - 1), y]]
        rc = [px[x, y] for x in range(min(W - 1, x1 + 2), min(W, x1 + 7))]
        L = tuple(int(median(c[i] for c in lc)) for i in range(3))
        Rr = tuple(int(median(c[i] for c in rc)) for i in range(3)) if rc else L
        n = x1 - x0 + 1
        for j in range(n):
            t = (j + 0.5) / n
            px[x0 + j, y] = tuple(round(L[i] * (1 - t) + Rr[i] * t) for i in range(3))


def residual(im, box, mode):
    """지운 상자 안에 아직 글자처럼 튀는 픽셀 수(배경 줄 중앙값과 차이 > 기준)."""
    if box is None:
        return 0
    px = im.load()
    x0, y0, x1, y1 = box
    thr = 45 if mode == "chip" else 9
    n = 0
    for y in range(y0, y1 + 1):
        row = [_lum(px[x, y]) for x in range(x0, x1 + 1)]
        m = median(row)
        n += sum(1 for v in row if abs(v - m) > thr)
    return n


def strip(path, mode, out=None):
    im = Image.open(path)
    fmt = im.format
    im = im.convert("RGB")
    box = find_box(im, mode)
    if box is None:
        return {"file": str(path), "box": None, "changed": False, "residual": 0}
    fill_box(im, box)
    res = residual(im, box, mode)
    dst = out or path
    if fmt == "WEBP":
        im.save(dst, "WEBP", quality=88, method=6)
    else:
        im.save(dst, "JPEG", quality=90, optimize=True, progressive=True)
    return {"file": str(path), "box": box, "changed": True, "residual": res}


def _synthetic(W, H, mode, with_label):
    im = Image.new("RGB", (W, H))
    px = im.load()
    for y in range(H):
        v = 200 - int(40 * y / H)
        for x in range(W):
            px[x, y] = (v, v - 2, v - 4)
    # 제품 대신 왼쪽 가운데 진한 상자(지우면 안 되는 곳)
    d = ImageDraw.Draw(im)
    d.rectangle((W * 0.15, H * 0.2, W * 0.45, H * 0.85), fill=(60, 50, 40))
    if with_label:
        if mode == "chip":
            f = ImageFont.truetype(FONT, max(12, W // 40))
            t = "CAD 3D 렌더"
            tw = d.textlength(t, font=f)
            x1, y1 = W - W * 0.02, H - H * 0.03
            d.rounded_rectangle((x1 - tw - 16, y1 - f.size - 10, x1, y1), radius=6, fill=(70, 70, 70))
            d.text((x1 - tw - 8, y1 - f.size - 6), t, font=f, fill=(255, 255, 255))
        else:
            f = ImageFont.truetype(FONT, max(14, W // 90))
            t = "CAD 기반 3D 렌더 (실물 사진 아님)"
            tw = d.textlength(t, font=f)
            d.text((W - tw - W * 0.02, H - H * 0.028 - f.size), t, font=f, fill=(112, 108, 102))
    return im


def selftest():
    import io
    ok = True
    for mode, (W, H) in (("chip", (600, 600)), ("text", (1600, 2000))):
        for with_label in (True, False):
            im = _synthetic(W, H, mode, with_label)
            before = im.copy()
            box = find_box(im, mode)
            if with_label:
                good = box is not None
                if good:
                    fill_box(im, box)
                    good = residual(im, box, mode) == 0 and find_box(im, mode) is None
                    # 상자 밖(제품 자리)은 그대로여야 한다
                    good = good and im.crop((0, 0, box[0], H)).tobytes() == before.crop((0, 0, box[0], H)).tobytes()
            else:
                good = box is None
            print(("PASS" if good else "FAIL"), mode, "글자 있음 → 지워짐·상자 밖 그대로" if with_label else "글자 없음 → 손대지 않음")
            ok = ok and good
    # 회귀: 밝은 벽 + 어두운 바닥이 오른쪽 아래에 같이 있는 렌더(미러 07) — 상자는 글자 상자만, 벽·바닥 경계는 그대로
    for with_label in (True, False):
        W, H = 640, 728
        im = Image.new("RGB", (W, H), (150, 150, 152))
        d = ImageDraw.Draw(im)
        d.polygon([(int(W * 0.5), 0), (W, 0), (W, int(H * 0.6)), (int(W * 0.5), H)], fill=(225, 226, 228))
        if with_label:
            f = ImageFont.truetype(FONT, 20)
            d.rounded_rectangle((W - 140, H - 52, W - 12, H - 20), radius=6, fill=(68, 68, 70))
            d.text((W - 128, H - 48), "CAD 3D 렌더", font=f, fill=(255, 255, 255))
        before = im.copy()
        box = find_box(im, "chip")
        if with_label:
            good = box is not None and (box[2] - box[0]) * (box[3] - box[1]) < 0.02 * W * H
            if good:
                fill_box(im, box)
                good = residual(im, box, "chip") == 0 and im.crop((0, 0, W, box[1])).tobytes() == before.crop((0, 0, W, box[1])).tobytes()
        else:
            good = box is None
        print(("PASS" if good else "FAIL"), "chip 벽·바닥 경계", "글자 상자만 지움" if with_label else "글자 없음 → 손대지 않음")
        ok = ok and good
    print("SELFTEST", "OK" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "--selftest":
        sys.exit(0 if selftest() else 1)
    if len(a) < 2 or a[0] not in ("chip", "text"):
        print(__doc__)
        sys.exit(2)
    bad = 0
    for p in a[1:]:
        r = strip(p, a[0])
        print(r)
        bad += r["residual"] > 0
    sys.exit(1 if bad else 0)
