# email-pool-manager

邮箱池管理 + OpenAI 账号注册系统。批量注册临时邮箱（mail.tm / Tempmail.lol）、导入已有 IMAP 邮箱，集中托管并持续探活，可选按目标存量自动补池；同时保留上游完整的 OpenAI 批量注册 / Token 管理 / NewAPI 同步能力。

> 来源声明：基于 [asasugar/AIAccountPoolX](https://github.com/asasugar/AIAccountPoolX)（MIT License）改造，新增邮箱池管理与 mail.tm 支持等能力，原 LICENSE 保留。
>
> ⚠️ 免责声明：本项目仅供学习、研究和内部测试使用。请自行遵守相关平台条款和当地法律法规，不要用于违法或滥用场景。

## 核心功能

### 邮箱池管理（本项目新增的重点）

- **平台化批量注册**：左侧平台列表新增 `Mail.tm` / `Tempmail.lol` 两个平台，复用标准任务控件（数量/间隔/并发/启停/成功失败统计），`count=0` 无限创建；任务创建的邮箱自动入池
- **批量自动注册**：mail.tm（内置 ~6s/个 节流与 429 退避）、Tempmail.lol 一键批量建号；IMAP 邮箱（QQ/Outlook 等）手动导入纳管
- **托管**：邮箱实体落库（地址/密码/收信 token/远端账号 id），支持用途备注、搜索过滤、分页
- **存活检测**：mail.tm 探活 = 重登校验（兼做保活）+ 域名下线检查；Tempmail.lol 探活 = inbox 可用性（该服务邮箱天然短时效，判死属预期）；IMAP 探活 = 登录校验
- **调度**：定时全量探活（默认 24h，可关）+ 手动单条/全量探活
- **自动补池**：配置目标存活数后，探活发现不足自动补建（默认关闭）
- **注册联动**：OpenAI 注册流程创建的临时邮箱可自动入池（可关）
- **删除**：本地移除 + mail.tm 远端账号真删（purge_remote）

### 继承自上游的能力

- OpenAI HTTP/OAuth 批量注册、并发控制、统计
- Token 刷新/占用/释放、账号-Token 关联、NewAPI 渠道同步
- Tempmail.lol / IMAP（含 Outlook OAuth2）/ QQ 邮箱多源验证码轮询
- 代理池（静态/动态 API）、可选 AWS API Gateway IP 轮换
- Vue 3 + Element Plus 三栏控制台、WebSocket 实时日志

## 部署

### Docker Compose（推荐）

```bash
cp packages/backend/config.example.json packages/backend/config.json  # 本地调试
# 或 NAS/服务器部署：准备 deploy/config.json（不入库）后：
docker compose up -d --build
```

- 后端：容器内 1455（宿主映射见 `docker-compose.yml`，默认 1456）
- 前端：nginx 80（默认映射 3081）
- 容器出网代理：通过 `HTTP_PROXY/HTTPS_PROXY` 环境变量注入（compose 中已示例指向本机代理）
- 数据：SQLite（`backend-data` 卷）；配置：`/app/runtime/config.json`

### 启动邮箱池

1. 打开 Web UI → 右栏切换「邮箱池」
2. 选择 provider（Mail.tm / Tempmail.lol），填数量，点「批量创建」（后台任务，进度看实时日志）
3. 点「全部探活」确认存活；在设置区可开定时探活与自动补池

## 配置说明

| 配置项 | 默认 | 说明 |
|---|---|---|
| `email_pool_check_interval_hours` | 24 | 定时全量探活间隔（小时），0=关闭 |
| `email_pool_target_size` | 0 | mail.tm 目标存活数，探活后自动补建，0=关闭 |
| `email_pool_auto_capture` | true | OpenAI 注册创建的临时邮箱自动入池 |

邮箱源预设（mail.tm / Tempmail.lol / QQ / Outlook）在 Web UI「系统配置」中切换，`active_email_preset` 决定注册用哪个邮箱源。

## 开发

```bash
pnpm install:all   # 前端 pnpm + 后端 pip 依赖
pnpm dev           # 前端 :3000 / 后端 :1455
```

- 后端：FastAPI + SQLAlchemy（SQLite）+ httpx；前端：Vue 3 + TS + Vite + Element Plus
- 邮箱池后端代码：`app/email_pool.py`（服务）、`app/api/emails.py`（API）、`app/email_utils/mailtm.py`（mail.tm 客户端）、`app/email_utils/pool_health.py`（探活）

## License

MIT（沿用上游）
