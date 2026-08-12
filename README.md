# IP-Stream-Checker - 流媒体解锁与IP风险检测整合工具

一个集成了IP-risk检测和流媒体解锁测试功能的综合工具，能够自动测试流媒体解锁情况以及IP-risk检测。

## 功能特性

### 🎯 核心功能
- **IP-risk检测**：基于Clash Meta的高性能IP风险检测
- **流媒体解锁测试**：支持超过100个流媒体服务的地区限制检测
- **自动化测试**：一键启动完整的流媒体和IP检测流程
- **可视化报告**：直观的Web界面展示测试结果

### 🚀 技术特点
- 基于FastAPI构建的高性能Web服务
- 支持多种IP数据源（Ping0和ippure）
- 智能缓存系统，避免重复检测
- 支持Docker容器化部署
- 统一的配置管理系统

## 快速开始

### 使用Docker部署

```bash
# 1. 克隆项目
git clone https://github.com/your-repo/IP-Stream-Checker.git
cd IP-Stream-Checker

# 2. 启动服务
docker-compose up -d --build
```

### 访问Web界面
- Web界面：`http://localhost:8000`
- API文档：`http://localhost:8000/docs`

## 项目架构

```
IP-Stream-Checker/
├── app/                 # 主应用模块
│   ├── ip_checker/      # IP-risk检测模块
│   ├── stream_tester/   # 流媒体测试模块
│   └── web/            # Web界面
├── config/             # 配置文件
├── requirements.txt    # 依赖包
├── Dockerfile         # Docker配置
└── docker-compose.yml # Docker Compose配置
```

## 功能模块

### IP-risk检测
- 支持多种IP数据源（Ping0和ippure）
- 智能缓存系统
- API订阅转换服务
- Web可视化面板

### 流媒体解锁测试
- 支持100+流媒体服务
- 自动化测试流程
- 详细的地区限制检测结果
- 实时监控功能

## 配置说明

通过修改`config/config.yaml`文件可以调整以下配置：
- IP检测超时时间
- 缓存有效期
- 流媒体测试项目
- 代理设置

## 许可证

本项目采用MIT许可证。请遵守当地法律法规使用本工具。

## 贡献

欢迎提交Pull Requests来改进本工具或添加新的流媒体测试项目。