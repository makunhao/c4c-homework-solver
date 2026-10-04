#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compare_with_starter.py —— 同题对比：把本项目的题集喂给 starter kit 的求解器

为什么需要它
------------
「与 Claude 基线对比」这一条，最没用的做法是把两个不同测试集上的准确率
（94.4% vs 100%）并排放在一起——那是两道不同的卷子，比了等于没比。

真正有用的做法是：**把同一套题喂给两个求解器**。这个脚本做的就是这件事。

它做三件事：
  1. 读本项目的 examples/problems.json
  2. 转成 starter 的题目格式，import starter 的 scripts/solve.py 调用它
  3. 打印逐题对照（starter 结果 vs 本项目结果）

⚠️ 它**不修改 starter 任何文件**，只 import 它的模块。
⚠️ starter 依赖 sympy：pip install sympy

用法
----
    python scripts/compare_with_starter.py \
        --starter /path/to/c4c-homework-solver-starter \
        --problems examples/problems.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

# 本项目题型 → starter 题型 的映射。
# starter 的 SOLVERS 表里只有这些 key（见其 scripts/solve.py 的 SOLVERS dict）；
# 本项目的 linear_system / stats 在 starter 里**没有对应实现**，
# 分别落在 solve_matrix（空壳）与 solve_calculation（无表达式可算）上。
STARTER_TYPE = {
    "quadratic": "equation",
    "linear_system": "matrix",
    "stats": "calculation",
}


def to_starter_problem(p: dict) -> dict:
    """本项目题目 → starter 题目格式。

    starter 的格式是 {id, text, math_expressions:[{latex}], type, sub_problems}，
    与本项目不同——所以要转。**这一步本身就是"两版接口不通用"的证据。**
    """
    stype = STARTER_TYPE.get(p.get("type", ""), "calculation")
    latex = ""
    t = p.get("type")
    if t == "quadratic":
        a, b, c = p.get("a", 0), p.get("b", 0), p.get("c", 0)
        latex = f"{a}x^{{2}}{b:+d}x{c:+d} = 0"
    elif t == "linear_system":
        latex = " ; ".join(
            " + ".join(f"{coef}x_{j}" for j, coef in enumerate(row))
            + f" = {rhs}"
            for row, rhs in zip(p.get("A", []), p.get("b", [])))
    return {
        "id": p.get("id", "?"),
        "text": p.get("question", ""),
        "math_expressions": ([{"latex": latex}] if latex else []),
        "type": stype,
        "sub_problems": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="同题对比：本项目 vs starter kit")
    ap.add_argument("--starter", required=True, help="starter kit 解压后的根目录")
    ap.add_argument("--problems", default=str(ROOT / "examples" / "problems.json"))
    ap.add_argument("--ours", default=str(ROOT / "out" / "results.json"),
                    help="本项目已产出的 results.json（用来对照）")
    args = ap.parse_args()

    starter_scripts = Path(args.starter) / "scripts"
    if not (starter_scripts / "solve.py").exists():
        print(f"[compare] 找不到 starter 的 solve.py：{starter_scripts}", file=sys.stderr)
        return 2
    sys.path.insert(0, str(starter_scripts))
    try:
        import solve as starter_solve             # noqa: PLC0415
    except ImportError as e:
        print(f"[compare] 无法 import starter 的 solve 模块（缺依赖？pip install sympy）：{e}",
              file=sys.stderr)
        return 2

    problems = json.loads(Path(args.problems).read_text(encoding="utf-8"))
    ours = None
    if Path(args.ours).exists():
        ours_doc = json.loads(Path(args.ours).read_text(encoding="utf-8"))
        ours = dict(zip([p["id"] for p in ours_doc["problems"]], ours_doc["results"]))

    print("=" * 78)
    print(f"同题对比 · {len(problems)} 题")
    print("=" * 78)
    print(f"{'题':<5}{'题型':<16}{'starter（SymPy 版）':<30}{'本项目':<28}")
    print("-" * 78)
    s_ok = o_ok = 0
    for p in problems:
        sp = to_starter_problem(p)
        try:
            r = starter_solve.solve_problem(sp)
            s_solved = bool(r.get("solved"))
            s_ans = str(r.get("answer") or r.get("answer_latex") or "")
            s_show = f"✓ {s_ans[:22]}" if s_solved else f"✗ {str(r.get('reason') or '')[:22]}"
        except Exception as e:                    # noqa: BLE001
            s_solved = False
            s_show = f"✗ EXC {type(e).__name__}"

        if ours and p["id"] in ours:
            r2 = ours[p["id"]]
            o_solved = bool(r2["solved"].get("ok"))
            o_verified = r2["verify"].get("verified") is True
            o_show = ("✓ " + ("已校验" if o_verified else "未校验")) if o_solved else "✗ 未求解"
        else:
            o_solved, o_show = False, "（未跑）"

        s_ok += s_solved
        o_ok += o_solved
        print(f"{p['id']:<5}{p.get('type',''):<16}{s_show:<30}{o_show:<28}")

    print("-" * 78)
    print(f"{'合计':<21}starter {s_ok}/{len(problems)}"
          f"     本项目 {o_ok}/{len(problems)}")
    print("=" * 78)
    print("注：starter 在 linear_system / stats 上**没有实现**（solve_matrix 是空壳），")
    print("    差距反映的是「扩展点被填上」，不是「水平高低」——见《验证报告》3.2。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
