"""Hiệu chỉnh bộ quyết định (M12) — logistic regression 1 lớp, thuần NumPy.

Mô hình được lưu ở ``models/calibration.json``; nếu chưa có thì dùng mặc
định (ngưỡng giữ nhiều đáp án).
"""

from __future__ import annotations

import json
import logging
import math
import os
from typing import Any

import config
from decide.features import FEATURE_NAMES

log = logging.getLogger(__name__)

MODEL_PATH = os.path.join(config.MODELS_DIR, "calibration.json")

DEFAULT_MODEL: dict[str, Any] = {
    "weights": [0.0] * len(FEATURE_NAMES),
    "intercept": 0.0,
    "threshold": 0.35,
    "margin": config.CALIB_MARGIN,
    "trained": False,
    "n_train": 0,
}


def load_model(path: str = MODEL_PATH) -> dict[str, Any]:
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and "weights" in data:
                return data
        except (OSError, ValueError):
            pass
    return dict(DEFAULT_MODEL)


def save_model(model: dict[str, Any], path: str = MODEL_PATH) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(model, fh, ensure_ascii=False, indent=1)


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def predict_proba(model: dict[str, Any], feats: dict[str, float]) -> float:
    """Xác suất câu hỏi **trả lời được**."""
    weights = model.get("weights") or []
    z = float(model.get("intercept", 0.0))
    for i, name in enumerate(FEATURE_NAMES):
        if i < len(weights):
            z += float(weights[i]) * float(feats.get(name, 0.0))
    return sigmoid(z)


def fit(samples: list[tuple[dict[str, float], int]], epochs: int = 400,
        lr: float = 0.35) -> dict[str, Any]:
    """Huấn luyện logistic regression (nhãn 1 = trả lời được).

    ``samples``: [(đặc trưng, nhãn)].
    """
    if not samples:
        return dict(DEFAULT_MODEL)
    n = len(samples)
    dim = len(FEATURE_NAMES)
    w = [0.0] * dim
    b = 0.0
    for _ in range(epochs):
        gw = [0.0] * dim
        gb = 0.0
        for feats, label in samples:
            z = b + sum(w[i] * float(feats.get(name, 0.0)) for i, name in enumerate(FEATURE_NAMES))
            p = sigmoid(z)
            err = p - label
            gb += err
            for i, name in enumerate(FEATURE_NAMES):
                gw[i] += err * float(feats.get(name, 0.0))
        for i in range(dim):
            w[i] -= lr * gw[i] / n
        b -= lr * gb / n
    model = {
        "weights": [round(x, 6) for x in w],
        "intercept": round(b, 6),
        "threshold": 0.35,
        "margin": config.CALIB_MARGIN,
        "trained": True,
        "n_train": n,
        "feature_names": FEATURE_NAMES,
    }
    return model


def choose_threshold(model: dict[str, Any], samples: list[tuple[dict[str, float], int]]
                      ) -> float:
    """Chọn ngưỡng tối đa F1 trên tập train (có sẵn)."""
    best_t, best_f1 = 0.5, -1.0
    for t in [i / 100 for i in range(5, 96, 5)]:
        tp = fp = fn = 0
        for feats, label in samples:
            p = predict_proba(model, feats) >= t
            if p and label:
                tp += 1
            elif p and not label:
                fp += 1
            elif not p and label:
                fn += 1
        if tp == 0:
            continue
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        rec = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        if f1 > best_f1:
            best_f1, best_t = f1, t
    return best_t
