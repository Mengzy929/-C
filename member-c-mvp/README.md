# 起研 · 成员 C 独立 MVP

本交付物可离线运行，不需要 API key、数据库、npm 安装或第三方 Python 包。它实现教学决策、输出检查、五层固定样本阅读、原文定位与本地交互演示。当前版本 **0.1.0，接口与规则均为待团队确认的草案**。

## 启动

需要 Python 3.11 或以上。本次实际验证环境为 Windows 11 / Python 3.14.6；其他版本未逐一实测。

Windows：双击 `start-demo.cmd`，保留命令行窗口，在浏览器打开 **http://127.0.0.1:8765**。

也可以在本目录运行：

```powershell
python -m qiyan_c.demo --port 8765
```

端口被占用时改为 `--port 8766`，同时访问对应地址。停止服务按 Ctrl+C。页面只能通过该本地服务访问，不能直接双击 HTML，因为交互会调用 Python 核心。

演示服务只监听 `127.0.0.1`，用于本机测试，不是团队正式后端，不应作为生产服务部署。数据保存在服务进程内，停止服务即清除；页面可导出本次 JSON 记录。

## 验证

双击 `run-checks.cmd`，或在本目录运行：

```powershell
python tools/check.py
```

检查内容包括单元/集成测试、120 组决策表、10000 组随机上限、输出检查样本、能力扫描，以及本机纯决策延迟和教学上下文大小。结果写入 `reports/checks.json`。其中 120 和 10000 是测试方法内部的用例数量，不是 unittest 测试方法数量。

只运行测试：

```powershell
python -m unittest discover -s tests -v
```

只检查资产是否可装载：

```powershell
python -X utf8 -m qiyan_c.demo --check
```

## 已完成

| 模块 | 内容 |
|---|---|
| `qiyan_c/teaching.py` | 规则编译与冻结、T2 提示等级、硬上限、原因、显式版本匹配 |
| `qiyan_c/guard.py` | 直接答案标记、已知答案片段、部分代码/代写模式检查；一次重写后抑制违规正文 |
| `qiyan_c/prompts.py` | 只装配 For the model 段；支持真实 tokenizer 回调与预算拒绝 |
| `qiyan_c/reading.py` | 章节树 DFS 与索引、版本/原文校验、Unicode 与 UTF-16 位置转换、五层阅读状态机 |
| `qiyan_c/events.py` | 不可变事件序列、事件 ID 去重/冲突拒绝、显式放弃与复习意向 |
| `web/` | 阅读、提示、反馈、解释确认、思考变化和导出界面；无构建依赖 |
| `qiyan_c/demo.py` | 独立本地演示驱动；重复请求去重；与纯核心分离 |
| `skills/` | 项目内部能力包的 manifest、规则、提示规格；不是安装到 Codex 的个人技能 |

纯核心不读文件、不写存储、不联网、不调用模型、不读取系统当前时间。初始化文件读取位于 `assets.py`，本地 HTTP、时钟和会话写操作位于 `demo.py`，报告写入位于 `tools/`。

## 规则口径

- `attempts` 表示**当前问题已经完成的未通过作答次数**；0 表示尚未失败。进入下一层后重置。
- 硬上限采用成员 C 文档 §5.3：`3 if attempts >= 2 or giveup else 2`。
- `giveup=True` 只在学生确认查看解释后传入；闲聊始终不启用教学。
- 五个 Intent、base 表、penalty 为本轮起草内容，原资料没有提供完整枚举或配置，尚未经过团队评审。
- `scaffold` 目前只验证并传递，不代表已实现自适应脚手架或 T1 掌握度模型。
- 规则使用 **JSON 兼容的 YAML 1.2 子集**，因此可用标准库读取；不是支持任意 YAML 语法的解析器。
- 版本锁只保证本地已加载规则快照。团队真实 thread 的版本存取由 B/A 接入，本包不写 checkpoint。

## 真实能力边界

1. 样文、实验数字均为合成教学素材；不编造 DOI，不声称引用已核验。
2. 五层问题与关键词判答固定在 fixture 中；不是任意论文的智能问答。否定句、改写、复杂推理可能误判。
3. guard 是启发式检查。构造样本上的表现不能代表真实语义识别能力；`tests` 中专门记录了会放过的改写例子。
4. guard 仅返回 `display/rewrite/suppress`。本包没有真实模型，也不会真的执行模型重写；宿主最多调用一次并再检测。
5. 复习输出为 `scheduled=false` 的意向；没有提醒。负向权重是事件信息，没有真正修改正式掌握度。
6. 没有 A/B/D 的会话、计划审批、真实解析、引用核验、数据库或定时任务。独立演示不证明全系统已联调。
7. prompt 大小默认报告 UTF-8 字节估计，不冒充真实模型 token；接入真实模型时传其 tokenizer 重新验收 900-token 预算。
8. 未进行真实学生实验或独立人工盲评，不声称提高了学习效果。

## 核心调用示例

```python
from qiyan_c.assets import load_rules
from qiyan_c.contracts import Dimension, Intent, Mastery, TeachingRequest
from qiyan_c.teaching import decide
from qiyan_c.guard import detect

rules = load_rules()  # 仅初始化时读取本地文件
request = TeachingRequest(
    intent=Intent.UNDERSTAND,
    dimension=Dimension.READING,
    mastery=Mastery.GUIDED,
    attempts=1,
)
directive = decide(request, rules)  # 纯函数
checked = detect("请找到比较两种流程的原文位置。", directive)
assert checked.allowed
```

项目没有要求先执行 `pip install`；直接在本目录运行。`pyproject.toml` 记录基本项目元数据；正式 Python 构建/发布配置待团队仓库确定后再接。

## 后续接入

详见 `docs/接口交接.md`、`docs/演示与算法说明.md` 与 `docs/验收报告.md`。拿到 GitHub 仓库后，先读取其 AGENTS.md、已有源码和依赖规范，再迁移模块；不直接覆盖他人的 contracts 或前端基座。

原先“8 周 M0”的长期设计已经收敛为两周 C 的独立交付。完整 T1、T3、T4、paper-reader、真实模型语义判答及平台联调仍属于后续工作。
