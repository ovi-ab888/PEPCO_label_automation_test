"""
engine/label_engine.py
Shared core engine used by every label type (inner, outer, ...).
Takes a FIXED template PDF + one Excel row -> returns a filled PDF (bytes).

Field config entry:
{
    "name": "Excel_Column_Name",
    "type": "text" | "barcode" | "qr",
    "x": 10, "y": 20,                 # position in PDF points, top-left origin
    "font_size": 8,                   # text only
    "prefix": "Style: ",              # optional, text only
    "suffix": "",                     # optional, text only
    "cover": [x0, y0, x1, y1],        # optional: white-out a placeholder area first
    "width": 100, "height": 30,       # barcode only
    "size": 60,                       # qr only
    "font": "arial",                  # optional, key into FONTS dict below
}
"""

import io
import os
import fitz  # PyMuPDF
import qrcode
import barcode
from barcode.writer import ImageWriter

# Map a short font key -> ttf file path. Drop real font files into /fonts and
# list them here for exact brand-font matching. Falls back to built-in Helvetica
# if the file isn't found, so this is fully optional.
FONTS_DIR = os.path.join(os.path.dirname(__file__), "..", "fonts")
FONTS = {
    "arial": os.path.join(FONTS_DIR, "arial.ttf"),
    "arial_bold": os.path.join(FONTS_DIR, "arialbd.ttf"),
    "tahoma": os.path.join(FONTS_DIR, "tahoma.ttf"),
    "helv_bold_oblique": os.path.join(FONTS_DIR, "Helvetica_Bold_Oblique.ttf"),
    "pepco_ovi": os.path.join(FONTS_DIR, "PEPCO_Ovi.ttf"),
}

# PyMuPDF built-in fonts — always available, no file needed
BUILTIN_FONTS = {
    "helv": "helv",        # Helvetica
    "hebo": "hebo",        # Helvetica-Bold
    "heit": "heit",        # Helvetica-Oblique
    "cour": "cour",        # Courier
    "tiro": "tiro",        # Times Roman
}


def _make_qr_image(data: str) -> bytes:
    img = qrcode.make(str(data))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_barcode_image(data: str, barcode_type: str = "code128", color_hex: str = "#000000",
                         guard_height_factor: float = 1.0, show_small_text: bool = False) -> bytes:
    data = str(data).strip()

    if barcode_type == "ean13":
        digits = "".join(ch for ch in data if ch.isdigit())
        if len(digits) >= 13:
            digits = digits[:12]
        elif len(digits) == 12:
            pass
        else:
            digits = digits.zfill(12)
        BARCODE_CLASS = barcode.get_barcode_class("ean13")
        code_input = digits
    else:
        BARCODE_CLASS = barcode.get_barcode_class("code128")
        code_input = data

    buf = io.BytesIO()
    writer = ImageWriter()
    # NOTE: options must be passed to write(), not just the writer constructor.
    # guard_height_factor (taller start/center/end guard bars, standard EAN13
    # look) only takes visual effect when write_text is True — the library ties
    # the guard-bar extension to the reserved text-baseline area.
    options = {
        "write_text": show_small_text,
        "quiet_zone": 1,
        "foreground": color_hex,
        "guard_height_factor": guard_height_factor,
        "font_size": 8,
        "text_distance": 3,
    }
    BARCODE_CLASS(code_input, writer=writer).write(buf, options)
    return buf.getvalue()


def _ean13_checksum(code12: str) -> int:
    total = 0
    for j, ch in enumerate(code12):
        weight = 1 if j % 2 == 0 else 3
        total += int(ch) * weight
    import math
    return math.ceil(total / 10) * 10 - total


# --- Exact EAN13 bar-position tables, ported 1:1 from the Illustrator JSX ---
_EAN_L = {
    "0": [3, 2, 6, 1], "1": [2, 2, 6, 1], "2": [2, 1, 5, 2], "3": [1, 4, 6, 1], "4": [1, 1, 5, 2],
    "5": [1, 2, 6, 1], "6": [1, 1, 3, 4], "7": [1, 3, 5, 2], "8": [1, 2, 4, 3], "9": [3, 1, 5, 2],
}
_EAN_G = {
    "0": [1, 1, 4, 3], "1": [1, 2, 5, 2], "2": [2, 2, 5, 2], "3": [1, 1, 6, 1], "4": [2, 3, 6, 1],
    "5": [1, 3, 6, 1], "6": [4, 1, 6, 1], "7": [2, 1, 6, 1], "8": [3, 1, 6, 1], "9": [2, 1, 4, 3],
}
_EAN_DICT_L = {
    "0": "LLLLLL", "1": "LLGLGG", "2": "LLGGLG", "3": "LLGGGL", "4": "LGLLGG",
    "5": "LGGLLG", "6": "LGGGLL", "7": "LGLGLG", "8": "LGLGGL", "9": "LGGLGL",
}
_EAN_DICT_R = {
    "sep": [1, 1, 3, 1],
    "0": [0, 3, 5, 1], "1": [0, 2, 4, 2], "2": [0, 2, 3, 2], "3": [0, 1, 5, 1], "4": [0, 1, 2, 3],
    "5": [0, 1, 3, 3], "6": [0, 1, 2, 1], "7": [0, 1, 4, 1], "8": [0, 1, 3, 1], "9": [0, 3, 4, 1],
}


def draw_ean13_vector(page, x0, y0, code13, target_width, color=(0, 0, 0),
                       height_ratio=0.168, block_ratio=0.00472, guard_extra=1.15):
    """
    Draw a 13-digit EAN13 barcode as real vector rectangles directly on the PDF
    page — same bar-position math as the Illustrator JSX (CreateBarcodeBars),
    so the proportions match exactly. Guard bars (start, center, end) render
    `guard_extra`x taller than the data bars, top-aligned at y0 (taller ones
    extend further down) — this is what makes it read as a proper EAN13
    symbol instead of a flat block of bars.

    x0, y0        = top-left of the barcode in PDF points (page coords)
    target_width  = desired total barcode width in points
    Returns (total_width_drawn, tall_bar_height) for layout purposes.
    """
    code13 = "".join(ch for ch in str(code13) if ch.isdigit())
    if len(code13) < 13:
        code13 = code13.zfill(12)
        code13 += str(_ean13_checksum(code13))
    code13 = code13[:13]

    height = target_width * height_ratio
    block = target_width * block_ratio
    gap_d = block * 7
    tall_h = height * guard_extra

    state = {"x": 0.0}

    def add_rect(x_off, w_mult, h):
        rx = x0 + state["x"] + block * x_off
        rw = block * w_mult
        if rw <= 0:
            return
        rect = fitz.Rect(rx, y0, rx + rw, y0 + h)
        page.draw_rect(rect, color=None, fill=color)

    def draw_sep(h):
        p = _EAN_DICT_R["sep"]
        add_rect(p[0], p[1], h)
        add_rect(p[2], p[3], h)

    def draw_right_digit(ch, h):
        p = _EAN_DICT_R[ch]
        add_rect(p[0], p[1], h)
        add_rect(p[2], p[3], h)

    def draw_left_group(content, h):
        pattern = _EAN_DICT_L[content[0]]
        for i in range(1, len(content)):
            lg = pattern[i - 1]
            params = _EAN_L[content[i]] if lg == "L" else _EAN_G[content[i]]
            add_rect(params[0], params[1], h)
            add_rect(params[2], params[3], h)
            state["x"] += gap_d

    draw_sep(tall_h)                              # start guard (tall)
    state["x"] += block * 4
    draw_left_group(code13[0:7], height)          # digits 1-6, normal height
    draw_sep(tall_h)                              # center guard (tall)
    state["x"] += block * 5
    for j in range(7, 12):                        # digits 7-11, normal height
        draw_right_digit(code13[j], height)
        state["x"] += gap_d
    draw_right_digit(code13[12], height)          # checksum digit, normal height
    state["x"] += block * 6
    draw_sep(tall_h)                              # end guard (tall)

    return state["x"], tall_h


def _clean(value):
    if value is None or (isinstance(value, float) and value != value):  # NaN
        return ""
    # pandas Timestamp / python datetime -> DD-MM-YYYY instead of raw "2026-08-16 00:00:00"
    if hasattr(value, "strftime"):
        return value.strftime("%d-%m-%Y")
    return str(value)


def expand_tc_barcode_variants(row: dict, max_variants: int = 7) -> list:
    """
    A single Excel row can carry several TC_Number_stN / Barcode_stN pairs
    (st1..st7) when one order covers several sizes on the same style/color.
    Each filled pair becomes its own output page — everything else in the
    row (Style, Colour, Product_name, qty, etc.) stays identical, only
    TC_Number_st1 / Barcode_st1 get overwritten per page so the existing
    single-variant field configs (which read TC_Number_st1/Barcode_st1) work
    unchanged. Returns a list of row dicts, one per page.
    Falls back to [row] unchanged if no stN pairs are filled at all (keeps
    plain single-TC rows working exactly as before).
    """
    variants = []
    for i in range(1, max_variants + 1):
        tc_val = row.get(f"TC_Number_st{i}")
        bc_val = row.get(f"Barcode_st{i}")
        if _clean(tc_val) or _clean(bc_val):
            new_row = dict(row)
            new_row["TC_Number_st1"] = tc_val
            new_row["Barcode_st1"] = bc_val
            variants.append(new_row)
    return variants if variants else [row]


def fill_single_label(template_path: str, row: dict, field_config: list) -> bytes:
    """Fill ONE label (one Excel row) onto a copy of the template. Returns PDF bytes."""
    doc = fitz.open(template_path)
    page = doc[0]

    for field in field_config:
        name = field.get("name")
        ftype = field.get("type", "text")

        # fixed_text needs no row lookup at all — it's a literal label the
        # template itself doesn't print (used for pad.pdf, which is fully blank).
        if ftype == "fixed_text":
            font_size = field.get("font_size", 8)
            color = field.get("color", [0, 0, 0])
            color = tuple(c / 255 if c > 1 else c for c in color)
            font_key = field.get("font", "helv")
            fontname = "helv"
            fontfile = None
            if font_key in FONTS and os.path.exists(FONTS[font_key]):
                fontname = font_key
                fontfile = FONTS[font_key]
            elif font_key in BUILTIN_FONTS:
                fontname = BUILTIN_FONTS[font_key]
            page.insert_text(
                (field["x"], field["y"]), field.get("text", ""), fontsize=font_size,
                color=color, fontname=fontname, fontfile=fontfile,
            )
            continue

        if name not in row:
            continue
        value = _clean(row[name])

        x, y = field["x"], field["y"]

        cover = field.get("cover")
        if cover:
            page.draw_rect(fitz.Rect(*cover), color=None, fill=(1, 1, 1))

        if ftype == "text":
            font_size = field.get("font_size", 8)
            color = field.get("color", [0, 0, 0])
            color = tuple(c / 255 if c > 1 else c for c in color)
            text_out = field.get("prefix", "") + value + field.get("suffix", "")

            font_key = field.get("font", "helv")
            fontname = "helv"
            fontfile = None
            if font_key in FONTS and os.path.exists(FONTS[font_key]):
                fontname = font_key
                fontfile = FONTS[font_key]
            elif font_key in BUILTIN_FONTS:
                fontname = BUILTIN_FONTS[font_key]

            # "align": "center" centers the text horizontally within a box.
            # Default box = [x, x+114] (the inner-label gray bar width) unless
            # the field gives its own "center_in": [x0, x1].
            align = field.get("align", "left")
            if align == "center":
                try:
                    font_obj = fitz.Font(fontfile=fontfile) if fontfile else fitz.Font(fontname)
                    text_width = font_obj.text_length(text_out, fontsize=font_size)
                except Exception:
                    text_width = fitz.get_text_length(text_out, fontname=fontname, fontsize=font_size)
                box_x0, box_x1 = field.get("center_in", [x, x + 114])
                x = box_x0 + ((box_x1 - box_x0) - text_width) / 2

            page.insert_text(
                (x, y), text_out, fontsize=font_size, color=color,
                fontname=fontname, fontfile=fontfile,
            )

        elif ftype == "qr":
            size = field.get("size", 60)
            img_bytes = _make_qr_image(value)
            page.insert_image(fitz.Rect(x, y, x + size, y + size), stream=img_bytes)

        elif ftype == "barcode":
            barcode_type = field.get("barcode_type", "code128")
            color = field.get("color", [0, 0, 0])
            color = tuple(c / 255 if c > 1 else c for c in color)

            if barcode_type == "ean13_vector":
                # Exact vector match to the Illustrator JSX — draws real bars,
                # not an image. width = total barcode width in points.
                w = field.get("width", 150)
                draw_ean13_vector(
                    page, x, y, value, w, color=color,
                    height_ratio=field.get("height_ratio", 0.168),
                    block_ratio=field.get("block_ratio", 0.00472),
                    guard_extra=field.get("guard_extra", 1.15),
                )
            else:
                w = field.get("width", 150)
                h = field.get("height", 40)
                color_hex = field.get("color_hex", "#000000")
                guard_height_factor = field.get("guard_height_factor", 1.0)
                show_small_text = field.get("show_small_text", False)
                img_bytes = _make_barcode_image(
                    value, barcode_type, color_hex, guard_height_factor, show_small_text
                )
                page.insert_image(fitz.Rect(x, y, x + w, y + h), stream=img_bytes)

    out = doc.tobytes()
    doc.close()
    return out


def compose_pdf_into_rect(base_doc, page_index, rect, source_pdf_bytes):
    """
    Place a whole generated single-page PDF (e.g. an already-filled Inner or
    Outer label) into a rectangle on another PDF's page — used to build the
    "pad" by compositing separately-generated Inner/Outer labels onto the
    blank pad template, rather than duplicating their field mappings.
    """
    page = base_doc[page_index]
    src_doc = fitz.open("pdf", source_pdf_bytes)
    page.show_pdf_page(rect, src_doc, 0)
    src_doc.close()


def generate_multipage_pdf(template_path: str, rows: list, field_config: list) -> bytes:
    """rows = list of dicts (each dict = one Excel row). Returns single merged multi-page PDF."""
    merged = fitz.open()
    for row in rows:
        single_bytes = fill_single_label(template_path, row, field_config)
        single_doc = fitz.open("pdf", single_bytes)
        merged.insert_pdf(single_doc)
        single_doc.close()
    out = merged.tobytes()
    merged.close()
    return out
