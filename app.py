import sys
import os
sys.path.append(os.path.dirname(__file__))

import json
import pandas as pd
import streamlit as st
import fitz

from engine.label_engine import fill_single_label, generate_multipage_pdf
from labels.inner_label import TEMPLATE_PATH, CONFIG_PATH, load_field_config

st.set_page_config(page_title="Inner Label Generator", layout="wide")
st.title("🏷️ Inner Label Generator (70mm x 50mm)")
st.caption("Step 1: Inner label only. Outer label will be added as a separate step.")

excel_file = st.file_uploader("Upload Excel data", type=["xlsx", "xls"])
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
           "Change a value → preview updates instantly below.")

if "field_config" not in st.session_state:
    st.session_state.field_config = load_field_config()

# Only text/barcode fields are editable here (cover stays as configured)
FONT_OPTIONS = ["helv", "hebo", "heit", "cour", "tiro",
                "arial", "arial_bold", "tahoma",
                "helv_bold_oblique", "pepco_ovi"]

editable_rows = []
for f in st.session_state.field_config:
    editable_rows.append({
        "name": f["name"],
        "type": f.get("type", "text"),
        "x": f.get("x", 0),
        "y": f.get("y", 0),
        "font_size": f.get("font_size", ""),
        "font": f.get("font", "helv"),
        "prefix": f.get("prefix", ""),
    })
edit_df = pd.DataFrame(editable_rows)

edited = st.data_editor(
    edit_df,
    use_container_width=True,
    disabled=["name", "type"],  # name/type stay fixed, only position/size/font editable
    hide_index=True,
    key="field_editor",
    column_config={
        "font": st.column_config.SelectboxColumn(
            options=FONT_OPTIONS,
            help="helv=Helvetica, hebo=Helvetica-Bold, heit=Helvetica-Italic, "
                 "cour=Courier, tiro=Times. arial/arial_bold/tahoma need a .ttf "
                 "file in /fonts (falls back to helv if missing).",
        ),
    },
)

# merge edits back into full field_config (keep cover/width/height untouched)
new_config = []
for original, (_, row) in zip(st.session_state.field_config, edited.iterrows()):
    updated = dict(original)
    updated["x"] = float(row["x"])
    updated["y"] = float(row["y"])
    if updated.get("type") == "text":
        updated["font_size"] = float(row["font_size"]) if row["font_size"] != "" else 8
        updated["font"] = row["font"]
        updated["prefix"] = row["prefix"]
    new_config.append(updated)
st.session_state.field_config = new_config

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        "💾 Download updated field_mapping.json",
        data=json.dumps(new_config, indent=2),
        file_name="inner_field_mapping.json",
        mime="application/json",
    )
with col2:
    st.caption("⬆️ Download this and replace `config/inner_field_mapping.json` "
               "in your GitHub repo to make changes permanent.")

# ---------------- Live preview ----------------
st.subheader("👁️ Live Preview (row 1)")
preview_bytes = fill_single_label(TEMPLATE_PATH, first_row, new_config)
doc = fitz.open("pdf", preview_bytes)
pix = doc[0].get_pixmap(matrix=fitz.Matrix(5, 5))
st.image(pix.tobytes("png"), width=550)
doc.close()

# ---------------- Generate all ----------------
st.subheader("🚀 Generate All Inner Labels")
if st.button("Generate PDF", type="primary"):
    rows = df.to_dict(orient="records")
    with st.spinner(f"Generating {len(rows)} inner labels..."):
        final_pdf = generate_multipage_pdf(TEMPLATE_PATH, rows, new_config)
    st.success(f"Done — {len(rows)} inner labels generated.")
    st.download_button(
        "⬇️ Download Inner Labels PDF",
        data=final_pdf,
        file_name="inner_labels.pdf",
        mime="application/pdf",
    )
