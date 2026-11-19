import PostalMime from "postal-mime";

function json(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Headers": "Authorization, Content-Type",
      "Access-Control-Allow-Methods": "GET, POST, DELETE, OPTIONS",
    },
  });
}

function authorized(request, env) {
  if (!env.EMAIL_POOL_TOKEN) return false;
  const header = request.headers.get("Authorization") || "";
  const token = header.replace(/^Bearer\s+/i, "").trim();
  return token === env.EMAIL_POOL_TOKEN;
}

export default {
  // Email Routing catch-all -> this Worker
  async email(message, env, ctx) {
    const to = String(message.to || "").toLowerCase().trim();
    const from = String(message.from || "");
    const subject = message.headers.get("subject") || "";
    let text = "";
    let html = "";
    try {
      const buffer = await new Response(message.raw).arrayBuffer();
      const parsed = await PostalMime.parse(buffer);
      text = parsed.text || "";
      html = typeof parsed.html === "string" ? parsed.html : "";
    } catch (e) {
      text = "[parse error] " + (e && e.message ? e.message : String(e));
    }
    await env.DB.prepare(
      "INSERT INTO messages (address, sender, subject, text, html, received_at) VALUES (?, ?, ?, ?, ?, ?)"
    )
      .bind(to, from, subject, text, html, new Date().toISOString())
      .run();
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;

    if (request.method === "OPTIONS") return json({ ok: true });
    if (path === "/health") return json({ ok: true });

    if (!authorized(request, env)) {
      return json({ ok: false, error: "unauthorized" }, 401);
    }

    // POST /v1/addresses  {address}
    if (request.method === "POST" && path === "/v1/addresses") {
      let body = {};
      try {
        body = await request.json();
      } catch {}
      const address = String(body.address || "").toLowerCase().trim();
      if (!address || !address.includes("@")) {
        return json({ ok: false, error: "invalid address" }, 400);
      }
      await env.DB.prepare(
        "INSERT INTO addresses (address, created_at) VALUES (?, ?) ON CONFLICT(address) DO NOTHING"
      )
        .bind(address, new Date().toISOString())
        .run();
      return json({ ok: true, address });
    }

    // GET /v1/addresses
    if (request.method === "GET" && path === "/v1/addresses") {
      const { results } = await env.DB.prepare(
        "SELECT address, created_at FROM addresses ORDER BY created_at DESC LIMIT 1000"
      ).all();
      return json({ ok: true, items: results || [] });
    }

    // GET /v1/messages?address=...&limit=
    if (request.method === "GET" && path === "/v1/messages") {
      const address = (url.searchParams.get("address") || "").toLowerCase().trim();
      const limit = Math.min(Math.max(parseInt(url.searchParams.get("limit") || "20", 10) || 20, 1), 100);
      const columns =
        "id, address, sender, subject, received_at, substr(coalesce(text,''), 1, 500) AS preview";
      const stmt = address
        ? env.DB.prepare(
            `SELECT ${columns} FROM messages WHERE address = ? ORDER BY id DESC LIMIT ?`
          ).bind(address, limit)
        : env.DB.prepare(`SELECT ${columns} FROM messages ORDER BY id DESC LIMIT ?`).bind(limit);
      const { results } = await stmt.all();
      return json({ ok: true, items: results || [] });
    }

    const byId = path.match(/^\/v1\/messages\/(\d+)$/);
    if (byId && request.method === "GET") {
      const row = await env.DB.prepare("SELECT * FROM messages WHERE id = ?")
        .bind(Number(byId[1]))
        .first();
      if (!row) return json({ ok: false, error: "not found" }, 404);
      return json({ ok: true, item: row });
    }

    if (byId && request.method === "DELETE") {
      await env.DB.prepare("DELETE FROM messages WHERE id = ?").bind(Number(byId[1])).run();
      return json({ ok: true });
    }

    return json({ ok: false, error: "not found" }, 404);
  },
};
