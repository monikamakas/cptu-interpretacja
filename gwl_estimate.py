"""
Automatyczne szacowanie zwierciadła wody gruntowej (ZWG) na podstawie u2
w płytkiej, czystej warstwie piaszczystej (gdzie nadciśnienie wciskania
szybko dysypuje, więc u2 ≈ ciśnienie hydrostatyczne).
"""
import numpy as np
import pandas as pd
from calc import compute_profile

GAMMA_W = 9.81


def estimate_gwl(raw_df, max_search_depth=10.0, min_run_m=0.3, ic_threshold=1.9):
    """
    raw_df: kolumny 'Głębokość [m]', 'qc [MPa]', 'fs [MPa]', 'u2 [MPa]'
    Zwraca dict: {gwl, low, high, n_points, method, ok}
    """
    prof0 = compute_profile(raw_df, gwl=0.0, area_ratio=0.8, nkt=15.0)
    z = prof0["Głębokość [m]"].values
    Ic = prof0["Ic [-]"].values
    u2_kpa = raw_df["u2 [MPa]"].values * 1000.0

    sand = (Ic < ic_threshold) & (z <= max_search_depth) & (z > 0.1)
    if sand.sum() < 10:
        return dict(gwl=0.0, low=None, high=None, n_points=0, ok=False,
                     method="Brak wystarczająco czystej, płytkiej warstwy piaszczystej – ZWG nieoszacowane, ustaw ręcznie.")

    # znajdz najplytszy ciagly odcinek piasku o dlugosci >= min_run_m
    idx = np.where(sand)[0]
    runs = np.split(idx, np.where(np.diff(idx) != 1)[0] + 1)
    runs = [r for r in runs if (z[r[-1]] - z[r[0]]) >= min_run_m]
    if not runs:
        return dict(gwl=0.0, low=None, high=None, n_points=0, ok=False,
                     method="Brak wystarczająco długiego, ciągłego odcinka piasku – ZWG nieoszacowane, ustaw ręcznie.")
    run = runs[0]  # najplytszy

    zz = z[run]
    uu = u2_kpa[run]
    gwl_points = zz - uu / GAMMA_W
    gwl = float(np.median(gwl_points))
    low = float(np.percentile(gwl_points, 25))
    high = float(np.percentile(gwl_points, 75))
    return dict(gwl=round(gwl, 2), low=round(low, 2), high=round(high, 2), n_points=len(run), ok=True,
                method=f"Wyznaczone z u2 w warstwie piaszczystej {zz[0]:.2f}–{zz[-1]:.2f} m "
                       f"({len(run)} punktów), metoda: ZWG = głębokość − u2/γw.")
