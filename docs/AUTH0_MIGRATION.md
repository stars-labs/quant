# GoTrue → Auth0 迁移 Runbook

状态跟踪（完成后勾选）：

- [x] Stage 2 — DB 迁移 `031_auth0_migration.sql` 已应用（2026-07-28，双读兼容，GoTrue 照常工作）
- [x] Stage 3 — 前端已改为 auth0-spa-js + Universal Login（等 tenant 参数填入后才可部署）
- [x] Stage 1 — Auth0 tenant 配置 + 19 用户导入（2026-07-29 经 Management API 自动完成，见下方「实际配置记录」；**遗留一步：GCP redirect URI**）
- [x] Stage 4 — 切换完成（2026-07-29 18:20-18:50 CST）。要点/偏差记录：
  - arm-002 上 `nixos-rebuild` 包装脚本会静默卡死，实际用 `nix build .#...toplevel` + `switch-to-configuration switch`（gen 197）。
  - **构建时 nixpkgs 被 override 回线上旧版 `567a49d`**：main 的 flake.lock（20260723）里 datadog-agent 的 python3.14 集成在 aarch64 构建失败。下次 `nix flake update` 前要先解决 datadog（升级/裁剪），否则复现。
  - Realtime 没有自动 seed 租户：按 STACK.md 走 Admin API `POST /api/tenants` 重建了 quant 租户（新密钥）。WS 验证：新 anon JWT 101 / 错密钥 403。
  - `ensure_user()` 初版在 PostgREST 只读事务（GET）里 INSERT 报 25006，已改为仅在读写事务执行（031 已同步修正）。
  - Auth0 SPA 回调白名单补上了 `starslab.qzz.io` 与 `quant.freeman-xiong.workers.dev`（7 月 Cloudflare 迁移后的实际域名）。
  - 验证全绿：anon 200 / Auth0 token RLS 归属本人 / GoTrue 形态 401 / auth-only 视图 200 / 新用户写入 201（ensure_user 落库）/ auth.panda.qzz.io 404 / SSR 门禁 303 / 三个 nautilus 服务 active。
- [ ] Stage 5 — 退役清理（稳定 ≥1 周后，`032_retire_gotrue.sql`）

架构约定（全部代码已按此实现）：

- Auth0 API 用 **HS256** 签名，signing secret 写入 sops `oracle-arm-002/jwt-secret`（方向：Auth0 生成 → 抄进 sops；不可反向自定义）。
- 用户身份 = **namespaced custom claims**（post-login Action 注入）：
  - `https://panda.qzz.io/uid` — 稳定 UUID（老用户 = 原 GoTrue `auth.users.id`；新用户首登生成）。DB 的 `auth.uid()`、前端 `session.user.sub`都读它。
  - `https://panda.qzz.io/role` — 恒为 `authenticated`（PostgREST 的 role-claim）。
  - `https://panda.qzz.io/email`。
- `auth.uid()` 等函数已是双读版（namespaced 优先，回退旧 `sub`），业务表 FK 已指向 `quant.users` 影子表。

---

## Stage 1 实际配置记录（2026-07-29，tenant `autolife.jp.auth0.com`，与其他项目共用）

| 资源 | 值 |
|---|---|
| API | `quant PostgREST`，id `6a69abfab599a9f59794e314`，identifier `https://api.panda.qzz.io`，**HS256**，exp 3600，offline access ✅ |
| SPA 应用 | `quant dashboard`，client_id `8aAbuMhZlFa94TbPozNZIKSxfSlv0B4r`（已写入前端 config.ts 默认值），rotating refresh token 30d/idle 15d |
| Google connection | `con_GmTEkT2c9JgH0GKJ`，已配 GCP client `903515141994-…` + sops 里的 secret，已启用给 SPA |
| DB connection | `con_49RxAhPbfPHqsQsq`（Username-Password-Authentication），密码 ≥8 位，signup 开，已启用给 SPA |
| Action | `quant-claims`，id `1c39707f-84ed-471c-9664-fb7da2acd42d`，已部署并绑定 post-login（tenant 里唯一 binding），Secret `LEGACY_GOOGLE_MAP` 已配 2 个 Google 用户映射 |
| 用户导入 | job `job_eYkxvf5g8P14s5Oe`：17/17 成功 0 失败，逐个核对 `app_metadata.legacy_uid` 与 `auth.users.id` 一致 |
| E2E 验证 | 临时用户走 ROPG：token `alg=HS256`（签名与 API signing secret 吻合）、`aud=https://api.panda.qzz.io`、三个 namespaced claims 正确、新用户路径自动生成 UUID 并写回 app_metadata。测试用户与 password grant 已清理 |

**遗留手工步骤（Google 登录生效前必须做）**：GCP Console → Credentials → OAuth Client `903515141994-…` → Authorised redirect URIs **新增** `https://autolife.jp.auth0.com/login/callback`（否则 Google 登录报 redirect_uri_mismatch；邮箱密码登录不受影响）。

切换日取 signing secret：Dashboard → APIs → quant PostgREST → Settings → Signing Secret（或 Management API `GET /resource-servers/6a69abfab599a9f59794e314`）。

注意：tenant 的 `default_directory` 已设为 `Username-Password-Authentication`（E2E 测试需要，保留无害）。

## Stage 1 — Auth0 tenant（Dashboard 手工操作，已由上表覆盖，留作参考）

### 1. API

APIs → Create API：

| 项 | 值 |
|---|---|
| Identifier | `https://api.panda.qzz.io`（建后不可改） |
| Signing Algorithm | **HS256** |
| Token Expiration | 3600 |
| Allow Offline Access | ✅ |

⚠️ **第一件事就验证**：用下面建好的 SPA 走一次登录，jwt.io 查 access token header 必须是 `alg: HS256`。若 tenant 拒绝 SPA+HS256 组合，整个方案要回退 RS256 重新评估（Realtime 不支持 RS256）——先验证再做后续步骤。

Signing Secret 在 API → Settings 页可见，Stage 4 时抄进 sops。

### 2. Application（SPA）

Applications → Create → Single Page Application：

- Allowed Callback URLs：`https://quant.panda.qzz.io/auth/callback, https://quant.xiongchenyu6.workers.dev/auth/callback, http://localhost:5173/auth/callback`
- Allowed Logout URLs / Allowed Web Origins：`https://quant.panda.qzz.io, https://quant.xiongchenyu6.workers.dev, http://localhost:5173`
- Refresh Token Rotation：✅（Absolute Lifetime 建议 30 天）

记下 **Domain** 和 **Client ID** → 前端构建变量：
`VITE_AUTH0_DOMAIN` / `VITE_AUTH0_CLIENT_ID` / `VITE_AUTH0_AUDIENCE=https://api.panda.qzz.io`
（`web/apps/app/src/lib/config.ts` 读取；本地 dev 放 `.env.local`，生产写进 `wrangler.jsonc` vars 或构建环境。）

### 3. Database Connection

默认 `Username-Password-Authentication` 即可：signup 开启，密码策略 ≥8 位（对齐 GoTrue 现状，无邮箱验证要求）。

### 4. Google Social Connection

- Authentication → Social → Google：填现有 GCP OAuth Client（id `903515141994-i4q7kuslcjsff955t8vt1fmre2jh9gk0.apps.googleusercontent.com`）+ secret（sops `oracle-arm-002/google-oauth-secret`）。
- GCP Console → 该 Client → Authorised redirect URIs **新增** `https://<tenant>.auth0.com/login/callback`（旧的 `https://auth.panda.qzz.io/callback` 切换完成后再删）。

### 5. Post-Login Action

Actions → Library → Build Custom → Login / Post Login，代码：

```js
exports.onExecutePostLogin = async (event, api) => {
  const NS = 'https://panda.qzz.io';
  let uid = event.user.app_metadata && event.user.app_metadata.legacy_uid;
  if (!uid) {
    // 2 个 Google 老用户无法带密码导入，用 email→uuid 映射兜底；
    // 其余情况 = 新用户，首登生成稳定 UUID 并写回。
    const legacy = JSON.parse(event.secrets.LEGACY_GOOGLE_MAP || '{}');
    uid = legacy[event.user.email] || require('crypto').randomUUID();
    api.user.setAppMetadata('legacy_uid', uid);
  }
  api.accessToken.setCustomClaim(`${NS}/uid`, uid);
  api.accessToken.setCustomClaim(`${NS}/role`, 'authenticated');
  api.accessToken.setCustomClaim(`${NS}/email`, event.user.email);
};
```

Action Secret：`LEGACY_GOOGLE_MAP` = 下方导出的 Google 用户映射 JSON。部署后拖进 Login flow。

### 6. 用户导出（arm-002 上只读执行）

```bash
# 17 个邮箱密码用户 → bulk import JSON（bcrypt 哈希原样导入，密码无感迁移）
ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -Atc \"
SELECT json_agg(json_build_object(
  'email', u.email,
  'email_verified', true,
  'custom_password_hash', json_build_object(
     'algorithm', 'bcrypt',
     'hash', json_build_object('value', u.encrypted_password)),
  'app_metadata', json_build_object('legacy_uid', u.id)
))
FROM auth.users u
JOIN auth.identities i ON i.user_id = u.id AND i.provider = 'email'
WHERE u.encrypted_password IS NOT NULL AND u.encrypted_password <> '';
\"" > /tmp/auth0_users_import.json

# 2 个 Google 用户 → LEGACY_GOOGLE_MAP
ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -Atc \"
SELECT json_object_agg(u.email, u.id)
FROM auth.users u
JOIN auth.identities i ON i.user_id = u.id AND i.provider = 'google';
\""
```

导入：Dashboard → User Management → Import/Export（或 Management API `POST /api/v2/jobs/users-imports`，connection 选 database connection，upsert=false），确认 17 条全部成功。

### 7. Stage 1 验收

- 老邮箱用户在 Universal Login 用**原密码**登录成功。
- jwt.io 解码 access token：`alg=HS256`、`aud=https://api.panda.qzz.io`、三个 namespaced claims 正确，uid 与 `auth.users.id` 一致。
- Google 老用户登录后 Dashboard 里 `app_metadata.legacy_uid` = 原 UUID。
- （可选提前联调）此时用该 access token 手动 curl PostgREST 会 401（aud/密钥还没换）——预期。

---

## Stage 4 — 切换窗口（15–30 分钟，提前公告需重新登录）

1. 冻结：公告期间勿注册。若 Stage 1 导出后有新 GoTrue 注册：重跑导出补导 + `INSERT INTO quant.users (id,email) SELECT id,email FROM auth.users ON CONFLICT DO NOTHING;`
2. sops：`dotfiles/secrets/common.yaml` 里 `oracle-arm-002/jwt-secret` 换成 Auth0 API Signing Secret（key 名不变，postgrest/realtime 模板自动继承）。
3. `postgres.nix` commit（见 dotfiles 分支）：删 gotrue 服务/sops 模板/nginx auth vhost；PostgREST `jwt-aud = "https://api.panda.qzz.io"`、`jwt-role-claim-key = ''."https://panda.qzz.io/role"''`、`db-pre-request = "quant.ensure_user"`。
4. `NIXPKGS_ALLOW_INSECURE=1 nixos-rebuild switch --flake .#oracle-arm-002 --build-host root@oracle-arm-002 --target-host root@oracle-arm-002 --impure`
5. Realtime 租户密文重种（存的是旧密钥的 AES 密文，不会自动换）：
   ```bash
   ssh oracle-arm-002 "sudo runuser -u postgres -- psql -d api -c \"DELETE FROM _realtime.extensions; DELETE FROM _realtime.tenants WHERE external_id='quant';\""
   ssh oracle-arm-002 "sudo systemctl restart supabase-realtime"   # SEED_SELF_HOST=true 会用新密钥重种
   ```
6. 用新密钥重签 `REALTIME_ANON_JWT`（payload `{role:"anon", iss:"supabase", ref:"quant", exp:2092…}`）填进前端构建变量，`cd web/apps/app && pnpm run deploy`。

### 验证清单

- 老邮箱用户原密码登录 → /signals、/dca 显示**迁移前旧数据**（legacy_uid 链路）。
- 新注册用户能保存 preferences（`ensure_user` 生效，无 FK 报错）。
- Realtime：/live 页 WS 订阅有推送（anon token + 登录态各验一次）。
- Telegram 绑定读写、回测提交（backtest_jobs INSERT）。
- 11 个 SSR 页（/live /wf /nautilus …）经 `qt_jwt` cookie 出用户数据。
- `/execution` 的连接列表只展示当前用户的数据；网页不接收交易所密钥。
- 负面：旧 GoTrue token 打 PostgREST 401；`auth.panda.qzz.io` 不可达。

### 回滚（窗口内）

revert postgres.nix + sops 恢复旧 jwt-secret → rebuild → realtime 重种（同上 delete+restart）→ 前端回滚上一版。DB 031 双读兼容**无需回滚**。**Stage 5 之前不要动 auth schema 的表——它是回滚保险。**

---

## Stage 5 — 退役清理（稳定 ≥1 周后）

1. `ssh oracle-arm-002 "sudo runuser -u postgres -- pg_dump -d api -n auth" > backup_auth_schema_$(date +%F).sql`
2. 新建 `migrations/032_retire_gotrue.sql`：drop auth schema 内 GoTrue 全部表（**保留 schema 与 uid/role/email/jwt 四个函数**）；可删 `auth.uid()` 的旧 `sub` 回退分支；`REASSIGN OWNED BY supabase_auth_admin TO postgres; DROP OWNED BY supabase_auth_admin; DROP ROLE supabase_auth_admin;`
3. dotfiles：删 sops 里 gotrue 专属条目（google-oauth-secret 若仅 gotrue 用）；GCP 删旧 redirect URI；DNS 删 `auth.panda.qzz.io`。
4. 仓库：更新 CLAUDE.md / AGENTS.md 的 auth 描述；`web-vanilla/` 已随切换弃用（不修）。

## 附：日后轮换 Auth0 signing secret

Auth0 API → rotate signing secret → 同步 sops → `nixos-rebuild switch` → realtime 租户 delete+restart 重种 → 重签 `REALTIME_ANON_JWT` → 重新部署前端。旧 token 最长 1 小时内自然过期。

---

## 2026-07-30 巡检记录（迁移后首夜）

夜间 12h 全部正常：market-collector 22 次、news-collector 36 次（194 条）、stress-index 12 次、
signal-evaluator/alert-dispatcher 常驻无错、ohlc_15m 持续跟进、零 read-only 报错。

顺带修掉两个**早于本次迁移**的问题：

1. **`quant.semi_universe` 停更一个月**（2026-06-28 之后）——`nautilus_equity/semi_analysis.py` 从来
   没有定时任务。后果：`stress_index` 缺 breadth 分量（每小时一条 `breadth unavailable`）、
   `signal_evaluator` 的美股白名单退化到 NVDA/AMD/QQQ 三只。现已加入 nur `quant-collectors`
   （`quant-semi-analysis.timer`，每天 22:20 UTC 美股收盘后，`--load`；env 多了 numpy/pandas）。
   验证：44 行刷新入库，压力指数分量数 3 → 4（`breadth=11.4→89`）。
2. **restic 备份两台机器一直失败**：`nixos-modules/server/backup/default.nix` 的仓库 URL 里
   `https://` 写了两遍 → S3 客户端解析出空 bucket。已修正为 `s3:https://s3.tebi.io/...`。
   修好后错误变成 **`The Access Key Id you provided does not exist in our records`** ——
   即 sops `restic/s3` 里的 tebi.io 凭据已失效，**需要在 tebi.io 重新生成 access key 并更新 sops**
   （`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`）。在那之前 `/home` 仍然没有备份。
   amd-002 也需 rebuild 才能拿到 URL 修复。
