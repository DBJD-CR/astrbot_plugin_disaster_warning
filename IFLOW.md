# AstrBot 灾害预警插件 - IFLOW.md

## 项目概述

AstrBot 灾害预警插件是一个功能强大的多数据源灾害预警系统，专为 AstrBot 设计。该插件能够实时推送地震、海啸、气象预警信息，支持来自全球多个权威机构的数据源，包括中国地震台网、日本气象厅、USGS、Global Quake 等。

项目采用 Python 编写，基于异步架构设计，具有高度模块化、松耦合的工业级架构，专注于在高并发灾害数据流下的实时性、鲁棒性与准确性。

## 核心功能

1. **多数据源支持**：支持多达 16 个可自由选择启用的细粒度数据源
2. **智能推送控制**：基于震级、烈度、震度设置推送阈值，支持频率控制
3. **事件去重功能**：防止同一地震事件被重复推送
4. **本地预估烈度**：基于用户位置计算本地烈度影响
5. **图片渲染功能**：基于 Playwright 的高性能图片渲染引擎
6. **灵活配置**：通过 WebUI 界面进行配置

## 架构组件

### 主要模块
- `main.py`：插件主入口，负责初始化和命令处理
- `core/disaster_service.py`：核心灾害预警服务，整合所有组件
- `core/handlers/`：数据处理器目录，处理不同数据源
- `core/filters/`：过滤器目录，实现各种过滤逻辑
- `models/models.py`：数据模型定义
- `utils/formatters/`：消息格式化器
- `resources/card_templates/`：渲染卡片模板

### 核心服务组件
- **WebSocketManager**：WebSocket连接管理器
- **HandlerRegistry**：处理器注册表
- **EventDeduplicator**：事件去重器
- **IntensityCalculator**：本地烈度计算器
- **MessagePushManager**：消息推送管理器
- **MessageLogger**：原始消息记录器
- **StatisticsManager**：统计数据管理器

## 数据模型

### 主要枚举
- `DisasterType`：灾害类型（地震、海啸、气象预警等）
- `DataSource`：数据源类型（FAN Studio、P2P、Wolfx、Global Quake等）

### 核心数据类
- `EarthquakeData`：地震数据模型
- `TsunamiData`：海啸数据模型
- `WeatherAlarmData`：气象预警数据模型
- `DisasterEvent`：统一灾害事件格式

## 构建和运行

### 依赖安装
```bash
pip install -r requirements.txt
```

主要依赖包括：
- aiohttp>=3.8.0
- pydantic>=2.0.0
- python-dateutil>=2.8.0
- asyncio-mqtt>=0.13.0
- jinja2>=3.0.0
- playwright>=1.30.0

### 插件运行
插件作为 AstrBot 的扩展模块运行，通过 AstrBot 的插件系统加载。

## 开发约定

### 代码风格
- 使用 Python 3.10+ 语法
- 遵循 PEP 8 代码规范
- 使用类型注解增强代码可读性
- 采用异步编程模式

### 配置管理
- 通过 WebUI 配置界面进行配置
- 使用 `_conf_schema.json` 定义配置架构
- 支持细粒度的数据源配置

### 日志记录
- 使用 AstrBot 的 logger 系统
- 支持原始消息日志记录
- 详细的错误和调试信息记录

## 系统架构特点

1. **并发与异步任务调度**：完全基于 asyncio 异步框架构建
2. **数据规范化模型**：统一抽象层，将异构数据转换为标准模型
3. **智能去重矩阵**：复杂模糊匹配指纹算法
4. **浏览器级渲染管线**：Playwright 驱动的卡片渲染
5. **自愈型连接管理器**：支持主备服务器切换和指数退避重连

## 命令系统

插件提供丰富的命令支持：
- `/灾害预警` - 显示帮助信息
- `/灾害预警状态` - 查看服务运行状态
- `/灾害预警统计` - 查看事件统计报告
- `/灾害预警测试` - 测试推送功能
- `/灾害预警模拟` - 模拟地震事件测试
- 以及其他管理命令

## 数据源配置

插件支持多种数据源配置，包括：
- FAN Studio 综合源
- P2P地震情報 WebSocket
- Wolfx API
- Global Quake 实时测算

## 过滤器系统

包含多种过滤器：
- 烈度过滤器（Intensity Filter）
- 震度过滤器（Scale Filter）
- 本地预估烈度过滤器
- 气象预警过滤器
- 报数控制过滤器

## 可用性与稳定性

插件具备以下可靠性特性：
- 自愈型连接管理
- 重连机制（包括兜底重连）
- 心跳监测
- 状态恢复
- 统计数据持久化