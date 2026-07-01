import numpy as np
import pandas as pd
from calc import sbt_zone

def detect_layers(profile, min_thickness=0.30, smooth_window=15):
    """Automatyczny podzial na warstwy na podstawie wygladzonego wskaznika Ic (SBTn)."""
    d = profile.copy().reset_index(drop=True)
    ic_smooth = d["Ic [-]"].rolling(smooth_window, center=True, min_periods=1).median()
    zones = ic_smooth.apply(lambda v: sbt_zone(v)[0])

    # scal sasiednie punkty o tej samej strefie w segmenty
    seg_id = (zones != zones.shift()).cumsum()
    segs = []
    for sid, grp in d.groupby(seg_id):
        z0, z1 = grp["Głębokość [m]"].iloc[0], grp["Głębokość [m]"].iloc[-1]
        segs.append(dict(start=z0, end=z1, zone=zones.loc[grp.index].iloc[0], idx=grp.index.tolist()))

    # scal cienkie segmenty z sasiednim segmentem - ale TYLKO jesli sasiad jest podobnego typu gruntu.
    # Cienka, ale KONTRASTOWA warstwa (np. torf/glina w piasku) NIE jest scalana, bo to zwykle
    # geotechnicznie najważniejsza przekładka - zamiast tego zostaje oznaczona jako wymagająca uwagi.
    # Twardy próg poniżej którego traktujemy segment jako szum pomiarowy (zawsze scalany):
    noise_floor = 0.10
    changed = True
    while changed:
        changed = False
        for i, s in enumerate(segs):
            thickness = s["end"] - s["start"]
            if thickness < min_thickness and len(segs) > 1:
                candidates = []
                if i > 0:
                    candidates.append(i - 1)
                if i < len(segs) - 1:
                    candidates.append(i + 1)
                # kontrast do kazdego sasiada
                contrasts = {j: abs(s["zone"] - segs[j]["zone"]) for j in candidates}
                similar = [j for j in candidates if contrasts[j] <= 1]
                if thickness < noise_floor:
                    # zbyt cienkie, żeby było wiarygodne - scal z najbliższym sąsiadem niezależnie od kontrastu
                    pool = candidates
                elif similar:
                    # scalaj tylko z podobnym sąsiadem (bezpieczne scalenie transytowe)
                    pool = similar
                else:
                    # kontrastowa cienka warstwa, np. przekładka torfu/gliny w piasku -> NIE scalaj
                    s["protected"] = True
                    continue
                nb = min(pool, key=lambda j: segs[j]["end"] - segs[j]["start"]) if False else \
                     max(pool, key=lambda j: segs[j]["end"] - segs[j]["start"])
                lo, hi = sorted([i, nb])
                merged = dict(start=segs[lo]["start"], end=segs[hi]["end"],
                              zone=segs[lo]["zone"] if (segs[lo]["end"]-segs[lo]["start"]) >= (segs[hi]["end"]-segs[hi]["start"]) else segs[hi]["zone"],
                              idx=segs[lo]["idx"] + segs[hi]["idx"])
                segs = segs[:lo] + [merged] + segs[hi+1:]
                changed = True
                break

    rows = []
    for s in segs:
        sub = d.loc[s["idx"]]
        zone, desc = sbt_zone(sub["Ic [-]"].median())
        is_fine = zone <= 4       # grunt spoisty/pyłowy -> Su, OCR mają sens
        is_coarse = zone >= 5     # grunt niespoisty -> Dr, Es mają sens
        thickness = round(s["end"] - s["start"], 2)
        row = {
            "Od [m]": round(s["start"], 2), "Do [m]": round(s["end"], 2),
            "Miąższość [m]": thickness,
            "Strefa SBTn": zone, "Opis": desc,
            "Uwaga": "cienka warstwa kontrastowa - zweryfikuj" if (s.get("protected") and thickness < min_thickness) else "",
        }
        gated_cols = {
            "Dr [%]": is_coarse, "Es [MPa]": is_coarse,
            "Su [kPa]": is_fine, "Su/sigma'v0 [-]": is_fine,
            "OCR (Robertson 2009) [-]": is_fine, "OCR (Kulhawy-Mayne) [-]": is_fine,
        }
        for col in ["qt [MPa]", "Rf [%]", "Ic [-]", "gamma [kN/m3]", "N60 [-]",
                    "Dr [%]", "phi [deg]", "Es [MPa]", "M [MPa]", "Go [MPa]",
                    "Su [kPa]", "Su/sigma'v0 [-]", "OCR (Robertson 2009) [-]", "OCR (Kulhawy-Mayne) [-]",
                    "k [m/s]"]:
            if col in gated_cols and not gated_cols[col]:
                row[col + " śr"] = np.nan
                row[col + " std"] = np.nan
                continue
            vals = sub[col].dropna()
            if col == "k [m/s]":
                # srednia geometryczna (arytmetyczna myli przy wartościach na wielu rzędach wielkości)
                vals = vals[vals > 0]
                row[col + " śr"] = float(10 ** np.log10(vals).mean()) if len(vals) else np.nan
                row[col + " std"] = np.nan
                continue
            row[col + " śr"] = round(vals.mean(), 2) if len(vals) else np.nan
            row[col + " std"] = round(vals.std(), 2) if len(vals) > 1 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
