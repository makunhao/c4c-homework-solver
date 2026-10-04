---
name: homework-solver
description: >
  作业自动求解与排版流水线。输入一份题目文件（JSON），输出一份排版好的 PDF：
  每题自动求解 → 自动复算校验 → 中文 LaTeX 排版 → xelatex 编译。
  内置四类确定性求解器（一元二次方程 / 线性方程组 / 描述统计 / **线性代数：行列式·行最简形·特征值**），
  用标准库 fractions 做精确有理数运算，零第三方 Python 依赖；
  其余题型可挂接任意 OpenAI 兼容端点（含本地 Ollama 上的国产模型）。
  当你需要批量做计算题、把一叠题目变成可提交的 PDF、或者想让「求解」这一步能自动复算时使用。
  触发短语（中文）：自动做题 / 作业求解 / 批量解方程 / 题目转 PDF / 生成作业 PDF /
  自动排版作业 / 解线性方程组 / 描述统计计算 / 作业流水线 / 一键出作业。
  Trigger phrases (English): auto solve homework / solve problems to PDF /
  homework solver / batch solve equations / render homework pdf /
  verify answers automatically.
  也适用于：任何「一组结构化题目 → 一份带步骤的 PDF」的场景。
---

# homework-solver · 作业自动求解与排版

> 一句话：**输入一份题目 JSON，输出一份排版好的 PDF——而且每道题解完会自己复算一遍，错的红框标出。**

---

## 为什么需要它

做作业的痛苦循环里，**真正有创造力的只有"求解"这一步，其余全是搬运和格式工作**：

```
收到作业 → 手抄题目 → 手算 → 手写 LaTeX → 编译 → 发现排版错 → 改 → 再编译 → 提交
```

本工具把这条链压缩成一条命令。

但它真正想解决的不是"省时间"，而是另一个更隐蔽的问题：

> **求解器最危险的不是解错，是解错了还排版得很漂亮。**

一份排版精良的 PDF 会让人**默认它是对的**。所以本工具把"验证"从**事后人工复核**
挪进了**流程里的强制步骤**——每解一题，立刻用**另一条独立路径**复算一次。
校验不过的题，在 PDF 里用红框标出并注明"不应采信"，**不会安静地混在正确答案里。**

---

## 什么时候用 / 不用

| 用 | 不用 |
|---|---|
| 有一组计算题要变成可提交的 PDF | 需要**证明题 / 开放论述**——本工具的确定性求解器不做推理 |
| 想让答案自动被复算校验一遍 | 需要 OCR 扫描件——本工具只吃结构化 JSON |
| 想换一门课直接复用（改题目文件即可） | 需要执行题目附带的代码——**本工具只做静态求解与排版，绝不执行外部代码** |

---

## 快速开始

```bash
# ① 最小用法：跑内置题集
python scripts/homework_solver.py examples/problems.json --out out/

# ② 出结构化结果（供其他程序读）
python scripts/homework_solver.py examples/problems.json --out out/ --json

# ③ 挂本地国产模型处理确定性求解器覆盖不到的题型
python scripts/homework_solver.py examples/problems_llm.json --out out_llm/ --llm \
  --base-url http://127.0.0.1:11434/v1 --model qwen2.5:3b

# ④ 指定 xelatex 路径（默认走 C2 留下的便携 MiKTeX）
python scripts/homework_solver.py examples/problems.json --out out/ --xelatex /path/to/xelatex

# ⑤ 自测（正路径 / 对抗路径 / 错误路径，零依赖）
python scripts/selftest.py
```

**依赖：Python ≥ 3.9（零第三方库）+ 一个可用的 xelatex。**

### 产物

```
out/
├── homework.pdf      ← 可直接提交
├── homework.tex      ← LaTeX 源码（可继续手工改）
└── results.json      ← 结构化结果（含每题求解与校验记录）
```

---

## 输入格式

一份 JSON 数组，每题至少三个字段：`id` / `type` / `question`。

```json
[
  {
    "id": "P1",
    "type": "quadratic",
    "title": "一元二次方程",
    "question": "解方程 $x^{2}-5x+6=0$。",
    "a": 1, "b": -5, "c": 6
  }
]
```

`type` 决定走哪条求解路径：

| `type` | 额外字段 | 解法 | 校验方式 |
|---|---|---|---|
| `quadratic` | `a` `b` `c` | 求根公式 | 把根代回 $ax^2+bx+c$，看是否归零 |
| `linear_system` | `A`（系数矩阵）`b`（常数向量） | 高斯消元 | 把解代回**每一个**方程 |
| `matrix`（`op=det`） | `A`（方阵） | 余子式展开 | **消元取主元之积**（两种算法互验） |
| `matrix`（`op=rref`） | `A`（方阵） | 高斯–若尔当 | **rank(A) vs rank(Aᵀ)**（转置后重新消元） |
| `matrix`（`op=eigen`） | `A`（2/3 阶方阵） | 精确特征多项式 + 有理根 | **因式分解还原比对** + 数值根代回残差 |
| `stats` | `data`（数列） | 均值/中位数/样本标准差/极差 | 用**另一条公式**重算（首尾配对求均值、$\Sigma x^2$ 等价式求标准差） |
| 其他任意值 | — | 报"未求解"；加 `--llm` 则交模型 | **无自动校验**（如实标注） |

> **口径只写一处。** 测试集规模 = 题目文件的实际条目数，不手写、不在别处复述。
> 引用数字时请指向 `results.json`。

---

## 关键设计

1. **求解与校验走两条独立路径。** 校验不是"把同一个式子再跑一遍"，
   而是换一条算法（代回 vs 求值；高斯消元 vs 逐行代入；定义式 vs 等价式）。
   同一个 bug 跑两遍还是同一个 bug——那样不叫校验。

2. **只用 LaTeX 内核，不用外部宏包画框。** 答案框用 `\fcolorbox` + `minipage` 手写
   （见 `scripts/homework_solver.py` 的 `TEX_HEAD` 注释）。
   理由：**交付形态是"别人拿到能跑"，多一个宏包依赖就多一处别人跑不起来的地方。**

3. **LLM 层可选，且明确标注"无自动校验"。** 模型输出无法机器复算，
   所以管线会把它如实标成「由模型求解，无自动校验；仅供人工复核」。**不假装校验过。**

4. **绝不执行外部代码。** 只做静态求解与排版。

---

## 目录结构

```
homework-solver/
├── SKILL.md                    ← 本文件
├── scripts/
│   ├── homework_solver.py      ← 流水线全流程（求解 / 校验 / 排版 / 编译）
│   ├── selftest.py             ← 对抗性自测（故意注入错误答案，逼出红框路径）
│   └── compare_with_starter.py ← 同题对比 starter kit（需要 sympy）
├── references/
│   └── prompt.md               ← LLM 求解的 prompt 模板（--llm 时使用）
└── examples/
    ├── problems.json           ← 内置题集（确定性求解器覆盖的 6 题，含 1 个边界用例）
    └── problems_llm.json       ← 需模型求解的 2 题（用于验证 --llm 通路）
```

---

## 边界与已知限制

| 限制 | 说明 |
|---|---|
| 覆盖题型有限 | 内置求解器做四类。**再往上（微积分、ODE、广义特征值）需要符号/迭代法**——要么引入依赖，要么引入浮点收敛判据，都破坏"精确可验证"这条底线 |
| 不处理 OCR | 输入必须是结构化 JSON；扫描件需先用别的工具转成文本 |
| `--llm` 通路无自动校验 | 如实标注，不假装 |
| **本地小模型不可靠** | 实测 **qwen2.5:0.5b 两题全错**、**qwen2.5:3b 只对一半**。**生产使用请换 7B 以上，或只用确定性求解器** |
| **LLM 输出不可复现** | 同一模型在 `temperature=0` 下两次运行结果仍可能不同（Ollama 未固定 seed）——这也是它必须被标成"无自动校验"的原因 |
| 需自备 xelatex | 本工具不附带编译器；Overleaf、系统 TeX、便携 MiKTeX 均可 |
