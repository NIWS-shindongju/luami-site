#!/usr/bin/env node
/**
 * 루아미 사이트 출고 게이트 (재사용 도구)
 *   node tools/site-gate.js                  전체 HTML 검사
 *   node tools/site-gate.js a.html b.html    지정 파일만
 *
 * 잰다:
 *  1) 태그 균형(section/div/details/a/article)
 *  2) JSON-LD 파싱 유효성
 *  3) 금액 노출(브랜드 가드레일 — 숫자+원 / ₩ / 만원)
 *  4) 금지 카피(최저가·지금신청·하루만) + 렌탈 아닌 서비스 표현
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
// ★2026-09-27 L49 — 동주님이 제품 확정 가격표(판매·렌탈)를 공개하기로 하면서 "부스 판매" 표현은
// 더 이상 과장이 아니라 사실 표기다(컨셉 부스는 판매만·렌탈 불가). "포토부스 제작"(주문 제작 서비스로
// 오인될 표현)만 계속 막는다.
const BANNED_SERVICE = /포토부스\s*(를)?\s*제작/;
const MONEY = [/[0-9][0-9,]*\s*원(?![가단장본격료칙상])/g, /₩\s*[0-9]/g, /[0-9][0-9,]*\s*만\s*원/g];
const MONEY_OK = [/^0\s*원$/, /무료/];
// ★2026-09-27 L49 — 가격 가드레일 방향 전환: "금액 노출 자체를 금지"가 아니라
// "이 표에 없는 숫자가 원 단위로 노출되면 막는다"(오탈자·구권가 잔존 방지).
// tools/prices.json 이 단일 출처(products.html·guide.html 모두 이 값만 써야 한다).
const PRICES_PATH = path.join(__dirname, 'prices.json');
const CANONICAL_PRICES = new Set(
  JSON.parse(fs.readFileSync(PRICES_PATH, 'utf8')).items.flatMap((it) => it.amounts)
);

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

function checkCopy(file, html) {
  const body = bodyText(html);
  const exposed = exposedText(html);
  for (const re of MONEY) {
    const hits = exposed.match(re) || [];
    for (const hit of hits) {
      const h = hit.trim().replace(/\s+/g, '');
      if (MONEY_OK.some((ok) => ok.test(h))) continue;
      if (CANONICAL_PRICES.has(h)) continue;
      add(file, 'price-mismatch', '가격표(tools/prices.json)에 없는 금액 노출: "' + h + '"');
    }
  }
  for (const re of BANNED_COPY) {
    const m = body.match(re);
    if (m) add(file, 'banned-copy', '금지 카피: "' + m[0] + '"');
  }
  const sm = body.match(BANNED_SERVICE);
  if (sm) add(file, 'service-wording', '렌탈 아닌 표현: "' + sm[0] + '"');
  for (const c of COMPETITORS) if (exposed.includes(c)) add(file, 'competitor', '경쟁사 실명: "' + c + '"');
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

// 규칙 9) 가격표(tools/prices.json)의 모든 확정 금액이 사이트 어딘가(전형적으로 products.html·guide.html)에
// 실제로 노출되는지 — 틀린 값이 아니라 "빠진 값"도 잡는다. 전체 스캔(파일 지정 없을 때)에서만 돈다.
function checkPriceCoverage(files) {
  const seen = new Set();
  for (const f of files) {
    const html = fs.readFileSync(f, 'utf8');
    const exposed = exposedText(html);
    for (const re of MONEY) {
      const hits = exposed.match(re) || [];
      for (const hit of hits) seen.add(hit.trim().replace(/\s+/g, ''));
    }
  }
  for (const amt of CANONICAL_PRICES) {
    if (!seen.has(amt)) add(PRICES_PATH, 'price-missing', '가격표에 있지만 사이트에 노출되지 않음: "' + amt + '"');
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
  // 가격표(tools/prices.json)에 실제로 있는 값 하나를 대조군으로 쓴다 — "정상판이 걸리면 안 되는" 시험이라
  // canonical 값을 하드코딩하지 않고 실제 파일에서 가져와야 표가 바뀌어도 selftest가 계속 맞다.
  const REAL_PRICE = [...CANONICAL_PRICES][0];
  const CASES = [
    ['price-mismatch', CLEAN.replace('렌탈 문의 주세요.', '대여료 150,000원입니다.')],
    ['price-mismatch', CLEAN.replace('렌탈 문의 주세요.', '월 30만원부터.')],
    // 틀린 값(가격표에 없는 숫자)을 끼워 넣으면 문다 — "얼마나 최근 값인지"가 아니라 "표와 다른 숫자"를 잡는 시험.
    // 5,555,555원은 실제 가격표 12개 항목 중 무엇과도 겹치지 않는 합성값(우연한 충돌 방지를 위해 고정값 사용).
    ['price-mismatch', CLEAN.replace('렌탈 문의 주세요.', '이번만 5,555,555원에 드립니다.')],
    ['banned-copy', CLEAN.replace('렌탈 문의 주세요.', '업계 최저가 보장.')],
    ['service-wording', CLEAN.replace('렌탈 문의 주세요.', '포토부스 제작해 드립니다.')],
    ['competitor', CLEAN.replace('렌탈 문의 주세요.', '인생네컷보다 낫습니다.')],
    ['tag-balance', CLEAN.replace('</section>', '')],
    ['json-ld', CLEAN.replace('{"@type":"Thing"}', '{"@type":,}')],
    ['missing-image', CLEAN.replace('assets/images/hero.webp', 'assets/images/__nope__.webp')],
    ['dead-link', CLEAN.replace('<a href="assets/images/hero.webp">', '<a href="__nope__.html">')],
  ];
  // 정상판 대조군: 가격표에 있는 실제 금액을 노출해도 걸리지 않아야 한다("금액 자체 금지"가 아니므로).
  const CLEAN_WITH_REAL_PRICE = CLEAN.replace('렌탈 문의 주세요.', '판매 ' + REAL_PRICE + '입니다.');
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
  const cleanPrice = run(CLEAN_WITH_REAL_PRICE);
  if (cleanPrice.length) {
    console.log('  FAIL  가격표 실제 금액(' + REAL_PRICE + ')을 노출한 정상판이 걸림: ' + cleanPrice.join(','));
    bad++;
  } else console.log('  ok    가격표 실제 금액(' + REAL_PRICE + ') 노출 — 정상판 통과(금액 자체는 안 막는다)');
  for (const [rule, html] of CASES) {
    const got = run(html);
    if (got.includes(rule)) console.log('  ok    ' + rule + ' — 합성 결함을 물었다');
    else {
      console.log('  FAIL  ' + rule + ' — 합성 결함을 놓쳤다 (잡힌 것: ' + (got.join(',') || '없음') + ')');
      bad++;
    }
  }
  fs.unlinkSync(tmp);
  console.log(bad ? '\n역검증 FAIL — ' + bad + '건' : '\n역검증 PASS — 10개 규칙 + 정상판 대조군 전부 정상');
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
  checkPriceCoverage(files);
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
