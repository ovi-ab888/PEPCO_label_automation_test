import sys
import os
sys.path.append(os.path.dirname(__file__))

import pandas as pd
import streamlit as st
import fitz

from labels.inner_label import generate_single, generate_batch

st.set_page_config(page_title="Inner Label Generator", layout="centered")
st.title("🏷️ Inner Label Generator (70mm x 50mm)")
st.caption("Step 1: Inner label only. Outer label will be added as a separate step.")

excel_file = st.file_uploader("Upload Excel data", type=["xlsx", "xls"])
if not excel_file:
    st.info("Upload an Excel file to continue (or use data/sample_data.xlsx to test).")
    st.stop()

df = pd.read_excel(excel_file)
st.success(f"Loaded {len(df)} rows")
st.dataframe(df, use_container_width=True)

st.subheader("👁️ Preview (row 1)")
first_row = df.iloc[0].to_dict()
preview_bytes = generate_single(first_row)
doc = fitz.open("pdf", preview_bytes)
pix = doc[0].get_pixmap(matrix=fitz.Matrix(4, 4))
st.image(pix.tobytes("png"), width=450)
doc.close()

st.subheader("🚀 Generate All Inner Labels")
if st.button("Generate PDF", type="primary"):
    rows = df.to_dict(orient="records")
    with st.spinner(f"Generating {len(rows)} inner labels..."):
        final_pdf = generate_batch(rows)
    st.success(f"Done — {len(rows)} inner labels generated.")
    st.download_button(
        "⬇️ Download Inner Labels PDF",
        data=final_pdf,
        file_name="inner_labels.pdf",
        mime="application/pdf",
    )

