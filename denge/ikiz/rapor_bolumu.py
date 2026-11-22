"""Belge §12 (Simülasyon) için hesaplar, tablolar, şekiller ve yer tutucular.

`simulasyon_bolumu(tasarim, sekil_dizini, csv_yolu)` senaryo matrisini, motor karşılaştırmasını ve pay taramasını
koşturur (paralel), şekilleri çizer, sonuçları CSV'ye yazar ve şablondaki @@ik_…@@ yer tutucularını döndürür.
"""

from __future__ import annotations

import math
import time
from dataclasses import replace
from pathlib import Path

import numpy as np

from .. import model
from ..kutle_merkezi import yere_degme_acilari
from . import cizim, kontrol, toplu
from .ayarlar import MOTOR_ADLARI, govde, ikiz_ayarlari, motorlar
from .senaryolar import SATIN_ALINAN, SENARYO_ADLARI, SENARYO_KODLARI, Kurulum, calistir, degerlendir, senaryolar


def s(x, n=2) -> str:
    return f"{x:.{n}f}".replace("-", "−").replace(".", ",")


def tablo(basliklar, satirlar, hiza=None) -> str:
    hiza = hiza or ["l"] + ["r"] * (len(basliklar) - 1)
    ayirac = ["---:" if h == "r" else (":---:" if h == "c" else "---") for h in hiza]
    cizgiler = ["| " + " | ".join(basliklar) + " |", "| " + " | ".join(ayirac) + " |"]
    cizgiler += ["| " + " | ".join(str(h) for h in satir) + " |" for satir in satirlar]
    return "\n".join(cizgiler)


DURUM = {"tahmini": "tahmini", "ön liste": "ön liste", "doğrulanamadı": "[doğrulanamadı]", "ölçülmüş": "ölçülmüş", "öneri": "[öneri]",
         "şartname": "şartname", "sabit": "sabit"}
KTR = {"lqr": "LQI", "pid": "PID"}
KST = {"kalman": "Kalman", "tamamlayici": "Tamamlayıcı"}
PIL = {"dolu": "dolu", "bos": "boş"}
ISARET = {True: "✓", False: "✗"}


def _deger(k) -> str:
    d = k["deger"]
    if isinstance(d, bool):
        return "evet" if d else "hayır"
    if isinstance(d, list):
        return "(" + "; ".join(f"{v:g}".replace(".", ",") for v in d) + ")"
    if isinstance(d, str):
        return d
    return f"{d:g}".replace(".", ",")


def _birim(b: str) -> str:
    return b.replace("*", "·").replace("^2", "²").replace("deg", "°").replace("sqrt(Hz)", "√Hz").replace("ug", "µg")


def v(metin: str) -> str:
    """Senaryo değerlendiricisinin metinlerinde ondalık virgül."""
    return metin.replace(".", ",")


def parametre_tablosu(t, onekler) -> str:
    satirlar = [[f"`{y}`", _deger(k), _birim(k["birim"]), DURUM[k["durum"]], k["kaynak"]]
                for y, k in t.kayitlar() if y.startswith(onekler)]
    return tablo(["Parametre", "Değer", "Birim", "Durum", "Kaynak"], satirlar, ["l", "r", "l", "l", "l"])


def simulasyon_bolumu(t, sekil_dizini: Path, csv_yolu: Path, paralel: bool = True, gif: bool = True) -> dict:
    t0 = time.time()
    ay = ikiz_ayarlari(t)
    mot = motorlar(t, ay.J_rotor)
    D: dict[str, str] = {}
    sa, z = ay.senaryo, ay.zaman

    # -- Koşular -------------------------------------------------------------------
    isler = list(dict.fromkeys(toplu.ana_isler() + toplu.motor_isleri()))
    sonuclar = toplu.calistir_hepsi(t, isler, paralel)
    ana = [d for d in sonuclar if d["kurulum"]["motor"] == SATIN_ALINAN]
    pay = toplu.pay_taramasi(t, paralel=paralel)
    J_aralik = t.kayit("ikiz.rotor_ataleti_motor")["aralik"]
    pay_J = {J: toplu.pay_taramasi(t, piller=("bos",), paralel=paralel, J_rotor=J) for J in J_aralik}
    toplu.csv_yaz(csv_yolu, toplu.alt_satirlari(sonuclar))
    D["ik_sure"] = s(time.time() - t0, 0)
    D["ik_n_kosu"] = str(len(sonuclar))
    D["ik_n_ana"] = str(len(ana))

    # -- Ayarlar ve parametreler ------------------------------------------------------
    D |= {"ik_dt_ms": s(1000 * ay.fizik.dt, 1), "ik_Ts_ms": s(1000 * z.Ts, 0), "ik_f_kontrol": s(1 / z.Ts, 0),
          "ik_gec_hesap_ms": s(1000 * z.hesaplama_gecikmesi, 1), "ik_gec_komut": s(z.komut_gecikmesi, 2),
          "ik_pencere_ms": s(1000 * z.hiz_penceresi, 0), "ik_mu": s(ay.fizik.mu, 1), "ik_bosluk_deg": s(math.degrees(ay.fizik.bosluk), 1),
          "ik_R_ic": s(ay.fizik.R_ic, 2), "ik_J_rotor": f"{ay.J_rotor:.1e}".replace(".", ","),
          "ik_dlpf": s(ay.sensor.suzgec_hz, 0), "ik_gyro_std": s(math.degrees(ay.sensor.gyro_gurultu) * math.sqrt(math.pi / 2 * ay.sensor.suzgec_hz), 3),
          "ik_tau_tf": s(ay.kestirim.tau_tamamlayici, 1), "ik_alfa_tf": s(ay.kestirim.tau_tamamlayici / (ay.kestirim.tau_tamamlayici + z.Ts), 3),
          "ik_imu_z": s(1000 * ay.sensor.imu_konum[1], 0), "ik_V_dolu": s(ay.pil["dolu"], 1), "ik_V_bos": s(ay.pil["bos"], 1),
          "ik_durma": s(sa.durma_hizi, 2), "ik_mesafe_tol": s(100 * sa.mesafe_toleransi, 0), "ik_aci_tol": s(math.degrees(sa.aci_toleransi), 0),
          "ik_topar_aci": s(math.degrees(sa.toparlanma_acisi), 0), "ik_tepki_esigi": s(100 * sa.tepki_esigi, 0),
          "ik_baslangic": s(math.degrees(sa.baslangic_egimi), 0), "ik_sigorta": s(sa.sigorta, 0),
          "ik_akim_siniri": s(ay.kontrol.akim_siniri, 1), "ik_telafi": s(ay.kontrol.olu_bolge_telafisi, 1),
          "ik_dusme_esigi": s(math.degrees(ay.kontrol.dusme_esigi), 0), "ik_ref_tau": s(ay.kontrol.referans_suzgeci, 2)}
    D["tablo_ik_param"] = parametre_tablosu(t, ("ikiz.", "imu.", "zamanlama."))
    D["tablo_ik_ayar"] = parametre_tablosu(t, ("kestirim.", "kontrol.yontem", "kontrol.denge_acisi", "kontrol.dusme_esigi", "kontrol.akim_siniri",
                                               "kontrol.olu_bolge_telafisi", "kontrol.zit_emk_telafisi", "kontrol.ileri_besleme", "kontrol.referans_suzgeci",
                                               "senaryo.", "simulasyon."))
    D["tablo_ik_motor"] = tablo(
        ["Motor", "Oran", "K_t [N·m/A]", "K_e [V·s/rad]", "R [Ω]", "I₀ [A]", "Sürtünme K_t·I₀ [N·cm]", "J_m = J_rotor·N² [kg·m²]",
         f"Boşta hız, {s(ay.pil['bos'], 1)} V [m/s]", "Enkoder [sayım/tur]"],
        [[MOTOR_ADLARI[k], f"1:{m.N:g}".replace(".", ","), s(m.K_t, 3), s(m.K_e, 3), s(m.R, 2), s(m.I0, 2), s(100 * m.tau_f, 2),
          f"{m.J_m:.2e}".replace(".", ","), s(m.kararli_devir(ay.pil["bos"]) * t.d("teker.yaricap"), 2), s(m.cpr, 0)] for k, m in mot.items()],
    )

    # -- Kontrolcü kazançları ve kararlılık ----------------------------------------------
    gv = govde(t, True, mot[SATIN_ALINAN])
    a = ay.kontrol
    K_yeni = kontrol.lqr_tasarla(gv.p, a.lqr_Q, a.lqr_R, z.Ts)
    Kp_yeni = kontrol.donus_lqr_tasarla(gv.p, a.lqr_Q_donus, a.lqr_R_donus, z.Ts)
    fark = max(float(np.max(np.abs(np.array(a.lqr_K) - K_yeni) / np.abs(K_yeni))),
               float(np.max(np.abs(np.array(a.lqr_K_donus) - Kp_yeni) / np.abs(Kp_yeni))))
    D["ik_K_fark"] = s(100 * fark, 1)
    ozd = {}
    for etiket, kutulu in (("kutulu", True), ("kutusuz", False)):
        p = govde(t, kutulu, mot[SATIN_ALINAN]).p
        ozd[etiket] = (kontrol.kapali_cevrim_ozdegerleri(p, a.lqr_K, z.Ts), kontrol.kapali_cevrim_ozdegerleri(p, a.lqr_K, z.Ts, 1))
    kut = np.log(ozd["kutulu"][0].astype(complex)) / z.Ts
    kut = sorted(kut, key=lambda c: c.real)
    D["ik_kutuplar"] = ", ".join(s(c.real, 1) if abs(c.imag) < 1e-6 else f"{s(c.real, 1)} ± {s(abs(c.imag), 1)}j" for c in kut if c.imag >= -1e-9)
    D["ik_ozd_max"] = s(max(float(np.max(np.abs(v[0]))) for v in ozd.values()), 4)
    D["ik_ozd_gecikmeli"] = s(max(float(np.max(np.abs(v[1]))) for v in ozd.values()), 4)
    D["ik_kutup_acik"] = s(model.kararsiz_kutup(gv.p), 2)
    kb, kt_, kd = a.ileri_besleme
    D["tablo_ik_kazanc"] = tablo(
        ["Kontrolcü", "Kazanç", "Değer", "Birim / not"],
        [["PID", "İç döngü (K_p, K_i, K_d)", "; ".join(s(x, 3) for x in a.pid_aci), "N·m/rad; N·m/(rad·s); N·m·s/rad"],
         ["PID", "Dış döngü (K_px, K_dx)", "; ".join(s(x, 3) for x in a.pid_konum), "rad/m; rad·s/m → eğim komutu"],
         ["PID", "Eğim komutu sınırı", s(math.degrees(a.aci_komut_siniri), 1) + "°", "dış döngü çıkışı"],
         ["PID", "Dönüş (K_p, K_d)", "; ".join(s(x, 3) for x in a.pid_donus), "N·m/rad; N·m·s/rad (τ_R − τ_L)"],
         ["LQI", "Q (x, ẋ, θ, θ̇, ∫x)", "; ".join(f"{x:g}" for x in a.lqr_Q), f"R = {a.lqr_R:g}"],
         ["LQI", "K", "; ".join(s(x, 3) for x in a.lqr_K), "N·m/m; N·m·s/m; N·m/rad; N·m·s/rad; N·m/(m·s)"],
         ["LQR (dönüş)", "Q (ψ, ψ̇) / R", "; ".join(f"{x:g}" for x in a.lqr_Q_donus) + f" / {a.lqr_R_donus:g}", ""],
         ["LQR (dönüş)", "K_ψ", "; ".join(s(x, 3) for x in a.lqr_K_donus), "N·m/rad; N·m·s/rad"],
         ["İkisi", "İleri besleme (c₁/mgl, M_x r, 2r J_ψ/d)", f"{s(kb, 4)}; {s(kt_, 4)}; {s(kd, 4)}", "rad/(m/s²); N·m/(m/s²); N·m/(rad/s²)"],
         ["İkisi", "İntegral katkı sınırı", s(a.integral_siniri, 3), "N·m"]],
        ["l", "l", "r", "l"],
    )

    # -- Senaryo tanımları ------------------------------------------------------------------
    sens = senaryolar(ay)
    tanim = {
        "O1-1": f"Robot dik konumun {s(math.degrees(sa.baslangic_egimi), 0)}° önünde bırakılır; 30 s",
        "O1-23": f"t = 1 s: ileri {s(sa.o1_mesafe, 1)} m ({s(sa.o1_sure, 0)} s profil); yerleşme {s(sa.yerlesme_suresi, 0)} s + {s(sa.o1_bekleme, 0)} s dur; geri {s(sa.o1_mesafe, 1)} m; {s(sa.o1_bekleme, 0)} s dur",
        "O1-4+": f"Gövde +{s(math.degrees(sa.toparlanma_acisi_baslangic), 0)}°'de durağan bırakılır (kontrolcü açık); {s(sens['O1-4+'].sure, 0)} s",
        "O1-4-": f"Gövde −{s(math.degrees(sa.toparlanma_acisi_baslangic), 0)}°'de durağan bırakılır; {s(sens['O1-4-'].sure, 0)} s",
        "O2": f"Eldivenden sırayla: ileri {s(sa.o2_mesafe, 1)} m ({s(sa.o2_sure, 0)} s), geri, sola {s(math.degrees(sa.o2_donus), 0)}° ({s(sa.donus_sure, 0)} s), sağa; her komuttan sonra yerleşme + 1 s dur",
    }
    olcut = {
        "O1-1": f"30 s düşmez (şartname); başlangıçtan uzaklaşma {s(sa.statik_kayma_siniri, 2)} m'yi aşarsa uyarı [öneri]",
        "O1-23": f"Her yönde {s(sa.o1_mesafe, 1)} m ± %{s(100 * sa.mesafe_toleransi, 0)} [öneri]; 3 s boyunca ortalama hız ≤ {s(sa.durma_hizi, 2)} m/s [öneri]",
        "O1-4+": f"10 s içinde eğim dik duruşun ±{s(math.degrees(sa.toparlanma_acisi), 0)}°'sine girer ve kalır [öneri]; iki yön birlikte geçmeli (şartname)",
        "O1-4-": "Aynı",
        "O2": f"Komuttan sonra {s(sa.komut_tepki_suresi, 0)} s içinde tepki (şartname; tepki = teker {s(100 * sa.tepki_esigi, 0)} cm ya da 2° hareket [öneri]); {s(sa.o2_mesafe, 1)} m ± %{s(100 * sa.mesafe_toleransi, 0)}, 90° ± {s(math.degrees(sa.aci_toleransi), 0)}° [öneri]; durur [öneri]",
    }
    D["tablo_ik_senaryo"] = tablo(["Senaryo", "Akış", "Geçme ölçütü (alt testin kendi koşulları)"],
                                  [[SENARYO_ADLARI[k], tanim[k], olcut[k]] for k in SENARYO_KODLARI], ["l", "l", "l"])

    # -- Ana matris ------------------------------------------------------------------------
    satirlar, gecen = [], {}
    for ktr in ("lqr", "pid"):
        for kst in ("kalman", "tamamlayici"):
            for kutulu in (True, False):
                for pil in ("dolu", "bos"):
                    r = toplu.alt_test_sonuclari(ana, kontrolcu=ktr, kestirici=kst, kutulu=kutulu, pil=pil)
                    gecen[(ktr, kst, kutulu, pil)] = r
                    satirlar.append([f"{KTR[ktr]} + {KST[kst]}", "takılı" if kutulu else "yok", PIL[pil]]
                                    + [ISARET[r[a]] for a in toplu.ALT_TEST_SIRASI] + [f"{sum(r.values())}/{len(r)}"])
    D["tablo_ik_matris"] = tablo(["Kontrolcü + kestirici", "Kutu", "Pil", *toplu.ALT_TEST_SIRASI, "Toplam"], satirlar,
                                 ["l", "l", "l"] + ["c"] * len(toplu.ALT_TEST_SIRASI) + ["r"])
    for ktr in ("lqr", "pid"):
        for kst in ("kalman", "tamamlayici"):
            g = [v for (a1, a2, _, _), r in gecen.items() if (a1, a2) == (ktr, kst) for v in r.values()]
            D[f"ik_gecen_{ktr}_{kst}"] = f"{sum(g)}/{len(g)}"
    tum = [v for r in gecen.values() for v in r.values()]
    D["ik_gecen_ana"] = f"{sum(tum)}/{len(tum)}"

    detay = []
    for kod in SENARYO_KODLARI:
        for kutulu in (True, False):
            for pil in ("dolu", "bos"):
                d = toplu.bul(ana, kod, kontrolcu="lqr", kestirici="kalman", kutulu=kutulu, pil=pil)
                o = d["olcutler"]
                detay.append([SENARYO_ADLARI[kod], "takılı" if kutulu else "yok", PIL[pil], s(o["en_buyuk_egim"], 1), s(o["yere_degme_payi"], 1),
                              s(o["doyum_suresi"], 2), s(o["tepe_akim"], 2), s(o["rms1_akim"], 2), s(o["kayma_suresi"], 2),
                              "-" if math.isnan(o["kutu_alfa"]) else s(o["kutu_alfa"], 1), s(o["kestirim_hatasi"], 2),
                              " / ".join(f"{x['ad']}: {v(x['deger'])}" for x in d["alt"]), "geçti" if d["gecti"] else "**kaldı**"])
    D["tablo_ik_detay"] = tablo(["Senaryo", "Kutu", "Pil", "En büyük eğim [°]", "Yere değme payı [°]", "Doyum süresi [s]", "Tepe akım [A]",
                                 "1 s etkin akım [A]", "Teker kayması [s]", "Kutu görünür eğimi [°]", "Kestirim hatası [°]", "Ölçülen", "Sonuç"],
                                detay, ["l", "l", "l"] + ["r"] * 8 + ["l", "l"])
    o_ana = [toplu.bul(ana, k, kontrolcu="lqr", kestirici="kalman", kutulu=ku, pil=pi)["olcutler"]
             for k in SENARYO_KODLARI for ku in (True, False) for pi in ("dolu", "bos")]
    o_hareket = [toplu.bul(ana, k, kontrolcu="lqr", kestirici="kalman", kutulu=ku, pil=pi)["olcutler"]
                 for k in ("O1-1", "O1-23", "O2") for ku in (True, False) for pi in ("dolu", "bos")]
    D |= {"ik_egim_max": s(max(o["en_buyuk_egim"] for o in o_hareket), 1),
          "ik_pay_min": s(min(o["yere_degme_payi"] for o in o_ana), 1), "ik_doyum_max": s(max(o["doyum_suresi"] for o in o_ana), 2),
          "ik_tepe_akim": s(max(o["tepe_akim"] for o in o_ana), 2), "ik_rms_max": s(max(o["rms1_akim"] for o in o_ana), 2),
          "ik_kayma_max": s(max(o["kayma_suresi"] for o in o_ana), 2),
          "ik_kutu_alfa": s(max(o["kutu_alfa"] for o in o_ana if not math.isnan(o["kutu_alfa"])), 1),
          "ik_kutu_surtunme": s(math.degrees(gv.kutu_surtunme_acisi), 1), "ik_kutu_devrilme": s(math.degrees(gv.kutu_devrilme_acisi), 0)}
    d_t = toplu.bul(ana, "O1-4+", kontrolcu="lqr", kestirici="kalman", kutulu=True, pil="bos")
    D["ik_t_topar"] = v(d_t["alt"][0]["deger"])
    d_t2 = toplu.bul(ana, "O1-4+", kontrolcu="pid", kestirici="kalman", kutulu=True, pil="bos")
    D["ik_t_topar_pid"] = v(d_t2["alt"][0]["deger"])
    d2 = toplu.bul(ana, "O2", kontrolcu="lqr", kestirici="kalman", kutulu=True, pil="bos")
    tepki = [k[2] for x in d2["alt"] for k in x["kosullar"] if k[0].startswith("Tepki")]
    D["ik_tepki"] = ", ".join(tepki).replace(".", ",").replace(" s,", ",")

    kalanlar = []
    for d in ana:
        for x in d["alt"]:
            if not x["gecti"]:
                k = d["kurulum"]
                kalanlar.append(f"- **{x['ad']}**, {KTR[k['kontrolcu']]} + {KST[k['kestirici']]}, kutu {'takılı' if k['kutulu'] else 'yok'}, "
                                f"{PIL[k['pil']]} pil: {x['neden']}")
    D["ik_kalanlar"] = "\n".join(kalanlar).replace(".", ",") if kalanlar else "- Satın alınan motorla ana matriste kalan alt test yok."
    D["ik_kalan_sayisi"] = str(len(kalanlar))
    gruplar: dict[str, list] = {}
    for d in ana:
        for x in d["alt"]:
            for n in x["notlar"]:
                tur = "kutu yuvada kayar" if n.startswith("kutu yuvada kayar") else n.split(":")[0].split(" (")[0]
                gruplar.setdefault(tur, []).append(f"{x['ad']}, {KTR[d['kurulum']['kontrolcu']]} + {KST[d['kurulum']['kestirici']]}")
    D["ik_notlar"] = "; ".join(f"{tur} ({len(set(yer))} alt testte, ör. {sorted(set(yer))[0]})" for tur, yer in gruplar.items()) if gruplar else "yok"

    # -- Kestirim karşılaştırması (ivme telafisi açık/kapalı) -----------------------------
    ay_telafisiz = ay.degistir(kestirim=replace(ay.kestirim, ivme_telafisi=False))
    kest_satir, kest_kay = [], {}
    for kod in ("O1-1", "O1-23", "O1-4+", "O2"):
        hucre = []
        for etiket, kst, ayk in (("Kalman", "kalman", ay), ("Tamamlayıcı", "tamamlayici", ay), ("Kalman, telafisiz", "kalman", ay_telafisiz),
                                 ("Tamamlayıcı, telafisiz", "tamamlayici", ay_telafisiz)):
            kay = calistir(t, kod, Kurulum(SATIN_ALINAN, True, "bos", "lqr", kst), ayk)
            d = degerlendir(kay, ayk)
            hucre.append(f"{s(d['olcutler']['kestirim_hatasi'], 2)}° ({'geçti' if d['gecti'] else '**kaldı**'})")
            if kod == "O1-23":
                kest_kay[etiket] = kay
        kest_satir.append([SENARYO_ADLARI[kod], *hucre])
    D["tablo_ik_kestirim"] = tablo(["Senaryo (LQI, kutulu, boş pil)", "Kalman", "Tamamlayıcı", "Kalman, ivme telafisiz", "Tamamlayıcı, ivme telafisiz"],
                                   kest_satir, ["l", "r", "r", "r", "r"])
    cizim.kestirim_grafigi(sekil_dizini / "sekil_18_ikiz_kestirim.png",
                           [(e, kest_kay[e]) for e in ("Kalman", "Tamamlayıcı", "Kalman, telafisiz")],
                           "Eğim kestirim hatası, Ö1-2/3 (LQI, kutulu, boş pil)")

    # -- Motor karşılaştırması --------------------------------------------------------------
    msatir = []
    for m in toplu.MOTORLAR:
        for pil in ("dolu", "bos"):
            hucre = [MOTOR_ADLARI[m] if pil == "dolu" else "", PIL[pil]]
            for ktr in ("lqr", "pid"):
                r = [v for ku in (True, False) for v in toplu.alt_test_sonuclari(sonuclar, motor=m, kontrolcu=ktr, kestirici="kalman", kutulu=ku, pil=pil).values()]
                hucre.append(f"{sum(r)}/{len(r)}")
            ds = [d for d in sonuclar if d["kurulum"]["motor"] == m and d["kurulum"]["pil"] == pil and d["kurulum"]["kestirici"] == "kalman"]
            hucre += [s(max(d["olcutler"]["doyum_suresi"] for d in ds), 2), s(max(d["olcutler"]["tepe_akim"] for d in ds), 2),
                      s(min(pay["aci"][(m, pil, 1)], pay["aci"][(m, pil, -1)]), 1)]
            if pil == "bos":
                hucre.append(" / ".join(s(min(pay_J[J]["aci"][(m, "bos", 1)], pay_J[J]["aci"][(m, "bos", -1)]), 1) for J in J_aralik))
            else:
                hucre.append("")
            msatir.append(hucre)
    D["tablo_ik_motorlar"] = tablo(
        ["Motor", "Pil", "LQR (motora göre) geçen", "PID (dosya) geçen", "En uzun doyum [s]", "Tepe akım [A]", "Toparlanabilen en büyük eğim [°]",
         f"Aynısı, J_rotor = {J_aralik[0]:.1e} / {J_aralik[1]:.1e} kg·m²".replace(".", ",")],
        msatir, ["l", "l", "r", "r", "r", "r", "r", "r"])
    for m in toplu.MOTORLAR:
        for pil in ("dolu", "bos"):
            D[f"ik_pay_{m}_{pil}"] = s(min(pay["aci"][(m, pil, 1)], pay["aci"][(m, pil, -1)]), 1)
        for J, ad in zip(J_aralik, ("alt", "ust")):
            D[f"ik_pay_{m}_{ad}"] = s(min(pay_J[J]["aci"][(m, "bos", 1)], pay_J[J]["aci"][(m, "bos", -1)]), 1)
        for ktr in ("lqr", "pid"):
            r = [v for pil in ("dolu", "bos") for ku in (True, False)
                 for v in toplu.alt_test_sonuclari(sonuclar, motor=m, kontrolcu=ktr, kestirici="kalman", kutulu=ku, pil=pil).values()]
            D[f"ik_gecen_{m}_{ktr}"] = f"{sum(r)}/{len(r)}"
        neden = pay["neden"][(m, "bos", 1)]
        D[f"ik_neden_{m}"] = ("devir sınırı" if "devir sınırı" in neden else "tork sınırı" if "tork sınırı" in neden
                              else "teker kayması" if "kayma" in neden else "kontrolcü/kestirim")
    def kategori(neden: str) -> str:
        if "yere değdi" in neden:
            return "düşme"
        return ", ".join(sorted({"durma" if "durur" in parca else "toparlanma süresi" if "toparlanır" in parca else
                                 "mesafe ya da açı" if "≈" in parca else "tepki süresi" if "Tepki" in parca else "diğer"
                                 for parca in neden.split(";")}))
    sayac: dict[str, int] = {}
    for d in sonuclar:
        if d["kurulum"]["motor"] != SATIN_ALINAN:
            for x in d["alt"]:
                if x["neden"]:
                    for kat in kategori(x["neden"]).split(", "):
                        sayac[kat] = sayac.get(kat, 0) + 1
    D["ik_aday_kalma"] = ", ".join(f"{k} ({n})" for k, n in sorted(sayac.items(), key=lambda a: -a[1])) if sayac else "yok"
    pb = {m: min(pay["aci"][(m, "bos", 1)], pay["aci"][(m, "bos", -1)]) for m in toplu.MOTORLAR}
    sira = sorted(toplu.MOTORLAR, key=lambda m: -pb[m])
    D["ik_pay_sirasi"] = " > ".join(f"{m}" for m in sira)
    D["ik_pay_cumle"] = (f"Boş pilde payı en yüksek olan {sira[0]} RPM, en düşük olan {sira[-1]} RPM'dir (1000 RPM {s(pb['1000'], 1)}°, "
                         f"530 RPM {s(pb['530'], 1)}°, 333 RPM {s(pb['333'], 1)}°).")
    duz = {J: {m: min(pay_J[J]["aci"][(m, "bos", 1)], pay_J[J]["aci"][(m, "bos", -1)]) for m in toplu.MOTORLAR} for J in J_aralik}
    hep_en_dusuk = [m for m in toplu.MOTORLAR if all(min(x, key=x.get) == m for x in (pb, *duz.values()))]
    hep_en_yuksek = [m for m in toplu.MOTORLAR if all(max(x, key=x.get) == m for x in (pb, *duz.values()))]
    D["ik_duyarlilik_cumle"] = (
        f"$J_\\text{{rotor}}$ aralığın alt ucuna (×{s(J_aralik[0] / ay.J_rotor, 2)}) inince paylar 1000 / 530 / 333 RPM için "
        + " / ".join(f"{s(duz[J_aralik[0]][m], 1)}°" for m in toplu.MOTORLAR) + f", üst ucuna (×{s(J_aralik[1] / ay.J_rotor, 1)}) çıkınca "
        + " / ".join(f"{s(duz[J_aralik[1]][m], 1)}°" for m in toplu.MOTORLAR) + " olur. "
        + (f"{hep_en_dusuk[0]} RPM üç durumda da en düşük paydadır" if hep_en_dusuk else "En düşük paylı motor ataletle değişir")
        + (f", {hep_en_yuksek[0]} RPM üçünde de en yüksek." if hep_en_yuksek else "; en yüksek paylı motor ise ataletle değişir.")).replace("\\\\", "\\")
    gecen_m = {m: {ktr: [vv for pil in ("dolu", "bos") for ku in (True, False)
                         for vv in toplu.alt_test_sonuclari(sonuclar, motor=m, kontrolcu=ktr, kestirici="kalman", kutulu=ku, pil=pil).values()]
                   for ktr in ("lqr", "pid")} for m in toplu.MOTORLAR}
    D["ik_durus_cumle"] = "; ".join(f"{m} RPM: LQI {sum(g['lqr'])}/{len(g['lqr'])}, PID {sum(g['pid'])}/{len(g['pid'])}" for m, g in gecen_m.items()) + "."
    en_iyi = lambda m: max(sum(gecen_m[m]["lqr"]), sum(gecen_m[m]["pid"]))
    destekler = pb["333"] > pb["1000"] and en_iyi("333") >= en_iyi("1000")
    D["ik_karar_cumle"] = (
        "Simülasyon 1000 RPM motoru 333 RPM ile değiştirmeyi destekliyor: 333 RPM hem daha fazla pay sağlıyor hem de testleri en az aynı ölçüde geçiyor."
        if destekler else
        f"Simülasyon 1000 RPM motoru 333 RPM ile değiştirmeyi desteklemiyor: 333 RPM bu modelde daha fazla pay sağlamıyor "
        f"(boş pilde {s(pb['333'], 1)}°, 1000 RPM'de {s(pb['1000'], 1)}°) ve testleri daha az geçiyor (en iyi kontrolcüyle 333 RPM {en_iyi('333')}/32, "
        f"1000 RPM {en_iyi('1000')}/32). "
        "Bu nedenle **değişim önerisini askıya alıyoruz**; satın alınan motorla devam edilip §11.5'teki ölçüm yapılmalı.")
    D["ik_karar_kisa"] = "değişimi destekliyor" if destekler else "değişim önerisi askıda"

    # -- Şekiller --------------------------------------------------------------------------
    def kos(kod, **kw):
        k = Kurulum(**{"motor": SATIN_ALINAN, "kutulu": True, "pil": "bos", "kontrolcu": "lqr", "kestirici": "kalman", **kw})
        return calistir(t, kod, k, ay)

    lp = lambda kod, **kw: [("LQI + Kalman", kos(kod, **kw)), ("PID + Kalman", kos(kod, kontrolcu="pid", **kw))]
    cizim.zaman_grafigi(sekil_dizini / "sekil_14_ikiz_denge.png",
                        [("Ö1-1: 30 s statik denge (boş pil, kutulu)", lp("O1-1"), {"oteleme": False}),
                         ("Ö1-4: +10°'den toparlanma", lp("O1-4+"), {"oteleme": False}),
                         ("Ö1-4: −10°'den toparlanma", lp("O1-4-"), {"oteleme": False})], genislik=3.9)
    cizim.zaman_grafigi(sekil_dizini / "sekil_15_ikiz_oteleme.png",
                        [("Ö1-2/3: 1 m ileri, 3 s dur, 1 m geri, 3 s dur (boş pil)", lp("O1-23"), {}),
                         ("Aynısı, dolu pil", lp("O1-23", pil="dolu"), {})], genislik=4.6)
    cizim.o2_grafigi(sekil_dizini / "sekil_16_ikiz_o2.png", lp("O2"))
    mk = [(MOTOR_ADLARI[m], kos("O1-4+", motor=m)) for m in toplu.MOTORLAR]
    cizim.motor_grafigi(sekil_dizini / "sekil_17_ikiz_motorlar.png", mk, pay["aci"],
                        {"bos": f"Boş pil, {s(ay.pil['bos'], 1)} V", "dolu": f"Dolu pil, {s(ay.pil['dolu'], 1)} V"})
    if gif:
        n = cizim.animasyon(sekil_dizini / "ikiz_o1_4.gif", kos("O1-4+"), t, fps=20, t_son=4.0,
                            baslik="Ö1-4: +10°'den toparlanma (LQI + Kalman, 1000 RPM, boş pil, kutulu)", hiz=0.5)
        D["ik_gif_kare"] = str(n)
    D["ik_yd_ileri"] = s(math.degrees(yere_degme_acilari(t)["ileri"]), 1)
    D["ik_yd_geri"] = s(math.degrees(yere_degme_acilari(t)["geri"]), 1)
    D["ik_sure_toplam"] = s(time.time() - t0, 0)
    return D
