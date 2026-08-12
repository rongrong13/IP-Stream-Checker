# ⚡ IP-Stream-Checker

流媒体解锁检测 + IP-risk 检测整合工具。

由两个开源项目整合而成:

| 来源项目 | 语言 | 提供能力 |
|---|---|---|
| [clash-ip-checker-docker](https://github.com/tombcato/clash-ip-checker) | Python/FastAPI | IP-risk 检测(Clash 切换节点 + Ping0/ippure 数据源)、订阅转换、任务队列、Web 面板 |
| [MediaUnlockTest](https://github.com/HsukqiLee/MediaUnlockTest) | Go | 100+ 流媒体服务的解锁检测(Netflix、Disney+、ChatGPT 等) |

> 对每个节点:自动切换 Clash 节点 → 检测 IP 风险(Ping0/ippure)→ 检测流媒体解锁情况(MediaUnlockTest),结果标注在节点名上,如:
> `香港-01 【🟢 住宅|原生】 🎬NF✓(US)·D+✗·GPT✓`

---

## 核心功能

*   **API 订阅转换**: `http://127.0.0.1:8000/check?url=[原始订阅链接]` — 直接替换原始订阅,每个节点自动完成 IP 检测 + 流媒体解锁检测
*   **Web 可视化面板**: `http://127.0.0.1:8000/ipcheck` — 实时显示检测进度和日志
*   **智能缓存**: 基于内容 MD5 的去重缓存,默认 10 分钟有效期;任务复用,多用户共享同一检测任务
*   **数据源可选**: `Ping0` / `ippure`,可选降级策略
*   **流媒体解锁检测**: 可配置检测哪些服务(默认核心 6 个),检测结果实时标注在节点名
*   **单容器部署**: 容器内同时运行 Mihomo 内核 + FastAPI 服务 + MediaUnlockTest 二进制

---

## 快速开始

### 使用 Docker Compose

```bash
# 1. 启动服务
docker-compose up -d --build

# 2. 访问 Web 面板
# http://127.0.0.1:8000/ipcheck

# 3. 替换订阅链接(在 Clash 客户端中添加)
# http://127.0.0.1:8000/check?url=[原始订阅链接]
```

### 配置说明

编辑 `config.yaml`:

```yaml
# IP 检测
source: "ping0"            # 数据源: ping0 / ippure
fallback: true             # 主源失败时降级到备用源
request_timeout: 15        # 单节点 IP 检测超时(秒)

# 流媒体解锁检测(整合 MediaUnlockTest)
stream_test:
  enabled: true
  providers:               # 要测试的服务名(留空 = 全部,极慢)
    - "Netflix"
    - "Disney+"
    - "Youtube Premium"
    - "OpenAI ChatGPT"
    - "Anthropic Claude"
    - "Spotify Registration"
  timeout: 90              # 单节点流媒体检测超时(秒)
  conc: 20                 # 并发数
  node_label: true         # 是否在节点名中标注结果
```

---

## 项目结构

```
IP-Stream-Checker/
├── main.py                 # FastAPI 服务(订阅转换 /check、Web 面板 /ipcheck)
├── core/                   # IP 检测核心(checker_service、job_manager、clash_api、sources/)
├── stream_tester/          # 流媒体检测集成层(subprocess 调用 mediatest)
├── mediatest/              # MediaUnlockTest Go 源码(含新增 -json 模式)
├── templates/              # Web 面板
├── config.yaml             # 统一配置
├── Dockerfile              # 多阶段构建(golang → python + mihomo)
└── docker-compose.yml
```

## 流媒体检测的自动化调用

`stream_tester/media_unlock.py` 通过 subprocess 调用 mediatest 二进制:

```bash
mediatest -json -http-proxy http://127.0.0.1:7890 -conc 20 \
          -providers "Netflix,Disney+,Youtube Premium,OpenAI ChatGPT"
```

输出 JSON 数组:

```json
[
  {"name": "Netflix", "status": 1, "status_text": "ok", "region": "US", "info": "", "ok": true},
  {"name": "Disney+", "status": 3, "status_text": "no", "region": "", "info": "", "ok": false}
]
```

## 许可证

MIT
