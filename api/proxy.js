// Vercel serverless function with extra debug logging.
// مسیر: /api/proxy
// این فایل را در ریشهٔ پروژه داخل پوشهٔ `api/` قرار دهید.
// روی Vercel: متغیر محیطی API_KEY را در Settings پروژه قرار دهید.
export default async function handler(req, res) {
  // Set CORS dynamically to the request origin to avoid browser blocking in browsers
  const origin = req.headers['origin'] || req.headers['referer'] || '*';
  // For safety, if origin is undefined or 'null', fallback to '*'
  const allowOrigin = origin && origin !== 'null' ? origin : '*';
  res.setHeader('Access-Control-Allow-Origin', allowOrigin);
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    console.log('[proxy] Method not allowed:', req.method);
    return res.status(405).json({ error: 'Method not allowed' });
  }

  const API_KEY = process.env.API_KEY;
  if (!API_KEY) {
    console.log('[proxy] Missing API_KEY in env');
    return res.status(500).json({ error: 'Server missing API_KEY environment variable' });
  }

  const body = req.body || {};
  const target = body.endpoint || 'https://tabitoken.com/v1/chat/completions';
  const model = body.model;
  const messages = body.messages;

  console.log('[proxy] Incoming request. origin=', req.headers['origin'] || req.headers['host'], 'target=', target);
  console.log('[proxy] Model=', model);
  // Log a trimmed preview of messages for debugging (avoid logging huge payloads)
  try {
    const preview = JSON.stringify(messages ? messages.slice(0,5) : []);
    console.log('[proxy] Messages preview=', preview);
  } catch (e) {
    console.log('[proxy] Could not stringify messages preview', e);
  }

  if (!model || !messages) {
    console.log('[proxy] Bad request: missing model or messages');
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

    console.log('[proxy] Upstream status=', r.status);
    // Log upstream response body truncated to reasonable length
    const truncated = text && text.length > 1000 ? text.slice(0,1000) + '... [truncated]' : text;
    console.log('[proxy] Upstream response (truncated)=', truncated);

    try {
      const json = JSON.parse(text);
      return res.status(r.status).json(json);
    } catch (e) {
      // not JSON
      return res.status(r.status).send(text);
    }
  } catch (err) {
    console.error('[proxy] Fetch error:', err);
    return res.status(500).json({ error: String(err) });
  }
}
