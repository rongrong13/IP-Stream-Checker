# IP-Stream-Checker 项目总结

> 供后续 AI 编码代理(Zcode agent 等)继续优化使用的项目全景文档。

---

## 一、项目定位

**流媒体解锁检测 + IP 风险检测整合工具**。输入一个 Clash 订阅链接,自动为每个节点完成:

1. IP 风险检测(出口 IP 的机房/代理属性 + 风险度百分比)
2. 流媒体解锁检测(Netflix / Disney+ / YouTube / ChatGPT / Gemini / Claude 等)
3. 按用户设定的阈值**自动移除高风险节点**,输出可直接导入 OpenClash 的订阅
4. 结果标注在节点名上,并提供自研 Web 面板 + 历史记录回看

典型节点名输出:
```
🇭🇰 HK-01·61%·GM✓(sg)·NF✓(us)·GPT✓【🟡 机房|原生】
```

## 二、项目来源(整合自两个开源项目)

| 源项目 | 语言 | 提供能力 | 本项目吸收方式 |
|---|---|---|---|
| `clash-ip-checker-docker`(同目录参考源) | Python/FastAPI | IP 风险检测、订阅转换 `/check`、任务队列、MD5 缓存、SSE 进度 | 作为**基座**,保留其服务框架 |
| `MediaUnlockTest-main`(同目录参考源) | Go | 100+ 流媒体解锁检测 | 源码内置 `mediatest/`,Python 通过 subprocess 调用其 `-json` 模式 |

> 两个源项目保留在项目同目录供对照参考。

## 三、目录结构(核心)

```
IP-Stream-Checker/
├── main.py                    # FastAPI 入口: /ipcheck 面板, /check 订阅转换,
│                              #   /status/stream SSE, /api/history, /api/settings
├── core/
│   ├── checker_service.py     # 核心检测编排: 切节点→IP检测→流媒体检测→重命名/过滤
│   ├── job_manager.py         # 任务队列/并发控制/取消/历史写入
│   ├── clash_api.py           # Mihomo API 封装(加载配置/切节点/端口)
│   ├── config.py              # 配置加载(config.yaml + 环境变量)
│   ├── history.py             # 检测历史记录存储(最近50条, JSON)
│   └── sources/               # IP 风险数据源
│       ├── ipapi.py           # ★ 当前默认: ip-api.com 免费启发式(可靠)
│       ├── ping0.py           # 旧源: ping0.cc(现被 Cloudflare 拦截, 基本失效)
│       └── ippure.py          # 旧源: ippure(官方 API 与镜像已失效)
├── stream_tester/
│   └── media_unlock.py        # subprocess 调用 mediatest 二进制, 解析 JSON,
│                              #   生成"只含解锁成功项"的节点名摘要
├── mediatest/                 # MediaUnlockTest Go 源码(已加 -json/-providers 模式)
├── templates/index.html       # 自研 Web 面板(彩虹主题, 无外部 CDN)
├── tests/                     # 单元测试(评分/格式化/缓存键/数据源顺序, 不触网, CI 跑 pytest)
├── config.yaml                # 统一配置(数据源/流媒体开关/测活/风险过滤阈值/保留天数/打乱顺序)
├── Dockerfile                 # 多阶段: golang交叉编译mediatest → python+mihomo
├── docker-compose.yml
└── data/                      # 运行数据(挂载卷): 结果yaml + 历史记录 + 缓存
```

## 四、核心功能清单

- **订阅转换**: `http://IP:8000/check?url=<原始订阅>` → 返回检测后订阅
- **IP 风险检测**(`core/sources/ipapi.py`):
  - 通过节点代理实时查 `ip-api.com`(免费、无反爬、HTTP)
  - 字段: 出口 IP、机房(hosting)、代理(proxy)、移动网络(mobile)、ISP/ASN
  - 启发式风险度 0-100%: 机房+45 / 代理+35 / 云厂商ASN+15 / 移动-10, 取整 clamp
  - 属性: `ip_attr`=机房/住宅, `ip_src`=代理/原生
- **流媒体解锁检测**(`stream_tester/media_unlock.py`):
  - 默认检测 7 个: Netflix, Disney+, Youtube Premium, OpenAI ChatGPT, Anthropic Claude, Google Gemini, Spotify Registration(可配置/可增)
  - 只显示**解锁成功**的服务(✓), 失败不显示; 仅 IP 检测成功的节点才测
- **风险节点自动过滤**: Web 设置"去除风险度高于 X%"(0=关), 超阈值节点从 proxies 与 proxy-groups 一并移除
- **检测历史记录**: 完成自动写入(最近50条), Web 左侧列表点击回看 YAML 结果; 结果文件按 `result_retention_days`(默认7天)自动清理
- **Web 设置面板**: 数据源(ipapi/ping0/ippure)、降级、超时、ippure地址、流媒体服务多选开关、风险过滤阈值、保留天数 —— 全部写入 `config.yaml` 持久化
- **队列/缓存**: 缓存键 = 订阅内容 + 检测选项(source/fallback/skip_keywords/风险阈值/流媒体服务) 的 MD5,
  不同设置互不覆盖;任务复用、同 IP 限流、Request ID 防竞态、任务状态字典容量上限(100)、日志上限(200)
- **节点测活**(借鉴 subs-check): 检测前用 Mihomo 内核并发测活(`GET /group/GLOBAL/delay?url=generate_204`),
  不可用节点不进入 IP/流媒体检测;死节点策略 skip(跳过不标注)/remove(从输出移除)
- **打乱测试顺序**(借鉴 subs-check shuffle-test-order): `shuffle_test_order` 开启后打乱测试先后,输出保持原序
- **可选鉴权**: 环境变量 `API_TOKEN` 非空时启用,全部 API 校验 `Authorization: Bearer`(SSE 与 /check 订阅链接走 query token)

## 五、技术架构要点

- **运行时**: Docker 单容器 = Mihomo(Clash Meta)内核 + FastAPI + mediatest 二进制 + 预置 GeoIP
- **Dockerfile 多阶段**: `golang` 阶段用 `--platform=$BUILDPLATFORM` 原生交叉编译 mediatest(GOARCH 由 TARGETARCH 注入, 旧 Docker 自动 `go env GOARCH` 兜底); mihomo 二进制从 Docker Hub `metacubex/mihomo:v1.19.18` 镜像阶段 COPY(走 registry-mirrors 加速, 比 GitHub 下载可靠)
- **国内网络适配**: Go 依赖 `goproxy.cn`、pip 阿里云镜像、apt 阿里源、GeoIP 走 jsDelivr(尽力而为)
- **架构支持**: amd64 + arm64(已在软路由 arm64 实测部署)
- **API 一览**:
  - `GET /ipcheck` — Web 面板
  - `GET /check?url=...&source=...&filter_risk_threshold=...&request_id=...` — 触发检测(返回订阅)
  - `GET /status/stream?url=...` — SSE 实时进度
  - `POST /cancel` — 取消任务
  - `GET /api/history` / `GET /api/history/{md5}` / `DELETE /api/history` — 历史
  - `GET /api/settings` / `POST /api/settings` — 设置读写

## 六、部署现状

- **软路由**(Kwrt OpenWrt, arm64): 源码部署在路由器本地的 docker_compose 目录, `docker compose up -d --build` 启动, 面板 `http://<路由器IP>:8000/ipcheck`
- **镜像**: 本地"镜像"目录下的 arm64 免构建 tar 包
- **GitHub**: `https://github.com/rongrong13/IP-Stream-Checker`(默认分支 master, gh CLI 已登录可推送)

## 七、已知问题与优化状态(供 Zcode agent 的 TODO)

> 2026-08-13 已完成的优化(详见 CHANGELOG 1.2.0): 缓存键冲突、取消竞态、SSE 悬挂、
> 内存增长、降级白等失效源、节点测活(subs-check 借鉴)、打乱顺序、ip-api 限速重试与评分增强、
> 可选 API_TOKEN 鉴权、依赖版本固定、单元测试(CI 跑 pytest)。

1. **容器内测活/检测链路端到端验证待完成**: 测活接口 `GET /group/GLOBAL/delay` 已按 Mihomo API 实现,
   但"容器内真实订阅端到端跑通"未验证(本地链路经路由器 OpenClash 结果不准,未实测)
2. **风险度是启发式推断值**(非精确第三方评分): 如需更精确,可接入 IPQualityScore / AbuseIPDB(需免费注册 key,前端加配置项)
3. **ping0/ippure 数据源已失效**: 已排除出自动降级池(不再白等超时),保留为手动可选;彻底修复需过 Cloudflare,成本高
   - **不稳定的根因(已排查)**: ping0.cc 有 Cloudflare Turnstile 挑战 + HTML 正则解析(结构易碎);
     scamalytics/ippure 同为"网页爬取式"源(亦有 CF 保护);JSON API 式源(ip-api)才稳定。
     如需更高精度建议走第三方 API(见第 2 条),不建议再维护 HTML 爬取式源
4. **ip-api 免费版限速**(HTTP 约 45 次/分): 已加 429 自动重试(退避 1s/2s);大订阅(>45节点)仍可能触发限流,可进一步做全局速率控制
5. **流媒体检测耗时**: 每节点默认 7 服务约 10-30 秒;已用"测活前置"剔除死节点,但仍可按服务/结果做缓存进一步加速
6. **前端可继续美化**: 可扩展节点级详情展示(风险/解锁明细表格)、检测对比、导出报告等
7. **共享设备数/原生广播**等 ping0 专属字段在 ipapi 源下缺失,若需要可加 ipinfo.io 交叉补充
8. 安全: `/check` 接受任意 URL 做代理(SSRF 面),已提供可选 `API_TOKEN` 鉴权(环境变量设置后全部 API 校验 Bearer),
   若暴露公网请务必开启;SSE 与订阅链接走 query token

## 八、与 AI 编码代理(Zcode agent)的 GitHub 协作

> Zcode / Zed 的 agent 可以直接读取、修改、推送本仓库,本机凭据已全部就绪。

**仓库信息**
- GitHub: `https://github.com/rongrong13/IP-Stream-Checker`(默认分支 **master**)
- 本地路径: 以实际克隆/解压位置为准(本项目为 git 仓库, `git clone` 或直接打开本地目录即可)
- git remote(SSH): `git@github.com:rongrong13/IP-Stream-Checker.git`

**本机凭据(都已验证可用, 无需再配置)**
- `gh` CLI 已登录账号 `rongrong13`(token 存系统钥匙串, 支持 `gh` 命令与 git HTTPS 凭据)
- SSH key: 本机已配置 SSH key 并添加到 GitHub, `ssh -T git@github.com` 认证通过(推送免密)
- git remote 使用 SSH 格式, `git push` 直接可用

**Zcode 可执行的 GitHub 操作**
```bash
# 方式1: 直接打开本地项目(路径以实际位置为准)
zed <项目本地路径>

# 方式2: 从 GitHub 克隆(全新环境)
git clone git@github.com:rongrong13/IP-Stream-Checker.git

# 改完提交推送(SSH 免密 / gh 凭据均可)
git add -A && git commit -m "..." && git push origin master
```

**注意事项**
- 主分支为 `master`(不是 main), 推送目标统一 `origin master`
- 修改后请保持 `PROJECT_SUMMARY.md` 与 README 同步更新
- 若 Zcode 需要调用 GitHub API(如开 PR / 查 issue), 用 `gh api`(已登录)即可

## 九、快速命令

```bash
# 本地构建+运行
docker compose up -d --build

# 触发一次检测(替换真实订阅链接)
curl "http://127.0.0.1:8000/check?url=<订阅链接>&filter_risk_threshold=30"

# 查看历史
curl http://127.0.0.1:8000/api/history
```
