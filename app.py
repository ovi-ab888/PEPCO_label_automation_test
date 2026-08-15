import sys
import os
sys.path.append(os.path.dirname(__file__))

import json
import pandas as pd
import streamlit as st
import fitz

from engine.label_engine import fill_single_label, generate_multipage_pdf, compose_pdf_into_rect
import labels.inner_label as inner_label
import labels.outer_label as outer_label
import labels.pad_label as pad_label

st.set_page_config(page_title="PEPCO Label Automation", layout="wide")
st.title("🏷️ PEPCO Label Automation")

MODES = {
    "Inner (70x50mm)": inner_label,
    "Outer (100x100mm)": outer_label,
    "Pad (full sheet)": pad_label,
}
mode_name = st.radio("Choose what to generate", list(MODES.keys()), horizontal=True)
mod = MODES[mode_name]
TEMPLATE_PATH = mod.TEMPLATE_PATH
CONFIG_PATH = mod.CONFIG_PATH
load_field_config = mod.load_field_config

st.caption(f"Template: `{os.path.relpath(TEMPLATE_PATH)}`  |  Config: `{os.path.relpath(CONFIG_PATH)}`")

excel_file = st.file_uploader("Upload Excel data", type=["xlsx", "xls"], key=f"upload_{mode_name}")
if not excel_file:
    st.info("Upload an Excel file to continue (or use data/sample_data.xlsx to test).")
    st.stop()

df = pd.read_excel(excel_file)
st.success(f"Loaded {len(df)} rows")
with st.expander("📋 Excel data preview"):
    st.dataframe(df, use_container_width=True)

first_row = df.iloc[0].to_dict()

# ---------------- Live field position / font size editor ----------------
st.subheader("🎛️ Adjust position & font size")
st.caption("x, y = position in points (top-left origin). font_size in points. "
           "Change a value → preview updates instantly below. "
           "fixed_text rows (labels the template itself doesn't print, e.g. pad's 'ITEM') "
           "are shown read-only here — edit their x/y directly in the JSON if needed.")

state_key = f"field_config_{mode_name}"
if state_key not in st.session_state:
    st.session_state[state_key] = load_field_config()

FONT_OPTIONS = ["helv", "hebo", "heit", "cour", "tiro",
                "arial", "arial_bold", "tahoma",
                "helv_bold_oblique", "pepco_ovi"]

editable_rows = []
for f in st.session_state[state_key]:
    editable_rows.append({
        "name": f.get("name", f.get("text", "(fixed)")),
        "type": f.get("type", "text"),
        "x": float(f.get("x", 0)),
        "y": float(f.get("y", 0)),
        "font_size": float(f.get("font_size", 8)),
        "font": f.get("font", "helv"),
        "prefix": f.get("prefix", ""),
    })
edit_df = pd.DataFrame(editable_rows)

edited = st.data_editor(
    edit_df,
    use_container_width=True,
    disabled=["name", "type"],
    hide_index=True,
    key=f"field_editor_{mode_name}",
    column_config={
        "x": st.column_config.NumberColumn(step=1.0),
        "y": st.column_config.NumberColumn(step=1.0),
        "font_size": st.column_config.NumberColumn(step=0.5, min_value=1.0),
        "font": st.column_config.SelectboxColumn(
            options=FONT_OPTIONS,
            help="helv=Helvetica, hebo=Helvetica-Bold, heit=Helvetica-Italic, "
                 "cour=Courier, tiro=Times. arial/arial_bold/tahoma/helv_bold_oblique/"
                 "pepco_ovi need a matching .ttf file in /fonts.",
        ),
    },
)

new_config = []
for original, (_, row) in zip(st.session_state[state_key], edited.iterrows()):
    updated = dict(original)
    updated["x"] = float(row["x"])
    updated["y"] = float(row["y"])
    if updated.get("type") in ("text", "fixed_text"):
        updated["font_size"] = float(row["font_size"])
        updated["font"] = row["font"]
        if updated.get("type") == "text":
            updated["prefix"] = row["prefix"]
    new_config.append(updated)
st.session_state[state_key] = new_config

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "💾 Download updated field_mapping.json",
        data=json.dumps(new_config, indent=2),
        file_name=os.path.basename(CONFIG_PATH),
        mime="application/json",
    )
with col2:
    st.caption(f"⬆️ Download this and replace `{os.path.relpath(CONFIG_PATH)}` "
               "in your GitHub repo to make changes permanent.")

# ---------------- Live preview ----------------
st.subheader("👁️ Live Preview (row 1)")
if mode_name == "Pad (full sheet)":
    st.caption("Pad composes the separately-generated Inner + Outer labels onto the blank "
               "pad template — it always uses their last-saved configs. Edit Inner/Outer "
               "position on their own tabs; edit header fields (Order ID, Item, Style Code, "
               "Color) right here.")
    # header fields use the live-edited config; inner/outer come from their saved configs
    header_pdf = fill_single_label(TEMPLATE_PATH, first_row, new_config)
    doc = fitz.open("pdf", header_pdf)
    inner_bytes = inner_label.generate_single(first_row)
    outer_bytes = outer_label.generate_single(first_row)
    compose_pdf_into_rect(doc, 0, pad_label.INNER_RECT, inner_bytes)
    compose_pdf_into_rect(doc, 0, pad_label.OUTER_RECT, outer_bytes)
    preview_bytes = doc.tobytes()
    doc.close()
else:
    preview_bytes = fill_single_label(TEMPLATE_PATH, first_row, new_config)
    doc = fitz.open("pdf", preview_bytes)

doc = fitz.open("pdf", preview_bytes)
zoom = 5 if mode_name != "Pad (full sheet)" else 2
pix = doc[0].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
st.image(pix.tobytes("png"), width=550 if mode_name != "Pad (full sheet)" else 900)
doc.close()

# ---------------- Generate all ----------------
st.subheader(f"🚀 Generate All ({mode_name})")
if st.button("Generate PDF", type="primary", key=f"generate_{mode_name}"):
    rows = df.to_dict(orient="records")
    with st.spinner(f"Generating {len(rows)} labels..."):
        if mode_name == "Pad (full sheet)":
            # save the live-edited header config first so the batch run picks it up
            with open(CONFIG_PATH, "w") as f:
                json.dump(new_config, f, indent=2)
            final_pdf = pad_label.generate_batch(rows)
        else:
            final_pdf = generate_multipage_pdf(TEMPLATE_PATH, rows, new_config)
    st.success(f"Done — {len(rows)} labels generated.")
    st.download_button(
        "⬇️ Download PDF",
        data=final_pdf,
        file_name=f"{mode_name.split()[0].lower()}_labels.pdf",
        mime="application/pdf",
    )
