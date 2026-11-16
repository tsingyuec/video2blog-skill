#!/usr/bin/env python3
"""把强化学习博客里「代码样式公式」批量转成 KaTeX 行内公式。

只处理被 check_md_math.mjs 判定为「疑似未转换」的反引号片段：
含 _ ^ { } \\ 或数学关键字，且不是纯标识符。

用法：
  python3 scripts/check/convert_math_inline.py --dry-run <md...>
  python3 scripts/check/convert_math_inline.py --apply  <md...>
"""
import re
import sys
import pathlib

MATH_HINT = re.compile(
    r"[_^{}\\]|\b(argmax|argmin|sum|prod|frac|sqrt|mathbb|mathcal|epsilon|gamma|alpha|lambda|theta|pi|sigma|mu|max|min|log|exp)\b"
)

GREEK = {
    "π": r" \pi ", "γ": r" \gamma ", "ε": r" \varepsilon ", "α": r" \alpha ",
    "δ": r" \delta ", "μ": r" \mu ", "θ": r" \theta ", "λ": r" \lambda ",
    "σ": r" \sigma ", "ρ": r" \rho ", "τ": r" \tau ", "ω": r" \omega ",
    "β": r" \beta ", "η": r" \eta ", "κ": r" \kappa ", "ν": r" \nu ",
    "Π": r" \Pi ", "Ω": r" \Omega ", "Δ": r" \Delta ", "Φ": r" \Phi ",
    "Σ": r" \sum ",
}

SYMBOLS = {
    "·": r" \cdot ", "×": r" \times ", "÷": r" \div ", "−": "-", "–": "-",
    "≤": r" \le ", "≥": r" \ge ", "≠": r" \ne ", "≈": r" \approx ",
    "←": r" \leftarrow ", "→": r" \to ", "⇌": r" \rightleftharpoons ",
    "…": r" \dots ", "′": "'", "∣": r" \mid ", "∞": r" \infty ",
    "∈": r" \in ", "∀": r" \forall ", "∃": r" \exists ", "∑": r" \sum ",
    "∏": r" \prod ", "√": r" \sqrt", "±": r" \pm ", "∼": r" \sim ",
}

SUBS = dict(zip("₀₁₂₃₄₅₆₇₈₉", "0123456789"))
SUPS = dict(zip("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
SUPS.update({"ⁿ": "n", "ⁱ": "i", "ᵏ": "k", "ᵗ": "t", "²": "2", "³": "3", "¹": "1"})

FUNCS = [
    (r"(?<![A-Za-z\\])argmax(?![A-Za-z])", r"\\arg\\max "),
    (r"(?<![A-Za-z\\])argmin(?![A-Za-z])", r"\\arg\\min "),
    (r"(?<![A-Za-z\\])softmax(?![A-Za-z])", r"\\operatorname{softmax} "),
    (r"(?<![A-Za-z\\])max(?![A-Za-z])", r"\\max "),
    (r"(?<![A-Za-z\\])min(?![A-Za-z])", r"\\min "),
    (r"(?<![A-Za-z\\])log(?![A-Za-z])", r"\\log "),
    (r"(?<![A-Za-z\\])ln(?![A-Za-z])", r"\\ln "),
    (r"(?<![A-Za-z\\])exp(?![A-Za-z])", r"\\exp "),
    (r"(?<![A-Za-z\\])sum(?![A-Za-z])", r"\\sum "),
]


def fix_unicode_scripts(s: str) -> str:
    # 组合符号：μ̂ -> \hat{\mu}，μ̄ -> \bar{\mu}
    s = re.sub(r"(.)\u0302", lambda m: r"\hat{%s}" % m.group(1), s)
    s = re.sub(r"(.)\u0304", lambda m: r"\bar{%s}" % m.group(1), s)

    def repl(m):
        base, run = m.group(1), m.group(2)
        ch = run[0]
        if ch in SUBS:
            return f"{base}_{SUBS[ch]}"
        return f"{base}^{SUPS.get(ch, ch)}"

    # 连续 Unicode 上下标 -> LaTeX
    s = re.sub(r"(?<![_^{])([A-Za-z\u0370-\u03ff\)\]])([₀-₉⁰-⁹ⁿⁱᵏᵗ²³¹]+)", repl, s)
    return s


def sqrt_convert(s: str) -> str:
    """sqrt(...) -> \\sqrt{...}，支持一层括号配对。"""
    out = []
    i = 0
    while i < len(s):
        m = re.match(r"sqrt\(", s[i:])
        if not m:
            out.append(s[i])
            i += 1
            continue
        j = i + 5
        depth = 1
        k = j
        while k < len(s) and depth:
            if s[k] == "(":
                depth += 1
            elif s[k] == ")":
                depth -= 1
            k += 1
        if depth:
            out.append(s[i])
            i += 1
            continue
        inner = s[j:k - 1]
        out.append(r"\sqrt{" + inner + "}")
        i = k
    return "".join(out)


def bars(s: str) -> str:
    """| 作条件竖线用 \\mid；整段被 | 包住时用 \\lvert \\rvert。"""
    if s.startswith("|") and s.count("|") == 2:
        first = s.index("|")
        last = s.rindex("|")
        return r"\lvert " + s[first + 1:last] + r" \rvert" + s[last + 1:]
    s = s.replace(r"\|", r" \mid ")
    return s.replace("|", r" \mid ")


def convert(inner: str) -> str:
    s = inner
    s = fix_unicode_scripts(s)

    # 已知整体替换（避免通用规则误伤）
    exact = {
        "state_return / state_count": r"\frac{\text{state\_return}}{\text{state\_count}}",
        "TD target": r"\text{TD target}",
        "Regret": r"\text{Regret}",
        "Agent ⇌ Environment : {S, A, R}": r"\text{Agent} \rightleftharpoons \text{Environment} : \{S, A, R\}",
    }
    if s in exact:
        return exact[s]

    s = sqrt_convert(s)

    for a, b in FUNCS:
        s = re.sub(a, b, s)

    for a, b in GREEK.items():
        s = s.replace(a, b)
    for a, b in SYMBOLS.items():
        s = s.replace(a, b)

    # E[...] -> \mathbb{E}[...]
    s = re.sub(r"(?<![A-Za-z\\])E(?=\[)", r"\\mathbb{E}", s)

    # 中文放进 \text{}
    s = re.sub(r"([\u4e00-\u9fff]+)", lambda m: r"\text{%s}" % m.group(1), s)

    s = bars(s)

    # ^(n-1) -> ^{n-1}
    s = re.sub(r"\^\(([^()]*)\)", r"^{\1}", s)

    # 常见的 字母+单个数字 下标（s1 -> s_1）
    for a, b in (("s1", r"s_1"), ("s2", r"s_2"), ("s3", r"s_3"), ("s4", r"s_4"),
                 ("a1", r"a_1"), ("a2", r"a_2"), ("a3", r"a_3"), ("a4", r"a_4")):
        s = re.sub(r"(?<![A-Za-z0-9_{^\\])" + a + r"(?![0-9A-Za-z])", b, s)

    # a* / π* / q* -> 上标星号
    s = re.sub(r"([A-Za-z\)])\s*\*", r"\1^*", s)

    # 收尾清理：运算符两侧空白、去掉 _ ^ 后的空格
    s = re.sub(r"\s{2,}", " ", s)
    s = re.sub(r"([_^])\s+", r"\1", s)
    s = re.sub(r"\s+([_^])", r"\1", s)
    s = re.sub(r"\s+([})])", r"\1", s)
    s = re.sub(r"([({])\s+", r"\1", s)
    s = re.sub(r"\}\s+\(", r"}(", s)
    s = re.sub(r"(\\[a-zA-Z]+)\s+\(", r"\1(", s)
    return s.strip()


def split_fences(text):
    parts = []
    buf = []
    inf = False
    mark = ""
    for line in text.split("\n"):
        m = re.match(r"^\s*(`{3,}|~{3,})", line)
        if not inf and m:
            if buf:
                parts.append((False, "\n".join(buf)))
                buf = []
            inf = True
            mark = m.group(1)
            buf.append(line)
            continue
        if inf:
            buf.append(line)
            if m and m.group(1)[0] == mark[0] and len(m.group(1)) >= len(mark):
                parts.append((True, "\n".join(buf)))
                buf = []
                inf = False
                mark = ""
            continue
        buf.append(line)
    if buf:
        parts.append((inf, "\n".join(buf)))
    return parts


def process(path: pathlib.Path, apply: bool):
    text = path.read_text(encoding="utf-8")
    changes = []

    def do_part(part):
        def repl(m):
            inner = m.group(0)[1:-1]
            if not MATH_HINT.search(inner):
                return m.group(0)
            if re.fullmatch(r"[A-Za-z0-9_./-]+", inner):
                return m.group(0)
            new = "$" + convert(inner) + "$"
            changes.append((inner, new))
            return new

        return re.sub(r"`[^`\n]+`", repl, part)

    new_parts = []
    for is_code, part in split_fences(text):
        new_parts.append(part if is_code else do_part(part))
    new_text = "\n".join(new_parts)

    if apply and new_text != text:
        path.write_text(new_text, encoding="utf-8")
    return changes


if __name__ == "__main__":
    mode = sys.argv[1]
    files = [pathlib.Path(a) for a in sys.argv[2:]]
    total = 0
    for f in files:
        ch = process(f, mode == "--apply")
        if ch:
            print(f"\n=== {f} （{len(ch)} 处）===")
            for old, new in ch:
                print(f"  - `{old}`")
                print(f"  + {new}")
            total += len(ch)
    print(f"\n共 {total} 处，模式 {mode}")