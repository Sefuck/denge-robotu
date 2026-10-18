"""Rapor şekilleri (matplotlib, basılı rapora uygun statik PNG).

Renkler referans veri görselleştirme paletinin ilk üç kategorik slotudur (açık mod);
metin her zaman mürekkep tonlarındadır, seri kimliği lejant + çizgi tipiyle de taşınır.
"""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

MAVI, TURUNCU, CAMGOBEGI = "#2a78d6", "#eb6834", "#1baf7a"
MUREKKEP, IKINCIL, SOLUK = "#0b0b0b", "#52514e", "#898781"
IZGARA, EKSEN = "#e1e0d9", "#c3c2b7"
DOLGU, DOLGU_KENAR = "#ecebe6", "#b5b4ab"


def stil():
    plt.rcParams.update(
        {
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "savefig.facecolor": "white",
            "axes.edgecolor": EKSEN,
            "axes.linewidth": 0.8,
            "axes.grid": True,
            "grid.color": IZGARA,
            "grid.linewidth": 0.6,
            "axes.axisbelow": True,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "xtick.color": EKSEN,
            "ytick.color": EKSEN,
            "xtick.labelcolor": IKINCIL,
            "ytick.labelcolor": IKINCIL,
            "axes.labelcolor": IKINCIL,
            "axes.titlecolor": MUREKKEP,
            "axes.titlesize": 10,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "text.color": MUREKKEP,
            "font.size": 9,
            "lines.linewidth": 1.6,
            "lines.solid_capstyle": "round",
            "lines.solid_joinstyle": "round",
            "legend.frameon": False,
            "legend.fontsize": 8.5,
            "legend.labelcolor": IKINCIL,
            "savefig.dpi": 170,
            "savefig.bbox": "tight",
        }
    )


def _virgul(x, _pos=None):
    s = f"{x:g}"
    return s.replace("-", "−").replace(".", ",")


def _eksenler(*axs):
    for ax in axs:
        ax.xaxis.set_major_formatter(FuncFormatter(_virgul))
        ax.yaxis.set_major_formatter(FuncFormatter(_virgul))


def sayi(x, n=2):
    return f"{x:.{n}f}".replace("-", "−").replace(".", ",")


def _kaydet(fig, yol):
    fig.savefig(yol)
    plt.close(fig)


# ---------------------------------------------------------------------------
def yerlesim(yol, tasarim, yuva_secenekleri: dict, km_kutusuz, km_kutulu, z_cp):
    """Şekil 1: yan ve ön görünüşte yerleşim, KM noktaları, yuva seçenekleri."""
    stil()
    r = tasarim.d("teker.yaricap")
    d = tasarim.d("teker.iz_genisligi")
    w_t = tasarim.d("teker.genislik")
    bilesenler = tasarim.bilesenler(kutulu=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 5.2), gridspec_kw={"width_ratios": [1.0, 1.05]})

    for ax, (iy, etiket) in ((ax1, (0, "x (ileri) [m]")), (ax2, (1, "y (sol) [m]"))):
        ax.axhline(-r, color=EKSEN, lw=1.2, zorder=1)
        ax.set_aspect("equal")
        ax.set_xlabel(etiket)
        ax.set_ylabel("z (aks üstü) [m]")
        ax.grid(False)

    # Yan görünüş
    (x0, x1), (z0, z1) = tasarim.d("govde.zarf.x_aralik"), tasarim.d("govde.zarf.z_aralik")
    ax1.add_patch(mpatches.Rectangle((x0, z0), x1 - x0, z1 - z0, fill=False, ec=EKSEN, lw=0.8, zorder=2))
    ax1.add_patch(mpatches.Circle((0, 0), r, fc="white", ec=SOLUK, lw=1.2, zorder=3, alpha=0.9))
    ax1.plot(0, 0, "o", ms=3, color=SOLUK, zorder=4)
    etiketler = {}
    for b in bilesenler:
        if b.kategori == "sasi":
            continue
        x, y, z = b.konum
        dx, dy, dz = b.boyut
        renk = TURUNCU if b.kategori == "kutu" else DOLGU
        kenar = TURUNCU if b.kategori == "kutu" else DOLGU_KENAR
        for ax, (u, du) in ((ax1, (x, dx)), (ax2, (y, dy))):
            ax.add_patch(mpatches.Rectangle((u - du / 2, z - dz / 2), du, dz, fc=renk, ec=kenar, lw=0.8, zorder=5, alpha=0.95))
        ad = b.ad.replace(" (sol)", "").replace(" (sağ)", "")
        etiketler.setdefault(ad, (x + dx / 2, z))
    # Bileşen etiketleri (sağda, kılavuz çizgili)
    sirali = sorted(etiketler.items(), key=lambda kv: kv[1][1])
    y_etiket = np.linspace(-0.015, 0.29, len(sirali))
    for (ad, (xe, ze)), ye in zip(sirali, y_etiket):
        ax1.annotate(ad, xy=(xe, ze), xytext=(0.095, ye), fontsize=7.5, color=IKINCIL, va="center",
                     arrowprops=dict(arrowstyle="-", color=EKSEN, lw=0.6, shrinkA=0, shrinkB=1))
    # KM noktaları
    ax1.plot(km_kutusuz[0], km_kutusuz[2], "o", ms=8, mfc="white", mec=MUREKKEP, mew=1.5, zorder=8, label="KM, kutusuz")
    ax1.plot(km_kutulu[0], km_kutulu[2], "o", ms=8, color=MUREKKEP, mec="white", mew=1.5, zorder=8, label="KM, kutulu")
    ax1.plot(0, z_cp, marker="_", ms=14, mew=1.6, color=MAVI, zorder=8, label="Vuruş merkezi $z_{cp}$")
    # Yuva seçenekleri
    for ad, z in yuva_secenekleri.items():
        ax1.plot([-0.11, -0.085], [z, z], color=TURUNCU if ad == tasarim.d("yuk.yuva.onerilen") else SOLUK, lw=1.4)
        ax1.text(-0.112, z, {"ust": "üst", "orta": "orta", "alt": "alt"}[ad], ha="right", va="center", fontsize=7.5, color=IKINCIL)
    z_ust = max(yuva_secenekleri.values())
    ax1.text(-0.0975, z_ust + 0.03, "yuva\nseçenekleri", ha="center", fontsize=7.5, color=SOLUK)
    ax1.set_xlim(-0.14, 0.24)
    ax1.set_ylim(-0.05, max(z1, z_ust) + 0.09)
    ax1.legend(loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=3, fontsize=7.5)
    ax1.annotate(f"KM\nkutusuz {sayi(1000 * km_kutusuz[2], 0)} mm\nkutulu {sayi(1000 * km_kutulu[2], 0)} mm",
                 xy=(km_kutulu[0] - 0.006, km_kutulu[2]), xytext=(-0.138, (min(yuva_secenekleri.values()) + sorted(yuva_secenekleri.values())[1]) / 2),
                 fontsize=7.5, color=IKINCIL, va="center",
                 arrowprops=dict(arrowstyle="-", color=EKSEN, lw=0.6))
    ax1.set_title("Yan görünüş (x–z)")

    # Ön görünüş: tekerler ve gövde zarfı
    w = 0.16
    ax2.add_patch(mpatches.Rectangle((-w / 2, z0), w, z1 - z0, fill=False, ec=EKSEN, lw=0.8, zorder=2))
    for s in (-1, 1):
        ax2.add_patch(mpatches.Rectangle((s * d / 2 - w_t / 2, -r), w_t, 2 * r, fc="#d9d8d1", ec=SOLUK, lw=0.8, zorder=4))
    ax2.annotate("", xy=(d / 2, -r - 0.012), xytext=(-d / 2, -r - 0.012),
                 arrowprops=dict(arrowstyle="<->", color=SOLUK, lw=0.7), annotation_clip=False)
    ax2.text(0, -r - 0.022, f"iz genişliği d = {sayi(d * 100, 0)} cm", ha="center", va="top", fontsize=7.5, color=IKINCIL)
    ax2.plot(0, km_kutulu[2], "o", ms=8, color=MUREKKEP, mec="white", mew=1.5, zorder=8)
    kx, ky, kz = tasarim.d("yuk.kutu.boyut")
    z_kutu = tasarim.kutu_merkez_z()
    ax2.text(0, z_kutu + kz / 2 + 0.012, "ilaç kutusu (uzun kenarı yanal)", ha="center", fontsize=7.5, color=IKINCIL)
    ax2.text(-d / 2, r + 0.008, "teker", ha="center", fontsize=7.5, color=IKINCIL)
    ax2.text(d / 2, r + 0.008, "teker", ha="center", fontsize=7.5, color=IKINCIL)
    ax2.set_xlim(-0.16, 0.16)
    ax2.set_ylim(-0.08, max(z1, z_ust) + 0.09)
    ax2.set_title("Ön görünüş (y–z)")
    _eksenler(ax1, ax2)
    fig.tight_layout()
    _kaydet(fig, yol)


def kutup_haritasi(yol, kutuplar_nominal, kutuplar_Jm, sifirlar_x, Jm_deger, kutuplar_kutusuz):
    """Şekil 2: eğim alt sisteminin kutupları ve X/U sıfırları."""
    stil()
    fig, ax = plt.subplots(figsize=(7.2, 3.0))
    ax.axhline(0, color=EKSEN, lw=0.8)
    ax.axvline(0, color=EKSEN, lw=0.8)
    ax.axvspan(0, 14, color="#fbe9e1", zorder=0, lw=0)
    ax.text(13.6, 0.82, "sağ yarı düzlem (kararsız)", ha="right", va="top", fontsize=8, color=IKINCIL)
    ax.plot(np.real(kutuplar_nominal), np.imag(kutuplar_nominal), "x", ms=10, mew=2.2, color=MAVI, label="Kutup, kutulu (nominal)")
    ax.plot(np.real(kutuplar_kutusuz), np.imag(kutuplar_kutusuz) + 0.25, "x", ms=8, mew=1.6, color=CAMGOBEGI, label="Kutup, kutusuz")
    ax.plot(np.real(kutuplar_Jm), np.imag(kutuplar_Jm) - 0.25, "x", ms=8, mew=1.6, color=TURUNCU,
            label=f"Kutup, J_m = {_virgul(Jm_deger)} kg·m² (motor bilinmiyor)")
    ax.plot(np.real(sifirlar_x), np.imag(sifirlar_x), "o", ms=9, mfc="white", mec=MUREKKEP, mew=1.4, label="X/U sıfırı (nominal)")
    p = np.max(np.real(kutuplar_nominal))
    ax.annotate(f"+{sayi(p)} 1/s", xy=(p, 0), xytext=(p, 0.55), ha="center", fontsize=8, color=MUREKKEP,
                arrowprops=dict(arrowstyle="-", color=EKSEN, lw=0.6))
    ax.annotate("x, ẋ: çift kutup 0'da", xy=(0, 0), xytext=(-5.5, 0.55), ha="center", fontsize=8, color=IKINCIL,
                arrowprops=dict(arrowstyle="-", color=EKSEN, lw=0.6))
    ax.set_xlim(-14, 14)
    ax.set_ylim(-1, 1)
    ax.set_xlabel("Reel eksen [1/s]")
    ax.set_ylabel("Sanal eksen [1/s]")
    ax.set_yticks([-1, 0, 1])
    ax.legend(loc="lower left", ncol=2, fontsize=7.5, bbox_to_anchor=(0, -0.02))
    ax.set_title("Eğim alt sisteminin açık çevrim kutupları (u = τ_R + τ_L girişi)")
    _eksenler(ax)
    fig.tight_layout()
    _kaydet(fig, yol)


def dusme(yol, serbest: dict, kilitli: dict, dogrusal: dict, temas_derece: tuple[float, float], pasif_sure: float):
    """Şekil 3: ±10°'den açık çevrim düşme (θ ve x). temas_derece = (ileri, geri) yere değme açıları."""
    ileri, geri = temas_derece
    stil()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 3.4))
    for isaret in (+1, -1):
        s, k, d = serbest[isaret], kilitli[isaret], dogrusal[isaret]
        ek = "" if isaret > 0 else "_"
        ax1.plot(d["t"], np.degrees(d["theta"]), color=CAMGOBEGI, lw=1.4, ls=(0, (4, 2)), label=ek + "Doğrusal model, serbest teker")
        ax1.plot(s["t"], np.degrees(s["theta"]), color=MAVI, label=ek + "Doğrusal olmayan, serbest teker (u = 0)")
        ax1.plot(k["t"], np.degrees(k["theta"]), color=TURUNCU, label=ek + "Doğrusal olmayan, kilitli teker")
        for sim_, renk in ((s, MAVI), (k, TURUNCU)):
            ax1.plot(sim_["t"][-1], np.degrees(sim_["theta"][-1]), "o", ms=7, color=renk, mec="white", mew=1.5, zorder=5)
        ax2.plot(s["t"], 100 * s["x"], color=MAVI, label=ek + "Serbest teker")
        ax2.plot(k["t"], 100 * k["x"], color=TURUNCU, label=ek + "Kilitli teker")
        for sim_ in (s, k):
            ax2.text(sim_["t"][-1] + 0.006, 100 * sim_["x"][-1], f"θ₀ = {'+' if isaret > 0 else '−'}10°", va="center", fontsize=7.5, color=IKINCIL)
    ax1.axhline(ileri, color=SOLUK, lw=0.8)
    ax1.axhline(-geri, color=SOLUK, lw=0.8)
    ax1.text(0.005, ileri + 2, f"gövde yere değer (ileri {sayi(ileri, 1)}°)", fontsize=7.5, color=IKINCIL)
    ax1.text(0.005, -geri - 2, f"gövde yere değer (geri {sayi(geri, 1)}°)", fontsize=7.5, color=IKINCIL, va="top")
    tk = max(kilitli[1]["t"][-1], kilitli[-1]["t"][-1])
    for isaret, aci in ((1, ileri), (-1, -geri)):
        for sim_ in (serbest[isaret], kilitli[isaret]):
            ax1.text(sim_["t"][-1] + 0.008, aci - isaret * 5, f"{sayi(sim_['t'][-1])} s", fontsize=8, color=MUREKKEP, va="center")
    ax1.set_xlim(0, tk * 1.3)
    ax1.set_ylim(-geri * 1.25, ileri * 1.25)
    ax1.set_xlabel("t [s]")
    ax1.set_ylabel("θ [°]")
    ax1.set_title("Gövde eğimi: ±10°'den bırakma, motorlar enerjisiz")
    ax1.legend(loc="center right", fontsize=7)
    ax1.text(tk * 1.28, ileri * 1.2, f"pasif test sınırı: {sayi(pasif_sure, 0)} s", ha="right", fontsize=7.5, color=SOLUK)
    ax2.set_xlim(0, tk * 1.3)
    ax2.set_xlabel("t [s]")
    ax2.set_ylabel("Aks konumu x [cm]")
    ax2.set_title("Aks konumu: serbest teker gövdenin tersine kaçar")
    ax2.legend(loc="upper left", fontsize=7.5)
    _eksenler(ax1, ax2)
    fig.tight_layout()
    _kaydet(fig, yol)


def toparlanma(yol, ref: dict, el_toplam: float, tutma: float, cekis: float, T: float):
    """Şekil 4: referans toparlanma manevrası."""
    stil()
    nl = ref["dogrusal_olmayan"]
    t = ref["t"]
    fig, axs = plt.subplots(3, 1, figsize=(7.4, 6.4), sharex=True)
    axs[0].plot(t, np.degrees(ref["theta"]), color=MAVI)
    axs[0].axhline(0, color=EKSEN, lw=0.8)
    axs[0].set_ylabel("θ [°]")
    axs[0].set_title(f"Referans toparlanma manevrası: +10°'den durağana, T = {sayi(T, 1)} s (kontrolcü değildir)")
    axs[1].plot(t, nl["xd"], color=MAVI, label="ẋ (doğrusal olmayan)")
    axs[1].plot(t, nl["x"], color=CAMGOBEGI, ls=(0, (4, 2)), label="x [m]")
    axs[1].set_ylabel("ẋ [m/s], x [m]")
    axs[1].legend(loc="upper right")
    axs[2].plot(t, nl["u"], color=MAVI, label="Doğrusal olmayan model (ters dinamik)")
    axs[2].plot(t, ref["u"], color=CAMGOBEGI, ls=(0, (4, 2)), label="Doğrusal model")
    for deger, metin in ((el_toplam, r"el hesabı $m g l \sin 10° + J_O \ddot{\theta}_r$"), (cekis, "çekiş sınırı μ·m·g·r"), (tutma, "10°'de tutma torku (tam model)")):
        axs[2].axhline(deger, color=SOLUK, lw=0.8)
        axs[2].text(t[-1], deger, f"{metin}: {sayi(deger, 3)} N·m", ha="right", va="bottom", fontsize=7.5, color=IKINCIL)
    axs[2].set_ylabel("τ_R + τ_L [N·m]")
    axs[2].set_xlabel("t [s]")
    axs[2].set_ylim(min(0, nl["u"].min()) * 1.3 - 0.02, cekis * 1.15)
    axs[2].legend(loc="center right", fontsize=7.5, bbox_to_anchor=(1.0, 0.45))
    _eksenler(*axs)
    fig.tight_layout()
    _kaydet(fig, yol)


def tork_sure(yol, tarama: dict, tutma: float, el_toplam: float, cekis: float, r: float):
    """Şekil 5: manevra süresine göre tepe tork ve tepe teker devri."""
    stil()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 3.3))
    T = tarama["T"]
    ax1.plot(T, tarama["u_dogrusal_olmayan"], "-o", ms=4.5, color=MAVI, mec="white", mew=1.0, label="Tepe tork, referans manevra")
    for deger, metin, va in ((el_toplam, "el hesabı", "bottom"), (cekis, "çekiş sınırı", "bottom"), (tutma, "tutma torku (asimptot)", "top")):
        ax1.axhline(deger, color=SOLUK, lw=0.8)
        ax1.text(T[-1], deger * (0.97 if va == "top" else 1.0), f"{metin} {sayi(deger, 3)}", ha="right", va=va, fontsize=7.5, color=IKINCIL)
    ax1.set_ylim(0, cekis * 1.15)
    ax1.set_xlabel("Manevra süresi T [s]")
    ax1.set_ylabel("τ_R + τ_L [N·m]")
    ax1.set_title("±10° toparlanma: tepe tork")
    devir = tarama["v_tepe"] / (2 * math.pi * r) * 60
    ax2.plot(T, devir, "-o", ms=4.5, color=MAVI, mec="white", mew=1.0)
    ax2.set_xlabel("Manevra süresi T [s]")
    ax2.set_ylabel("Tepe teker devri [dev/dk]")
    ax2.set_title("±10° toparlanma: tepe teker devri")
    ax2.set_ylim(0, devir.max() * 1.15)
    _eksenler(ax1, ax2)
    fig.tight_layout()
    _kaydet(fig, yol)


def motor_secim(yol, nokta_A, nokta_A_asgari, nokta_B, cekis_motor_basi, ts_fonksiyonu):
    """Şekil 6: tork-devir gereksinim noktaları ve seçim diyagramı (motor başına, teker milinde)."""
    stil()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 3.6))
    n_ust = 450
    ornek_n0 = [1.6 * nokta_B[0], 2.5 * nokta_B[0], 3.4 * nokta_B[0]]
    for n0 in ornek_n0:
        ts = float(ts_fonksiyonu(n0, [nokta_A, nokta_B])[0])
        ax1.plot([0, n0], [ts, 0], color=EKSEN, lw=1.0)
    ax1.plot([], [], color=EKSEN, lw=1.0, label="Sınırdaki doğrusal motor eğrileri")
    ax1.axhline(cekis_motor_basi, color=SOLUK, lw=0.8)
    ax1.text(n_ust, cekis_motor_basi, f"çekiş sınırı {sayi(cekis_motor_basi, 3)} N·m", ha="right", va="bottom", fontsize=7.5, color=IKINCIL)
    for (n, tau), etiket, renk in ((nokta_A, "A (önerilen)", MAVI), (nokta_A_asgari, "A' (asgari)", CAMGOBEGI), (nokta_B, "B (seyir)", TURUNCU)):
        ax1.plot(n, tau, "o", ms=9, color=renk, mec="white", mew=2, zorder=5, label=f"{etiket}: {sayi(tau, 3)} N·m @ {n:.0f} dev/dk")
    ax1.set_xlim(0, n_ust)
    ax1.set_ylim(0, 0.65)
    ax1.set_xlabel("Teker devri n [dev/dk]")
    ax1.set_ylabel("Motor başına tork [N·m]")
    ax1.set_title("Gereksinim noktaları (motor başına)")
    ax1.legend(loc="upper right", fontsize=7.2)

    n0 = np.linspace(nokta_B[0] * 1.02, 600, 400)
    onerilen = ts_fonksiyonu(n0, [nokta_A, nokta_B])
    asgari = ts_fonksiyonu(n0, [nokta_A_asgari, nokta_B])
    ax2.fill_between(n0, onerilen, 3.0, color="#e5f0fc", lw=0, zorder=0)
    ax2.plot(n0, onerilen, color=MAVI, label="Önerilen sınır (A ve B)")
    ax2.plot(n0, asgari, color=CAMGOBEGI, ls=(0, (4, 2)), label="Asgari sınır (A' ve B)")
    ax2.text(560, 1.2, "uygun bölge", ha="right", fontsize=8.5, color=IKINCIL)
    ax2.set_xlim(0, 600)
    ax2.set_ylim(0, 1.5)
    ax2.set_xlabel("Boşta devir n₀ [dev/dk], batarya min. geriliminde")
    ax2.set_ylabel("Durma torku τ_s [N·m]")
    ax2.set_title("Seçim diyagramı (aday noktası eğrinin üstünde)")
    ax2.legend(loc="upper right", fontsize=7.5)
    sag = ax2.secondary_yaxis("right", functions=(lambda x: x / 0.0980665, lambda x: x * 0.0980665))
    sag.set_ylabel("τ_s [kgf·cm]")
    sag.tick_params(colors=EKSEN, labelcolor=IKINCIL)
    sag.yaxis.set_major_formatter(FuncFormatter(_virgul))
    _eksenler(ax1, ax2)
    fig.tight_layout()
    _kaydet(fig, yol)


def km_yuksekligi(yol, tar: dict, l_nominal: float):
    """Şekil 7: KM yüksekliğinin (batarya konumuyla) kutuplara, torka ve düşme süresine etkisi."""
    stil()
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(9.6, 3.3))
    l = 100 * tar["l"]
    ax1.plot(l, tar["p_serbest"], color=MAVI, label="Tam model, serbest teker")
    ax1.plot(l, tar["p_kilitli"], color=TURUNCU, label="Tam model, kilitli teker")
    ax1.plot(l, tar["kok_g_l"], color=CAMGOBEGI, ls=(0, (4, 2)), label="√(g/l) yaklaşımı")
    ax1.set_ylim(0, max(tar["kok_g_l"].max(), tar["p_serbest"].max()) * 1.15)
    ax1.set_ylabel("Kararsız kutup [1/s]")
    ax1.set_title("Düşme hızı")
    ax1.legend(loc="lower left", fontsize=7.2)
    ax2.plot(l, tar["tau_statik"], color=MAVI, label="m·g·l·sin10° (el hesabı statik)")
    ax2.plot(l, tar["tau_tutma"], color=TURUNCU, label="Tutma torku (tam model)")
    ax2.set_ylim(0, tar["tau_statik"].max() * 1.2)
    ax2.set_ylabel("τ_R + τ_L [N·m]")
    ax2.set_title("10°'deki tork")
    ax2.legend(loc="upper left", fontsize=7.2)
    ax3.plot(l, 1000 * tar["t_dusme"], color=MAVI)
    ax3.set_ylabel("10°'den yere değme [ms]")
    ax3.set_title("Düşme süresi (serbest teker)")
    ax3.set_ylim(0, 1000 * tar["t_dusme"].max() * 1.2)
    for ax in (ax1, ax2, ax3):
        ax.axvline(100 * l_nominal, color=SOLUK, lw=0.8)
        ax.set_xlabel("KM yüksekliği l [cm] (batarya aşağı → yukarı)")
    ax1.text(100 * l_nominal, ax1.get_ylim()[1] * 0.97, " nominal", fontsize=7.5, color=SOLUK, va="top")
    _eksenler(ax1, ax2, ax3)
    fig.tight_layout()
    _kaydet(fig, yol)


def kutu_yuvasi(yol, tar: dict, z_cp: float, secenekler: dict, onerilen: str, surtunme_acisi: float):
    """Şekil 8: kutu yüksekliğinin KM'ye, kutba ve yuvadaki görünür eğime etkisi."""
    stil()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 3.4))
    z = 100 * tar["z"]
    ax1.plot(z, 1000 * tar["dl"], color=MAVI)
    ax1.axhline(0, color=EKSEN, lw=0.8)
    ax1.set_xlabel("Kutu merkezinin yüksekliği [cm]")
    ax1.set_ylabel("Kutu eklenince Δl [mm]")
    ax1.set_title("Kutunun KM yüksekliğine etkisi", pad=16)
    ax2.plot(z, tar["alfa_toparlanma"], color=MAVI, label="±10° referans toparlanma")
    ax2.plot(z, tar["alfa_oteleme"], color=TURUNCU, label="Ö1 1 m referans öteleme")
    ax2.axhline(surtunme_acisi, color=SOLUK, lw=0.8)
    ax2.text(z[0], surtunme_acisi, f" kayma sınırı atan μ = {sayi(surtunme_acisi, 1)}°", va="bottom", fontsize=7.5, color=IKINCIL)
    ax2.axvline(100 * z_cp, color=EKSEN, lw=0.8)
    ax2.text(100 * z_cp, surtunme_acisi * 0.42, " $z_{cp}$", fontsize=7.5, color=SOLUK)
    ax2.set_ylim(0, surtunme_acisi * 1.2)
    ax2.set_xlabel("Kutu merkezinin yüksekliği [cm]")
    ax2.set_ylabel("Yuvadaki en büyük görünür eğim α [°]")
    ax2.set_title("Kutunun yuvada hissettiği eğim", pad=16)
    ax2.legend(loc="center left", fontsize=7.5, bbox_to_anchor=(0, 0.55))
    for ax in (ax1, ax2):
        for ad, zs in secenekler.items():
            ax.axvline(100 * zs, color=TURUNCU if ad == onerilen else EKSEN, lw=1.0 if ad == onerilen else 0.6, zorder=0)
            ust = ax.get_ylim()[1]
            ax.text(100 * zs, ust, {"ust": "üst", "orta": "orta", "alt": "alt"}[ad], ha="center", va="bottom", fontsize=7.5,
                    color=MUREKKEP if ad == onerilen else SOLUK)
    _eksenler(ax1, ax2)
    fig.tight_layout()
    _kaydet(fig, yol)


def oteleme(yol, ref: dict, v_trapez: float, T: float, mesafe: float):
    """Şekil 9: Ö1 1 m referans öteleme."""
    stil()
    t = ref["t"]
    nl = ref["dogrusal_olmayan"]
    fig, axs = plt.subplots(1, 3, figsize=(9.6, 3.0))
    axs[0].plot(t, nl["x"], color=MAVI)
    axs[0].set_ylabel("x [m]")
    axs[0].set_title(f"Konum: {sayi(mesafe, 1)} m, {sayi(T, 0)} s")
    i = int(np.argmin(ref["x"]))
    axs[0].annotate(f"önce {sayi(-1000 * ref['x'][i], 1)} mm geri", xy=(t[i], ref["x"][i]), xytext=(2.0, 0.08), fontsize=7.5,
                    color=IKINCIL, arrowprops=dict(arrowstyle="-", color=EKSEN, lw=0.6))
    axs[1].plot(t, nl["xd"], color=MAVI, label="7. derece polinom (düz çıkış)")
    ta = 0.25 * T
    axs[1].plot([0, ta, T - ta, T], [0, v_trapez, v_trapez, 0], color=TURUNCU, ls=(0, (4, 2)), label="Trapez (devir tablosu)")
    axs[1].set_ylabel("ẋ [m/s]")
    axs[1].set_title("Hız")
    axs[1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), fontsize=7)
    axs[2].plot(t, np.degrees(ref["theta"]), color=MAVI)
    axs[2].axhline(0, color=EKSEN, lw=0.8)
    axs[2].set_ylabel("θ [°]")
    axs[2].set_title("Gövde eğimi (hızlanmak için öne yatar)")
    for ax in axs:
        ax.set_xlabel("t [s]")
    _eksenler(*axs)
    fig.tight_layout()
    _kaydet(fig, yol)
