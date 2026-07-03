"""
Ekstraktor danych z kart CPTU (PDF wektorowy, np. z programu CPT-Star).
Automatycznie wykrywa ramki wykresów, kalibruje osie na podstawie
podpisanych wartości i wyciąga krzywe qc, fs, u2, Rf(qc) w funkcji głębokości.
"""
import re
from collections import defaultdict, Counter
from pdfminer.high_level import extract_pages
from pdfminer.layout import LTLine, LTCurve, LTFigure, LTTextLineHorizontal, LTChar, LTContainer

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


def _load_page_objects(pdf_path, page_index=0):
    """page_index=0: przetwarzaj tylko pierwszą stronę PDF (tam, gdzie są surowe
    krzywe qc/fs/u2/Rf). Karty wielostronicowe (np. z gotową interpretacją na
    kolejnych stronach) nie mieszają się wtedy z danymi z innych stron."""
    lines, texts = [], []
    for i, page in enumerate(extract_pages(pdf_path)):
        if page_index is not None and i != page_index:
            continue
        raw_chars = []
        handled_ids = set()
        for el in _walk(page):
            if isinstance(el, LTLine):
                lines.append(el)
            elif isinstance(el, LTCurve):
                # niektóre programy (np. Geoteko) rysują krzywą jako jeden obiekt
                # wielopunktowy zamiast wielu osobnych odcinków (LTLine) - zbieramy
                # go też, żeby nie stracić danych krzywej
                lines.append(el)
            elif isinstance(el, LTChar):
                # tylko tekst poziomy - obrócony (np. pionowy podpis "Depth [m]") ma
                # dominujące składowe b/c macierzy transformacji zamiast a/d
                if abs(el.matrix[1]) < 0.01:
                    raw_chars.append(el)
            elif isinstance(el, LTTextLineHorizontal):
                # rozbij linię tekstu na tokeny (liczby) po przerwach w x, na podstawie
                # pozycji poszczególnych znaków (żeby "0 5 10 ... 40" dało 9 osobnych liczb).
                # Kolejność znaków zostaje taka, jak w strumieniu PDF (NIE sortujemy wg x0) -
                # przy gęstej podziałce etykiety mogą się wizualnie nachodzić, a sortowanie
                # po x0 przestawiałoby wtedy kolejność cyfr na błędną.
                chars = [c for c in el if isinstance(c, LTChar)]
                for c in chars:
                    handled_ids.add(id(c))
                if not chars:
                    t = el.get_text().strip()
                    if t:
                        texts.append((t, el.bbox))
                    continue
                _tokenize_chars(chars, texts)
        # Zapasowa metoda: znaki, które NIE zostały objęte żadną LTTextLineHorizontal
        # (w niektórych PDF-ach - np. część kart z programu Geoteko - dotyczy to
        # wszystkich albo prawie wszystkich znaków na stronie) grupujemy sami po
        # zbliżonej współrzędnej Y (ta sama linia wizualna), zachowując kolejność ze
        # strumienia PDF (poprawna kolejność odczytu).
        leftover = [c for c in raw_chars if id(c) not in handled_ids]
        if leftover:
            by_y = defaultdict(list)
            for c in leftover:
                by_y[round(c.y0, 0)].append(c)
            for y_key in sorted(by_y):
                _tokenize_chars(by_y[y_key], texts)
    return lines, texts


def _tokenize_chars(chars, texts):
    """Rozbija listę znaków (w kolejności odczytu) na tokeny liczbowe po przerwach w x."""
    if not chars:
        return
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
    if not frames:
        return []
    # Może być więcej niż jedna "grupa" paneli na stronie (np. surowe dane i gotowa
    # interpretacja jedna nad drugą, jak w formacie Geoteko) - grupujemy po pełnej
    # pozycji (dół,góra), NIE samej wysokości (dwie różne grupy mogą mieć przypadkiem
    # identyczną wysokość, ale inną pozycję). Zachowujemy WSZYSTKIE spójne grupy -
    # właściwy zestaw 4 krzywych (qc/fs/u2/Rf) i tak zostanie wybrany później po
    # kolorze linii lub etykiecie osi, nie po pozycji na stronie.
    pos_key = Counter((round(f[1], 0), round(f[3], 0)) for f in frames)
    valid_pos = {k for k, cnt in pos_key.items() if cnt >= 3}
    panels = [f for f in frames if (round(f[1], 0), round(f[3], 0)) in valid_pos]
    panels = sorted(set(panels), key=lambda f: f[0])
    # w obrębie KAŻDEJ grupy odfiltruj ramki o niespójnej szerokości (np.
    # fałszywe, podwójnie szerokie dopasowania, gdy dodatkowa kolumna z opisem
    # litologii ma inną szerokość niż panele z danymi)
    filtered = []
    for k in valid_pos:
        group = [f for f in panels if (round(f[1], 0), round(f[3], 0)) == k]
        widths = Counter(round(f[2] - f[0], -1) for f in group)
        common_w = widths.most_common(1)[0][0]
        filtered += [f for f in group if abs(round(f[2] - f[0], -1) - common_w) < 1]
    panels = sorted(set(filtered), key=lambda f: (-f[1], f[0]))  # grupy od góry strony, w grupie od lewej
    # usuń duplikaty/zawieranie się (porównanie x ORAZ y - inaczej pomyliłoby panele
    # należące do różnych grup/wykresów ułożonych jeden nad drugim na tej samej stronie)
    dedup = []
    for f in panels:
        if not any(abs(f[0]-g[0]) < 1 and abs(f[2]-g[2]) < 1 and abs(f[1]-g[1]) < 1 for g in dedup):
            dedup.append(f)
    return sorted(dedup, key=lambda f: (-f[1], f[0]))


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
    # odrzuć liczby leżące wyraźnie na lewo od ramki (przeciek etykiety/adnotacji
    # z sąsiedniego panelu, złapany przez tolerancję pozycyjną _nearby_numbers)
    nums = [n for n in nums if n[1] >= x0 - 1]
    if len(nums) < 2:
        return None
    nums.sort(key=lambda n: n[1])  # sortuj wg pozycji x
    if len(nums) == 2:
        v_a, x_a = nums[0][0], nums[0][1]
        v_b, x_b = nums[1][0], nums[1][1]
        if x_b == x_a:
            return None
        step = (v_b - v_a) / (x_b - x_a)
        return dict(x0=x_a, x1=x1, v0=v_a, v1=v_a + step * (x1 - x_a))
    # 3+ punktów: mediana nachyleń między wszystkimi parami - odporna na pojedynczy
    # zepsuty odczyt (np. etykiety sąsiednich paneli nachodzące na granicy, gubiące
    # znak "-" przy wartościach ujemnych). Punkt odniesienia: mediana wartości x.
    slopes = []
    for i in range(len(nums)):
        for j in range(i + 1, len(nums)):
            dx = nums[j][1] - nums[i][1]
            if dx > 1:
                slopes.append((nums[j][0] - nums[i][0]) / dx)
    if not slopes:
        return None
    slopes.sort()
    step = slopes[len(slopes) // 2]
    # punkt odniesienia najbliższy medianie x (mniej narażony na zniekształcenia brzegowe)
    xs = [n[1] for n in nums]
    xs.sort()
    x_med = xs[len(xs) // 2]
    ref = min(nums, key=lambda n: abs(n[1] - x_med))
    v_ref, x_ref = ref[0], ref[1]
    return dict(x0=nums[0][1], x1=x1, v0=v_ref + step * (nums[0][1] - x_ref),
                v1=v_ref + step * (x1 - x_ref))


def _calibrate_depth_axis(texts, frames):
    left = min(f[0] for f in frames)
    y0 = min(f[1] for f in frames)
    y1 = max(f[3] for f in frames)
    nums = _nearby_numbers(texts, x_range=(left - 60, left - 2), y_range=(y0 - 5, y1 + 5))
    if len(nums) < 2:
        return None
    nums.sort(key=lambda n: -n[2])  # od góry (małe y głębokości) do dołu
    # odrzuć punkty łamiące monotoniczność (np. przeciek liczby z sąsiedniego panelu
    # tuż za granicą szukanego obszaru) - głębokość musi rosnąć w dół strony
    clean = [nums[0]]
    for n in nums[1:]:
        if n[0] >= clean[-1][0]:
            clean.append(n)
    nums = clean
    if len(nums) < 2:
        return None
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

CURVE_KEYWORDS = {
    "qc [MPa]": ("qc",),
    "fs [MPa]": ("fs",),
    "u2 [MPa]": ("u2",),
    "Rf(qc) [%]": ("rf", "rf(qc)"),
}


def _curve_linewidth(lines, color):
    """Najczęstsza szerokość linii dla danego koloru krzywej - używana do
    odróżnienia krzywej Rf (kolor czarny) od czarnych linii ramki/siatki,
    których szerokość bywa inna w różnych programach generujących karty."""
    ref_lw = Counter(round(l.linewidth, 2) for l in lines
                      if l.stroking_color == (0.0, 0.0, 1.0) and l.linewidth).most_common(1)
    return ref_lw[0][0] if ref_lw else 0.28


def _title_match(texts, frame, keywords):
    """Szuka etykiety osi (np. 'qc [MPa]') w paśmie nad daną ramką panelu.
    Używane jako sygnał identyfikacji krzywej, gdy wszystkie krzywe mają ten sam
    kolor (spotykane np. w kartach z programu Geoteko) i samo dopasowanie po
    kolorze nie wystarcza."""
    x0, y0, x1, y1 = frame
    for t, box in texts:
        tx0, ty0, tx1, ty1 = box
        cx = (tx0 + tx1) / 2
        if x0 - 5 <= cx <= x1 + 5 and y1 - 2 <= ty0 <= y1 + 45:
            low = re.sub(r"[^a-z0-9()]", "", t.lower())
            if low in keywords:
                return True
    return False


def _guess_test_id(texts, page_num):
    """Próbuje odgadnąć numer/nazwę sondowania z tekstu na stronie (np. 'D1', 'CPT-3').
    W razie niepowodzenia zwraca numer strony jako etykietę zapasową."""
    candidates = Counter()
    for t, box in texts:
        if re.fullmatch(r"[A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]{1,6}[-_]?\d{1,4}", t) and not t.isdigit():
            candidates[t] += 1
    if candidates:
        return candidates.most_common(1)[0][0]
    return f"strona {page_num + 1}"


def extract_cpt(pdf_path, depth_negative=True, page_index=0):
    lines, texts = _load_page_objects(pdf_path, page_index=page_index)
    frames = _find_frames(lines)
    if len(frames) < 4:
        raise ValueError(f"Nie znaleziono 4 paneli wykresu (znaleziono {len(frames)}). "
                          "Sprawdź, czy PDF zawiera wektorowe wykresy CPTU.")

    curve_lw = _curve_linewidth(lines, (0.0, 0.0, 1.0))

    def lines_for_color(name, color):
        if name == "Rf(qc) [%]":
            return [l for l in lines if l.stroking_color == 0.0 and l.linewidth
                    and abs(l.linewidth - curve_lw) < 0.05]
        return [l for l in lines if l.stroking_color == color]

    color_lines = {name: lines_for_color(name, color) for name, color in CURVE_COLORS}

    # Jeśli kolorowych obiektów (poza czarną Rf) jest bardzo mało, panele identyfikujemy
    # po etykiecie osi (np. "qc [MPa]") zamiast po kolorze - dotyczy PDF-ów, gdzie same
    # ramki/siatka zdominowały by dopasowanie po kolorze (np. gdy krzywa jest jednym
    # wielopunktowym obiektem, a nie setkami osobnych odcinków).
    distinct_color_total = sum(len(color_lines[n]) for n in ["qc [MPa]", "fs [MPa]", "u2 [MPa]"])
    use_title_matching = distinct_color_total < 20

    # przypisz każdej ramce tę krzywą, której najwięcej segmentów mieści się w jej zakresie x
    # (odporne na inną kolejność paneli w różnych programach, np. Rf/U2 zamienione miejscami)
    assigned = {}
    used_frames = set()
    if use_title_matching:
        for name, keywords in CURVE_KEYWORDS.items():
            for i, f in enumerate(frames):
                if i in used_frames:
                    continue
                if _title_match(texts, f, keywords):
                    assigned[name] = f
                    used_frames.add(i)
                    break
    else:
        for name in [n for n, _ in CURVE_COLORS]:
            counts = []
            for i, f in enumerate(frames):
                if i in used_frames:
                    continue
                fx0, fx1 = f[0], f[2]
                cnt = sum(1 for l in color_lines[name] if fx0 - 1 <= l.x0 <= fx1 + 1 and fx0 - 1 <= l.x1 <= fx1 + 1)
                counts.append((cnt, i))
            if not counts:
                continue
            best_cnt, best_i = max(counts)
            if best_cnt > 0:
                assigned[name] = frames[best_i]
                used_frames.add(best_i)

    missing = [n for n, _ in CURVE_COLORS if n not in assigned]
    if missing:
        raise ValueError(f"Nie udało się rozpoznać paneli dla: {', '.join(missing)}. "
                          "Sprawdź, czy PDF zawiera wektorowe wykresy CPTU w standardowym układzie.")

    depth_cal = _calibrate_depth_axis(texts, list(assigned.values()))
    if depth_cal is None:
        raise ValueError("Nie udało się skalibrować osi głębokości (brak podpisów liczbowych).")

    def depth_from_y(y):
        return depth_cal["a"] * y + depth_cal["b"]

    Y0, Y1 = depth_cal["y0"], depth_cal["y1"]

    import pandas as pd
    series = {}
    for name, _ in CURVE_COLORS:
        frame = assigned[name]
        xcal = _calibrate_x_axis(texts, frame)
        if xcal is None:
            raise ValueError(f"Nie udało się skalibrować osi wartości dla panelu {name}.")
        fx0, fy0, fx1, fy1 = frame
        # Kandydaci: obiekty o kolorze pasującym do konwencji krzywych CPTU (niebieski/
        # czerwony/bordowy/czarny) - NIE dowolny kolor, bo szara siatka wykresu ma
        # zwykle więcej odcinków niż sama krzywa i wygrałaby błędnie. Wybieramy kolor
        # o największej łącznej liczbie punktów spośród tych kandydatów.
        plausible_colors = {(0.0, 0.0, 1.0), (1.0, 0.0, 0.0), (0.502, 0.0, 0.0), 0.0}
        candidates = [l for l in lines
                      if l.x0 >= fx0 - 1 and l.x1 <= fx1 + 1 and l.y0 >= Y0 - 1 and l.y1 <= Y1 + 1
                      and l.stroking_color in plausible_colors]
        point_counts = Counter()
        for l in candidates:
            npts = len(l.pts) if getattr(l, "pts", None) and len(l.pts) > 2 else 2
            point_counts[l.stroking_color] += npts
        sel = []
        if point_counts:
            best_color = point_counts.most_common(1)[0][0]
            sel = [l for l in candidates if l.stroking_color == best_color]
        pts = set()
        for l in sel:
            if getattr(l, "pts", None) and len(l.pts) > 2:
                for px, py in l.pts:
                    pts.add((px, py))
            else:
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


def count_pages(pdf_path):
    return len(list(extract_pages(pdf_path)))


def extract_all_soundings(pdf_path, depth_negative=True):
    """Wyciąga WSZYSTKIE sondowania z pliku PDF - jedna strona = jedno sondowanie
    (spotykane np. w plikach zbiorczych z programu Geoteko, gdzie każda strona
    zawiera osobny test CPTU). Zwraca listę dict: {test_id, df, page}.
    Strony, których nie da się przetworzyć (np. inny układ, brak wykresu), są
    pomijane - błąd zapisany w polu 'error'.
    """
    n_pages = count_pages(pdf_path)
    results = []
    for i in range(n_pages):
        try:
            lines, texts = _load_page_objects(pdf_path, page_index=i)
            test_id = _guess_test_id(texts, i)
            df = extract_cpt(pdf_path, depth_negative=depth_negative, page_index=i)
            results.append(dict(test_id=test_id, df=df, page=i + 1, error=None))
        except Exception as e:
            results.append(dict(test_id=f"strona {i + 1}", df=None, page=i + 1, error=str(e)))
    return results
