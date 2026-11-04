"""Prompt cho LLM (M9/M10/M12).

Nguyên tắc: LLM **không tính ngày, không viết luật nghiệp vụ** — nó chỉ điền
vào tập đóng (schema) và được kiểm tra lại bằng code.
"""

from __future__ import annotations

from dtypes import BizContext, TimeWindow

SPEC_PROMPT = """Bạn là bộ chuyển câu hỏi thành đặc tả truy vấn cho dữ liệu bán hàng.

[LUẬT]
- "hôm nay" = ngày trong câu hỏi; các cửa sổ thời gian đã được tính sẵn.
- Chỉ dùng metric có trong danh sách.
- filters.values phải lấy từ danh sách giá trị được cung cấp.
- time chỉ được dùng các nhãn có trong danh sách cửa sổ.
- output: number (tiền/số lượng), percent (%), string (tên), date (ngày),
  boolean (có/không), list (danh sách).

[ĐỒ NGHĨA]
{cards}

[CỬA SỔ THỜI GIAN]
{windows}

[DANH SÁCH GIÁ TRỊ]
{values}

[THỰC THỂ ĐÃ KHỚP]
{entities}

[CÂU HỎI]
{question}

Trả về JSON theo schema."""

SQL_PROMPT = """Bạn viết SQL DuckDB để trả lời câu hỏi về dữ liệu bán hàng.

[QUY TẮC]
- Chỉ dùng các bảng/view được cung cấp.
- Bắt buộc lọc theo as_of: mọi phát sinh phải có ngày <= '{as_of}'.
- Không tự tính cửa sổ thời gian: dùng đúng các khoảng ngày được cung cấp.
- Không dùng phép tính nghiệp vụ tự định nghĩa (đã có sẵn trong view).
- Trả về đúng một câu SELECT, không dùng CTE phức tạp nếu không cần.

[ĐỒ NGHĨA]
{cards}

[BẢNG]
{tables}

[CÂU HỎI]
{question}

Trả về JSON theo schema."""

ANSWER_PROMPT = """Trả lời câu hỏi về dữ liệu bán hàng chỉ dựa vào số liệu được cung cấp.

[LUẬT]
- Không suy đoán. Nếu số liệu không đủ để trả lời ⇒ type="unanswerable".
- Tiền: số nguyên đồng. Phần trăm: 2 chữ số thập phân.
- Trả về JSON theo schema.

[ĐỒ NGHĨA]
{cards}

[SỐ LIỆU]
{data}

[CÂU HỎI]
{question}

Trả về JSON theo schema."""

JUDGE_PROMPT = """So sánh đáp án dự đoán với đáp án đúng và chấm điểm.
Trả về JSON theo schema.

[ĐỒ NGHĨA]
{cards}

[CÂU HỎI]
{question}

[ĐÁP ÁN ĐÚNG]
{reference}

[ĐÁP ÁN DỰ ĐOÁN]
{prediction}"""


def _windows_block(windows: list[TimeWindow]) -> str:
    if not windows:
        return "(không có)"
    return "\n".join(
        f"- {w.label}: từ {w.start.isoformat()} đến {w.end.isoformat()}"
        + (f" (loại: {w.kind})" if w.kind != "period" else "")
        for w in windows)


def spec_prompt(question: str, ctx: BizContext, windows: list[TimeWindow],
                entities: list[str]) -> str:
    values = "\n".join(f"- {k}: {', '.join(v[:20])}" for k, v in (ctx.value_dict or {}).items())
    return SPEC_PROMPT.format(
        cards=ctx.card, windows=_windows_block(windows),
        values=values or "(không có)",
        entities="\n".join(f"- {e}" for e in entities) or "(không có)",
        question=question)


def sql_prompt(question: str, ctx: BizContext, as_of: str, tables: str) -> str:
    return SQL_PROMPT.format(cards=ctx.card, tables=tables, as_of=as_of, question=question)


def answer_prompt(question: str, ctx: BizContext, data: str) -> str:
    return ANSWER_PROMPT.format(cards=ctx.card, data=data, question=question)


def judge_prompt(question: str, ctx: BizContext, reference: str, prediction: str) -> str:
    return JUDGE_PROMPT.format(cards=ctx.card, question=question,
                               reference=reference, prediction=prediction)
