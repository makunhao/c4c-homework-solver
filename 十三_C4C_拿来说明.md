# C4C · 拿来说明

> 作者：十三　｜　挑战：C4C 作业自动求解与排版
> 依据 C4C 明文要求：**「必须从 starter kit 出发。说明你拿了什么、改了什么、
> Claude 版本与你的国产模型版本有何差异。」**

---

## 一、起点是什么（先把原物看清楚）

我把 `c4c-homework-solver-starter.zip` **解包看了完整结构**（55 个文件），
而不是照着 `CHALLENGE.md` 的文字描述动手。实际结构与文档描述**不一致**——这点后面会讲。

### 1.1 真实的流水线：不是 5 个 stage，是 7 个

`CHALLENGE.md` 写的是五阶段（摄入 → 解析 → 求解 → 排版 → 编译）。
但 `scripts/` 里实际有 **8 个脚本**：

| 脚本 | 规模 | 做什么 |
|---|---|---|
| `bootstrap.py` | 4.2 KB | 环境自检、依赖检查 |
| `ingest.py` | 5.9 KB | 文档 → Markdown |
| **`classify.py`** | 11.6 KB | **题型分类**（文档里没提的一个 stage） |
| `parse_problems.py` | 13.2 KB | Markdown → 结构化题目 |
| **`retrieve.py`** | 5.9 KB | **检索 oracles/ 里的教材/教学参考**（文档里也没提） |
| `solve.py` | **67.3 KB** | 求解主引擎 |
| `render_latex.py` | 10.9 KB | 排版 + 编译 |
| `pipeline.py` | 7.7 KB | 把上面串起来 |

> **实际是 7 段，不是 5 段。** 多出来的两段是 `classify`（分类）与 `retrieve`（检索）。
> 我按实际结构理解，而不是按文档描述理解——这决定了后面"哪些段我做了、哪些没做"。

### 1.2 求解引擎：SymPy 驱动，且**有大片空白**

`solve.py` 67 KB 里有一个 `SOLVERS` 路由表（10 个求解器）：

```python
SOLVERS = {
    "calculation": solve_calculation,   "equation": solve_equation,
    "matrix": solve_matrix,             "ode": solve_ode,
    "proof": solve_proof,               "graph": solve_graph,
    "epsilon_delta": solve_epsilon_delta, "tangent": solve_tangent,
    "limit": solve_limit,               "conceptual": solve_conceptual,
}
```

**但其中三个是空壳**，而且是作者自己标的"学生扩展点"：

```python
def solve_matrix(problem): return _unsolved(problem, "矩阵解析需要扩展（学生扩展点）。")
def solve_ode(problem):    return _unsolved(problem, "ODE 求解需要扩展（学生扩展点）。")
def solve_proof(problem):  return _unsolved(problem, "证明题需要 LLM 求解器（学生扩展点）。")
```

——这正是挑战要我填的坑。**注意 `matrix` 是空的，而 `equation` 用的是 SymPy 的 `solve()`。**

### 1.3 依赖与模板

| 文件 | 内容 | 我的判断 |
|---|---|---|
| `requirements.txt` | `sympy>=1.12`、`pyyaml>=6.0`（PDF/Word/OCR 均为**注释掉的**可选） | 参见 §3.1 |
| `references/homework_template.tex` | 用 `fancyhdr` 页眉页脚 + `\answer{}` 命令（内部 `\fcolorbox{blue}{blue!5}`） | 参见 §2.1、§2.2 |
| `references/sympy_cheatsheet.md` | SymPy 常用函数速查 | 没拿（见 §3.1） |
| `oracles/` | 教材/教学法参考（Stewart 教材、教学指南等 5 份） | 没拿（见 §3.3） |

### 1.4 一个关键事实：**starter 里没有"答案校验"**

我全文检索了 `verif` / `verify` / `check_answer`：

- `solve.py:856` 的注释 "Try to compute the limit to verify" —— 说的是**算极限**，不是验答案
- `solve.py:1285-1289` —— 是一段**静态模板字符串**（"To verify: check units, limiting cases..."），
  出现在"概念题标准答案"里，**不是真的在验**

**starter 的 `_make_solution(steps, answer)` 只负责把答案装进结构体，从不回头验证它。**

→ 这就是本方案核心设计（自校验）的立足点：**它不是我改造来的，是补上了一个原本不存在的环节。**

---

## 二、拿了什么（逐条，附出处）

| # | 拿的东西 | 在原物里的位置 | 我怎么用 |
|---|---|---|---|
| 1 | **按 `type` 路由到求解器**的表驱动结构 | `solve.py:1374` 的 `SOLVERS` dict | 直接沿用这个模式，改成 `DETERMINISTIC`：`{type: (solver, verifier)}`——**值从"一个函数"变成"一对函数"**（求解 + 校验），这是本项目的核心改动 |
| 2 | **答案框的视觉语言** | `homework_template.tex` 的 `\answer{}`：`\fcolorbox{blue}{blue!5}{\displaystyle #1}` | 保留 `\fcolorbox` + 双色参数这个形态，但**重写成可装多行内容的宏**（原版只装一个数学式） |
| 3 | **题目 + 解答交替排版** | `homework_template.tex` 的 `problem`/`solution` 环境 + `render_latex.py:81 render_problem` | 保留"题目—求解过程—答案框"的三段节奏 |
| 4 | **排版与编译分离** | `render_latex.py:239` 的 `compile_pdf()` | 沿用"先出 `.tex` 再编译成 `.pdf`"的两步；**但成功判据改了**（见 §2.4） |
| 5 | **产物落 JSON 供程序读** | `test_cases/*/3_solutions.json` | 沿用；我的 `results.json` 额外带了 `verify` 字段 |
| 6 | **每题独立的 `id` / `type` / `steps` / `answer` 结构** | `solve.py:1503 _make_solution` | 结构照搬；额外加 `verify` |
| 7 | **SKILL.md 的 description 策略** | `SKILL.md`（12.8 KB） | 沿用"把触发短语写进 description"（中英各若干条），见我的 `SKILL.md` |

---

## 三、改了什么（以及为什么改）

### 3.1 【最大的改动】砍掉 SymPy，换成零依赖

| | starter | 我的版本 |
|---|---|---|
| 求解引擎 | SymPy（`sympy>=1.12`）+ `pyyaml` | **纯 Python 标准库** |
| 覆盖题型 | 微积分极限/切线/ε-δ（强） + 矩阵/ODE（空壳） | 二次方程 / 线性方程组 / 描述统计（实装） |
| 第三方依赖 | 2 个（含一个 47 MB 量级的符号库） | **0** |

**为什么砍？** 本流水线的交付形态是"**别人拿到能跑**"。
SymPy 是这个 starter 最大的依赖，也是最大的失败面——版本、wheel、编译环境都可能出问题。

**代价我如实承认：**
- SymPy 能做微积分、ODE、广义特征值，这些我做不到（矩阵特征值后来用 `fractions` 精确实现了 2/3 阶，
  但**没有用 SymPy**——这条底线没破）；
- 我手写的二次方程求根公式、高斯消元、描述统计，**在题型广度上远不如 SymPy**；
- 换句话说，**我是用"题型广度"换了"零依赖 + 可自动校验"**。

这是一次**有意识的取舍，不是能力不足的借口**。如果目标变成"覆盖尽可能多的题型"，
正确的做法是装回 SymPy；如果目标是"任何人拿到就能跑通并且答案可信"，零依赖更优。
C4C 的评审里有「可复用性 10%」和「流水线完整度 20%」两条，我押注在前者。

### 3.2 丢掉 `fancyhdr`，改用 `\pagestyle{plain}`

starter 的模板用 `fancyhdr` 做页眉页脚（课程名 / 姓名 / 作业编号 / 页码）。
我没沿用，**原因是真实的环境约束**：

> 本机用的是**便携版 MiKTeX**（C2 里为中文排版打通的工具链）。
> 它**没有 `fancyhdr`**，而 MiKTeX 的自动装包在这台机器上没生效。

我没有花时间补依赖，而是把页眉页脚降级成 `\pagestyle{plain}`（只保留页码），
课程信息改放在标题区。

> **这与 §3.1 是同一条原则**：宁可版面朴素一点，也不要多一个"别人跑不起来"的点。

### 3.3 砍掉 Stage 1（文档摄入）与 `retrieve`（检索）

`CHALLENGE.md` 把"PDF/Word/OCR 摄入"列为 Stage 1。
**我的版本不做摄入**——输入直接是结构化 JSON。

**为什么？** 摄入链是**独立的一整条技术线**（pdfplumber / python-docx / Tesseract / Vision API），
每一环都要装库、都要处理失败样本。把力气平摊到"摄入 + 求解 + 排版"三段，
每段都只能做到半吊子。

**我的选择是：把 Stage 1 砍掉，把全部力气压在"求解可信"上。**
这条边界在 `SKILL.md` 和《方案设计》的"边界与已知限制"里都写明了，**不隐藏**。

同理，starter 的 `oracles/`（教材参考）与 `retrieve.py` 我**没有拿**——
它们是"给答案找依据"的设计，而我的路线是"让答案自证"。

### 3.4 【核心新增】求解后立刻自校验

starter **没有校验**（§1.4 已证）。我加了一条硬约束：

> **每解一题，立刻用一条独立路径复算一次；校验不过的题在 PDF 里用红框标出。**

关键在"独立"两个字：

| 题型 | 求解路径 | 校验路径 |
|---|---|---|
| 二次方程 | 求根公式 | 把根**代回** $ax^2+bx+c$ 求值 |
| 线性方程组 | **高斯消元**（前向消元 + 回代） | 把解**逐行代回**每个方程 |
| 描述统计 | 均值 = Σx/n；标准差 = 定义式 $\sqrt{\Sigma(x_i-\bar x)^2/(n-1)}$ | 均值用**排序后首尾配对**；标准差用 **$(\Sigma x^2 - n\bar x^2)/(n-1)$ 等价式** |

**为什么必须换路径？** 同一个 bug 跑两遍还是同一个 bug。
如果校验只是"把求解器再调一次"，那它验证的是"程序确定性"，不是"答案正确性"。

### 3.5 【核心新增】口径只写一处

starter 的 `test_cases/` 下每个用例都有独立的 `1_ingested.json` / `2_parsed.json` / `3_solutions.json`，
数据散在多处。我的做法：**所有数字的唯一出处是 `results.json`**，
文档里引用的题目总数、求解数、校验通过数，全部指向它，**不手写**。

> 这条是对同班那份 83 分被扣的直接回应（它的 README 写 30 题、自述写 48 题）。

### 3.6 编译成功判据：从 `returncode == 0` 改成"看产物"

`render_latex.py:239` 的 `compile_pdf()` 返回 `bool`。我一开始照抄思路用 `returncode == 0`，
**结果踩了个真坑**：xelatex 在有警告（字体替换、overfull box）时也会返回非零，
于是 **PDF 明明生成了，流水线却报"失败"**。

我改成看**产物**：

```python
errors = [ln for ln in log.splitlines() if ln.startswith("!")]
if pdf.exists() and pdf.stat().st_size > 1000 and not errors:
    return True, ...
```

**"命令退出码"是过程指标，"PDF 存在且没有 `!` 错误行"是结果指标。**
判据要挂在结果上。

---

## 四、Claude 版本 vs 我的版本：差异在哪

挑战的核心要求是"**迁移引擎**"。摊开讲，两版的差异是这样的：

| 维度 | Claude 基线（starter） | 我的版本 |
|---|---|---|
| **跑在哪** | Claude Code（技能形态） | **纯 Python CLI，不绑定任何宿主** |
| **推理从哪来** | 隐含依赖 Claude 的推理（`solve_conceptual` 是模板；`solve_proof` 直接空缺说"需要 LLM 求解器"） | **确定性求解器为主**；预留 OpenAI 兼容端点可挂**国产模型**（实测走本地 Ollama 的 qwen2.5） |
| **求解是否正确** | **无校验机制** | **每题自校验，结果写进 PDF** |
| **依赖** | sympy + pyyaml | **0** |
| **题型** | 微积分强，矩阵/ODE/证明空壳 | 二次方程/线性方程组/描述统计/**线性代数**实装；其余交模型 |
| **中文** | 模板里 `ctex` 是**注释掉的** | `xeCJK` + 微软雅黑，**默认出中文** |
| **页眉** | `fancyhdr` | `\pagestyle{plain}`（环境约束，见 §3.2） |

### 关于"迁移到国产模型"这条，我要说得更准确一点

挑战的措辞是"把流水线从 Claude 迁移到 Qwen/Kimi"。但**这个 starter 其实并没有真的调 Claude**——
它的 `solve.py` 是纯 SymPy；`solve_conceptual` 用的是**硬编码模板**；
`solve_proof` 干脆标着"需要 LLM 求解器（学生扩展点）"。

> **所以"迁移"这件事，起点并不是"一段调用 Claude 的代码"，
> 而是一个"用符号计算 + 模板凑出来的、留了 LLM 缺口的"系统。**

我做的是**两条腿**：

1. **把确定性那一段做扎实**（零依赖、带自校验）——这是主体；
2. **把 LLM 那个缺口补上，并且真的接上一个国产模型**（本地 Ollama + qwen2.5，
   OpenAI 兼容端点）。实测结果如实写在《验证报告》里——**包括模型答错的部分**。

我**没有**宣称"达到了 94.4% 基线"。那条基线测的是**微积分极限**，
而 C4C 明确要求"非微积分极限"学科。**两者不在同一个测试集上，不可比。**
我做过的最接近的对照，在《验证报告》第二节。

---

## 五、一句话总结

| | |
|---|---|
| **拿了** | 表驱动的求解器路由、答案框的视觉语言、题目/解答交替的排版节奏、排版与编译分离、`_make_solution` 的结果结构、SKILL.md 的 description 策略 |
| **改了** | 砍 SymPy 换零依赖（用题型广度换可移植性）、丢 fancyhdr 换 plain、砍摄入与检索两段、编译判据从退出码改成看产物 |
| **加了** | **求解后自校验**（starter 完全没有）、**口径只写一处**、LLM 缺口的真实落地（接本地国产模型） |
| **没做** | 文档摄入（PDF/Word/OCR）、`oracles/` 检索、微积分/ODE/广义特征值等需要符号或迭代法的题型
  （**矩阵 det/RREF/特征值已于 2026-10-04 实装**——用的不是 SymPy，是标准库 `fractions` 的精确有理数） |
