# CPTU – narzędzia

Apka webowa (Streamlit) do pracy z kartami CPTU (PDF):

1. **📥 Eksport do Excel** – dane z wykresów (qc, fs, u2, Rf) trafiają do gotowego
   pliku Excel z prawdziwymi wykresami (głębokość ujemna – wygląda jak karta PDF).
2. **🧭 Interpretacja geotechniczna** – pełna interpretacja wg Robertsona (CPT Guide,
   6th ed., 2015) i Kulhawy'ego & Mayne'a (1990): klasyfikacja gruntu (Ic/SBTn),
   warstwowanie, ciężar objętościowy, φ', Dr, Es, moduł edometryczny M, G0, N60,
   Su, OCR (dwie metody), wodoprzepuszczalność k – jako gotowy raport PDF.
   Obsługuje wgranie kilku kart CPTU naraz.

## Jak to wystawić "na świat" (jednorazowo, ~10 minut)

### 1. Wrzuć te pliki na GitHub
1. Wejdź na [github.com/new](https://github.com/new)
2. Nazwa repozytorium: `cptu-interpretacja`, ustaw jako **Public**
3. Wrzuć **całą zawartość tego folderu**, zachowując strukturę:
   ```
   app.py
   extractor.py
   calc.py
   layering.py
   plotting.py
   gwl_estimate.py
   pdf_report.py
   excel_export.py
   requirements.txt
   fonts/DejaVuSans.ttf
   fonts/DejaVuSans-Bold.ttf
   pages/1_Excel.py
   pages/2_Interpretacja.py
   ```
   Foldery `fonts/` i `pages/` muszą zostać zachowane (nie spłaszczaj struktury) –
   Streamlit rozpoznaje `pages/` automatycznie jako osobne zakładki, a `fonts/`
   zawiera czcionkę do polskich znaków w PDF (żeby nie zależeć od czcionek
   systemowych serwera).
4. Commit changes

### 2. Wystaw apkę na Streamlit Community Cloud
1. [share.streamlit.io](https://share.streamlit.io) → zaloguj się przez GitHub
2. **New app** → repo `cptu-interpretacja`, branch `main`, plik główny: `app.py`
3. **Deploy**

Po 1-2 minutach dostajesz link `https://cptu-interpretacja-xxxxx.streamlit.app`
do wysłania dalej.

### Aktualizacje
Podmiana plików na GitHubie → Streamlit Cloud przeładowuje apkę automatycznie.

## Struktura projektu

- `extractor.py` – silnik czytający wektorowe wykresy z PDF (wspólny dla obu funkcji)
- `calc.py` – korelacje geotechniczne (Ic, SBTn, γ, φ', Dr, Es, M, G0, Su, OCR, k)
- `layering.py` – automatyczny, "bezpieczny" podział na warstwy (chroni cienkie,
  kontrastowe przekładki przed scaleniem)
- `plotting.py` – wykres profilu interpretacyjnego (6 paneli, głębokość ujemna)
- `gwl_estimate.py` – automatyczne szacowanie ZWG z u2 w płytkim piasku
- `pdf_report.py` – budowa raportu PDF (strona tytułowa z założeniami, wykres,
  tabela warstw, metodyka/wzory, ograniczenia)
- `excel_export.py` – budowa pliku Excel z danymi i wykresami
- `pages/1_Excel.py`, `pages/2_Interpretacja.py` – ekrany apki

## Założenia edytowalne w apce (na kartę CPTU)

- **ZWG** – domyślnie szacowane automatycznie z u2 w płytkim piasku, zawsze do
  ręcznej korekty
- **Współczynnik powierzchni stożka (a)** – domyślnie 0,80
- **Nkt** (do wyznaczenia Su) – domyślnie 15
- **Minimalna miąższość warstwy** – domyślnie 1,0 m (cienkie, kontrastowe warstwy
  i tak nie są scalane – patrz `layering.py`)

## Ograniczenia (aktualny stan)

- Zakłada standardowy układ 4 paneli qc/fs/u2/Rf(qc) w karcie PDF (jak generuje
  CPT-Star)
- Nie obsługuje jeszcze wgrywania wyników badań laboratoryjnych (planowane
  w kolejnym etapie)
- Klasyfikacja Ic/SBTn jest wiarygodna (>80% zgodności wg literatury), ale
  bezwzględne wartości Su/OCR/φ' bez lokalnej kalibracji są orientacyjne –
  raport PDF jasno to opisuje na stronie tytułowej
