"""Khảo sát `zaic_tools` — công thức chấm của BTC (EXECUTION-PLAN.md §8.0.2).

Sinh: `reports/zaic_scoring.md`.
"""
import re
from pathlib import Path

from _bootstrap import ROOT, SPLIT  # noqa: F401

from lifemate import config

KEYWORDS = ["f1", "score", "compare", "match", "canon", "validate", "fuzzy", "token", "precision", "recall"]


def main():
    zaic_dir = config.split_dir(SPLIT) / "zaic_tools"
    readme = zaic_dir / "README.md"
    modules = sorted(p.name for p in zaic_dir.glob("*.py"))
    apps = sorted(p.name for p in (zaic_dir / "apps").glob("*.py"))

    hits = []
    for path in list(zaic_dir.glob("*.py")) + list((zaic_dir / "apps").glob("*.py")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        for i, line in enumerate(text.splitlines(), 1):
            low = line.lower()
            if any(kw in low for kw in KEYWORDS) and ("def " in line or "class " in line or "==" in line):
                hits.append(f"{path.relative_to(zaic_dir)}:{i}: {line.strip()[:160]}")

    has_formula = any("f1" in h.lower() for h in hits)
    md = []
    md.append("# `zaic_tools` — công thức chấm của BTC\n")
    md.append(f"- Thư mục: `{zaic_dir}`")
    md.append(f"- Module cấp cao: {', '.join(modules)}")
    md.append(f"- Số module app: {len(apps)}\n")
    md.append("## (a) Công thức F1-call\n")
    if has_formula:
        md.append("Có dấu hiệu công thức trong mã:\n")
    else:
        md.append("**Không có công thức F1-call trong mã `zaic_tools`.** ")
        md.append("Gói dữ liệu chỉ có runtime chạy tool + `canon`/`state_hash`; phần chấm điểm "
                  "chạy ở máy chấm của BTC, không nằm trong gói.\n")
    md.append("⇒ Dùng định nghĩa F1-call của `EXECUTION-PLAN.md` §9.1 (3 kiểu khớp: "
              "`strict`, `fuzzy-aware`, `soft`), ưu tiên `fuzzy-aware`.\n")
    md.append("### Các dòng liên quan tìm được\n")
    md.append("```")
    for h in hits[:60]:
        md.append(h)
    md.append("```\n")
    md.append("## (b) Lệnh CLI kiểm tra file nộp\n")
    md.append("```bash")
    md.append(f"python -m zaic_tools --split {SPLIT} --root {config.DATA_ROOT} --validate submission.jsonl")
    md.append("```\n")
    md.append("## (c) Hàm có thể import để dùng lại\n")
    md.append("```python")
    md.append("from zaic_tools import schema_validate, state_hash, canon, ToolEnv")
    md.append("from zaic_tools.validate import schema_error")
    md.append("```\n")
    md.append("- `schema_validate(calls, catalog)` → một dict `{ok, error, name}` cho mỗi call (dùng lại được trong `eval/metrics.py`).")
    md.append("- `state_hash(state)` = sha256 của `canon(state)` ⇒ `state_hash` của dòng nộp.\n")
    if readme.exists():
        md.append("## Nội dung `zaic_tools/README.md`\n")
        md.append("```")
        md.append(readme.read_text(encoding="utf-8")[:4000])
        md.append("```")

    out = config.reports_dir() / "zaic_scoring.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8")
    print({"->": str(out), "has_f1_formula": has_formula, "n_modules": len(modules)})


if __name__ == "__main__":
    main()
