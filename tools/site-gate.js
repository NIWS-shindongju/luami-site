#!/usr/bin/env node
/**
 * 루아미 사이트 출고 게이트 (재사용 도구)
 *   node tools/site-gate.js                  전체 HTML 검사
 *   node tools/site-gate.js a.html b.html    지정 파일만
 *
 * 잰다:
 *  1) 태그 균형(section/div/details/a/article)
 *  2) JSON-LD 파싱 유효성
 *  3) 금액 = data/prices.json 대조(2026-10-04~). 가격표에 없는 금액(price-mismatch),
 *     폐기된 옛 금액(price-retired), JSON-LD Offer 가격, 부가세 표기 불일치(vat-label),
 *     가격표 금액이 pricing.html 에 빠짐(price-missing). data/*.json 문자열도 같은 규칙으로 본다.
 *     (예전 '금액 노출 금지'·'제작/판매 표현 금지'는 구매가·커스텀 제작 공개로 폐지)
 *  4) 금지 카피(최저가·지금신청·초특가·파격할인)
 *  5) 경쟁사 실명
 *  6) 이미지 참조 실물 존재 + index 이미지 중복
 *  7) sitemap ↔ 실제 파일 정합
 * 종료코드: 위반 있으면 1
 */
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const COMPETITORS = ['인생네컷', '포토이즘', '하루필름', '포토그레이', '셀픽스', '모노맨션', '인싸포토', '지금이순간', '모멘트컷', '심플큐브', '피키픽', '포토시그니처'];
const BANNED_COPY = [/최저가/, /지금\s*신청/, /초특가/, /파격\s*할인/];
const crypto = require('crypto');

// ── 가격 단일 출처: data/prices.json ─────────────────────────────────────────
// 허용 금액 = 항목 금액 + 규칙(rules.std_total)으로 계산되는 예시 합계 + 1년 비교값.
// 순수 함수로 둔 이유: 셀프테스트에서 합성 가격표로 양방향 시험을 하려고.
function loadPrices(p) {
  return JSON.parse(fs.readFileSync(p || path.join(ROOT, 'data', 'prices.json'), 'utf8'));
}
function allowedWon(P) {
  const it = P.items;
  const s = new Set();
  for (const k of Object.keys(it)) s.add(it[k].amount * 10000);
  const [a, b, c] = P.rules.std_total.map((k) => it[k].amount);
  const total = (u, m) => a + b * (u - 1) + c * u * (m - 1);
  for (const e of P.examples || []) s.add(total(e.units, e.months) * 10000);
  const Y = P.rules.year_months;
  if (Y) {
    s.add(total(1, Y) * 10000);
    s.add(c * (Y - 1) * 10000);
  }
  return s;
}
const sha = (x) => crypto.createHash('sha256').update(String(x)).digest('hex');
// 텍스트에서 금액 표기를 뽑아 원 단위 정수로: 185만원 / 1,850,000원 / ₩1,850,000
// 공백은 [ \t]* 만 허용(줄바꿈을 넘어 '…04\n원형' 같은 오탐 방지). 원가·원본·원형·원목 등 낱말은 제외.
const MONEY_RE = /₩[ \t]*([0-9][0-9,]*)|([0-9][0-9,]*)[ \t]*만[ \t]*원|([0-9][0-9,]*)[ \t]*원(?![가단장본격료칙상형목통래작리인])/g;
function moneyHits(text) {
  const out = [];
  let m;
  MONEY_RE.lastIndex = 0;
  while ((m = MONEY_RE.exec(text))) {
    const raw = m[0].trim();
    let won;
    if (m[1] !== undefined) won = Number(m[1].replace(/,/g, ''));
    else if (m[2] !== undefined) won = Number(m[2].replace(/,/g, '')) * 10000;
    else won = Number(m[3].replace(/,/g, ''));
    if (!won) continue; // 0원
    out.push({ raw, won });
  }
  return out;
}
let PRICES = null;
let ALLOWED = new Set();
let RETIRED = new Set();
function usePrices(P) {
  PRICES = P;
  ALLOWED = allowedWon(P);
  RETIRED = new Set(((P.retired_sha256 || {}).hashes) || []);
}
try {
  usePrices(loadPrices());
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

function checkJsonLd(file, html) {
  const re = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/g;
  let m;
  let n = 0;
  while ((m = re.exec(html))) {
    n++;
    try {
      JSON.parse(m[1]);
    } catch (e) {
      add(file, 'json-ld', '블록 ' + n + ' 파싱 실패: ' + String(e.message).slice(0, 70));
    }
  }
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
  return stripCode(m ? m[0] : html).replace(/<[^>]*>/g, ' ');
}

// 검색결과에 노출되는 문구 (title·description 포함) — 금액·경쟁사는 여기까지 본다.
function exposedText(html) {
  const metas = [];
  const re = /<meta[^>]*name=["'](?:description|keywords)["'][^>]*content=["']([^"']*)["']/gi;
  let m;
  while ((m = re.exec(html))) metas.push(m[1]);
  const t = html.match(/<title>([\s\S]*?)<\/title>/i);
  return bodyText(html) + ' ' + metas.join(' ') + ' ' + (t ? t[1] : '');
}

function checkMoneyText(file, text, where) {
  if (!PRICES) {
    add(file, 'price-mismatch', 'data/prices.json 을 읽지 못함 — 금액 대조 불가');
    return;
  }
  for (const h of moneyHits(text)) {
    if (RETIRED.has(sha(h.won))) add(file, 'price-retired', '폐기된 옛 금액' + (where || '') + ': "' + h.raw + '"');
    else if (!ALLOWED.has(h.won)) add(file, 'price-mismatch', '가격표(data/prices.json)에 없는 금액' + (where || '') + ': "' + h.raw + '"');
  }
}

// JSON-LD 안의 Offer·PriceSpecification 가격도 가격표와 같아야 한다.
function checkOffers(file, html) {
  if (!PRICES) return;
  const re = /<script[^>]*type=["']application\/ld\+json["'][^>]*>([\s\S]*?)<\/script>/g;
  let m;
  while ((m = re.exec(html))) {
    let j;
    try {
      j = JSON.parse(m[1]);
    } catch (e) {
      continue;
    }
    (function walk(o) {
      if (Array.isArray(o)) return o.forEach(walk);
      if (!o || typeof o !== 'object') return;
      const t = [].concat(o['@type'] || []);
      if (o.price !== undefined && t.some((x) => /Offer|PriceSpecification/.test(x))) {
        const won = Number(o.price);
        if (RETIRED.has(sha(won))) add(file, 'price-retired', 'JSON-LD 폐기 금액: ' + o.price);
        else if (!ALLOWED.has(won)) add(file, 'price-mismatch', 'JSON-LD 가격이 가격표에 없음: ' + o.price);
        if (o.priceCurrency && o.priceCurrency !== PRICES.currency) add(file, 'price-mismatch', 'JSON-LD 통화 ' + o.priceCurrency);
      }
      Object.keys(o).forEach((k) => walk(o[k]));
    })(j);
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
  checkVat(file, exposed);
  for (const re of BANNED_COPY) {
    const m = body.match(re);
    if (m) add(file, 'banned-copy', '금지 카피: "' + m[0] + '"');
  }
  for (const c of COMPETITORS) if (exposed.includes(c)) add(file, 'competitor', '경쟁사 실명: "' + c + '"');
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

// 폐기 금액은 HTML·data 밖(문서·메모 .md/.txt 등)에 남아도 공개 URL로 나간다 → 저장소 전체 텍스트를 본다.
function checkRetiredEverywhere() {
  if (!PRICES) return;
  const exts = /\.(md|txt|xml|csv|js|css)$/;
  (function w(d) {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      if (e.name.startsWith('.') || e.name === 'node_modules') continue;
      const p = path.join(d, e.name);
      if (e.isDirectory()) w(p);
      else if (exts.test(e.name) && p !== __filename) {
        const t = fs.readFileSync(p, 'utf8');
        for (const h of moneyHits(t)) if (RETIRED.has(sha(h.won))) add(p, 'price-retired', '폐기된 옛 금액(파일): "' + h.raw + '"');
      }
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

// 규칙 8) sitemap lastmod ↔ 실제 최종수정일
// 순수 함수로 분리한 이유: 합성 입력으로 양방향(정상판 통과 / 결함판 검출) 시험이 가능해야 한다.
// entries = [{loc, lastmod}], dateOf(relPath) -> 'YYYY-MM-DD' | null
function staleLastmod(entries, dateOf) {
  const out = [];
  for (const e of entries) {
    const r = e.loc === '' ? 'index.html' : e.loc;
    if (!r.endsWith('.html')) continue;
    const real = dateOf(r);
    if (!real) continue;
    if (!e.lastmod) {
      out.push({ loc: e.loc, msg: 'lastmod 없음 (실제 수정 ' + real + ')' });
      continue;
    }
    if (e.lastmod < real) out.push({ loc: e.loc, msg: 'lastmod ' + e.lastmod + ' 인데 실제 수정 ' + real });
  }
  return out;
}

function gitDateOf(relPath) {
  try {
    const d = require('child_process')
      .execSync('git log -1 --format=%ad --date=short -- "' + relPath + '"', { cwd: ROOT, encoding: 'utf8' })
      .trim();
    return /^\d{4}-\d{2}-\d{2}$/.test(d) ? d : null;
  } catch (e) {
    return null;
  }
}

function checkSitemap(files) {
  const sp = path.join(ROOT, 'sitemap.xml');
  if (!fs.existsSync(sp)) return;
  const xml = fs.readFileSync(sp, 'utf8');
  const locs = [];
  const re = /<loc>https:\/\/luamiphoto\.com\/([^<]*)<\/loc>/g;
  let m;
  while ((m = re.exec(xml))) locs.push(m[1]);
  for (const l of locs) {
    const r = l === '' ? 'index.html' : l;
    if (r.endsWith('.html') && !fs.existsSync(path.join(ROOT, r))) add(sp, 'sitemap', 'sitemap에 있으나 파일 없음: ' + l);
  }
  const set = new Set(locs.map((l) => (l === '' ? 'index.html' : l)));
  for (const f of files) {
    const r = rel(f);
    if (r === '404.html' || r === 'thanks.html') continue;
    // ★noindex 페이지는 sitemap 완전성 검사에서 뺀다 — 원리는 하드코딩 파일명이 아니라
    // robots 메타다. noindex 페이지를 sitemap에 넣는 건 구글이 스스로 모순 신호라고
    // 지적하는 관행이라(권장하지 않음), 초안/비공개 페이지는 넣지 않는 게 맞다.
    const body = fs.readFileSync(f, 'utf8');
    if (/meta\s+name="robots"[^>]*noindex/i.test(body)) continue;
    if (!set.has(r)) add(sp, 'sitemap', '파일이 sitemap에 없음: ' + r);
  }
  const entries = [];
  const re2 = /<loc>https:\/\/luamiphoto\.com\/([^<]*)<\/loc>\s*<lastmod>([^<]*)<\/lastmod>/g;
  let m2;
  while ((m2 = re2.exec(xml))) entries.push({ loc: m2[1], lastmod: m2[2] });
  for (const l of locs) if (!entries.some((e) => e.loc === l)) entries.push({ loc: l, lastmod: '' });
  for (const v of staleLastmod(entries, gitDateOf)) add(sp, 'stale-lastmod', v.msg + ' — ' + (v.loc || '/'));
}

// --selftest: 결함을 합성해 각 규칙이 실제로 무는지 + 정상판은 통과하는지 양방향 확인.
// 출고 데이터가 나쁘기를 기대하지 않는다 — 대조군을 여기서 직접 만든다.
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
  const REAL = '1개월 미만 ' + man(a0) + ', 2대면 ' + man(a0 + b0) + ', 1대 3개월 ' + man(a0 + 2 * c0) +
    ', 구매 ' + man(it0.std_buy.amount) + ' ' + (vatLabels(P0).cur || '') + '. 포토부스 제작·판매도 합니다.';
  // 폐기 금액 하나를 해시에서 역으로 찾아 쓴다(평문을 이 파일에 싣지 않으려고).
  let RETIRED_MAN = null;
  for (let n = 1; n <= 5000 && RETIRED_MAN === null; n++) if (RETIRED.has(sha(n * 10000))) RETIRED_MAN = n;
  const WRONG = man(a0 + 5); // 가격표에 없는 금액(정찰가 +5만)
  const OTHER_VAT = vatLabels(P0).others[0];
  const offer = (won) => '<script type="application/ld+json">{"@type":"Product","offers":{"@type":"Offer","price":' + won + ',"priceCurrency":"KRW"}}</script>';
  const CLEAN_P = CLEAN.replace('렌탈 문의 주세요.', REAL).replace('</body>', offer(a0 * 10000) + '</body>');
  const CASES = [
    ['price-mismatch', CLEAN_P.replace(REAL, REAL + ' 대여료 150,000원입니다.')],
    ['price-mismatch', CLEAN_P.replace(REAL, REAL + ' 월 30만원부터.')],
    ['price-mismatch', CLEAN_P.replace(man(a0) + ',', WRONG + ',')],
    ['price-mismatch', CLEAN_P.replace('"price":' + a0 * 10000, '"price":' + (a0 + 5) * 10000)],
    ['price-retired', CLEAN_P.replace(REAL, REAL + ' 예전엔 ' + man(RETIRED_MAN || 1) + '이었습니다.')],
    ['vat-label', CLEAN_P.replace(REAL, REAL + ' (' + (OTHER_VAT || '부가세 포함') + ')')],
    ['banned-copy', CLEAN.replace('렌탈 문의 주세요.', '업계 최저가 보장.')],
    ['competitor', CLEAN.replace('렌탈 문의 주세요.', '인생네컷보다 낫습니다.')],
    ['tag-balance', CLEAN.replace('</section>', '')],
    ['json-ld', CLEAN.replace('{"@type":"Thing"}', '{"@type":,}')],
    ['missing-image', CLEAN.replace('assets/images/hero.webp', 'assets/images/__nope__.webp')],
    ['dead-link', CLEAN.replace('<a href="assets/images/hero.webp">', '<a href="__nope__.html">')],
  ];
  const tmp = path.join(ROOT, 'tools', '.gate-selftest.html');
  const run = (html) => {
    viol.length = 0;
    fs.writeFileSync(tmp, html, 'utf8');
    checkBalance(tmp, html);
    checkJsonLd(tmp, html);
    checkCopy(tmp, html);
    checkImages(tmp, html);
    checkLinks(tmp, html);
    return viol.map((v) => v.rule);
  };
  // 규칙 8 stale-lastmod 는 파일이 아니라 (sitemap, git날짜) 쌍을 보므로 별도 대조군으로 시험한다.
  // 대상 데이터가 나빠지길 기다리지 않고 정상판·결함판을 여기서 직접 합성한다.
  const DATES = { 'index.html': '2026-09-08', 'guide.html': '2026-08-06' };
  const dateOf = (r) => DATES[r] || null;
  const lmClean = [
    { loc: '', lastmod: '2026-09-08' },
    { loc: 'guide.html', lastmod: '2026-08-06' },
    { loc: 'assets/x.webp', lastmod: '2020-01-01' },
    { loc: 'unknown.html', lastmod: '2020-01-01' },
  ];
  const lmStale = [
    { loc: '', lastmod: '2026-07-13' },
    { loc: 'guide.html', lastmod: '2026-08-06' },
  ];
  const lmMissing = [{ loc: '', lastmod: '' }];
  let bad = 0;
  {
    const okRes = staleLastmod(lmClean, dateOf);
    if (okRes.length) {
      console.log('  FAIL  stale-lastmod — 정상판이 걸림: ' + okRes.map((v) => v.loc).join(','));
      bad++;
    } else console.log('  ok    stale-lastmod 정상판 통과(최신 lastmod·비HTML·미추적 파일 오탐 없음)');
    const st = staleLastmod(lmStale, dateOf);
    if (st.length === 1 && st[0].loc === '') console.log('  ok    stale-lastmod — 낡은 lastmod 를 물었다');
    else {
      console.log('  FAIL  stale-lastmod — 낡은 lastmod 를 놓쳤다 (' + st.length + '건)');
      bad++;
    }
    const ms = staleLastmod(lmMissing, dateOf);
    if (ms.length === 1) console.log('  ok    stale-lastmod — lastmod 누락을 물었다');
    else {
      console.log('  FAIL  stale-lastmod — lastmod 누락을 놓쳤다');
      bad++;
    }
  }
  const clean = run(CLEAN);
  if (clean.length) {
    console.log('  FAIL  정상판이 걸림: ' + clean.join(','));
    bad++;
  } else console.log('  ok    정상판 통과(오탐 없음)');
  if (RETIRED_MAN === null) {
    console.log('  FAIL  prices.json retired_sha256 에서 폐기 금액을 찾지 못함 — price-retired 시험 불가');
    bad++;
  }
  const cleanP = run(CLEAN_P);
  if (cleanP.length) {
    console.log('  FAIL  가격표 금액·예시 합계·JSON-LD Offer·제작/판매 문구를 넣은 정상판이 걸림: ' + cleanP.join(','));
    bad++;
  } else console.log('  ok    가격 정상판 통과 — 가격표 금액·계산 예시·Offer·"제작·판매" 문구 오탐 없음');
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
    if (okD.length) {
      console.log('  FAIL  data JSON 정상판이 걸림: ' + okD.join(','));
      bad++;
    } else console.log('  ok    data JSON 정상판 통과');
    if (badD.includes('price-mismatch')) console.log('  ok    data JSON — 틀린 금액을 물었다');
    else {
      console.log('  FAIL  data JSON — 틀린 금액을 놓쳤다');
      bad++;
    }
  }
  for (const [rule, html] of CASES) {
    const got = run(html);
    if (got.includes(rule)) console.log('  ok    ' + rule + ' — 합성 결함을 물었다');
    else {
      console.log('  FAIL  ' + rule + ' — 합성 결함을 놓쳤다 (잡힌 것: ' + (got.join(',') || '없음') + ')');
      bad++;
    }
  }
  fs.unlinkSync(tmp);
  console.log(bad ? '\n역검증 FAIL — ' + bad + '건' : '\n역검증 PASS — 결함 ' + (CASES.length + 4) + '종 검출 + 정상판 대조군 3종 통과');
  process.exit(bad ? 1 : 0);
}

const argv = process.argv.slice(2);
const files = argv.length ? argv.map((a) => path.resolve(a)) : walk(ROOT);
for (const f of files) {
  const html = fs.readFileSync(f, 'utf8');
  checkBalance(f, html);
  checkJsonLd(f, html);
  checkCopy(f, html);
  checkImages(f, html);
  checkLinks(f, html);
}
if (!argv.length) {
  checkSitemap(files);
  checkDataJson(path.join(ROOT, 'data'));
  checkRetiredEverywhere();
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
