"""Nạp `zaic_tools` của một split (EXECUTION-PLAN.md §8.2).

R7: mỗi split có `zaic_tools` riêng ⇒ 1 process chỉ nạp một split.
"""
import sys
from pathlib import Path

_LOADED_SPLIT = None
_LOADED_CLASS = None


def load_toolenv_class(split: str, root: Path):
    """Chèn <root>/<split> vào sys.path, import zaic_tools, trả về ToolEnv.

    Nếu process đã nạp một split khác ⇒ raise RuntimeError (R7).
    """
    global _LOADED_SPLIT, _LOADED_CLASS
    if _LOADED_SPLIT is not None and _LOADED_SPLIT != split:
        raise RuntimeError(
            f"process đã nạp split '{_LOADED_SPLIT}', không được nạp thêm split '{split}' (R7)"
        )
    if _LOADED_CLASS is not None:
        return _LOADED_CLASS

    root = Path(root)
    split_path = root / split
    if not split_path.is_dir():
        raise FileNotFoundError(f"không thấy thư mục split: {split_path}")
    if str(split_path) not in sys.path:
        sys.path.insert(0, str(split_path))
    try:
        import zaic_tools  # noqa: E402
    except ImportError as e:  # pragma: no cover - lỗi môi trường dữ liệu
        raise ImportError(f"không import được zaic_tools từ {split_path}: {e}") from e
    _LOADED_SPLIT = split
    _LOADED_CLASS = zaic_tools.ToolEnv
    return _LOADED_CLASS


def loaded_split():
    return _LOADED_SPLIT
