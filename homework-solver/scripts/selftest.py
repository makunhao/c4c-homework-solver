#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
selftest.py —— 流水线的对抗性自测（零依赖，直接跑）

为什么要有它
------------
《验证报告》里 5 道题全部"自校验通过"——这是好事，但它同时意味着
**"校验失败时会怎样"这条路径从来没被跑过**。
一条没被跑过的分支，等于没有。所以这里**故意注入错误答案**，把它逼出来。

三个用例：
  T1 正路径   —— 正常题集必须 5/5 求解且 5/5 校验通过
  T2 对抗路径 —— **故意让求解器给出错误答案**，校验必须报 False，
                 且渲染出的 LaTeX 必须含红框与"不应采信"
  T3 错误路径 —— 超出覆盖范围的题型必须"未求解"，且备注**不得**出现
                 "由模型求解"（曾经写错，见 AI日志 5.2）

用法：
    python scripts/selftest.py
退出码 0 = 全过；1 = 有失败。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import homework_solver as H                              # noqa: E402

PROBLEMS = json.loads((ROOT / "examples" / "problems.json").read_text(encoding="utf-8"))
FAILS: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  —— {detail}" if detail else ""))
    if not cond:
        FAILS.append(name)


# ══════════════════════════════════════════════════════════════
# T1 正路径
# ══════════════════════════════════════════════════════════════
print("T1 正路径：正常题集")
res = H.solve_all(PROBLEMS, use_llm=False)
solved = sum(1 for r in res if r["solved"].get("ok"))
verified = sum(1 for r in res if r["verify"].get("verified") is True)
check("求解数 = 5", solved == 5, f"实际 {solved}")
check("校验通过数 = 5", verified == 5, f"实际 {verified}")
check("无校验未通过", all(r["verify"].get("verified") is not False for r in res))


# ══════════════════════════════════════════════════════════════
# T2 对抗路径：注入错误答案，校验必须抓到
# ══════════════════════════════════════════════════════════════
print("\nT2 对抗路径：故意让二次方程求解器给出错误答案")

_orig = H.solve_quadratic


def _wrong_solver(p: dict) -> dict:
    """返回一对错的根：P1 的正确答案是 3 和 2，这里故意给 4 和 2。"""
    out = _orig(p)
    if out.get("ok"):
        out["roots"] = [4.0, 2.0]
        out["conclusion"] = r"x_1 = 4,\quad x_2 = 2"
        out["steps"] = [r"（测试注入：这是一组\textbf{故意错误}的根）"]
    return out


H.solve_quadratic = _wrong_solver
H.DETERMINISTIC["quadratic"] = (_wrong_solver, H.verify_quadratic)
try:
    bad = H.solve_all(PROBLEMS, use_llm=False)
    failed = [i for i, r in enumerate(bad) if r["verify"].get("verified") is False]
    check("错误答案被抓到（至少 1 题校验失败）", len(failed) >= 1, f"实际 {len(failed)} 题失败")

    tex = H.render_tex(PROBLEMS, bad)
    # 渲染出来的是 \hwboxout{...}，它展开成 \fcolorbox——断言的应该是**源码里那个宏**
    check("渲染结果含红框（红色 hwboxout）", r"\hwboxout{red!75}{red!6}" in tex)
    check("渲染结果含「自校验未通过」", "自校验未通过" in tex)
    check("渲染结果含「不应采信」", "不应采信" in tex)
    check("渲染结果含具体残差（不是只报失败）", "f(" in tex and "代回复算" in tex)

    # 把注入后的产物落盘，作为证据
    out = ROOT / "out_selftest_fail"
    out.mkdir(exist_ok=True)
    (out / "homework_fail.tex").write_text(tex, encoding="utf-8")
    print(f"    → 证据已落盘：{out / 'homework_fail.tex'}")
finally:
    H.solve_quadratic = _orig
    H.DETERMINISTIC["quadratic"] = (_orig, H.verify_quadratic)


# ══════════════════════════════════════════════════════════════
# T3 错误路径：不支持题型的三态备注
# ══════════════════════════════════════════════════════════════
print("\nT3 错误路径：不支持的题型")
p6 = [p for p in PROBLEMS if p["id"] == "P6"][0]
r6 = H.solve_all([p6], use_llm=False)[0]
check("报告为未求解", r6["solved"].get("ok") is False)
check("校验状态为 None（不适用）", r6["verify"].get("verified") is None)
check("备注**不含**「由模型求解」", "由模型求解" not in r6["verify"].get("note", ""),
      f"实际备注：{r6['verify'].get('note')}")
check("备注含「未求解」", "未求解" in r6["verify"].get("note", ""))

# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 62)
if FAILS:
    print(f"✗ 自测未通过：{len(FAILS)} 项失败")
    for f in FAILS:
        print(f"    - {f}")
    print("=" * 62)
    sys.exit(1)
print("✓ 自测全过（T1 正路径 / T2 对抗路径 / T3 错误路径）")
print("=" * 62)
sys.exit(0)
