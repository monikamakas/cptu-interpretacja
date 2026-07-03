# STATUS.md — stan projektu cptu-interpretacja

Aktualizowane na bieżąco. Wklej ten plik na start nowej rozmowy z Claude, żeby kontynuować bez powtarzania historii.

## Co to jest

Apka webowa (Streamlit), repo GitHub: **cptu-interpretacja**, wdrożona na Streamlit
Community Cloud. Dwie funkcje:
1. **Eksport do Excel** – karta CPTU (PDF) → dane + wykresy w Excelu
2. **Interpretacja geotechniczna** – karta CPTU (PDF) → pełna interpretacja wg
   Robertsona (klasyfikacja gruntu, warstwowanie, φ', Es, M, G0, Su, OCR, k) → raport PDF

Obsługuje wgranie **kilku kart CPTU naraz** (batch + ZIP z wynikami).

## Struktura repo

```
app.py                      # strona startowa
pages/1_Excel.py            # eksport do Excel
pages/2_Interpretacja.py    # interpretacja geotechniczna (multi-upload)
extractor.py                # silnik: czyta wektorowe wykresy z PDF
calc.py                     # korelacje geotechniczne (Robertson, Kulhawy-Mayne)
layering.py                 # automatyczny, "bezpieczny" podział na warstwy
plotting.py                 # wykres profilu interpretacyjnego (6 paneli)
gwl_estimate.py             # automatyczne szacowanie ZWG z u2
pdf_report.py                # budowa raportu PDF
excel_export.py             # budowa Excela z wykresami
fonts/DejaVuSans*.ttf       # czcionka do PDF (polskie znaki, niezależna od serwera)
requirements.txt
```

## Kluczowe decyzje projektowe

- **Metodyka**: CPT Guide 6th ed. (Robertson, 2015) + Kulhawy & Mayne (1990).
  Ic/SBTn iteracyjnie ze zmiennym wykładnikiem n (Robertson 2009).
- **Głębokość zawsze ujemna** w wykresach/Excelu (0 na górze, rośnie w dół – jak
  oryginalna karta PDF).
- **Rozpoznawanie krzywych po KOLORZE, nie po pozycji panelu** (niebieski=qc,
  czerwony=fs, bordowy=u2, czarny=Rf) – różne programy CPT mają różną kolejność
  paneli, ale kolor jest uniwersalny.
- **ZWG szacowane automatycznie** z u2 w płytkiej, czystej warstwie piaszczystej
  (tam nadciśnienie penetracji szybko dysypuje, więc u2 ≈ ciśnienie hydrostatyczne).
  Zawsze pokazywane jako **edytowalne** pole w apce – auto-szacowanie to punkt
  startowy, nie wyrocznia.
- **Domyślne założenia (edytowalne w apce)**: współczynnik powierzchni stożka
  a=0,80; Nkt=15 (zakres 14–16); min. miąższość warstwy 1,0 m; SHANSEP S=0,22,
  m=0,80 (Ladd 1991 – bez lokalnej kalibracji to orientacja, literatura pokazuje
  S: 0,16–0,48, m: 0,12–0,91 wg rodzaju gruntu).
- **Trzy niezależne metody OCR/σ'p do porównania**: Robertson (2009), Kulhawy-Mayne
  (1990), SHANSEP (Ladd i Foott, 1974: OCR=(su/(S·σ'v0))^(1/m)). Naprężenie
  prekonsolidacji σ'p = σ'v0·OCR liczone dla każdej metody.
- **K0 dwoma metodami**: Jaky (1944, NC) K0=1−sinφ' – dotyczy wszystkich gruntów;
  Kulhawy-Mayne (OC, uwzględnia przekonsolidowanie) – tylko grunty spoiste.
- Tabela warstw w PDF podzielona na dwie: ogólna (parametry fizyczne) + osobna
  dla wytrzymałości/historii naprężeń gruntów spoistych (Su, 3×OCR, σ'p, K0) –
  jedna tabela zrobiła się za gęsta po dodaniu tych parametrów.
- **Poprawka nazewnictwa**: ujednolicono K0/Ko na "K0" wszędzie (wcześniej
  niespójne). K0 (NC, Jaky) i K0 (OC, Kulhawy-Mayne) pokazane teraz OBOK SIEBIE
  w drugiej tabeli (dla gruntów spoistych) do bezpośredniego porównania – wcześniej
  trzeba było zaglądać do dwóch różnych tabel.
- **"Bezpieczny" podział na warstwy**: cienkie warstwy o kontrastowym charakterze
  względem obu sąsiadów (np. przekładka torfu/gliny w piasku) NIE są scalane mimo
  progu miąższości – oznaczane jako "Uwaga: zweryfikuj". Scalane są tylko cienkie
  warstwy przejściowe między podobnymi gruntami.
- **Raport PDF jasno rozdziela wiarygodność**: klasyfikacja gruntu (Ic/SBTn) ma
  >80% zgodności z próbkami (Robertson 2009) – wiarygodna. Bezwzględne Su/OCR/φ'
  zależą od współczynników z literatury (Nkt, k) – orientacyjne do czasu lokalnej
  kalibracji badaniami laboratoryjnymi.

## Historia napraw (ważne, żeby nie robić tego samo drugi raz)

1. **Sklejanie liczb na osi** (np. "40" i "45" → "4045") – różne karty mają różny
   odstęp między cyframi na osi. Naprawione: tokenizacja w naturalnej kolejności
   znaków ze strumienia PDF (NIE sortować wg pozycji x – to myli kolejność przy
   nachodzących na siebie etykietach) + odzyskiwanie liczb wzorcem tekstowym
   z "sklejonych" fragmentów, gdy pozycyjne rozdzielenie jest niemożliwe (etykiety
   naprawdę nachodzą na siebie wizualnie, np. skala co 0,05).
2. **Kalibracja osi wartości**: bierzemy tylko **pierwsze dwie** znalezione liczby
   (zawsze bezpiecznie rozdzielone) i ekstrapolujemy krok do prawej krawędzi ramki
   panelu – zamiast próbować parsować całą (czasem nachodzącą) etykietę osi.
3. **Różna kolejność paneli w różnych programach** (np. Rf i U2 zamienione miejscami
   względem CPT-Star) – naprawione przez identyfikację krzywej po kolorze linii,
   nie po pozycji panelu.
4. **Dodatkowa kolumna litologii** po lewej stronie karty myliła wykrywanie ramek
   (fałszywe, podwójnie szerokie dopasowania) – dodany filtr spójności szerokości.
5. **Wielostronicowe PDF-y** (strony 2-3 z gotową interpretacją innego programu) –
   apka czyta świadomie tylko pierwszą stronę.
6. **Ujemne qt psuło całe obliczenia** (log z liczby ujemnej → NaN kaskadowo przez
   cały profil) – u2 bywa lekko ujemne (szum blisko zera), qc było zabezpieczone
   przed ujemnymi wartościami, ale qt (pochodna qc i u2) już nie. Naprawione.
7. **Font PDF**: DejaVuSans dołączony bezpośrednio do repo (folder `fonts/`) –
   apka nie zależy od czcionek zainstalowanych na serwerze Streamlit Cloud.
8. **Kolizje kluczy widgetów Streamlit** przy dwóch plikach o tej samej nazwie –
   naprawione: klucze widgetów zawierają indeks pliku, nie tylko nazwę.
9. **Struktura folderów na GitHubie**: pliki trzeba wgrywać jako CAŁE FOLDERY
   (przeciągnięcie folderu `pages/` i `fonts/`, nie pojedynczych plików z nich) –
   inaczej GitHub spłaszcza strukturę i apka się wywala (`st.page_link` nie
   znajduje stron, `fonts/DejaVuSans.ttf` nie istnieje).

## Przetestowane karty CPTU (różne formaty, wszystkie działają)

- CPTU_nr_5, 11, 12 (program CPT-Star, różne warianty gęstości podziałki osi)
- CPTu-1 (inny program – Uni-Geo/.sta, inna kolejność paneli, kolumna litologii,
  wielostronicowy PDF z gotową interpretacją na str. 2-3)
- Wyniki_CPT_Darłowo (program Geoteko) – **NOWOŚĆ: obsługa wielu sondowań w jednym
  pliku**, jedna strona = jedno CPTU. Format specyficzny: krzywe zapisane jako
  pojedynczy wielopunktowy obiekt (LTCurve) zamiast wielu odcinków (LTLine); dwa
  bloki wykresów (surowe dane + gotowa interpretacja) jeden nad drugim na tej samej
  stronie o tej samej wysokości ramek, ale innej pozycji; tekst nie pogrupowany w
  linie przez bibliotekę PDF (własne grupowanie po Y); etykiety osi sąsiednich
  paneli czasem nachodzą na granicy (gubiąc np. znak "-").

## Kluczowe funkcje w extractor.py

- `extract_cpt(pdf_path, depth_negative=True, page_index=0)` – pojedyncze
  sondowanie z jednej strony (domyślnie strona 1, jak dotychczas)
- `extract_all_soundings(pdf_path, depth_negative=True)` – **NOWOŚĆ**: wszystkie
  sondowania z pliku (każda strona = próba ekstrakcji), zwraca listę
  `{test_id, df, page, error}`. Numer testu (`test_id`) zgadywany z tekstu na
  stronie (wzorzec litera+cyfry, np. "D1"), z fallbackiem na "strona N".
- Rozpoznawanie krzywej: najpierw po KOLORZE (jak dotychczas), a jeśli kolorowych
  obiektów jest bardzo mało (< 20) – fallback na dopasowanie po ETYKIECIE OSI
  (np. "qc [MPa]") w paśmie nad panelem. Dotyczy PDF-ów, gdzie wszystkie krzywe
  mają ten sam kolor.
- Wybór właściwych linii/punktów w obrębie już przypisanej ramki: kolor o
  największej łącznej liczbie punktów SPOŚRÓD znanych kolorów konwencji CPTU
  (niebieski/czerwony/bordowy/czarny) – NIE dowolny kolor (szara siatka ma więcej
  odcinków niż krzywa i wygrywałaby błędnie, gdyby nie było tego ograniczenia).
- Kalibracja osi wartości: mediana nachyleń między wszystkimi parami znalezionych
  liczb (nie tylko pierwsze dwie) – odporne na pojedynczy zepsuty odczyt (np.
  etykiety sąsiednich paneli nachodzące na granicy, gubiące znak "-" przy
  wartościach ujemnych).
- Kalibracja osi głębokości: filtr monotoniczności odrzucający punkty łamiące
  rosnącą kolejność (przeciek liczby z sąsiedniego panelu).
- `_load_page_objects`: tekst grupowany najpierw standardowo (LTTextLineHorizontal),
  a znaki NIEOBJĘTE tym grupowaniem (część lub wszystkie na stronie, zależnie od
  PDF-a) grupowane zapasowo po współrzędnej Y, z pominięciem tekstu obróconego
  (np. pionowy podpis "Depth [m]", rozpoznawany po macierzy transformacji znaku).
- Krzywe zbierane zarówno z LTLine (wiele odcinków) jak i LTCurve (jeden
  wielopunktowy obiekt, `.pts`) – różne programy CPT rysują to inaczej.

## Co NIE jest jeszcze zrobione (świadomie odłożone)

- **Upload wyników badań laboratoryjnych** – odłożone, bo formaty raportów lab
  są dużo mniej jednolite niż karty CPT. Do ustalenia: prosty formularz/Excel do
  ręcznego wpisania kluczowych wartości, vs. odczyt przez AI (Claude API, koszt +
  potrzeba kroku "sprawdź i popraw").
- **Moduł Sichardta / wydatku studni (odwodnienia)** – policzony ręcznie jako
  jednorazowy przykład na karcie nr 11 (promień leja depresji, wydatek studni),
  NIE wbudowany jeszcze jako stała funkcja apki. Metoda: wzór Sichardta
  (R = 3000·s·√k) + Thiem (Q = 2πTs/ln(R/rw)) na bazie k z profilu CPT.
- **Porównanie z gotowymi interpretacjami innych programów** – karta CPTu-1 ma
  na str. 2-3 gotowe φ, Su, OCR, Eoed z innego software'u. Można by to wyciągnąć
  i porównać z naszymi wynikami jako sprawdzian metody – pomysł, nie zrobiony.
- Możliwe dalsze usprawnienia raportu PDF (dyskutowane, nie wdrożone): tabelka
  wrażliwości na ZWG (co by było gdyby), Su jako zakres (Nkt niski/wysoki) zamiast
  jednej liczby, oznaczanie stref przejściowych o niepewnej klasyfikacji.

## Kontekst zawodowy Moniki

Inżynier geotechnik/hydrotechnik w Keller Polska. Cel długoterminowy: pełna
dokumentacja geotechniczna generowana na podstawie kart CPTU + (docelowo) badań
laboratoryjnych. Woli konkret bez teorii, krótkie odpowiedzi, ostrzega wprost przed
niepewnością/ryzykiem błędu zamiast to bagatelizować.
