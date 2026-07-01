"""
Interpretacja CPTU wg metod Robertsona (CPT Guide, 6th ed. 2015) i Kulhawy'ego & Mayne'a (1990).
Wejście: profil qc, fs, u2 (MPa) w funkcji głębokości (m).
Wyjście: pełny profil parametrów geotechnicznych.
"""
import numpy as np
import pandas as pd

PA = 100.0      # kPa, cisnienie referencyjne
GAMMA_W = 9.81  # kN/m3

SBT_TABLE = [
    # (Ic_max, zone, description)
    (1.31, 7, "Żwir do gęstego piasku"),
    (2.05, 6, "Piasek: piasek czysty do piasku pylastego"),
    (2.60, 5, "Mieszanina piasku: piasek pylasty do pyłu piaszczystego"),
    (2.95, 4, "Mieszanina pyłu: pył ilasty do gliny pylastej"),
    (3.60, 3, "Glina: glina pylasta do gliny"),
    (999,  2, "Grunt organiczny - namuł"),
]

def sbt_zone(ic):
    if np.isnan(ic):
        return np.nan, "brak danych"
    for ic_max, zone, desc in SBT_TABLE:
        if ic <= ic_max:
            return zone, desc
    return 2, "Grunt organiczny - namuł"


def compute_profile(df, gwl=0.0, area_ratio=0.8, nkt=15.0, gamma_init=18.0):
    """
    df: kolumny 'Głębokość [m]', 'qc [MPa]', 'fs [MPa]', 'u2 [MPa]'
    gwl: głębokość zwierciadła wody gruntowej [m p.p.t.]
    area_ratio: współczynnik powierzchni netto stożka 'a' (typowo 0.55-0.85)
    nkt: współczynnik stożka do wyznaczania su (typowo 14-18)
    """
    d = df.sort_values("Głębokość [m]").reset_index(drop=True).copy()
    n = len(d)
    z = d["Głębokość [m]"].values
    qc = np.clip(d["qc [MPa]"].values, 0.001, None)
    fs = np.clip(d["fs [MPa]"].values, 0.0001, None)
    u2 = d["u2 [MPa]"].values

    qt = qc + u2 * (1 - area_ratio)  # MPa

    gamma = np.full(n, gamma_init)
    sigma_v = np.zeros(n)   # kPa
    sigma_v0 = np.zeros(n)  # kPa (efektywne)
    u0 = np.zeros(n)

    Rf = np.zeros(n)
    Qt = np.zeros(n)
    Fr = np.zeros(n)
    Bq = np.zeros(n)
    Ic = np.zeros(n)
    Qtn = np.zeros(n)

    # iteracyjne wyznaczenie gamma / naprężeń / Ic (2 przebiegi wystarczają do zbieżności)
    for _pass in range(3):
        prev_z = 0.0
        sv = 0.0
        for i in range(n):
            dz = z[i] - prev_z
            sv += gamma[i] * max(dz, 0)
            sigma_v[i] = sv
            u0[i] = GAMMA_W * max(z[i] - gwl, 0)
            sigma_v0[i] = max(sv - u0[i], 1.0)
            prev_z = z[i]

        qt_kpa = qt * 1000.0
        fs_kpa = fs * 1000.0
        u2_kpa = u2 * 1000.0
        qn = np.clip(qt_kpa - sigma_v, 1.0, None)

        Rf_ = (fs / qt) * 100.0
        Fr_ = (fs_kpa / qn) * 100.0
        Bq_ = (u2_kpa - u0) / qn

        n_exp = np.full(n, 1.0)
        for _ in range(4):
            Qtn_ = (qn / PA) * (PA / sigma_v0) ** n_exp
            Qtn_ = np.clip(Qtn_, 1.0, None)
            Ic_ = np.sqrt((3.47 - np.log10(Qtn_)) ** 2 + (np.log10(np.clip(Fr_, 0.01, None)) + 1.22) ** 2)
            n_exp = np.clip(0.381 * Ic_ + 0.05 * (sigma_v0 / PA) - 0.15, 0.5, 1.0)

        Rf, Fr, Bq, Ic, Qtn = Rf_, Fr_, Bq_, Ic_, Qtn_
        Qt = qn / sigma_v0

        Rf_safe = np.clip(Rf, 0.05, None)
        gamma = GAMMA_W * (0.27 * np.log10(Rf_safe) + 0.36 * np.log10(qt_kpa / PA) + 1.236)
        gamma = np.clip(gamma, 12.0, 22.0)

    qn = np.clip(qt * 1000.0 - sigma_v, 1.0, None)

    # SBTn
    zones, descs = zip(*[sbt_zone(v) for v in Ic])
    zones = np.array(zones, dtype=float)

    # N60 (Robertson 2012, na bazie Ic)
    N60 = (qt * 1000.0 / PA) / (10 ** (1.1268 - 0.2817 * Ic))

    # Dr (tylko grunty niespoiste, Ic < 2.60) wg Kulhawy&Mayne (uproszczone Robertson: Dr^2 = Qtn/350)
    Dr = np.where(Ic < 2.60, np.sqrt(np.clip(Qtn, 0, None) / 350.0) * 100.0, np.nan)
    Dr = np.clip(Dr, 0, 100)

    # kat tarcia wewnetrznego
    phi_sand = 17.6 + 11 * np.log10(np.clip(Qtn, 1, None))
    Bq_pos = np.clip(Bq, 0.001, None)
    phi_nth = 29.5 * Bq_pos ** 0.121 * (0.256 + 0.336 * Bq_pos + np.log10(np.clip(Qt, 0.1, None)))
    phi_clay_default = 28.0
    phi = np.where(Ic < 2.60, phi_sand,
                   np.where(Bq > 0.1, phi_nth, phi_clay_default))
    phi = np.clip(phi, 15, 45)

    # moduly
    alpha_E = 0.015 * (10 ** (0.55 * Ic + 1.68))
    Es = np.where(Ic < 2.60, alpha_E * qn / 1000.0, np.nan)  # MPa

    alpha_M_fine = np.clip(Qt, None, 14.0)
    alpha_M_coarse = 0.0188 * (10 ** (0.55 * Ic + 1.68))
    alpha_M = np.where(Ic > 2.2, alpha_M_fine, alpha_M_coarse)
    M = alpha_M * qn / 1000.0  # MPa

    alpha_vs = 10 ** (0.55 * Ic + 1.68)
    Vs = np.sqrt(alpha_vs * qn / PA)  # m/s
    rho = gamma / GAMMA_W  # t/m3 (gamma_w=9.81 -> rho w Mg/m3 przy sile ciezkosci ~9.81)
    Go = rho * Vs ** 2 / 1000.0  # MPa

    # su, su/sigma'v, OCR (tylko grunty spoiste, Ic > 2.60)
    fine = Ic > 2.60
    Su = np.where(fine, qn / nkt, np.nan)  # kPa
    Su_ratio = np.where(fine, Su / sigma_v0, np.nan)
    OCR_robertson = np.where(fine, 0.25 * np.clip(Qt, 0.01, None) ** 1.25, np.nan)
    OCR_km = np.where(fine, 0.33 * Qt, np.nan)
    Ko = np.where(fine, 0.5 * np.sqrt(np.clip((OCR_robertson + OCR_km) / 2, 0, None)), np.nan)

    # wodoprzepuszczalnosc k (Robertson 2010), wg zakresu Ic
    k_perm = np.where(Ic <= 3.27,
                       10 ** (0.952 - 3.04 * Ic),
                       10 ** (-4.52 - 1.37 * Ic))  # m/s

    out = pd.DataFrame({
        "Głębokość [m]": z,
        "qc [MPa]": qc, "fs [MPa]": fs, "u2 [MPa]": u2, "qt [MPa]": qt,
        "sigma_v [kPa]": sigma_v, "u0 [kPa]": u0, "sigma_v0 [kPa]": sigma_v0,
        "Rf [%]": Rf, "Qt [-]": Qt, "Qtn [-]": Qtn, "Fr [%]": Fr, "Bq [-]": Bq,
        "Ic [-]": Ic, "SBTn zone": zones, "SBTn opis": descs,
        "gamma [kN/m3]": gamma,
        "N60 [-]": N60, "Dr [%]": Dr, "phi [deg]": phi,
        "Es [MPa]": Es, "M [MPa]": M, "Vs [m/s]": Vs, "Go [MPa]": Go,
        "Su [kPa]": Su, "Su/sigma'v0 [-]": Su_ratio,
        "OCR (Robertson 2009) [-]": OCR_robertson, "OCR (Kulhawy-Mayne) [-]": OCR_km,
        "Ko [-]": Ko, "k [m/s]": k_perm,
    })
    return out
