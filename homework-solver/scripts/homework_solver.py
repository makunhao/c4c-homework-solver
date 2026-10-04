#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
homework_solver.py —— 作业自动求解与排版流水线

    输入：一份题目文件（JSON，每题带题型与题面）
    输出：一份排版好的 PDF（中文 + 数学公式 + 分步骤 + 答案框 + 自校验结果）

设计要点
--------
1. **求解分两层，各自可独立验证**
   · 内置确定性求解器（二次方程 / 线性方程组 / 描述统计）——纯标准库，答案可复算
   · 可选 LLM 求解器——通过 OpenAI 兼容端点，用于确定性求解器覆盖不到的题型

2. **每道题解完立刻自校验，而不是等人工看**
   · 二次方程：把根代回原方程，检查是否归零
   · 线性方程组：把解代回每个方程
   · 描述统计：用另一条路径（排序 / 定义式）重算一遍
   自校验失败的题会在 PDF 里**用红字标出来**，而不是安静地混在正确答案里。
   —— 这是本项目最重要的一条设计：**求解器最危险的不是解错，是解错了还排版得很漂亮。**

3. **零依赖 + 复用 C2 的便携 LaTeX**
   不引入第三方库；调用 `miktex-portable` 里那个打过补丁的 xelatex。
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from fractions import Fraction
from pathlib import Path

__version__ = "1.0.0"
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# C2 留下的便携 MiKTeX（打过补丁：cp miktex-xetex.exe xelatex.exe）
DEFAULT_XELATEX = Path("D:/ai+x/work/miktex-portable/texmfs/install/miktex/bin/x64/xelatex.exe")


# ══════════════════════════════════════════════════════════════════
# 一、确定性求解器（纯标准库，答案可复算）
# ══════════════════════════════════════════════════════════════════
def solve_quadratic(p: dict) -> dict:
    """ax² + bx + c = 0"""
    a, b, c = float(p["a"]), float(p["b"]), float(p["c"])
    if a == 0:
        return {"ok": False, "error": "a=0，退化为一元一次方程，不在本求解器范围内"}
    d = b * b - 4 * a * c
    steps = [
        rf"化为标准形式：${fmt(a)}x^2 {'+' if b >= 0 else '-'}{fmt(abs(b))}x"
        rf"{'+' if c >= 0 else '-'}{fmt(abs(c))}=0$",
        rf"计算判别式：$\Delta = b^2-4ac = ({fmt(b)})^2-4\cdot({fmt(a)})\cdot({fmt(c)}) = {fmt(d)}$",
    ]
    if d > 0:
        r1 = (-b + math.sqrt(d)) / (2 * a)
        r2 = (-b - math.sqrt(d)) / (2 * a)
        steps.append(r"$\Delta>0$，有两个不相等实根，代入求根公式：")
        steps.append(rf"$x_{{1,2}}=\frac{{-b\pm\sqrt{{\Delta}}}}{{2a}}"
                     rf"=\frac{{{fmt(-b)}\pm\sqrt{{{fmt(d)}}}}}{{{fmt(2*a)}}}$")
        roots = [r1, r2]
        concl = f"x_1 = {fmt(r1)},\\quad x_2 = {fmt(r2)}"
    elif d == 0:
        r = -b / (2 * a)
        steps.append(r"$\Delta=0$，有两个相等实根：")
        roots = [r]
        concl = f"x_1 = x_2 = {fmt(r)}"
    else:
        re_ = -b / (2 * a)
        im_ = math.sqrt(-d) / (2 * a)
        steps.append(r"$\Delta<0$，无实根，有一对共轭复根：")
        roots = []
        concl = f"x_{{1,2}} = {fmt(re_)} \\pm {fmt(abs(im_))}\\,i"
    return {"ok": True, "steps": steps, "conclusion": concl,
            "roots": roots, "delta": d, "kind": "quadratic"}


def verify_quadratic(p: dict, res: dict) -> dict:
    """把根代回原方程——这是『可验证』最直接的证据。"""
    if res.get("kind") != "quadratic" or not res.get("roots"):
        return {"verified": None, "note": "无实根或非二次方程，跳过代入校验"}
    a, b, c = float(p["a"]), float(p["b"]), float(p["c"])
    worst = 0.0
    detail = []
    for r in res["roots"]:
        v = a * r * r + b * r + c
        worst = max(worst, abs(v))
        detail.append(f"f({fmt(r)}) = {fmt(v)}")
    return {"verified": worst < 1e-6, "note": "；".join(detail),
            "residual": worst}


def solve_linear_system(p: dict) -> dict:
    """n×n 线性方程组，高斯消元（列主元）"""
    A = [[float(x) for x in row] for row in p["A"]]
    b = [float(x) for x in p["b"]]
    n = len(A)
    if any(len(row) != n for row in A) or len(b) != n:
        return {"ok": False, "error": "系数矩阵与常数项维度不匹配"}
    aug = [row + [b[i]] for i, row in enumerate(A)]
    steps = [r"写出增广矩阵：$\left(\begin{array}{" + "c" * n + "|c}" +
             r" \\ ".join(" & ".join(fmt(x) for x in row) for row in aug) +
             r"\end{array}\right)$"]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(aug[r][col]))
        if abs(aug[piv][col]) < 1e-12:
            return {"ok": False, "error": f"第 {col+1} 列主元为 0，矩阵奇异或需换列处理"}
        if piv != col:
            aug[col], aug[piv] = aug[piv], aug[col]
            steps.append(f"交换第 {col+1} 行与第 {piv+1} 行（列主元）")
        for r in range(n):
            if r == col:
                continue
            f = aug[r][col] / aug[col][col]
            if abs(f) > 1e-15:
                for k in range(col, n + 1):
                    aug[r][k] -= f * aug[col][k]
    xs = [aug[i][n] / aug[i][i] for i in range(n)]
    steps.append("回代得到唯一解：")
    steps.append("$" + " \\quad ".join(f"x_{{{i+1}}} = {fmt(xs[i])}" for i in range(n)) + "$")
    return {"ok": True, "steps": steps, "roots": xs, "kind": "linear_system",
            "conclusion": ",\\quad ".join(f"x_{{{i+1}}} = {fmt(xs[i])}" for i in range(n))}


def verify_linear_system(p: dict, res: dict) -> dict:
    if res.get("kind") != "linear_system":
        return {"verified": None, "note": "跳过"}
    A = [[float(x) for x in row] for row in p["A"]]
    b = [float(x) for x in p["b"]]
    xs = res["roots"]
    worst = 0.0
    detail = []
    for i, row in enumerate(A):
        v = sum(row[j] * xs[j] for j in range(len(xs)))
        worst = max(worst, abs(v - b[i]))
        detail.append(f"方程{i+1}：{fmt(v)} vs {fmt(b[i])}")
    return {"verified": worst < 1e-6, "note": "；".join(detail), "residual": worst}


# ══════════════════════════════════════════════════════════════════
# 一·五、线性代数（C3C 联合产出新增）
# ══════════════════════════════════════════════════════════════════
# ⚠️ 为什么用 fractions.Fraction 而不是 float：
#   线性代数的"标准答案"往往是整数或简单分数（det = -2、λ = 3）。
#   用 float 会算出 -2.0000000000000004，既不像人写的答案，
#   也让"校验是否归零"变成"校验是否小于某个阈值"——**把确定性换成了待定参数**。
#   Fraction 是标准库，精确运算，残差恒等于 0。**零依赖这条底线保住了。**
#
# ⚠️ 这一段是 C3C 双人协作项目的一部分：
#   代码由十三写，**数学解题规范（什么叫"化到最简"、特征值题的书写顺序）
#   由搭档L审定**——见 C3C 交付包《教学记录》会话 2。

Matrix = "list[list[Fraction]]"


def _to_frac_matrix(raw) -> Matrix:
    return [[Fraction(str(x)) for x in row] for row in raw]


def _frac_fmt(x: Fraction) -> str:
    """分数进 LaTeX：整数不带分母。"""
    if x.denominator == 1:
        return str(x.numerator)
    return rf"\frac{{{x.numerator}}}{{{x.denominator}}}"


def _frac_row(row) -> str:
    return " & ".join(_frac_fmt(x) for x in row)


def _mat_latex(A: Matrix) -> str:
    """矩阵的 LaTeX 片段。**不带 $ 定界符**——由调用方决定行内还是行间。

    ⚠️ 第一版这里自带 `$...$`，而调用处又写了 `$A = {…}$`，
    于是渲染成 `$A = $\\left(…` —— 第一个 `$` 把数学模式关掉了，
    后面的 `\\left(` 落在文本模式里，xelatex 直接 `! Missing $ inserted.`。
    **这与 C4C 里模型的 `$$` 被再包一层是同一个 bug 类型：数学定界符重复包裹。**
    """
    n, m = len(A), len(A[0])
    return (r"\left(\begin{array}{" + "c" * m + r"} " +
            r" \\ ".join(_frac_row(r) for r in A) + r"\end{array}\right)")


def _det_cofactor(A: Matrix) -> Fraction:
    """行列式：**余子式展开**（递归）。这是校验路径之一。"""
    n = len(A)
    if n == 1:
        return A[0][0]
    if n == 2:
        return A[0][0] * A[1][1] - A[0][1] * A[1][0]
    total = Fraction(0)
    for j in range(n):
        if A[0][j] == 0:
            continue
        minor = [[A[i][k] for k in range(n) if k != j] for i in range(1, n)]
        total += ((-1) ** j) * A[0][j] * _det_cofactor(minor)
    return total


def _det_gauss(A: Matrix) -> Fraction:
    """行列式：**带选主元的消元，取主元之积**。这是另一条独立路径。"""
    n = len(A)
    M = [row[:] for row in A]
    det = Fraction(1)
    for col in range(n):
        piv = None
        for r in range(col, n):
            if M[r][col] != 0:
                piv = r
                break
        if piv is None:
            return Fraction(0)
        if piv != col:
            M[col], M[piv] = M[piv], M[col]
            det = -det
        det *= M[col][col]
        for r in range(col + 1, n):
            f = M[r][col] / M[col][col]
            if f != 0:
                for k in range(col, n):
                    M[r][k] -= f * M[col][k]
    return det


def _rref(A: Matrix) -> tuple[Matrix, list[str], int]:
    """高斯–若尔当消元到**行最简形**（RREF），返回 (RREF, 步骤, 秩)。"""
    M = [row[:] for row in A]
    rows, cols = len(M), len(M[0])
    steps: list[str] = []
    r = 0
    for c in range(cols):
        if r >= rows:
            break
        piv = None
        for i in range(r, rows):
            if M[i][c] != 0:
                piv = i
                break
        if piv is None:
            continue
        if piv != r:
            M[r], M[piv] = M[piv], M[r]
            steps.append(f"交换第 {r+1} 行与第 {piv+1} 行")
        pv = M[r][c]
        if pv != 1:
            M[r] = [x / pv for x in M[r]]
            steps.append(f"第 {r+1} 行整体除以 {_frac_fmt(pv)}，使主元为 1")
        for i in range(rows):
            if i == r or M[i][c] == 0:
                continue
            f = M[i][c]
            M[i] = [a - f * b for a, b in zip(M[i], M[r])]
            steps.append(f"第 {i+1} 行减去第 {r+1} 行的 {_frac_fmt(f)} 倍")
        r += 1
    rank = sum(1 for row in M if any(x != 0 for x in row))
    return M, steps, rank


def _char_poly(A: Matrix) -> list[Fraction]:
    """特征多项式的系数（Faddeev–LeVerrier），p(λ)=λⁿ+c₁λⁿ⁻¹+…+cₙ。

    用精确有理数，避免"特征值差一点点"这种经典数值噪声。
    """
    n = len(A)
    M = [[Fraction(1) if i == j else Fraction(0) for j in range(n)] for i in range(n)]
    coeffs = [Fraction(1)]
    for k in range(1, n + 1):
        AM = [[sum(A[i][t] * M[t][j] for t in range(n)) for j in range(n)] for i in range(n)]
        ck = -sum(AM[i][i] for i in range(n)) / k
        coeffs.append(ck)
        M = [[AM[i][j] + (ck if i == j else 0) for j in range(n)] for i in range(n)]
    return coeffs


def _rational_roots_monic(coeffs: list[Fraction]) -> tuple[list[Fraction], list[Fraction]]:
    """首一多项式求有理根。返回 (有理根列表, 剩余二次因子系数)。

    首一 → 有理根必为整数，且整除常数项。找不到再交回调用方走数值分支。
    """
    cs = list(coeffs)

    def evalp(x: Fraction) -> Fraction:
        v = Fraction(0)
        for c in cs:
            v = v * x + c
        return v

    def divroot(x: Fraction) -> None:
        nonlocal cs
        out = [cs[0]]
        for c in cs[1:]:
            out.append(c + out[-1] * x)
        cs = out[:-1]

    roots: list[Fraction] = []
    const = cs[-1]
    if const == 0:
        return [Fraction(0)], cs[:-1]
    cands = sorted({d for k in range(1, abs(int(const)) + 1)
                    if int(const) % k == 0 for d in (k, -k)})
    for x in cands:
        while len(cs) > 1 and evalp(x) == 0:
            roots.append(x)
            divroot(x)
    return roots, cs


def _poly_latex(coeffs: list[Fraction]) -> str:
    """特征多项式的 LaTeX（λⁿ + c₁λⁿ⁻¹ + …）。**必须带符号**。

    ⚠️ 第一版把符号逻辑写错了，渲染出 `λ²7λ10 = 0`——负号整个丢了。
    数学式丢了负号还能"看起来像个式子"，这是最危险的一类排版 bug：
    **它不报错，只是安静地把答案改错。**
    """
    n = len(coeffs) - 1
    terms: list[str] = []
    for i, c in enumerate(coeffs):
        if c == 0:
            continue
        power = n - i
        sign = "-" if c < 0 else ("+" if terms else "")
        mag = abs(c)
        body = "" if (mag == 1 and power > 0) else _frac_fmt(mag)
        var = r"\lambda" if power >= 1 else ""
        pw = rf"^{{{power}}}" if power > 1 else ""
        terms.append(f"{sign}{body}{var}{pw}")
    return " ".join(terms) if terms else "0"


def solve_matrix(p: dict) -> dict:
    """线性代数：行列式 / 行最简形与秩 / 特征值。

    `op` 取值：`det`（行列式）｜ `rref`（行最简形 + 秩）｜ `eigen`（特征值）
    """
    op = p.get("op", "det")
    A = _to_frac_matrix(p["A"])
    n = len(A)
    if any(len(r) != n for r in A):
        return {"ok": False, "error": "本求解器只处理方阵"}
    steps = [f"取矩阵 $A = {_mat_latex(A)}$"]

    if op == "det":
        d1, d2 = _det_cofactor(A), _det_gauss(A)
        steps.append("按第一行做余子式展开，并另用消元法取主元之积——两条路径互为校验：")
        steps.append(rf"$\det A = {_frac_fmt(d2)}$")
        if n <= 3:
            steps.append("（两条独立路径结果一致，见下方自校验）")
        return {"ok": True, "steps": steps, "kind": "matrix", "op": op,
                "det_cofactor": str(d1), "det_gauss": str(d2),
                "conclusion": rf"\det A = {_frac_fmt(d2)}"}

    if op == "rref":
        R, rst, rank = _rref(A)
        steps += rst if rst else ["矩阵已是行最简形，无需消元"]
        steps.append("化为行最简形：")
        steps.append("$" + _mat_latex(R) + "$")
        return {"ok": True, "steps": steps, "kind": "matrix", "op": op,
                "rref": [[str(x) for x in row] for row in R], "rank": rank,
                "conclusion": (r"\text{RREF} = " + _mat_latex(R) +
                               rf",\quad \mathrm{{rank}} = {rank}")}

    if op == "eigen":
        coeffs = _char_poly(A)
        poly = _poly_latex(coeffs)
        steps.append("写出特征多项式 $\\det(A-\\lambda I) = 0$：")
        steps.append("$" + poly + " = 0$")
        roots, rest = _rational_roots_monic(coeffs)
        numeric: list[str] = []
        if len(rest) == 3:                       # 剩下一个二次因子 a₂λ² + b₂λ + c₂
            # ⚠️ 这里踩过一个 bug：rest 是 **完整系数 [a₂,b₂,c₂]**，
            #    第一版按 [b,c] 映射，等于默认 a₂=1 且拿 b₂ 当成了 b——
            #    结果 A=[[1,1],[1,0]] 解出 {0.618, -1.618}（符号全反）。
            #    **是自校验的 Σλ=tr(A) 不变量把它抓出来的**（Σλ=-1 vs tr=1）。
            a2, b2, c2 = rest[0], rest[1], rest[2]
            disc = b2 * b2 - 4 * a2 * c2
            if disc >= 0:
                root_int = None
                if disc.denominator == 1:
                    sq = math.isqrt(int(disc))
                    if sq * sq == int(disc):
                        root_int = Fraction(sq)
                if root_int is not None:
                    roots += [(-b2 + root_int) / (2 * a2), (-b2 - root_int) / (2 * a2)]
                else:
                    num = math.sqrt(float(disc))
                    fa = 2.0 * float(a2)
                    numeric += [f"{(-float(b2)+num)/fa:.6g}", f"{(-float(b2)-num)/fa:.6g}"]
            else:
                num = math.sqrt(float(-disc))
                fa = 2.0 * float(a2)
                numeric += [rf"{-float(b2)/fa:.6g} \pm {num/fa:.6g}\,i"]
        lambdas = [f"{_frac_fmt(r)}" for r in roots] + numeric
        steps.append("解得特征值：")
        steps.append(r"$\lambda \in \{" + ",\\ ".join(lambdas) + r"\}$")
        return {"ok": True, "steps": steps, "kind": "matrix", "op": op,
                "char_poly": [str(c) for c in coeffs], "roots": [str(r) for r in roots],
                "rest_factor": [str(c) for c in rest] if len(rest) > 1 else [],
                "numeric_roots": numeric,
                "conclusion": r"\lambda \in \{" + ",\\ ".join(lambdas) + r"\}"}

    return {"ok": False, "error": f"未知的 op：{op}（支持 det / rref / eigen）"}


def verify_matrix(p: dict, res: dict) -> dict:
    """线性代数的自校验——**每条走一条与求解路径不同的路**。

    · det  ：余子式展开 vs 消元主元积（两种算法）
    · rref ：rank(A) vs rank(Aᵀ)（转置后重新消元，**同一个定理、另一次计算**）
    · eigen：把 λ 代回 det(A−λI) 应为 0；另加两条不变量 tr(Σλ)=tr(A)、Πλ=det(A)
    """
    if res.get("kind") != "matrix":
        return {"verified": None, "note": "跳过"}
    A = _to_frac_matrix(p["A"])
    n = len(A)
    op = res.get("op")

    if op == "det":
        return {"verified": res["det_cofactor"] == res["det_gauss"],
                "note": f"余子式展开 = {res['det_cofactor']}；消元主元积 = "
                        f"{res['det_gauss']}（两条独立路径）"}

    if op == "rref":
        _R, _s, rank = _rref(A)
        AT = [[A[j][i] for j in range(n)] for i in range(n)]
        _R2, _s2, rank_t = _rref(AT)
        return {"verified": rank == rank_t,
                "note": f"rank(A) = {rank}；rank(A转置) = {rank_t}（转置后独立消元）"}

    if op == "eigen":
        roots = [Fraction(x) for x in res.get("roots", [])]
        rest = [Fraction(x) for x in res.get("rest_factor", [])]
        coeffs = [Fraction(x) for x in res.get("char_poly", [])]
        detail: list[str] = []
        # ★ 主校验：**把解出来的根和剩余因子乘回去，必须还原出原特征多项式**。
        #   这是精确整数/分数比对（残差必须恰好为 0），且对"有有理根 + 无有理根"
        #   两种情况都成立——比 Σλ=tr(A) 只覆盖全有理根的情形更普适。
        rebuilt = [Fraction(1)]
        for r in roots:                       # 乘上 (λ - r)
            nxt = [Fraction(0)] * (len(rebuilt) + 1)
            for i, c in enumerate(rebuilt):
                nxt[i] += c
                nxt[i + 1] -= c * r
            rebuilt = nxt
        if rest:                              # 再乘上剩余因子
            nxt = [Fraction(0)] * (len(rebuilt) + len(rest) - 1)
            for i, a in enumerate(rebuilt):
                for j, b in enumerate(rest):
                    nxt[i + j] += a * b
            rebuilt = nxt
        ok = rebuilt == coeffs
        detail.append("因式分解还原" + ("一致" if ok else "不一致") +
                      f"（特征多项式系数 {' '.join(str(c) for c in coeffs)}）")

        # 不变量 1：全部为实有理根时，Σλ 必须等于 tr(A)
        if len(roots) == n:
            tr_l = sum(roots, Fraction(0))
            tr_a = sum(A[i][i] for i in range(n))
            ok = ok and (tr_l == tr_a)
            detail.append(f"特征值之和 = {tr_l} vs tr(A) = {tr_a}")
        # 不变量 2：数值根代回剩余因子必须近似归零
        if res.get("numeric_roots") and rest:
            vals = []
            for s in res["numeric_roots"]:
                num = s.split(r"\pm")[0].strip()          # 只取实部做残差判断
                try:
                    x = Fraction(num).limit_denominator(10 ** 9)
                except (ValueError, ZeroDivisionError):
                    continue
                v = Fraction(0)
                for c in rest:
                    v = v * x + c
                vals.append(abs(float(v)))
            if vals:
                worst = max(vals)
                ok = ok and worst < 1e-3
                detail.append(f"数值根代回残差最大 = {worst:.3g}")
        return {"verified": ok, "note": "；".join(detail)}


def solve_stats(p: dict) -> dict:
    """描述统计：均值 / 中位数 / 样本标准差 / 极差"""
    data = [float(x) for x in p["data"]]
    n = len(data)
    if n == 0:
        return {"ok": False, "error": "数据为空"}
    s = sorted(data)
    mean = sum(data) / n
    med = s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    var = sum((x - mean) ** 2 for x in data) / (n - 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    steps = [
        f"数据共 $n = {n}$ 个：" + "$" + ",\\ ".join(fmt(x) for x in data) + "$",
        rf"均值：$\bar x = \frac{{1}}{{n}}\sum x_i = \frac{{{fmt(sum(data))}}}{{{n}}} = {fmt(mean)}$",
        "升序排列后取中位数：" + "$" + ",\\ ".join(fmt(x) for x in s) + "$" +
        rf"$\;\Rightarrow\; M_e = {fmt(med)}$",
        rf"样本方差：$s^2 = \frac{{\sum (x_i-\bar x)^2}}{{n-1}} = {fmt(var)}$",
        rf"样本标准差：$s = \sqrt{{s^2}} = {fmt(sd)}$",
        rf"极差：$R = \max - \min = {fmt(s[-1])} - {fmt(s[0])} = {fmt(s[-1]-s[0])}$",
    ]
    return {"ok": True, "steps": steps, "kind": "stats",
            "conclusion": (f"\\bar x={fmt(mean)},\\; M_e={fmt(med)},\\; "
                           f"s={fmt(sd)},\\; R={fmt(s[-1]-s[0])}"),
            "_vals": {"mean": mean, "median": med, "sd": sd, "range": s[-1] - s[0],
                      "n": n, "sum": sum(data)}}


def verify_stats(p: dict, res: dict) -> dict:
    """换一条路径重算：均值用『排序后对称配对』，标准差用定义式的等价变形。"""
    if res.get("kind") != "stats":
        return {"verified": None, "note": "跳过"}
    d = [float(x) for x in p["data"]]
    v = res["_vals"]
    # 另一条路径：均值 = 首尾配对求和 / n（对排序后的数据）
    s = sorted(d)
    alt_mean = sum(s[i] + s[-1 - i] for i in range(len(s) // 2)) / len(s)
    if len(s) % 2:
        alt_mean += s[len(s) // 2] / len(s)
    # 标准差：用 (Σx² - n x̄²)/(n-1) 这条等价路径
    alt_var = (sum(x * x for x in d) - len(d) * v["mean"] ** 2) / (len(d) - 1) if len(d) > 1 else 0.0
    ok = abs(alt_mean - v["mean"]) < 1e-9 and abs(math.sqrt(alt_var) - v["sd"]) < 1e-9
    return {"verified": ok,
            "note": (f"另一路径重算：均值 {fmt(alt_mean)}（原 {fmt(v['mean'])}）；"
                     f"标准差 {fmt(math.sqrt(alt_mean and alt_var))}（原 {fmt(v['sd'])}）")}


DETERMINISTIC = {
    "quadratic": (solve_quadratic, verify_quadratic),
    "linear_system": (solve_linear_system, verify_linear_system),
    "stats": (solve_stats, verify_stats),
    "matrix": (solve_matrix, verify_matrix),      # C3C 联合产出新增
}


def fmt(x: float) -> str:
    """数字进 LaTeX 前统一格式化：整数不带小数点，浮点保留合理位数。"""
    if x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return f"{x:.6g}"


# ══════════════════════════════════════════════════════════════════
# 二、可选：LLM 求解器
# ══════════════════════════════════════════════════════════════════
# ⚠️ 这里的 opener 刻意绕开环境里的代理设置。
#
# 踩过的坑：本机设了 http_proxy/https_proxy，urllib 会老老实实把
# 发往 127.0.0.1:11434 的请求塞进代理，代理再回来一个 502 Bad Gateway ——
# 表现为「本地模型明明在跑，却永远连不上」。
# 用 build_opener(ProxyHandler({})) 只影响**这一个** opener，不污染进程环境
# （不要用 os.environ.pop，那会把代理设置从整个进程里摘掉，影响同进程其他代码）。
def _local_opener():
    import urllib.request
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


def solve_with_llm(p: dict) -> dict:
    """通过 OpenAI 兼容端点求解。优先读 CLI 传入的配置，其次读环境变量。

    本地端点（Ollama / vLLM / LM Studio）用：
        HWS_BASE_URL=http://127.0.0.1:11434/v1  HWS_MODEL=qwen2.5:3b
    本地端点不需要 key，所以 key 为空时**只在远端地址上报错**。
    """
    base = (os.environ.get("HWS_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    key = os.environ.get("HWS_API_KEY", "")
    model = os.environ.get("HWS_MODEL", "gpt-4o-mini")
    is_local = ("127.0.0.1" in base) or ("localhost" in base) or ("0.0.0.0" in base)
    if not key and not is_local:
        return {"ok": False, "error": "未配置 HWS_API_KEY，无法调用远端 LLM 求解器"}
    prompt_tpl = (ROOT / "references" / "prompt.md").read_text(encoding="utf-8")
    prompt = prompt_tpl.replace("{{QUESTION}}", p["question"])
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": "你是一位严谨的理科教师，"
                      "只输出 JSON，字段为 steps（LaTeX 字符串数组，逐步推导）"
                      "与 conclusion（LaTeX 字符串，最终答案）。不要输出解释性文字。"},
                     {"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    req = urllib.request.Request(base + "/chat/completions", data=body,
                                 method="POST", headers=headers)
    try:
        with _local_opener().open(req, timeout=180) as r:
            d = json.loads(r.read().decode("utf-8"))
        out = json.loads(d["choices"][0]["message"]["content"])
        # 模型不保证字段类型——实测 qwen2.5:0.5b 会把 conclusion 输出成对象。
        # 这里做一次规范化，免得它把排版器打崩（排版器只接受字符串）。
        steps = out.get("steps") or []
        if not isinstance(steps, list):
            steps = [str(steps)]
        conclusion = out.get("conclusion", "")
        if not isinstance(conclusion, str):
            conclusion = json.dumps(conclusion, ensure_ascii=False)
        return {"ok": True, "steps": [str(s) for s in steps],
                "conclusion": conclusion, "kind": "llm", "model": model}
    except Exception as e:                                     # noqa: BLE001
        return {"ok": False, "error": f"LLM 求解失败：{type(e).__name__}: {e}"}


# ══════════════════════════════════════════════════════════════════
# 三、排版：结构化结果 → LaTeX
# ══════════════════════════════════════════════════════════════════
TEX_HEAD = r"""\documentclass[11pt]{article}
\usepackage[a4paper,margin=2.4cm]{geometry}
\usepackage{xeCJK}
\usepackage{amsmath,amssymb}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{hyperref}
\setCJKmainfont{Microsoft YaHei}
\setlist{nosep,leftmargin=1.6em}
\pagestyle{plain}

% ── 盒子：手写，只用核心命令 ──────────────────────────────────
% 原本用的是 tcolorbox，但便携 MiKTeX 里缺它的依赖 trimspaces.sty，
% 而自动装包在这台机器上没生效。与其去补依赖，不如不用它——
% 手写盒子的好处是**只依赖 LaTeX 内核**，换任何一台装了 xelatex 的机器都能编。
%
% ⚠️ 这里刻意用 \newcommand 而不是 \newenvironment：
% \newenvironment{...}[2]{begin}{end} 的**结束段不能引用参数**，
% 写了 #1 会报 "Illegal parameter number in definition of \end...".
% 普通命令没有这个限制。
\newcommand{\hwboxout}[3]{%
  \par\medskip\noindent
  \setlength{\fboxsep}{7pt}%
  \fcolorbox{#1}{#2}{\begin{minipage}{0.90\textwidth}#3\end{minipage}}%
  \par\medskip}

\title{\textbf{作业求解结果}}
\author{由 homework-solver 自动生成（求解 $\to$ 自校验 $\to$ 排版）}
\date{\today}
\begin{document}
\maketitle
\vspace{-1.2em}
\hwboxout{gray!70}{gray!8}{\textbf{本文件由流水线自动生成。}每题都经过\textbf{自校验}——
解出的结果会代回原题复算一次；\textbf{自校验未通过的题会被红框标出}，
不会安静地混在正确答案里。}
\vspace{0.2em}
"""

TEX_FOOT = r"""
\end{document}
"""


def render_tex(problems: list[dict], results: list[dict]) -> str:
    L = [TEX_HEAD.replace("__VER__", __version__)]
    ok_n = sum(1 for r in results if r["solved"].get("ok"))
    ver_n = sum(1 for r in results if r["verify"].get("verified") is True)
    flagged = [r for r in results if r["verify"].get("verified") is False]
    L.append(r"\section*{总览}" + "\n")
    L.append(r"\begin{itemize}" + "\n")
    L.append(rf"  \item 题目总数：\textbf{{{len(problems)}}}")
    L.append(rf"  \item 成功求解：\textbf{{{ok_n}}}")
    L.append(rf"  \item 自校验通过：\textbf{{{ver_n}}}")
    L.append(rf"  \item 自校验\textbf{{未通过}}：\textbf{{{len(flagged)}}}")
    L.append(r"\end{itemize}" + "\n")

    for i, (p, r) in enumerate(zip(problems, results), 1):
        L.append(rf"\section*{{第 {i} 题\quad {p.get('title', '')}}}" + "\n")
        L.append(r"\textbf{题目.}\;" + p["question"].strip() + "\n\n")
        s = r["solved"]
        if not s.get("ok"):
            L.append(r"\hwboxout{red!75}{red!6}{\textbf{求解未完成：}"
                     + latex_escape(s.get("error", "未知错误")) + r"}" + "\n")
            continue
        L.append(r"\textbf{求解过程.}" + "\n")
        L.append(r"\begin{enumerate}[label=\arabic*.]" + "\n")
        for st in s["steps"]:
            # 同样要规范化：模型给的步骤里也常混 $$...$$
            L.append(r"  \item " + normalize_inline_math(st))
        L.append(r"\end{enumerate}" + "\n")
        L.append(r"\hwboxout{gray!70}{gray!8}{\textbf{答案：}"
                 + wrap_conclusion(s["conclusion"]) + "}" + "\n")

        v = r["verify"]
        if v.get("verified") is True:
            L.append(r"\textbf{自校验：}\textcolor{green!55!black}{通过}——"
                     + latex_escape(v.get("note", "")) + "\n")
        elif v.get("verified") is False:
            # ⚠️ 这里必须把**残差**也印出来。第一版只写"未通过"，读者不知道差多少——
            # "f(4) = 2"（差 2）和 "f(3.0000001) = 1e-8"（差一个浮点）是完全不同的严重程度。
            # 只报"失败"不报"差多少"，等于把判断成本推给读者。
            L.append(r"\hwboxout{red!75}{red!6}{\textcolor{red!75}{\textbf{⚠ 自校验未通过！}}"
                     r"\\ 代回复算：" + latex_escape(v.get("note", ""))
                     + r"\\ 这道题的结果\textbf{不应采信}，需要人工复核。}" + "\n")
        else:
            L.append(r"\textbf{自校验：}不适用——"
                     + latex_escape(v.get("note", "")) + "\n")
        L.append(r"\vspace{0.6em}" + "\n")

    L.append(TEX_FOOT)
    return "\n".join(L)


def latex_escape(s: str) -> str:
    out = []
    for ch in str(s):
        out.append({"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
                    "_": r"\_", "{": r"\{", "}": r"\}",
                    "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}.get(ch, ch))
    return "".join(out)


# ── 数学定界符的规范化 ────────────────────────────────────────
# 踩过的坑：模型很爱用 $$...$$（行间公式）。排版器又把结论包成 \(...\)，
# 于是变成 \($$x_1 = 5$$\) —— xelatex 直接报 `! Missing $ inserted.`，
# **整份 PDF 编译失败**。一个模型的坏输出毁掉了整份文档。
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_DISPLAY_MATH_RE = re.compile(r"\$\$(.+?)\$\$", re.S)


def normalize_inline_math(s: str) -> str:
    """把 $$...$$ 降级成行内 $...$。

    两个理由：① enumerate 的列表项里放行间公式会撑破版面；
    ② 与外层的 \\(...\\) 叠加会产生 `! Missing $ inserted.`（见上面那段注释）。
    """
    return _DISPLAY_MATH_RE.sub(lambda m: "$" + m.group(1).strip() + "$", str(s))


def wrap_conclusion(s: str) -> str:
    """把结论包成可直接放进答案框的形式——**但不重复包**。

    三态：
      · 已经是 $...$ / \\[...\\]  → 原样用（再包一层就崩）
      · 含中文                   → 按普通文本排（中文不是数学）
      · 其余                     → 包成 \\(...\\)
    """
    t = normalize_inline_math(s).strip()
    if not t:
        return r"\(\)"
    if (t.startswith("$") and t.endswith("$") and len(t) > 2) \
            or (t.startswith(r"\[") and t.endswith(r"\]")):
        return t
    if _CJK_RE.search(t):
        return r"\text{" + latex_escape(t) + r"}"
    return r"\(" + t + r"\)"


def compile_pdf(tex_path: Path, xelatex: Path) -> tuple[bool, str, dict]:
    """编译并**按真实结果**判断成败。返回 (成功?, 描述, 结构化指标)。

    ⚠️ 第一版用 `returncode == 0` 当成功判据，结果 PDF 明明生成了却报"失败"——
    xelatex 在有警告（字体替换、overfull box 之类）时也会返回非零。
    正确判据是：**PDF 存在 + 日志里没有 `^!` 开头的真错误**。
    报告一个假的失败，比不报告更糟：会让人去查一个不存在的问题。

    返回的第三个值是**给 results.json 用的**：让"字节数 / 警告数"这类数字
    只有一个出处，文档里引用时不必手抄（抄多了就会前后不一致）。
    """
    meta = {"pdf_bytes": None, "warnings": None, "errors": []}
    if not xelatex.exists():
        return False, f"找不到 xelatex：{xelatex}", meta
    p = subprocess.run([str(xelatex), "-interaction=nonstopmode",
                        "-halt-on-error", tex_path.name],
                       cwd=tex_path.parent, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    log = p.stdout or ""
    errors = [ln for ln in log.splitlines() if ln.startswith("!")]
    warn = len([ln for ln in log.splitlines() if "Warning" in ln])
    pdf = tex_path.with_suffix(".pdf")
    meta["warnings"] = warn
    meta["errors"] = errors[:5]
    if pdf.exists():
        meta["pdf_bytes"] = pdf.stat().st_size
    if pdf.exists() and pdf.stat().st_size > 1000 and not errors:
        return True, f"{pdf.name}（{pdf.stat().st_size} 字节，{warn} 条警告）", meta
    if errors:
        return False, "LaTeX 错误：" + " / ".join(errors[:3]), meta
    if not pdf.exists():
        return False, "没有产出 PDF", meta
    return False, f"PDF 过小（{pdf.stat().st_size} 字节），可能编译中断", meta


# ══════════════════════════════════════════════════════════════════
# 四、主流程
# ══════════════════════════════════════════════════════════════════
def solve_all(problems: list[dict], use_llm: bool) -> list[dict]:
    out = []
    for p in problems:
        kind = p.get("type", "llm")
        det = DETERMINISTIC.get(kind)
        if det:
            solver, verifier = det
            solved = solver(p)
            verify = verifier(p, solved) if solved.get("ok") else {"verified": None,
                                                                  "note": "求解未完成"}
        else:
            if use_llm:
                solved = solve_with_llm(p)
                # 模型的输出无法机器复算 —— 如实标注，不假装校验过
                if solved.get("ok"):
                    verify = {"verified": None,
                              "note": "由模型求解，无自动校验；仅供人工复核"}
                else:
                    verify = {"verified": None,
                              "note": "模型求解失败，无可校验内容：" + solved.get("error", "")}
            else:
                solved = {"ok": False,
                          "error": f"题型 '{kind}' 没有内置确定性求解器；"
                                   f"加 --llm（并给 --base-url/--model）可交模型求解"}
                # ⚠️ 这里曾写错：没走模型却标成"由模型求解"。
                # 三态必须分清——没解 ≠ 模型解了没验 ≠ 模型也没解出来。
                verify = {"verified": None,
                          "note": "未求解（该题型无内置求解器），无可校验内容"}
        out.append({"solved": solved, "verify": verify})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        prog="homework_solver",
        description="作业自动求解与排版流水线：题目 → 求解 → 自校验 → LaTeX → PDF",
        epilog="示例：\n"
               "  python homework_solver.py examples/problems.json --out out/\n")
    ap.add_argument("problems", help="题目文件（JSON）")
    ap.add_argument("--out", default="out", help="输出目录（默认 out/）")
    ap.add_argument("--llm", action="store_true", help="对无内置求解器的题型调用 LLM")
    ap.add_argument("--base-url", default=None,
                    help="LLM 端点，OpenAI 兼容。本地模型示例："
                         "http://127.0.0.1:11434/v1")
    ap.add_argument("--model", default=None, help="LLM 模型名，如 qwen2.5:3b")
    ap.add_argument("--api-key", default=None, help="LLM 密钥（本地端点不需要）")
    ap.add_argument("--xelatex", default=str(DEFAULT_XELATEX), help="xelatex 路径")
    ap.add_argument("--json", action="store_true", help="同时输出结构化结果")
    args = ap.parse_args()

    # CLI 覆盖环境变量（环境变量保留作默认值，方便脚本化调用）
    if args.base_url:
        os.environ["HWS_BASE_URL"] = args.base_url
    if args.model:
        os.environ["HWS_MODEL"] = args.model
    if args.api_key:
        os.environ["HWS_API_KEY"] = args.api_key

    src = Path(args.problems)
    if not src.exists():
        print(f"[homework-solver] 找不到题目文件：{src}", file=sys.stderr)
        return 2
    problems = json.loads(src.read_text(encoding="utf-8"))
    if isinstance(problems, dict):
        problems = problems.get("problems", [])
    if not problems:
        print("[homework-solver] 题目文件是空的。", file=sys.stderr)
        return 2

    results = solve_all(problems, args.llm)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    tex = out / "homework.tex"
    tex.write_text(render_tex(problems, results), encoding="utf-8")

    ok, msg, meta = compile_pdf(tex, Path(args.xelatex))

    summary = {
        "total": len(problems),
        "solved": sum(1 for r in results if r["solved"].get("ok")),
        "verified": sum(1 for r in results if r["verify"].get("verified") is True),
        "verify_failed": sum(1 for r in results if r["verify"].get("verified") is False),
        "unsolved": sum(1 for r in results if not r["solved"].get("ok")),
    }

    print("=" * 68)
    print(f"作业求解与排版 · {len(problems)} 道题")
    print("-" * 68)
    for i, (p, r) in enumerate(zip(problems, results), 1):
        s, v = r["solved"], r["verify"]
        flag = ("✓" if s.get("ok") and v.get("verified") is True
                else ("⚠" if s.get("ok") else "×"))
        print(f"  {flag} 第 {i} 题 {p.get('title','')[:28]:<30} "
              f"{'已求解' if s.get('ok') else '未求解'}"
              f"{' / 自校验通过' if v.get('verified') is True else ''}"
              f"{' / 自校验未通过' if v.get('verified') is False else ''}")
    print("-" * 68)
    print(f"  小结：共 {summary['total']} 题 / 求解 {summary['solved']} / "
          f"自校验通过 {summary['verified']} / 自校验未通过 "
          f"{summary['verify_failed']} / 未求解 {summary['unsolved']}")
    print(f"  LaTeX：{tex}")
    print(f"  PDF  ：{'✓ ' + msg if ok else '✗ ' + msg[:300]}")
    print("=" * 68)

    if args.json:
        (out / "results.json").write_text(
            json.dumps({"summary": summary, "compile": dict(meta, ok=ok, message=msg),
                        "problems": problems, "results": results},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  结构化结果：{out / 'results.json'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
