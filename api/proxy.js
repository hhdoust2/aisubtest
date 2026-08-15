// Vercel serverless function (Node 18+ runtime assumed).
// مسیر: /api/proxy
// این فایل را در ریشهٔ پروژه داخل پوشه‌ی `api/` قرار دهید.
// روی Vercel: متغیر محیطی API_KEY را در Settings پروژه قرار دهید.
export default async function handler(req, res) {
  // اجازهٔ CORS برای تست محلی/مرورگر (اگر فرانت‌اند شما از همان دامنه لود می‌شود، مشکلی نیست).
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const API_KEY = process.env.API_KEY;
  if (!API_KEY) {
    return res.status(500).json({ error: 'Server missing API_KEY environment variable' });
  }

  const body = req.body || {};
  const target = body.endpoint || 'https://tabitoken.com/v1/chat/completions';
  const model = body.model;
  const messages = body.messages;

  if (!model || !messages) {
    return res.status(400).json({ error: 'Missing required fields: model and messages' });
  }

  try {
    const r = await fetch(target, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + API_KEY
      },
      body: JSON.stringify({ model, messages })
    });

    const text = await r.text();
    try {
      const json = JSON.parse(text);
      res.status(r.status).json(json);
    } catch (e) {
      res.status(r.status).send(text);
    }
  } catch (err) {
    console.error('proxy error', err);
    res.status(500).json({ error: String(err) });
  }
}
