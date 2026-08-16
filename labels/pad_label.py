"""
labels/pad_label.py
"Pad" (full proof sheet) — the pad.pdf template stays BLANK. At generation
time we:
  1. Generate the Inner label (via labels.inner_label, same config used for
     the standalone Inner output).
  2. Generate the Outer label (via labels.outer_label, same config used for
     the standalone Outer output).
  3. Composite both onto a copy of pad.pdf at the Inner/Outer box positions.
  4. Fill the header fields (Order ID, Item, Style Code, Color) directly on
     the pad.

This way inner_field_mapping.json / outer_field_mapping.json stay the single
source of truth — editing them updates the Pad output automatically too.
"""
import os
import json
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
import fitz
from engine.label_engine import fill_single_label, compose_pdf_into_rect, expand_tc_barcode_variants
import labels.inner_label as inner_label
import labels.outer_label as outer_label

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "pad.pdf")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "pad_header_mapping.json")

# Where the Inner/Outer boxes sit on the pad page (PDF points, top-left origin)
INNER_RECT = fitz.Rect(90.027, 350.416, 288.452, 492.686)
OUTER_RECT = fitz.Rect(378.794, 257.954, 661.259, 541.419)


def load_field_config():
    """Header-only fields — Inner/Outer field editing happens on their own tabs."""
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def _generate_one_page(row: dict) -> bytes:
    """Build ONE pad page for a row that already has a single TC_Number_st1/
    Barcode_st1 pair (variant expansion, if any, happens before this is called)."""
    header_config = load_field_config()

    pad_bytes = fill_single_label(TEMPLATE_PATH, row, header_config)
    doc = fitz.open("pdf", pad_bytes)

    inner_bytes = inner_label.generate_single(row)
    outer_bytes = outer_label.generate_single(row)

    compose_pdf_into_rect(doc, 0, INNER_RECT, inner_bytes)
    compose_pdf_into_rect(doc, 0, OUTER_RECT, outer_bytes)

    out = doc.tobytes()
    doc.close()
    return out


def generate_single(row: dict) -> bytes:
    """
    row = one Excel row as a dict. If the row carries multiple TC_Number_stN /
    Barcode_stN pairs (st1..st7), this returns ONE PAGE PER PAIR — all other
    fields stay identical across pages, only TC_Number/Barcode change. A row
    with just TC_Number_st1/Barcode_st1 filled still returns a single page,
    same as before.
    """
    variants = expand_tc_barcode_variants(row)
    if len(variants) == 1:
        return _generate_one_page(variants[0])

    merged = fitz.open()
    for variant_row in variants:
        page_bytes = _generate_one_page(variant_row)
        page_doc = fitz.open("pdf", page_bytes)
        merged.insert_pdf(page_doc)
        page_doc.close()
    out = merged.tobytes()
    merged.close()
    return out


def generate_batch(rows: list) -> bytes:
    """rows = list of Excel row dicts. Returns one merged multi-page PDF
    (all pads, with each row already expanded into its own TC/Barcode variant
    pages via generate_single)."""
    merged = fitz.open()
    for row in rows:
        single_bytes = generate_single(row)
        single_doc = fitz.open("pdf", single_bytes)
        merged.insert_pdf(single_doc)
        single_doc.close()
    out = merged.tobytes()
    merged.close()
    return out
