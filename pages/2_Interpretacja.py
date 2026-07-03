import io
import zipfile
from datetime import datetime

import streamlit as st
import pandas as pd

from extractor import extract_cpt
from gwl_estimate import estimate_gwl
from pdf_report import build_pdf_report

st.set_page_config(page_title="Interpretacja geotechniczna CPTU", page_icon="🧭", layout="wide")
st.title("🧭 Interpretacja geotechniczna CPTU")
st.caption("Wrzuć jedną lub kilka kart CPTU (PDF) – dostaniesz pełną interpretację wg Robertsona "
           "(klasyfikacja gruntu, warstwowanie, φ', Es, M, G0, Su, OCR, wodoprzepuszczalność) jako raport PDF.")

uploaded_files = st.file_uploader("Karty CPTU (PDF) – można wgrać kilka naraz", type=["pdf"],
                                    accept_multiple_files=True)


@st.cache_data(show_spinner=False)
def _extract(file_bytes, filename):
    df = extract_cpt(io.BytesIO(file_bytes), depth_negative=False)
    gwl_info = estimate_gwl(df)
    return df, gwl_info


if not uploaded_files:
    st.info("Czekam na przynajmniej jeden plik PDF z kartą CPTU.")
    st.stop()

reports = {}  # filename -> (pdf_bytes, profile, layers)

for i, uf in enumerate(uploaded_files):
    file_bytes = uf.getvalue()
    with st.expander(f"📄 {uf.name}", expanded=(len(uploaded_files) == 1)):
        try:
            with st.spinner("Czytam wykresy z PDF..."):
                raw_df, gwl_info = _extract(file_bytes, uf.name)
        except Exception as e:
            st.error(f"Nie udało się przetworzyć pliku: {e}")
            st.info("Najczęstsza przyczyna: PDF nie zawiera wektorowych wykresów, albo ma inny układ "
                     "paneli niż standardowy qc / fs / u2 / Rf(qc).")
            continue

        st.success(f"Odczytano {len(raw_df)} wierszy, głębokość do {raw_df['Głębokość [m]'].max():.2f} m.")

        st.markdown("**Dane karty**")
        c1, c2, c3, c4 = st.columns(4)
        test_number = c1.text_input("Numer testu", "", key=f"tn_{i}_{uf.name}")
        cone_number = c2.text_input("Nr stożka", "", key=f"cn_{i}_{uf.name}")
        date_str = c3.text_input("Data", "", key=f"dt_{i}_{uf.name}")
        investor = c4.text_input("Inwestor", "", key=f"inv_{i}_{uf.name}")

        st.markdown("**Założenia obliczeniowe** — sprawdź i popraw, jeśli znasz lepsze wartości")
        if gwl_info["ok"]:
            st.caption(f"💡 Automatyczne oszacowanie ZWG: {gwl_info['method']}")
            default_gwl = gwl_info["gwl"]
        else:
            st.warning(gwl_info["method"])
            default_gwl = 0.0

        c1, c2, c3, c4 = st.columns(4)
        gwl = c1.number_input("ZWG [m p.p.t.]", value=float(default_gwl), step=0.1,
                               key=f"gwl_{i}_{uf.name}",
                               help="Głębokość zwierciadła wody gruntowej. Ujemna wartość = powyżej "
                                    "poziomu odniesienia karty (np. gdy sondowanie wykonano spod wody).")
        area_ratio = c2.number_input("Współcz. powierzchni stożka (a)", value=0.80, min_value=0.5,
                                      max_value=1.0, step=0.01, key=f"a_{i}_{uf.name}")
        nkt = c3.number_input("Nkt (do Su)", value=15.0, min_value=10.0, max_value=20.0, step=0.5,
                               key=f"nkt_{i}_{uf.name}")
        min_thickness = c4.number_input("Min. miąższość warstwy [m]", value=1.0, min_value=0.2,
                                         max_value=3.0, step=0.1, key=f"mt_{i}_{uf.name}")

        c5, c6 = st.columns(2)
        shansep_s = c5.number_input("SHANSEP S (do OCR/σ'p)", value=0.22, min_value=0.10, max_value=0.50,
                                     step=0.01, key=f"s_{i}_{uf.name}",
                                     help="Typowa wartość literaturowa: 0,22 (Ladd 1991, gliny o niskiej-średniej "
                                          "wrażliwości). Bez badań laboratoryjnych z tej lokalizacji to orientacja.")
        shansep_m = c6.number_input("SHANSEP m (do OCR/σ'p)", value=0.80, min_value=0.10, max_value=1.00,
                                     step=0.01, key=f"m_{i}_{uf.name}",
                                     help="Typowa wartość literaturowa: 0,80 (Ladd 1991).")

        meta = dict(test_number=test_number, cone_number=cone_number, date=date_str,
                    investor=investor, source_file=uf.name)

        if st.button("🔄 Przelicz i pokaż podgląd", key=f"btn_{i}_{uf.name}"):
            with st.spinner("Liczę interpretację geotechniczną..."):
                pdf_buf, profile, layers = build_pdf_report(
                    raw_df, meta, gwl=gwl, gwl_method_note=gwl_info["method"],
                    area_ratio=area_ratio, nkt=nkt, min_thickness=min_thickness,
                    smooth_window=max(5, int(min_thickness * 25)),
                    shansep_s=shansep_s, shansep_m=shansep_m,
                )
                reports[uf.name] = (pdf_buf.getvalue(), profile, layers)
                st.session_state[f"report_{i}_{uf.name}"] = (pdf_buf.getvalue(), profile, layers)

        cached = st.session_state.get(f"report_{i}_{uf.name}")
        if cached:
            pdf_bytes, profile, layers = cached
            st.markdown(f"**Wykryto {len(layers)} warstw**")
            st.dataframe(
                layers[["Od [m]", "Do [m]", "Miąższość [m]", "Opis", "Uwaga"]],
                use_container_width=True, height=min(400, 40 + 35 * len(layers)),
            )
            st.download_button(
                "⬇️ Pobierz raport PDF",
                data=pdf_bytes,
                file_name=f"CPTU_{test_number or uf.name.replace('.pdf','')}_interpretacja.pdf",
                mime="application/pdf",
                key=f"dl_{i}_{uf.name}",
            )
            csv_bytes = profile.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Pobierz pełny profil (CSV)",
                data=csv_bytes,
                file_name=f"CPTU_{test_number or uf.name.replace('.pdf','')}_profil.csv",
                mime="text/csv",
                key=f"dlcsv_{i}_{uf.name}",
            )

# --- pobranie wszystkich naraz, jesli jest wiecej niz 1 plik i wszystkie przeliczone ---
all_ready = [uf.name for i, uf in enumerate(uploaded_files) if st.session_state.get(f"report_{i}_{uf.name}")]
if len(uploaded_files) > 1 and all_ready:
    st.divider()
    st.subheader("📦 Pobierz wszystkie naraz")
    if len(all_ready) < len(uploaded_files):
        st.caption(f"Gotowe: {len(all_ready)} z {len(uploaded_files)} kart — przelicz pozostałe, "
                   "żeby dodać je do paczki ZIP.")
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for i, f in enumerate(uploaded_files):
            cached = st.session_state.get(f"report_{i}_{f.name}")
            if not cached:
                continue
            pdf_bytes, profile, layers = cached
            base = f.name.replace(".pdf", "")
            zf.writestr(f"{base}_interpretacja.pdf", pdf_bytes)
            zf.writestr(f"{base}_profil.csv", profile.to_csv(index=False))
    zip_buf.seek(0)
    st.download_button(
        "⬇️ Pobierz paczkę ZIP (wszystkie gotowe raporty)",
        data=zip_buf,
        file_name=f"CPTU_interpretacje_{datetime.now().strftime('%Y%m%d')}.zip",
        mime="application/zip",
    )
