# C4C · 教学说明

> 作者：十三　｜　挑战：C4C 作业自动求解与排版
> 目标读者：**想拿它做作业的人**（同学），以及**想换一门课复用它的人**。

---

## 一、30 秒上手

```bash
# 1. 不需要装任何东西（零第三方 Python 依赖，Python ≥ 3.9）
python scripts/homework_solver.py examples/problems.json --out out/

# 2. 看产物
open out/homework.pdf        # Windows: start out/homework.pdf
```

**就两步。** 输入的是一份题目文件，输出的是一份排版好的 PDF。

> 唯一的外部要求：机器上得有一个 `xelatex`。
> 没有的话，产物里的 `homework.tex` 可以直接丢到 Overleaf 编译。

---

## 二、它要的输入长什么样

一份 JSON 数组。**每题至少要三个字段**：`id`、`type`、`question`。

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

> `question` 用 LaTeX 语法写公式（`$...$` 行内、`$$...$$` 行间）。
> `title` 只影响 PDF 里的小标题，可以不写。

### `type` 怎么选

这一列决定走哪条路：

| 你写的 `type` | 还要给什么 | 结果 |
|---|---|---|
| `quadratic` | `a` `b` `c` | 自动解，**且自动复算校验** |
| `linear_system` | `A`（二维数组，系数矩阵）、`b`（一维数组） | 自动解，**且自动复算校验** |
| `stats` | `data`（一维数组） | 自动解，**且自动复算校验** |
| 其它任意字符串 | — | 不加 `--llm` 就如实报"未求解"；加 `--llm` 交给模型 |

---

## 三、输出怎么读

产物三个文件：

```
out/
├── homework.pdf      ← 交给老师的就是它
├── homework.tex      ← 想手工改排版就改这个
└── results.json      ← 想让别的程序读结果就读这个
```

**PDF 里每题长这样：**

```
第 1 题  一元二次方程
题目. 解方程 x² - 5x + 6 = 0。
  求解过程.
  1. 化为标准形式：1x² - 5x + 6 = 0
  2. 计算判别式：Δ = b² - 4ac = (-5)² - 4·(1)·(6) = 1
  3. Δ > 0，有两个不相等实根，代入求根公式
  4. x₁,₂ = ...
  ┌──────────────────────────┐
  │ 答案：x₁ = 3,  x₂ = 2     │   ← 灰框
  └──────────────────────────┘
  自校验：通过——f(3) = 0; f(2) = 0      ← 绿字
```

**如果校验没过**，那一步会变成红框：

```
  ┌────────────────────────────────────────┐
  │ ⚠ 自校验未通过！                        │   ← 红框
  │ 这道题的结果不应采信，需要人工复核。      │
  └────────────────────────────────────────┘
```

> **这是本工具最想让你注意的地方。**
> 它不会把一个算错的答案和算对的答案并排放在一起，让你自己看漏。

---

## 四、"自校验"到底在验什么

不是"把同一个式子再跑一遍"，而是**换一条独立路径**：

| 题型 | 求解用 | 校验用 | 为什么独立 |
|---|---|---|---|
| 二次方程 | 求根公式 | 把根**代回** $ax^2+bx+c$ 求值 | 求根 vs 求值，两条不同的计算 |
| 线性方程组 | 高斯消元 | 把解**代回每一个方程** | 消元 vs 逐行代入 |
| 描述统计 | 均值 = 总和 ÷ n；标准差 = 定义式 | 均值用"排序后首尾配对"；标准差用 $(\Sigma x^2 - n\bar x^2)/(n-1)$ | **不同公式**，不是同一个式子跑两遍 |

**同一个 bug 跑两遍还是同一个 bug。** 那样不叫校验。

---

## 五、换一门课怎么用

**不用改代码。** 只要你的题型落在那三类里：

1. 把题目按上面的 JSON 结构写进一个新文件（比如 `my_homework.json`）
2. 跑 `python scripts/homework_solver.py my_homework.json --out out/`

**题目超出一、二次方程 / 线性方程组 / 描述统计 / 线性代数怎么办？**

两条路：

| 路 | 怎么做 | 代价 |
|---|---|---|
| 自己加求解器 | 在 `scripts/homework_solver.py` 里照 `solve_quadratic` 写一个 `solve_xxx`，再写一个 `verify_xxx`，登记进 `DETERMINISTIC` | 要写代码，但**校验是自动的** |
| 挂模型 | `--llm --base-url ... --model ...` | **没有自动校验**，PDF 里会如实标出来 |

---

## 六、挂一个本地国产模型（可选）

如果你有 Ollama：

```bash
# 拉一个国产模型（推荐 7B 以上）
ollama pull qwen2.5:7b

# 让它处理确定性求解器搞不定的题
python scripts/homework_solver.py examples/problems_llm.json --out out_llm/ --llm \
  --base-url http://127.0.0.1:11434/v1 --model qwen2.5:7b
```

也支持任何 **OpenAI 兼容端点**（vLLM、LM Studio、各家云 API）：

```bash
python scripts/homework_solver.py hw.json --out out/ --llm \
  --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
  --api-key $DASHSCOPE_API_KEY --model qwen-plus
```

> ⚠️ **别用太小的模型。** 实测 `qwen2.5:0.5b` 在应用题上给出错误结论
> （见交付包《验证报告》的对照数据）。**7B 以下请只用确定性求解器。**

---

## 七、常见问题

**Q：报"找不到 xelatex"**
用 `--xelatex /完整/路径/xelatex` 指定。Windows 上便携 MiKTeX 的路径形如
`D:/.../miktex/bin/x64/xelatex.exe`。

**Q：PDF 生成失败了，但 `homework.tex` 在**
说明是编译环境的问题，不是流水线的问题。把 `.tex` 传到 Overleaf 就能出 PDF。

**Q：某道题被标成"未求解"**
说明那个 `type` 没有对应的内置求解器。加 `--llm`，或者照上面的表自己写一个。

**Q：能不能直接从 PDF / Word 读题？**
本工具**不做** OCR 和文档解析——它只吃结构化 JSON。
扫描件/Word 请先用别的工具转成文字，再手工整理成 JSON。
（挑战原文把"文档摄入"列为 Stage 1 的候选能力，本实现在 SKILL.md 里如实标注了这条边界。）

**Q：它会执行我的题目吗？**
不会。**只做静态求解与排版，绝不执行外部代码。**
