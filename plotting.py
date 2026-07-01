import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ZONE_COLORS = {
    2: "#8B5A2B", 3: "#6B8E23", 4: "#4682B4", 5: "#DAA520",
    6: "#D2B48C", 7: "#A9A9A9",
}
ZONE_LABELS = {
    2: "Namuł/org.", 3: "Glina", 4: "Pył/glina pyl.",
    5: "Piasek pylasty", 6: "Piasek", 7: "Piasek gęsty/żwir",
}

def make_profile_figure(profile, layers, title="CPTU – profil interpretacyjny"):
    z = -profile["Głębokość [m]"]
    zmax = -z.min()

    fig, axes = plt.subplots(1, 6, figsize=(16, 11), sharey=True)
    fig.suptitle(title, fontsize=13, fontweight="bold")

    # panel 1: qt, fs*10
    ax = axes[0]
    ax.plot(profile["qt [MPa]"], z, color="blue", lw=0.7)
    ax.set_xlabel("qt [MPa]")
    ax.set_title("Opór stożka", fontsize=9)

    # panel 2: Ic + SBTn shading
    ax = axes[1]
    for _, row in layers.iterrows():
        color = ZONE_COLORS.get(int(row["Strefa SBTn"]) if not np.isnan(row["Strefa SBTn"]) else 6, "#CCCCCC")
        ax.axhspan(-row["Od [m]"], -row["Do [m]"], color=color, alpha=0.5)
    ax.plot(profile["Ic [-]"], z, color="black", lw=0.6)
    ax.set_xlabel("Ic [-]")
    ax.set_xlim(1, 4)
    ax.set_title("SBTn (Robertson)", fontsize=9)

    # panel 3: gamma
    ax = axes[2]
    ax.plot(profile["gamma [kN/m3]"], z, color="saddlebrown", lw=0.7)
    ax.set_xlabel("γ [kN/m³]")
    ax.set_title("Ciężar objętościowy", fontsize=9)

    # panel 4: phi & Dr
    ax = axes[3]
    ax.plot(profile["phi [deg]"], z, color="darkorange", lw=0.7, label="φ' [°]")
    ax.set_xlabel("φ' [°]", color="darkorange")
    ax2 = ax.twiny()
    ax2.plot(profile["Dr [%]"], z, color="teal", lw=0.7, label="Dr [%]")
    ax2.set_xlabel("Dr [%]", color="teal")
    ax.set_title("φ' i Dr (grunty niespoiste)", fontsize=9)

    # panel 5: Es, M
    ax = axes[4]
    ax.plot(profile["Es [MPa]"], z, color="purple", lw=0.6, label="Es")
    ax.plot(profile["M [MPa]"], z, color="green", lw=0.6, label="M")
    ax.set_xlabel("Es, M [MPa]")
    ax.legend(fontsize=6, loc="lower right")
    ax.set_title("Moduły odkształcenia", fontsize=9)

    # panel 6: Su & OCR
    ax = axes[5]
    ax.plot(profile["Su [kPa]"], z, color="red", lw=0.8, label="Su [kPa]")
    ax.set_xlabel("Su [kPa]", color="red")
    ax3 = ax.twiny()
    ax3.plot(profile["OCR (Robertson 2009) [-]"], z, color="black", lw=0.6, ls="--", label="OCR")
    ax3.set_xlabel("OCR [-]", color="black")
    ax.set_title("Su i OCR (grunty spoiste)", fontsize=9)

    for ax in axes:
        ax.grid(True, alpha=0.3)
    axes[0].set_ylabel("Głębokość [m] (0 = powierzchnia terenu)")

    # legenda stref SBTn
    handles = [plt.Rectangle((0, 0), 1, 1, color=c, alpha=0.5) for c in ZONE_COLORS.values()]
    labels = list(ZONE_LABELS.values())
    fig.legend(handles, labels, loc="lower center", ncol=6, fontsize=8, bbox_to_anchor=(0.5, 0.0))

    plt.tight_layout(rect=[0, 0.05, 1, 0.96])
    return fig
