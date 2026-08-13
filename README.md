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

*   **API 订阅转换**: `http://设备IP:8000/check?url=[原始订阅链接]` — 把带检测结果的订阅链接直接替换进 Clash/Mihomo 客户端,每个节点自动完成 IP 检测 + 流媒体解锁检测
*   **Web 可视化面板**: `http://设备IP:8000/ipcheck` — 自研界面(彩虹主题),实时进度日志、历史记录回看、设置面板
*   **检测历史记录**: 每次检测结果自动留存(最近 50 条),切换链接后仍可回看历史结果与节点详情
*   **风险节点自动过滤**: 可在 Web 设置"去除风险度高于 X% 的节点",超出的节点从输出订阅中移除,方便直接导入 OpenClash
*   **结果本地保留**: 检测结果按天保留在挂载卷(默认 7 天,可配置),过期自动清理,不占网页空间
*   **智能缓存**: 基于"订阅内容 + 检测选项"的 MD5 去重缓存,不同检测设置互不覆盖;任务复用,多用户共享同一检测任务
*   **节点测活**: 正式检测前用 Mihomo 内核并发测活,不可用节点自动跳过(不进入 IP/流媒体检测),死节点可配置为"跳过不标注"或"从输出移除",大订阅明显加速
*   **打乱测试顺序**: 可选打乱节点测试先后(避免相邻节点扎堆同一时间窗口),输出订阅保持原序
*   **数据源可选**: `ipapi`(默认,可靠)/ `Ping0` / `ippure`,自动降级只回落到当前可用源
*   **流媒体解锁检测**: 可配置检测哪些服务(默认核心 7 个,含 Gemini),结果实时标注在节点名
*   **可选访问鉴权**: 设置环境变量 `API_TOKEN` 后所有 API 需 Bearer 令牌(未设置时行为不变),适合暴露公网时防止白嫖/SSRF
*   **单容器部署**: 容器内同时运行 Mihomo 内核 + FastAPI 服务 + MediaUnlockTest 二进制
*   **多架构支持**: 镜像支持 `amd64`(x86 软路由/NAS)和 `arm64`(ARM 路由器)

---

## 🖥️ Web 界面

启动后浏览器打开 **`http://设备IP:8000/ipcheck`**(如本机 `http://127.0.0.1:8000/ipcheck`)。

Web 面板提供:

1. **输入订阅链接**: 粘贴你的 Clash 订阅地址,点击"开始检测"
2. **实时进度**: 每个节点的检测状态、日志实时滚动显示(SSE 推送)
3. **停止按钮**: 随时中断正在进行的检测任务
4. **高级设置**: 可覆盖队列大小、缓存时长、数据源、测活开关、死节点策略、打乱顺序等(需在 `config.yaml` 打开 `SHOW_ADVANCED_SETTINGS`)
5. **访问令牌**: 服务端启用 `API_TOKEN` 鉴权时,页面顶部出现令牌输入框(保存在本机浏览器 localStorage);检测完成的订阅链接会自动附带 token,可直接粘贴到 Clash 客户端

检测完成后,回到 Clash 客户端刷新订阅,即可看到每个节点的检测标注:

```
节点名 【🟢 住宅|原生】 🎬NF✓(US)·D+✗·GPT✓
```

---

## 部署方式 A: x86 设备 / NAS(Docker Compose)

适合 x86 软路由、NAS、云服务器等有 Docker Compose 的环境。

```bash
# 1. 拉取代码
git clone https://github.com/rongrong13/IP-Stream-Checker.git
cd IP-Stream-Checker

# 2. 启动(首次构建需 10-20 分钟,国内网络已适配镜像源)
docker compose up -d --build

# 3. 访问
# Web 面板: http://127.0.0.1:8000/ipcheck
```

---

## 部署方式 B: OpenWrt 路由器(arm64)直接用 Docker Compose

以 **Kwrt 定制 OpenWrt(qualcommax/ipq60xx, arm64)** 为例。镜像已支持 arm64,直接在路由器上构建部署。

### 步骤 1: 把项目放到路由器上

方法一(推荐,走局域网):电脑上下载项目 zip,解压后用 scp 传到路由器:

```bash
# 电脑上执行(路由器地址假设 192.168.1.1)
scp -r IP-Stream-Checker root@192.168.1.1:/root/
```

方法二:路由器 SSH 里直接 git clone(需要能访问 GitHub,国内可能慢):

```bash
cd /root
git clone https://github.com/rongrong13/IP-Stream-Checker.git
```

### 步骤 2: 配置 Docker 国内镜像加速(强烈推荐)

路由器上访问 Docker Hub 拉取基础镜像(golang/python 共 1GB+)很慢,建议配置加速。SSH 登录路由器:

```bash
# 查看当前配置
cat /etc/docker/daemon.json 2>/dev/null || echo "{}"

# 写入加速镜像(若文件不存在则创建)
mkdir -p /etc/docker
echo '{"registry-mirrors": ["https://docker.m.daocloud.io"]}' > /etc/docker/daemon.json

# 重启 Docker 服务生效(OpenWrt 上)
/etc/init.d/dockerd restart
```

> 若 `dockerd` 服务名不同,可用 `service dockerd restart` 或 LuCI 里重启 Docker。

### 步骤 3: 路由器上构建并启动

SSH 登录路由器,进入项目目录:

```bash
cd /root/IP-Stream-Checker

# 构建并后台启动(首次构建 20-40 分钟,依赖国内镜像源已内置)
docker compose up -d --build
# 若提示无 docker compose,用旧版命令:
# docker-compose up -d --build
```

### 步骤 4: 验证

```bash
# 查看容器状态(STATUS 应为 Up)
docker ps | grep ip-stream-checker

# 看启动日志(出现 "Clash API is ready." 与 "Uvicorn running" 即成功)
docker logs -f ip-stream-checker-clash-checker-1
```

浏览器打开 **`http://192.168.1.1:8000/ipcheck`** 即可使用。

### 步骤 5: 放行防火墙端口(重要)

OpenWrt 默认拦截外部访问,在 LuCI 添加防火墙规则:

**网络 → 防火墙 → 通信规则 → 添加**:
- 名称: `ip-stream-checker`
- 协议: TCP
- 源区域: lan
- 目标区域: 设备(输入)
- 目标端口: `8000`
- 动作: 接受

### 修改配置

编辑 `/root/IP-Stream-Checker/config.yaml` 后重启容器:

```bash
vi /root/IP-Stream-Checker/config.yaml   # 修改配置
docker compose restart                    # 重启生效
```

> ⚠️ 路由器性能与内存有限(ipq60xx 约 1GB RAM),首次构建 Go 依赖时若出现 OOM,可临时停止其他容器再构建,或在 LuCI 里给 docker 加 swap。

### 升级

```bash
cd /root/IP-Stream-Checker
git pull          # 或重新上传新代码
docker compose up -d --build   # 自动重建并滚动更新
```

---

## 配置说明

编辑 `config.yaml`(部署后挂载进容器):

```yaml
# IP 检测
source: "ping0"            # 数据源: ping0 / ippure
fallback: true             # 主源失败时降级到备用源
request_timeout: 15        # 单节点 IP 检测超时(秒)
max_queue_size: 10         # 同时最多处理的任务数
max_age: 360               # 缓存有效期(秒), 0 = 每次重新检测
skip_keywords:             # 名字含这些关键词的节点跳过检测
  - "剩余"
  - "到期"

# 流媒体解锁检测(整合 MediaUnlockTest)
stream_test:
  enabled: true            # 是否启用
  binary_path: /usr/local/bin/mediatest
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

# 是否在 Web 面板显示高级设置
SHOW_ADVANCED_SETTINGS: false
```

> ⚠️ 流媒体检测会显著拉长整个任务:默认 6 个服务约每节点 10-30 秒;全量(留空 providers)需数分钟/节点,节点多的订阅请勿使用。

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
├── Dockerfile              # 多阶段构建(golang 交叉编译 → python + mihomo)
├── docker-compose.yml
└── .github/workflows/ci.yml  # GitHub Actions: 语法检查 + Docker 构建
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

`status_text` 取值: `ok` / `restricted`(地区限制) / `no`(不支持) / `network_error` / `banned` / `failed` / `unexpected`

---

## 常见问题

**Q: 检测任务一直卡在排队?**
检查 `max_queue_size` 配置;多人同时检测时队列会满,稍等或加大队列。

**Q: 节点全部显示 ❌ 失败?**
节点本身不可用(IP 检测两个数据源都超时)。可用真实可用节点测试;若节点正常,尝试把 `source` 换成 `ippure`。

**Q: 路由器上容器起不来?**
`docker logs ip-stream-checker` 看日志。常见原因:镜像架构不对(必须是 arm64)、8000 端口被占用。

**Q: 路由器上想更新版本?**
重复"部署方式 B":电脑重新构建 → `docker save` → `scp` → 路由器 `docker load`(会自动覆盖)→ `docker rm -f ip-stream-checker` → 重新 `docker run`。

**Q: 国内网络下载 GitHub 资源失败?**
构建时 GeoIP/geosite 预下载为"尽力而为"(失败跳过,global 模式不依赖);Go 依赖走 goproxy.cn、pip 走阿里云镜像,均已适配。

---

## 许可证

MIT
