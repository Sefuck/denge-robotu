"""Dijital ikiz çıktıları: zaman grafikleri (θ, x, PWM, akım), motor karşılaştırması, kestirim hatası ve 2D animasyon (GIF).

Biçim denge/sekiller.py ile aynıdır (aynı palet ve eksen stili); seriler lejant + çizgi tipiyle de ayrılır.
"""

from __future__ import annotations

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..sekiller import CAMGOBEGI, IKINCIL, MAVI, MUREKKEP, SOLUK, TURUNCU, _eksenler, _kaydet, sayi, stil  # noqa: E402

RENKLER = (MAVI, TURUNCU, CAMGOBEGI)
CIZGILER = ("-", (0, (4, 2)), (0, (1.5, 1.5)))


def _d(x):
    return np.degrees(x)


def _seri(ax, kay, kanal, i, etiket, olcek=1.0, lw=1.3, alpha=1.0):
    ax.plot(kay.k("t"), olcek * kay.k(kanal), color=RENKLER[i], ls=CIZGILER[i], lw=lw, label=etiket, alpha=alpha)


def _dusme_isareti(ax, kay, kanal, i, olcek=1.0):
    if kay.dustu:
        ax.plot(kay.k("t")[-1], olcek * kay.k(kanal)[-1], "x", color=RENKLER[i], ms=8, mew=2)


def zaman_sutunu(axs, kayitlar, baslik: str, oteleme: bool = True, donus: bool = False):
    """axs: dört eksen (θ, x ya da ψ, PWM, akım). kayitlar: [(etiket, Kayit)]."""
    a_th, a_x, a_d, a_i = axs
    for i, (etiket, kay) in enumerate(kayitlar):
        _seri(a_th, kay, "theta", i, etiket, olcek=180 / math.pi)
        _dusme_isareti(a_th, kay, "theta", i, 180 / math.pi)
        if donus:
            _seri(a_x, kay, "psi", i, etiket, olcek=180 / math.pi)
        else:
            _seri(a_x, kay, "x", i, etiket, olcek=100)
        _seri(a_d, kay, "d_R", i, etiket, olcek=100, lw=0.7, alpha=0.85)
        _seri(a_i, kay, "I_R", i, etiket, lw=0.7, alpha=0.85)
    kay0 = kayitlar[0][1]
    trim = _d(kay0.gv["theta_trim"])
    a_th.axhline(trim, color=SOLUK, lw=0.8)  # dik duruş (KM aksın üstünde)
    if oteleme or donus:
        ref = kay0.k("psi_ref") * 180 / math.pi if donus else 100 * kay0.k("x_ref")
        a_x.plot(kay0.k("t"), ref, color=SOLUK, lw=1.0, ls=(0, (2, 2)), label="referans")
    a_d.axhline(100, color=SOLUK, lw=0.8)
    a_d.axhline(-100, color=SOLUK, lw=0.8)
    a_th.set_title(baslik)
    a_th.set_ylabel("Gövde eğimi θ [°]")
    a_x.set_ylabel("Sapma ψ [°]" if donus else "Konum x [cm]")
    a_d.set_ylabel("Sağ motor PWM [%]")
    a_i.set_ylabel("Sağ motor akımı [A]")
    a_i.set_xlabel("t [s]")
    a_th.legend(loc="best", fontsize=7)
    _eksenler(*axs)


def zaman_grafigi(yol, sutunlar: list[tuple[str, list, dict]], genislik: float = 4.6):
    """sutunlar: [(başlık, [(etiket, Kayit)], seçenekler)] → 4 satırlık zaman grafiği."""
    stil()
    fig, axs = plt.subplots(4, len(sutunlar), figsize=(genislik * len(sutunlar), 8.2), sharex="col", squeeze=False)
    for j, (baslik, kayitlar, sec) in enumerate(sutunlar):
        zaman_sutunu(axs[:, j], kayitlar, baslik, **sec)
        if "xlim" in sec.get("_", {}):
            axs[0, j].set_xlim(*sec["_"]["xlim"])
    fig.tight_layout()
    _kaydet(fig, yol)


def o2_grafigi(yol, kayitlar):
    """Ö2: θ, x, ψ, iki motorun PWM'i ve akımı (ilk kayıt için sol motor da)."""
    stil()
    fig, axs = plt.subplots(5, 1, figsize=(8.6, 9.4), sharex=True)
    for i, (etiket, kay) in enumerate(kayitlar):
        _seri(axs[0], kay, "theta", i, etiket, 180 / math.pi)
        _seri(axs[1], kay, "x", i, etiket, 100)
        _seri(axs[2], kay, "psi", i, etiket, 180 / math.pi)
    kay = kayitlar[0][1]
    axs[1].plot(kay.k("t"), 100 * kay.k("x_ref"), color=SOLUK, lw=1, ls=(0, (2, 2)), label="referans")
    axs[2].plot(kay.k("t"), kay.k("psi_ref") * 180 / math.pi, color=SOLUK, lw=1, ls=(0, (2, 2)), label="referans")
    axs[3].plot(kay.k("t"), 100 * kay.k("d_R"), color=MAVI, lw=0.7, label=f"Sağ ({kayitlar[0][0]})")
    axs[3].plot(kay.k("t"), 100 * kay.k("d_L"), color=TURUNCU, lw=0.7, ls=(0, (4, 2)), label=f"Sol ({kayitlar[0][0]})")
    axs[4].plot(kay.k("t"), kay.k("I_R"), color=MAVI, lw=0.7, label="Sağ")
    axs[4].plot(kay.k("t"), kay.k("I_L"), color=TURUNCU, lw=0.7, ls=(0, (4, 2)), label="Sol")
    for ax, ad in zip(axs, ("Gövde eğimi θ [°]", "Konum x [cm]", "Sapma ψ [°]", "PWM [%]", "Motor akımı [A]")):
        ax.set_ylabel(ad)
        ax.legend(loc="upper left", fontsize=7, ncol=3)
    axs[0].set_title("Ö2: 0,5 m ileri, 0,5 m geri, 90° sol, 90° sağ (komutlar eldivenden, gecikmeli)")
    axs[-1].set_xlabel("t [s]")
    _eksenler(*axs)
    fig.tight_layout()
    _kaydet(fig, yol)


def motor_grafigi(yol, kayitlar, pay: dict, piller: dict):
    """Solda Ö1-4 +10° (boş pil) θ / PWM / akım, sağda en büyük toparlanabilen açı (çubuk)."""
    stil()
    fig = plt.figure(figsize=(10.4, 6.6))
    gs = fig.add_gridspec(3, 2, width_ratios=(1.5, 1.0))
    a = [fig.add_subplot(gs[i, 0]) for i in range(3)]
    for ax in a[1:]:
        ax.sharex(a[0])
    for i, (etiket, kay) in enumerate(kayitlar):
        _seri(a[0], kay, "theta", i, etiket, 180 / math.pi)
        _dusme_isareti(a[0], kay, "theta", i, 180 / math.pi)
        _seri(a[1], kay, "d_R", i, etiket, 100, lw=0.8)
        _seri(a[2], kay, "I_R", i, etiket, lw=0.8)
    a[0].set_title("Ö1-4, +10°'den toparlanma, boş pil, kutulu")
    for ax, ad in zip(a, ("Gövde eğimi θ [°]", "Sağ motor PWM [%]", "Sağ motor akımı [A]")):
        ax.set_ylabel(ad)
    a[1].axhline(100, color=SOLUK, lw=0.8)
    a[0].legend(fontsize=7.5)
    a[0].set_xlim(0, 3)
    a[2].set_xlabel("t [s]")
    b = fig.add_subplot(gs[:, 1])
    motorlar = list(dict.fromkeys(m for m, _, _ in pay))
    y = np.arange(len(motorlar))
    h = 0.36
    for j, (pil, etiket) in enumerate(piller.items()):
        degerler = [min(pay[(m, pil, 1)], pay[(m, pil, -1)]) for m in motorlar]
        cub = b.barh(y + (j - 0.5) * h, degerler, height=h - 0.04, color=RENKLER[j], label=etiket, edgecolor="white", linewidth=1.5)
        for c, dg in zip(cub, degerler):
            b.text(dg + 0.4, c.get_y() + c.get_height() / 2, f"{sayi(dg, 1)}°", va="center", fontsize=8, color=MUREKKEP)
    b.axvline(10, color=SOLUK, lw=0.9)
    b.text(10.4, -0.62, "şartname: ±10°", fontsize=7.5, color=IKINCIL, va="bottom")
    b.set_yticks(y, [f"{m} RPM" for m in motorlar])
    b.set_ylim(len(motorlar) - 0.4, -0.75)
    b.set_xlim(0, 1.3 * max(pay.values()))
    b.set_xlabel("Toparlanabilen en büyük eğim [°] (iki yönün küçüğü)")
    b.set_title("Pay: Ö1-4 kaç dereceye kadar geçer?")
    b.legend(loc="lower right", fontsize=7.5)
    b.grid(axis="y", visible=False)
    _eksenler(*a)
    b.xaxis.set_major_formatter(a[0].xaxis.get_major_formatter())
    fig.tight_layout()
    _kaydet(fig, yol)


def kestirim_grafigi(yol, kayitlar, baslik: str):
    """Eğim kestirim hatası θ̂ − θ ve hız profili."""
    stil()
    fig, axs = plt.subplots(2, 1, figsize=(8.6, 5.0), sharex=True, gridspec_kw={"height_ratios": (2, 1)})
    for i, (etiket, kay) in enumerate(kayitlar):
        axs[0].plot(kay.k("t"), _d(kay.k("theta_k") - kay.k("theta")), color=RENKLER[i], ls=CIZGILER[i], lw=1.0, label=etiket)
    kay = kayitlar[0][1]
    axs[1].plot(kay.k("t"), kay.k("v"), color=SOLUK, lw=1.2)
    axs[0].axhline(0, color=SOLUK, lw=0.8)
    axs[0].set_ylabel("Kestirim hatası θ̂ − θ [°]")
    axs[0].set_title(baslik)
    axs[0].legend(fontsize=7.5, loc="lower left")
    axs[1].set_ylabel("Hız v [m/s]")
    axs[1].set_xlabel("t [s]")
    _eksenler(*axs)
    fig.tight_layout()
    _kaydet(fig, yol)


# ---------------------------------------------------------------------------
# 2D animasyon
# ---------------------------------------------------------------------------
def animasyon(yol, kay, tasarim, fps: int = 25, t_son: float | None = None, baslik: str = "", hiz: float = 1.0) -> int:
    """Yandan görünüş: zemin, teker, gövde zarfı, kutu, KM. Kamera robotu izler. Dönen: kare sayısı."""
    from matplotlib.animation import FuncAnimation, PillowWriter

    stil()
    r = tasarim.d("teker.yaricap")
    (x0, x1), (z0, z1) = tasarim.d("govde.zarf.x_aralik"), tasarim.d("govde.zarf.z_aralik")
    kx, _, kz = tasarim.d("yuk.kutu.boyut")
    zk = tasarim.kutu_merkez_z()
    t = kay.k("t")
    t_son = t[-1] if t_son is None else min(t_son, t[-1])
    kareler = np.arange(0.0, t_son, hiz / fps)
    idx = np.clip(np.searchsorted(t, kareler), 0, len(t) - 1)
    fig, ax = plt.subplots(figsize=(6.0, 3.6), dpi=80)
    ax.set_aspect("equal")
    ax.grid(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_visible(False)
    ax.set_yticks([])
    govde = mpatches.Polygon(np.zeros((4, 2)), closed=True, fc="#ecebe6", ec=IKINCIL, lw=1.2)
    kutu = mpatches.Polygon(np.zeros((4, 2)), closed=True, fc=TURUNCU, ec="white", lw=1.0, visible=kay.gv["kutulu"])
    teker = mpatches.Circle((0, r), r, fc="white", ec=MUREKKEP, lw=1.6)
    jant, = ax.plot([], [], color=MUREKKEP, lw=1.2)
    for p in (govde, kutu, teker):
        ax.add_patch(p)
    zemin, = ax.plot([], [], color=SOLUK, lw=1.5)
    iz, = ax.plot([], [], color=MAVI, lw=1.0, alpha=0.6)
    yazi = ax.text(0.02, 0.95, "", transform=ax.transAxes, fontsize=9, color=MUREKKEP, va="top")
    ax.set_title(baslik, fontsize=9)

    def don(xb, zb, th, x):
        c, s = math.cos(th), math.sin(th)
        return np.column_stack([x + xb * c + zb * s, r - xb * s + zb * c])

    xs = kay.k("x")

    def ciz(i):
        j = idx[i]
        x, th = xs[j], kay.k("theta")[j]
        govde.set_xy(don(np.array([x0, x1, x1, x0]), np.array([z0, z0, z1, z1]), th, x))
        kutu.set_xy(don(np.array([-kx / 2, kx / 2, kx / 2, -kx / 2]), np.array([zk - kz / 2, zk - kz / 2, zk + kz / 2, zk + kz / 2]), th, x))
        teker.center = (x, r)
        phi = x / r
        jant.set_data([x, x + r * math.sin(phi)], [r, r + r * math.cos(phi)])
        ax.set_xlim(x - 0.35, x + 0.35)
        ax.set_ylim(-0.02, 0.26)
        zemin.set_data([x - 0.4, x + 0.4], [0, 0])
        iz.set_data(xs[: j + 1], np.zeros(j + 1) + 0.002)
        yazi.set_text(f"t = {sayi(t[j], 2)} s   θ = {sayi(math.degrees(th), 1)}°   x = {sayi(100 * x, 1)} cm")
        return govde, kutu, teker, jant, zemin, iz, yazi

    anim = FuncAnimation(fig, ciz, frames=len(kareler), blit=False)
    anim.save(yol, writer=PillowWriter(fps=fps))
    plt.close(fig)
    return len(kareler)
