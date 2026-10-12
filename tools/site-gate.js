#!/usr/bin/env node
/**
 * 루아미 사이트 출고 게이트 (재사용 도구)
 *   node tools/site-gate.js                  전체 HTML 검사
 *   node tools/site-gate.js a.html b.html    지정 파일만
 *   node tools/site-gate.js --selftest       양방향 자가시험(합성 결함 + 실제 사이트에 심은 결함은 FAIL, 정상판·실제 사이트는 PASS)
 *   node tools/site-gate.js --stale-lastmod-json   sitemap 에서 lastmod 를 올려야 할 loc 목록(JSON) — build_products.py 가 쓴다
 *
 * 잰다:
 *  1) 태그 균형(section/div/details/a/article)
 *  2) JSON-LD 파싱 유효성
 *  3) 금액 = data/prices.json 대조. 가격표에 없는 금액(price-mismatch) — 본문·title·meta description/keywords·
 *     og:/twitter: 메타·JSON-LD 의 모든 문자열(FAQ 답변 등)까지. JSON-LD Offer 가격, 부가세 표기 불일치(vat-label),
 *     가격표 금액이 pricing.html 에 빠짐(price-missing). data/*.json 문자열, 저장소의 md/txt/xml/js/css 도 같은 금액 규칙.
 *  4) 제품 ↔ 가격 연결(price-binding, 2026-10-04 r4):
 *     a. data-price-key="k" / data-price-total="대수:개월" 표식이 붙은 글자 금액 = prices.json 의 그 항목·규칙 합계
 *     b. data-product / data-package="slug" 묶음 안의 금액 항목은 그 제품 것이어야 함(prices.json products[slug])
 *     c. 제품 상세 JSON-LD Offer 가격 = 그 제품의 렌탈·구매 항목 금액
 *     d. 표식이 없는 손글: 같은 글 조각(문단·목록 한 줄·표 한 행·메타·JSON-LD 문자열)에서 금액 바로 앞의 가장 가까운
 *        제품 이름이 그 금액의 주인 제품이 아니면 FAIL(예: '포토키오스크 … 500만원' 인데 500만원은 스탠다드 부스 구매가)
 *  5) 포함/별도 분리: data-list="included" 목록 안에 '별도' 항목(included-list) · 정가 제품 페이지·가격 페이지에
 *     prices.json includes 그대로의 포함 목록(package-binding) · 설치 조건 표의 빈 값 행(empty-row)
 *  6) 금지 카피(최저가·지금신청·초특가·파격할인) · 경쟁사 실명
 *  7) 이미지 참조 실물 존재 + index 이미지 중복 · 깨진 내부 링크
 *  8) sitemap ↔ 실제 파일 정합 + lastmod 정책(stale-lastmod, 아래)
 *  9) 사각지대 메우기(2026-10-04 r4 V2 M7):
 *     a. 속성 글자 — alt·title·aria-label·data-caption·placeholder 값도 금액·부가세·경쟁사 규칙(검색·라이트박스·화면낭독기에 노출)
 *     b. '원' 없는 'N만'(숫자 뒤 '만'에서 끝나는 금액) 도 금액으로 본다. 단 명·장·매·개·회·건·번·대·곳 같은 셈 단위가 바로 뒤면 금액 아님
 *     c. 한글 수사 금액('팔백만원'·'백팔십오만 원')도 숫자로 바꿔 같은 규칙
 *     d. 공개 경로의 PDF(pdf-unchecked / price-mismatch): pdftotext 로 글자를 뽑아 금액 규칙 — 뽑을 수 없으면 FAIL
 *        (사람이 확인 못 한 PDF 가 공개 URL 로 나가지 않게. 이미지 속 글자는 여전히 못 읽는다)
 *
 * lastmod 정책(2026-10-04 r4): lastmod = 그 페이지 '본문'이 마지막으로 바뀐 날.
 *   본문 = title · meta description · og/twitter 메타 · JSON-LD · <body> 글자 · 본문 이미지(src·alt) · 본문 링크(href).
 *   공통 크롬(메뉴 머리·서랍·고정 바·하단 바·푸터·상단 띠)·스크립트·CSS/JS 버전 쿼리는 본문이 아니다(바뀌어도 lastmod 그대로).
 *   판정: lastmod 날 23:59 UTC 시점 커밋의 같은 파일과 지금 작업본의 본문 지문이 다르면 stale. lastmod 가 오늘이면 통과.
 *   build_products.py 가 같은 판정(--stale-lastmod-json)으로 sitemap lastmod 를 오늘로 올린다 — 생성기와 게이트가 한 규칙.
 *   (예전: git 마지막 커밋 날짜 비교 → 메뉴·버전 쿼리만 바뀌어도 FAIL 이라 생성기의 '사례 페이지는 안 올림'과 충돌했다)
 * 종료코드: 위반 있으면 1
 */
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const cp = require('child_process');

const ROOT = path.join(__dirname, '..');
const COMPETITORS = ['인생네컷', '포토이즘', '하루필름', '포토그레이', '셀픽스', '모노맨션', '인싸포토', '지금이순간', '모멘트컷', '심플큐브', '피키픽', '포토시그니처'];
// 2026-10-12: 영문·로고 표기 경쟁사명. 대소문자 무시·단어 경계. 위 한글 목록만으로는 'MOODIT'·'WYC' 를 심어도 PASS 였다(검증 레인 실측).
// 'Haru Film' 은 동주님 결정 대기(협력 브랜드인지 — 오너 질문 #6)라 아직 넣지 않는다. 결정 나면 여기에 추가.
const COMPETITORS_RE = [/출칵출칵/, /\bMOODIT\b/i, /\bBYTP\b/i, /\bWYC\b/i, /\bSNAP\s?CLUB\b/i, /\bpic\s?dot\b/i, /\bPHOTO\s?SIGNATURE\b/i];
function competitorHits(text) {
  const hits = COMPETITORS.filter((c) => text.includes(c));
  for (const re of COMPETITORS_RE) { const m = text.match(re); if (m) hits.push(m[0]); }
  return hits;
}
const BANNED_COPY = [/최저가/, /지금\s*신청/, /초특가/, /파격\s*할인/];

// ── 가격 단일 출처: data/prices.json ─────────────────────────────────────────
// 허용 금액 = 항목 금액 + 규칙(rules.std_total)으로 계산되는 예시 합계 + 1년 비교값.
// 순수 함수로 둔 이유: 셀프테스트에서 합성 가격표로 양방향 시험을 하려고.
function loadPrices(p) {
  return JSON.parse(fs.readFileSync(p || path.join(ROOT, 'data', 'prices.json'), 'utf8'));
}
function loadProducts(p) {
  return JSON.parse(fs.readFileSync(p || path.join(ROOT, 'data', 'products.json'), 'utf8'));
}
function stdTotal(P, u, m) {
  const [a, b, c] = P.rules.std_total.map((k) => P.items[k].amount);
  return a + b * (u - 1) + c * u * (m - 1);
}
function allowedWon(P) {
  const it = P.items;
  const s = new Set();
  for (const k of Object.keys(it)) s.add(it[k].amount * 10000);
  for (const e of P.examples || []) s.add(stdTotal(P, e.units, e.months) * 10000);
  const Y = P.rules.year_months;
  if (Y) {
    s.add(stdTotal(P, 1, Y) * 10000);
    s.add(P.items[P.rules.std_total[2]].amount * (Y - 1) * 10000);
  }
  return s;
}
// 항목 key → 그 항목을 쓰는 제품들(prices.json products[slug] 의 rental·purchase·separate)
function keyOwners(P) {
  const own = {};
  for (const slug of Object.keys(P.products || {})) {
    const m = P.products[slug];
    if (slug.startsWith('_') || !m || typeof m !== 'object') continue;
    const keys = [].concat(m.rental || [], m.purchase || [], m.rental_summary || [], (m.separate || []).map((s) => s.key));
    for (const k of keys) if (k) (own[k] = own[k] || new Set()).add(slug);
  }
  return own;
}
// 금액(원) → 주인 제품들. 규칙 합계(계산 예시·1년)는 std_total 첫 항목의 주인 제품 몫.
function amountOwners(P) {
  const ko = keyOwners(P);
  const out = new Map();
  const put = (won, slugs) => {
    if (!out.has(won)) out.set(won, new Set());
    for (const s of slugs) out.get(won).add(s);
  };
  for (const k of Object.keys(ko)) if (P.items[k]) put(P.items[k].amount * 10000, ko[k]);
  const base = ko[P.rules.std_total[0]] || new Set();
  for (const e of P.examples || []) put(stdTotal(P, e.units, e.months) * 10000, base);
  const Y = P.rules.year_months;
  if (Y) {
    put(stdTotal(P, 1, Y) * 10000, base);
    put(P.items[P.rules.std_total[2]].amount * (Y - 1) * 10000, base);
  }
  return out;
}
function productNames(PJ) {
  const all = [].concat(PJ.lineup || [], PJ.custom ? [PJ.custom] : [], PJ.concepts || []);
  return all.map((x) => [x.name, x.slug]).sort((a, b) => b[0].length - a[0].length);
}

// 텍스트에서 금액 표기를 뽑아 원 단위 정수로: 185만원 / 1,850,000원 / ₩1,850,000
// 공백은 [ \t]* 만 허용(줄바꿈을 넘어 '…04\n원형' 같은 오탐 방지). 원가·원본·원형·원목 등 낱말은 제외.
const MONEY_RE = /₩[ \t]*([0-9][0-9,]*)|([0-9][0-9,]*)[ \t]*만[ \t]*원|([0-9][0-9,]*)[ \t]*원(?![가단장본격료칙상형목통래작리인])|([0-9][0-9,]*)[ \t]*만(?![ \t]*원)(?![ \t]*(?:명|장|매|개|회|건|번|부|권|곳|뷰|대|평|여|가지|팔로워|시간|분|초|년|km|㎡))|([일이삼사오육칠팔구십백천]+)[ \t]*만[ \t]*원/g;
// 한글 수사(만 아래 자리) → 정수: '팔백' 800, '백팔십오' 185, '천이백팔십오' 1285
function hangulNum(s) {
  const D = { 일: 1, 이: 2, 삼: 3, 사: 4, 오: 5, 육: 6, 칠: 7, 팔: 8, 구: 9 };
  const U = { 십: 10, 백: 100, 천: 1000 };
  let total = 0;
  let d = 0;
  for (const ch of s) {
    if (D[ch]) d = D[ch];
    else if (U[ch]) {
      total += (d || 1) * U[ch];
      d = 0;
    }
  }
  return total + d;
}
function moneyHits(text) {
  const out = [];
  let m;
  const re = new RegExp(MONEY_RE.source, 'g');
  while ((m = re.exec(text))) {
    const raw = m[0].trim();
    let won;
    if (m[1] !== undefined) won = Number(m[1].replace(/,/g, ''));
    else if (m[2] !== undefined) won = Number(m[2].replace(/,/g, '')) * 10000;
    else if (m[3] !== undefined) won = Number(m[3].replace(/,/g, ''));
    else if (m[4] !== undefined) won = Number(m[4].replace(/,/g, '')) * 10000;
    else won = hangulNum(m[5]) * 10000;
    if (!won) continue; // 0원
    out.push({ raw, won, index: m.index });
  }
  return out;
}
let PRICES = null;
let ALLOWED = new Set();
let OWNERS = { key: {}, amount: new Map() };
let NAMES = [];
function usePrices(P, PJ) {
  PRICES = P;
  ALLOWED = allowedWon(P);
  OWNERS = { key: keyOwners(P), amount: amountOwners(P) };
  if (PJ) NAMES = productNames(PJ);
}
try {
  usePrices(loadPrices(), loadProducts());
} catch (e) {
  PRICES = null;
}
function vatLabels(P) {
  const L = P.vat.labels;
  const cur = L[P.vat.mode] || '';
  const others = Object.keys(L).filter((k) => k !== P.vat.mode && L[k] && L[k] !== cur).map((k) => L[k]);
  return { cur, others };
}

const SKIP_DIRS = new Set(['assets', 'tools', 'node_modules']);

function walk(dir, acc) {
  acc = acc || [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (e.name.startsWith('.') || SKIP_DIRS.has(e.name)) continue;
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, acc);
    else if (e.name.endsWith('.html')) acc.push(p);
  }
  return acc;
}

const viol = [];
const rel = (f) => path.relative(ROOT, f).split(path.sep).join('/');
const add = (file, rule, msg) => viol.push({ file: rel(file), rule, msg });

function checkBalance(file, html) {
  for (const tag of ['section', 'div', 'details', 'a', 'article']) {
    const open = (html.match(new RegExp('<' + tag + '[\\s>]', 'g')) || []).length;
    const close = (html.match(new RegExp('</' + tag + '>', 'g')) || []).length;
    if (open !== close) add(file, 'tag-balance', '<' + tag + '> ' + open + '개 / </' + tag + '> ' + close + '개');
  }
}

const LD_RE = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/g;
function ldBlocks(html) {
  const out = [];
  let m;
  const re = new RegExp(LD_RE.source, 'g');
  while ((m = re.exec(html))) out.push(m[1]);
  return out;
}

function checkJsonLd(file, html) {
  ldBlocks(html).forEach((b, i) => {
    try {
      JSON.parse(b);
    } catch (e) {
      add(file, 'json-ld', '블록 ' + (i + 1) + ' 파싱 실패: ' + String(e.message).slice(0, 70));
    }
  });
}

// JSON-LD 의 모든 문자열 값(FAQ 답변·설명 등) — 검색결과에 그대로 노출되는 글이라 금액 규칙을 똑같이 적용한다.
function ldStrings(html) {
  const out = [];
  for (const b of ldBlocks(html)) {
    let j;
    try {
      j = JSON.parse(b);
    } catch (e) {
      continue;
    }
    (function w(o) {
      if (typeof o === 'string') out.push(o);
      else if (Array.isArray(o)) o.forEach(w);
      else if (o && typeof o === 'object') Object.keys(o).forEach((k) => (k === '@context' || k === '@type' ? null : w(o[k])));
    })(j);
  }
  return out;
}

function decodeEntities(s) {
  return s.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&nbsp;/g, ' ');
}

// 메타 문구: description·keywords·og:title/description·twitter:title/description (검색·공유 미리보기에 그대로 나간다)
function metaStrings(html) {
  const out = [];
  const re = /<meta\b[^>]*>/gi;
  let m;
  while ((m = re.exec(html))) {
    const tag = m[0];
    const k = (tag.match(/\b(?:name|property)=["']([^"']+)["']/i) || [])[1];
    const c = (tag.match(/\bcontent=["']([^"']*)["']/i) || [])[1];
    if (!k || c === undefined) continue;
    if (/^(description|keywords|og:(title|description|image:alt)|twitter:(title|description))$/i.test(k)) out.push(decodeEntities(c));
  }
  return out;
}

function stripCode(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/g, ' ')
    .replace(/<style[\s\S]*?<\/style>/g, ' ')
    .replace(/<!--[\s\S]*?-->/g, ' ');
}

// 방문자가 실제로 읽는 본문 (head·meta 제외) — 카피 규칙은 여기만 본다.
function bodyText(html) {
  const m = html.match(/<body[\s\S]*<\/body>/i);
  return decodeEntities(stripCode(m ? m[0] : html).replace(/<[^>]*>/g, ' '));
}

// 본문 속성 글자: 이미지 대체글·툴팁·화면낭독기 이름·라이트박스 캡션·입력칸 안내 (화면·검색·낭독기에 노출된다)
function attrStrings(html) {
  const body = stripCode((html.match(/<body[\s\S]*<\/body>/i) || [html])[0]);
  const out = [];
  const re = /\s(?:alt|title|aria-label|data-caption|placeholder)="([^"]*)"/gi;
  let m;
  while ((m = re.exec(body))) if (m[1].trim()) out.push(decodeEntities(m[1]));
  return out;
}

// 검색결과·공유 미리보기에 노출되는 문구 (본문 + 속성 글자 + title + 메타 + JSON-LD 문자열) — 금액·경쟁사는 여기까지 본다.
function exposedText(html) {
  const t = html.match(/<title>([\s\S]*?)<\/title>/i);
  return [bodyText(html), attrStrings(html).join('\n'), metaStrings(html).join('\n'), t ? decodeEntities(t[1]) : '', ldStrings(html).join('\n')].join('\n');
}

function checkMoneyText(file, text, where) {
  if (!PRICES) {
    add(file, 'price-mismatch', 'data/prices.json 을 읽지 못함 — 금액 대조 불가');
    return;
  }
  for (const h of moneyHits(text)) {
    if (!ALLOWED.has(h.won)) add(file, 'price-mismatch', '가격표(data/prices.json)에 없는 금액' + (where || '') + ': "' + h.raw + '"');
  }
}

// 제품 상세 경로 → slug
const slugOfFile = (file) => ((rel(file).match(/^products\/([a-z0-9-]+)\.html$/) || [])[1] || null);

// JSON-LD 안의 Offer·PriceSpecification 가격도 가격표와 같아야 하고, 제품 상세에선 그 제품 항목이어야 한다.
function checkOffers(file, html) {
  if (!PRICES) return;
  const slug = slugOfFile(file);
  const own = new Set();
  if (slug) for (const k of Object.keys(OWNERS.key)) if (OWNERS.key[k].has(slug) && PRICES.items[k]) own.add(PRICES.items[k].amount * 10000);
  for (const b of ldBlocks(html)) {
    let j;
    try {
      j = JSON.parse(b);
    } catch (e) {
      continue;
    }
    (function walk(o) {
      if (Array.isArray(o)) return o.forEach(walk);
      if (!o || typeof o !== 'object') return;
      const t = [].concat(o['@type'] || []);
      if (o.price !== undefined && t.some((x) => /Offer|PriceSpecification/.test(x))) {
        const won = Number(o.price);
        if (!ALLOWED.has(won)) add(file, 'price-mismatch', 'JSON-LD 가격이 가격표에 없음: ' + o.price);
        else if (slug && !own.has(won)) add(file, 'price-binding', 'JSON-LD 가격 ' + won / 10000 + '만원이 ' + slug + ' 의 가격 항목이 아님');
        if (o.priceCurrency && o.priceCurrency !== PRICES.currency) add(file, 'price-mismatch', 'JSON-LD 통화 ' + o.priceCurrency);
      }
      Object.keys(o).forEach((k) => walk(o[k]));
    })(j);
  }
}

// 4a·4b: 금액 표식과 제품 묶음
const tagText = (s) => decodeEntities(s.replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ').trim();
function checkBound(file, html) {
  if (!PRICES) return;
  const it = PRICES.items;
  const re = /<([a-z][a-z0-9]*)\b([^>]*?)\bdata-price-(key|total)="([^"]*)"([^>]*)>([\s\S]*?)<\/\1>/gi;
  let m;
  while ((m = re.exec(html))) {
    const kind = m[3];
    const val = m[4];
    const text = tagText(m[6]);
    const hits = moneyHits(text);
    let want = null;
    if (kind === 'key') want = it[val] ? it[val].amount * 10000 : null;
    else {
      const p = val.split(':').map(Number);
      if (p.length === 2 && p.every((x) => x > 0)) want = stdTotal(PRICES, p[0], p[1]) * 10000;
    }
    if (want === null) add(file, 'price-binding', '가격표에 없는 표식 data-price-' + kind + '="' + val + '"');
    else if (!hits.length) add(file, 'price-binding', '표식 ' + val + ' 안에 금액 글자가 없음: "' + text.slice(0, 40) + '"');
    else if (hits[0].won !== want) add(file, 'price-binding', '표식 ' + val + ' = ' + want / 10000 + '만원인데 화면 금액 "' + hits[0].raw + '"');
  }
  // 묶음: <tr data-product="slug"> … </tr>, <div … data-package="slug"> … (다음 묶음 또는 섹션 끝까지)
  const boxes = [];
  const reTr = /<tr\b[^>]*\bdata-product="([a-z0-9-]+)"[^>]*>([\s\S]*?)<\/tr>/gi;
  while ((m = reTr.exec(html))) boxes.push([m[1], m[2]]);
  const rePk = /\bdata-package="([a-z0-9-]+)"/gi;
  while ((m = rePk.exec(html))) {
    const rest = html.slice(m.index);
    const end = rest.slice(1).search(/data-package="|<\/section>/);
    boxes.push([m[1], end < 0 ? rest : rest.slice(0, end + 1)]);
  }
  for (const [slug, inner] of boxes) {
    const reK = /data-price-key="([a-z0-9_]+)"/g;
    let k;
    while ((k = reK.exec(inner))) {
      const o = OWNERS.key[k[1]];
      if (!o || !o.has(slug)) add(file, 'price-binding', slug + ' 묶음 안에 다른 제품의 가격 항목 ' + k[1]);
    }
  }
}

// 4d: 표식 없는 손글 — 글 조각마다 '금액 바로 앞 가장 가까운 제품 이름'이 그 금액의 주인인지
const BLOCK_END = /<\/(?:p|li|tr|h[1-6]|dd|dt|figcaption|summary|a|div|section|article|blockquote|caption|label|button|header|footer|nav|ul|ol|table|details)>/i;
function textSegments(html) {
  const body = (html.match(/<body[\s\S]*<\/body>/i) || [html])[0];
  const segs = stripCode(body).split(BLOCK_END).map(tagText).filter(Boolean);
  const t = html.match(/<title>([\s\S]*?)<\/title>/i);
  return segs.concat(attrStrings(html), metaStrings(html), t ? [decodeEntities(t[1])] : [], ldStrings(html));
}
function proximityViolations(text) {
  const out = [];
  if (!PRICES || !NAMES.length) return out;
  for (const h of moneyHits(text)) {
    const owners = OWNERS.amount.get(h.won);
    if (!owners || !owners.size) continue;
    let best = null;
    for (const [name, slug] of NAMES) {
      const i = text.lastIndexOf(name, h.index);
      if (i >= 0 && (!best || i > best.i)) best = { i, name, slug };
    }
    if (best && !owners.has(best.slug)) out.push('"' + best.name + '" 뒤 금액 "' + h.raw + '"은 ' + [...owners].join('·') + ' 의 가격: …' + text.slice(Math.max(0, best.i), h.index + h.raw.length).slice(-70) + '…');
  }
  return out;
}
function checkProximity(file, html) {
  for (const s of textSegments(html)) for (const v of proximityViolations(s)) add(file, 'price-binding', v);
}

// 5) 포함 목록 · 정가 제품 포함 목록 대조 · 설치 조건 표 빈 행
function includedLists(html) {
  const out = [];
  const re = /<(ul|ol)\b[^>]*\bdata-list="included"[^>]*>([\s\S]*?)<\/\1>/gi;
  let m;
  while ((m = re.exec(html))) {
    const lis = m[2].split(/<li\b/i).slice(1);
    out.push(lis.map((li) => ({ item: decodeEntities((li.match(/\bdata-item="([^"]*)"/) || [])[1] || ''), text: tagText('<li' + li) })));
  }
  return out;
}
function checkLists(file, html) {
  for (const l of includedLists(html)) for (const x of l) if (/별도/.test(x.text)) add(file, 'included-list', "'포함' 목록 안에 별도 항목: \"" + x.text.slice(0, 40) + '"');
}
function packagePagesFor(relPath, P) {
  const fixed = Object.keys(P.products || {}).filter((s) => !s.startsWith('_') && P.products[s] && P.products[s].rental_summary);
  if (relPath === 'pricing.html') return fixed;
  const m = relPath.match(/^products\/([a-z0-9-]+)\.html$/);
  return m && fixed.includes(m[1]) ? [m[1]] : [];
}
function checkPackages(file, html, relPath) {
  if (!PRICES) return;
  const lists = includedLists(html).map((l) => l.map((x) => x.item).filter(Boolean).sort().join('|'));
  for (const slug of packagePagesFor(relPath || rel(file), PRICES)) {
    const inc = (PRICES.items[PRICES.products[slug].rental_summary].includes || []).slice().sort().join('|');
    if (!lists.includes(inc)) add(file, 'package-binding', slug + ' 의 포함 목록(prices.json includes: ' + inc.replace(/\|/g, '·') + ')이 이 페이지 포함 목록에 그대로 없음');
  }
}
function checkEmptyRows(file, html) {
  const re = /<table\b[^>]*\bdata-table="install"[^>]*>([\s\S]*?)<\/table>/gi;
  let m;
  while ((m = re.exec(html))) {
    const rows = m[1].split(/<tr\b/i).slice(1);
    for (const r of rows) {
      const cells = [];
      const rc = /<td\b[^>]*>([\s\S]*?)<\/td>/gi;
      let c;
      while ((c = rc.exec(r))) cells.push(tagText(c[1]));
      if (!cells.length || cells.some((t) => !t || /^[-—–·?]+$|^미정$|^확인 ?중$/.test(t))) add(file, 'empty-row', '설치 조건 표에 빈 값 행: "' + tagText('<tr' + r).slice(0, 40) + '"');
    }
  }
}

function checkVat(file, text) {
  if (!PRICES) return;
  const { others } = vatLabels(PRICES);
  for (const o of others) if (text.includes(o)) add(file, 'vat-label', '부가세 표기 불일치: "' + o + '" (현재 설정: ' + PRICES.vat.mode + ')');
}

function checkCopy(file, html) {
  const body = bodyText(html);
  const exposed = exposedText(html);
  checkMoneyText(file, exposed);
  checkOffers(file, html);
  checkBound(file, html);
  checkProximity(file, html);
  checkVat(file, exposed);
  for (const re of BANNED_COPY) {
    const m = body.match(re);
    if (m) add(file, 'banned-copy', '금지 카피: "' + m[0] + '"');
  }
  for (const c of competitorHits(exposed)) add(file, 'competitor', '경쟁사 실명: "' + c + '"');
}

function checkStructure(file, html, relPath) {
  checkLists(file, html);
  checkPackages(file, html, relPath);
  checkEmptyRows(file, html);
}

// data/**/*.json 의 문자열 값(카피·가격 문구)도 같은 금액 규칙으로 본다. prices.json 자체는 숫자라 해당 없음.
function checkDataJson(dir) {
  const out = [];
  (function w(d) {
    if (!fs.existsSync(d)) return;
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) w(p);
      else if (e.name.endsWith('.json')) out.push(p);
    }
  })(dir);
  for (const f of out) {
    let j;
    try {
      j = JSON.parse(fs.readFileSync(f, 'utf8'));
    } catch (e) {
      add(f, 'json-ld', 'data JSON 파싱 실패');
      continue;
    }
    const strs = [];
    (function walk(o) {
      if (typeof o === 'string') strs.push(o);
      else if (Array.isArray(o)) o.forEach(walk);
      else if (o && typeof o === 'object') Object.keys(o).forEach((k) => walk(o[k]));
    })(j);
    checkMoneyText(f, strs.join('\n'), ' (data)');
    if (path.basename(f) !== 'prices.json') checkVat(f, strs.join('\n')); // prices.json 은 표기 후보 목록 자체를 담는다
  }
}

// HTML·data 밖의 저장소 텍스트(문서·메모 .md/.txt, sitemap, js, css)도 공개 URL로 나간다 → 같은 금액 규칙.
// (예전 retired_sha256 '폐기 금액 해시' 목록은 없앴다: 가격표 밖 금액은 어차피 전부 FAIL 이고, 만원 단위 정수 해시는
//  몇 천 번 대입으로 바로 풀려 평문을 숨기지도 못했다.)
function checkTextFiles() {
  if (!PRICES) return;
  const exts = /\.(md|txt|xml|csv|js|css)$/;
  (function w(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.name.startsWith('.') || e.name === 'node_modules') continue;
      const p = path.join(d, e.name);
      if (e.isDirectory()) w(p);
      else if (exts.test(e.name) && p !== __filename) checkMoneyText(p, fs.readFileSync(p, 'utf8'), ' (파일)');
    }
  })(ROOT);
}

// 9d) 공개 경로의 PDF — 글자를 뽑아 금액·경쟁사 규칙. 뽑지 못하면 FAIL(확인 안 된 문서는 공개하지 않는다).
function pdftotextExtract(f) {
  const r = cp.spawnSync('pdftotext', ['-layout', '-q', f, '-'], { encoding: 'utf8' });
  if (r.error || r.status !== 0) return null;
  return r.stdout;
}
function checkPdf(file, extract) {
  const text = (extract || pdftotextExtract)(file);
  if (text === null || text === undefined) {
    add(file, 'pdf-unchecked', 'PDF 글자를 뽑지 못함(pdftotext 없음·실패) — 공개 URL 로 나가는 문서라 사람이 금액·제품을 확인한 뒤 올리거나 저장소에서 빼야 함');
    return;
  }
  checkMoneyText(file, text, ' (PDF)');
  checkVat(file, text);
  for (const c of competitorHits(text)) add(file, 'competitor', '경쟁사 실명(PDF): "' + c + '"');
}
function checkPdfs() {
  (function w(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.name.startsWith('.') || e.name === 'node_modules') continue;
      const p = path.join(d, e.name);
      if (e.isDirectory()) w(p);
      else if (/\.pdf$/i.test(e.name)) checkPdf(p);
    }
  })(ROOT);
}

// 가격표의 모든 항목 금액이 pricing.html 에 실제로 보이는지(가격 페이지가 빠뜨리지 않았는지).
function checkPriceCoverage() {
  if (!PRICES) return;
  const pf = path.join(ROOT, 'pricing.html');
  if (!fs.existsSync(pf)) {
    add(pf, 'price-missing', 'pricing.html 없음');
    return;
  }
  const html = fs.readFileSync(pf, 'utf8');
  const seen = new Set(moneyHits(exposedText(html)).map((h) => h.won));
  for (const k of Object.keys(PRICES.items)) {
    const won = PRICES.items[k].amount * 10000;
    if (!seen.has(won)) add(pf, 'price-missing', '가격표 항목이 pricing.html 에 안 보임: ' + k + ' ' + PRICES.items[k].amount + '만원');
  }
  const { cur } = vatLabels(PRICES);
  if (cur && !bodyText(html).includes(cur)) add(pf, 'vat-label', 'pricing.html 에 현재 부가세 표기("' + cur + '")가 없음');
}

function checkImages(file, html) {
  const refs = [];
  const re = /(?:src|href)=["'](?:\.\.\/)?(assets\/images\/[^"']+)["']/g;
  let m;
  while ((m = re.exec(html))) refs.push(m[1]);
  for (const r of new Set(refs)) {
    if (!fs.existsSync(path.join(ROOT, r))) add(file, 'missing-image', '없는 이미지: ' + r);
  }
  if (path.basename(file) === 'index.html') {
    const c = {};
    for (const r of refs) c[r] = (c[r] || 0) + 1;
    for (const k of Object.keys(c)) if (c[k] > 1) add(file, 'dup-image', 'index 이미지 중복 ' + c[k] + '회: ' + k);
  }
}

function checkLinks(file, html) {
  const dir = path.dirname(file);
  const re = /href=["']([^"'#?][^"']*\.html)(?:[#?][^"']*)?["']/g;
  let m;
  const seen = new Set();
  while ((m = re.exec(html))) {
    const href = m[1];
    if (/^(https?:|mailto:|tel:)/.test(href) || seen.has(href)) continue;
    seen.add(href);
    const target = href.startsWith('/') ? path.join(ROOT, href.slice(1)) : path.resolve(dir, href);
    if (!fs.existsSync(target)) add(file, 'dead-link', '깨진 내부 링크: ' + href);
  }
}

// ── 규칙 8) sitemap lastmod = 본문이 마지막으로 바뀐 날 ─────────────────────────
// 본문 지문: 공통 크롬·스크립트·자산 버전 쿼리를 걷어낸 뒤 글자·이미지·링크·메타·JSON-LD 로 만든 해시.
function contentFingerprint(html) {
  const t = (html.match(/<title>([\s\S]*?)<\/title>/i) || ['', ''])[1].trim();
  const lds = ldBlocks(html).map((b) => {
    try {
      return JSON.stringify(JSON.parse(b));
    } catch (e) {
      return b.trim();
    }
  });
  let body = (html.match(/<body[\s\S]*<\/body>/i) || [''])[0];
  body = stripCode(body)
    .replace(/<header class="nav"[\s\S]*?<\/header>/g, ' ')
    .replace(/<div class="drawer-scrim"[\s\S]*?(?=<div class="stickybar")/g, ' ')
    .replace(/<div class="stickybar"[\s\S]*?<\/div>/g, ' ')
    .replace(/<div class="util">[\s\S]*?<\/div>\s*<\/div>/g, ' ')
    .replace(/<div class="mcta">[\s\S]*?<\/div>/g, ' ')
    .replace(/<footer[\s\S]*?<\/footer>/g, ' ')
    .replace(/<div class="(?:grain|progress)"[^>]*><\/div>/g, ' ');
  const attrs = [];
  const re = /<(img|a|source|video)\b[^>]*>/gi;
  let m;
  while ((m = re.exec(body))) {
    const tag = m[0];
    for (const a of ['src', 'href', 'alt', 'poster']) {
      const v = (tag.match(new RegExp('\\b' + a + '=["\']([^"\']*)["\']')) || [])[1];
      if (v !== undefined) attrs.push(a + '=' + v.replace(/\?v=[^"'#]*/, ''));
    }
  }
  const text = decodeEntities(body.replace(/<[^>]*>/g, ' ')).replace(/\s+/g, ' ').trim();
  return crypto.createHash('sha256').update(JSON.stringify([t, metaStrings(html), lds, text, attrs])).digest('hex');
}

// entries = [{loc, lastmod}], fpNow(rel) -> 지문|null(파일 없음), fpAt(rel, date) -> 지문|null(그날엔 파일 없음)|undefined(판정 불가)
function staleLastmod(entries, fpNow, fpAt, today) {
  const out = [];
  for (const e of entries) {
    const r = e.loc === '' ? 'index.html' : e.loc;
    if (!r.endsWith('.html')) continue;
    const now = fpNow(r);
    if (now === null) continue; // 파일 없음은 sitemap 정합 규칙이 따로 본다
    if (!e.lastmod) {
      out.push({ loc: e.loc, msg: 'lastmod 없음' });
      continue;
    }
    if (e.lastmod >= today) continue;
    const old = fpAt(r, e.lastmod);
    if (old === undefined) continue;
    if (old === null) out.push({ loc: e.loc, msg: 'lastmod ' + e.lastmod + ' 뒤에 생긴 페이지' });
    else if (old !== now) out.push({ loc: e.loc, msg: 'lastmod ' + e.lastmod + ' 뒤에 본문이 바뀜' });
  }
  return out;
}

const _revAt = {};
let _hasGit = null;
function gitFpAt(relPath, date) {
  if (_hasGit === null) {
    try {
      cp.execSync('git rev-parse --git-dir', { cwd: ROOT, stdio: 'ignore' });
      _hasGit = true;
    } catch (e) {
      _hasGit = false;
    }
  }
  if (!_hasGit) return undefined; // git 이 없다 → 판정 불가
  const sh = { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] };
  if (!(date in _revAt)) {
    try {
      _revAt[date] = cp.execSync('git rev-list -1 --before="' + date + ' 23:59:59 +0000" HEAD', sh).trim();
      // 얕은 클론이라 그날 이전 이력이 잘려 있으면, 남아 있는 가장 오래된 커밋을 기준으로 삼는다:
      // 그 커밋과 지금이 다르면 lastmod 뒤에 바뀐 것이 확실하고, 같으면 바뀌었다는 증거가 없다(통과).
      if (!_revAt[date] && cp.execSync('git rev-parse --is-shallow-repository', sh).trim() === 'true') {
        _revAt[date] = cp.execSync('git rev-list --reverse HEAD', sh).split('\n')[0].trim();
      }
    } catch (e) {
      _revAt[date] = '';
    }
  }
  const rev = _revAt[date];
  if (!rev) return null; // 그날 이전 이력이 없음(얕은 클론 아님) → 지금 본문은 그 뒤에 생긴 것
  try {
    const old = cp.execSync('git show ' + rev + ':"' + relPath + '"', { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], maxBuffer: 1 << 26 });
    return contentFingerprint(old);
  } catch (e) {
    return null; // 그 시점에 파일이 없었다
  }
}
const fsFpNow = (r) => (fs.existsSync(path.join(ROOT, r)) ? contentFingerprint(fs.readFileSync(path.join(ROOT, r), 'utf8')) : null);
const todayUTC = () => new Date().toISOString().slice(0, 10);

function sitemapEntries(xml) {
  const locs = [];
  const re = /<loc>https:\/\/luamiphoto\.com\/([^<]*)<\/loc>/g;
  let m;
  while ((m = re.exec(xml))) locs.push(m[1]);
  const entries = [];
  const re2 = /<loc>https:\/\/luamiphoto\.com\/([^<]*)<\/loc>\s*<lastmod>([^<]*)<\/lastmod>/g;
  let m2;
  while ((m2 = re2.exec(xml))) entries.push({ loc: m2[1], lastmod: m2[2] });
  for (const l of locs) if (!entries.some((e) => e.loc === l)) entries.push({ loc: l, lastmod: '' });
  return { locs, entries };
}

function checkSitemap(files) {
  const sp = path.join(ROOT, 'sitemap.xml');
  if (!fs.existsSync(sp)) return;
  const xml = fs.readFileSync(sp, 'utf8');
  const { locs, entries } = sitemapEntries(xml);
  for (const l of locs) {
    const r = l === '' ? 'index.html' : l;
    if (r.endsWith('.html') && !fs.existsSync(path.join(ROOT, r))) add(sp, 'sitemap', 'sitemap에 있으나 파일 없음: ' + l);
  }
  const set = new Set(locs.map((l) => (l === '' ? 'index.html' : l)));
  for (const f of files) {
    const r = rel(f);
    if (r === '404.html' || r === 'thanks.html') continue;
    // ★noindex 페이지는 sitemap 완전성 검사에서 뺀다 — 원리는 하드코딩 파일명이 아니라 robots 메타다.
    const body = fs.readFileSync(f, 'utf8');
    if (/meta\s+name="robots"[^>]*noindex/i.test(body)) continue;
    if (!set.has(r)) add(sp, 'sitemap', '파일이 sitemap에 없음: ' + r);
  }
  for (const v of staleLastmod(entries, fsFpNow, gitFpAt, process.env.BUILD_DATE || todayUTC())) add(sp, 'stale-lastmod', v.msg + ' — ' + (v.loc || '/'));
}

if (process.argv.includes('--stale-lastmod-json')) {
  const sp = path.join(ROOT, 'sitemap.xml');
  const { entries } = sitemapEntries(fs.readFileSync(sp, 'utf8'));
  const st = staleLastmod(entries, fsFpNow, gitFpAt, process.env.BUILD_DATE || todayUTC());
  process.stdout.write(JSON.stringify(st.map((v) => v.loc)));
  process.exit(0);
}

// 한 파일에 대한 전 규칙(sitemap·data·저장소 전체 규칙 제외)
function checkFile(file, html, relPath) {
  checkBalance(file, html);
  checkJsonLd(file, html);
  checkCopy(file, html);
  checkStructure(file, html, relPath);
  checkImages(file, html);
  checkLinks(file, html);
}

// --selftest: 결함을 합성해 각 규칙이 실제로 무는지 + 정상판은 통과하는지 양방향 확인.
// 출고 데이터가 나쁘기를 기대하지 않는다 — 대조군을 여기서 직접 만든다. 실제 사이트 페이지에도 결함을 심어 본다.
if (process.argv.includes('--selftest')) {
  const CLEAN = [
    '<html><head><title>루아미</title><meta name="description" content="무인 포토부스 렌탈">',
    '</head><body><section><div><p>장소·기간·구성에 따라 달라집니다. 렌탈 문의 주세요.</p>',
    '<p>행사 당일 하루만 운영하는 방식이 아니라 상설로 둡니다. QR로 4장의 원본파일을 받습니다.</p>',
    '<a href="assets/images/hero.webp">사진</a></div></section>',
    '<script type="application/ld+json">{"@type":"Thing"}</script></body></html>',
  ].join('');
  // 가격 대조 규칙의 대조군: 실제 data/prices.json 값으로 만든 '정상 금액' 문장(정상판에 포함 → 걸리면 오탐).
  const P0 = loadPrices();
  const it0 = P0.items;
  const man = (n) => n.toLocaleString('en-US') + '만원';
  const [a0, b0, c0] = P0.rules.std_total.map((k) => it0[k].amount);
  const VAT = vatLabels(P0).cur || '';
  const REAL = '1개월 미만 ' + man(a0) + ', 2대면 ' + man(a0 + b0) + ', 1대 3개월 ' + man(a0 + 2 * c0) +
    ', 구매 스탠다드 부스 ' + man(it0.std_buy.amount) + ' · 포토키오스크 ' + man(it0.wood_buy.amount) + ' ' + VAT + '. 포토부스 제작·판매도 합니다.';
  const WRONG = man(a0 + 5); // 가격표에 없는 금액(정찰가 +5만)
  const OTHER_VAT = vatLabels(P0).others[0];
  const offer = (won) => '<script type="application/ld+json">{"@type":"Product","offers":{"@type":"Offer","price":' + won + ',"priceCurrency":"KRW"}}</script>';
  const faq = (ans) => '<script type="application/ld+json">{"@type":"FAQPage","mainEntity":[{"@type":"Question","name":"얼마인가요?","acceptedAnswer":{"@type":"Answer","text":"' + ans + '"}}]}</script>';
  const BOUND = '<p>렌탈 <span class="amt" data-price-key="std_short">' + man(a0) + '</span> · 2대 <span class="amt" data-price-total="2:1">' + man(a0 + b0) + '</span></p>' +
    '<table><tr data-product="photo-kiosk"><th>포토키오스크</th><td><span class="amt" data-price-key="wood_buy">' + man(it0.wood_buy.amount) + '</span></td></tr></table>';
  const STD_INC = it0[P0.products['standard-booth'].rental_summary].includes || [];
  const INCL = '<ul data-list="included">' + STD_INC.map((x) => '<li data-item="' + x + '">' + x + '</li>').join('') + '</ul><ul data-list="separate"><li>운송비 별도</li></ul>' +
    '<table data-table="install"><tbody><tr><th scope="row">차지 면적</th><td>1,860 × 1,860mm</td></tr></tbody></table>';
  const OG = '<meta property="og:description" content="스탠다드 부스 ' + man(a0) + '">';
  const KOR = { 1: '일', 2: '이', 3: '삼', 4: '사', 5: '오', 6: '육', 7: '칠', 8: '팔', 9: '구' };
  const hangul = (n) => [[1000, '천'], [100, '백'], [10, '십']].reduce((acc, [u, c]) => { const q = Math.floor(acc[1] / u); return q ? [acc[0] + (q > 1 ? KOR[q] : '') + c, acc[1] % u] : acc; }, ['', n]).reduce((s, r) => s + (r ? KOR[r] : ''));
  const NOTMONEY = '<p>스탠다드 부스는 ' + hangul(a0) + '만원부터, 지금까지 사진 1만 장 넘게 뽑았습니다. <img src="assets/images/hero.webp" alt="스탠다드 부스 ' + man(a0) + ' 설치 모습"></p>';
  const CLEAN_P = CLEAN.replace('렌탈 문의 주세요.', REAL).replace('</head>', OG + '</head>')
    .replace('</section>', BOUND + INCL + NOTMONEY + '</section>')
    .replace('</body>', offer(a0 * 10000) + faq('2대면 ' + man(a0 + b0) + '(' + VAT + ')입니다.') + '</body>');
  const CASES = [
    ['price-mismatch', CLEAN_P.replace(REAL, REAL + ' 대여료 150,000원입니다.')],
    ['price-mismatch', CLEAN_P.replace(REAL, REAL + ' 월 30만원부터.')],
    ['price-mismatch', CLEAN_P.replace('1개월 미만 ' + man(a0) + ',', '1개월 미만 ' + WRONG + ',')],
    ['price-mismatch', CLEAN_P.replace('"price":' + a0 * 10000, '"price":' + (a0 + 5) * 10000)],
    ['price-mismatch', CLEAN_P.replace('2대면 ' + man(a0 + b0) + '(', '2대면 ' + man(a0 + b0 + 20) + '(')], // FAQ JSON-LD 답변에만 틀린 금액
    ['price-mismatch', CLEAN_P.replace(OG, OG.replace(man(a0), WRONG))], // og:description 에만 틀린 금액
    ['price-mismatch', CLEAN_P.replace('alt="스탠다드 부스 ' + man(a0) + ' 설치 모습"', 'alt="스탠다드 부스 23만원 설치 모습"')], // 이미지 대체글(alt)에만 틀린 금액
    ['price-mismatch', CLEAN_P.replace(REAL, REAL + ' 일반 키오스크 ' + (a0 * 4 + 60) + '만.')], // '원' 없는 N만(가격표에 없는 값을 계산해 만든다 — 폐기 금액 문자열을 저장소에 두지 않음)
    ['price-mismatch', CLEAN_P.replace(REAL, REAL + ' 일반 키오스크 팔백만원.')], // 한글 수사 금액
    ['price-binding', CLEAN_P.replace('data-price-key="wood_buy">' + man(it0.wood_buy.amount), 'data-price-key="wood_buy">' + man(it0.std_buy.amount))],
    ['price-binding', CLEAN_P.replace('data-price-total="2:1">' + man(a0 + b0), 'data-price-total="2:1">' + man(a0 + 2 * b0))],
    ['price-binding', CLEAN_P.replace('data-price-key="wood_buy">' + man(it0.wood_buy.amount), 'data-price-key="std_buy">' + man(it0.std_buy.amount))], // 포토키오스크 행에 스탠다드 구매가 항목
    ['price-binding', CLEAN_P.replace('포토키오스크 ' + man(it0.wood_buy.amount), '포토키오스크 ' + man(it0.std_buy.amount))], // 손글: 이름 ↔ 금액 뒤바뀜
    ['price-binding', CLEAN_P.replace(REAL, REAL + ' 미러포토부스는 ' + man(a0) + '입니다.')], // 협의 제품 이름 뒤 정가
    ['included-list', CLEAN_P.replace('<ul data-list="included">', '<ul data-list="included"><li>운송비 별도</li>')],
    ['empty-row', CLEAN_P.replace('</tbody></table>', '<tr><th scope="row">전원</th><td> </td></tr></tbody></table>')],
    ['vat-label', CLEAN_P.replace(REAL, REAL + ' (' + (OTHER_VAT || '부가세 포함') + ')')],
    ['banned-copy', CLEAN.replace('렌탈 문의 주세요.', '업계 최저가 보장.')],
    ['competitor', CLEAN.replace('렌탈 문의 주세요.', '인생네컷보다 낫습니다.')],
    ['competitor', CLEAN.replace('렌탈 문의 주세요.', 'Moodit 부스보다 낫습니다.')], // 영문·대소문자 섞임
    ['competitor', CLEAN.replace('렌탈 문의 주세요.', '출칵출칵 매장에도 들어갑니다.')],
    ['competitor', CLEAN.replace('렌탈 문의 주세요.', 'WYC 팝업 납품 사례.')],
    ['tag-balance', CLEAN.replace('</section>', '')],
    ['json-ld', CLEAN.replace('{"@type":"Thing"}', '{"@type":,}')],
    ['missing-image', CLEAN.replace('assets/images/hero.webp', 'assets/images/__nope__.webp')],
    ['dead-link', CLEAN.replace('<a href="assets/images/hero.webp">', '<a href="__nope__.html">')],
  ];
  const tmp = path.join(ROOT, 'tools', '.gate-selftest.html');
  const run = (html, file, relPath) => {
    viol.length = 0;
    const f = file || tmp;
    if (!file) fs.writeFileSync(tmp, html, 'utf8');
    checkFile(f, html, relPath);
    return viol.map((v) => v.rule);
  };
  let bad = 0;
  let n = 0;
  const ok = (cond, msg) => {
    n++;
    if (cond) console.log('  ok    ' + msg);
    else {
      console.log('  FAIL  ' + msg);
      bad++;
    }
  };
  // 규칙 8 stale-lastmod — 지문 함수와 판정 함수를 따로 합성 시험
  {
    const page = (body, extra) => '<html><head><title>T</title><meta name="description" content="D"><link rel="stylesheet" href="assets/style.css?v=' + (extra || 'a') + '"></head><body>' +
      '<div class="util"><div class="wrap"><span>띠</span></div></div><header class="nav"><div class="wrap">메뉴' + (extra || '') + '</div></header>' +
      '<div class="drawer-scrim"></div><div class="stickybar" id="sbar"><a href="index.html">L</a></div>' + body +
      '<footer><div class="wrap">푸터' + (extra || '') + '</div></footer><div class="mcta"><a href="tel:1">전화</a></div><script src="assets/main.js?v=' + (extra || 'a') + '"></script></body></html>';
    const A = page('<main><p>본문 하나</p><img src="assets/images/x.webp" alt="사진"></main>');
    const fp = contentFingerprint;
    ok(fp(A) === fp(page('<main><p>본문 하나</p><img src="assets/images/x.webp" alt="사진"></main>', 'b')), 'stale-lastmod 지문 — 메뉴·푸터·CSS/JS 버전만 바뀌면 같음');
    ok(fp(A) !== fp(page('<main><p>본문 둘</p><img src="assets/images/x.webp" alt="사진"></main>')), 'stale-lastmod 지문 — 본문 글자가 바뀌면 다름');
    ok(fp(A) !== fp(page('<main><p>본문 하나</p><img src="assets/images/y.webp" alt="사진"></main>')), 'stale-lastmod 지문 — 본문 사진이 바뀌면 다름');
    ok(fp(A) !== fp(A.replace('</head>', '<script type="application/ld+json">{"a":1}</script></head>')), 'stale-lastmod 지문 — JSON-LD 가 바뀌면 다름');
    const FP = { 'index.html': 'N1', 'guide.html': 'N2', 'new.html': 'N3' };
    const AT = { 'index.html@2026-09-08': 'N1', 'guide.html@2026-08-06': 'OLD', 'new.html@2026-08-06': null };
    const now = (r) => (r in FP ? FP[r] : null);
    const at = (r, d) => (r + '@' + d in AT ? AT[r + '@' + d] : undefined);
    const T = '2026-10-04';
    ok(staleLastmod([{ loc: '', lastmod: '2026-09-08' }, { loc: 'assets/x.webp', lastmod: '2020-01-01' }, { loc: 'guide.html', lastmod: T }], now, at, T).length === 0,
      'stale-lastmod 정상판 통과(본문 그대로·비HTML·오늘 날짜 오탐 없음)');
    const s1 = staleLastmod([{ loc: 'guide.html', lastmod: '2026-08-06' }], now, at, T);
    ok(s1.length === 1 && /본문이 바뀜/.test(s1[0].msg), 'stale-lastmod — lastmod 뒤 본문이 바뀐 페이지를 물었다');
    ok(staleLastmod([{ loc: 'new.html', lastmod: '2026-08-06' }], now, at, T).length === 1, 'stale-lastmod — lastmod 뒤에 생긴 페이지를 물었다');
    ok(staleLastmod([{ loc: '', lastmod: '' }], now, at, T).length === 1, 'stale-lastmod — lastmod 누락을 물었다');
  }
  ok(run(CLEAN).length === 0, '정상판 통과(오탐 없음)');
  const cleanP = run(CLEAN_P);
  ok(cleanP.length === 0, '가격 정상판 통과 — 표식 금액·묶음·계산 예시·Offer·FAQ JSON-LD·og·포함 목록·설치 표·"제작·판매" 오탐 없음' + (cleanP.length ? ' (걸린 것: ' + cleanP.join(',') + ')' : ''));
  // data JSON 규칙: 합성 data 폴더로 정상/결함 양방향
  {
    const dd = path.join(ROOT, 'tools', '.gate-selftest-data');
    fs.mkdirSync(dd, { recursive: true });
    const df = path.join(dd, 'x.json');
    const runData = (obj) => {
      viol.length = 0;
      fs.writeFileSync(df, JSON.stringify(obj), 'utf8');
      checkDataJson(dd);
      return viol.map((v) => v.rule);
    };
    const okD = runData({ note: '2대면 ' + man(a0 + b0) + '이에요.' });
    const badD = runData({ note: '2대면 ' + man(a0 + b0 + 1) + '이에요.' });
    fs.rmSync(dd, { recursive: true, force: true });
    ok(okD.length === 0, 'data JSON 정상판 통과');
    ok(badD.includes('price-mismatch'), 'data JSON — 틀린 금액을 물었다');
  }
  // 9d PDF: 글자를 뽑는 함수를 바꿔 끼워 양방향(실제 pdftotext 유무와 무관하게 규칙만 시험)
  {
    const runPdf = (ex) => {
      viol.length = 0;
      checkPdf(path.join(ROOT, 'x.pdf'), ex);
      return viol.map((v) => v.rule);
    };
    ok(runPdf(() => '스탠다드 부스 ' + man(a0) + ' · 인화지 700매').length === 0, 'PDF 정상판 통과(가격표 금액만)');
    ok(runPdf(() => '공급 단가: 박스당 230,000원').includes('price-mismatch'), 'PDF — 가격표에 없는 금액을 물었다');
    ok(runPdf(() => null).includes('pdf-unchecked'), 'PDF — 글자를 못 뽑으면 FAIL(확인 안 된 문서)');
  }
  for (const [rule, html] of CASES) {
    const got = run(html);
    ok(got.includes(rule), rule + ' — 합성 결함을 물었다' + (got.includes(rule) ? '' : ' (잡힌 것: ' + (got.join(',') || '없음') + ')'));
  }
  fs.unlinkSync(tmp);
  // 실제 사이트: 지금 페이지는 가격·연결·포함 규칙에 통과해야 하고, 같은 페이지에 결함을 하나 심으면 FAIL 이어야 한다.
  {
    const PRICE_RULES = new Set(['price-mismatch', 'price-binding', 'included-list', 'package-binding', 'empty-row', 'vat-label']);
    const real = (r) => fs.readFileSync(path.join(ROOT, r), 'utf8');
    const runReal = (r, html) => run(html, path.join(ROOT, r), r).filter((x) => PRICE_RULES.has(x));
    const pages = ['index.html', 'pricing.html', 'products.html', 'guide.html', 'products/standard-booth.html', 'products/photo-kiosk.html', 'products/mirror-booth.html'];
    for (const r of pages) {
      const got = runReal(r, real(r));
      ok(got.length === 0, '실제 ' + r + ' 통과' + (got.length ? ' (걸린 것: ' + viol.filter((v) => PRICE_RULES.has(v.rule)).slice(0, 3).map((v) => v.rule + ' ' + v.msg).join(' / ') + ')' : ''));
    }
    const wb = man(it0.wood_buy.amount);
    const sb = man(it0.std_buy.amount);
    let planted = 0;
    const plant = (r, from, to, rule, label, re) => {
      planted++;
      const src = real(r);
      const hit = re ? (re.lastIndex = 0, re.test(src)) : src.includes(from);
      if (re) re.lastIndex = 0;
      if (!hit) return ok(false, '실제 ' + r + ' 심기 실패 — 원문에 "' + (re || from) + '" 없음(' + label + ')');
      const mut = re ? src.replace(re, to) : src.replace(from, to);
      const got = runReal(r, mut);
      ok(got.includes(rule), '실제 ' + r + ' 에 ' + label + ' 심음 → ' + rule + ' FAIL' + (got.includes(rule) ? '' : ' (잡힌 것: ' + (got.join(',') || '없음') + ')'));
    };
    plant('products/photo-kiosk.html', 'data-price-key="wood_buy">' + wb, 'data-price-key="wood_buy">' + sb, 'price-binding', '포토키오스크 구매가를 스탠다드 구매가로');
    plant('pricing.html', null, (m) => m.replace(man(a0 + b0), man(a0 + b0 + 20)), 'price-mismatch', 'FAQ JSON-LD 답변에만 틀린 2대 합계',
      /<script type="application\/ld\+json">\s*\{"@context":"https:\/\/schema\.org","@type":"FAQPage"[\s\S]*?<\/script>/);
    plant('pricing.html', null, (m) => m.replace(man(a0), WRONG), 'price-mismatch', 'og:description 에만 틀린 금액', /<meta property="og:description" content="[^"]*">/);
    plant('index.html', '포토키오스크 ' + wb, '포토키오스크 ' + sb, 'price-binding', '손글 "포토키오스크 구매가" 자리에 스탠다드 구매가');
    plant('products/standard-booth.html', null, '', 'package-binding', '포함 목록에서 설치·회수 삭제', /<li data-item="설치·회수">[\s\S]*?<\/li>/g);
    plant('products/standard-booth.html', '<ul class="ie-list" data-list="included">', '<ul class="ie-list" data-list="included"><li>운송비 별도</li>', 'included-list', "'포함' 목록에 운송비 별도");
    plant('products/standard-booth.html', '</tbody></table><p class="ins-note">', '<tr><th scope="row">전원</th><td></td></tr></tbody></table><p class="ins-note">', 'empty-row', '설치 조건 표에 빈 값 행');
    plant('products/standard-booth.html', '"price":' + it0.std_buy.amount * 10000, '"price":' + it0.wood_buy.amount * 10000, 'price-binding', 'JSON-LD Offer 구매가를 포토키오스크 구매가로');
    console.log(bad ? '\n역검증 FAIL — ' + bad + '/' + n + '건' : '\n역검증 PASS — ' + n + '개 시험(합성 결함 ' + CASES.length + '종 + 실제 페이지에 심은 결함 ' + planted + '종 검출, 정상판·실제 페이지 ' + pages.length + '장 통과)');
  }
  process.exit(bad ? 1 : 0);
}

const argv = process.argv.slice(2);
const files = argv.length ? argv.map((a) => path.resolve(a)) : walk(ROOT);
for (const f of files) checkFile(f, fs.readFileSync(f, 'utf8'));
if (!argv.length) {
  checkSitemap(files);
  checkDataJson(path.join(ROOT, 'data'));
  checkTextFiles();
  checkPdfs();
  checkPriceCoverage();
}

console.log('검사 대상 ' + files.length + '개 HTML');
if (!viol.length) {
  console.log('PASS — 위반 0건');
  process.exit(0);
}
const byRule = {};
for (const v of viol) {
  if (!byRule[v.rule]) byRule[v.rule] = [];
  byRule[v.rule].push(v);
}
for (const rule of Object.keys(byRule)) {
  const list = byRule[rule];
  console.log('\n[' + rule + '] ' + list.length + '건');
  for (const v of list.slice(0, 12)) console.log('  ' + v.file + ': ' + v.msg);
  if (list.length > 12) console.log('  ... 외 ' + (list.length - 12) + '건');
}
console.log('\nFAIL — 위반 ' + viol.length + '건');
process.exit(1);
