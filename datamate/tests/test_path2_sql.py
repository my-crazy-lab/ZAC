from types import SimpleNamespace

from paths.path2_sql import _validate_sql_refs


def test_path2_rejects_as_of_identifier():
    ctx = SimpleNamespace(views={"v_orders"}, con=None)
    assert "as_of" in (_validate_sql_refs(ctx, "SELECT * FROM v_orders WHERE order_date <= as_of") or "")


def test_path2_rejects_non_view_source():
    ctx = SimpleNamespace(views={"v_orders"}, con=None)
    assert "không tồn tại" in (_validate_sql_refs(ctx, "SELECT * FROM c_orders") or "")


def test_path2_accepts_known_view():
    ctx = SimpleNamespace(views={"v_orders"}, con=None)
    assert _validate_sql_refs(ctx, "SELECT COUNT(*) FROM v_orders") is None
