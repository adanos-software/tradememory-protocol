import ast, pathlib

DET = pathlib.Path(__file__).resolve().parents[2] / "detector"

def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                yield a.name
        elif isinstance(node, ast.ImportFrom):
            yield node.module or ""

def test_detector_never_imports_owm():
    offenders = []
    for py in DET.rglob("*.py"):
        for mod in _imported_modules(py):
            if mod.startswith("tradememory.owm"):
                offenders.append((py.name, mod))
    assert offenders == [], f"detector must not import owm: {offenders}"

def test_detector_only_allows_whitelisted_tradememory():
    # the only tradememory import allowed is the ssrt engine
    bad = []
    for py in DET.rglob("*.py"):
        for mod in _imported_modules(py):
            if mod.startswith("tradememory.") and not mod.startswith("tradememory.ssrt"):
                bad.append((py.name, mod))
    assert bad == [], f"only tradememory.ssrt allowed: {bad}"
