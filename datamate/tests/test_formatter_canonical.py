from types import SimpleNamespace

from fmt.formatter import _canonical_text


def test_canonical_text_restores_stored_accents():
    ctx = SimpleNamespace(
        entity_index=SimpleNamespace(entries=[("product", "Snack Oishi tôm cay 40g", None)]),
        value_dict={},
    )
    assert _canonical_text("snack oishi tom cay 40g", ctx) == "Snack Oishi tôm cay 40g"
