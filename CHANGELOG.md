<!-- markdownlint-disable MD024 -->
<!-- markdownlint-disable MD025 -->
<!-- markdownlint-disable MD033 -->
<!-- markdownlint-disable MD034 -->
<!-- markdownlint-disable MD041 -->
# ChangeLog

# 2026/02/05 v1.3.9

本次更新修复了 **中国地震预警网省级预警 (CEA-PR)** 数据源无法正常格式化的问题，并引入了 **启动自检机制** 以防止类似问题再次发生。同时，本次更新还包含大量的 **稳定性增强**、**性能优化** 与 **代码重构**，修复了多个潜在的资源泄露风险，并对底层网络连接与文件 I/O 进行了深度加固。

## 🚀 What's Changed

### 🐛 Bug Fixes (修复)

- **CEA-PR 修复**: 修复了中国地震预警网省级预警 (`cea-pr`) 数据源因缺少格式化器注册导致无法正常显示格式化消息，回退到基础格式的问题 by @DBJD-CR

### 🛡️ Stability & Security (稳定性与安全)

- **启动自检**: 新增注册表完整性自检机制，插件启动时会自动检查数据源、处理器、格式化器和配置的一致性，防止配置遗漏 by @DBJD-CR
- **资源泄露防护**:
  - 修复了插件初始化失败时可能导致后台任务（如遥测、心跳）残留的问题，现在会强制清理所有资源 by @DBJD-CR
  - 修复了 `aiohttp.ClientSession` 可能的泄露问题，确保在创建新会话前安全关闭旧会话 by @DBJD-CR
  - 修复了日志去重缓存可能无限增长导致的内存泄露风险，实现了 FIFO 清理策略 by @DBJD-CR
- **并发控制**:
  - 限制了 WebSocket 重连任务的并发数量，防止网络波动时产生“重连风暴” by @DBJD-CR
  - 为浏览器渲染服务添加了页面获取与信号量的超时控制，防止高负载下系统卡死 by @DBJD-CR
  - 实现了日志轮转的文件锁机制，防止多线程/协程竞争导致的文件损坏 by @DBJD-CR
- **潜在问题**:
  - 修复了 `translate_place_name` 在高频调用时潜在的阻塞主线程的问题 by @DBJD-CR
  - 修复了日志写入时潜在的因磁盘满等 IO 错误导致程序崩溃的问题 by @DBJD-CR
- **地图渲染**:
  - 延长了 `.map_ready` 的等待超时时间，提高地图加载成功概率 by @DBJD-CR

### ⚡ Performance (性能优化)

- **I/O 优化**:
  - **异步预加载**: 实现了 `fe_regions` 数据的异步预加载机制，彻底消除了同步文件读取阻塞事件循环的隐患 by @DBJD-CR
  - **异步日志**: 将日志写入操作移交到线程池执行，避免阻塞主事件循环 by @DBJD-CR
  - **原子化写入**: 地震列表缓存写入改为“写入临时文件 -> 原子重命名”的方式，防止写入中断导致文件损坏 by @DBJD-CR
- **超时控制**:
  - 为 WebSocket 握手过程添加了显式的超时控制，避免连接尝试无限挂起 by @DBJD-CR
  - 为定时获取地震列表的 HTTP 请求添加了 60 秒超时限制 by @DBJD-CR
- **缓存优化**:
  - 实现了时区对象缓存 (`_timezone_cache`)，避免频繁创建相同的 `timezone` 对象 by @DBJD-CR
  - 将高频调用的正则表达式预编译为模块级常量，提升格式化性能 by @DBJD-CR
- **时区优化**:
  - 优化部分文件中跨时区去重逻辑中的时区处理问题，引入了更准确的 IANA 时区支持 by @DBJD-CR

### ♻️ Refactor (重构)

- **自动映射**: 重构了数据源 ID 映射逻辑，实现了从模型定义到消息管理器的自动同步，消除了硬编码维护的风险 by @DBJD-CR
- **代码规范**:
  - 统一了浮点数转换逻辑，修复了部分处理器混用导入函数和基类方法的问题 by @DBJD-CR
  - 提取了 `ROMAN_TO_INT` 到工具类，消除了硬编码 by @DBJD-CR
  - 统一了所有数据处理器的数据提取逻辑 (`_extract_data`)，消除了大量重复代码 by @DBJD-CR
  - **转换逻辑统一**: 新增 `utils/converters.py` 工具类，统一了所有处理器的烈度/震度转换和数值转换逻辑，消除了大量重复代码 by @DBJD-CR
- **清理策略**:
  - 改进了临时文件清理逻辑，增加了文件数量上限检查（默认 256 个），并优先清理最旧的文件 by @DBJD-CR
  - 实现了过期事件的自动清理机制，防止内存无限增长 by @DBJD-CR

---

# 2026/02/01 v1.3.8

Hot Fix For v1.3.7

> [!TIP]
>
> **有关地震关键词过滤的补充说明**：
>
> 我们在 v1.3.5 版本的更新中引入了基于关键词的地震事件过滤器，如果你要填写黑白名单，请注意：
>
> - 关键词填写应以 `省州市区/督道府县` 的级别填写， **请勿填写国家/地区名**，这会导致绝大部分符合推送条件的消息被过滤。
> - 关键词填写应该尽量简短 (避免填写完整的省市名，如 `XX省XX市`，根据过滤范围直接填 `浙江`、`杭州` 即可)。
> - ✅ 正确示例（精确过滤）：“新疆”、“西双版纳州”、“大同市”、“陇西县”、“宜蘭縣”、“千葉県”、“能登半島”、“宗谷地方”、“阿拉斯加”
> - ✅ 正确示例（模糊匹配）：“省”、“州”、“市”、“县”、“県”、“区”、“地区”、“道”、“附近”、“岛”、“海”、“沖”
> - ❌ 错误示例：“中国”、“台湾”、“日本”、“美国”

## 🚀 What's Changed

### ✨ New Features (新功能)

- 增强了消息格式化器的错误检测机制，现在当缺少格式化映射时会输出明确的警告日志，而不是静默回退到基础格式 by @DBJD-CR
- 增加了格式化器调用的异常捕获保护，确保单一格式化器出错不会导致整个推送流程中断 by @DBJD-CR
- 增加了处理器注册表的自检逻辑，启动时会自动检查是否所有定义的数据源映射都已正确注册，避免因配置遗漏导致的功能异常 by @DBJD-CR
- **可配置页面池**: 新增 `browser_pool_size` 配置项，允许用户调整浏览器页面池大小以优化并发处理能力（默认 2） by @DBJD-CR
- **遥测心跳**: 新增定时心跳数据功能，每12小时自动发送心跳数据（仅包含实例ID、时间戳和运行时长），用于统计活跃实例 by @Aloys233 in #64

### ⚡ Optimization (优化)

- **极速渲染优化**: 优化了浏览器等待策略，大幅提升卡片渲染速度（从 3-7s 提升至 1-4s） by @DBJD-CR
- **时间测量优化**: 心跳运行时长测量改用 `time.monotonic()` 单调时钟，避免系统时间调整带来的问题 by @Aloys233 in #64

### 🐛 Bug Fixes (修复)

- **BrowserManager 修复**: 修复了并发启动浏览器时可能导致 `TargetClosedError` 崩溃的问题，增加了初始化锁机制 by @DBJD-CR
- 修复了 CWA 地震报告因缺少映射关系导致无法解析，回退到基础格式化的问题 by @DBJD-CR
- 修复了在 Python 3.11 以下版本环境中因缺少 `tomllib` 标准库导致插件无法加载的问题。现在通过引入可选依赖 `tomli` 并增加兼容性逻辑来解决此问题 by @DBJD-CR

### 📚 Documentation & Chore (文档与杂项)

- **Workflows**:
  - 新增 **屎山代码检测** 工作流，自动评估代码质量并生成趣味报告 by @DBJD-CR
  - 新增并优化 **Stale** 工作流，支持多语言自动回复与统一的标签管理 by @DBJD-CR
  - 新增并升级 **Ruff** 代码检查工作流，支持智能生成详细报告与 PR 评论 by @DBJD-CR
- **Badges**: 新增 **屎山指数** 徽章，“含金量”拉满 by @DBJD-CR
- 更新适用于 v1.3.8 的 `README.md` 文档和 `CHANGELOG.md` by @DBJD-CR

---

**Full Changelog**: https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/compare/v1.3.7...v1.3.8

---

# 2026/01/31 v1.3.7

本次更新主要适配了 Fan Studio 上游 API 服务端点变更，支持推送中国地震预警网省级网地震预警，并对台湾地区的地震预警功能进行了升级。

## 🚀 What's Changed

### ✨ New Features (新功能)

- **CWA Upgrade (台湾中央气象署升级)**:
  - 适配了 Fan Studio 新的 `/cwa-eew` 接口，确保地震预警功能正常运行 by @DBJD-CR
  - 新增 **台湾地震报告** (CWA Report) 数据源，支持接收包含震中图、等震度图的正式地震报告 by @DBJD-CR
  - 新增 `locationDesc` 字段解析，支持显示台湾地震预警的 **影响区域** 描述 by @DBJD-CR
  - 新增 `CWAReportFormatter` 消息格式化器，优化台湾地震报告的排版与图片展示 by @DBJD-CR
- **CEA Upgrade (中国地震预警网升级)**:
  - 适配了 Fan Studio 的 `/cea-pr` 接口，支持接收 **省级地震预警中心** 发布的地震预警信息 by @DBJD-CR
  - 新增 `province` 字段识别逻辑，当接收到省级预警时，标题将自动显示为“XX地震局”（如四川地震局） by @DBJD-CR

### 🎨 Visualization (可视化与渲染)
  
- **UI Polish (UI 润色)**:
  - 新增 **强降温预警** Emoji 图标映射 (📉🥶) by @DBJD-CR
  - 优化地震列表卡片的深度显示：0km 智能显示为“极浅”或“ごく浅い”，并自动适配中日文标签 by @DBJD-CR
  
### ♻️ Refactor (架构重构)

- **Config Update**: 更新配置文件结构，新增 `taiwan_cwa_report` 开关，允许用户独立控制预警和报告的推送 by @DBJD-CR
- **Router Logic**: 适配 `handler_registry` 的消息路由逻辑，根据消息特征智能分发至对应的 EEW 或 Report 处理器 by @DBJD-CR
- 移除获取 AstrBot 版本的静态方法，改为使用独立函数获取版本信息 by @Aloys233 in #58

### 🐛 Bug Fixes (修复)

- 修复了因上游 API 变更导致的 CWA 数据源解析错误的问题 by @DBJD-CR
- 修复了在 Windows 系统下时间格式化时因中文字符导致的 `UnicodeEncodeError` 报错 by @DBJD-CR
- 修复了遥测上报其他插件报错的问题 by @Aloys233 in #57
- 修复了 Wolfx 数据源日志过滤策略失效的问题，防止 HTTP 列表数据刷屏仅记录 WebSocket 列表摘要记录 by @DBJD-CR
- 修复了定时清理任务被打断导致临时文件夹 (`/temp`) 中旧图片文件堆积的问题，现在每次启动时会自动清理残留文件 by @DBJD-CR

### 📚 Documentation & Chore (文档与杂项)

- 根据 AI (KIMI K2.5) 审核建议修改了多个代码文件 by @Aloys233 in #57
- 根据 @sourcery-ai[bot] PR review 建议修改了多个代码文件 by @DBJD-CR & @sourcery-ai[bot]
- 更新适用于 v1.3.7 的 `README.md` 文档和 `CHANGELOG.md` by @DBJD-CR & @sourcery-ai[bot]

---

**Full Changelog**: https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/compare/v1.3.6...v1.3.7

---

# 2026/01/27 v1.3.6

Hot Fix For v1.3.5

## 🚀 What's Changed

### 🐛 Bug Fixes (修复)

- 修复了预警消息重复推送的问题 in #55 by @Aloys233
- 修复并增强了遥测的错误上报功能 in #51 by @Aloys233
- 修复了未清理干净的函数调用 by @DBJD-CR

---

**Full Changelog**: https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/compare/v1.3.5...v1.3.6

---

# 2026/01/27 v1.3.5

> [!IMPORTANT]
>
> 由于本次更新重构了 UMO 的获取逻辑，更新后您需要**重新配置需要推送的会话**。你可以使用指令 `/sid` 来快速获取 UMO 或手动构造。
>
> 更多详细的更新内容可查阅 README 文档，感谢您的支持。

本次更新再次重构了插件的部分组件，并引入了 **Leaflet.js** 配合 D3.js 进行更强大的地图渲染。新增了用于帮助改进插件的 **遥测系统** 并调整了 **Wolfx 连接逻辑**，让 Wolfx 数据源也能正常使用。此外，我们还新增了多项实用指令与过滤器，让预警更加直观、精准与智能。

特别感谢 @Aloys233 在遥测系统上做出的贡献！🤝

## 🚀 What's Changed

### ✨ New Features (新功能)

- **Data Fusion (数据融合)**:
  - 新增 **CENC 地震情报融合策略**：智能合并 Fan Studio 与 Wolfx 的数据，利用 Wolfx 的烈度信息补充 Fan 的数据，同时解决 Wolfx 字段不稳定的问题 by @DBJD-CR
  - 增强 **JMA EEW 解析**：支持显示 PLUM 法、训练报、取消报及警报区域等详细信息 by @DBJD-CR
- **Smart Filter (智能过滤)**:
  - 新增 **全局地震关键词过滤器**：支持自定义黑白名单，控制推送范围 by @DBJD-CR
  - 新增 **中国省份常量列表 (Model)**：增强文件复用性，让代码更简洁 by @DBJD-CR
- **Commands (指令系统)**:
  - 新增 `/地震列表查询` 指令：支持查询历史地震记录，并配备了仿 `JQuake` 风格的精美 **卡片渲染模板** by @DBJD-CR
  - 新增 `/灾害预警推送开关` 指令：支持在群组/会话中快速开启或关闭推送功能 by @Aloys233 & @DBJD-CR in #44 & #46
- **Configuration (配置升级)**:
  - **UMO 重构**：全面重构会话构建逻辑，支持更灵活的多平台/多实例推送配置 by @DBJD-CR
  - 新增 **自定义时区** 配置项，优化跨时区服务器的时间显示问题 by @DBJD-CR
  - 新增 **气象预警图标** ，自动根据预警类型代码附加中国气象局官方预警图标 by @DBJD-CR

### 🎨 Visualization (可视化与渲染)

- **Map Engine Upgrade (地图引擎升级)**:
  - **Leaflet.js**：支持更强大的地图瓦片渲染功能 by @Aloys233 in #45
  - 新增适用于所有地震事件的 **基础地图瓦片渲染模板**，告别简陋的链接跳转 by @DBJD-CR
  - 新增用于 `/地震列表查询` 的仿 `JQuake` 风格的卡片模板 by @DBJD-CR
  - 改进了 EEW 类型数据源的地图瓦片渲染行为 by @DBJD-CR
- **UI Polish (UI 润色)**:
  - 优化震源深度显示：添加深度格式化函数，0km 显示为“极浅” by @Aloys233 in #45
  - 调整卡片样式中的部分文字描述 by @DBJD-CR

### ♻️ Refactor (架构重构)

- **Time Utils (时间工具)**：新增专用的时间解析、转换、格式化工具类，统一处理所有时间逻辑，增强鲁棒性 by @DBJD-CR
- **Telemetry (遥测)**:
  - 新增并简单重构了 **遥测管理器**，优化事件上报、错误处理逻辑并调整 Payload 结构以符合新版 API 规范 by @Aloys233 #47
  - 修复遥测管理器初始化时硬编码插件版本的 Bug by @DBJD-CR
- **Connection Strategy (连接策略)**:
  - 重构 **Wolfx 处理器**，支持全量连接策略，解决因连接数限制导致的 503 错误 by @DBJD-CR
  - 移除废弃的 `/灾害预警测试` 指令及相关冗余代码，简化代码结构 by @Aloys233 in #44
  - 更多文件中的的代码清理与格式化工作以及日志调整 by @DBJD-CR

### 🐛 Bug Fixes (修复)

- **Logic**: 修复国内地区统计 Top10 未正确排除国外地震的 Bug by @DBJD-CR
- **Logic**: 修复 Wolfx JMA EEW 没有正确传导报数参数的问题 by @DBJD-CR
- **Logic**: 修复获取 EEW 事件指纹的逻辑，增强时间解析能力 by @DBJD-CR
- **System**: 修复部分函数调用参数错误的问题 by @DBJD-CR
- **Security**: 更新遥测管理器中的编码密钥以增强安全性 by @Aloys233 in #43

### 📚 Documentation (文档)

- **Badges**: 新增 **高仿 GitHub Trending** 与 **Plugin Market Rank** 徽章，排面拉满 by @DBJD-CR
- **Changelog**: 初始提交 - 新增符合 AstrBot v4.12.0+ 规范的 **插件更新日志文档** (`CHANGELOG.md`)，支持在 AstrBot WebUI 直接查看更新日志，并在插件更新完成时自动弹出窗口展示 by @DBJD-CR
- **Guide**: 更新适用于 v1.3.5 的 `README.md` 和 `CONTRIBUTING.md`，以及众多插件文件中的注释 by @DBJD-CR

---

> 下个大版本中将会推出插件自己的 WebUI 并实现精细化的配置管理，敬请期待！

**Full Changelog**: https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/compare/v1.3.1...v1.3.5

---

# 2026/01/12 v1.3.1

> [!WARNING]
> 以下内容由 AI 生成，我只做了简单润色，请仔细甄别

本次更新将灾害预警插件的体验提升到了全新的高度，引入了基于 Playwright 的现代化卡片渲染引擎。同时，我们重构了气象预警过滤器、报数控制器以及底层的网络连接模块，使插件更加稳定、强大且易于配置。

特别感谢 @Aloys233 为本次更新带来的精美卡片模板与渲染逻辑！🎨

## 🚀 What's Changed

### ✨ New Features (新功能)

- **Global Quake Visualization**:
  - 新增 Global Quake **消息卡片推送**功能，支持异步渲染，告别纯文本时代 by @Aloys233 in #21
  - 新增 **Aurora (极光)** 和 **DarkNight (暗夜)** 等多款精美卡片主题模板 by @Aloys233 in #22
  - 新增震中标记描边效果，微调极光主题样式以提升可视性 by @DBJD-CR
  - 新增卡片开关配置项，用户可自由选择文本或图片模式 by @DBJD-CR
- **Weather Filter 2.0**:
  - 全新的气象预警过滤器，支持按 **省份/地区白名单** 进行精准投递 by @DBJD-CR
  - 支持按 **预警颜色级别** (🔵/🟡/🟠/🔴) 进行过滤 by @DBJD-CR
  - 优化气象预警展示，为不同类型的灾害添加了专属 **Emoji 图标** by @DBJD-CR
- **Granular Control**:
  - **拆分报数控制器**：将原本全局统一的报数限制拆分为三套独立配置 (CEA/CWA, JMA, Global Quake)，默认值更科学 by @DBJD-CR
  - 新增 **插件启动静默期** 配置，防止重启时旧消息刷屏 by @DBJD-CR
  - 新增 **管理员配置项** 与指令权限分级逻辑 by @DBJD-CR
- **Statistics**:
  - 新增 `StatisticalManager` 统计管理器，支持更丰富和统一的事件记录 by @DBJD-CR
  - 新增气象预警与 CENC 地震测定的 **地区统计功能** by @DBJD-CR
  - 回归并增强 `/灾害预警统计` 指令，新增 `/灾害预警统计清除` 指令 by @DBJD-CR

### ♻️ Refactor (重构)

- **Network Overhaul**: **彻底移除 `websockets` 库依赖**，全面迁移至 `aiohttp` 重构 WebSocket 连接管理，解决兼容性问题并提升稳定性 by @DBJD-CR
  - **Command System**:
  - 重构 `/灾害预警状态`，提供数据源状态、运行时间等更有价值的调试信息 by @DBJD-CR
  - 重构 `/灾害预警配置`，现在直接返回完整的 JSON 配置内容，所见即所得 by @DBJD-CR
- **Log Optimization**: 优化 Wolfx 数据源的日志记录逻辑，支持配置最大记录数，防止 HTTP 轮询导致日志文件冗余 by @Aloys233 & @DBJD-CR in #20
- **Image Cache**: 实现了图片缓存文件的自动清理机制，防止磁盘空间占用过大 by @DBJD-CR

### 🐛 Bug Fixes (修复)

- **Critical**: 修复了自动清理任务中因时区问题导致的报错 by @DBJD-CR
- **Logic**: 修复了“只推送最终报”功能失效的问题 by @DBJD-CR
- **Logic**: 修复了 KMA (韩国气象厅) 消息被错误识别为 CWA (台湾中央气象署) 的问题 by @DBJD-CR
- **Config**: 修复了推送间隔为 0 时逻辑判断错误的问题 by @Aloys233 in #21
- **System**: 修复了临时文件路径创建逻辑，确保正确使用 AstrBot 提供的数据目录 by @Aloys233 & DBJD-CR in #22 & #26
- **Data**: 修复了 Wolfx 地震信息测定字段解析错误的问题 by @DBJD-CR

### 📚 Documentation & Chore (文档与杂项)

- **Docs**: 更新适用于 v1.3.1 的 README 文档，补充新功能说明 by @DBJD-CR
- **Deps**: 更新 `requirements.txt` 依赖列表 (新增 `playwright` 等) by @DBJD-CR
- **UI**: 为 WebUI 的数值配置项添加滑动条组件 (Slider) 支持 by @DBJD-CR
- **I18n**: 调整 MaxIntensity 键名映射与 Emoji 映射行为 by @DBJD-CR

---

## ❤️ New Contributors

@sourcery-ai[bot] made their first contribution (Grammar fix) in #26

**Full Changelog**: https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/compare/v1.2.3...v1.3.1

---

# 2026/01/01 v1.2.3

本次更新主要修复了 Fan 数据源的连接问题，并新增了气象预警过滤白名单功能。

## 🚀 What's Changed

### ✨ New Features (新功能)

- 新增按省份（包括直辖市与港澳台地区）过滤气象预警  by @Aloys233 in #19

### ♻️ Refactor (重构)

- Fan Studio API 使用新的 `/all` 路径建立连接，减少重复连接和资源浪费 by @DBJD-CR
- 设计了新的兜底重试机制，将原有的重连机制改为短时间内的重连行为与长时间的自动重试机制结合，并提取为常量支持在 WebUI 中进行配置 by @Aloys233 in #19

### 🐛 Bug Fixes (修复)

- 修复日本气象厅（JMA）：紧急地震速报选项失效的问题 by @Aloys233 in #17
- 修复了本地预估烈度功能没有正常工作的问题 by @Aloys233 in #18
- 修复了部分数据源遇到整数震级时的小数点位数显示问题，统一显示一位小数 by @Aloys233 in #19

### 📚 Documentation & Chore (文档与杂项)

- 更新适用于 v1.2.3 的 README 文档 by @DBJD-CR
- 使用 Ruff 格式化代码并修复潜在问题 by @DBJD-CR

---

> 我们在 1.3.0 版本中会专注于优化推送范围和过滤等社区反馈的问题，并引入新的消息卡片，敬请期待！

**Full Changelog**: https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/compare/v1.2.2...v1.2.3

---

# 2025/12/24 v1.2.2 (功能完备版)

> [!WARNING]
> 以下内容由 AI 生成，我只做了简单润色，请仔细甄别

本次更新正式完成了对  **Global Quake** 数据源的支持，引入了专用过滤器和更丰富的数据字段，并修复了主备服务器切换机制失效等关键问题。自此，本插件终于完整实现了发布之初时的所有功能描述。

感谢 @Aloys233 在接入 Global Qukae 数据源上的贡献！

## 🚀 What's Changed

### ✨ New Features (新功能)

- 新增 Global Quake 专用过滤器配置选项，支持更精细的推送控制 by @DBJD-CR
- 支持显示 **最大加速度 (PGA)** 和 **触发测站数量** 字段 by @DBJD-CR
- 优化震级和深度的格式化显示，确保与其他数据源风格一致 by @Aloys233 in #11
- 全面修改过滤器逻辑为 **OR (或)** 关系，现在只要满足任意一个启用过滤器的条件即会推送 by @DBJD-CR

### ♻️ Refactor (重构)

- 拆分数据处理器 (`data_handlers`) 和消息格式化器 (`message_formatters`)，代码结构更清晰 by @Aloys233 in #10
- 规范包的导出结构，优化模块引用 by @DBJD-CR
- 移除重构后的冗余逻辑代码 by @DBJD-CR

### 🐛 Bug Fixes (修复)

- 修复了主备服务器切换机制失效的问题，提升服务可用性 by @DBJD-CR
- 修复了因 API 字段变动导致 CWA 推送被错误过滤的问题 by @DBJD-CR

### 📚 Documentation & Chore (文档与杂项)

- 更新适用于 v1.2.2 的 README 文档 by @DBJD-CR
- 使用 Ruff 格式化代码并修复潜在问题 by @DBJD-CR

---

> 我们在下个版本中会专注于优化推送范围和过滤等社区反馈的问题，敬请期待！

**Full Changelog**: https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/compare/v1.2.0...v1.2.2

---

# 2025/12/20 v1.2.0

> [!WARNING]
> 以下内容由 AI 生成，我只做了简单润色，请仔细甄别

本次更新修复了 v1.1.0 中存在的众多 Bug 与推送问题，并引入了许多新功能。

特别感谢 @Aloys233 在本版本中的杰出贡献！🎉

## 🚀 What's Changed

### ✨ New Features (新功能)

- 新增本地烈度计算器（根据震级和距离估算），并支持 USGS 英文地名自动翻译为中文 by @Aloys233 in #5
- 新增 **Fan Studio JMA EEW** (日本气象厅紧急地震速报) 数据源支持 by @Aloys233 in #8
- 实现 Fan Studio 主/备服务器连接与故障自动切换逻辑 by @Aloys233 in #8
- 新增 `/灾害预警模拟` 命令，方便测试和预览预警效果 by @Aloys233 in #5
- 优化预估本地烈度在消息中的展示，使用 Emoji 图标直观展示烈度等级 by @DBJD-CR
- 添加气象预警去重缓存，防止短时间内因重连导致的重复推送 by @DBJD-CR

### ♻️ Refactor (重构)

- 将散落在根目录的代码文件归类至 `core/`, `models/`, `utils/` 等模块，并使其成为规范的 Python 包 by @Aloys233 in #5
- 重构 Global Quake 配置板块，移除冗余开关并合并相关设置 by @Aloys233 in #8
- 部分重构消息处理与过滤逻辑，移除无效的数据源配置与映射 by @DBJD-CR

### 🐛 Bug Fixes (修复)

- 修复了时区问题导致的时间窗口过滤失效 bug by @DBJD-CR
- 修复 WebSocket 连接成功后重试次数未重置的问题 by @Aloys233 in #5
- 修复查看 `/灾害预警状态` 命令失效的问题 by @Aloys233 in #5
- 修复了部分数据源映射错误 by @Aloys233 in #8

### 📚 Documentation & Chore (文档与杂项)

- 添加 `CONTRIBUTING.md` (贡献指南) 和 `CODE_OF_CONDUCT.md` (行为准则) by @DBJD-CR
- 更新适用于 v1.2.0 的 README 文档 by @DBJD-CR
- 使用 Ruff 格式化代码 by @DBJD-CR
- 更新 `.gitignore` 忽略 IDE 配置文件 by @Aloys233 in #5

---

## ❤️ New Contributors

- @Aloys233 made their first contribution in #5

**Full Changelog**: https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/compare/v1.1.0...v1.2.0

---

# 2025/12/13 v1.1.0

> [!WARNING]
> 以下内容由 AI 生成，我只做了简单润色，请仔细甄别

本次更新对插件架构进行了深度重构，重点优化了多源数据的处理逻辑、推送策略及消息展示效果，旨在提供更精准、专业的灾害预警服务。

## 🚀 What's Changed

### ♻️ 核心架构重构

- **数据源处理细分**：针对不同数据源（CEA, CWA, JMA, USGS 等）实现了独立的解析与处理流程，确保每个数据源的特性（如字段定义、状态标识）都能被准确识别。
- **过滤器拆分**：将原有的全局过滤器拆分为“震级+烈度”和“震级+震度”两套独立系统，并新增 USGS 专用的震级过滤器，实现了更精细的阈值控制。
- **报数控制优化**：明确了报数控制的作用范围，仅对 EEW（紧急地震速报）类数据源生效，避免误拦截 CENC、USGS 等非报数类情报。

### ✨ 功能增强与优化

- **多源协同去重**：
  - 调整了去重策略，不再简单屏蔽后续数据源。现在允许多个数据源对同一事件进行推送，实现了多源信息的互补。
  - 强化了**单数据源内部去重**，有效防止同一数据源因网络波动或重复分发导致的刷屏问题。
- **专业消息格式化**：
  - 全新设计的消息模板，针对不同数据源定制了专属的 Emoji 和字段布局。
  - 实现了智能状态标识：
    - **CENC/USGS**：自动区分 [自动测定] 与 [正式测定]。
    - **JMA**：自动识别 [震度速报]、[震源相关情报] 与 [震源・震度情报] 以及更多情报类型。
    - **JMA EEW**：根据预估最大震度自动判断 [予报] 或 [警报]。
- **USGS 数据源优化**：新增了针对 USGS 的专用去重逻辑和状态升级机制（Automatic -> Reviewed），确保信息的准确性与时效性。

### 🛠️ 系统稳定性

- **日志系统适配**：全面适配新架构，确保所有数据源的原始消息都能被正确记录和格式化，保留了核心的垃圾信息过滤功能。
- **配置结构调整**：优化了配置文件结构，支持更细粒度的数据源开关和参数设置。

### 🐛 问题修复

- 修复了原始消息记录器无法写入日志的问题。
- 修复了`测试预警命令失效`的问题。
- 修复了 WebSockets 库版本的兼容性问题，并添加依赖版本控制。@jinyiwei2012 in #4

---

## New Contributors

- @jinyiwei2012 made their first contribution in #4

---

# 2025/12/06 v1.0.0

> [!WARNING]
> 以下内容由 AI 生成，我只做了简单润色，请仔细甄别

# 🚀 AstrBot 灾害预警插件 v1.0.0

AstrBot 多数据源灾害预警插件的首个发行版。

## ✨ 主要功能

- **多数据源支持**：USGS、JMA、中国地震台网、气象预警、P2P地震网络......
- **智能消息处理**：重复事件过滤、类型分类、原始消息记录
- **灵活配置**：自定义推送规则、震级阈值、地区筛选

## 🚧 已知限制

- 已知部分地图服务商的缩放级别参数可能不生效
- 部分数据源无法写入原始消息日志
- Global Quake 服务基本处于不可用状态
