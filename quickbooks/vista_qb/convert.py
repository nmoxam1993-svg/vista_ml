"""Convert QBO Excel exports (.xlsx / .xls) to CSV for the engine.

QBO writes report numbers as formulas ("=769614.49", "=(B13)+(C13)...") with
no cached values, so a plain reader sees zeros. We evaluate those formulas
ourselves: only numbers, cell references, + - * / and parentheses are allowed.

Usage: python -m vista_qb.convert data/raw   (converts every .xls/.xlsx there)
Needs openpyxl (xlsx) and xlrd (xls) - the only non-stdlib dependencies.
"""

import ast
import csv
import operator
import re
import sys
from pathlib import Path

_REF = re.compile(r"\$?([A-Z]{1,3})\$?(\d+)")
_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.USub: operator.neg, ast.UAdd: operator.pos}


def _col_index(letters):
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def _arith(node):
    if isinstance(node, ast.Expression):
        return _arith(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_arith(node.left), _arith(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_arith(node.operand))
    raise ValueError("unsupported formula")


def evaluate_grid(grid):
    """Replace formula strings in a 2D list with their numeric values."""
    cache = {}

    def value(r, c, depth=0):
        if (r, c) in cache:
            return cache[(r, c)]
        v = grid[r][c] if r < len(grid) and c < len(grid[r]) else None
        if isinstance(v, str) and v.startswith("=") and depth < 200:
            expr = v[1:].replace("SUM(", "(")
            expr = _REF.sub(lambda m: repr(value(int(m.group(2)) - 1, _col_index(m.group(1)), depth + 1) or 0), expr)
            try:
                v = _arith(ast.parse(expr, mode="eval"))
            except (ValueError, SyntaxError, ZeroDivisionError):
                pass  # leave non-arithmetic formulas as text
        if isinstance(v, float):
            v = round(v, 2) + 0.0  # kill float noise like -3.4e-18 and -0.0
        cache[(r, c)] = v
        return v

    return [[value(r, c) for c in range(len(row))] for r, row in enumerate(grid)]


def read_grid(path):
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        import openpyxl
        ws = openpyxl.load_workbook(path, data_only=False).active
        return [list(r) for r in ws.iter_rows(values_only=True)]
    import xlrd
    s = xlrd.open_workbook(path).sheet_by_index(0)
    return [s.row_values(i) for i in range(s.nrows)]


def convert(path):
    path = Path(path)
    grid = evaluate_grid(read_grid(path))
    out = path.with_suffix(".csv")
    with out.open("w", newline="") as f:
        csv.writer(f).writerows([["" if v is None else v for v in row] for row in grid])
    return out, len(grid)


def main():
    folder = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
    for p in sorted(folder.iterdir()):
        if p.suffix.lower() in (".xls", ".xlsx"):
            out, n = convert(p)
            print(f"{p.name} -> {out.name} ({n} rows)")


if __name__ == "__main__":
    main()
