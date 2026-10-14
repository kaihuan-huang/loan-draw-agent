from __future__ import annotations

import typing

import pytest

from loan_draw.extract import clean_ocr, invoice_schema


# Found by the hard eval set (2026-10-14): scanned amounts like "34,492.2O" were misread or dropped.
@pytest.mark.parametrize("raw, want", [
    ("Amount due: USD 34,492.2O", "Amount due: USD 34,492.20"),
    ("Amount of payment: $l2,3O4.5l", "Amount of payment: $12,304.51"),
    ("lNVOICE PIN-6017 from Pinecrest", "lNVOICE PIN-6017 from Pinecrest"),  # words are left alone
    ("Total: $1,000.00", "Total: $1,000.00"),
])
def test_clean_ocr_fixes_letters_inside_amounts_only(raw, want):
    assert clean_ocr(raw) == want


# Found by the hard eval set: "rough-in wiring" was not mapped to the "electrical" budget line.
def test_invoice_line_is_limited_to_the_loans_budget_lines():
    schema = invoice_schema(["electrical", "framing"])
    ann = schema.model_fields["line"].annotation
    assert set(typing.get_args(typing.get_args(ann)[0])) == {"electrical", "framing"}
    assert schema(line="framing").line == "framing"
    with pytest.raises(ValueError):
        schema(line="rough-in wiring")
