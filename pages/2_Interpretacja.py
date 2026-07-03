import io
import zipfile
from datetime import datetime

import streamlit as st
import pandas as pd

from extractor import extract_all_soundings
from gwl_estimate import estimate_gwl
from pdf_report import build_pdf_report

st.set_page_config(page_title="Interpretacja geotechniczna CPTU", page_icon="🧭", layout="wide")
st.title("🧭 Interpretacja geotechniczna CPTU")
st.caption("Wrzuć jedną lub kilka kart CPTU (PDF) – dostaniesz pełną interpretację wg Robertsona "
           "(klasyfikacja gruntu, warstwowanie, φ', Es, M, G0, Su, OCR, wodoprzepuszczalność) jako raport PDF. "
           "Obsługuje też pliki zbiorcze, gdzie każda strona to osobne sondowanie.")

uploaded_files = st.file_uploader("Karty CPTU (PDF) – można wgrać kilka naraz", type=["pdf"],
                                    accept_multiple_files=True)


@st.cache_data(show_spinner=False)
def _extract_all(file_bytes, filename):
    """Zwraca listę sondowań znalezionych w pliku: [{test_id, df, page, error, gwl_info}, ...]"""
    results = extract_all_soundings(io.BytesIO(file_bytes), depth_negative=False)
    for r in results:
        if r["df"] is not None:
            r["gwl_info"] = estimate_gwl(r["df"])
        else:
            r["gwl_info"] = None
    return results


if not uploaded_files:
    st.info("Czekam na przynajmniej jeden plik PDF z kartą CPTU.")
    st.stop()

# zbierz wszystkie sondowania ze wszystkich plików w jedną płaską listę,
# każde z unikalnym kluczem (nazwa pliku + numer strony)
all_soundings = []  # (key, file_label, sounding_dict)
for uf in uploaded_files:
    file_bytes = uf.getvalue()
    with st.spinner(f"Czytam {uf.name}..."):
        try:
            results = _extract_all(file_bytes, uf.name)
        except Exception as e:
            st.error(f"Nie udało się otworzyć pliku {uf.name}: {e}")
            continue
    multi = len(results) > 1
    for r in results:
        label = f"{uf.name} — {r['test_id']}" if multi else uf.name
        key = f"{uf.name}__p{r['page']}"
        all_soundings.append((key, label, r))

if not all_soundings:
    st.warning("Nie znaleziono żadnego sondowania w wgranych plikach.")
    st.stop()

st.success(f"Znaleziono {len(all_soundings)} sondowań w {len(uploaded_files)} pliku(-ach).")

for key, label, r in all_soundings:
    with st.expander(f"📄 {label}", expanded=(len(all_soundings) == 1)):
        if r["error"] or r["df"] is None:
            st.error(f"Nie udało się przetworzyć: {r['error']}")
            st.info("Najczęstsza przyczyna: PDF nie zawiera wektorowych wykresów, albo ma inny układ "
                     "paneli niż standardowy qc / fs / u2 / Rf(qc).")
            continue

        raw_df = r["df"]
        gwl_info = r["gwl_info"]
        st.success(f"Odczytano {len(raw_df)} wierszy, głębokość do {raw_df['Głębokość [m]'].max():.2f} m.")

        st.markdown("**Dane karty**")
        c1, c2, c3, c4 = st.columns(4)
        default_test_number = r["test_id"] if not r["test_id"].startswith("strona") else ""
        test_number = c1.text_input("Numer testu", default_test_number, key=f"tn_{key}")
        cone_number = c2.text_input("Nr stożka", "", key=f"cn_{key}")
        date_str = c3.text_input("Data", "", key=f"dt_{key}")
        investor = c4.text_input("Inwestor", "", key=f"inv_{key}")

        st.markdown("**Założenia obliczeniowe** — sprawdź i popraw, jeśli znasz lepsze wartości")
        if gwl_info["ok"]:
            st.caption(f"💡 Automatyczne oszacowanie ZWG: {gwl_info['method']}")
            default_gwl = gwl_info["gwl"]
        else:
            st.warning(gwl_info["method"])
            default_gwl = 0.0

        c1, c2, c3, c4 = st.columns(4)
        gwl = c1.number_input("ZWG [m p.p.t.]", value=float(default_gwl), step=0.1,
                               key=f"gwl_{key}",
                               help="Głębokość zwierciadła wody gruntowej. Ujemna wartość = powyżej "
                                    "poziomu odniesienia karty (np. gdy sondowanie wykonano spod wody).")
        area_ratio = c2.number_input("Współcz. powierzchni stożka (a)", value=0.80, min_value=0.5,
                                      max_value=1.0, step=0.01, key=f"a_{key}")
        nkt = c3.number_input("Nkt (do Su)", value=15.0, min_value=10.0, max_value=20.0, step=0.5,
                               key=f"nkt_{key}")
        min_thickness = c4.number_input("Min. miąższość warstwy [m]", value=1.0, min_value=0.2,
                                         max_value=3.0, step=0.1, key=f"mt_{key}")

        c5, c6 = st.columns(2)
        shansep_s = c5.number_input("SHANSEP S (do OCR/σ'p)", value=0.22, min_value=0.10, max_value=0.50,
                                     step=0.01, key=f"s_{key}",
                                     help="Typowa wartość literaturowa: 0,22 (Ladd 1991, gliny o niskiej-średniej "
                                          "wrażliwości). Bez badań laboratoryjnych z tej lokalizacji to orientacja.")
        shansep_m = c6.number_input("SHANSEP m (do OCR/σ'p)", value=0.80, min_value=0.10, max_value=1.00,
                                     step=0.01, key=f"m_{key}",
                                     help="Typowa wartość literaturowa: 0,80 (Ladd 1991).")

        meta = dict(test_number=test_number, cone_number=cone_number, date=date_str,
                    investor=investor, source_file=label)

        if st.button("🔄 Przelicz i pokaż podgląd", key=f"btn_{key}"):
            with st.spinner("Liczę interpretację geotechniczną..."):
                pdf_buf, profile, layers = build_pdf_report(
                    raw_df, meta, gwl=gwl, gwl_method_note=gwl_info["method"],
                    area_ratio=area_ratio, nkt=nkt, min_thickness=min_thickness,
                    smooth_window=max(5, int(min_thickness * 25)),
                    shansep_s=shansep_s, shansep_m=shansep_m,
                )
                st.session_state[f"report_{key}"] = (pdf_buf.getvalue(), profile, layers)

        cached = st.session_state.get(f"report_{key}")
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
                file_name=f"CPTU_{test_number or key}_interpretacja.pdf",
                mime="application/pdf",
                key=f"dl_{key}",
            )
            csv_bytes = profile.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Pobierz pełny profil (CSV)",
                data=csv_bytes,
                file_name=f"CPTU_{test_number or key}_profil.csv",
                mime="text/csv",
                key=f"dlcsv_{key}",
            )

# --- pobranie wszystkich naraz, jesli jest wiecej niz 1 sondowanie i wszystkie przeliczone ---
all_ready = [key for key, _, _ in all_soundings if st.session_state.get(f"report_{key}")]
if len(all_soundings) > 1 and all_ready:
    st.divider()
    st.subheader("📦 Pobierz wszystkie naraz")
    if len(all_ready) < len(all_soundings):
        st.caption(f"Gotowe: {len(all_ready)} z {len(all_soundings)} sondowań — przelicz pozostałe, "
                   "żeby dodać je do paczki ZIP.")
    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w") as zf:
        for key, label, r in all_soundings:
            cached = st.session_state.get(f"report_{key}")
            if not cached:
                continue
            pdf_bytes, profile, layers = cached
            base = key.replace(".pdf", "").replace("__p", "_str")
            zf.writestr(f"{base}_interpretacja.pdf", pdf_bytes)
            zf.writestr(f"{base}_profil.csv", profile.to_csv(index=False))
    zip_buf.seek(0)
    st.download_button(
        "⬇️ Pobierz paczkę ZIP (wszystkie gotowe raporty)",
        data=zip_buf,
        file_name=f"CPTU_interpretacje_{datetime.now().strftime('%Y%m%d')}.zip",
        mime="application/zip",
    )
