"""Cấu hình tập trung cho toàn bộ harness (EXECUTION-MVP.md §4.3).

Mọi hằng số và cờ nằm ở đây; các module khác không tự định nghĩa ngưỡng.
Giá trị mặc định có thể ghi đè bằng biến môi trường hoặc bằng `--set KEY=VALUE`
của `eval/run.py` (dùng cho ablation).
"""
import json
import os
from pathlib import Path


def _load_env():
    """Nạp .env tối giản: KEY=VALUE, bỏ dòng trống/#, không ghi đè biến đã có."""
    p = Path(__file__).resolve().parent.parent / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_ROOT = Path(os.getenv("LIFEMATE_DATA_ROOT", str(REPO_ROOT / "train+public_test")))
SPLIT_DEFAULT = "train"

# --- LLM: MiniMax qua API OpenAI-compatible ---
LLM_BASE_URL = os.getenv("LIFEMATE_LLM_BASE_URL", "")
LLM_API_KEY = os.getenv("LIFEMATE_LLM_API_KEY", "")
LLM_MODEL = os.getenv("LIFEMATE_LLM_MODEL", "")
LLM_EXTRA_BODY = json.loads(os.getenv("LIFEMATE_LLM_EXTRA_BODY", "{}") or "{}")
LLM_TEMPERATURE = 0
LLM_TIMEOUT, LLM_MAX_RETRIES = 60, 5
LLM_MAX_TOKENS = 512

# --- Nhận diện thực thể ---
ENTITY_MATCH_THRESHOLD = 0.80
ENTITY_AMBIGUITY_GAP = 0.05
ENTITY_UNIQUE_MIN_CONF = 0.90

# --- Scope [MVP3] ---
# Ngưỡng chốt từ reports/scope_tune.json (quét trên tune_ids, ràng buộc
# recall act+ask >= 99%; tín hiệu từ vựng, giả định LLM trả CO).
SCOPE_RATIO_THRESHOLD = 0.3
SCOPE_COVERAGE_THRESHOLD = 0.0
SCOPE_SKIP_LLM_IF_RATIO_GE = 0.9

# --- Prefetch ---
PREFETCH_MODE = "off"            # "off" | "deps" | "all"
PREFETCH_MAX_READS = 2

# --- Gate ---
XREF_MODE = "strict"             # "strict" | "lenient"
DEFER_UNVERIFIED_REF_WRITES = True
MAX_NUDGES = 2
ENABLE_AUTOFILL_REF = True
ENABLE_OVERRIDE = False
ENABLE_AMBIG_ASK = False
ASK_AFTER_PARTIAL = True
ONE_OF_ASK_MODE = "auto"
DROP_DUPLICATE_READS = True
SILENT_RETRY = 1

# --- Executor ---
MAX_TURNS, MAX_WRITES = 6, 8
SAMPLE_DEADLINE_S = 120
REPEAT_MARKERS = ("thêm", "nữa", "lại", "tiếp")

# --- Prompt/few-shot ---
SNAPSHOT_MAX_CHARS = 6000
ENABLE_FEWSHOT = False
FEWSHOT_K = 3
ENABLE_POLICY_RULES = False

# --- Ghi log ---
DEBUG_DIR = "debug"
CACHE_DIR = "cache"
DEBUG_MAX_BYTES = 200_000

# --- Thư mục artefact (tuyệt đối, dựa trên REPO_ROOT) ---
REPORTS_DIR = REPO_ROOT / "reports"
RUNS_DIR = REPO_ROOT / "runs"


def cache_dir() -> Path:
    return REPO_ROOT / CACHE_DIR


def debug_dir() -> Path:
    return REPO_ROOT / DEBUG_DIR


def reports_dir() -> Path:
    return REPORTS_DIR


def runs_dir() -> Path:
    return RUNS_DIR


def split_dir(split: str) -> Path:
    return DATA_ROOT / split


def catalog_path(split: str) -> Path:
    return split_dir(split) / f"{split}_tools_catalog.json"


def samples_path(split: str) -> Path:
    return split_dir(split) / f"{split}.jsonl"


def llm_configured() -> bool:
    """Đủ cấu hình để gọi LLM hay chưa."""
    return bool(LLM_BASE_URL and LLM_MODEL)


# --- Ghi đè cấu hình cho ablation (`--set KEY=VALUE`) ---
_OVERRIDABLE = {
    k: v for k, v in list(globals().items())
    if k.isupper() and not k.startswith("_") and isinstance(v, (bool, int, float, str))
}


def coerce_like(default_value, raw: str):
    """Ép kiểu theo giá trị mặc định của biến (bool -> True/False/1/0, int, float, str)."""
    if isinstance(default_value, bool):
        low = raw.strip().lower()
        if low in ("1", "true", "yes", "on"):
            return True
        if low in ("0", "false", "no", "off"):
            return False
        return bool(low)
    if isinstance(default_value, int):
        try:
            return int(raw)
        except ValueError:
            return default_value
    if isinstance(default_value, float):
        try:
            return float(raw)
        except ValueError:
            return default_value
    return raw


def apply_overrides(pairs) -> dict:
    """Áp các cặp KEY=VALUE lên module này; trả về dict các giá trị đã ghi đè.

    `pairs` là list chuỗi "KEY=VALUE" (hoặc cặp (key, value)).
    """
    applied = {}
    for item in pairs or []:
        if isinstance(item, str):
            if "=" not in item:
                continue
            key, raw = item.split("=", 1)
        else:
            key, raw = item
        key = key.strip()
        if key not in _OVERRIDABLE:
            continue
        value = coerce_like(_OVERRIDABLE[key], raw)
        globals()[key] = value
        applied[key] = value
    return applied
