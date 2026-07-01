"""Budowa raportu PDF z interpretacją geotechniczną CPTU."""
from io import BytesIO
from datetime import date

import pandas as pd
import matplotlib
matplotlib.use("Agg")
matplotlib.rcParams["font.family"] = "DejaVu Sans"
import matplotlib.pyplot as plt

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
                                 Image, PageBreak, HRFlowable)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from calc import compute_profile
from layering import detect_layers
from plotting import make_profile_figure

import os

PAGE = landscape(A4)
_FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
try:
    pdfmetrics.registerFont(TTFont("DejaVuSans", os.path.join(_FONT_DIR, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", os.path.join(_FONT_DIR, "DejaVuSans-Bold.ttf")))
    _FONT = "DejaVuSans"
    _FONT_BOLD = "DejaVuSans-Bold"
except Exception:
    # awaryjnie: Helvetica nie ma polskich znaków diakrytycznych, ale apka nie powinna się wywalić
    _FONT = "Helvetica"
    _FONT_BOLD = "Helvetica-Bold"


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1r", fontName=_FONT_BOLD, fontSize=17, spaceAfter=10))
    styles.add(ParagraphStyle(name="H2r", fontName=_FONT_BOLD, fontSize=12, spaceBefore=10, spaceAfter=6, textColor=colors.HexColor("#2F5597")))
    styles.add(ParagraphStyle(name="Bodyr", fontName=_FONT, fontSize=9, leading=13))
    styles.add(ParagraphStyle(name="Smallr", fontName=_FONT, fontSize=7.5, leading=10, textColor=colors.HexColor("#555555")))
    styles.add(ParagraphStyle(name="Warnr", fontName=_FONT_BOLD, fontSize=9.5, leading=13, textColor=colors.HexColor("#B00000")))
    styles.add(ParagraphStyle(name="Cell", fontName=_FONT, fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="CellHead", fontName=_FONT_BOLD, fontSize=8, leading=10, textColor=colors.white))
    styles.add(ParagraphStyle(name="CellSmall", fontName=_FONT, fontSize=7, leading=8.5))
    styles.add(ParagraphStyle(name="CellSmallHead", fontName=_FONT_BOLD, fontSize=7, leading=8.5, textColor=colors.white))
    return styles


def build_pdf_report(raw_df, meta, gwl, gwl_method_note, area_ratio, nkt, min_thickness=1.0, smooth_window=25):
    """
    raw_df: kolumny 'Głębokość [m]', 'qc [MPa]', 'fs [MPa]', 'u2 [MPa]'
    meta: dict z kluczami test_number, cone_number, date, investor, source_file
    Zwraca BytesIO z gotowym PDF.
    """
    styles = _styles()

    def P(text, style="Cell"):
        return Paragraph(str(text), styles[style])

    profile = compute_profile(raw_df, gwl=gwl, area_ratio=area_ratio, nkt=nkt)
    layers = detect_layers(profile, min_thickness=min_thickness, smooth_window=smooth_window)

    fig = make_profile_figure(profile, layers,
                               title=f"CPTU nr {meta.get('test_number','')} – profil interpretacyjny "
                                     f"({meta.get('source_file','')})")
    img_buf = BytesIO()
    fig.savefig(img_buf, format="png", dpi=170)
    plt.close(fig)
    img_buf.seek(0)

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=PAGE, topMargin=14*mm, bottomMargin=14*mm,
                             leftMargin=14*mm, rightMargin=14*mm,
                             title=f"Interpretacja CPTU nr {meta.get('test_number','')}")
    story = []

    # === STRONA TYTUŁOWA ===
    story.append(Paragraph("Interpretacja geotechniczna sondowania CPTU", styles["H1r"]))
    story.append(Paragraph(
        f"Sondowanie nr {meta.get('test_number','—')} &nbsp;|&nbsp; Nr stożka: {meta.get('cone_number','—')} "
        f"&nbsp;|&nbsp; Data: {meta.get('date','—')} &nbsp;|&nbsp; Inwestor: {meta.get('investor','—')}",
        styles["Bodyr"]))
    story.append(Paragraph(
        f"Plik źródłowy: {meta.get('source_file','—')} &nbsp;|&nbsp; Raport wygenerowany: {date.today().isoformat()}",
        styles["Smallr"]))
    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", color=colors.HexColor("#2F5597"), thickness=1.2))
    story.append(Spacer(1, 8))

    story.append(Paragraph("Podstawa metodyczna", styles["H2r"]))
    story.append(Paragraph(
        "Interpretacja wykonana na podstawie ciągłych pomiarów qc, fs, u2 (odczytanych wektorowo z karty PDF) "
        "wg metod Robertsona (Cone Penetration Testing Guide, 6th ed., Gregg Drilling, 2015) oraz uzupełniająco "
        "Kulhawy'ego i Mayne'a (1990). Wskaźnik zachowania gruntu Ic i strefy SBTn wyznaczono iteracyjnie "
        "z wykorzystaniem zmiennego wykładnika naprężeń n wg Robertson (2009).", styles["Bodyr"]))

    story.append(Paragraph("Przyjęte założenia", styles["H2r"]))
    assum_data = [
        ["Parametr", "Przyjęta wartość", "Uzasadnienie / uwagi"],
        ["Zwierciadło wody gruntowej (ZWG)", f"{gwl:.2f} m p.p.t.", gwl_method_note],
        ["Współczynnik powierzchni netto stożka (a)", f"{area_ratio:.2f}",
         "Wpływa na korektę qc → qt, istotne głównie w gruntach spoistych. Ustaw wg karty kalibracji sondy, jeśli znasz."],
        ["Współczynnik stożka Nkt (do wyznaczenia Su)", f"{nkt:.0f} (typowy zakres: 14–16)",
         "Su = (qt − σv) / Nkt – bez lokalnej kalibracji (badania laboratoryjne) to wartość orientacyjna."],
        ["Ciężar objętościowy gruntu γ", "wyznaczony z korelacji CPT (Robertson 2010)",
         "Brak bezpośrednich pomiarów – naprężenia pionowe integrowane z tej korelacji."],
    ]
    t = Table([[P(c, "CellHead") for c in assum_data[0]]] + [[P(c) for c in row] for row in assum_data[1:]],
              colWidths=[62*mm, 55*mm, 140*mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#B00000")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#FFF3F3")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t)
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Klasyfikacja gruntu i przebieg warstwowania (Ic/SBTn) są oparte na relacji potwierdzonej w literaturze "
        "z ponad 80% zgodnością względem próbek gruntu (Robertson 2009). Bezwzględne wartości Su, OCR i φ' "
        "zależą od współczynników empirycznych (Nkt, k) i powinny być traktowane jako orientacyjne do czasu "
        "lokalnej kalibracji badaniami laboratoryjnymi. Parametry φ', Es, M, G0, Dr, N60 dotyczą gruntów "
        "niespoistych (Ic &lt; 2,60), a Su, Su/σ'v0, OCR – gruntów spoistych (Ic &gt; 2,60).",
        styles["Smallr"]))
    story.append(PageBreak())

    # === WYKRES ===
    story.append(Paragraph(f"Profil interpretacyjny – sondowanie nr {meta.get('test_number','')}", styles["H2r"]))
    img = Image(img_buf)
    avail_w = PAGE[0] - 28*mm
    avail_h = PAGE[1] - 45*mm
    ratio = img.imageWidth / img.imageHeight
    if avail_w / ratio <= avail_h:
        img.drawWidth = avail_w
        img.drawHeight = avail_w / ratio
    else:
        img.drawHeight = avail_h
        img.drawWidth = avail_h * ratio
    story.append(img)
    story.append(PageBreak())

    # === TABELA WARSTW ===
    story.append(Paragraph("Automatyczny podział na warstwy – wartości średnie", styles["H2r"]))
    story.append(Paragraph(
        f"Podział na podstawie wygładzonego Ic (mediana ruchoma, okno ~{smooth_window*0.02:.1f} m), "
        f"docelowa min. miąższość {min_thickness:.1f} m. Cienkie warstwy o wyraźnie odmiennym charakterze "
        "od obu sąsiadów nie są scalane – są oznaczane w kolumnie „Uwaga”. Wartości spoza zakresu "
        "stosowalności metody oznaczono jako „–”.", styles["Smallr"]))
    story.append(Spacer(1, 4))

    cols = ["Od\n[m]", "Do\n[m]", "Miąż.\n[m]", "SBTn\nopis", "qt śr\n[MPa]", "Ic śr\n[-]",
            "γ śr\n[kN/m³]", "φ' śr\n[°]", "Dr śr\n[%]", "M śr\n[MPa]", "Su śr\n[kPa]", "OCR śr\n(Robertson)",
            "k śr\n[m/s]", "Uwaga"]
    rows = [cols]
    for _, r in layers.iterrows():
        def fmt(v):
            return "–" if pd.isna(v) else f"{v:.1f}"
        def fmt_k(v):
            return "–" if pd.isna(v) else f"{v:.1e}"
        rows.append([
            f"{r['Od [m]']:.2f}", f"{r['Do [m]']:.2f}", f"{r['Miąższość [m]']:.2f}", r["Opis"],
            fmt(r["qt [MPa] śr"]), fmt(r["Ic [-] śr"]), fmt(r["gamma [kN/m3] śr"]),
            fmt(r["phi [deg] śr"]), fmt(r["Dr [%] śr"]), fmt(r["M [MPa] śr"]),
            fmt(r["Su [kPa] śr"]), fmt(r["OCR (Robertson 2009) [-] śr"]), fmt_k(r["k [m/s] śr"]),
            r.get("Uwaga", ""),
        ])
    t2 = Table([[P(c, "CellSmallHead") for c in rows[0]]] + [[P(c, "CellSmall") for c in row] for row in rows[1:]],
               repeatRows=1, colWidths=[12*mm, 12*mm, 12*mm, 38*mm, 16*mm, 13*mm, 15*mm, 13*mm, 13*mm, 15*mm, 15*mm, 18*mm, 16*mm, 28*mm])
    t2.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5597")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5FA")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t2)
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Pełny profil (co 0,02 m) ze wszystkimi wyznaczonymi parametrami dostępny jest jako plik CSV.",
        styles["Smallr"]))
    story.append(PageBreak())

    # === METODYKA ===
    story.append(Paragraph("Metodyka i zastosowane wzory", styles["H2r"]))
    formulas = [
        ("Naprężenia", "σv = Σγ·Δz (całkowite); σ'v = σv − u0; u0 = γw·(z − ZWG)", "-"),
        ("Skorygowany opór stożka", "qt = qc + u2·(1 − a)", "Lunne, Robertson, Powell (1997)"),
        ("Znormalizowany opór (Qt, n=1)", "Qt = (qt − σv) / σ'v", "Robertson (1990)"),
        ("Znorm. opór ze zmiennym n", "Qtn = [(qt−σv)/Pa]·(Pa/σ'v)ⁿ,  n = 0,381·Ic + 0,05·(σ'v/Pa) − 0,15 (≤1,0), iteracyjnie", "Robertson (2009)"),
        ("Znorm. stosunek tarcia", "Fr = fs / (qt − σv) · 100%", "Robertson (1990)"),
        ("Wskaźnik zachowania gruntu", "Ic = [(3,47 − log Qtn)² + (log Fr + 1,22)²]^0,5", "Robertson (2009)"),
        ("Strefy SBTn wg Ic", "Ic&lt;1,31 żwir/piasek gęsty; 1,31–2,05 piasek; 2,05–2,60 piasek pylasty; "
                              "2,60–2,95 pył/glina pyl.; 2,95–3,60 glina; &gt;3,60 organiczne", "Robertson (1990, 2010)"),
        ("Ciężar objętościowy", "γ/γw = 0,27·log(Rf) + 0,36·log(qt/Pa) + 1,236,  Rf = fs/qt·100%", "Robertson (2010)"),
        ("Ekwiwalent SPT N60", "(qt/Pa)/N60 = 10^(1,1268 − 0,2817·Ic)", "Robertson (2012)"),
        ("Gęstość względna Dr (grunty niespoiste)", "Dr² = Qtn / 350", "Robertson (2010), uproszczone wg Kulhawy-Mayne"),
        ("Kąt tarcia wewn. – piaski", "φ' = 17,6 + 11·log(Qtn)", "Kulhawy i Mayne (1990)"),
        ("Kąt tarcia wewn. – grunty spoiste", "φ' = 29,5·Bq^0,121·(0,256 + 0,336·Bq + log Qt),  gdy Bq&gt;0,1; "
                                              "w przeciwnym razie przyjęto φ'=28°", "Senneset i in. (1989), Mayne (2006)"),
        ("Moduł Younga Es (piaski)", "Es = αE·(qt − σv), αE = 0,015·10^(0,55·Ic+1,68)", "Robertson (2009)"),
        ("Moduł edometryczny M", "Ic&gt;2,2: M=Qt·(qt−σv) (Qt&lt;14) lub 14·(qt−σv);  Ic&lt;2,2: M=0,0188·10^(0,55Ic+1,68)·(qt−σv)", "Robertson (2009)"),
        ("Prędkość fali poprzecznej / G0", "Vs = [αvs·(qt−σv)/Pa]^0,5, αvs=10^(0,55Ic+1,68);  G0 = ρ·Vs²", "Robertson (2009)"),
        ("Wytrzymałość na ścinanie bez odpł. su", "su = (qt − σv) / Nkt,  Nkt ≈ 14–16", "Lunne, Robertson, Powell (1997)"),
        ("Stosunek su/σ'v0 i OCR (Robertson)", "su/σ'v0 = Qt/Nkt;  OCR = 0,25·Qt^1,25", "Robertson (2009)"),
        ("OCR (Kulhawy-Mayne)", "OCR = k·Qt,  k ≈ 0,33 (zakres 0,2–0,5)", "Kulhawy i Mayne (1990)"),
        ("Współczynnik parcia bocznego Ko", "Ko ≈ 0,5·√OCR", "Kulhawy i Mayne (1990)"),
        ("Wodoprzepuszczalność k", "Ic≤3,27: k=10^(0,952−3,04·Ic) m/s;  Ic&gt;3,27: k=10^(−4,52−1,37·Ic) m/s "
                                   "(dokładność rzędu wielkości)", "Robertson (2010)"),
    ]
    rows_f = [["Parametr", "Wzór", "Źródło"]] + [[a, b, c] for a, b, c in formulas]
    t3 = Table([[P(c, "CellHead") for c in rows_f[0]]] + [[P(c) for c in row] for row in rows_f[1:]],
               repeatRows=1, colWidths=[62*mm, 145*mm, 58*mm])
    t3.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2F5597")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#DDDDDD")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F2F5FA")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(t3)
    story.append(PageBreak())

    # === OGRANICZENIA ===
    story.append(Paragraph("Ograniczenia i sugerowane dalsze kroki", styles["H2r"]))
    story.append(Paragraph(
        "<b>1. To korelacje, nie pomiary — ale nie wszystkie w tym raporcie są tak samo niepewne.</b> "
        "Klasyfikacja gruntu i przebieg warstwowania (Ic/SBTn) są oparte na relacji potwierdzonej w literaturze "
        "z ponad 80% zgodnością względem próbek gruntu (Robertson 2009) – tej części można ufać jako dobrego "
        "obrazu ośrodka. Natomiast bezwzględne wartości Su, OCR i φ' zależą od współczynników empirycznych "
        "(Nkt, k), które są średnimi z literatury, nie wartościami wyznaczonymi dla tego gruntu. W praktyce "
        "projektowej CPT służy do ciągłego rozpoznania i wytypowania warstw krytycznych, a wartości liczbowe "
        "kluczowe dla projektu potwierdza się badaniami laboratoryjnymi z tych warstw.", styles["Bodyr"]))
    story.append(Paragraph(
        "<b>2. Brak kalibracji lokalnej.</b> Współczynniki Nkt i k (OCR) są wartościami domyślnymi z literatury. "
        "Gdy pojawią się wyniki badań laboratoryjnych z tej lokalizacji, można je wykorzystać do lokalnej "
        "kalibracji – tak jak w metodzie SHANSEP (wymaga parametrów S i m z badań laboratoryjnych na próbkach "
        "z tego gruntu, nie z literatury dla innej lokalizacji).", styles["Bodyr"]))
    story.append(Paragraph(
        "<b>3. Rozdzielenie gruntów na spoiste/niespoiste jest przybliżone.</b> Granica Ic=2,60 bywa nieostra "
        "w warstwach przejściowych – niektóre wartości Su/φ' w takich strefach mogą być zaniżone lub zawyżone.",
        styles["Bodyr"]))
    story.append(Paragraph(
        "<b>4. Automatyczny podział na warstwy jest orientacyjny.</b> Algorytm chroni cienkie, kontrastowe "
        "przekładki przed scaleniem, ale ostateczne granice warstw powinien zweryfikować geotechnik.",
        styles["Bodyr"]))

    doc.build(story)
    buf.seek(0)
    return buf, profile, layers
