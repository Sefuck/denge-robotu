"""Satın alınan motor (JGB37-520 12 V 1000 RPM): gereksinime karşı sınama, karar ve çözüm seçenekleri.

Veri sayfası değerleri [doğrulanamadı]; `motor_olcum` alanları doldurulunca ölçülen değerler kullanılır ve karar
yeniden üretilir. Bütün torklar teker milinde, motor başınadır. Komut satırı:
    python -m denge.motor --satin-alinan --yan-yana
"""

from __future__ import annotations

import math

import numpy as np

from . import model, motor
from .kutle_merkezi import yere_degme_acilari
from .motor import MotorAdayi

ONEK = "motor_satin_alinan"
KARARLAR = ("uygun", "sınırda", "uygun değil")


# ---------------------------------------------------------------------------
# Aday: veri sayfası, ölçüm varsa ölçüm
# ---------------------------------------------------------------------------
def olculen_alanlar(tasarim) -> list[str]:
    return [k for k in ("bosta_devir", "bosta_akim", "durma_torku", "durma_akimi", "cpr_teker")
            if not isinstance(tasarim.d(f"motor_olcum.{k}"), list)]


def aday(tasarim) -> MotorAdayi:
    """Satın alınan motor. Ölçülen alanlar olcum_plani.gerilim'de ölçülmüştür; ölçülmeyenler veri sayfasından o gerilime ölçeklenir."""
    vs = motor.aday_tasarimdan(tasarim, ONEK)
    olc = olculen_alanlar(tasarim)
    if not olc:
        return vs
    V = tasarim.d("olcum_plani.gerilim")
    oran = V / vs.gerilim
    m = lambda k, varsayilan: tasarim.d(f"motor_olcum.{k}") if k in olc else varsayilan
    N = m("cpr_teker", 4 * vs.ppr * vs.reduksiyon) / (4 * vs.ppr)
    return MotorAdayi(vs.ad + " (ölçüm)", V, m("bosta_devir", vs.bosta_devir * oran), m("durma_torku", vs.durma_torku * oran),
                      m("durma_akimi", vs.durma_akimi * oran), m("bosta_akim", vs.bosta_akim), N, vs.ppr)


def ek_reduksiyon(a: MotorAdayi, k: float, verim: float) -> MotorAdayi:
    """Motor ile teker arasına 1:k aktarma: tork × k·verim, devir / k, enkoder sayımı × k (enkoder motor milinde)."""
    if k == 1:
        return a
    return MotorAdayi(f"{a.ad} + 1:{k:g}", a.gerilim, a.bosta_devir / k, a.durma_torku * k * verim, a.durma_akimi, a.bosta_akim,
                      a.reduksiyon * k, a.ppr)


def cpr(a: MotorAdayi) -> float:
    return 4 * a.ppr * a.reduksiyon


# ---------------------------------------------------------------------------
# Sınama
# ---------------------------------------------------------------------------
def gereksinim_ozeti(tasarim) -> dict:
    """Sınamada kullanılan gereksinimler (§4): A, A₀, A', B, referans ve agresif manevra, seyir, enkoder hedefi."""
    g = motor.gereksinimleri_hesapla(tasarim)
    p = g["p"]
    seyir = g["hareketler"][0]
    return {"g": g, "p": p, "nA": g["nokta_A"][0], "tA": g["nokta_A"][1], "tA0": g["nokta_A0"][1], "cekis": g["cekis_toplam"] / 2,
            "nB": g["nokta_B"][0], "tB": g["nokta_B"][1], "ref": float(np.max(np.abs(g["ref"]["dogrusal_olmayan"]["u"]))) / 2,
            "agr": g["J_m_tablosu"][0]["tepe_agresif"] / 2, "n_seyir": seyir["rpm"], "cpr_min": g["enkoder"]["cpr_min"], "SF": g["SF"]}


def sina(a: MotorAdayi, G: dict, V: float) -> dict:
    """Aday verilen pil geriliminde: A devrindeki tork, sağlanan SF, çekiş, manevra payları, B, PWM kullanımı."""
    T = a.tork(G["nA"], V)
    n0, ts = a.egriler(V)
    return {"V": V, "n0": n0, "ts": ts, "T_A": T, "sf": T / G["tA0"], "A": T >= G["tA"], "A0": T >= G["tA0"], "cekis_orani": T / G["cekis"],
            "ref": T / G["ref"], "agr": T / G["agr"], "B": a.tork(G["nB"], V) >= G["tB"],
            "pwm_seyir": motor.pwm_orani(a, V, G["n_seyir"], 0.0), "pwm_B": motor.pwm_orani(a, V, G["nB"], G["tB"]),
            "pwm_olu": motor.pwm_orani(a, V, 0.0, 0.0), "i_tepe": 2 * a.akim(min(G["tA"], T))}


def karar(boş: dict, cpr_deger: float, cpr_min: float, SF: float) -> str:
    """uygun: boş pilde SF'li gereksinim + enkoder + seyir; sınırda: boş pilde katsayısız gereksinim ve seyir; değilse uygun değil."""
    if boş["sf"] >= SF and cpr_deger >= cpr_min and boş["B"]:
        return "uygun"
    if boş["sf"] >= 1.0 and boş["B"]:
        return "sınırda"
    return "uygun değil"


def gereken_akim_penceresi(r: float, dv: float, cpr_deger: float) -> float:
    """Bir sayımın hız karşılığı dv olsun diye gereken sayım penceresi [s]."""
    return 2 * math.pi * r / (dv * cpr_deger)


def sf_bire_inen_gerilim(a: MotorAdayi, G: dict) -> float:
    """Katsayısız el hesabının tam karşılandığı en düşük pil gerilimi [V] (tork ve boşta devir gerilimle orantılı)."""
    alt, ust = 1.0, 30.0
    for _ in range(60):
        orta = (alt + ust) / 2
        alt, ust = (alt, orta) if a.tork(G["nA"], orta) >= G["tA0"] else (orta, ust)
    return ust


# ---------------------------------------------------------------------------
# Çözümler
# ---------------------------------------------------------------------------
def teker_taramasi(tasarim, a: MotorAdayi, yaricaplar) -> list[dict]:
    """Teker yarıçapı değişince: devir, gereksinimler, sağlanan SF, çekiş, enkoder hedefi, yere değme ve yerden yükseklik."""
    V = tasarim.batarya_gerilimleri()["min"]
    en_alt = max(abs(tasarim.d("govde.braket_alt_kose")[1]), tasarim.d("govde.motor.boyut")[0] / 2)
    sonuc = []
    for r in yaricaplar:
        t = tasarim.degistir({"teker.yaricap": r})
        G = gereksinim_ozeti(t)
        s = sina(a, G, V)
        yd = yere_degme_acilari(t)
        sonuc.append({"r": r, "nA": G["nA"], "tA0": G["tA0"], "sf": s["sf"], "ref": s["ref"], "cekis": G["cekis"], "cekis_orani": s["cekis_orani"],
                      "cpr_min": G["cpr_min"], "nB": G["nB"], "B": s["B"], "ileri": yd["ileri"], "geri": yd["geri"], "yukseklik": r - en_alt,
                      "tutma": G["g"]["tutma_tam"] / 2})
    return sonuc


def reduksiyon_taramasi(tasarim, a: MotorAdayi, oranlar, verim: float) -> list[dict]:
    G = gereksinim_ozeti(tasarim)
    V = tasarim.batarya_gerilimleri()
    satirlar = []
    for k in oranlar:
        b = ek_reduksiyon(a, k, verim)
        s_min, s_max = sina(b, G, V["min"]), sina(b, G, V["max"])
        satirlar.append({"k": k, "aday": b, "min": s_min, "max": s_max, "cpr": cpr(b), "karar": karar(s_min, cpr(b), G["cpr_min"], G["SF"]),
                         "Jm_carpani": k**2})
    return satirlar


def kutle_senaryolari(tasarim) -> list[tuple[str, dict]]:
    """Kütle ve KM yüksekliğini azaltan [öneri] senaryoları (parametre değişiklikleri)."""
    zb = tasarim.d("govde.batarya.konum")
    ze = tasarim.d("govde.elektronik.konum")
    alt_kat = 0.025 + tasarim.d("govde.batarya.boyut")[2] / 2
    orta_kat = 0.105 + tasarim.d("govde.elektronik.boyut")[2] / 2
    takas = {"govde.batarya.konum": [zb[0], zb[1], alt_kat], "govde.elektronik.konum": [ze[0], ze[1], orta_kat]}
    hafif = {"govde.sasi.kutle": tasarim.kayit("govde.sasi.kutle")["aralik"][0]}
    return [("Şu anki tasarım", {}),
            ("Batarya alt kata (elektronik yerinde; yer varsa)", {"govde.batarya.konum": [zb[0], zb[1], alt_kat]}),
            ("Batarya ve elektronik yer değiştirir", takas),
            ("Kutu yuvası orta katta", {"yuk.yuva.onerilen": "orta"}),
            (f"Şasi {1000 * hafif['govde.sasi.kutle']:.0f} g (aralığın alt ucu)", hafif),
            ("Batarya alt kata + kutu orta kata + hafif şasi", {"govde.batarya.konum": [zb[0], zb[1], alt_kat], "yuk.yuva.onerilen": "orta", **hafif})]


def kutle_taramasi(tasarim, a: MotorAdayi) -> list[dict]:
    V = tasarim.batarya_gerilimleri()["min"]
    sonuc = []
    for ad, degisiklik in kutle_senaryolari(tasarim):
        t = tasarim.degistir(degisiklik) if degisiklik else tasarim
        G = gereksinim_ozeti(t)
        p = G["p"]
        s = sina(a, G, V)
        sonuc.append({"ad": ad, "m": t.toplam_kutle(), "l": p.l, "mbl": p.m_b * p.l, "el": 2 * G["tA0"], "sf": s["sf"], "kutup": model.kararsiz_kutup(p),
                      "cekis": G["cekis"]})
    return sonuc


def gereken_el(a: MotorAdayi, G: dict, V: float, SF: float) -> float:
    """SF'nin sağlanması için el hesabının (iki motor toplamı) inmesi gereken değer [N m]."""
    return 2 * a.tork(G["nA"], V) / SF


# ---------------------------------------------------------------------------
def yazdir(tasarim, satin_alinan: bool = True, yan_yana: bool = True):
    _s = motor._s
    V = tasarim.batarya_gerilimleri()
    G = gereksinim_ozeti(tasarim)
    a = aday(tasarim)
    olc = olculen_alanlar(tasarim)
    if satin_alinan:
        print(f"\nSatın alınan motor: {a.ad} ({'ölçülen: ' + ', '.join(olc) if olc else 'veri sayfası, [doğrulanamadı]'}); torklar teker milinde, motor başına\n")
        for k in ("min", "max"):
            print(f"Pil {_s(V[k], 1)} V:\n| Ölçüt | Gereksinim | Aday | Sonuç |\n|---|---|---|---|")
            for x in motor.degerlendir(a, G["g"], V, V[k]):
                sonuc = "-" if x["sonuc"] is None else ("GEÇTİ" if x["sonuc"] else "KALDI")
                print(f"| {x['olcut']} | {x['gerek']} | {x['aday']} | {sonuc} |")
            s = sina(a, G, V[k])
            print(f"Sağlanan emniyet katsayısı {_s(s['sf'], 2)} (hedef {_s(G['SF'], 1)}); tork / çekiş sınırı {_s(s['cekis_orani'], 2)}; "
                  f"PWM: seyirde %{100 * s['pwm_seyir']:.0f}, B'de %{100 * s['pwm_B']:.0f}, kalkış eşiği %{100 * s['pwm_olu']:.0f}\n")
        s = sina(a, G, V["min"])
        print(f"KARAR: {karar(s, cpr(a), G['cpr_min'], G['SF']).upper()} (enkoder {cpr(a):.0f} / hedef {G['cpr_min']:.0f} sayım)")
    if yan_yana:
        seri = {round(x.reduksiyon): x for x in motor.satici_serisi_adaylari(tasarim)}
        print(f"\nYan yana (satıcının veri sayfası, 12 V serisi):\n| Motor | Pil [V] | Tork @ A [N·m] | SF | A (SF) | A₀ | Tork/çekiş | B | Enkoder | PWM seyir |\n|---|---:|---:|---:|---|---|---:|---|---:|---:|")
        for N in (10, 19, 30):
            for k in ("min", "max"):
                s = sina(seri[N], G, V[k])
                e = lambda b: "GEÇTİ" if b else "KALDI"
                print(f"| {seri[N].ad} | {_s(V[k], 1)} | {_s(s['T_A'])} | {_s(s['sf'], 2)} | {e(s['A'])} | {e(s['A0'])} | {_s(s['cekis_orani'], 2)} | "
                      f"{e(s['B'])} | {cpr(seri[N]):.0f} | %{100 * s['pwm_seyir']:.0f} |")
    print("\nNot: değerler satıcı veri sayfasından [doğrulanamadı]; motor ölçülünce motor_olcum alanları doldurulur (belge §11.5).")
