import streamlit as st

st.set_page_config(page_title="CPTU – narzędzia", page_icon="📊", layout="centered")

st.title("📊 CPTU – narzędzia")
st.caption("Wrzuć kartę (lub kilka kart) CPTU – wybierz, co chcesz zrobić z danymi.")

col1, col2 = st.columns(2)
with col1:
    st.subheader("📥 Eksport do Excel")
    st.write("Dane z wykresów (qc, fs, u2, Rf) trafiają do gotowego pliku Excel z wykresami "
             "(głębokość ujemna – wygląda jak karta PDF).")
    st.page_link("pages/1_Excel.py", label="Przejdź do eksportu →", icon="📥")
with col2:
    st.subheader("🧭 Interpretacja geotechniczna")
    st.write("Pełna interpretacja wg Robertsona: klasyfikacja gruntu, warstwowanie, "
             "φ', Es, M, G0, Su, OCR, wodoprzepuszczalność – gotowy raport PDF.")
    st.page_link("pages/2_Interpretacja.py", label="Przejdź do interpretacji →", icon="🧭")

st.divider()
st.caption("Obsługiwane pliki: karty CPTU PDF z wektorowymi wykresami (np. z programu CPT-Star).")
