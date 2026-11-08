"""Prompt cho LLM (M9/M10/M12).

Nguyên tắc: LLM **không tính ngày, không viết luật nghiệp vụ** — nó chỉ điền
vào tập đóng (schema) và được kiểm tra lại bằng code.
"""

from __future__ import annotations

import os

from dtypes import BizContext, TimeWindow
from schema.business_graph import render_graph_card
from schema.context import render_context

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
- Mọi ngày phải dùng literal ISO trong cửa sổ hoặc as_of={as_of}; tuyệt đối không dùng tên cột/biến `as_of`.
- Không tự tính cửa sổ thời gian: dùng đúng các khoảng ngày được cung cấp.
- Không dùng phép tính nghiệp vụ tự định nghĩa (đã có sẵn trong view).
- Trả về đúng một câu SELECT, không dùng CTE phức tạp nếu không cần.

[ĐỒ NGHĨA]
{cards}

[BẢNG]
{tables}

[CỬA SỔ THỜI GIAN]
{windows}

[CÂU HỎI]
{question}

Trả về JSON theo schema."""

PLANNER_PROMPT = """Bạn là bộ chọn truy vấn cho dữ liệu bán hàng. Bạn KHÔNG viết SQL.

[CÂU HỎI]
{question}

{normalized}[CÁCH CHỌN TEMPLATE]
- Hỏi tổng/bao nhiêu trong kỳ → template có hậu tố .total.
- Hỏi theo sản phẩm/nhóm hàng/khách/kênh/nhân viên/tháng/ngày, hoặc "nhất/top" →
  template .<subject>.rank (limit = số câu hỏi yêu cầu, mặc định 5).
- Hỏi "chiếm bao nhiêu %/tỷ trọng" → template .<subject>.share.
- Hỏi "so với kỳ trước" → template .window.compare.
- Hỏi "tháng nào/ngày nào cao nhất", "tăng/giảm liên tục" → .window.series hoặc .window.trend.
- Hỏi tồn kho/công nợ tại thời điểm → template .point.
- Metric: doanh thu/tiền bán=revenue; số lượng=qty; số đơn=orders; số khách=customers;
  giá trị trung bình mỗi đơn=aov; huỷ=cancel_rate/cancelled_orders; lợi nhuận=profit.
- Subject: sản phẩm/mặt hàng=product; nhóm/ngành=category; khách=customer;
  tháng=month; ngày=day; kênh=channel; thanh toán=pay_method.
- "tháng 9/2025", "quý 3/2025" là MỐC THỜI GIAN, không phải chiều phân tích.
  Chỉ chọn subject month/day khi câu hỏi hỏi "tháng nào", "theo từng tháng",
  "ngày nào", "theo từng ngày".
- "top N", "bán chạy", "hàng nào chạy nhất" là xếp hạng theo product, không theo tháng.
  "chạy nhất/bán chạy/bán nhiều nhất" dùng metric qty (trừ khi câu hỏi nói rõ
  doanh thu/tiền). Hỏi "top N/những gì" dùng .rank; hỏi "nào/nhất" cần tên dùng .top.
- "bao nhiêu đơn/bill/hoá đơn" dùng template .total, không dùng .day.rank.
- "bình quân/trung bình mỗi đơn" dùng metric aov.
- Doanh thu/tiền/số lượng của MỘT mặt hàng/khách cụ thể → template .total kèm
  filter đúng đối tượng (không cần template riêng theo đối tượng).
- Giá bán/giá nhập bình quân của một mặt hàng → price.product.total /
  import_avg_price.product.total kèm filter product.
- Hỏi "số đơn có doanh thu/tiền hàng từ X trở lên" → template orders.threshold,
  đặt params.threshold = X (chỉ số, bỏ dấu chấm).
- Hỏi "bao nhiêu khách mua từ N đơn trở lên" → template customers.threshold,
  đặt params.threshold = N.
- Hỏi "size M/L/XL" → filters field="size", values=["M"] (không tự suy ra
  một sản phẩm cụ thể).
- Hỏi "đơn trả bằng chuyển khoản/tiền mặt/thẻ" → filters field="pay_method".
  "bán qua Shopee/Zalo/kênh X" → filters field="channel".
- "nhóm/loại hàng X" → filters field="category"; "khách X" → filters customer.
- Nếu [THỰC THỂ ĐÃ KHỚP] có pay_method/channel/category/customer, PHẢI thêm
  filter tương ứng, không được bỏ qua.
- Hỏi "N mặt hàng/khách..." (N>1) → dùng .rank, không dùng .top.
- Hỏi "tháng nào/ngày nào/kỳ nào ... cao nhất/nhiều nhất" (chọn một kỳ trong
  nhiều kỳ) → dùng template .window.peak.
- params chỉ chứa các khóa của template; không đưa metric/subject/output vào params.

[QUY TẮC BẮT BUỘC]
- Chỉ chọn đúng một template_id trong danh sách bên dưới.
- Không tự tạo template, không đổi metric/subject/output của template.
- filters.values phải lấy đúng từ danh sách giá trị; chỉ thêm filter khi câu hỏi
  nhắc đích danh đối tượng đó.
- time chỉ dùng nhãn trong danh sách cửa sổ thời gian.
- params chỉ dùng khóa template cho phép; không gửi chuỗi rỗng.
- Nếu thật sự không có template phù hợp, trả template_id="" và confidence=0.

[NGỮ CẢNH SHOP]
{context}

[VIEW/CỘT/GIÁ TRỊ]
{cards}

[DANH SÁCH TEMPLATE]
{catalog}

[CỬA SỔ THỜI GIAN]
{windows}

[GIÁ TRỊ HỢP LỆ]
{values}

[THỰC THỂ ĐÃ KHỚP]
{entities}

Trả JSON: template_id, params, filters, time, confidence, evidence
(evidence: trích ngắn lý do chọn, dùng đúng thuật ngữ trong ngữ cảnh shop)."""

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
        cards=ctx.card + _graph_block(question, ctx), windows=_windows_block(windows),
        values=values or "(không có)",
        entities="\n".join(f"- {e}" for e in entities) or "(không có)",
        question=question)


def _values_block(ctx: BizContext) -> str:
    return "\n".join(f"- {k}: {', '.join(v[:20])}"
                     for k, v in (ctx.value_dict or {}).items()) or "(không có)"


def planner_prompt(question: str, ctx: BizContext, windows: list[TimeWindow],
                   entities: list[str], templates: list,
                   normalized: str = "") -> str:
    from engine.catalog import render_catalog

    context = render_context(getattr(ctx, "context", None)) or ctx.card
    norm_block = ""
    if normalized and normalized.strip() and normalized.strip() != question.strip():
        norm_block = f"[CÂU HỎI ĐÃ CHUẨN HÓA]\n{normalized}\n\n"
    return PLANNER_PROMPT.format(
        normalized=norm_block,
        context=context,
        cards=ctx.card[:4000],
        catalog=render_catalog(templates) or "(không có template)",
        windows=_windows_block(windows),
        values=_values_block(ctx),
        entities="\n".join(f"- {e}" for e in entities) or "(không có)",
        question=question)


def sql_prompt(question: str, ctx: BizContext, as_of: str, tables: str,
               windows: list[TimeWindow] | None = None) -> str:
    graph = _graph_block(question, ctx)
    return SQL_PROMPT.format(cards=ctx.card + graph, tables=tables, as_of=as_of,
                             windows=_windows_block(windows or []), question=question)


def _graph_block(question: str, ctx: BizContext) -> str:
    mode = os.environ.get("DATAMATE_GRAPH_MODE", "subgraph").lower()
    if not ctx.graph or mode == "off":
        return ""
    return "\n" + render_graph_card(ctx.graph, question if mode == "subgraph" else "")


def answer_prompt(question: str, ctx: BizContext, data: str) -> str:
    return ANSWER_PROMPT.format(cards=ctx.card, data=data, question=question)


def judge_prompt(question: str, ctx: BizContext, reference: str, prediction: str) -> str:
    return JUDGE_PROMPT.format(cards=ctx.card, question=question,
                               reference=reference, prediction=prediction)
