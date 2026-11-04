"""Cấu hình toàn cục của DataMate (phase 1 — MVP, gọi API).

Nguồn chuẩn: EXECUTION-MVP.md §3.4.  Mọi giá trị đọc từ biến môi trường;
không có secret trong repo.
"""

from __future__ import annotations

import os

RANDOM_SEED = 20261103
HOLDOUT_BUSINESSES = 6
SCHEMA_VERSION = "v4"

DATA_ROOT = os.environ.get("DATAMATE_DATA_ROOT", ".")
SPLIT = os.environ.get("DATAMATE_SPLIT", "public_test")
OUT_DIR = os.environ.get("DATAMATE_OUT_DIR", "public_test")
LOG_DIR = os.environ.get("DATAMATE_LOG_DIR", "public_test/logs")
CACHE_DIR = os.environ.get("DATAMATE_CACHE_DIR", "/tmp/datamate_cache")
DEADLINE_S = 5.25 * 3600

# LLM — phase 1: API MiniMax (OpenAI-compatible). Không tự host model.
LLM_BASE_URL = os.environ.get("DATAMATE_LLM_BASE_URL", "")
LLM_BASE_URLS = tuple(
    u.strip()
    for u in os.environ.get("DATAMATE_LLM_BASE_URLS", LLM_BASE_URL).split(",")
    if u.strip()
)
LLM_API_KEY = os.environ.get("DATAMATE_LLM_API_KEY", "")
LLM_MODEL = os.environ.get("DATAMATE_LLM_MODEL", "MiniMax-M3.1-flash")
LLM_CONCURRENCY = 16
LLM_MAX_RETRIES = 4
LLM_TIMEOUT_S = 120
LLM_CTX_TOKENS = 8192

# Chấm điểm (rulebook §9)
NUM_ABS_TOL = 1e-9
NUM_DECIMALS = 2
PERCENT_DECIMALS = 2
MONEY_ROUND = "half_up"

# Nghiệp vụ
EXPIRING_DEFAULT_DAYS = 30
SLOW_QTY_PERCENTILE = 25
HIGH_STOCK_PERCENTILE = 75
K1 = 3
K2 = 5
CALIB_MARGIN = 0.05
UNVERIFIED_EXTRA_MARGIN = 0.15
CALIB_MIN_TRAIN_PER_OUTTYPE = 50
SQL_TIMEOUT_S = 20
SQL_MAX_ROWS = 1000

# Ghi file
BATCH_SIZE = 32

# Thư mục artefact (không commit)
SURVEY_DIR = os.environ.get("DATAMATE_SURVEY_DIR", "survey")
CACHE_DB_DIR = CACHE_DIR
MODELS_DIR = os.environ.get("DATAMATE_MODELS_DIR", "models")


def split_dir(split: str | None = None) -> str:
    """Thư mục gốc của một split (``train`` hoặc ``public_test``)."""
    s = split or SPLIT
    return os.path.join(DATA_ROOT, s)


def out_path(split: str | None = None) -> str:
    s = split or SPLIT
    return os.path.join(DATA_ROOT, s, "submission.jsonl")


def log_dir(split: str | None = None) -> str:
    s = split or SPLIT
    return os.path.join(DATA_ROOT, s, "logs")


def cache_dir() -> str:
    return CACHE_DB_DIR
