"""Bộ quyết định cuối (M12): trả lời / không trả lời được / escalate."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import config
from decide.answerability import check as check_answerability
from decide.calibrate import load_model, predict_proba
from decide.candidate_check import check_candidate
from decide.features import extract_features
from dtypes import Answer, AnswerCheck, AnswerType, BizContext, EntityMatch, TimeWindow
from engine.semantics import metric_compatible
from text.normalize import nd

log = logging.getLogger(__name__)


@dataclass
class Decision:
    action: str            # "answer" | "unanswerable" | "abstain" | "escalate"
    answer: Answer | None = None
    p_unanswerable: float = 0.0
    reason: str = ""


def decide(question: str, ctx: BizContext, windows: list[TimeWindow],
           entities: list[EntityMatch] | None = None,
           candidate: Answer | None = None,
           model: dict[str, Any] | None = None,
           spec_metric: str | None = None,
           spec_subject: str | None = None,
           spec_intent: str | None = None,
           spec_output: str | None = None,
           as_of=None, candidate_path: str | None = None,
           candidate_agreement: float = 1.0) -> Decision:
    """Quyết định cuối cho một câu hỏi."""
    model = model or load_model()
    check: AnswerCheck = check_answerability(question, ctx, windows, entities, as_of)

    if not check.answerable:
        return Decision(action="unanswerable",
                        answer=Answer(type=AnswerType.UNANSWERABLE.value,
                                      reason=check.reason),
                        p_unanswerable=check.p_unanswerable, reason=check.reason)

    if candidate is None:
        return Decision(action="abstain", answer=None,
                        p_unanswerable=check.p_unanswerable, reason="no_candidate")

    ok_kind, kind_reason = check_candidate(question, candidate)
    if not ok_kind:
        return Decision(action="abstain", answer=None,
                        p_unanswerable=check.p_unanswerable, reason=kind_reason)

    # Spec chọn sai miền dữ liệu (hỏi phiếu nhập mà tính doanh thu, hỏi đơn
    # huỷ mà đếm mọi đơn) vẫn ra số hợp lý nên cửa kiểu đáp án không bắt
    # được. So khớp ngữ nghĩa ở đây; lệch thì bỏ, không nộp số sai.
    has_entity = any(e.kind in ("product", "customer") for e in (entities or []))
    ok_sem, sem_reason = metric_compatible(nd(question), spec_metric, spec_output,
                                           has_entity=has_entity)
    if not ok_sem:
        return Decision(action="abstain", answer=None,
                        p_unanswerable=check.p_unanswerable, reason=sem_reason)

    # Đo riêng năng lực planner/SQL: bỏ qua calibration cũ (đang học trên
    # pipeline cũ nên chặn oan đáp án đúng).
    if os.environ.get("DATAMATE_DECIDER", "on").lower() in ("off", "0", "none"):
        return Decision(action="answer", answer=candidate, p_unanswerable=0.0,
                        reason="decider_off")

    feats = extract_features(question, ctx, windows, entities,
                             spec_metric, spec_subject, spec_intent, spec_output,
                             candidate_path=candidate_path,
                             candidate_agreement=candidate_agreement)
    p = predict_proba(model, feats)
    threshold = float(model.get("threshold", 0.35))
    margin = float(model.get("margin", config.CALIB_MARGIN))
    if p < threshold:
        # SAI = −1, BỎ = 0 ⇒ thà **abstain**, không phải "unanswerable"
        return Decision(action="abstain", answer=None, p_unanswerable=1.0 - p,
                        reason="p_trong_thap")
    if p < threshold + margin and ctx.schema_conf < 0.6:
        return Decision(action="abstain", answer=None, p_unanswerable=1.0 - p,
                        reason="schema_conf_thap")
    return Decision(action="answer", answer=candidate, p_unanswerable=1.0 - p, reason="ok")
