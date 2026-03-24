# 最小搜索 Agent MVP

这是一个基于 `FastAPI` 的最小搜索 Agent，实现以下闭环：

1. 用户在网页输入问题
2. DeepSeek 判断是否需要搜索
3. 如果需要，调用 Tavily 搜索
4. DeepSeek 基于搜索结果生成最终答案
5. 页面展示答案、搜索结果和最小执行日志

## 1. 安装依赖

```bash
pip install -r requirements.txt
```

## 2. 配置本地环境变量

复制 `.env.example` 为 `.env`，并填写真实密钥：

```bash
copy .env.example .env
```

必填项：

- `DEEPSEEK_API_KEY`
- `TAVILY_API_KEY`

默认模型：

- `DEEPSEEK_MODEL=deepseek-chat`
- `DEEPSEEK_BASE_URL=https://api.deepseek.com`

## 3. 启动服务

```bash
uvicorn app.main:app --reload
```

启动后访问：

- `http://127.0.0.1:8000`

## 4. MVP 特性

- 单轮问答
- 单个 LLM：DeepSeek
- 单个搜索工具：Tavily
- 判断是否搜索
- 搜索结果回填总结
- 最小运行日志
- 基础异常处理

## 5. 已知边界

- 不支持多轮记忆
- 不支持流式输出
- 不保证所有问题都能稳定触发最优搜索词
- 依赖外部 API 可用性与 Key 配置正确
