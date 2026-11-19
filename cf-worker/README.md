# email-pool-worker（Cloudflare Email Worker）

corekiln.com 收信基础设施：Email Routing catch-all → 本 Worker → 解析 MIME 存 D1 → Bearer API 读取。
email-pool-manager 的 `corekiln` provider 通过该 API 建地址、查信、取验证码。

## 部署（zone 已迁移到 Cloudflare 后）

```bash
cd cf-worker
npm install                      # postal-mime
npx wrangler login               # 或 CLOUDFLARE_API_TOKEN 环境变量
npx wrangler d1 create email-pool          # 记下 database_id 回填 wrangler.toml
npx wrangler d1 execute email-pool --remote --file schema.sql
npx wrangler secret put EMAIL_POOL_TOKEN   # 自定义一串强随机 token
npx wrangler deploy
```

路由（避免 workers.dev 在国内访问不稳，走自有域名）：

- Cloudflare Dashboard → Workers → email-pool-worker → Settings → Triggers → Add route：
  `email-api.corekiln.com/*`（zone: corekiln.com）
- DNS 添加占位记录（Proxied）：`AAAA email-api → 100::`（或 A → 192.0.2.1）

## Email Routing

Dashboard → Email → Email Routing → Enable（自动写入 MX 与 SPF）→ Catch-all → Send to Worker → `email-pool-worker`。
`support@corekiln.com` 如需继续转发：添加一条自定义地址规则（优先级高于 catch-all）。

## API

鉴权：`Authorization: Bearer $EMAIL_POOL_TOKEN`

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 免鉴权健康检查 |
| POST | `/v1/addresses` `{address}` | 登记地址（catch-all 本身已收；登记用于管理） |
| GET | `/v1/addresses` | 地址列表 |
| GET | `/v1/messages?address=a@corekiln.com&limit=20` | 按地址列最新邮件（含 500 字预览） |
| GET | `/v1/messages/{id}` | 邮件全文（text/html） |
| DELETE | `/v1/messages/{id}` | 删除邮件 |
