"""2D ikiz (denge/ikiz) ile 3D ikizi (MuJoCo) aynı senaryolarda yan yana koşturur; tablo, şekil ve belge yer tutucuları.

İki ikizde motor modeli, sensör gürültüsü (aynı tohum), kestirici, kontrolcü ve değerlendirme aynıdır; fark yalnız
fiziktedir: 3D'de gövde 6 serbestlikli, teker–zemin ve kutu–yuva temasları yumuşak (MuJoCo), dişli boşluğu esnek
bir yaydır (2D'de rijit, plastik çarpma), kutu yuvada serbest cisimdir (2D'de gövdeye rijit).
"""

from __future__ import annotations

import math
import os
import re
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from ..ikiz.ayarlar import ikiz_ayarlari
from ..ikiz.senaryolar import SENARYO_ADLARI, Kurulum, calistir, degerlendir
from ..parametreler import Tasarim

SENARYOLAR_3D = ("O1-1", "O1-23", "O1-4+", "O1-4-", "O2", "O5")
PILLER = ("dolu", "bos")
PIL = {"dolu": "dolu", "bos": "boş"}


def s(x, n=2) -> str:
    return f"{x:.{n}f}".replace("-", "−").replace(".", ",")


VARYANTLAR = {"2d": "2D ikiz (Python)", "3d": "3D ikiz (MuJoCo)", "3d_oneri": "3D + öneri", "2d_oneri": "2D + öneri",
              "3d_dar": "3D, 8 mm temas"}


def oneri_ayarlari(ay):
    """Öneri: sapma z jiroskobuyla, dönüşte integral (parametre dosyasındaki öneri değeri)."""
    from dataclasses import replace

    return ay.degistir(kestirim=replace(ay.kestirim, sapma_jiroskopla=True),
                       kontrol=replace(ay.kontrol, donus_integrali=ay.kontrol.oneri3d_donus_integrali))


def _kos(arg):
    veri, varyant, kod, pil = arg
    t = Tasarim(veri)
    if varyant == "3d_dar":
        t = t.degistir({"ikiz.teker_temas_genisligi": 0.008})
    ay = ikiz_ayarlari(t)
    if varyant.endswith("oneri"):
        ay = oneri_ayarlari(ay)
    boyut = varyant[:2]
    k = Kurulum("1000", True, pil, "lqr", "kalman")
    t0 = time.time()
    if boyut == "3d":
        from .kosucu import calistir3d, degerlendir3d

        kay = calistir3d(t, kod, k, ay)
        d = degerlendir3d(kay, ay)
    else:
        kay = calistir(t, kod, k, ay)
        d = degerlendir(kay, ay)
    d["sure_duvar"] = time.time() - t0
    d["iz"] = {a: kay.k(a)[::4].copy() for a in ("t", "theta", "x", "psi", "theta_k", "bosluk")}
    return varyant, kod, pil, d


def karsilastir(t: Tasarim, paralel: bool = True) -> dict:
    """{(kod, pil): {varyant: değerlendirme}}; 8 mm temas yalnız dönüşlü senaryolarda (Ö2, Ö5)."""
    isler = [(t.veri, b, kod, pil) for kod in SENARYOLAR_3D for pil in PILLER for b in ("2d", "3d", "3d_oneri", "2d_oneri")]
    isler += [(t.veri, "3d_dar", kod, pil) for kod in ("O2", "O5") for pil in PILLER]
    if paralel:
        with ProcessPoolExecutor(min(len(isler), os.cpu_count() or 1)) as ex:
            sonuc = list(ex.map(_kos, isler))
    else:
        sonuc = [_kos(i) for i in isler]
    out: dict = {}
    for b, kod, pil, d in sonuc:
        out.setdefault((kod, pil), {})[b] = d
    return out


def _deger(d) -> str:
    return " / ".join(a["deger"].replace(".", ",") for a in d["alt"])


def tablo(sonuc: dict) -> str:
    bas = ["Senaryo (kutulu, LQI + Kalman)", "Pil", "Sonuç 2D / 3D / 3D + öneri", "Ölçülen 2D", "Ölçülen 3D", "Ölçülen 3D + öneri", "En büyük eğim [°]",
           "Doyum [s]", "Tepe akım [A]", "Teker kayması [s]", "Dişli boşlukta [%]", "Kestirim hatası [°]",
           "Kutu: 2D görünür eğim [°] / 3D kayma [mm], dönme [°]"]
    satirlar = []
    for (kod, pil), x in sonuc.items():
        a, b, c = x["2d"], x["3d"], x["3d_oneri"]
        oa, ob = a["olcutler"], b["olcutler"]
        k3 = b.get("kutu3d") or {"kayma": float("nan"), "egim": float("nan")}
        e = lambda d: "geçti" if d["gecti"] else "**kaldı**"
        satirlar.append([SENARYO_ADLARI[kod], PIL[pil], f"{e(a)} / {e(b)} / {e(c)}", _deger(a), _deger(b), _deger(c),
                         f"{s(oa['en_buyuk_egim'], 1)} / {s(ob['en_buyuk_egim'], 1)}", f"{s(oa['doyum_suresi'])} / {s(ob['doyum_suresi'])}",
                         f"{s(oa['tepe_akim'])} / {s(ob['tepe_akim'])}", f"{s(oa['kayma_suresi'])} / {s(ob['kayma_suresi'])}",
                         f"{s(100 * oa['bosluk_orani'], 0)} / {s(100 * ob['bosluk_orani'], 0)}",
                         f"{s(oa['kestirim_hatasi'])} / {s(ob['kestirim_hatasi'])}",
                         f"{s(oa['kutu_alfa'], 1)} / {s(1000 * k3['kayma'], 1)}, {s(math.degrees(k3['egim']), 1)}"])
    hiza = ["l"] * 6 + ["r"] * 7
    ayirac = ["---:" if h == "r" else "---" for h in hiza]
    return "\n".join(["| " + " | ".join(bas) + " |", "| " + " | ".join(ayirac) + " |"] + ["| " + " | ".join(r) + " |" for r in satirlar])


def farklar(sonuc: dict) -> dict:
    """Sonucu farklı olan alt testler ve sayısal farkların özeti (belge metni için)."""
    farkli = []
    for (kod, pil), x in sonuc.items():
        for a2, a3 in zip(x["2d"]["alt"], x["3d"]["alt"]):
            if a2["gecti"] != a3["gecti"]:
                farkli.append(f"{a2['ad']} ({PIL[pil]} pil): 2D {'geçti' if a2['gecti'] else 'kaldı'}, 3D {'geçti' if a3['gecti'] else 'kaldı'}"
                              + (f" — {a3['neden'] or a2['neden']}" if (a3['neden'] or a2['neden']) else ""))
    gecen = {b: sum(a["gecti"] for x in sonuc.values() if b in x for a in x[b]["alt"]) for b in VARYANTLAR}
    sayi = {b: sum(len(x[b]["alt"]) for x in sonuc.values() if b in x) for b in VARYANTLAR}
    g2, g3, n = gecen["2d"], gecen["3d"], sayi["2d"]
    donus = lambda b: [a["deger"] for x in sonuc.values() if b in x for a in x[b]["alt"] if "90°" in a["ad"]]
    o = lambda b, anahtar: [x[b]["olcutler"][anahtar] for x in sonuc.values()]
    topar = {b: [float(x[b]["alt"][0]["deger"].split()[0]) for (kod, _), x in sonuc.items() if kod.startswith("O1-4") and x[b]["alt"][0]["gecti"]]
             for b in ("2d", "3d")}
    k3 = [x["3d"]["kutu3d"] for x in sonuc.values() if x["3d"].get("kutu3d")]
    return {"farkli": farkli, "gecen_2d": g2, "gecen_3d": g3, "n": n, "gecen": gecen, "sayi": sayi,
            "donus": {b: donus(b) for b in VARYANTLAR},
            "kayma_2d": max(o("2d", "kayma_suresi")), "kayma_3d": max(o("3d", "kayma_suresi")),
            "bosluk_2d": float(np.mean(o("2d", "bosluk_orani"))), "bosluk_3d": float(np.mean(o("3d", "bosluk_orani"))),
            "kest_2d": float(np.mean(o("2d", "kestirim_hatasi"))), "kest_3d": float(np.mean(o("3d", "kestirim_hatasi"))),
            "egim_2d": max(o("2d", "en_buyuk_egim")), "egim_3d": max(o("3d", "en_buyuk_egim")),
            "topar_2d": max(topar["2d"]) if topar["2d"] else float("nan"), "topar_3d": max(topar["3d"]) if topar["3d"] else float("nan"),
            "kutu_kayma": max(k["kayma"] for k in k3) if k3 else float("nan"), "kutu_egim": max(k["egim"] for k in k3) if k3 else float("nan"),
            "sure_3d": sum(x["3d"]["sure_duvar"] for x in sonuc.values()), "sim_3d": sum(x["3d"]["olcutler"]["sure"] for x in sonuc.values())}


def karsilastirma_grafigi(yol: Path, sonuc: dict, pil: str = "bos") -> None:
    """Ö1-4 (+10°) eğimi ve Ö1-2/3 konumu, 2D ve 3D üst üste."""
    import matplotlib.pyplot as plt

    from ..ikiz.cizim import CIZGILER, RENKLER
    from ..sekiller import _eksenler, _kaydet, stil

    stil()
    fig, axs = plt.subplots(1, 3, figsize=(12.0, 3.4))
    for i, b in enumerate(("2d", "3d")):
        etiket = "2D ikiz (Python)" if b == "2d" else "3D ikiz (MuJoCo)"
        for ax, kod, kanal, olcek in ((axs[0], "O1-4+", "theta", 180 / math.pi), (axs[1], "O1-23", "x", 100.0), (axs[2], "O5", "psi", 180 / math.pi)):
            iz = sonuc[(kod, pil)][b]["iz"]
            ax.plot(iz["t"], olcek * iz[kanal], color=RENKLER[i], ls=CIZGILER[i], lw=1.3, label=etiket)
    axs[0].set_xlim(0, 4)
    axs[0].set(title="Ö1-4: +10°'den toparlanma", xlabel="t [s]", ylabel="Gövde eğimi θ [°]")
    axs[1].set(title="Ö1-2/3: 1 m ileri, 1 m geri", xlabel="t [s]", ylabel="Konum x [cm]")
    axs[2].set(title="Ö5: dönüşler", xlabel="t [s]", ylabel="Sapma ψ [°]")
    axs[0].legend(fontsize=7.5)
    _eksenler(*axs)
    fig.tight_layout()
    _kaydet(fig, yol)


def belge_bolumu(t: Tasarim, sekil_dizini: Path, paralel: bool = True) -> dict:
    """§12.11 yer tutucuları: kütle eşleşmesi, karşılaştırma tablosu, farklar, şekiller."""
    import mujoco

    from ..ikiz.ayarlar import motorlar
    from . import mjcf, video

    t0 = time.time()
    ay = ikiz_ayarlari(t)
    mot = motorlar(t, ay.J_rotor)["1000"]
    D: dict[str, str] = {"ik3_mujoco": mujoco.__version__}
    fark_I = fark_km = fark_m = 0.0
    for kutulu in (True, False):
        m = mujoco.MjModel.from_xml_string(mjcf.mjcf(t, mot, ay, kutulu))
        dd = mujoco.MjData(m)
        mujoco.mj_forward(m, dd)
        M, km, I = mjcf.kutle_ozellikleri(m, dd)
        g = t.govde(kutulu=kutulu)
        fark_m = max(fark_m, abs(M - g.kutle))
        fark_km = max(fark_km, float(np.max(np.abs(km - g.km))))
        fark_I = max(fark_I, float(np.max(np.abs(I - g.atalet)) / np.max(np.abs(g.atalet))))
        if kutulu:
            D["ik3_nv"], D["ik3_ngeom"] = str(m.nv), str(m.ngeom)
            video.kare_png(sekil_dizini / "sekil_20_ikiz3d.png", m, dd.qpos.copy(), uzaklik=0.62)
    D |= {"ik3_fark_m": f"{fark_m:.0e}", "ik3_fark_km": f"{fark_km:.0e}", "ik3_fark_I": f"{fark_I:.0e}"}

    r = karsilastir(t, paralel)
    f = farklar(r)
    D["tablo_ik3"] = tablo(r)
    for b in VARYANTLAR:
        D[f"ik3_gecen_{b}"] = f"{f['gecen'][b]}/{f['sayi'][b]}"
    dn = lambda b: ", ".join(x.replace(".", ",").replace("-", "−") for x in f["donus"][b])
    D |= {"ik3_donus_3d": dn("3d"), "ik3_donus_oneri": dn("3d_oneri"), "ik3_donus_dar": dn("3d_dar"), "ik3_donus_2d": dn("2d"),
          "ik3_kayma_2d": s(f["kayma_2d"]), "ik3_kayma_3d": s(f["kayma_3d"]), "ik3_topar_2d": s(f["topar_2d"]), "ik3_topar_3d": s(f["topar_3d"]),
          "ik3_kest_2d": s(f["kest_2d"]), "ik3_kest_3d": s(f["kest_3d"]), "ik3_bosluk_2d": s(100 * f["bosluk_2d"], 0), "ik3_bosluk_3d": s(100 * f["bosluk_3d"], 0),
          "ik3_kutu_kayma": s(1000 * f["kutu_kayma"], 1), "ik3_kutu_egim": s(math.degrees(f["kutu_egim"]), 2),
          "ik3_bosluk_mm": s(1000 * t.d("yuk.yuva.bosluk"), 0),
          "ik3_hiz": s(f["sim_3d"] / f["sure_3d"], 0), "ik3_dt_ms": s(1000 * t.d("simulasyon.adim_3d"), 2),
          "ik3_k_g": s(t.d("ikiz.disli_rijitligi"), 0), "ik3_c_g": s(t.d("ikiz.disli_sonumu"), 2),
          "ik3_temas_mm": s(1000 * t.d("ikiz.teker_temas_genisligi"), 0), "ik3_ki": s(ay.kontrol.oneri3d_donus_integrali, 1)}
    eksi = lambda metin: re.sub(r"(?<![\w])-(?=\d)", "−", metin)
    D["ik3_farkli"] = "\n".join(eksi(f"- {x}".replace(".", ",")) for x in f["farkli"]) if f["farkli"] else "- Sonucu farklı alt test yok."
    o5 = [x["3d_oneri"] for (kod, _), x in r.items() if kod == "O5"]
    D["ik3_o5_oneri"] = ", ".join(" / ".join(a["deger"].replace("hedefe ", "").replace(".", ",") for a in d["alt"][1:]) for d in o5)
    karsilastirma_grafigi(sekil_dizini / "sekil_19_ikiz3d_karsilastirma.png", r)
    D["ik3_sure"] = s(time.time() - t0, 0)
    return D
