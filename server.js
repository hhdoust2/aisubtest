// سرور محلی نمونه (برای تست لوکال). اجرا: npm install && node server.js
// این سرور یک endpoint /proxy فراهم می‌کند که مشابه فانکشن Vercel عمل می‌کند.
const express = require('express');
const cors = require('cors');
const fetch = require('node-fetch'); // v2
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json({ limit: '1mb' }));

const API_KEY = process.env.API_KEY;
if (!API_KEY) {
  console.warn('هشدار: API_KEY در متغیرهای محیطی تنظیم نشده. از requestهای مستقیم استفاده نکنید.');
}

app.post('/proxy', async (req, res) => {
  const { endpoint, model, messages } = req.body;
  const target = endpoint || 'https://tabitoken.com/v1/chat/completions';
  if (!API_KEY) return res.status(500).json({ error: 'Server missing API_KEY' });
  if (!model || !messages) return res.status(400).json({ error: 'Missing model or messages' });

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
    console.error(err);
    res.status(500).json({ error: err.message || String(err) });
  }
});

const port = process.env.PORT || 3000;
app.listen(port, () => console.log('Local proxy listening on', port));
