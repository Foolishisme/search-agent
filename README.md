# Minimal Search Agent

一个基于 `FastAPI` 的轻量级 Search Agent Demo。当前版本已经不再是最早的单轮问答原型，而是一套可运行、可继续扩展的最小 Agent 系统。

当前已具备的核心能力包括：

- 会话记忆
- 流式输出
- 搜索增强
- 附件上传
- Canvas Markdown 文档
- Mermaid / SVG 渲染
- 中断与回滚
- WSL Python 执行
- 全局 Rules
- 动态 Skills

## 当前能力

### 执行链路

- 轻规划执行链路
  - `direct_answer`
  - `information_gathering`
  - `python_execution`
- 统一 Tool Schema
  - `search_web`
  - `save_markdown_artifact`
  - `execute_python_wsl`
- 搜索阶段动态重试
  - 最多 3 次搜索尝试
  - 搜索后由模型判断 `answer / retry / stop`

### 会话与交互

- 流式问答接口
  - `POST /api/ask/stream`
  - NDJSON 事件流
- 会话记忆
  - 每个会话持久化为一个 Markdown 文件
  - 历史消息、每轮日志、每轮引用来源一起保存
- 中断与回滚
  - 运行中可取消
  - 未完成轮次不会写入正式会话记忆
  - 附件和 Canvas 副作用一并回滚
- 复制能力
  - 支持复制每轮 Assistant 输出
  - 支持复制历史用户输入

### 内容输入与产物

- 附件上传
  - 支持 `PDF / TXT / MD`
- Canvas 文档
  - 会话级 Markdown 文档
  - 支持生成、编辑、保存、下载
- 全局 Rules
  - 每轮请求默认注入
  - 前端支持查看与修改 `.agent/rules.md`
- Skills
  - 动态上下文，不是工具
  - 前端支持增删改查
  - 每轮由 planner 选择后按需加载

### 富文本与可视化

- Mermaid 渲染
  - 回答区和 Canvas 预览支持 ` ```mermaid ` 代码块
- SVG 渲染
  - 回答区和 Canvas 预览支持 ` ```svg ` 代码块
  - 前端按独立组件渲染，并做基础安全清洗
- Markdown 表格渲染
  - 支持 GFM 表格语法
  - 前端提供表头、边框、横向滚动样式

### Python 执行

- WSL Python 执行
  - 临时脚本写入 `target/temp/`
  - 执行后返回 `stdout / stderr / exit_code`
  - 执行结束删除临时脚本

## 当前架构

当前不再是旧版的 `search / canvas / final` 同级动作循环，而是更轻的分层结构：

```text
用户问题
  -> Planner
  -> route = direct_answer | information_gathering | python_execution
  -> information_gathering 内部按需搜索与重试
  -> python_execution 内部生成 Python 并执行
  -> Final Answer
  -> Canvas Postprocess(optional)
  -> 提交完整轮次
```

更具体一点：

1. 前端提交问题和可选附件
2. Runtime 调用 Planner，决定粗方向
3. 如果需要外部信息，进入 `information_gathering`
4. 如果需要代码执行，进入 `python_execution`
5. 搜索或 Python 工具结果回填为统一 `ToolObservation`
6. 生成最终答案
7. 如果用户明确要求保存 Markdown 文档，再执行 Canvas 后处理
8. 本轮成功后才写入会话记忆

## Prompt 分层

模型当前看到的是三层上下文，而不是单一大 prompt：

1. 全局工具上下文
   - 当前有哪些工具
   - 每个工具的用途和参数
2. 当前计划
   - `direct_answer / information_gathering / python_execution`
   - 是否请求 Canvas
   - 本轮选中了哪些 Skills
3. 当前进展 / 工具结果
   - 已执行过哪些工具
   - 成功还是失败
   - 当前已有的结果和证据

另外，每轮还会默认带入：

- `.agent/rules.md`
- planner 选中的 skill 内容

## Rules 与 Skills

### Rules

全局 Rules 存放在：

```text
.agent/rules.md
```

特点：

- 每轮请求默认注入
- 前端可查看和修改
- 文件不存在时会按空文件处理

### Skills

Skills 存放在：

```text
.agent/skills/index.json
.agent/skills/<skill_id>/SKILL.md
```

特点：

- Skill 是动态上下文，不是工具
- `index.json` 维护列表、顺序和基本描述
- 每个 Skill 有稳定的 `skill_id`
- 每个 Skill 也有递增的 `seq` 便于展示和排序
- planner 会根据当前问题选择需要加载的 Skills

默认会初始化一个最小 Skill：

- `Search Basics`

## 当前工具

### `search_web`

查询公开网页信息，返回标准化搜索结果。

### `save_markdown_artifact`

创建或更新当前会话的 Markdown 文档。

### `execute_python_wsl`

在 WSL 中执行 Python 代码，返回：

- `stdout`
- `stderr`
- `exit_code`

## Python 执行环境

当前 Python 执行跑在 WSL，而不是 Windows 本机 Python。

推荐配置：

- `WSL_DISTRO_NAME=Ubuntu-24.04`
- `WSL_PYTHON_COMMAND=/home/wyf/.venvs/search-agent/bin/python`

当前 WSL 虚拟环境已安装基础包：

- `matplotlib`
- `pandas`
- `seaborn`
- `numpy`

如果修改 `.env` 中的 WSL Python 配置，需要重启服务后才会生效。

## 前端结构

当前前端已经从单文件内联脚本，拆成了静态资源结构：

```text
templates/
  index.html
static/
  css/
    app.css
  js/
    app.js
    api.js
    rendering.js
```

页面结构大致如下：

- 左侧栏
  - 个人偏好
  - Skills
  - 历史对话
- 中间主区
  - 会话工具条
  - 当前会话内容
  - 本轮答案
  - Canvas 文档
  - 输入区
- 补充面板
  - 执行日志
  - 搜索结果

当前前端还支持：

- 历史侧栏展开 / 收起
- Rules / Skills 管理面板
- 每轮复制按钮
- 每轮日志和来源折叠展示

## 技术栈

- Backend: `FastAPI`
- LLM: `DeepSeek`
- Search: `Tavily`
- Python Execution: `WSL + python3`
- Frontend: 原生 `HTML / CSS / JS`
- Markdown: `marked` + `DOMPurify`
- Diagram: `Mermaid`

## 目录结构

```text
app/
  agent_config_store.py
  artifact_store.py
  artifact_tool.py
  attachment_store.py
  llm_client.py
  main.py
  python_executor.py
  run_manager.py
  runtime.py
  schemas.py
  search_tool.py
  session_store.py
  tool_registry.py
templates/
  index.html
static/
  css/
    app.css
  js/
    api.js
    app.js
    rendering.js
tests/
.agent/
  rules.md
  skills/
target/
  artifacts/
  sessions/
  temp/
  uploads/
```

## 安装

```bash
pip install -r requirements.txt
```

## 配置

复制 `.env.example` 到 `.env`：

```bash
copy .env.example .env
```

必填：

- `DEEPSEEK_API_KEY`
- `TAVILY_API_KEY`

常用配置：

- `DEEPSEEK_MODEL=deepseek-chat`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `SEARCH_TOP_K=10`
- `LLM_REQUEST_TIMEOUT=90`
- `SEARCH_REQUEST_TIMEOUT=20`
- `PYTHON_EXECUTION_TIMEOUT=30`
- `WSL_DISTRO_NAME=Ubuntu-24.04`
- `WSL_PYTHON_COMMAND=/home/wyf/.venvs/search-agent/bin/python`
- `LOG_LEVEL=INFO`
- `PROXY_URL=`

## 启动

```bash
uvicorn app.main:app --reload
```

打开：

- `http://127.0.0.1:8000`

## 主要接口

### 问答与运行

- `POST /api/ask`
  - 同步返回完整答案
- `POST /api/ask/stream`
  - 流式返回 NDJSON 事件
- `POST /api/runs/{run_id}/cancel`
  - 取消当前运行

### 会话

- `GET /api/sessions`
  - 会话列表
- `GET /api/sessions/{session_id}`
  - 会话详情
- `DELETE /api/sessions/{session_id}`
  - 删除会话、附件和文档

### Canvas 文档

- `GET /api/sessions/{session_id}/artifacts`
  - 会话文档列表
- `POST /api/sessions/{session_id}/artifacts/save`
  - 创建或更新 Markdown 文档
- `GET /api/sessions/{session_id}/artifacts/{artifact_id}`
  - 读取文档
- `GET /api/sessions/{session_id}/artifacts/{artifact_id}/download`
  - 下载 Markdown 文档

### Rules / Skills

- `GET /api/agent/rules`
- `PUT /api/agent/rules`
- `GET /api/agent/skills`
- `POST /api/agent/skills`
- `GET /api/agent/skills/{skill_id}`
- `PUT /api/agent/skills/{skill_id}`
- `DELETE /api/agent/skills/{skill_id}`

## Mermaid 使用方式

回答区和 Canvas 预览支持 Mermaid 代码块，例如：

````md
```mermaid
flowchart TD
    A["用户问题"] --> B["Planner"]
    B --> C{"route"}
    C -->|"direct_answer"| D["直接回答"]
    C -->|"information_gathering"| E["搜索与重试"]
    C -->|"python_execution"| F["WSL Python 执行"]
    E --> D
    F --> D
```
````

更适合 Mermaid 的场景：

- 流程图
- 时序图
- 架构图

## SVG 使用方式

回答区和 Canvas 预览支持 SVG 代码块，例如：

````md
```svg
<svg width="240" height="120" viewBox="0 0 240 120" xmlns="http://www.w3.org/2000/svg">
  <rect x="10" y="10" width="220" height="100" rx="16" fill="#f6efe3" stroke="#2f6fed"/>
  <text x="120" y="68" text-anchor="middle" font-size="20" fill="#1f2937">Hello SVG</text>
</svg>
```
````

当前实现会：

- 识别 ` ```svg ` 代码块
- 前端单独组件渲染
- 对 SVG 内容做基础安全清洗

## 中断策略

当前采用“整轮原子提交”：

- 运行中可以取消
- 取消后当前轮次不写入正式会话记忆
- 前端恢复到上一轮已完成状态
- 本轮附件和 Canvas 副作用回滚

也就是说：

- 要么这一轮完整提交
- 要么这一轮完全不提交

## 当前边界

- 还没有模型厂商原生 function calling
- 还没有真正的 token 级流式生成
- WSL Python 执行目前只返回文本结果，还没有完整文件产物展示
- Mermaid / SVG 目前只有前端渲染，没有更深入的纠错和调试信息
- 统计图表还没有独立图表引擎

## 下一步升级方向

建议优先看以下方向：

### 1. 标准 Tool Calling

把当前自有 tool schema 逐步过渡到模型厂商原生 tool calling 协议。

### 2. 图表能力

当前只支持 Mermaid 和 SVG，更适合流程图和简单矢量图。下一步可接入：

- `ECharts`
- `Chart.js`

用于：

- 柱状图
- 折线图
- 饼图
- 散点图

### 3. Python 执行增强

后续可以继续补：

- 图片 / CSV / JSON 文件产物回传
- 图表预览
- 更细的错误信息
- 更明确的资源限制

### 4. 搜索评估与收口

继续增强：

- 查询改写
- 结果去重
- 更清楚地表达“公开信息不足”
- 更合理的来源筛选

### 5. UI 信息架构继续收紧

例如：

- 输入区继续压紧
- Canvas 工作区更像独立面板
- Python 执行结果独立展示
- 移动端适配继续优化

### 6. 可观测性与评估

如果 demo 继续往产品走，这部分会越来越重要：

- 每轮 trace
- 工具调用统计
- 成本统计
- 成功率 / 失败率评估
- 回放与调试能力
