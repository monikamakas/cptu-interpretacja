import streamlit as st
import pandas as pd
from datetime import datetime

from extractor import extract_cpt
from excel_export import build_excel

st.set_page_config(page_title="CPTU → Excel", page_icon="📥", layout="centered")
st.title("📥 CPTU → Excel")
st.caption("Wrzuć kartę CPTU (PDF) – dostaniesz gotowy Excel z danymi i wykresami.")

uploaded = st.file_uploader("Karta CPTU (PDF)", type=["pdf"])

if uploaded is not None:
    with st.spinner("Czytam wykresy z PDF..."):
        try:
            df = extract_cpt(uploaded)
        except Exception as e:
            st.error(f"Nie udało się przetworzyć pliku: {e}")
            st.info("Najczęstsza przyczyna: PDF nie zawiera wektorowych wykresów, albo ma inny układ "
                     "paneli niż standardowy qc / fs / u2 / Rf(qc).")
            st.stop()

    st.success(f"Gotowe — odczytano {len(df)} wierszy, głębokość {df['Głębokość [m]'].min():.2f} "
               f"do {df['Głębokość [m]'].max():.2f} m.")

    tab1, tab2 = st.tabs(["Podgląd danych", "Podgląd wykresu"])
    with tab1:
        st.dataframe(df, use_container_width=True, height=400)
    with tab2:
        import plotly.graph_objects as go
        from plotly.subplots import make_subplots
        cols = ["qc [MPa]", "fs [MPa]", "u2 [MPa]", "Rf(qc) [%]"]
        colors = {"qc [MPa]": "blue", "fs [MPa]": "red", "u2 [MPa]": "maroon", "Rf(qc) [%]": "black"}
        fig = make_subplots(rows=1, cols=4, shared_yaxes=True, subplot_titles=cols)
        for i, c in enumerate(cols, start=1):
            fig.add_trace(go.Scatter(x=df[c], y=df["Głębokość [m]"], mode="lines",
                                      line=dict(color=colors[c]), name=c), row=1, col=i)
        fig.update_layout(height=600, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("Dane karty (opcjonalnie popraw przed eksportem)")
    c1, c2 = st.columns(2)
    test_number = c1.text_input("Numer testu", "")
    cone_number = c2.text_input("Nr stożka", "")
    c3, c4 = st.columns(2)
    date = c3.text_input("Data", "")
    investor = c4.text_input("Inwestor", "")

    meta = dict(test_number=test_number, cone_number=cone_number, date=date,
                investor=investor, source_file=uploaded.name)

    excel_bytes = build_excel(df, meta=meta)
    st.download_button(
        "⬇️ Pobierz Excel",
        data=excel_bytes,
        file_name=f"CPTU_{test_number or 'dane'}_{datetime.now().strftime('%Y%m%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
else:
    st.info("Czekam na plik PDF z kartą CPTU.")
