from types import SimpleNamespace

from schema.context import classify_rule, compile_context, render_context, rule_kinds


def test_classify_rule_finds_business_kinds():
    kinds = classify_rule("Đơn có ghi chú=hủy thì tính là đơn huỷ")
    assert "cancel" in kinds
    kinds = classify_rule("Quy đổi 1 thùng = 24 hộp")
    assert "unit" in kinds


def test_compile_context_keeps_rules_and_entities():
    readme = ("## Quy ước\n"
              "- Doanh thu = tổng tiền hàng sau chiết khấu\n"
              "- Phí ship là dòng riêng, không tính doanh thu\n")
    mapping = {"entities": {"lines": {"table": "ly", "tables": ["ly"],
                                       "cols": {"line_amount": "Tien", "qty": "SL"}}}}
    ctx = compile_context(readme, mapping, {}, SimpleNamespace(),
                          {"v_lines"}, {"line_amount", "qty"},
                          archetype="A_flat", schema_conf=0.9)
    kinds = rule_kinds(ctx)
    assert "revenue" in kinds
    assert "shipping" in kinds
    assert ctx["entities"]["lines"]["roles"] == ["line_amount", "qty"]
    text = render_context(ctx)
    assert "[SHOP CONTEXT]" in text
    assert "revenue" in text


def test_render_context_handles_missing_context():
    assert render_context(None) == ""
