# 🤝 贡献指南 (Contributing Guide)

感谢您有兴趣为 **AstrBot 灾害预警插件** 做出贡献！无论是修复 Bug、添加新功能，还是改进文档，您的每一次贡献都能让这个项目变得更好。

请在参与贡献之前，仔细阅读以下指南。

## 🐛 提交 Issue

### 报告 Bug

如果您在使用插件时遇到问题，请在提交 Issue 之前：

1. **搜索现有 Issue**：检查是否已经有人报告过类似的问题。
2. **更新到最新版本**：确保您使用的是插件的最新版本，问题可能已经在新版本中修复。

提交 Bug 报告时，请包含以下信息：

- **AstrBot 版本**：您正在使用的 AstrBot 版本号。
- **插件版本**：您正在使用的灾害预警插件版本号。
- **复现步骤**：详细描述如何触发该 Bug 的步骤。
- **预期行为**：您期望发生什么。
- **实际行为**：实际发生了什么。
- **日志截图/文本**：提供相关的错误日志或控制台输出（请注意隐藏敏感信息）。

### 功能建议

如果您有新的想法或建议，欢迎提交 Feature Request。请描述：

- **背景**：为什么需要这个功能？解决了什么痛点？
- **建议方案**：您设想的功能是如何工作的？
- **备选方案**：是否有其他替代方案？

## 💻 代码贡献

### 开发环境准备

1. Fork 本仓库到您的 GitHub 账号。
2. 克隆您的 Fork 仓库到本地：

    ```bash
    git clone https://github.com/your-username/astrbot_plugin_disaster_warning.git
    ```

3. 确保您已安装 Python 3.10+。
4. 安装项目依赖（通常 AstrBot 环境已包含大部分依赖，如有额外依赖请查看 `requirements.txt`）。

### 代码风格

为了保持代码的一致性和可读性，请遵循以下规范：

- **格式化**：使用 `ruff` 进行代码格式化和检查。
- **类型注解**：尽可能为函数和类添加 Python 类型提示 (Type Hints)。
- **文档字符串**：为模块、类和函数编写清晰的 Docstring。

### 提交 Pull Request (PR)

1. **创建分支**：从 `main` 分支创建一个新的功能分支。

    ```bash
    git checkout -b feat/your-feature-name
    # 或者
    git checkout -b fix/your-bug-fix
    ```

2. **提交更改**：编写代码并提交。请使用清晰、描述性的提交信息（推荐遵循 [Conventional Commits](https://www.conventionalcommits.org/) 规范）。
    - `feat`: 新功能
    - `fix`: 修复 Bug
    - `docs`: 文档变更
    - `style`: 代码格式调整（不影响逻辑）
    - `refactor`: 代码重构
    - `perf`: 性能优化
    - `chore`: 杂务

3. **推送到远程**：

    ```bash
    git push origin feat/your-feature-name
    ```

4. **发起 PR**：在 GitHub 上发起 Pull Request，详细描述您的更改内容和目的。
5. **代码审查**：等待维护者审查您的代码。如果有修改建议，请及时响应并更新代码。

## 📝 文档贡献

文档与代码同样重要。如果您发现 `README.md` 或其他文档中有错别字、表述不清或过时的内容，欢迎直接提交 PR 进行修正。

---

再次感谢您的贡献！🚀
