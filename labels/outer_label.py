"""
labels/outer_label.py
Outer label (100mm x 100mm) — generation logic.
"""
import os
import json
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from engine.label_engine import fill_single_label, generate_multipage_pdf

BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
TEMPLATE_PATH = os.path.join(BASE_DIR, "templates", "outer_template.pdf")
CONFIG_PATH = os.path.join(BASE_DIR, "config", "outer_field_mapping.json")


def load_field_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def generate_single(row: dict) -> bytes:
    """row = one Excel row as a dict. Returns filled outer-label PDF bytes."""
    field_config = load_field_config()
    return fill_single_label(TEMPLATE_PATH, row, field_config)


def generate_batch(rows: list) -> bytes:
    """rows = list of Excel row dicts. Returns one merged multi-page PDF (all outer labels)."""
    field_config = load_field_config()
    return generate_multipage_pdf(TEMPLATE_PATH, rows, field_config)
