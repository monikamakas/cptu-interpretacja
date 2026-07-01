"""
Ekstraktor danych z kart CPTU (PDF wektorowy, np. z programu CPT-Star).
Automatycznie wykrywa ramki wykresów, kalibruje osie na podstawie
podpisanych wartości i wyciąga krzywe qc, fs, u2, Rf(qc) w funkcji głębokości.
"""
import re
from collections import defaultdict, Counter
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTLine, LTFigure, LTTextLineHorizontal, LTChar, LTContainer

CURVE_ORDER = ["qc [MPa]", "fs [MPa]", "u2 [MPa]", "Rf(qc) [%]"]


def _walk(obj):
    for el in obj:
        yield el
        if isinstance(el, LTContainer):
            yield from _walk(el)


def _emit_token(token_chars, texts):
    """Dodaje token do listy texts. Jeśli token nie jest pojedynczą poprawną liczbą
    (bo etykiety osi wizualnie nachodzą na siebie przy gęstej podziałce i nie dały się
    rozdzielić po pozycji x), próbuje odzyskać wiele liczb wzorcem tekstowym na kolejności
    znaków w strumieniu PDF (ta kolejność jest poprawna nawet gdy pozycje x nachodzą)."""
    if not token_chars:
        return
    txt = "".join(ch.get_text() for ch in token_chars).strip()
    if not txt:
        return
    x0 = min(ch.x0 for ch in token_chars)
    x1 = max(ch.x1 for ch in token_chars)
    y0 = min(ch.y0 for ch in token_chars)
    y1 = max(ch.y1 for ch in token_chars)
    if re.fullmatch(r"-?\d+(\.\d+)?", txt):
        texts.append((txt, (x0, y0, x1, y1)))
        return
    # token nieparsowalny wprost - spróbuj odzyskać osadzone liczby dziesiętne (D.DD)
    # w poprawnej kolejności znaków (strumień PDF, nie posortowane wg x)
    recovered = False
    for m in re.finditer(r"\d\.\d{1,2}", txt):
        sub_chars = token_chars[m.start():m.end()]
        sx0 = min(ch.x0 for ch in sub_chars)
        sx1 = max(ch.x1 for ch in sub_chars)
        sy0 = min(ch.y0 for ch in sub_chars)
        sy1 = max(ch.y1 for ch in sub_chars)
        texts.append((m.group(), (sx0, sy0, sx1, sy1)))
        recovered = True
    if not recovered:
        texts.append((txt, (x0, y0, x1, y1)))


def _load_page_objects(pdf_path):
    lines, texts = [], []
    for page in extract_pages(pdf_path):
        for el in _walk(page):
            if isinstance(el, LTLine):
                lines.append(el)
            elif isinstance(el, LTTextLineHorizontal):
                # rozbij linię tekstu na tokeny (liczby) po przerwach w x, na podstawie
                # pozycji poszczególnych znaków (żeby "0 5 10 ... 40" dało 9 osobnych liczb).
                # Kolejność znaków zostaje taka, jak w strumieniu PDF (NIE sortujemy wg x0) -
                # przy gęstej podziałce etykiety mogą się wizualnie nachodzić, a sortowanie
                # po x0 przestawiałoby wtedy kolejność cyfr na błędną.
                chars = [c for c in el if isinstance(c, LTChar)]
                if not chars:
                    t = el.get_text().strip()
                    if t:
                        texts.append((t, el.bbox))
                    continue
                token_chars = [chars[0]] if chars[0].get_text() != " " else []
                for c in chars[1:]:
                    if not token_chars:
                        if c.get_text() != " ":
                            token_chars.append(c)
                        continue
                    gap = c.x0 - token_chars[-1].x1
                    if c.get_text() == " " or gap > 0.25:
                        _emit_token(token_chars, texts)
                        token_chars = []
                    if c.get_text() != " ":
                        token_chars.append(c)
                _emit_token(token_chars, texts)
    return lines, texts


def _find_frames(lines):
    """Znajduje prostokątne ramki wykresów: grupy 4 linii (2 poziome + 2 pionowe)
    tworzące zamknięty prostokąt. Zwraca listę (x0,y0,x1,y1) posortowaną wg x0."""
    # kandydaci: linie czarne/szare o dowolnej niezerowej szerokości, wystarczająco długie
    cand = [l for l in lines if l.linewidth and l.linewidth > 0.3]
    horiz = [l for l in cand if abs(l.y0 - l.y1) < 0.05 and (l.x1 - l.x0) > 30]
    vert = [l for l in cand if abs(l.x0 - l.x1) < 0.05 and (l.y1 - l.y0) > 30]

    # grupuj poziome linie po współrzędnej y (top/bottom kandydaci ramek)
    hy = defaultdict(list)
    for l in horiz:
        hy[round(l.y0, 1)].append(l)
    vx = defaultdict(list)
    for l in vert:
        vx[round(l.x0, 1)].append(l)

    # szukaj par (y_top, y_bottom) i (x_left, x_right) które się powtarzają jako ramki
    # prostsza heurystyka: znajdź wszystkie unikalne pary (x_left,x_right) o tej samej (y_top,y_bottom)
    frames = []
    y_levels = sorted(hy.keys())
    for i, ytop in enumerate(y_levels):
        for ybot in y_levels:
            if ybot >= ytop - 50:
                continue
            top_lines = hy[ytop]
            bot_lines = hy[ybot]
            for tl in top_lines:
                for bl in bot_lines:
                    if abs(tl.x0 - bl.x0) < 1 and abs(tl.x1 - bl.x1) < 1:
                        x0, x1 = tl.x0, tl.x1
                        # sprawdź czy istnieją odpowiednie linie pionowe spinające
                        left_ok = any(abs(l.x0 - x0) < 1 and l.y0 <= ybot + 1 and l.y1 >= ytop - 1 for l in vert)
                        right_ok = any(abs(l.x0 - x1) < 1 and l.y0 <= ybot + 1 and l.y1 >= ytop - 1 for l in vert)
                        if left_ok and right_ok and (x1 - x0) > 30:
                            frames.append((round(x0, 1), round(ybot, 1), round(x1, 1), round(ytop, 1)))
    frames = sorted(set(frames))
    # odfiltruj ramkę zewnętrzną (największą) i zostaw te o zbliżonej wysokości, ułożone obok siebie
    if not frames:
        return []
    heights = Counter(round(f[3] - f[1], 0) for f in frames)
    common_h = heights.most_common(1)[0][0]
    panels = [f for f in frames if abs((f[3] - f[1]) - common_h) < 2]
    panels = sorted(set(panels), key=lambda f: f[0])
    # usuń duplikaty/zawieranie się
    dedup = []
    for f in panels:
        if not any(abs(f[0]-g[0]) < 1 and abs(f[2]-g[2]) < 1 for g in dedup):
            dedup.append(f)
    return sorted(dedup, key=lambda f: f[0])


def _nearby_numbers(texts, x_range=None, y_range=None):
    out = []
    for t, (x0, y0, x1, y1) in texts:
        if x_range and not (x_range[0] - 3 <= (x0 + x1) / 2 <= x_range[1] + 3):
            continue
        if y_range and not (y_range[0] - 3 <= (y0 + y1) / 2 <= y_range[1] + 3):
            continue
        for tok in re.split(r"[^0-9.,\-]+", t):
            tok = tok.replace(",", ".")
            if re.fullmatch(r"-?\d+(\.\d+)?", tok):
                out.append((float(tok), (x0 + x1) / 2, (y0 + y1) / 2))
    return out


def _calibrate_x_axis(texts, frame):
    x0, y0, x1, y1 = frame
    nums = _nearby_numbers(texts, x_range=(x0, x1), y_range=(y1, y1 + 20))
    if len(nums) < 2:
        return None
    nums.sort(key=lambda n: n[1])  # sortuj wg pozycji x
    # Bierzemy TYLKO pierwsze dwie liczby (zawsze bezpiecznie rozdzielone, nawet gdy
    # dalsze etykiety osi wizualnie nachodzą na siebie przy gęstej podziałce - np. co 0.05)
    # i ekstrapolujemy krok wartości do prawej krawędzi ramki panelu.
    v_a, x_a = nums[0][0], nums[0][1]
    v_b, x_b = nums[1][0], nums[1][1]
    if x_b == x_a:
        return None
    step = (v_b - v_a) / (x_b - x_a)
    v1 = v_a + step * (x1 - x_a)
    return dict(x0=x_a, x1=x1, v0=v_a, v1=v1)


def _calibrate_depth_axis(texts, frames):
    left = min(f[0] for f in frames)
    y0 = min(f[1] for f in frames)
    y1 = max(f[3] for f in frames)
    nums = _nearby_numbers(texts, x_range=(left - 60, left - 2), y_range=(y0 - 5, y1 + 5))
    if len(nums) < 2:
        return None
    nums.sort(key=lambda n: -n[2])
    dmin, ymax = nums[0][0], nums[0][2]
    dmax, ymin = nums[-1][0], nums[-1][2]
    if ymax == ymin:
        return None
    a = (dmax - dmin) / (ymin - ymax)
    b = dmin - a * ymax
    return dict(a=a, b=b, y0=y0, y1=y1)


CURVE_COLORS = [
    ("qc [MPa]", (0.0, 0.0, 1.0)),
    ("fs [MPa]", (1.0, 0.0, 0.0)),
    ("u2 [MPa]", (0.502, 0.0, 0.0)),
    ("Rf(qc) [%]", 0.0),
]


def extract_cpt(pdf_path, depth_negative=True):
    lines, texts = _load_page_objects(pdf_path)
    frames = _find_frames(lines)
    if len(frames) < 4:
        raise ValueError(f"Nie znaleziono 4 paneli wykresu (znaleziono {len(frames)}). "
                          "Sprawdź, czy PDF zawiera wektorowe wykresy CPTU.")
    frames = frames[:4]

    depth_cal = _calibrate_depth_axis(texts, frames)
    if depth_cal is None:
        raise ValueError("Nie udało się skalibrować osi głębokości (brak podpisów liczbowych).")

    def depth_from_y(y):
        return depth_cal["a"] * y + depth_cal["b"]

    Y0, Y1 = depth_cal["y0"], depth_cal["y1"]

    import pandas as pd
    series = {}
    for (name, color), frame in zip(CURVE_COLORS, frames):
        xcal = _calibrate_x_axis(texts, frame)
        if xcal is None:
            raise ValueError(f"Nie udało się skalibrować osi wartości dla panelu {name}.")
        fx0, fy0, fx1, fy1 = frame
        if name == "Rf(qc) [%]":
            sel = [l for l in lines if l.stroking_color == 0.0 and l.linewidth and abs(l.linewidth - 0.28) < 0.05
                   and l.x0 >= fx0 - 1 and l.x1 <= fx1 + 1 and l.y0 >= Y0 - 1 and l.y1 <= Y1 + 1]
        else:
            sel = [l for l in lines if l.stroking_color == color
                   and l.x0 >= fx0 - 1 and l.x1 <= fx1 + 1 and l.y0 >= Y0 - 1 and l.y1 <= Y1 + 1]
        pts = set()
        for l in sel:
            pts.add((l.x0, l.y0)); pts.add((l.x1, l.y1))
        a = (xcal["v1"] - xcal["v0"]) / (xcal["x1"] - xcal["x0"])
        data = []
        for x, y in pts:
            val = xcal["v0"] + a * (x - xcal["x0"])
            depth = depth_from_y(y)
            if depth < -0.05 or depth > (depth_cal["a"] * Y0 + depth_cal["b"]) + 0.5:
                continue
            data.append((round(depth, 2), val))
        df = pd.DataFrame(data, columns=["depth", "val"]).groupby("depth", as_index=False).mean()
        series[name] = df.set_index("depth")["val"]

    full = pd.concat(series, axis=1).sort_index().reset_index()
    full = full.rename(columns={"depth": "Głębokość [m]"})
    for col in full.columns[1:]:
        full[col] = full[col].interpolate(limit_direction="both")
    if depth_negative:
        full["Głębokość [m]"] = -full["Głębokość [m]"]
    return full
