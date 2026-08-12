# ============================================================
# 阶段 1: 构建 MediaUnlockTest (Go) 二进制
# ============================================================
FROM golang:latest AS mediatest-builder

WORKDIR /build
# 使用国内 Go 模块代理(proxy.golang.org 在国内常无法访问)
ENV GOPROXY=https://goproxy.cn,direct
ENV CGO_ENABLED=0
# 先复制 go.mod/go.sum 以利用 Docker 层缓存
COPY mediatest/go.mod mediatest/go.sum ./
RUN go mod download

COPY mediatest/ .
# 构建流媒体解锁检测工具(-json 模式由 cli/main.go 提供)
RUN go build -ldflags="-s -w" -o /out/mediatest ./cli && \
    /out/mediatest -v

# ============================================================
# 阶段 2: Python 运行环境
# ============================================================
FROM python:3.10-slim-bookworm

WORKDIR /app
ENV PYTHONUNBUFFERED=1
# 使用阿里云 PyPI 镜像(pypi.org 在国内访问不稳定)
ENV PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ENV PIP_TRUSTED_HOST=mirrors.aliyun.com

# Install system dependencies
# Use Aliyun mirror to fix "Hash Sum mismatch" and connection issues
RUN sed -i 's/deb.debian.org/mirrors.aliyun.com/g' /etc/apt/sources.list.d/debian.sources && \
    sed -i 's/security.debian.org\/debian-security/mirrors.aliyun.com\/debian-security/g' /etc/apt/sources.list.d/debian.sources && \
    apt-get update && \
    apt-get install -y \
    curl \
    gzip \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Mihomo (Clash Meta)
# Using a fixed release for stability. Adjust arch if needed (amd64 assumed)
RUN curl -L -o clash.gz https://github.com/MetaCubeX/mihomo/releases/download/v1.19.18/mihomo-linux-amd64-v1.19.18.gz && \
    gunzip clash.gz && \
    chmod +x clash && \
    mv clash /usr/local/bin/clash

# Verify installation
RUN clash -v

# Pre-download GeoIP and GeoSite databases (尽力而为)
# 国内网络下载 GitHub 资源不稳定,失败不阻塞构建。
# 本项目使用 global 模式 + 无 rules,运行时并不需要这些库,缺失时 mihomo 会自行尝试下载。
RUN mkdir -p /root/.config/mihomo && \
    (curl -L --connect-timeout 8 -m 90 -o /root/.config/mihomo/geoip.metadb "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.metadb" && echo "geoip.metadb OK") || echo "WARN: geoip.metadb 下载失败,跳过" ; \
    (curl -L --connect-timeout 8 -m 90 -o /root/.config/mihomo/geosite.dat "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geosite.dat" && echo "geosite.dat OK") || echo "WARN: geosite.dat 下载失败,跳过" ; \
    (curl -L --connect-timeout 8 -m 90 -o /root/.config/mihomo/country.mmdb "https://cdn.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/country.mmdb" && echo "country.mmdb OK") || echo "WARN: country.mmdb 下载失败,跳过"

# 复制 Go 构建产物
COPY --from=mediatest-builder /out/mediatest /usr/local/bin/mediatest

# Copy App
COPY . .

# Ensure entrypoint is executable
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]
