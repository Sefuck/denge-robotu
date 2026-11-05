"""3. hafta dokümanını ve şekillerini parametre dosyasından üretir.

Kullanım:  python -m denge            (şekiller + tam belge + toplantı özeti + pytest özeti)
           python -m denge --testsiz  (pytest çalıştırmadan)
           python -m denge --pdf      (ayrıca docs/pdf/ altına PDF; depoya eklenmez)
Şablonlar (docs/sablon/hafta03.md, hafta03_ozet.md) içindeki @@anahtar@@ yer tutucuları doldurulur.
"""

from __future__ import annotations

import argparse
import datetime
import math
import re
import subprocess
import sys
import unicodedata

import numpy as np

from . import model, motor, sekiller, step, yuva_analizi
from . import simulasyon as sim
from .kutle_merkezi import vurus_merkezi, yere_degme_acilari
from .parametreler import KOK, Tasarim, fiziksel_mi, step_parametresi_mi

DOCS = KOK / "docs"
SEKIL = DOCS / "sekiller"
SABLON = DOCS / "sablon" / "hafta03.md"
CIKTI = DOCS / "hafta03_model_tork_km.md"
OZET_SABLON = DOCS / "sablon" / "hafta03_ozet.md"
OZET = DOCS / "hafta03_toplanti_ozeti.md"
PDF_DIZINI = DOCS / "pdf"

KGFCM = motor.KGFCM
DURUM_ETIKETI = {"tahmini": "tahmini", "ön liste": "ön liste", "doğrulanamadı": "[doğrulanamadı]", "ölçülmüş": "ölçülmüş",
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
def github_slug(baslik: str) -> str:
    """GitHub'ın Markdown başlık çapası: küçük harf, noktalama atılır, boşluk → tire."""
    kucuk = baslik.strip().lower()
    return "".join(c for c in kucuk if c.isalnum() or c in " -_" or unicodedata.category(c).startswith("M")).replace(" ", "-")


def bolum_baglari(metin: str, dosya: str) -> dict[str, str]:
    """'## 4. …' ve '### 4.7 …' başlıklarından bag_4, bag_4_7 → 'dosya#çapa' sözlüğü."""
    baglar = {}
    for e in re.finditer(r"^#{2,3} (\d+(?:\.\d+)?)\.? .*$", metin, re.M):
        baslik = e.group(0).lstrip("#").strip()
        baglar["bag_" + e.group(1).replace(".", "_")] = f"{dosya}#{github_slug(baslik)}"
    return baglar


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
        if yol.startswith(("batarya.", "zemin.", "yuk.kutu.surtunme", "teker.genislik")) or step_parametresi_mi(yol):
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
def step_bolumu(tasarim: Tasarim, g: dict, en_iyi: dict, V: dict, cpr_min: float) -> dict:
    """§10: step motor seçeneği ve DC ile karşılaştırma."""
    D: dict[str, str] = {}
    dc = tasarim.tahrik_tasarimi("dc")
    st = tasarim.tahrik_tasarimi("step")
    pd, ps = dc.model(kutulu=True), st.model(kutulu=True)
    egri = step.PullOut(tasarim)
    gs = motor.gereksinimleri_hesapla(st)
    man = step.manevralar(st)
    I, I2 = tasarim.d("step_hedef.akim_limiti"), tasarim.d("step_hedef.akim_limiti_sogutmali")
    Vm, Vn, V12 = V["min"], V["nominal"], 12.0
    SF = gs["SF"]
    nA, tA = gs["nokta_A"]
    tA0 = gs["nokta_A0"][1]
    nB = gs["nokta_B"][0]
    th0 = math.radians(tasarim.d("sartname.toparlanma_acisi"))
    T_ref = tasarim.d("hedef.referans_manevra_suresi")
    D["st_ad"] = tasarim.d("step_adayi.ad")
    D["st_egri_durumu"] = "ölçülmüş" if egri.olcum is not None else "geçici, kardeş motorlardan türetildi [doğrulanamadı]"

    # -- Şekiller
    sekiller.step_kardes(SEKIL / "sekil_10_step_kardes.png", egri)
    sekiller.step_cekme(SEKIL / "sekil_12_step_cekme.png", egri, {"12 V": V12, f"Boş batarya, {s(Vm, 1)} V": Vm}, I,
                        {"A": gs["nokta_A"], "A₀": gs["nokta_A0"], "A'": gs["nokta_A_asgari"], "B": gs["nokta_B"]}, man, gs["cekis_toplam"] / 2)
    sekiller.step_toparlanma(SEKIL / "sekil_11_step_toparlanma.png", man[0]["yorunge"], T_ref)

    # -- Sargılar ve kardeş eğriler
    a, b = egri.sargilar
    D["tablo_st_sargi"] = tablo(
        ["Değer", "1,5 A'lik satış (robo90, samm)", "1,7 A'lik katalog (MotionKing)", "Birinci sütunun kaynağı"],
        [["Faz akımı", f"{s(a.I_anma, 1)} A", f"{s(b.I_anma, 1)} A", "robo90, samm"],
         ["Faz direnci", f"{s(a.R, 1)} Ω", f"{s(b.R, 1)} Ω", "robo90, samm"],
         ["Faz endüktansı", f"{s(1000 * a.L, 1)} mH", f"{s(1000 * b.L, 1)} mH", "samm (robo90'da yok)"],
         ["Tutma torku", f"{s(100 * a.T_tutma, 0)} N·cm", f"≥ {s(100 * b.T_tutma, 0)} N·cm", "samm (robo90'da yok)"],
         ["Detent torku", f"{s(100 * a.T_detent, 1)} N·cm", f"≤ {s(100 * b.T_detent, 1)} N·cm", "samm (robo90'da yok)"],
         ["Rotor ataleti", f"{s(1e7 * a.J_rotor, 0)} g·cm²", f"{s(1e7 * b.J_rotor, 0)} g·cm²", "samm (robo90'da yok)"],
         ["Kütle", f"{s(1000 * a.kutle, 0)} g", f"{s(1000 * b.kutle, 0)} g", "robo90, samm"],
         ["Gövde boyu", f"{s(1000 * st.d('step_sargi.robo90.boy'), 0)} mm", f"{s(1000 * st.d('step_sargi.katalog.boy'), 0)} mm", "robo90, samm"],
         ["Mil çapı", "bulunamadı [doğrulanamadı]", f"Ø{s(1000 * st.d('step_sargi.katalog.mil_capi'), 0)} mm", "-"],
         ["Pull-out eğrisi", "bulunamadı", "bulunamadı", "-"]],
        ["l", "r", "r", "l"],
    )
    k1, k2 = egri.kardesler
    D["tablo_st_kardes"] = tablo(
        ["Kardeş motor (24 V)", "Akım (etkin)", "R, L", "Tutma torku", "En yüksek pull-out", "$n_b$", "$n_b$'de tork kaybı"],
        [[ad, f"{s(k.I_etkin, 2)} A", f"{s(k.R, 2)} Ω, {s(1000 * k.L, 1)} mH", f"{s(100 * k.T_tutma, 0)} N·cm", f"{s(100 * k.plato, 0)} N·cm", f"{s(k.n_b, 0)} dev/dk",
          f"%{s(100 * (1 - float(np.interp(1.0, k.s, k.g))), 0)}"] for ad, k in (("17HS15-1504S", k1), ("17HS15-1684S", k2))],
        ["l", "r", "r", "r", "r", "r", "r"],
    )
    D["st_capraz"] = s(100 * egri.capraz_hata(), 0)
    D["st_kayip_nb"] = "–".join(sorted({s(100 * (1 - float(np.interp(1.0, k.s, k.g))), 0) for k in (k1, k2)}))
    D["st_T_etiket"] = s(100 * a.T_tutma, 0)
    D["st_rezonans"] = s(egri.rezonans, 2)
    D["st_nb_a_12"] = s(step.gerilim_payi_devri(V12, I, a.K_t, a.R, a.L, tasarim.d("surucu.drv8825.rds_toplam")), 0)
    D["st_nb_a_9"] = s(step.gerilim_payi_devri(Vm, I, a.K_t, a.R, a.L, tasarim.d("surucu.drv8825.rds_toplam")), 0)
    D["st_nb_b_12"] = s(step.gerilim_payi_devri(V12, I, b.K_t, b.R, b.L, tasarim.d("surucu.drv8825.rds_toplam")), 0)
    D["st_nb_b_9"] = s(step.gerilim_payi_devri(Vm, I, b.K_t, b.R, b.L, tasarim.d("surucu.drv8825.rds_toplam")), 0)
    ayar = {"st_I": s(I, 1), "st_I_etkin": s(I / math.sqrt(2), 2), "st_T_a": s(100 * a.K_t * I, 1), "st_T_b": s(100 * b.K_t * I, 1),
            "st_vref": s(I / tasarim.d("surucu.drv8825.vref_kazanc"), 2), "st_I2": s(I2, 1), "st_I_tam": s(I / math.sqrt(2) * 100 / a.I_anma, 0)}
    D |= ayar
    aralik = lambda n_, V_: f"{s(100 * float(egri.alt(n_, V_, I)[0]), 1)}–{s(100 * float(egri.ust(n_, V_, I)[0]), 1)}"
    D["tablo_st_egri"] = tablo(
        ["Devir [dev/dk]", "Tam adım/s", "12 V: alt–üst [N·cm]", f"{s(Vm, 1)} V: alt–üst [N·cm]"],
        [[f"{n_}", s(n_ / 60 * 200, 0), aralik(n_, V12), aralik(n_, Vm)] for n_ in (30, 60, 105, 150, 200, 300, 400)],
    )

    # -- Model
    Aa, Ba, _, _ = model.ivme_girisli_durum_uzay(ps)
    Aal, Bal, _, _ = model.bagil_ivme_girisli_durum_uzay(ps)
    tfa = model.ivme_transfer_fonksiyonu(ps)
    ka = model.ivme_katsayilari(ps)
    D |= {"st_Aa": matris(Aa), "st_Ba": matris(Ba), "st_Aal": matris(Aal), "st_Bal": matris(Bal), "st_K_a": m(tfa["K_a"]), "st_z2": m(tfa["z2"]),
          "st_c1": m(ka["c1"]), "st_c2": m(ka["c2"]), "st_Jk": m(ka["J_k"]), "st_z": s(math.sqrt(tfa["z2"])), "st_z_m": m(math.sqrt(tfa["z2"])),
          "st_pk": s(model.kilitli_kutup(ps)), "st_pu": s(model.kararsiz_kutup(ps)), "st_zaman": s(1000 / math.sqrt(tfa["z2"]), 0),
          "st_Jm": s(1e7 * ps.J_m, 0)}
    y0 = man[0]["yorunge"]
    y_ref = sim.referans_toparlanma(ps, th0, T_ref)
    ileri = sim.ivme_girisli_ileri_simulasyon(ps, sim.ivme_fonksiyonu(ps, y_ref), [0.0, 0.0, th0, 0.0], y_ref["t"])
    D |= {"st_T_ref": s(T_ref, 1), "st_a_tepe": s(float(np.max(np.abs(y0["a"]))), 2), "st_n_tepe": s(float(man[0]["n"].max()), 0), "st_tau_tepe": s(100 * float(man[0]["tau"].max()), 1),
          "st_x_f": s(100 * y_ref["x_f"], 0)}
    hata = math.degrees(float(np.max(np.abs(ileri["theta"] - y_ref["theta"]))))
    D["st_ileri_hata"] = "< 0,001" if hata < 1e-3 else s(hata, 3)

    # -- Kütle etkisi
    temas_d, temas_s = yere_degme_acilari(dc), yere_degme_acilari(st)
    yd_d, yd_s = (temas_d["ileri"], temas_d["geri"]), (temas_s["ileri"], temas_s["geri"])
    dus = lambda p_, yd, mod: [sim.acik_cevrim_dusme(p_, i * th0, mod=mod, yere_degme=yd)["t_degme"] for i in (1, -1)]
    tum_d, tum_s = dus(pd, yd_d, "serbest") + dus(pd, yd_d, "kilitli"), dus(ps, yd_s, "serbest") + dus(ps, yd_s, "kilitli")
    gv_d, gv_s = dc.govde(kutulu=True), st.govde(kutulu=True)
    m_d, m_s = dc.toplam_kutle(kutulu=True), st.toplam_kutle(kutulu=True)
    satir = lambda ad, f, n_, olcek=1.0: [ad, s(olcek * f(0), n_), s(olcek * f(1), n_), f"%{s(100 * (f(1) / f(0) - 1), 0)}" if f(0) else "-"]
    secenek = lambda d_, s_: (lambda i: d_ if i == 0 else s_)
    D["tablo_st_kutle"] = tablo(
        ["Büyüklük", "DC (motor başı 150 g)", "Step (motor başı 300 g)", "Değişim"],
        [satir("Toplam kütle, kutulu [kg]", secenek(m_d, m_s), 2),
         satir("Gövde kütlesi $m_b$ [kg]", secenek(pd.m_b, ps.m_b), 3),
         satir("Aks → KM uzaklığı $l$ [mm]", secenek(pd.l, ps.l), 1, 1000),
         satir("Yatay KM ofseti $x_c$ [mm]", secenek(gv_d.km[0], gv_s.km[0]), 2, 1000),
         satir("Yunuslama ataleti $I_{yy}$ [g·m²]", secenek(pd.I_yy, ps.I_yy), 2, 1000),
         satir("$m_b l$ [g·m]", secenek(pd.m_b * pd.l, ps.m_b * ps.l), 1, 1000),
         satir("Statik tork $m_b g l \\sin 10°$ [N·m]", secenek(pd.m_b * pd.g * pd.l * math.sin(th0), ps.m_b * ps.g * ps.l * math.sin(th0)), 3),
         satir("El hesabı, iki motor [N·m]", secenek(g["el"]["toplam"], gs["el"]["toplam"]), 3),
         satir("10°'de tutma torku, tam model [N·m]", secenek(g["tutma_tam"], gs["tutma_tam"]), 3),
         satir("Çekiş sınırı, iki motor [N·m]", secenek(g["cekis_toplam"], gs["cekis_toplam"]), 3),
         satir("Kararsız kutup, tork girişi [1/s]", secenek(model.kararsiz_kutup(pd), model.kararsiz_kutup(ps)), 2),
         satir("Kilitli teker kutbu [1/s]", secenek(model.kilitli_kutup(pd), model.kilitli_kutup(ps)), 2),
         satir("Kutunun toplam kütledeki payı [%]", secenek(100 * tasarim.d("yuk.kutu.kutle") / m_d, 100 * tasarim.d("yuk.kutu.kutle") / m_s), 1),
         ["Pasif düşme süresi, ±10° [s]", f"{s(min(tum_d))}–{s(max(tum_d))}", f"{s(min(tum_s))}–{s(max(tum_s))}", "-"]],
    )
    D |= {"st_m": s(m_s, 2), "st_m_dc": s(m_d, 2), "st_dm": s(m_s - m_d, 2), "st_l": s(1000 * ps.l, 1), "st_l_dc": s(1000 * pd.l, 1),
          "st_cekis_motor": s(100 * gs["cekis_toplam"] / 2, 1)}

    # -- Adım kaçırma
    sonuc_st = lambda x: "geçer" if x["rezonans"] >= 1 else ("rezonans yoksa geçer" if x["alt"] >= 1 else "**geçmez**")
    noktalar = [{"ad": ad, "n": np.array([n_]), "tau": np.array([t_])} for ad, (n_, t_) in
                ((f"A: el hesabı × SF {s(SF, 0)}", gs["nokta_A"]), ("A₀: el hesabı", gs["nokta_A0"]), ("A': çekiş sınırı", gs["nokta_A_asgari"]), ("B: seyir + hız payı", gs["nokta_B"]))]
    pay_satir = []
    for x in noktalar + man:
        p12, p9 = step.pay(egri, x, V12, I), step.pay(egri, x, Vm, I)
        pay_satir.append([x["ad"], s(float(x["n"].max()), 0), s(100 * float(x["tau"].max()), 1), f"{s(p12['alt'])}–{s(p12['ust'])}", f"{s(p9['alt'])}–{s(p9['ust'])}", s(p9["rezonans"]), sonuc_st(p9)])
    D["tablo_st_pay"] = tablo(["Nokta / manevra", "Tepe devir [dev/dk]", "Tepe tork [N·cm]", "Pay, 12 V (alt–üst)", f"Pay, {s(Vm, 1)} V (alt–üst)", f"Pay, {s(Vm, 1)} V alt × rezonans", "Sonuç (boş batarya)"],
                              pay_satir, ["l", "r", "r", "r", "r", "r", "l"])
    pA, pA0, pA2 = (step.pay(egri, x, Vm, I) for x in noktalar[:3])
    mn = [step.pay(egri, x, Vm, I) for x in man]
    T_A_alt = float(egri.alt(nA, Vm, I)[0])
    n_sf, n_a0 = step.devir_siniri(egri, tA, Vm, I), step.devir_siniri(egri, tA0, Vm, I)
    n_sf12, n_a012 = step.devir_siniri(egri, tA, V12, I), step.devir_siniri(egri, tA0, V12, I)
    mu = tasarim.d("zemin.surtunme")
    a_tavan = step.ivme_siniri(ps, T_A_alt / SF, mu)
    bm = step.burulma_modu(ps, float(egri.alt(0.0, Vm, I)[0]))
    D |= {"st_pay_A_alt": s(pA["alt"]), "st_pay_A_ust": s(pA["ust"]), "st_pay_A_rez": s(pA["rezonans"]),
          "st_sf_alt": s(pA0["alt"]), "st_sf_ust": s(pA0["ust"]), "st_sf_rez": s(pA0["rezonans"]), "st_tA": s(100 * tA, 1), "st_tA0": s(100 * tA0, 1), "st_nA": s(nA, 0),
          "st_pay_A2_alt": s(pA2["alt"]), "st_pay_man_min": s(min(x["alt"] for x in mn)), "st_pay_man_rez": s(min(x["rezonans"] for x in mn)),
          "st_n_sf": s(n_sf, 0), "st_n_a0": s(n_a0, 0), "st_n_sf12": s(n_sf12, 0), "st_n_a012": s(n_a012, 0), "st_v_sf": s(n_sf * 2 * math.pi * ps.r / 60, 2),
          "st_a_tavan": s(a_tavan, 1), "st_mug": s(mu * ps.g, 1), "st_f_burulma": s(bm["f"], 0), "st_J_orani": s(bm["J_yuk"] / ps.J_m, 0),
          "st_n_burulma": s(bm["f"] / 200 * 60, 0)}

    # -- Adım frekansı
    r = ps.r
    pencere = tasarim.d("hedef.hiz_kestirim_penceresi")
    f_k = tasarim.d("hedef.kontrol_frekansi")
    mikro = tasarim.d("step_hedef.mikro_adim")
    tb = step.mikro_adim_tablosu(r, pencere, (nB, n_sf), f_k)
    D["tablo_st_mikro"] = tablo(
        ["Mikro adım", "Adım/teker devri", "Yol/adım [mm]", f"Hız adımı ({s(1000 * pencere, 0)} ms) [m/s]", f"STEP @ {s(nB, 0)} dev/dk [kHz]", f"STEP @ {s(n_sf, 0)} dev/dk [kHz]", "Adım/kontrol çevrimi", f"≥ {s(cpr_min, 0)} sayım"],
        [[f"1/{x['mikro']}" + (" [öneri]" if x["mikro"] == mikro else ""), str(x["cpr"]), s(1000 * x["ds"], 3), s(x["dv"], 3), s(x["f1"] / 1000, 2), s(x["f2"] / 1000, 2), s(x["adim_cevrim"], 1), "yeterli" if x["cpr"] >= cpr_min else "yetersiz"] for x in tb],
        ["l", "r", "r", "r", "r", "r", "r", "l"],
    )
    sec = next(x for x in tb if x["mikro"] == mikro)
    Ts = 1.0 / f_k
    plan = tasarim.d("step_hedef.planlama_suresi")
    z = math.sqrt(tfa["z2"])
    D |= {"st_mikro": f"1/{mikro}", "st_cpr": str(sec["cpr"]), "st_f_sf": s(sec["f2"] / 1000, 1),
          "st_f_max": s(tasarim.d("surucu.drv8825.f_step_max") / 1000, 0),
          "st_gecikme": s(1000 * (Ts + plan), 0), "st_gecikme_var": s(1000 * (Ts + 0.020), 0), "st_pt": s(z * (Ts + plan), 2), "st_pt_var": s(z * (Ts + 0.020), 2), "st_plan": s(1000 * plan, 0)}

    # -- Güç ve pil
    Rds = tasarim.d("surucu.drv8825.rds_toplam")
    P_l = tasarim.d("guc.lojik_gucu")
    C = tasarim.d("guc.batarya_kapasitesi")
    r_th = tasarim.d("surucu.drv8825.r_theta_ja")
    sinir = tasarim.d("surucu.motor_isinma_siniri")
    akim_satir = []
    for Ii in (1.0, 1.2, I, I2):
        gu = step.step_guc(a, Ii, Vn, Rds, P_l)
        akim_satir.append([s(Ii, 1) + (" [öneri]" if Ii == I else ""), s(Ii / tasarim.d("surucu.drv8825.vref_kazanc"), 2), s(Ii / math.sqrt(2), 2),
                           f"{s(100 * float(egri.alt(nA, Vm, Ii)[0]), 1)}–{s(100 * float(egri.ust(nA, Vm, Ii)[0]), 1)}", s(float(egri.alt(nA, Vm, Ii)[0]) / tA0, 2),
                           s(gu["P_bakir"], 1), s(gu["P_surucu"], 1), s(gu["I_bat"], 2), s(step.pil_suresi(C, Vn, gu["P_top"]), 1),
                           f"≈ {s(step.motor_isinmasi(a, Ii, sinir), 0)}", f"≈ {s(step.surucu_isinmasi(gu['P_surucu'], r_th), 0)}"])
    D["tablo_st_akim"] = tablo(
        ["Akım limiti [A, tepe]", "VREF [V]", "Faz etkin [A]", f"Tork @ {s(nA, 0)} dev/dk, {s(Vm, 1)} V [N·cm]", "Sağlanan SF (alt)", "Bakır kaybı, motor başı [W]", "Sürücü kaybı, sürücü başı [W]",
         f"Pil akımı, {s(Vn, 1)} V [A]", "Pil süresi [saat]", "Motor ısınması [°C]", "Sürücü ısınması [°C]"], akim_satir)
    gu0 = step.step_guc(a, I, Vn, Rds, P_l)
    guA = step.step_guc(a, I, Vm, tasarim.kayit("surucu.drv8825.rds_toplam")["aralik"][1], P_l, tA, nA)
    guS = step.step_guc(a, I, Vm, tasarim.kayit("surucu.drv8825.rds_toplam")["aralik"][1], P_l, float(egri.ust(n_sf, Vm, I)[0]), n_sf)
    gu2 = step.step_guc(a, I2, Vn, Rds, P_l)
    h_st, h_st2 = step.pil_suresi(C, Vn, gu0["P_top"]), step.pil_suresi(C, Vn, gu2["P_top"])
    a333 = en_iyi["aday"]
    P_dc0 = 2 * a333.bosta_akim * Vn + P_l
    h_dc = step.pil_suresi(C, Vn, P_dc0)
    i_dc_A = 2 * a333.akim(min(g["nokta_A"][1], a333.tork(g["nokta_A"][0], Vm)))
    sigorta = tasarim.d("elektrik.sigorta")
    kilit_dc = 2 * a333.durma_akimi * V["max"] / a333.gerilim
    D["tablo_st_guc"] = tablo(
        ["Durum", f"Step, {s(I, 1)} A limit", "DC 333 RPM", f"{s(sigorta, 0)} A sigorta"],
        [["Dengede dururken, pil akımı (lojik dahil)", f"{s(gu0['I_bat'], 2)} A", f"≈ {s(P_dc0 / Vn, 2)} A (boşta akım, üst sınır)", "ikisi de rahat"],
         [f"Aynı durumda pil süresi ({s(1000 * C, 0)} mAh, {s(Vn, 1)} V)", f"{s(h_st, 1)} saat", f"≈ {s(h_dc, 1)} saat", "-"],
         [f"A noktası, {s(Vm, 1)} V", f"{s(guA['I_bat'], 2)} A", f"{s(i_dc_A + P_l / Vm, 2)} A", "ikisi de rahat"],
         ["En kötü durum", f"{s(guS['I_bat'], 2)} A: akım sürücüde sınırlı, kilitlenmede artmaz", f"iki motor kilitli: {s(kilit_dc, 2)} A (dolu pil, {s(V['max'], 1)} V)", "step rahat, DC sınırda"]],
        ["l", "r", "r", "l"],
    )
    D |= {"st_I_bat": s(gu0["I_bat"], 2), "st_h": s(h_st, 1), "st_h2": s(h_st2, 1), "st_h_dc": s(h_dc, 1), "st_I_bat_dc": s(P_dc0 / Vn, 2),
          "st_I_bat_max": s(guS["I_bat"], 2), "st_dT_m": s(step.motor_isinmasi(a, I, sinir), 0), "st_dT_m2": s(step.motor_isinmasi(a, I2, sinir), 0),
          "st_dT_s": s(step.surucu_isinmasi(gu0["P_surucu"], r_th), 0), "st_tsd": s(tasarim.d("surucu.drv8825.tsd_min"), 0), "st_P_s": s(gu0["P_surucu"], 1), "st_r_th": s(r_th, 1),
          "st_Rds": s(Rds, 2), "st_V_min_s": s(tasarim.d("surucu.drv8825.besleme_min"), 1), "st_P_l": s(P_l, 0), "st_V_pay": s(Vm - tasarim.d("surucu.drv8825.besleme_min"), 1)}

    # -- Çözünürlük ve AS5600
    a_cpr = tasarim.d("sensor.as5600.cozunurluk")
    dc_cpr = 4 * a333.ppr * a333.reduksiyon
    tepe = float(egri.alt(0.0, Vm, I)[0])
    lag_A = math.degrees(step.yuk_gecikmesi(tA, tepe))
    lag_t = math.degrees(step.yuk_gecikmesi(gs["tutma_tam"] / 2, tepe))
    coz = lambda c: [s(360 / c, 3), s(1000 * 2 * math.pi * r / c, 3), s(2 * math.pi * r / (c * pencere), 3)]
    D["tablo_st_coz"] = tablo(
        ["Kaynak", "Sayım/teker devri", "°/sayım", "mm/sayım", f"Hız adımı ({s(1000 * pencere, 0)} ms) [m/s]", "Neyi söyler"],
        [["DC 333 RPM enkoder (x4)", f"{dc_cpr:.0f}", *coz(dc_cpr), "Motor milinin gerçek açısı; redüktör boşluğu kadar belirsiz"],
         [f"Step adım sayımı, {D['st_mikro']}", D["st_cpr"], *coz(sec["cpr"]), "Komutu söyler, gerçek açıyı değil; adım kaçarsa sayım bozulur"],
         ["AS5600 (12 bit)", f"{a_cpr}", *coz(a_cpr), "Milin gerçek açısı; doğrusallık hatası ±1°, gürültü 0,015–0,043° (1σ)"]],
        ["l", "r", "r", "r", "r", "l"],
    )
    gec = tasarim.d("sensor.as5600.gecikme")
    esik = tasarim.d("step_hedef.kayip_esigi")
    kayip_der = 4 * 1.8
    D |= {"st_dc_cpr": f"{dc_cpr:.0f}", "st_lag_A": s(lag_A, 2), "st_lag_A_mm": s(math.radians(lag_A) * r * 1000, 2), "st_lag_t": s(lag_t, 2),
          "st_kayip_der": s(kayip_der, 1), "st_kayip_lsb": s(kayip_der / 360 * a_cpr, 0), "st_esik_der": s(esik * 1.8, 1), "st_esik_lsb": s(esik * 1.8 / 360 * a_cpr, 0),
          "st_as_gec": s(1000 * gec, 2), "st_as_gec_der": s(float(man[2]["n"].max()) * 6 * gec, 2), "st_n_o1": s(float(man[2]["n"].max()), 0),
          "st_as_lsb": s(360 / a_cpr, 3)}

    # -- Pasif test
    det = lambda T: [sim.detent_dusme(ps, i * th0, T, yd_s)["t_degme"] for i in (1, -1)]
    Td_a, Td_b = 2 * a.T_detent, 2 * b.T_detent
    t_ser, t_kil = dus(ps, yd_s, "serbest"), dus(ps, yd_s, "kilitli")
    t_a, t_b = det(Td_a), det(Td_b)
    D["tablo_st_detent"] = tablo(
        ["Durum (motorlar enerjisiz)", "İki motorun toplam torku", "+10°'den yere değme", "−10°'den yere değme", "5 s sınırı"],
        [["Serbest mil (detent yok sayıldı)", "0", f"{s(t_ser[0])} s", f"{s(t_ser[1])} s", "düşer, testi geçer"],
         [f"Detent {s(100 * a.T_detent, 1)} N·cm/motor", f"{s(100 * Td_a, 1)} N·cm", f"{s(t_a[0])} s", f"{s(t_a[1])} s", "düşer, testi geçer"],
         [f"Detent {s(100 * b.T_detent, 1)} N·cm/motor", f"{s(100 * Td_b, 1)} N·cm", f"{s(t_b[0])} s", f"{s(t_b[1])} s", "düşer, testi geçer"],
         ["Mil tam kilitli (üst sınır)", "sonsuz", f"{s(t_kil[0])} s", f"{s(t_kil[1])} s", "düşer, testi geçer"]],
        ["l", "r", "r", "r", "l"],
    )
    D |= {"st_t_min": s(min(t_ser + t_kil)), "st_t_max": s(max(t_ser + t_kil)), "st_crr": s(ps.m_b * ps.l * math.sin(th0) / (m_s * ps.r), 2),
          "st_T_d_top": s(100 * Td_b, 1), "st_statik": s(100 * ps.m_b * ps.g * ps.l * math.sin(th0), 1)}

    # -- Mekanik
    yuk = ps.m_b * ps.g / 2
    kose = math.hypot(0.02115, 0.02115)
    D |= {"st_radyal": s(yuk, 1), "st_radyal_sinir": s(tasarim.d("step_adayi.radyal_yuk_siniri"), 0),
          "st_kose": s(1000 * kose, 1), "st_kose_pay": s(1000 * (ps.r - kose), 1), "st_r": s(1000 * ps.r, 1)}

    # -- Karşılaştırma
    c_st, c_dc = 2 * tasarim.d("maliyet.step_motor"), 2 * (tasarim.d("maliyet.dc_motor") + tasarim.d("maliyet.bts7960"))
    sf_dc, sf_dc_nom = en_iyi["nokta_A"][0] / g["nokta_A0"][1], motor.gereken_sf(a333, g, Vn)
    n0_dc = en_iyi["n0"]
    n_dc_a0 = n0_dc * (1 - g["nokta_A0"][1] / en_iyi["ts"])
    D["tablo_st_karsilastirma"] = tablo(
        ["Başlık", "DC: JGB37-520 333 RPM + BTS7960", "Step: 17HS4401 + DRV8825"],
        [["**Maliyet** (2 adet, KDV dahil)", f"≈ {s(c_dc, 0)} TL (motor {s(tasarim.d('maliyet.dc_motor'), 0)} + sürücü {s(tasarim.d('maliyet.bts7960'), 0)} TL). DRV8825'ler boşa kalır.",
          f"≈ {s(c_st, 0)} TL (motor {s(tasarim.d('maliyet.step_motor'), 0)} TL). Sürücü ve AS5600 alındı. Mil–teker bağlantısı hariç."],
         ["**Tork payı** (boş batarya, ±10°)", f"SF {s(sf_dc)}; nominalde {s(sf_dc_nom)}. Rotor ataleti bilinmiyor; büyükse gereksinim artar.",
          f"SF {D['st_sf_alt']}–{D['st_sf_ust']} [doğrulanamadı]; rezonans düşümüyle {D['st_sf_rez']}. Rotor ataleti ihmal edilecek kadar küçük."],
         ["**Hız payı** (boş batarya)", f"Boşta {s(n0_dc, 0)} dev/dk; A₀ torku {s(n_dc_a0, 0)} dev/dk'ya kadar. Gereken {s(g['nokta_B'][0], 0)} dev/dk.",
          f"A₀ torku ≈ {D['st_n_a0']} dev/dk'ya kadar, 2 kat emniyetli tork ≈ {D['st_n_sf']} dev/dk'ya kadar [doğrulanamadı]. Hız aşılırsa adım kaçar."],
         ["**Konum çözünürlüğü**", f"{D['st_dc_cpr']} sayım/teker devri; gerçek açı, ama redüktör boşluğu ölçülmedi.",
          f"{D['st_cpr']} adım/teker devri ({D['st_mikro']}); yalnız komut. AS5600 ile 4096 sayım gerçek açı."],
         ["**Kütle**", f"Toplam {D['st_m_dc']} kg; $l$ = {D['st_l_dc']} mm.", f"Toplam {D['st_m']} kg (+{D['st_dm']} kg); $l$ = {D['st_l']} mm. Statik tork aynı."],
         ["**Akım ve pil süresi**", f"Dengede ≈ {D['st_I_bat_dc']} A, ≈ {D['st_h_dc']} saat. İki motor kilitlenirse {s(kilit_dc, 2)} A.",
          f"Dengede {D['st_I_bat']} A, {D['st_h']} saat; akım dururken de akar. En kötü durum {D['st_I_bat_max']} A."],
         ["**Kontrol karmaşıklığı**", "Tork ya da gerilim girişi; ölü bölge telafisi, enkoder sayacı, hız kestirimi gerekir. Model $J_m$ ve $b$'ye bağlı; motor gelince tanılanır.",
          "İvme girişi; ölü bölge yok, enkoder ve hız döngüsü yok, model motora bağlı değil. Ama adım üreteci, ivme ve devir sınırı gerekir; tork doğrudan ayarlanamaz."],
         ["**Riskler**", "Redüktör boşluğu dengede titreşim yapabilir; veri sayfası [doğrulanamadı]; $J_m$ bilinmiyor. Aşırı yükte motor yavaşlar, robot hemen kaybedilmez.",
          f"Adım kaçarsa robot düşer. 12 V eğrisi ölçülmedi. Yük/rotor atalet oranı ≈ {D['st_J_orani']}:1 ve ≈ {D['st_f_burulma']} Hz burulma modu. Adım titreşimi IMU'ya gider. Motor sürekli ısınır. Mil–teker bağlantısı ve motor köşesi yerden payı dar."]],
        ["l", "l", "l"],
    )
    esik_gecer, esik_sinir = tA, tA * I / I2
    D |= {"st_c_fark": s(c_dc - c_st, 0), "st_sf_dc": s(sf_dc),
          "st_esik_gecer": s(100 * esik_gecer, 1), "st_esik_sinir": s(100 * esik_sinir, 1), "st_I_oran": s(I2 / I, 1), "st_motor_tl": s(tasarim.d("maliyet.step_motor"), 0)}
    return D


# ---------------------------------------------------------------------------
def hesapla_ve_ciz(tasarim: Tasarim, testler: bool = True) -> dict:
    SEKIL.mkdir(parents=True, exist_ok=True)
    tasarim = tasarim.tahrik_tasarimi("dc")  # §1–§9 DC motor içindir; §10 step motoru ayrıca hesaplar
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
    fiz = [(y, kk) for y, kk in tasarim.kayitlar() if fiziksel_mi(y) and not step_parametresi_mi(y)]
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
        [[f"{tasarim.d('batarya.seri_hucre')}S Li-ion (ön liste)", s(V["min"], 1), s(V["nominal"], 1), s(V["max"], 1),
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

    # -- Aday motor (ön liste: JGB37-520 530 RPM; veri sayfası rcdrone [doğrulanamadı]) --
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

    # -- Step motor seçeneği (§10) ----------------------------------------------
    D |= step_bolumu(tasarim, g, en_iyi, V, e["cpr_min"])

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
    gecen = re.search(r"(\d+) passed", D["pytest"])
    D["pytest_kisa"] = (f"{gecen.group(1)} doğrulama testinin hepsi geçti" if gecen and "failed" not in D["pytest"]
                        else ("testler bu üretimde çalıştırılmadı" if not testler else f"test sonucu: {D['pytest']}"))
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
    ap.add_argument("--pdf", action="store_true", help="docs/pdf/ altına PDF de üret")
    ap.add_argument("--parametreler", default=None)
    a = ap.parse_args(argv)
    tasarim = Tasarim.yukle(a.parametreler)
    D = hesapla_ve_ciz(tasarim, testler=not a.testsiz)
    uyari = "<!-- Otomatik üretildi (python -m denge). Düzenlemek için docs/sablon/{} ve parametreler.toml dosyalarını değiştirin. -->\n"
    metin = doldur(SABLON.read_text(encoding="utf-8"), D).split("\n", 1)[1]  # şablon uyarısı satırını at
    CIKTI.write_text(uyari.format(SABLON.name) + metin, encoding="utf-8")
    D |= bolum_baglari(metin, CIKTI.name)
    ozet = doldur(OZET_SABLON.read_text(encoding="utf-8"), D).split("\n", 1)[1]
    OZET.write_text(uyari.format(OZET_SABLON.name) + ozet, encoding="utf-8")
    print(f"Tam belge: {CIKTI.relative_to(KOK)}\nÖzet: {OZET.relative_to(KOK)}\nŞekiller: {SEKIL.relative_to(KOK)}/\nTestler: {D['pytest']}")
    if a.pdf:
        from . import pdf

        for md, css, baslik in ((OZET, "pdf_ozet.css", "3. Hafta Toplantı Özeti"), (CIKTI, "pdf.css", "3. Hafta: Model, Motor, Kutu Yuvası")):
            hedef = PDF_DIZINI / (md.stem + ".pdf")
            sayfa = pdf.pdf_uret(md, hedef, DOCS / "sablon" / css, baslik)
            print(f"PDF: {hedef.relative_to(KOK)} ({sayfa} sayfa)")
            if md is OZET and sayfa > 1:
                print("UYARI: özet bir sayfayı aşıyor")


if __name__ == "__main__":
    main()
