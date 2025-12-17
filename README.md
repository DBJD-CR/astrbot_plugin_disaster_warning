<div align="center">

# 🚨 AstrBot 灾害预警插件

# Disaster Warning Plugin for AstrBot

</div>

<p align="center">
  <img src="https://img.shields.io/badge/License-AGPL_3.0-blue.svg" alt="License: AGPL-3.0">
  <img src="https://img.shields.io/badge/Python-3.10+-blue.svg" alt="Python 3.10+">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/AstrBot-v4.7.4%20Compatible-brightgreen.svg" alt="Compatible with AstrBot v4.7.4">
  <img src="https://img.shields.io/badge/Release-v1.1.0-brightgreen.svg" alt="Release">
  <img src="https://img.shields.io/badge/QQ群-1033089808-12B7F3.svg" alt="QQ Group">
</p>

[![Moe Counter](https://count.getloli.com/get/@DBJD-CR2?theme=moebooru)](https://github.com/DBJD-CR/astrbot_plugin_disaster_warning)
<img width="256" height="256" align="right" alt="logo" src="https://github.com/user-attachments/assets/6b691800-a02e-43b0-87be-e6d438f6d264" />

---

  一个为 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 设计的，功能强大的多数据源灾害预警插件，它能让你的 Bot 提供实时的地震、海啸、气象预警信息推送服务。

## 📑 快速导航

<div align="center">

| 🧭 章节 | ℹ️ 内容 |
|---------|---------|
| [✨ 功能特性](#-功能特性) | 多数据源支持与智能推送 |
| [🚀 安装与使用](#-安装与使用) | 安装步骤与配置示例 |
| [📊 推送示例](#-推送示例) | 地震/海啸/气象预警推送示例 |
| [📋 使用命令](#-使用命令) | 所有可用命令与示例 |
| [🏗️ 系统架构](#system-architecture) | 完整架构图与详细说明 |
| [⚙️ 架构细节](#architecture-details) | 配置参数与技术细节 |
| [🔧 调试功能](#-调试功能) | 日志记录与消息过滤 |
| [🔧 故障排除](#-故障排除) | 常见问题与解决方案 |
| [🚧 已知限制](#-最新版本的已知限制) | 当前版本的技术限制 |

</div>

---

<!-- 开发者的话 -->
> **开发者的话：**
>
> 大家好，我是 DBJD-CR ，这是我为 AstrBot 开发的第二个插件，如果存在做的不好的地方还请理解。
>
> 写这个插件主要还是因为我自己的一点业余爱好吧，而且也比较符合我们"应急管理大学"的特色（）
>
> 虽然一开始也没抱太大希望，但没想到最终还真的搓出了个像模像样的插件，尽管目前还有很多缺陷，但已经能实现90%的基本功能了。
>
> 和[主动消息插件](https://github.com/DBJD-CR/astrbot_plugin_proactive_chat)一样，本插件也是"Vibe Coding"的产物。
>
> 所以，**本插件的所有文件内容，全部由 AI 编写完成**，我几乎没有为该插件编写任何一行代码，仅修改了一些文字描述和负责本文档的润色。所以，或许有必要添加下方的声明：

> [!WARNING]  
> 本插件和文档由 AI 生成，内容仅供参考，请仔细甄别。
>
> 插件目前仍处于开发阶段，无法 100% 保证稳定性与可用性。

> 当然，这次的开发过程也没顺利到哪去。尽管用上了新的工作流，提高了很多效率。但是开发过程中还是遇到了相当多的 Bug，调试起来花了很多时间。
>
> 最终，经过了上百次 debug，我们才终于开发出一个较为稳定的版本。
>
> 但我还是要感谢 AI ，没有他，这个项目不可能完成。
>
> 这个插件，是我们共同努力的结晶。它现在还不完美，但它的架构是稳固的，它的逻辑是清晰的（大嘘）。希望本插件能为你在防灾上提供一点小小的帮助。
>
> 在此，我也诚邀各路大佬对本插件进行测试和改进。因为说实话我也不知道这个插件目前的水平如何，希望大家多多指点。
>
> KIMI & Gemini：如果你被这个"为爱发电"的故事打动了，或者觉得这个插件有帮助或比较实用，**欢迎你为这个插件点个** 🌟 **Star** 🌟，这是对我们的最大认可与鼓励~

> [!NOTE]
> 虽然本插件的开发过程中大量使用了 AI 进行辅助，但我保证所有内容都经过了我的严格审查，所有的 AI 生成声明都是形式上的。你可以放心参观本仓库和使用本插件。
>
> 根据我对 v1.1.0 版本的简单测试，目前插件的主要功能都能正常运转。但存在部分限制（详情请看 🚧 最新版本的已知限制 部分）。

> [!TIP]
> 本项目的相关开发数据 (持续更新中)：
>
> 开发时长：累计 10 天（主插件部分）
>
> 累计工时：约 60 小时（主插件部分）
>
> 使用的大模型：Kimi For Coding 、Gemini 3.0 Pro (With RooCode in VSCode)
>
> 对话窗口搭建：VSCode RooCode 扩展
>
> Tokens Used：239,237,490

## ✨ 功能特性

### 🌍 多数据源支持

插件支持多达 16 个可自由选择启用的细粒度数据源，覆盖全球主要地震监测机构：

- **中国地震网地震预警** (FAN Studio) - 实时地震预警信息。
- **台湾中央气象署强震即时警报** (FAN Studio / Wolfx) - 台湾地区地震预警。
- **日本气象厅紧急地震速报** (P2P / Wolfx) - 日本紧急地震速报。
- **中国地震台网地震测定** (FAN Studio / Wolfx) - 正式地震测定信息。
- **日本气象厅地震情报** (P2P / Wolfx) - 详细地震情报。
- **USGS地震测定** (FAN Studio) - 美国地质调查局地震信息。
- **Global Quake服务器** - 全球地震测站实时计算推送，精度有限。
- **中国气象局气象预警** (FAN Studio) - 气象灾害预警。
- **自然资源部海啸预警中心** (FAN Studio) - 海啸预警信息。
- **日本气象厅海啸预报** (P2P) - 日本海啸预报信息。

### 🎯 智能推送控制

- **阈值过滤** - 根据震级、烈度、震度设置推送阈值。
- **频率控制** - 可选的基于报数的智能推送，避免短时间内刷屏。
- **首报推送保证** - 确保预警信息首次下达时总是推送。
- **最终报保证** - 确保最终报总是推送。

### 🔁 事件去重功能

插件具备基础的事件去重功能，防止同一地震被同一个数据源重复推送：

**去重规则**：

- **时间窗口**：1 分钟内接收到的相似事件（无报数更新信息等）视为同一事件。
- **位置容差**：经纬度差异在 20 公里内视为同一事件。
- **震级容差**：震级差异在 0.5 级内视为同一事件。

### 📱 灵活配置

- **WebUI配置** - 支持通过 AstrBot WebUI 界面进行配置。
- **多群推送** - 支持配置特定 QQ 群接收预警（留空则不推送）。
- **专门格式化** - 统一的消息格式，确保信息完整。

## 🚀 安装与使用

1. **下载插件**: 通过 AstrBot 的插件市场下载。或从本 GitHub 仓库的 Release 下载 `astrbot_plugin_disaster_warning` 的 `.zip` 文件，在 AstrBot WebUI 中的插件页面中选择 `从文件安装` 。
2. **安装依赖**: 本插件的核心依赖大多已包含在 AstrBot 的默认依赖中，通常无需额外安装。如果你的环境中缺少以下依赖，请安装：

   ```bash
   pip install python-dateutil asyncio-mqtt
   ```

3. **重启 AstrBot (可选)**: 如果插件没有正常加载或生效，可以尝试重启你的 AstrBot 程序。
4. **配置插件**: 进入 WebUI，找到 `astrbot_plugin_disaster_warning` 插件，选择 `插件配置` 选项，配置相关参数。

### 阈值设置示例

```text
最小震级: 2.0        # 低于M2.0的地震不推送
最小烈度: 4.0        # 低于烈度4度的地震不推送
```

```text
最小震级: 2.0        # 低于M2.0的地震不推送
最小震度: 1.0        # 低于震度1的地震不推送
```

### 推送频率控制示例

```text
每收到N报推送一次: 1    # 每1报推送一次
最终报是否总是推送: true  # 最终报必定推送
是否忽略非最终报: false   # 不忽略中间报
```

## 📊 推送示例

### 地震预警推送示例

**中国地震预警网示例**：

```text
🚨[地震预警] 中国地震预警网
📋第 3 报(最终报)
⏰时间：2025年12月04日 15时44分05秒 (UTC+8)
📍震中：新疆克孜勒苏州阿合奇县 (41.12°N, 78.54°E)
📊震级：M 6.0
🏔️深度：10 km
💥预估最大烈度：7.8
🗺️地图链接: ......
```

**日本气象厅紧急地震速报示例**：

```text
🚨[紧急地震速报] [警报] 日本气象厅
📋第 5 报(最终报)
⏰时间：2025年12月04日 18时04分00秒 (UTC+9)
📍震中：十勝地方中部 (42.80°N, 143.20°E)
📊震级：M 5.8
🏔️深度：50 km
💥预估最大震度：5.0
⚠️警报区域：
  北海道道央(已到达)、北海道道南(未到达)、北海道道东(未到达)
🗺️地图链接: ......
```

**USGS地震情报示例**：

```text
🚨[地震情报] 美国地质调查局(USGS) [正式测定]
⏰时间：2025年12月04日 11时57分06秒 (UTC+8)
📍震中：46 km NNW of San Antonio, Puerto Rico (18.87°N, -67.28°W)
📊震级：M 3.2
🏔️深度：46.2 km
🗺️地图链接: ......
```

### 海啸预警推送示例

**中国海啸预警示例**：

```text
🌊[海啸预警]
📋海啸黄色警报
⚠️级别：黄色
🏢发布：自然资源部海啸预警中心
⏰发布时间：2025年07月15日 23时30分15秒 (UTC+8)
🌍震源：台湾花莲东部海域
📍台湾花莲 [黄色] 预计23:45到达 波高50-100cm
📍台东成功 [黄色] 预计00:15到达 波高30-80cm
  ...等5个预报区域
🔄事件编号：TS2025071501
```

**日本气象厅津波予報示例 (P2P)**：

```text
🌊[津波予報] 日本气象厅
📋津波注意報
⚠️級別：津波注意報
🏢発表：日本气象厅
⏰発表時刻：2025年12月04日 18时10分00秒 (UTC+9)
📍津波予報区域：
  • 北海道太平洋沿岸中部 (预计18:30到达) 🌊1m
  • 北海道太平洋沿岸东部 (预计18:40到达) 🌊0.5m
🔄事件ID：552
```

### 气象预警推送示例

```text
⛈️[气象预警]
📋广东省阳江市发布暴雨橙色预警信号
📝【阳江分镇暴雨红色预警降级为橙色】过去3小时，我市中北部出现强降水，预计强降水仍将持续，阳江市气象台于2025年4月25日12时37分将阳江分镇暴雨红色预警信号降级为橙色，请继续做好防御工作。
⏰生效时间：2025年04月25日 12时37分00秒 (UTC+8)
```

## 📋 使用命令

插件提供以下命令：

| 命令 | 描述 |
|------|------|
| `/灾害预警` | 显示插件帮助信息 |
| `/灾害预警状态` | 查看服务运行状态 |
| `/灾害预警测试 [群号] [灾害类型] [格式]` | 测试推送功能 |
| `/灾害预警统计` | 查看推送统计信息 |
| `/灾害预警配置 查看` | 查看当前配置摘要 |
| `/灾害预警去重统计` | 查看事件去重统计信息 |
| `/灾害预警模拟 <纬度> <经度> <震级> [深度] [数据源] [地名]` | 模拟地震事件测试 |
| `/灾害预警日志` | 查看原始消息日志统计 |
| `/灾害预警日志开关` | 开关原始消息日志记录 |
| `/灾害预警日志清除` | 清除所有原始消息日志 |

### 命令示例

```bash
# 查看服务状态
/灾害预警状态

# 测试推送到当前群（默认地震预警）
/灾害预警测试

# 测试推送到当前群（指定灾害类型，命令也支持中文，如 地震|海啸|气象|中国|日本|美国）
/灾害预警测试 earthquake     # 测试地震预警
/灾害预警测试 tsunami        # 测试海啸预警
/灾害预警测试 weather        # 测试气象预警

# 测试推送到当前群（指定灾害类型和格式）
/灾害预警测试 earthquake japan  # 测试日本地震格式
/灾害预警测试 earthquake usgs   # 测试美国地震格式

# 测试推送到指定群（默认地震预警）
/灾害预警测试 123456789

# 测试推送到指定群（指定灾害类型）
/灾害预警测试 123456789 earthquake  # 在群123456789测试地震预警
/灾害预警测试 123456789 tsunami     # 在群123456789测试海啸预警
/灾害预警测试 123456789 weather     # 在群123456789测试气象预警

# 查看统计信息
/灾害预警统计

# 模拟地震事件（用于测试过滤器和本地监控）
/灾害预警模拟 39.9 116.4 5.5           # 北京 M5.5 默认深度10km
/灾害预警模拟 35.6 139.7 6.0 30        # 东京 M6.0 深度30km
/灾害预警模拟 39.9 116.4 4.0 10 usgs_fanstudio "Test Location"  # 指定数据源和地名
```

---

## 📂 插件目录与结构

目录结构示例：

```bash
AstrBot/
└─ data/
   └─ plugins/
      └─ astrbot_plugin_disaster_warning/
         ├─ __init__.py                    # Python包初始化文件，支持相对导入
         ├─ _conf_schema.json              # WebUI配置界面schema定义
         ├─ main.py                        # 插件主入口文件，包含命令处理
         ├─ metadata.yaml                  # 插件元数据信息
         ├─ README.md                      # 插件说明文档
         ├─ requirements.txt               # 插件依赖列表
         ├─ logo.png                       # 插件Logo，适用于AstrBot v4.5.0+
         ├─ LICENSE                        # 许可证文件
         ├─ core/                          # 核心模块目录
         │   ├─ __init__.py
         │   ├─ disaster_service.py        # 核心灾害预警服务
         │   ├─ websocket_manager.py       # WebSocket连接管理器
         │   ├─ data_handlers.py           # 各数据源消息处理器
         │   ├─ message_manager.py         # 消息推送管理器
         │   ├─ message_formatters.py      # 专用消息格式化器
         │   └─ message_logger.py          # 原始消息记录器
         ├─ models/                        # 数据模型目录
         │   ├─ __init__.py
         │   ├─ models.py                  # 数据模型定义（地震、海啸、气象等）
         │   └─ data_source_config.py      # 数据源配置管理器
         ├─ utils/                         # 工具模块目录
         │   └─ fe_regions.py              # FE地震区划中文翻译
         └─ resources/                     # 资源文件目录
             └─ epsp-area.csv              # P2P地震区域代码映射表
```

插件运行时会自动创建数据存储目录：

```bash
AstrBot/
└─ data/
   └─ plugin_data/
      └─ astrbot_plugin_disaster_warning/
         ├─ raw_messages.log               # 原始消息日志文件（启用时）
         ├─ raw_messages.log.1             # 轮转日志文件（自动管理）
         └─ raw_messages.log.2             # 更多轮转文件...
```

---

## <span id="system-architecture">🏗️ 系统架构</span>

### 📊 架构图

```mermaid
graph TD
    %% 样式定义
    classDef source fill:#e1f5fe,stroke:#0277bd,stroke-width:2px,color:#01579b;
    classDef connection fill:#fff3e0,stroke:#ef6c00,stroke-width:2px,color:#e65100;
    classDef service fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px,color:#1b5e20;
    classDef logic fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px,color:#4a148c;
    classDef output fill:#ffebee,stroke:#c62828,stroke-width:2px,color:#b71c1c;
    classDef storage fill:#eceff1,stroke:#455a64,stroke-width:2px,color:#263238;

    %% 数据源层
    subgraph DataSources [🌍 数据源层 - Data Sources]
        direction TB
        FS[FAN Studio<br/>CEA/CWA/CENC/USGS/Weather/Tsunami]:::source
        P2P[P2P Quake<br/>JMA EEW/Info/Tsunami]:::source
        Wolfx[Wolfx<br/>JMA/CENC/CWA]:::source
        GQ[Global Quake<br/>Global Seismic]:::source
    end

    %% 插件核心系统
    subgraph CoreSystem [⚙️ 插件核心系统 - Core System]
        direction TB
        
        %% 连接与获取层
        subgraph ConnectionLayer [🔌 连接与获取 - Connection Layer]
            WSM[WebSocket Manager<br/>连接管理/自动重连/心跳保活]:::connection
            HTTP[HTTP Fetcher<br/>定时轮询获取]:::connection
            TCP[TCP Client<br/>Global Quake 专用连接]:::connection
        end

        %% 服务控制层
        subgraph ServiceLayer [🎮 服务控制 - Service Layer]
            DWS[DisasterWarningService<br/>核心服务协调器]:::service
            Logger[Message Logger<br/>原始消息记录/过滤/统计]:::service
        end

        %% 数据处理层
        subgraph ProcessingLayer [🧠 数据处理 - Processing Layer]
            Handlers[Data Handlers<br/>多源数据解析器工厂]:::logic
            
            subgraph Parsers [具体解析器]
                direction LR
                CEA_H[CEA Handler]:::logic
                JMA_H[JMA Handler]:::logic
                USGS_H[USGS Handler]:::logic
                Other_H[Weather/Tsunami Handlers]:::logic
            end
            
            Model[DisasterEvent Model<br/>统一事件模型 - Earthquake/Tsunami/Weather]:::logic
        end

        %% 消息管理层
        subgraph ManagerLayer [🛡️ 消息管理 - Manager Layer]
            MPM[MessagePushManager<br/>消息推送决策中心]:::logic
            
            subgraph Filters [智能过滤系统]
                direction TB
                Dedupe[EventDeduplicator<br/>多源事件去重 - 时间/位置/震级]:::logic
                Thres[Threshold Filters<br/>烈度/震级/震度阈值过滤]:::logic
                Freq[ReportController<br/>EEW报数频率控制]:::logic
            end
            
            Formatter[MessageFormatters<br/>多源消息格式化 & 地图生成]:::logic
        end
    end

    %% 存储层
    subgraph StorageLayer [💾 存储层 - Storage]
        LogFile[Raw Messages Log<br/>原始消息日志]:::storage
        Config[Plugin Config<br/>配置文件]:::storage
    end

    %% 输出层
    subgraph OutputLayer [🚀 输出层 - Output]
        AstrBot[AstrBot Context<br/>消息发送接口]:::output
        User[用户/群组<br/>QQ/Telegram/钉钉等]:::output
    end

    %% 数据流向
    FS --> |WebSocket| WSM
    P2P --> |WebSocket| WSM
    Wolfx --> |WebSocket| WSM
    Wolfx --> |HTTP| HTTP
    GQ --> |TCP| TCP

    WSM --> |原始消息流| DWS
    HTTP --> |JSON数据| DWS
    TCP --> |原始数据| DWS

    DWS --> |记录日志| Logger
    Logger -.-> |写入| LogFile
    
    DWS --> |分发消息| Handlers
    Handlers --> |调用| Parsers
    Parsers --> |标准化| Model
    Model --> |统一事件对象| DWS
    DWS --> |事件流| MPM

    MPM --> |读取配置| Config
    MPM --> |1.去重检查| Dedupe
    Dedupe --> |通过| Thres
    Thres --> |2.阈值检查| Freq
    Freq --> |3.频率控制| Formatter
    Formatter --> |构建消息链| AstrBot
    AstrBot --> |最终推送| User

    %% 补充说明
    Dedupe -.-> |过滤重复事件| MPM
    Thres -.-> |过滤低阈值事件| MPM
    Freq -.-> |过滤中间报数| MPM
```

### 📋 架构特点

1. **模块化设计**：
    - **连接层**：`WebSocketManager` 统一管理所有 WebSocket 连接，支持自动重连、心跳保活和多路复用，确保数据链路的稳定性。
    - **处理层**：采用工厂模式管理的 `DataHandlers`，针对不同数据源（FAN Studio, P2P, Wolfx 等）提供专门的解析器，易于扩展新的数据源。
    - **管理层**：`MessagePushManager` 集中管理推送逻辑，将去重、过滤、频率控制等策略与具体业务解耦。

2. **多源数据融合与去重**：
    - 插件支持同时连接多个数据源（如同时监听 FAN Studio 和 Wolfx 的 CEA 数据）。
    - `EventDeduplicator` 实现了基于**时间窗口**（1分钟）、**地理位置**（20km容差）和**震级**（0.5级容差）的智能去重算法，有效避免了多数据源带来的重复推送问题，同时保留了同一事件的更新能力（如报数更新、参数修正）。

3. **精细化推送控制**：
    - **阈值过滤**：支持针对不同数据源类型设置独立的过滤规则（如针对 CEA 使用烈度阈值，针对 USGS 使用震级阈值）。
    - **频率控制**：`ReportCountController` 专为 EEW（紧急地震速报）设计，支持"首报必推"、"最终报必推"以及"每 N 报推送一次"的策略，在时效性和打扰度之间取得平衡。

4. **强大的调试与监控能力**：
    - `MessageLogger` 提供了详尽的原始消息记录功能，支持自动过滤心跳包、P2P 节点状态等冗余信息。
    - 日志文件支持自动轮转和清理，且提供了可读性极强的格式化输出，极大地方便了问题排查和新数据源的开发分析。

---

## <span id="architecture-details">⚙️ 架构细节</span>

### 地图链接配置

插件支持在地震信息中自动添加地图链接：

```json
{
  "message_format": {
    "include_map": true,          // 是否包含地图链接
    "map_provider": "baidu",      // 地图服务商（推荐百度或高德）
    "map_zoom_level": 5           // 缩放级别（1-20），推荐5（约100公里比例尺）
  }
}
```

支持的地图服务商：

- `openstreetmap` - 免费开源地图。
- `google` - Google地图。
- `baidu` - 百度地图（推荐，中国大陆访问更稳定，并且目前做了专门优化）。
- `amap` - 高德地图（推荐，中国大陆访问更稳定）。

### WebSocket连接配置

```json
{
  "websocket_config": {
    "reconnect_interval": 10,      // 重连间隔（秒）
    "connection_timeout": 15,      // 连接超时（秒）
    "heartbeat_interval": 120      // 心跳间隔（秒）
  }
}
```

### FAN Studio 备用服务器配置

FAN Studio 提供主备两个服务器地址，插件会自动进行故障转移：

- **主服务器**: `wss://ws.fanstudio.tech/[路径]`
- **备用服务器**: `wss://ws.fanstudio.hk/[路径]`

**自动切换机制**：

- 当主服务器连接失败达到最大重试次数（默认 3 次）后，自动切换到备用服务器
- 备用服务器也失败 3 次后，停止重连
- 使用指数退避策略（30s → 60s → 120s → 240s）减少服务器压力

### Global Quake服务器配置

在 `data_sources.global_quake` 中配置服务器地址（启动 global_quake 功能后生效）：

```json
{
  "data_sources": {
    "global_quake": {
      "enabled": false,
      "primary_server": "server-backup.globalquake.net",
      "primary_port": 38000,
      "secondary_server": "server-backup.globalquake.net",
      "secondary_port": 38000
    }
  }
}
```

## 🔧 调试功能

### 原始消息格式记录

插件支持记录所有数据源的原始消息格式，便于开发和分析：

```json
{
  "debug_config": {
    "enable_raw_message_logging": true,      // 启用原始消息记录
    "raw_message_log_path": "raw_messages.log",  // 日志文件名
    "log_max_size_mb": 50,                   // 单个日志文件最大大小(MB)
    "log_max_files": 5,                      // 保留的日志文件数量
    "filter_heartbeat_messages": true,       // 过滤心跳包消息
    "filtered_message_types": ["heartbeat", "ping", "pong"],  // 过滤的消息类型
    "filter_p2p_areas_messages": true,       // 过滤P2P节点状态消息
    "filter_duplicate_events": true,         // 过滤重复地震事件
    "filter_connection_status": true         // 过滤连接状态消息
  }
}
```

#### 增强的可读性日志格式

插件提供**自动格式化的高可读性日志**，将原始的 JSON 数据转换为易读的中文格式。以下是部分示例：

**FAN Studio USGS地震测定**：

```text
===================================
🕐 日志写入时间: 2025-12-04 12:28:18
📡 来源: websocket_fan_studio_usgs
📋 类型: websocket_message
🔗 连接: URL: wss://ws.fanstudio.tech/usgs

📊 原始数据:
    📋 消息类型: initial
    📋 Data:
      📋 ID: 71501338
      📋 标题: M 3.2 - 46 km NNW of San Antonio, Puerto Rico
      📋 信息类型: reviewed
      📋 震级: M3.18
      📋 地名: 46 km NNW of San Antonio, Puerto Rico
      📋 震动时间: 2025-12-04 11:57:06
      📋 更新时间: 2025-12-04 12:27:09
      📋 经度: -67.2761666666667
      📋 纬度: 18.8746666666667
      📋 深度(km): 46.2km
      📋 官方链接: https://earthquake.usgs.gov/earthquakes/eventpa...
    📋 校验码: 9be951e4461d496a0094fe2b6546d8cf

🔧 插件版本: 1.1.0
===================================
```

**FAN Studio中国地震预警网**：

```text
===================================
🕐 日志写入时间: 2025-12-04 12:32:13
📡 来源: websocket_fan_studio_cea
📋 类型: websocket_message
🔗 连接: URL: wss://ws.fanstudio.tech/cea

📊 原始数据:
    📋 消息类型: initial
    📋 Data:
      📋 ID: bzcwijmrcyryy
      📋 事件编码: 202512021945.0001
      📋 震动时间: 2025-12-02 19:45:32
      📋 经度: 78.153
      📋 纬度: 36.509
      📋 地名: 新疆和田地区皮山县
      📋 震级: M4.9
      📋 预估烈度: 6.4
      📋 深度(km): 20km
      📋 更新次数: 1
    📋 校验码: bcf7a40698cc74e0287d9d5ea61b9dfb

🔧 插件版本: 1.1.0
===================================
```

**P2P地震情報详细震度信息**：

```text
===================================
🕐 日志写入时间: 2025-12-04 17:06:44
📡 来源: websocket_p2p_main
📋 类型: websocket_message
🔗 连接: URL: wss://api.p2pquake.net/v2/ws

📊 原始数据:
    📋 数据库ID: 69314fccc58757000701eb4d
    📋 消息代码: 551
    📋 附加评论:
      📋 自由附加文: 空字符串
    📋 地震信息:
      📋 日本境内海啸: None
      📋 海外海啸: Unknown
      📋 震源信息:
        📋 深度(km): 50km
        📋 纬度: 42.8
        📋 经度: 143.2
        📋 震级: M3.6
        📋 地点名称: 十勝地方中部
      📋 最大震度(原始): 20 (震度2)
      📋 发生时间: 2025/12/04 18:04:00
    📋 发布信息:
      📋 订正信息: None
      📋 数据来源: 気象庁
      📋 发生时间: 2025/12/04 18:06:54
      📋 消息类型: DetailScale
    📋 震度观测点 (8项):
      [1]:
        📋 观测点地址: 浦幌町桜町
        📋 区域标志: False
        📋 都道府县: 北海道
        📋 震度值: 20
      [2]:
        📋 观测点地址: 十勝池田町西１条
        📋 区域标志: False
        📋 都道府县: 北海道
        📋 震度值: 10
      ... 还有 3 项
    📋 发生时间: 2025/12/04 18:06:55.246
    📋 timestamp:
      📋 convert: 2025/12/04 18:06:55.241
      📋 register: 2025/12/04 18:06:55.246
    📋 user_agent: jmaxml-seis-parser-go, relay, register-api
    📋 ver: 20231023

🔧 插件版本: 1.1.0
===================================
```

**智能格式化特性**：

- **键名翻译**：自动将英文键名翻译为中文（如"magnitude"→"震级"，"epiIntensity"→"烈度"）。
- **数值格式化**：震级显示为"M4.5"，深度显示为"10km"。
- **列表优化**：数组内容显示项数和前 5 项详情（如"points (8项):"）。
- **嵌套处理**：支持多层 JSON 结构的递归格式化，保持层次清晰。
- **专业术语**：保留原始数据源的专业术语。
- **时间标准化**：统一时间格式显示，便于阅读。

**回退机制**：如果格式化失败，自动回退到标准 JSON 格式，确保日志记录可靠性。

#### 使用场景

1. **开发调试**：分析各数据源的实际消息格式。
2. **问题排查**：查看是否有消息丢失或格式异常。
3. **功能扩展**：基于真实数据格式开发新的解析器。
4. **性能分析**：统计各数据源的消息频率和内容。

#### 智能消息过滤功能

为了减少日志噪音，便于开发与调试，插件提供智能消息过滤功能：

**基础过滤**：

- **心跳包过滤**：自动过滤 `{"type": "heartbeat"}` 类型的消息。
- **可配置过滤类型**：支持自定义过滤 `ping`、`pong`、等消息类型。

**高级过滤**：

- **P2P节点状态过滤**：自动过滤包含 `areas` 数组的P2P网络节点状态消息，这些信息记录peer数量但对分析无意义。
- **重复事件过滤**：基于时间、位置、震级智能识别并过滤重复的地震事件，避免相同事件被多次记录。
- **连接状态过滤**：过滤 WebSocket 连接建立、断开等状态消息，专注于实际数据。

**过滤效果**：

- 日志文件大小增加速率预计减慢 90% 以上。
- 更容易识别有价值的信息。
- 提高日志分析效率。
- 支持查看过滤统计信息。
- **调试友好**：过滤后只记录实际的地震、海啸、气象等灾害数据。

#### 注意事项

- 日志文件存储在 `AstrBot/data/plugin_data/astrbot_plugin_disaster_warning/` 目录下。
- 启用日志记录会略微增加磁盘I/O，但对性能影响很小。
- 建议定期清理旧日志文件以节省磁盘空间。
- 日志文件会自动轮转，避免单个文件过大。

## 🔧 故障排除

### 常见问题

**Q: 插件启动失败怎么办？**
A: 检查以下几点：

- 确认插件已启用。
- 检查网络连接是否正常。
- 查看AstrBot日志获取详细错误信息。
- 确认配置文件格式正确。

**Q: 地图链接缩放级别不生效怎么办？**
A: 已知部分地图服务商的缩放级别参数可能不生效，这是当前版本的技术限制或地图 API 提供商的默认行为导致的。临时解决方案：

- 地图链接仍然可以正常显示震中位置。
- 用户可以在打开的地图页面中手动缩放查看详情。
- 核心震中位置标注功能完全正常。
- 如果你有更好的想法，或者知道如何解决该问题，欢迎提交PR！

**Q: 没有收到预警推送？**
A: 检查以下几点：

- 确认已配置目标QQ群号。
- 检查阈值设置是否过高。
- 确认数据源已启用。
- 使用`/灾害预警测试`命令测试推送功能。

**Q: 推送过于频繁怎么办？**
A: 调整推送频率控制：

- 增加"每收到N报推送一次"的值。
- 启用"是否忽略非最终报"选项。
- 提高震级、烈度阈值。
- 调整启用的数据源。

### 日志查看

插件日志会显示在 AstrBot 的日志中，关键词为`[灾害预警]`。可以通过以下方式查看：

1. 查看 AstrBot 控制台输出
2. 查看 AstrBot 日志文件
3. 使用`/灾害预警状态`命令查看服务状态

> [!CAUTION]
> 由于 AstrBot 的 Bug[#3903](https://github.com/AstrBotDevs/AstrBot/issues/3903)，AstrBot WebUI 控制台输出的日志在本插件的使用场景下**很可能**出现显示问题，丢失部分日志。如果要在控制台中查看完整的插件日志记录，请重新刷新 WebUI 控制台或直接查看 CMD 窗口。

---

## 🚧 最新版本的已知限制

**地图链接缩放级别问题**：

- 已知部分地图服务商的缩放级别参数可能不生效。

**Global Quake 服务状态**：

- Global Quake 服务基本处于不可用状态。
- 虽然插件能提示服务器成功连接，但是从未推送过任何事件，也没有记录到任何数据。
- 原因暂时未知，目前代码中只有一个"空壳实现"。

## 📈 性能优化

### 资源使用

- 插件使用异步 IO，对系统资源影响较小。
- WebSocket 连接会自动重连和心跳保活。
- 旧数据会定期清理，避免内存泄漏。

### 网络优化

- 支持多数据源同时连接。
- 具备断线重连机制。
- 合理的重连间隔避免频繁连接。
- **支持 FAN Studio 主备服务器自动切换**：当主服务器不可用时，自动故障转移到备用服务器。

## 🤝 贡献与支持

欢迎提交 [Issue](https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/issues) 和 [Pull Request](https://github.com/DBJD-CR/astrbot_plugin_disaster_warning/pulls) 来改进这个插件！

### 📞 联系我们

如果你对这个插件有任何疑问、建议或 bug 反馈，欢迎加入我的 QQ 交流群。

- **QQ 群**: 1033089808
- **群二维码**:
  
  <img width="281" alt="QQ Group QR Code" src="https://github.com/user-attachments/assets/53acb3c8-1196-4b9e-b0b3-ad3a62d5c41d" />

### 数据源支持

如需添加新的数据源支持，请提供：

- API 文档或接口说明。
- 数据格式示例。
- 推送频率信息。

## 📄 免责声明

本插件提供的灾害预警信息仅供参考，请勿作为紧急决策的唯一依据。在紧急情况下，请以官方发布的信息为准，并遵循当地应急管理部门的指示。

插件开发者不对因使用本插件造成的任何损失承担责任。

## 📄 许可证

GNU Affero General Public License v3.0 - 详见 [LICENSE](LICENSE) 文件。

本插件采用AGPL v3.0许可证，这意味着：

- 您可以自由使用、修改和分发本插件。
- 如果您在网络服务中使用本插件，必须公开源代码。
- 任何修改都必须使用相同的许可证。

## 🙏 致谢

感谢以下项目提供的 API 服务和文件：

- [FAN Studio](https://api.fanstudio.tech/) - 提供多源灾害数据。
- [P2P地震情報](https://www.p2pquake.net/) - 提供日本地震信息。
- [EPSP](https://github.com/p2pquake/epsp-specifications) - 提供 P2P 区域代码和详细的 API 文档。
- [Wolfx](https://wolfx.jp/) - 提供地震API服务。
- [Global Quake](https://globalquake.net/) - 提供全球地震监测。

## 📚 推荐阅读

我的其他插件：

- [主动消息 (Proactive_chat)](https://github.com/DBJD-CR/astrbot_plugin_proactive_chat) - 它能让你的 Bot 在特定的会话长时间没有新消息后，用一个随机的时间间隔，主动发起一次拥有上下文感知、符合人设且包含动态情绪的对话。

其他优秀的开源 EEW 项目：

- [要石 kanameishi](https://github.com/Lipomoea/kanameishi) - 基于多重 API 制作的地震预警和地震信息可视化 Web 应用.
- [EQuake](https://github.com/SeriesNotFound/EQuake) - 一款基于易语言（底层: C / C++）开发的轻量级中国、日本实时地震观测软件。

## 📊 仓库状态

![Alt](https://repobeats.axiom.co/api/embed/50006d7936120b80175215ef4e1437940e0ad51d.svg "Repobeats analytics image")

## ⭐️ 星星

[![Star History Chart](https://api.star-history.com/svg?repos=DBJD-CR/astrbot_plugin_disaster_warning&type=Date)](https://www.star-history.com/#DBJD-CR/astrbot_plugin_disaster_warning&Date)

---

Made with ❤️ by DBJD-CR & Kimi-For-Coding & Gemini 3.0 Pro
