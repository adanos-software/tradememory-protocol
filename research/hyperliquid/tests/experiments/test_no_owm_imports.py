"""Import-isolation guard for the experiments package.

Mirrors tests/detector/test_no_owm_imports.py: the experiment harness must never
import tradememory.owm.* and the ONLY tradememory.* import allowed (transitively,
via the detector) is tradememory.ssrt. The experiments package itself should only
depend on research.hyperliquid.* + stdlib.
"""
import ast
import pathlib

EXP = pathlib.Path(__file__).resolve().parents[2] / "experiments"


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            yield node.module or ""


def test_experiments_never_import_owm():
    offenders = []
    for py in EXP.rglob("*.py"):
        for mod in _imported_modules(py):
            if mod.startswith("tradememory.owm"):
                offenders.append((py.name, mod))
    assert offenders == [], f"experiments must not import owm: {offenders}"


def test_experiments_only_allow_whitelisted_tradememory():
    # the experiments package should not import tradememory.* directly at all;
    # the only tradememory dependency is tradememory.ssrt, reached via the detector.
    bad = []
    for py in EXP.rglob("*.py"):
        for mod in _imported_modules(py):
            if mod.startswith("tradememory.") and not mod.startswith("tradememory.ssrt"):
                bad.append((py.name, mod))
    assert bad == [], f"only tradememory.ssrt allowed (via detector): {bad}"
