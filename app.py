import sys
import os
sys.path.append(os.path.dirname(__file__))

import json
import pandas as pd
import streamlit as st
import fitz

from engine.label_engine import fill_single_label, generate_multipage_pdf
import labels.inner_label as inner_mod
import labels.outer_label as outer_mod

st.set_page_config(page_title="PEPCO Label Generator", layout="wide")

# ---------------- Sidebar Navigation ----------------
st.sidebar.title("🏷️ PEPCO Label Mode")
label_mode = st.sidebar.radio("Select Label Type:", ["Inner Label (70x50mm)", "Outer Label (100x100mm)"])

if label_mode == "Inner Label (70x50mm)":
    st.title("🏷️ Inner Label Generator (70mm x 50mm)")
    TEMPLATE_PATH = inner_mod.TEMPLATE_PATH
    load_config_fn = inner_mod.load_field_config
    session_key = "inner_field_config"
    json_filename = "inner_field_mapping.json"
else:
    st.title("📦 Outer Label Generator (100mm x 100mm)")
    TEMPLATE_PATH = outer_mod.TEMPLATE_PATH
    load_config_fn = outer_mod.load_field_config
    session_key = "outer_field_config"
    json_filename = "outer_field_mapping.json"

# ---------------- Excel Upload ----------------
excel_file = st.file_uploader("Upload Excel data", type=["xlsx", "xls"])
if not excel_file:
    st.info("Upload an Excel file to continue (or use data/sample_data.xlsx to test).")
    st.stop()

df = pd.read_excel(excel_file)
st.success(f"Loaded {len(df)} rows")
with st.expander("📋 Excel data preview"):
    st.dataframe(df, use_container_width=True)

first_row = df.iloc[0].to_dict()

# ---------------- Live field editor ----------------
st.subheader("🎛️ Adjust position & font size")
st.caption("x, y = position in points (top-left origin). font_size in points. "
           "Change a value → preview updates instantly below.")

if session_key not in st.session_state:
    st.session_state[session_key] = load_config_fn()

FONT_OPTIONS = ["helv", "hebo", "heit", "cour", "tiro",
                "arial", "arial_bold", "tahoma",
                "helv_bold_oblique", "pepco_ovi"]

editable_rows = []
for f in st.session_state[session_key]:
    editable_rows.append({
        "name": f["name"],
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
    key=f"field_editor_{label_mode}",
    column_config={
        "x": st.column_config.NumberColumn(step=1.0),
        "y": st.column_config.NumberColumn(step=1.0),
        "font_size": st.column_config.NumberColumn(step=0.5, min_value=1.0),
        "font": st.column_config.SelectboxColumn(options=FONT_OPTIONS),
    },
)

# Merge edits
new_config = []
for original, (_, row) in zip(st.session_state[session_key], edited.iterrows()):
    updated = dict(original)
    updated["x"] = float(row["x"])
    updated["y"] = float(row["y"])
    if updated.get("type") == "text":
        updated["font_size"] = float(row["font_size"])
        updated["font"] = row["font"]
        updated["prefix"] = row["prefix"]
    new_config.append(updated)
st.session_state[session_key] = new_config

col1, col2 = st.columns(2)
with col1:
    st.download_button(
        f"💾 Download updated {json_filename}",
        data=json.dumps(new_config, indent=2),
        file_name=json_filename,
        mime="application/json",
    )
with col2:
    st.caption(f"⬆️ Download this and replace `config/{json_filename}` in your repo.")

# ---------------- Live preview ----------------
st.subheader("👁️ Live Preview (row 1)")
preview_bytes = fill_single_label(TEMPLATE_PATH, first_row, new_config)
doc = fitz.open("pdf", preview_bytes)
pix = doc[0].get_pixmap(matrix=fitz.Matrix(4, 4))
st.image(pix.tobytes("png"), width=450)
doc.close()

# ---------------- Generate all ----------------
st.subheader(f"🚀 Generate All {label_mode}s")
if st.button("Generate PDF", type="primary"):
    rows = df.to_dict(orient="records")
    with st.spinner(f"Generating {len(rows)} labels..."):
        final_pdf = generate_multipage_pdf(TEMPLATE_PATH, rows, new_config)
    st.success(f"Done — {len(rows)} labels generated.")
    st.download_button(
        "⬇️ Download Labels PDF",
        data=final_pdf,
        file_name=f"{'outer' if 'Outer' in label_mode else 'inner'}_labels.pdf",
        mime="application/pdf",
    )
