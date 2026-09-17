// 정보통신망법 §50④⑥⑦ + 시행령 별표6 준수: 원클릭 수신거부, 로그인/추가입력 요구 없음,
// 처리 즉시 결과 통지(전송자 명칭·의사표시 사실 및 날짜·처리결과).
const crypto = require('crypto');
const { getStore } = require('@netlify/blobs');

function verify(email, sig, secret) {
  const expected = crypto.createHmac('sha256', secret).update(email.toLowerCase().trim()).digest('base64url');
  const a = Buffer.from(expected);
  const b = Buffer.from(sig || '');
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

function page(title, body) {
  return `<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>${title}</title>
<style>body{font-family:-apple-system,'Malgun Gothic',sans-serif;max-width:480px;margin:80px auto;padding:0 24px;color:#1F2417;line-height:1.7}
h1{font-size:20px}p{color:#444;font-size:15px}.brand{color:#8a8578;font-size:13px;margin-top:32px;border-top:1px solid #eee;padding-top:16px}</style>
</head><body>${body}<div class="brand">LUAMI 루아미 — luamiphoto.com</div></body></html>`;
}

exports.handler = async (event) => {
  const secret = process.env.UNSUB_SECRET;
  const { e, s, admin } = event.queryStringParameters || {};
  const store = getStore('luami-unsubscribes');

  // 관리용 목록 조회 (동일 secret 헤더 필요, 발송 파이프라인이 동기화 시 사용)
  if (admin) {
    if (admin !== secret) return { statusCode: 403, body: 'forbidden' };
    const { blobs } = await store.list();
    const records = await Promise.all(blobs.map(async (b) => JSON.parse(await store.get(b.key))));
    return { statusCode: 200, headers: { 'content-type': 'application/json' }, body: JSON.stringify(records) };
  }

  if (!e || !s) {
    return { statusCode: 400, headers: { 'content-type': 'text/html; charset=utf-8' }, body: page('잘못된 요청', '<h1>잘못된 요청입니다</h1><p>수신거부 링크가 올바르지 않습니다.</p>') };
  }

  let email;
  try { email = Buffer.from(e, 'base64url').toString('utf-8'); } catch { email = ''; }

  if (!email || !secret || !verify(email, s, secret)) {
    return { statusCode: 400, headers: { 'content-type': 'text/html; charset=utf-8' }, body: page('잘못된 요청', '<h1>잘못된 요청입니다</h1><p>수신거부 링크가 올바르지 않거나 위조되었습니다.</p>') };
  }

  const now = new Date(event.headers && event.headers['x-nf-request-time'] ? Number(event.headers['x-nf-request-time']) : Date.now());
  const dateStr = now.toISOString().slice(0, 10);
  const key = email.toLowerCase().trim();
  await store.setJSON(key, { email: key, requestedAt: now.toISOString(), source: 'unsubscribe-link' });

  const isOneClickPost = event.httpMethod === 'POST';
  const html = page(
    '수신거부 처리완료 / Unsubscribed',
    `<h1>수신거부가 처리되었습니다</h1>
     <p><b>전송자:</b> 루아미 LUAMI (luami@luamiphoto.com)</p>
     <p><b>대상 이메일:</b> ${key}</p>
     <p><b>요청 일자:</b> ${dateStr}</p>
     <p><b>처리 결과:</b> 즉시 처리되었으며, 앞으로 이 주소로 광고성 정보를 발송하지 않습니다.</p>
     <hr>
     <p style="color:#999;font-size:13px">Your unsubscribe request for <b>${key}</b> was processed immediately on ${dateStr}. You will not receive further marketing emails from LUAMI at this address.</p>`
  );

  return {
    statusCode: isOneClickPost ? 202 : 200,
    headers: { 'content-type': 'text/html; charset=utf-8' },
    body: html,
  };
};
