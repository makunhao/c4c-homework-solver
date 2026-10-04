# C4C · 作业自动求解与排版 —— 交付包索引

> 作者：十三　｜　挑战：C4C 作业自动求解与排版（`ch-20260717031447-k82c4m`）
> **一句话**：输入一份题目文件，输出一份排版好的 PDF——而且每道题解完会**自己复算一遍**，错的红框标出。

---

## 一、交付物对照表（按挑战要求逐条对）

| 挑战要求的文件 | 本包对应文件 | 说明 |
|---|---|---|
| `姓名_C4C_方案设计.md` | **`十三_C4C_方案设计.md`** | 架构、设计决策、实测数据、排版证据 |
| `姓名_C4C_homework-solver.skill` 或源码 | **`十三_C4C_homework-solver.skill`** + **`homework-solver/`** | 两者内容相同；`.skill` 是 zip 包，`homework-solver/` 是解开的源码 |
| `姓名_C4C_作业原件.*` | **`十三_C4C_作业原件.md`** | 人可读版；机器可读版在 `homework-solver/examples/problems.json` |
| `姓名_C4C_output.pdf` | **`十三_C4C_output.pdf`** | 与 `十三_C4C_output/homework.pdf` **同一个文件**（按命名规范在根目录放一份副本） |
| `姓名_C4C_验证报告.md` | **`十三_C4C_验证报告.md`** | 逐题对照 + 同题对比 starter + LLM 实测 + 诚实失败清单 |
| `姓名_C4C_教学说明.md` | **`十三_C4C_教学说明.md`** | 怎么装、怎么用、支持哪些课、换课怎么改 |
| `姓名_C4C_AI日志.md`（必须） | **`十三_C4C_AI日志.md`** | Round 0–6，含 **11 个真 bug** |
| `姓名_C4C_拿来说明.md` | **`十三_C4C_拿来说明.md`** | 从 starter 拿了什么、改了什么、两版差异 |

---

## 二、30 秒看懂它是什么

```bash
python scripts/homework_solver.py examples/problems.json --out out/ --json

# 输出：
#   小结：共 6 题 / 求解 5 / 自校验通过 5 / 自校验未通过 0 / 未求解 1
#   PDF  ：✓ homework.pdf（123532 字节，5 条警告）
```

**核心设计只有一句话**：

> **求解器最危险的不是解错，是解错了还排版得很漂亮。**
> 所以每解一题，立刻用**另一条独立路径**复算一次；
> 校验不过的题在 PDF 里用红框标出，**并印出残差**。

**"独立路径"的含义**：不是把同一个式子跑两遍——
二次方程用"求根公式 vs 代回求值"，线性方程组用"高斯消元 vs 逐行代入"，
描述统计用"定义式 vs 等价式"。

---

## 三、关键数字（唯一出处：`十三_C4C_output/results.json`）

| 项 | 值 |
|---|---|
| 题目总数 | **6** |
| 内置求解器覆盖 | **5**（二次方程 ×2 / 线性方程组 ×2 / 描述统计 ×1） |
| 成功求解 | **5 / 5** |
| **自校验通过** | **5 / 5** |
| 走错误路径 | **1**（超范围题型，如实报"未求解"） |
| PDF | **123,532 字节**，0 错误 / 5 警告 |
| 第三方 Python 依赖 | **0** |
| **同题对比 starter kit** | starter **2/6** ／ 本项目 **5/6** |
| LLM 通路（qwen2.5） | 0.5b **0/2**；3b **1/2**（照实记录） |
| 对抗性自测 | **全过**（T1 正路径 / T2 对抗路径 / T3 错误路径） |

---

## 四、目录结构

```
C4C交付包/
├── README.md                        ← 本文件
├── 十三_C4C_方案设计.md
├── 十三_C4C_验证报告.md
├── 十三_C4C_教学说明.md
├── 十三_C4C_拿来说明.md
├── 十三_C4C_AI日志.md
├── 十三_C4C_作业原件.md
├── 十三_C4C_output.pdf              ← 提交用的 PDF（与下面同名文件一致）
├── 十三_C4C_homework-solver.skill    ← 可运行技能包（zip）
├── homework-solver/                 ← 同一技能包的解开源码
│   ├── SKILL.md
│   ├── scripts/homework_solver.py   ← 主流水线
│   ├── scripts/selftest.py          ← 对抗性自测
│   ├── scripts/compare_with_starter.py ← 同题对比
│   ├── references/prompt.md
│   └── examples/{problems.json, problems_llm.json}
└── 十三_C4C_output/
    ├── homework.pdf                 ← 排版产物（提交版）
    ├── homework.tex                 ← LaTeX 源码
    ├── results.json                 ← **所有数字的唯一出处**
    └── 排版截图/                     ← 7 个证据文件（6 张 PNG + 1 份 PDF）
```

---

## 五、复现

```bash
cd homework-solver

# 主流程（零第三方依赖）
rm -rf out && python scripts/homework_solver.py examples/problems.json --out out --json

# 对抗性自测
python scripts/selftest.py

# 同题对比 starter（需要 sympy：pip install sympy）
python scripts/compare_with_starter.py --starter /path/to/c4c-homework-solver-starter

# LLM 通路（需要本机 Ollama）
python scripts/homework_solver.py examples/problems_llm.json --out out_llm --json --llm \
  --base-url http://127.0.0.1:11434/v1 --model qwen2.5:3b
```

> ⚠️ 主流程**请用空输出目录**——否则编译警告数会不同（原因见《方案设计》第四节）。

---

## 六、这个包里**没有**什么（如实列出）

| 未做 | 说明 |
|---|---|
| 微积分 / ODE / 广义特征值 / SVD | 需要符号计算库或迭代法，会打破"零依赖"与"精确可验证"
  （**矩阵特征值已于 2026-10-04 支持**，见 `examples/problems_linalg.json`） |
| 文档摄入（PDF / Word / OCR） | 输入只接受结构化 JSON |
| 图形生成 | starter 有 `solve_graph`，未沿用 |
| 微积分极限 94.4% 基线的复现 | 与 C4C"非微积分极限"的要求冲突 |
| 真实课程作业原件的测试 | 用的是自建题集，理由见《验证报告》第一节 |

**把这份清单放在索引里，是因为它和前五节的证据同等重要。**
一份只列达标项、不列失败项的交付包，本身就是不可验证的。
