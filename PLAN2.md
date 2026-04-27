# GPU 服务器显卡监控页与 Grafana 面板

## Summary
为当前双机 RAG 平台新增一套 GPU 监控能力，覆盖两层展示：

- 平台内新增一个原生 `GPU 监控` 页面，展示 `192.168.110.241` 上显卡与模型服务的核心概览。
- Grafana 新增一份详细 GPU dashboard，承接更深入排障与历史分析。
- 指标来源采用 `241` 上部署标准 GPU exporter，由 `117` 上的 Prometheus 抓取。
- GPU exporter 的部署说明与接入配置纳入本仓库，形成可复现的部署闭环。

## Key Changes
### 1. 指标采集与部署接入
- 在仓库内新增 GPU 节点监控部署说明，约定在 `192.168.110.241` 上部署 NVIDIA/DCGM exporter。
- 更新 `deploy/two-server/app-node/monitoring/prometheus/prometheus.yml`，新增针对 `241` 上 GPU exporter 的 scrape job。
- 更新应用节点部署文档与运行清单：
  - 在 `README.md`、`RUNBOOK_117.md`、`preflight.sh` 的说明中补充 GPU exporter 可达性检查与验收步骤。
- 不把 GPU exporter 纳入应用节点 compose；它属于 GPU 节点外部依赖，由仓库提供明确部署方法、端口约定、Prometheus 接入方式和验证命令。

### 2. 后端接口与聚合逻辑
- 在 `platform-api` 新增一组只读 GPU 监控接口，供前端原生页面读取。
- 后端通过服务端调用 Prometheus HTTP API 聚合 GPU 指标，避免浏览器直连 Prometheus/Grafana 带来的认证、CORS 和地址暴露问题。
- 建议接口形态：
  - `GET /api/gpu/overview`
  - 返回单次快照，不做数据库持久化
- 返回内容聚焦首版核心概览：
  - GPU 节点在线状态
  - 每张 GPU 的利用率
  - 每张 GPU 的显存使用量与占比
  - 每张 GPU 的温度
  - 每张 GPU 的功耗
  - GPU 总数、总显存、已用显存
  - 与 GPU 相关的模型服务状态摘要：`ollama`、`qwen27`、`qwen35`
  - Grafana 详细面板跳转地址
- 权限沿用现有监控页策略，允许 `superadmin / operator / viewer` 访问。

### 3. 平台内原生页面
- 在前端新增 `GPU 监控` 路由和侧边栏入口，风格保持现有 dashboard 语言，不重置整体设计系统。
- 页面结构采用“控制室概览”风格，首版只做核心概览，不引入复杂图表依赖：
  - 顶部状态条：GPU 节点、Exporter、Prometheus 抓取状态、最近采样时间
  - 汇总卡片：GPU 数量、总显存、已用显存、平均负载、最高温度、总功耗
  - GPU 卡片列表：每张卡显示利用率、显存、温度、功耗、状态
  - 模型服务联动区：展示 `ollama / qwen27 / qwen35` 健康状态，帮助判断“高负载但服务正常”或“服务异常但 GPU 空闲”
  - 外链动作：跳转 Grafana GPU 详细面板
- 复用现有共享样式层与组件风格，优先通过全局样式和现有 panel/card 体系扩展，不新增一套孤立样式。

### 4. Grafana 详细面板
- 新增一个 GPU 专用 dashboard JSON，并纳入现有 Grafana provisioning。
- Grafana 面板承接详细分析，至少包含：
  - 每卡 GPU 利用率趋势
  - 每卡显存使用趋势
  - 每卡温度趋势
  - 每卡功耗趋势
  - 节点级 GPU 汇总
- 在平台内原生页提供跳转入口，不做 iframe 嵌入。

## Public Interfaces
- 新增前端页面路由：`/gpu`
- 新增平台 API：
  - `GET /api/gpu/overview`
- 不修改现有认证模型；新接口走现有 JWT 与角色校验。
- 不修改现有数据库 schema；GPU 监控首版不落库。

## Test Plan
- 后端接口测试：
  - Prometheus 可用时，`/api/gpu/overview` 能返回规范字段
  - Prometheus 无响应或 exporter 缺失时，接口返回可读错误或降级状态，而不是 500 崩溃
  - viewer/operator/superadmin 均可访问，未登录用户被拒绝
- 前端页面测试：
  - 正常加载 GPU 概览、模型状态和 Grafana 跳转
  - 空数据、抓取失败、节点离线时有明确错误态/空态
  - 桌面与窄屏下卡片布局不破坏现有 shell
- 部署与验收：
  - `241` 上 exporter 启动后，`117` 上 Prometheus target 变为 `UP`
  - Grafana 能自动加载 GPU dashboard
  - 平台内 `GPU 监控` 页面与 Grafana 面板数据量级一致
  - 更新后的 `preflight`/runbook 能覆盖 exporter 可达性检查

## Assumptions
- GPU 指标来源使用标准 NVIDIA/DCGM exporter，部署在 `192.168.110.241`，并对 `117` 的 Prometheus 暴露抓取端口。
- 平台内页面首版只做核心概览，不做历史趋势图；详细历史趋势全部交给 Grafana。
- 平台内页面使用服务端聚合 Prometheus 数据，而不是前端直连 Prometheus 或嵌入 Grafana。
- 不引入新的前端图表库；首版以卡片、状态和进度式信息展示为主。
