"""3. hafta dokümanını ve şekillerini parametre dosyasından üretir.

Kullanım:  python -m denge            (şekiller + doküman + pytest özeti)
           python -m denge --testsiz  (pytest çalıştırmadan)
Şablon docs/sablon/hafta03.md içindeki @@anahtar@@ yer tutucuları doldurulur.
"""

from __future__ import annotations

import argparse
import datetime
import math
import re
import subprocess
import sys

import numpy as np

from . import model, motor, sekiller, yuva_analizi
from . import simulasyon as sim
from .kutle_merkezi import vurus_merkezi, yere_degme_acilari
from .parametreler import KOK, Tasarim, fiziksel_mi

DOCS = KOK / "docs"
SEKIL = DOCS / "sekiller"
SABLON = DOCS / "sablon" / "hafta03.md"
CIKTI = DOCS / "hafta03_model_tork_km.md"

KGFCM = motor.KGFCM
DURUM_ETIKETI = {"tahmini": "tahmini", "site": "site", "doğrulanamadı": "[doğrulanamadı]", "ölçülmüş": "ölçülmüş",
                 "şartname": "şartname", "öneri": "[öneri]", "sabit": "sabit"}


# ---------------------------------------------------------------------------
# Biçimlendirme
# ---------------------------------------------------------------------------
def s(x, n=2) -> str:
    """Metin içi sayı: ondalık virgül, gerçek eksi işareti."""
    return f"{x:.{n}f}".replace("-", "−").replace(".", ",")


def m(x, k=4) -> str:
    """LaTeX içi sayı, k anlamlı basamak, ondalık {,}."""
    if x == 0 or abs(x) < 1e-12:
        return "0"
    if abs(x - round(x)) < 1e-12:
        return str(int(round(x)))
    us = math.floor(math.log10(abs(x)))
    if -3 <= us < 4:
        basamak = max(0, k - 1 - us)
        return f"{x:.{basamak}f}".replace(".", "{,}")
    mantis = x / 10**us
    return f"{mantis:.{k - 1}f}".replace(".", "{,}") + rf"\times 10^{{{us}}}"


def matris(M, k=4) -> str:
    M = np.atleast_2d(M)
    satirlar = [" & ".join(m(float(v), k) for v in satir) for satir in M]
    return r"\begin{bmatrix} " + r" \\ ".join(satirlar) + r" \end{bmatrix}"


def tablo(basliklar, satirlar, hiza=None) -> str:
    hiza = hiza or ["l"] + ["r"] * (len(basliklar) - 1)
    ayirac = ["---:" if h == "r" else (":---:" if h == "c" else "---") for h in hiza]
    cizgiler = ["| " + " | ".join(basliklar) + " |", "| " + " | ".join(ayirac) + " |"]
    cizgiler += ["| " + " | ".join(str(h) for h in satir) + " |" for satir in satirlar]
    return "\n".join(cizgiler)


def birim_metni(b: str) -> str:
    return b.replace("*", "·").replace("^2", "²").replace("deg", "°")


def deger_metni(k: dict) -> str:
    d = k["deger"]
    if isinstance(d, list):
        return "(" + "; ".join(s(v, 3) for v in d) + ")"
    if isinstance(d, str):
        return d
    return s(d, 4).rstrip("0").rstrip(",") if isinstance(d, float) else str(d)


def aralik_metni(k: dict) -> str:
    if "aralik" not in k:
        return "-"
    a, b = k["aralik"]
    return f"{deger_metni({'deger': a})} – {deger_metni({'deger': b})}"


# ---------------------------------------------------------------------------
def pytest_ozeti() -> str:
    sonuc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=KOK, capture_output=True, text=True)
    satirlar = [x for x in sonuc.stdout.strip().splitlines() if x.strip()]
    return satirlar[-1] if satirlar else "pytest çıktısı alınamadı"


def duyarlilik(tasarim: Tasarim) -> list[list[str]]:
    """Aralığı tanımlı her fiziksel parametre uçlarına çekilince (tek tek) sonuçlar."""
    th0 = math.radians(tasarim.d("sartname.toparlanma_acisi"))
    t_r = tasarim.d("hedef.el_toparlanma_suresi")
    p0 = tasarim.model(kutulu=True)
    taban = (model.kararsiz_kutup(p0), motor.toparlanma_torku_el(p0, th0, t_r)["toplam"], motor.tutma_torku_tam(p0, th0))
    satirlar = []
    for yol, k in tasarim.kayitlar():
        if "aralik" not in k or not fiziksel_mi(yol):
            continue
        if yol.startswith(("batarya.", "zemin.", "yuk.kutu.surtunme", "teker.genislik")):
            continue  # modeli etkilemez (devir/çekiş tarafında ayrıca ele alınır)
        uclar = []
        for v in k["aralik"]:
            p = tasarim.degistir({yol: v}).model(kutulu=True)
            uclar.append((model.kararsiz_kutup(p), motor.toparlanma_torku_el(p, th0, t_r)["toplam"], motor.tutma_torku_tam(p, th0)))
        degisim = [max(abs(u[i] / taban[i] - 1) for u in uclar) for i in range(3)]
        satirlar.append(
            (max(degisim), [f"`{yol}`", aralik_metni(k) + f" {birim_metni(k['birim'])}",
                            f"{s(uclar[0][0])} – {s(uclar[1][0])}", f"{s(uclar[0][1], 3)} – {s(uclar[1][1], 3)}",
                            f"{s(uclar[0][2], 3)} – {s(uclar[1][2], 3)}", f"%{s(100 * max(degisim), 0)}"])
        )
    return [satir for _, satir in sorted(satirlar, key=lambda x: -x[0])], taban


# ---------------------------------------------------------------------------
def hesapla_ve_ciz(tasarim: Tasarim, testler: bool = True) -> dict:
    SEKIL.mkdir(parents=True, exist_ok=True)
    D: dict[str, str] = {}
    th0 = math.radians(tasarim.d("sartname.toparlanma_acisi"))
    p = tasarim.model(kutulu=True)
    p0 = tasarim.model(kutulu=False)
    g_kutulu, g_kutusuz = tasarim.govde(kutulu=True), tasarim.govde(kutulu=False)
    k = model.dogrusal_katsayilar(p)
    D["surum"] = tasarim.veri["meta"]["surum"]
    D["tarih"] = datetime.date.today().strftime("%d.%m.%Y")
    D["m_toplam"] = s(tasarim.toplam_kutle(kutulu=True))
    D["m_toplam_kutusuz"] = s(tasarim.toplam_kutle(kutulu=False))
    D |= {"kutu_kutle": s(1000 * tasarim.d("yuk.kutu.kutle"), 0), "r_mm": s(1000 * tasarim.d("teker.yaricap"), 0),
          "teker_cap": s(2000 * tasarim.d("teker.yaricap"), 0), "d_mm": s(1000 * tasarim.d("teker.iz_genisligi"), 0),
          "o2_sure": s(tasarim.d("hedef.o2_sure"), 0), "donus_sure": s(tasarim.d("hedef.donus_sure"), 0),
          "m_b_kutulu": s(tasarim.govde(kutulu=True).kutle, 2)}
    D["kutu_orani"] = s(100 * tasarim.d("yuk.kutu.kutle") / tasarim.toplam_kutle(kutulu=True), 1)

    # -- Parametre tabloları ----------------------------------------------------
    fiz = [(y, kk) for y, kk in tasarim.kayitlar() if fiziksel_mi(y)]
    D["tablo_fiziksel"] = tablo(
        ["Parametre", "Değer", "Birim", "Aralık", "Durum", "Kaynak"],
        [[f"`{y}`", deger_metni(kk), birim_metni(kk["birim"]), aralik_metni(kk), DURUM_ETIKETI[kk["durum"]], kk["kaynak"]] for y, kk in fiz],
        ["l", "r", "l", "r", "l", "l"],
    )
    diger = [(y, kk) for y, kk in tasarim.kayitlar() if y.startswith(("sartname.", "hedef.", "yuk.yuva.")) and not fiziksel_mi(y)]
    D["tablo_hedef"] = tablo(
        ["Parametre", "Değer", "Birim", "Durum", "Kaynak"],
        [[f"`{y}`", deger_metni(kk), birim_metni(kk["birim"]), DURUM_ETIKETI[kk["durum"]], kk["kaynak"]] for y, kk in diger],
        ["l", "r", "l", "l", "l"],
    )
    D["n_fiziksel"] = str(len(fiz))
    bilesenler = tasarim.bilesenler(kutulu=True)
    m_govde = sum(b.kutle for b in bilesenler)
    D["tablo_butce"] = tablo(
        ["Bileşen", "Kütle [g]", "x [mm]", "z [mm]", "Gövde kütlesindeki pay", "m·z katkısı [g·m]"],
        [[b.ad, s(1000 * b.kutle, 0), s(1000 * b.konum[0], 0), s(1000 * b.konum[2], 0), f"%{s(100 * b.kutle / m_govde, 1)}", s(1000 * b.kutle * b.konum[2], 1)]
         for b in bilesenler]
        + [["**Gövde toplamı** (tekerler hariç)", f"**{s(1000 * m_govde, 0)}**", s(1000 * g_kutulu.km[0], 1), s(1000 * g_kutulu.km[2], 1), "%100", s(1000 * m_govde * g_kutulu.km[2], 1)],
           ["Tekerler (2 adet, aksta)", s(2000 * tasarim.d("teker.kutle"), 0), "0", "0", "-", "0"]],
    )
    D["tablo_model_par"] = tablo(
        ["Büyüklük", "Sembol", "Kutusuz", "Kutulu", "Birim"],
        [
            ["Gövde kütlesi (motor statoru dahil)", "$m_b$", s(p0.m_b, 3), s(p.m_b, 3), "kg"],
            ["Aks → gövde KM uzaklığı", "$l$", s(1000 * p0.l, 1), s(1000 * p.l, 1), "mm"],
            ["Yunuslama ataleti (KM'de)", "$I_{yy}$", s(1000 * p0.I_yy, 2), s(1000 * p.I_yy, 2), "g·m²"],
            ["Yuvarlanma ataleti (KM'de)", "$I_{xx}$", s(1000 * p0.I_xx, 2), s(1000 * p.I_xx, 2), "g·m²"],
            ["Sapma ataleti (KM'de)", "$I_{zz}$", s(1000 * p0.I_zz, 2), s(1000 * p.I_zz, 2), "g·m²"],
            ["Teker kütlesi (bir)", "$m_w$", s(1000 * p.m_w, 0), s(1000 * p.m_w, 0), "g"],
            ["Teker dönme ataleti (bir)", "$J_w$", s(1e6 * p.J_w, 1), s(1e6 * p.J_w, 1), "g·cm²"],
            ["Teker yarıçapı / iz genişliği", "$r$, $d$", f"{s(1000 * p.r, 1)} / {s(1000 * p.d, 0)}", f"{s(1000 * p.r, 1)} / {s(1000 * p.d, 0)}", "mm"],
            ["Yansıyan rotor ataleti / viskoz sürtünme", "$J_m$, $b$", "0 / 0 (ihmal)", "0 / 0 (ihmal)", "kg·m², N·m·s"],
        ],
        ["l", "c", "r", "r", "l"],
    )

    # -- Doğrusal model ---------------------------------------------------------
    A, B, C, Dm = model.durum_uzay(p)
    Ap, Bp, _, _ = model.donus_durum_uzay(p)
    Ts = 1.0 / tasarim.d("hedef.kontrol_frekansi")
    Ad, Bd, _, _ = model.ayriklastir(A, B, C, Dm, Ts)
    tf = model.transfer_fonksiyonu_analitik(p)
    tf0 = model.transfer_fonksiyonu_analitik(p0)
    D |= {
        "M_x": m(k["M_x"]), "a12": m(k["a12"]), "a22": m(k["a22"]), "Delta": m(k["Delta"]), "mgl": m(k["mgl"]), "J_psi": m(k["J_psi"]),
        "A": matris(A), "B": matris(B), "Ap": matris(Ap), "Bp": matris(Bp), "Ad": matris(Ad, 5), "Bd": matris(Bd, 4),
        "Ts_ms": s(1000 * Ts, 0), "f_kontrol": s(tasarim.d("hedef.kontrol_frekansi"), 0),
        "K_theta": m(tf["K_theta"]), "p2": m(tf["p2"]), "K_x": m(tf["K_x"]), "z2": m(tf["z2"]), "K_psi": m(tf["K_psi"]),
        "p": s(math.sqrt(tf["p2"])), "p_m": m(math.sqrt(tf["p2"])), "z": s(math.sqrt(tf["z2"])), "z_m": m(math.sqrt(tf["z2"])),
        "tau_zaman": s(1000 / math.sqrt(tf["p2"]), 0), "p0": s(math.sqrt(tf0["p2"])),
        "rank_c": str(model.kontrol_edilebilirlik_rangi(A, B)),
        "rank_o2": str(model.gozlenebilirlik_rangi(A, np.array([[1, 0, 0, 0], [0, 0, 1, 0]]))),
        "rank_o1": str(model.gozlenebilirlik_rangi(A, np.array([[0, 0, 1, 0]]))),
        "p_kilitli": s(model.kilitli_kutup(p)), "p_kilitli0": s(model.kilitli_kutup(p0)),
        "kok_g_l": s(math.sqrt(p.g / p.l)), "kok_g_l0": s(math.sqrt(p0.g / p0.l)),
        "z0": s(math.sqrt(tf0["z2"])),
        "kutuplar": ", ".join(s(float(x.real)) for x in np.sort_complex(model.kutuplar(p)["egim"])),
        "bant_orani": s(2 * math.pi * tasarim.d("hedef.kontrol_frekansi") / math.sqrt(tf["p2"]), 0),
    }
    tablo_kutup = [["Eğim kutupları (serbest teker, $u$ girişi)", "±" + D["p0"] + ", 0, 0", "±" + D["p"] + ", 0, 0"],
                   ["Kilitli teker kutbu (redüktör geri sürülemezse)", "±" + D["p_kilitli0"], "±" + D["p_kilitli"]],
                   ["Noktasal kütle, sabit pivot: $\\sqrt{g/l}$", D["kok_g_l0"], D["kok_g_l"]],
                   ["$X/U$ sıfırları", "±" + D["z0"], "±" + D["z"]],
                   ["Sapma kutupları", "0, 0", "0, 0"]]
    D["tablo_kutup"] = tablo(["", "Kutusuz [1/s]", "Kutulu [1/s]"], tablo_kutup, ["l", "r", "r"])
    Jm_ornek = 1e-3
    D["Jm_ornek"] = s(Jm_ornek, 3)
    jm_satir = []
    for Jm in (0.0, 5e-4, 1e-3, 2.5e-3):
        pj = p.degistir(J_m=Jm)
        jm_satir.append([s(Jm, 4), s(model.kararsiz_kutup(pj)), f"%{s(100 * (model.kararsiz_kutup(pj) / model.kararsiz_kutup(p) - 1), 0)}"])
    for bb in (0.005, 0.02):
        pb = p.degistir(b=bb)
        jm_satir.append([f"b = {s(bb, 3)} N·m·s/rad", s(model.kararsiz_kutup(pb)), f"%{s(100 * (model.kararsiz_kutup(pb) / model.kararsiz_kutup(p) - 1), 0)}"])
    D["tablo_jm"] = tablo(["$J_m$ [kg·m²] (ya da $b$)", "Kararsız kutup [1/s]", "Nominale göre"], jm_satir)

    sekiller.kutup_haritasi(
        SEKIL / "sekil_02_kutuplar.png",
        model.kutuplar(p)["egim"], model.kutuplar(p.degistir(J_m=Jm_ornek))["egim"],
        np.array([-math.sqrt(tf["z2"]), math.sqrt(tf["z2"])]), Jm_ornek, model.kutuplar(p0)["egim"],
    )

    # -- Düşme ------------------------------------------------------------------
    temas = yere_degme_acilari(tasarim)
    yd = (temas["ileri"], temas["geri"])
    serbest = {i: sim.acik_cevrim_dusme(p, i * th0, mod="serbest", yere_degme=yd) for i in (1, -1)}
    kilitli = {i: sim.acik_cevrim_dusme(p, i * th0, mod="kilitli", yere_degme=yd) for i in (1, -1)}
    dogrusal = {}
    for i in (1, -1):
        t = np.linspace(0, serbest[i]["t_degme"] * 1.05, 300)
        y = sim.dogrusal_serbest_yanit(A, [0, 0, i * th0, 0], t)
        maske = np.abs(y[:, 2]) <= temas["ileri"] * 1.3
        dogrusal[i] = {"t": t[maske], "theta": y[maske, 2]}
    sekiller.dusme(SEKIL / "sekil_03_dusme.png", serbest, kilitli, dogrusal, (math.degrees(temas["ileri"]), math.degrees(temas["geri"])),
                   tasarim.d("sartname.pasif_test_suresi"))
    D["temas_geri"] = s(math.degrees(temas["geri"]), 1)
    D["temas_nokta"] = min(temas["noktalar"], key=lambda x: x[1])[0]
    D["temas_nokta_geri"] = min(temas["noktalar"], key=lambda x: x[2])[0]
    t_lin = sim.esige_ulasma_suresi(th0, temas["ileri"], math.sqrt(tf["p2"]))
    D |= {
        "temas": s(math.degrees(temas["ileri"]), 1), "t_serbest": s(serbest[1]["t_degme"]), "t_kilitli": s(kilitli[1]["t_degme"]),
        "x_serbest": s(100 * abs(serbest[1]["x"][-1]), 1), "x_kilitli": s(100 * abs(kilitli[1]["x"][-1]), 1),
        "t_lin": s(t_lin, 3), "t_serbest3": s(serbest[1]["t_degme"], 3), "t_lin_fark": s(100 * (1 - t_lin / serbest[1]["t_degme"]), 0), "t_kilitli3": s(kilitli[1]["t_degme"], 3),
        "pasif_kat": s(tasarim.d("sartname.pasif_test_suresi") / max(kilitli[i]["t_degme"] for i in (1, -1)), 0),
        "t_hepsi_min": s(min(x[i]["t_degme"] for x in (serbest, kilitli) for i in (1, -1))),
        "t_hepsi_max": s(max(x[i]["t_degme"] for x in (serbest, kilitli) for i in (1, -1))),
    }
    D["tablo_temas"] = tablo(
        ["Gövde noktası", "İleri eğimde yere değme", "Geri eğimde yere değme"],
        [[ad, "değmez" if math.isinf(a) else f"{s(math.degrees(a), 1)}°", "değmez" if math.isinf(b) else f"{s(math.degrees(b), 1)}°"]
         for ad, a, b in temas["noktalar"]],
        ["l", "r", "r"],
    )
    D["yere_degme_min"] = s(tasarim.d("hedef.yere_degme_min"), 0)

    # -- Motor ------------------------------------------------------------------
    g = motor.gereksinimleri_hesapla(tasarim)
    el, SF = g["el"], g["SF"]
    D["tablo_hareket"] = tablo(
        ["Hareket", "Miktar", "Süre [s] [öneri]", "Tepe teker hızı [m/s]", "İvme", "Teker devri [dev/dk]", "İvme torku, motor başı [N·m]"],
        [[h["hareket"], h["miktar"], s(h["sure"], 1), s(h["v_teker"], 3),
          f"{s(h['ivme'], 3)} m/s²" if "dönüş" not in h["hareket"] else f"{s(h['ivme'], 3)} m/s² (teker çevresi)",
          s(h["rpm"], 1), s(h["tork_motor_basi"], 4)] for h in g["hareketler"]],
    )
    nA, tA = g["nokta_A"]
    nA2, tA2 = g["nokta_A_asgari"]
    nB, tB = g["nokta_B"]
    ref = g["ref"]
    tepe_ref = float(np.max(np.abs(ref["dogrusal_olmayan"]["u"])))
    jt = g["J_m_tablosu"]
    tepe_agr = jt[0]["tepe_agresif"]
    D["tablo_jm_tork"] = tablo(
        ["$J_m$ [kg·m²]", "Kutup [1/s]", "10°'de tutma torku [N·m]", f"Referans manevra T = {s(g['T_ref'], 1)} s, tepe [N·m]",
         f"Agresif manevra T = {s(tasarim.d('hedef.el_toparlanma_suresi'), 1)} s, tepe [N·m]"],
        [[s(x["J_m"], 4), s(x["kutup"]), s(x["tutma"], 3), s(x["tepe_ref"], 3),
          s(x["tepe_agresif"], 3) + (" (çekiş sınırını aşar)" if x["tepe_agresif"] > g["cekis_toplam"] else "")] for x in jt],
    )
    D |= {
        "statik": s(el["statik"], 3), "J_O": m(el["J_O"]), "J_O_s": s(1000 * el["J_O"], 2), "thdd": s(el["theta_dd"], 2),
        "dinamik": s(el["dinamik"], 3), "el_toplam": s(el["toplam"], 3), "el_motor": s(el["toplam"] / 2, 3),
        "el_motor_kgfcm": s(el["toplam"] / 2 / KGFCM, 2), "SF": s(SF, 1), "tA": s(tA, 3), "tA_kgfcm": s(tA / KGFCM, 1),
        "nA": s(nA, 0), "tA2": s(tA2, 3), "tA2_kgfcm": s(tA2 / KGFCM, 1), "nA2": s(nA2, 0), "nB": s(nB, 0), "tB": s(tB, 3),
        "tutma": s(g["tutma_tam"], 3), "tutma_oran": s(100 * g["tutma_tam"] / el["statik"], 0),
        "tutma_carpan": s(1 / (1 + k["a12"] * math.cos(th0) / (k["M_x"] * p.r)), 3),
        "T_ref": s(g["T_ref"], 1), "tepe_ref": s(tepe_ref, 3), "tepe_ref_lin": s(float(np.max(np.abs(ref["u"]))), 3),
        "t_r": s(tasarim.d("hedef.el_toparlanma_suresi"), 1), "tepe_agr": s(tepe_agr, 3),
        "el_kat": s(el["toplam"] / tepe_ref, 1), "el_kat_agr": s(el["toplam"] / tepe_agr, 1),
        "jm_ust": s(jt[-1]["J_m"], 4), "tutma_jm_ust": s(jt[-1]["tutma"], 3), "tepe_ref_jm_ust": s(jt[-1]["tepe_ref"], 3),
        "tepe_agr_jm_ust": s(jt[-1]["tepe_agresif"], 3), "jm_esik": m(g["J_m_esik"], 2), "jm_esik_s": s(g["J_m_esik"], 4),
        "tutma_jm_kat": s(jt[-1]["tutma"] / jt[0]["tutma"], 1),
        "jm_karsilastirma": "el hesabını aşar" if jt[-1]["tepe_ref"] > el["toplam"] else "el hesabına yaklaşır",
        "jm_sf_yeter": "karşılar" if jt[-1]["tepe_ref"] <= SF * el["toplam"] else "karşılamaz",
        "v_ref": s(g["v_ref"], 2), "x_f": s(100 * ref["x_f"], 0), "th_min_ref": s(abs(math.degrees(ref["theta"].min())), 1),
        "xd_son": s(1000 * abs(ref["dogrusal_olmayan"]["xd"][-1]), 1),
        "cekis": s(g["cekis_toplam"], 3), "cekis_motor": s(g["cekis_toplam"] / 2, 3), "mu": s(tasarim.d("zemin.surtunme"), 1),
        "mu_gerek_el": s(SF * el["toplam"] / (g["m_toplam"] * p.g * p.r), 2), "mu_gerek_ref": s(tepe_ref / (g["m_toplam"] * p.g * p.r), 2),
        "v_seyir": s(g["v_seyir"], 3), "hiz_payi": s(tasarim.d("hedef.hiz_payi"), 1), "seyir_hareketi": g["seyir_hareketi"],
    }
    tr_satir = []
    for tr in (0.3, 0.5, 1.0):
        e = motor.toparlanma_torku_el(p, th0, tr)
        tr_satir.append([s(tr, 1), s(e["theta_dd"], 2), s(e["dinamik"], 3), s(e["toplam"], 3), s(e["toplam"] / 2, 3), s(SF * e["toplam"] / 2 / KGFCM, 2)])
    D["tablo_tr"] = tablo(["$t_r$ [s]", "$\\ddot\\theta_r$ [rad/s²]", "Dinamik pay [N·m]", "Toplam [N·m]", "Motor başı [N·m]", f"Motor başı × SF={s(SF, 1)} [kgf·cm]"], tr_satir)
    tarama = sim.toparlanma_taramasi(p, th0, [0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0])
    sekiller.toparlanma(SEKIL / "sekil_05_toparlanma.png", ref, el["toplam"], g["tutma_tam"], g["cekis_toplam"], g["T_ref"])
    sekiller.tork_sure(SEKIL / "sekil_06_tork_sure.png", tarama, g["tutma_tam"], el["toplam"], g["cekis_toplam"], p.r)
    sekiller.motor_secim(SEKIL / "sekil_07_motor_secim.png", g["nokta_A"], g["nokta_A_asgari"], g["nokta_B"], g["cekis_toplam"] / 2, motor.min_durma_torku)
    D["tablo_tarama"] = tablo(
        ["T [s]", "Tepe tork, doğrusal [N·m]", "Tepe tork, doğrusal olmayan [N·m]", "Tepe hız [m/s]", "Tepe devir [dev/dk]", "Yol $x_f$ [cm]"],
        [[s(T, 2), s(a, 3), s(b, 3), s(v, 2), s(motor.rpm(v, p.r), 0), s(100 * x, 0)]
         for T, a, b, v, x in zip(tarama["T"], tarama["u_dogrusal"], tarama["u_dogrusal_olmayan"], tarama["v_tepe"], tarama["x_f"])],
    )
    V = tasarim.batarya_gerilimleri()
    D |= {"V_min": s(V["min"], 1), "V_nom": s(V["nominal"], 1), "V_max": s(V["max"], 1), "n_hucre": str(tasarim.d("batarya.seri_hucre"))}
    ornek = []
    for n0 in (1.6 * nB, 2.0 * nB, 2.5 * nB, 3.4 * nB):
        ts_o = float(motor.min_durma_torku(n0, [g["nokta_A"], g["nokta_B"]])[0])
        ts_a = float(motor.min_durma_torku(n0, [g["nokta_A_asgari"], g["nokta_B"]])[0])
        ornek.append([s(n0, 0), s(ts_o, 3), s(ts_o / KGFCM, 1), s(ts_a, 3), s(ts_a / KGFCM, 1)])
    D["tablo_min_motor"] = tablo(["Boşta devir $n_0$ [dev/dk]", "Önerilen $\\tau_s$ [N·m]", "[kgf·cm]", "Asgari $\\tau_s$ [N·m]", "[kgf·cm]"], ornek)
    D["tablo_batarya"] = tablo(
        ["Paket", "Boş [V]", "Nominal [V]", "Tam dolu [V]", "Şartname §4.1 (≤ 24 V DC)"],
        [[f"{tasarim.d('batarya.seri_hucre')}S Li-ion (site)", s(V["min"], 1), s(V["nominal"], 1), s(V["max"], 1),
          "uygun" if V["max"] <= tasarim.d("sartname.max_gerilim") else "**aşıyor**"]],
        ["l", "r", "r", "r", "l"],
    )
    e = g["enkoder"]
    pencere = tasarim.d("hedef.hiz_kestirim_penceresi")
    D |= {"cpr_min": s(e["cpr_min"], 0), "ds_max": s(1000 * e["ds_max"], 2), "dv_hedef": s(tasarim.d("hedef.hiz_cozunurlugu"), 2),
          "pencere_ms": s(1000 * pencere, 0), "f_sayim": s(e["f_sayim_max"] / 1000, 1), "n_max": s(g["n_max"], 0),
          "dpsi": s(math.degrees(e["dpsi"]), 3), "hata_x": s(1000 * p.r * th0, 1), "hata_v": s(100 * p.r * 1.0, 0)}
    D["tablo_enkoder"] = tablo(
        ["Motor PPR", "Redüksiyon", "Teker başına sayım (x4)", "Yol/sayım [mm]", f"Hız adımı ({s(1000 * pencere, 0)} ms) [m/s]", "Sapma/sayım [°]", "Sayım frekansı [kHz]", "Sonuç"],
        [[str(x["ppr"]), f"1:{x['N']}", str(x["cpr_teker"]), s(1000 * x["ds"], 3), s(x["dv"], 3), s(math.degrees(x["dpsi"]), 3), s(x["f_max"] / 1000, 1),
          "yeterli" if x["cpr_teker"] >= e["cpr_min"] else "yetersiz"]
         for x in motor.enkoder_tablosu(p.r, p.d, pencere, g["n_max"], [7, 11, 13], [20, 30, 50])],
        ["r", "r", "r", "r", "r", "r", "r", "l"],
    )
    ot = sim.referans_oteleme(p, tasarim.d("sartname.o1_mesafe"), tasarim.d("hedef.o1_sure"))
    v_tr = g["hareketler"][0]["v_teker"]
    sekiller.oteleme(SEKIL / "sekil_04_oteleme.png", ot, v_tr, tasarim.d("hedef.o1_sure"), tasarim.d("sartname.o1_mesafe"))
    D |= {"ot_geri": s(-1000 * ot["x"].min(), 1), "ot_v": s(float(np.max(ot["dogrusal_olmayan"]["xd"])), 2),
          "ot_rpm": s(motor.rpm(float(np.max(ot["dogrusal_olmayan"]["xd"])), p.r), 0), "ot_th": s(math.degrees(np.max(np.abs(ot["theta"]))), 1),
          "ot_tork": s(float(np.max(np.abs(ot["dogrusal_olmayan"]["u"]))), 3), "o1_sure": s(tasarim.d("hedef.o1_sure"), 0),
          "v_tr": s(v_tr, 3), "ot_oran": s(float(np.max(ot["dogrusal_olmayan"]["xd"])) / v_tr, 2)}

    # -- Aday motor (site: JGB37-520 530 RPM; veri sayfası rcdrone [doğrulanamadı]) --
    aday = motor.aday_tasarimdan(tasarim)
    seri = motor.seri_adaylari(tasarim)
    deg = motor.degerlendir(aday, g, V)
    sonuc_metni = lambda x: "-" if x is None else ("**GEÇTİ**" if x else "**KALDI**")
    D["tablo_aday"] = tablo(["Ölçüt", "Gereksinim", "Aday (batarya min. gerilimi)", "Sonuç"],
                            [[x["olcut"], x["gerek"], x["aday"], sonuc_metni(x["sonuc"])] for x in deg], ["l", "l", "l", "c"])
    sf = {k: motor.gereken_sf(aday, g, V[k]) for k in ("min", "nominal", "max")}
    tarama_seri = motor.oran_taramasi(seri, g, V["min"])
    D["tablo_oran"] = tablo(
        ["Oran (12 V boşta devir)", "$n_0$ @ min. gerilim", "$\\tau_s$ @ min. gerilim [N·m]", "Tork @ A [N·m]", "Sağlanan SF", "A (SF)", "A₀", "B", "Enkoder [sayım]"],
        [[x["aday"].ad.replace(".", ","), f"{x['n0']:.0f}", s(x["ts"], 3), s(x["nokta_A"][0], 3), s(x["nokta_A"][0] / g["nokta_A0"][1], 2),
          sonuc_metni(x["nokta_A"][1]), sonuc_metni(x["nokta_A0"][1]), sonuc_metni(x["nokta_B"][1]), f"{x['cpr']:.0f}"] for x in tarama_seri],
        ["l", "r", "r", "r", "r", "c", "c", "c", "r"],
    )
    gecen_B = [x for x in tarama_seri if x["nokta_B"][1]]
    en_iyi = max(gecen_B, key=lambda x: x["nokta_A"][0])
    ara_min = motor.oran_araligi(seri, g, V["min"])
    ara_nom = motor.oran_araligi(seri, g, V["nominal"])
    aday_N = aday.reduksiyon
    cpr_aday = 4 * aday.ppr * aday.reduksiyon
    pencere_gerek = 2 * math.pi * p.r / (tasarim.d("hedef.hiz_cozunurlugu") * cpr_aday)
    mm = aday.motor_modeli()
    b_emf = mm.K_t * mm.K_e / mm.R
    A_V, *_ = model.gerilim_girisli_durum_uzay(p, mm)
    D |= {
        "aday_ad": aday.ad, "aday_N": s(aday_N, 1), "aday_n0": s(aday.bosta_devir, 0), "aday_ts": s(aday.durma_torku, 3),
        "aday_ts_kgfcm": s(aday.durma_torku / KGFCM, 1), "aday_tauA": s(aday.tork(nA, V["min"]), 3),
        "sf_min": s(sf["min"], 2), "sf_nom": s(sf["nominal"], 2), "sf_max": s(sf["max"], 2), "tA0": s(g["nokta_A0"][1], 3),
        "aday_gecer_SF": "karşılıyor" if sf["min"] >= SF else "karşılamıyor",
        "aday_gecer_SFsiz": "karşılıyor" if sf["min"] >= 1 else "karşılamıyor",
        "en_iyi_ad": en_iyi["aday"].ad.replace(".", ","), "en_iyi_tau": s(en_iyi["nokta_A"][0], 3),
        "en_iyi_sf": s(en_iyi["nokta_A"][0] / g["nokta_A0"][1], 2), "en_iyi_n0": s(en_iyi["n0"], 0),
        "en_iyi_cpr": f"{en_iyi['cpr']:.0f}", "en_iyi_oran2": s((en_iyi["aday"].reduksiyon / aday_N) ** 2, 1),
        "en_iyi_sf_nom": s(motor.gereken_sf(en_iyi["aday"], g, V["nominal"]), 2),
        "en_iyi_eksik": s(100 * (1 - en_iyi["nokta_A"][0] / g["nokta_A"][1]), 0),
        "cpr_aday": f"{cpr_aday:.0f}", "pencere_gerek": s(1000 * pencere_gerek, 1),
        "Kt": s(mm.K_t, 3), "Ke": s(mm.K_e, 3), "Ra": s(mm.R, 1), "b_emf": s(b_emf, 4),
        "p_gerilim": s(float(np.max(np.linalg.eigvals(A_V).real)), 2),
        "fit_c": s(ara_min["c"] / KGFCM, 3), "fit_K": s(ara_min["K"], 0),
    }
    oran_min = V["min"] / aday.gerilim
    N_yildiz = ara_min["K"] * oran_min / (2 * nA)  # A devrinde torku en büyük yapan oran
    sf_tavan = ara_min["c"] * oran_min * N_yildiz / 2 / g["nokta_A0"][1]
    D |= {"N_yildiz": s(N_yildiz, 0), "sf_tavan": s(sf_tavan, 2), "tutma_motor": s(g["tutma_tam"] / 2, 3),
          "aday_verim": s(tasarim.d("motor_adayi.verim_torku"), 3),
          "en_iyi_verim": s(tasarim.d("motor_serisi.verim_torku_kgfcm")[list(tasarim.d("motor_serisi.reduksiyon")).index(en_iyi["aday"].reduksiyon)] * KGFCM, 3)}
    if ara_min["aralik"]:
        D["oran_araligi_min"] = (f"≈ 1:{ara_min['aralik'][0]:.0f} – 1:{ara_min['aralik'][1]:.0f} "
                                 f"(12 V'ta ≈ {ara_min['devir_12V'][0]:.0f}–{ara_min['devir_12V'][1]:.0f} dev/dk)")
    else:
        D["oran_araligi_min"] = (f"bulunamadı: bu motor gövdesiyle hiçbir oran boş bataryada SF = {s(SF, 1)} değerini sağlamıyor; "
                                 f"en iyisi ≈ 1:{N_yildiz:.0f} oranında SF ≈ {s(sf_tavan, 2)}")
    D["oran_araligi_nom"] = (f"≈ 1:{ara_nom['aralik'][0]:.0f} – 1:{ara_nom['aralik'][1]:.0f} (12 V'ta ≈ {ara_nom['devir_12V'][0]:.0f}–{ara_nom['devir_12V'][1]:.0f} dev/dk)"
                             if ara_nom["aralik"] else "bulunamadı")

    # -- Kütle merkezi ve yuva --------------------------------------------------
    ka = yuva_analizi.com_karsilastirma(tasarim)
    D["tablo_com"] = tablo(
        ["Durum", "$m_b$ [kg]", "KM yüksekliği $z_c$ [mm]", "Yatay ofset $x_c$ [mm]", "Denge (trim) açısı", "Kutup [1/s]", "$m_b g l \\sin 10°$ [N·m]", "Yere değme süresi [s]"],
        [[x["etiket"], s(x["m_b"], 3), s(1000 * x["z_c"], 1), s(1000 * x["x_c"], 2), f"{s(x['trim'], 2)}°", s(x["p_serbest"]), s(x["tau_statik"], 3), s(x["t_dusme"], 3)] for x in ka],
    )
    D["tablo_kutu_etkisi"] = tablo(
        ["Yuva", "Kutu eklenince $\\Delta l$ [mm]", "Kutup değişimi", "$m_b g l \\sin 10°$ değişimi"],
        [[yuva_analizi.YUVA_ETIKETLERI[x["yuva"]], s(1000 * x["dl"], 1), f"%{s(x['dp_yuzde'], 1)}", f"%{s(x['dtau_yuzde'], 1)}"] for x in ka if x["kutulu"]],
    )
    oner = tasarim.d("yuk.yuva.onerilen")
    secenekler = {ad: tasarim.kutu_merkez_z(ad) for ad in yuva_analizi.YUVA_ETIKETLERI}
    manevralar = {"toparlanma": ref, "oteleme": ot}
    z_tarama = np.linspace(0.03, 0.29, 27)
    kt = yuva_analizi.kutu_yuksekligi_taramasi(tasarim, z_tarama, manevralar)
    kt_sec = yuva_analizi.kutu_yuksekligi_taramasi(tasarim, list(secenekler.values()), manevralar)
    mu_k = tasarim.d("yuk.kutu.surtunme")
    surtunme_acisi = math.degrees(math.atan(mu_k))
    sekiller.kutu_yuvasi(SEKIL / "sekil_09_kutu_yuvasi.png", kt, vurus_merkezi(p), secenekler, oner, surtunme_acisi)
    i_oner = list(secenekler).index(oner)
    fx_max = float(kt_sec["fx_toparlanma"][i_oner])
    kayma = yuva_analizi.kayma_etkisi(tasarim, [0.001, 0.002, 0.005, 0.010], fx_max)
    D["tablo_kayma"] = tablo(
        ["Boşluk δ (her yönde)", "KM kayması $\\Delta x_c$ [mm]", "Trim açısı değişimi", "Duvara çarpma hızı [m/s]", "Gövdede $\\Delta\\dot\\theta$ [rad/s]"],
        [[f"{s(1000 * x['delta'], 0)} mm", s(1000 * x["dx_c"], 3), f"{s(x['dtrim'], 3)}°", s(x["carpma_dv"], 3), s(x["dthetad"], 3)] for x in kayma],
    )
    tvb = tasarim.degistir({"yuk.kutu.kutle": tasarim.kayit("yuk.kutu.kutle")["aralik"][1]})
    kayma_agir = yuva_analizi.kayma_etkisi(tvb, [tasarim.d("yuk.yuva.bosluk")], fx_max)[0]
    D["tablo_secenek"] = tablo(
        ["Ölçüt", *[yuva_analizi.YUVA_ETIKETLERI[a] for a in secenekler]],
        [
            ["Kutu merkezinin yüksekliği [mm]", *[s(1000 * z, 0) for z in secenekler.values()]],
            ["Kutu eklenince $\\Delta l$ [mm]", *[s(1000 * x["dl"], 1) for x in ka if x["kutulu"]]],
            ["Kutu eklenince kutup değişimi", *[f"%{s(x['dp_yuzde'], 1)}" for x in ka if x["kutulu"]]],
            ["Kutu eklenince statik tork değişimi", *[f"%{s(x['dtau_yuzde'], 1)}" for x in ka if x["kutulu"]]],
            ["Yuvada en büyük görünür eğim, toparlanma", *[f"{s(a, 1)}°" for a in kt_sec["alfa_toparlanma"]]],
            ["Yuvada en büyük görünür eğim, Ö1 öteleme", *[f"{s(a, 1)}°" for a in kt_sec["alfa_oteleme"]]],
            ["Kamera görüşü (Ö4, §5.2 'taşınan eşyanın durumu')", "açık", "gövde içinde, kısmen kapalı", "kapalı"],
            ["Her test başında kutuyu yerleştirme", "kolay", "yandan, zor", "zor"],
            ["İç yerleşime etkisi", "yok", "kat düzeni değişir", "elektronik katıyla çakışır"],
        ],
        ["l", "c", "c", "c"],
    )
    D |= {
        "z_cp": s(1000 * vurus_merkezi(p), 0), "surtunme_acisi": s(surtunme_acisi, 1), "mu_k": s(mu_k, 1),
        "alfa_oner": s(float(kt_sec["alfa_toparlanma"][i_oner]), 1), "alfa_oran": s(surtunme_acisi / float(kt_sec["alfa_toparlanma"][i_oner]), 1),
        "fx_max": s(fx_max, 2), "oner_etiket": yuva_analizi.YUVA_ETIKETLERI[oner].lower(),
        "l0": s(1000 * p0.l, 1), "l1": s(1000 * p.l, 1), "dl_oner": s(1000 * (p.l - p0.l), 1),
        "xc": s(1000 * g_kutulu.km[0], 2), "trim": s(math.degrees(-math.atan2(g_kutulu.km[0], g_kutulu.km[2])), 2),
        "dp_oner": s([x for x in ka if x["kutulu"] and x["yuva"] == oner][0]["dp_yuzde"], 1),
        "dp_max": s(max(abs(x["dp_yuzde"]) for x in ka if x["kutulu"]), 1),
        "dl_max": s(max(abs(1000 * x["dl"]) for x in ka if x["kutulu"]), 1),
        "dtau_oner": s([x for x in ka if x["kutulu"] and x["yuva"] == oner][0]["dtau_yuzde"], 1),
        "kutu_agir": s(1000 * tvb.d("yuk.kutu.kutle"), 0), "dtrim_agir": s(kayma_agir["dtrim"], 3),
        "bosluk": s(1000 * tasarim.d("yuk.yuva.bosluk"), 0), "duvar": s(1000 * tasarim.d("yuk.yuva.duvar_yuksekligi"), 0),
        "kutu_y": s(1000 * tasarim.d("yuk.kutu.boyut")[2], 0), "kutu_oran_BH": s(tasarim.d("yuk.kutu.boyut")[0] / tasarim.d("yuk.kutu.boyut")[2], 1),
        "devrilme_acisi": s(math.degrees(math.atan(tasarim.d("yuk.kutu.boyut")[0] / tasarim.d("yuk.kutu.boyut")[2])), 0),
    }
    zb = np.linspace(0.03, 0.23, 11)
    bt = yuva_analizi.batarya_taramasi(tasarim, zb)
    sekiller.km_yuksekligi(SEKIL / "sekil_08_km_yuksekligi.png", bt, p.l)
    D |= {
        "bt_l_min": s(1000 * bt["l"][0], 0), "bt_l_max": s(1000 * bt["l"][-1], 0),
        "bt_p_min": s(bt["p_serbest"].min()), "bt_p_max": s(bt["p_serbest"].max()),
        "bt_kok_min": s(bt["kok_g_l"][-1]), "bt_kok_max": s(bt["kok_g_l"][0]),
        "bt_tau_min": s(bt["tau_statik"][0], 3), "bt_tau_max": s(bt["tau_statik"][-1], 3),
        "bt_tau_artis": s(100 * (bt["tau_statik"][-1] / bt["tau_statik"][0] - 1), 0),
        "bt_t_min": s(1000 * bt["t_dusme"].min(), 0), "bt_t_max": s(1000 * bt["t_dusme"].max(), 0),
        "bt_z_min": s(100 * zb[0], 0), "bt_z_max": s(100 * zb[-1], 0),
        "k_yaricap": s(1000 * math.sqrt(p.I_yy / p.m_b), 0),
    }
    sekiller.yerlesim(SEKIL / "sekil_01_yerlesim.png", tasarim, {a: tasarim.d(f"yuk.yuva.secenek.{a}") for a in secenekler},
                      g_kutusuz.km, g_kutulu.km, vurus_merkezi(p))

    # -- Duyarlılık -------------------------------------------------------------
    satirlar, taban = duyarlilik(tasarim)
    D["tablo_duyarlilik"] = tablo(
        ["Parametre", "Aralık", "Kutup [1/s]", "El hesabı toplam [N·m]", "Tutma torku [N·m]", "En büyük değişim"], satirlar,
        ["l", "l", "r", "r", "r", "r"],
    )
    sira = [satir[0].strip("`") for satir in satirlar]
    D["sira_kutu"] = str(sira.index("yuk.kutu.kutle") + 1)
    D["sira_batarya"] = str(sira.index("govde.batarya.kutle") + 1)
    D["duyarlilik_taban"] = f"kutup {s(taban[0])} 1/s, el hesabı {s(taban[1], 3)} N·m, tutma {s(taban[2], 3)} N·m"
    D["pytest"] = pytest_ozeti() if testler else "(bu üretimde testler çalıştırılmadı)"
    return D


def doldur(sablon: str, D: dict) -> str:
    metin = re.sub(r"@@(\w+)@@", lambda e: D[e.group(1)], sablon)
    kalan = re.findall(r"@@\w+@@", metin)
    if kalan:
        raise KeyError(f"Doldurulmamış yer tutucular: {kalan}")
    return metin


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--testsiz", action="store_true", help="pytest özetini atla")
    ap.add_argument("--parametreler", default=None)
    a = ap.parse_args(argv)
    tasarim = Tasarim.yukle(a.parametreler)
    D = hesapla_ve_ciz(tasarim, testler=not a.testsiz)
    metin = doldur(SABLON.read_text(encoding="utf-8"), D).split("\n", 1)[1]  # şablon uyarısı satırını at
    uyari = "<!-- Otomatik üretildi (python -m denge). Düzenlemek için docs/sablon/hafta03.md ve parametreler.toml dosyalarını değiştirin. -->\n"
    CIKTI.write_text(uyari + metin, encoding="utf-8")
    print(f"Doküman: {CIKTI.relative_to(KOK)}\nŞekiller: {SEKIL.relative_to(KOK)}/\nTestler: {D['pytest']}")


if __name__ == "__main__":
    main()
