# Socratic Hire · 画像澄清 Agent

用苏格拉底式追问，帮用人经理把「到底想招什么样的人」从模糊偏好澄清成结构化画像，并生成可交付给 HR 的招聘需求包。

## 功能

- **拷问式澄清对话**：ReAct Agent 像资深 HR 一样连环追问——抽象词具体化（「聪明」逼成可验证行为）、人格化二选一取舍（A/B 候选人暴露真实标准）、前后矛盾当面回指
- **提问大纲**：左中右三栏实时可见「问什么、问到哪、问出了什么」；大纲随回答动态生长（延伸新分支、提前覆盖、废弃失效问题）
- **简历式画像卡**：字段按基本信息/硬性门槛/弹性偏好分区，四态标记（待澄清/参考/待确认/已确认），必填项全部确认后收敛
- **真实岗位库参照（RAG）**：检索同类真实岗位 JD，把「问答题」变成「选择题」；用户可选定一份 JD 作为后续提问蓝本
- **招聘需求包**：收敛确认后一键生成——候选人画像（自然语言人物侧写）+ JD 草稿 + 结构化筛选标准，支持重新生成

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Flask、SQLAlchemy（SQLite）、手写 ReAct Agent 循环 |
| 前端 | React 19、TypeScript、Tailwind CSS 4、Vite（MD3 风格） |
| LLM | DeepSeek（对话/生成，OpenAI 兼容协议）、智谱 ZAI embedding-3（向量化） |
| 向量库 | Qdrant（本地文件模式，零服务依赖） |

## 快速开始

```bash
# 1. 后端依赖（Python 3.11+）
python -m venv .venv
source .venv/Scripts/activate        # Windows Git Bash；其他 shell 自行调整
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env                 # 填入 DEEPSEEK_API_KEY 和 Z_AI_API_KEY

# 3. 准备岗位数据（JSON，格式见下节），放入 data/jobs/ 后入库
python scripts/ingest_jobs.py

# 4. 前端构建
cd frontend && npm install && npm run build && cd ..

# 5. 启动（后端托管前端产物）
python -m backend.app               # http://localhost:8510
```

开发模式：`cd frontend && npm run dev`（5174 端口，代理 /api → 8510）。

> 注意：本地 Qdrant 是单写者文件锁，重新执行入库脚本前请先停掉后端进程。

## 岗位数据格式

`data/jobs/campus_jobs_all.json`（可多文件，按 `id` 合并去重）：

```json
{
  "jobs": [
    {
      "id": "唯一岗位 ID",
      "title": "岗位名称",
      "description": "职位描述",
      "requirement": "职位要求",
      "job_category": "岗位类别",
      "city_info": [{"name": "城市"}],
      "recruit_type": "招聘类型"
    }
  ]
}
```

路径可通过 `JOBS_DATA_DIR` / `JOBS_FULL_JSON` 环境变量覆盖。

## 项目结构

```
backend/
  agent/        ReAct 循环、9 个工具、系统 prompt、SSE 桥接
  core/         LLM 客户端、embedding、Qdrant 封装
  rag/          岗位检索与完整 JD 回补
  state.py      会话/画像卡/大纲持久化（SQLite）
frontend/
  src/features/ 对话、澄清面板（大纲/画像卡/需求包）
scripts/
  ingest_jobs.py  岗位数据一次性入库
```
