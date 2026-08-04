# Changelog

所有版本变更记录。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

## [v0.4.0] - 2026-08-04

### Added
- **WebSocket 实时推送** (`/ws/debate/{id}`) — 无需轮询，服务端主动推送
- **全局统计端点** (`/api/stats`) — 追踪辩论数、消息数、Token 消耗
- **辩论历史列表** — 查看所有过往辩论及其状态
- **Web UI 升级** — 改用 WebSocket，实时显示消息流

## [v0.3.0] - 2026-08-04

### Added
- **API Gateway** (FastAPI + REST API)
- **Docker 部署** (Dockerfile + docker-compose.yml)
- **Web UI** (实时监控界面)
- **异步任务处理** (线程隔离)

## [v0.2.0] - 2026-08-03

### Added
- 双方共识机制（必须所有 Agent 都同意才算达成共识）
- 轮次管理模式（每轮只有一个 Agent 发言）
- 单 Agent 故障隔离（故障 Agent 不参与共识判断）
- 讨论摘要生成（每 3 轮自动汇总）
- 方案质量校验（讨论充分性 + 内容完整性检查）
- 共识噪声过滤（过滤摘要消息和元讨论）
- 方案内容动态提取（从讨论中提取 API/数据模型/实现细节）

## [v0.1.0] - 2026-08-03

### Added
- 初始版本发布
- 多 Agent 辩论协作框架
- 基于 Redis Pub/Sub 的消息驱动
- 支持 DeepSeek / LongCat 多模型
- 单进程 / 多进程两种运行模式
- 工具沙盒（文件操作限制在工作区内）
