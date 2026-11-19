import sys
import io
import ast
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
_ROOT = Path(r"C:\VPS CONTABO\HFT_ML4T")

def parse_py_file(p: Path):
    try:
        tree = ast.parse(p.read_text(encoding='utf-8', errors='ignore'))
        classes = {}
        functions = []
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                methods = [m.name for m in node.body if isinstance(m, ast.FunctionDef)]
                classes[node.name] = methods
            elif isinstance(node, ast.FunctionDef):
                functions.append(node.name)
        return classes, functions
    except Exception as e:
        return {"ERROR": str(e)}, []

py_files = sorted(list(_ROOT.glob("*.py")) + list((_ROOT / "core").glob("*.py")) + list((_ROOT / "strategies").glob("*.py")))

print("=== GIAI ĐOẠN 1: BẢN ĐỒ TẤT CẢ FILE VÀ HÀM THEO 3 TẦNG ===")
for pf in py_files:
    rel = pf.relative_to(_ROOT)
    cls, fns = parse_py_file(pf)
    print(f"\n[{rel}]")
    if cls:
        for cname, methods in cls.items():
            print(f"  Class {cname}: {', '.join(methods[:8])}{' ...' if len(methods)>8 else ''}")
    if fns:
        print(f"  Functions: {', '.join(fns[:8])}{' ...' if len(fns)>8 else ''}")
