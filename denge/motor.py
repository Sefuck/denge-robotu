"""Motor tork/devir ve enkoder gereksinimleri; motor adayı değerlendirme.

Tüm torklar TEKER MİLİNDE (redüktör çıkışında) verilir. "Toplam" iki motorun toplamı,
"motor başı" tek motor içindir. Komut satırı:
    python -m denge.motor --ad "Aday-1" --gerilim 12 --bosta-devir 300 \
        --durma-torku 8 --tork-birimi kgcm --durma-akimi 3 --bosta-akim 0.2 --reduksiyon 30 --ppr 11
"""

from __future__ import annotations

import argparse
import math
from dataclasses import dataclass

import numpy as np

from . import model, simulasyon
from .model import ModelParametreleri

KGFCM = 0.0980665  # 1 kgf·cm = 0.0980665 N·m


def _s(x: float, n: int = 3, bilimsel: bool = False) -> str:
    """Ondalık virgüllü sayı (Türkçe çıktı)."""
    return (f"{x:.{n}e}" if bilimsel else f"{x:.{n}f}").replace(".", ",")


def rpm(v: float, r: float) -> float:
    """Teker çevresel hızı v [m/s] → teker devri [dev/dk]."""
    return v / (2 * math.pi * r) * 60.0


def trapez_profil(mesafe: float, sure: float, ivme_orani: float = 0.25) -> tuple[float, float]:
    """Simetrik trapez hız profili: (tepe hız, ivme). Sürenin ivme_orani kadarı hızlanma."""
    t_a = ivme_orani * sure
    v_tepe = mesafe / (sure - t_a)
    return v_tepe, v_tepe / t_a


def hareket_tablosu(tasarim, p: ModelParametreleri) -> list[dict]:
    """Ö1/Ö2 hareketleri için tepe teker hızı, devir ve ivme torku."""
    oran = tasarim.d("hedef.profil_ivme_orani")
    k = model.dogrusal_katsayilar(p)
    satirlar = []
    for ad, mesafe, sure in (
        ("Ö1 ileri/geri", tasarim.d("sartname.o1_mesafe"), tasarim.d("hedef.o1_sure")),
        ("Ö2 ileri/geri", tasarim.d("sartname.o2_mesafe"), tasarim.d("hedef.o2_sure")),
    ):
        v, a = trapez_profil(mesafe, sure, oran)
        satirlar.append(
            {"hareket": ad, "miktar": f"{mesafe:g} m".replace(".", ","), "sure": sure, "v_teker": v, "ivme": a, "rpm": rpm(v, p.r),
             # sabit ivmede (θ̈ = 0): τ_R + τ_L = M_x r a (iki motor eşit paylaşır)
             "tork_motor_basi": k["M_x"] * p.r * a / 2}
        )
    aci = math.radians(tasarim.d("sartname.o2_donus"))
    sure = tasarim.d("hedef.donus_sure")
    psid, psidd = trapez_profil(aci, sure, oran)
    v = p.d / 2 * psid  # yerinde dönüşte teker çevresel hızı
    satirlar.append(
        {"hareket": "Ö2 yerinde 90° dönüş", "miktar": f"{tasarim.d('sartname.o2_donus'):g}°", "sure": sure,
         "v_teker": v, "ivme": p.d / 2 * psidd, "rpm": rpm(v, p.r),
         # τ_R − τ_L = (2r/d) J_ψ ψ̈ → motor başına (r/d) J_ψ ψ̈
         "tork_motor_basi": p.r / p.d * k["J_psi"] * psidd}
    )
    return satirlar


def toparlanma_torku_el(p: ModelParametreleri, theta0: float, t_r: float) -> dict:
    """İstenen el hesabı: τ = m_b g l sinθ0 (statik) + J_O θ̈_r (dinamik), iki motor toplamı.

    J_O = I_yy + m_b l² (aks etrafında), θ̈_r = 4θ0/t_r² (yarı sürede hızlan, yarı sürede yavaşla).
    Teker ivmesinin gövdeyi doğrultan etkisini yok saydığı için muhafazakârdır.
    """
    J_O = p.I_yy + p.m_b * p.l**2
    statik = p.m_b * p.g * p.l * math.sin(theta0)
    th_dd = 4 * theta0 / t_r**2
    dinamik = J_O * th_dd
    return {"J_O": J_O, "statik": statik, "theta_dd": th_dd, "dinamik": dinamik, "toplam": statik + dinamik}


def tutma_torku_tam(p: ModelParametreleri, theta: float) -> float:
    """Tam model: θ'da θ̈ = 0, θ̇ = 0 tutmak için gereken toplam tork.

    Tork tekeri ileri iterken teker ivmesi de gövdeyi doğrultur:
    τ = m_b g l sinθ / (1 + a12(θ)/(M_x r)).
    """
    k = model.dogrusal_katsayilar(p)
    a12 = p.m_b * p.l * math.cos(theta) - 2 * p.J_m / p.r
    return p.m_b * p.g * p.l * math.sin(theta) / (1 + a12 / (k["M_x"] * p.r))


def cekis_siniri(p: ModelParametreleri, mu: float, m_toplam: float) -> float:
    """Tekerler kaymadan zemine aktarılabilecek en büyük toplam tork ≈ μ m g r [N m]."""
    return mu * m_toplam * p.g * p.r


def min_durma_torku(n0, noktalar) -> np.ndarray:
    """Doğrusal tork-devir eğrisi τ(n) = τ_s (1 − n/n0) tüm (n_i, τ_i) noktalarının üstünde kalsın
    diye boşta devri n0 olan motorun sahip olması gereken en küçük durma torku."""
    n0 = np.atleast_1d(np.asarray(n0, float))
    sonuc = np.zeros_like(n0)
    for n_i, tau_i in noktalar:
        with np.errstate(divide="ignore"):
            gerek = np.where(n0 > n_i, tau_i / (1 - n_i / n0), np.inf)
        sonuc = np.maximum(sonuc, gerek)
    return sonuc


def enkoder_gereksinimi(r: float, d: float, dv_hedef: float, pencere: float, n_max: float) -> dict:
    """Hız kestirimi çözünürlüğü hedefinden teker başına gereken en az sayım (CPR, x4 kod çözme sonrası)."""
    ds_max = dv_hedef * pencere  # bir sayımın karşılığı en fazla bu kadar yol olmalı
    cpr_min = 2 * math.pi * r / ds_max
    return {"ds_max": ds_max, "cpr_min": cpr_min, "f_sayim_max": cpr_min * n_max / 60.0, "dpsi": ds_max / d}


def enkoder_tablosu(r: float, d: float, pencere: float, n_max: float, ppr_listesi, reduksiyonlar) -> list[dict]:
    satirlar = []
    for ppr in ppr_listesi:
        for N in reduksiyonlar:
            cpr = 4 * ppr * N  # motor milinde PPR, x4 kuadratür, redüktörle çarpılır
            ds = 2 * math.pi * r / cpr
            satirlar.append(
                {"ppr": ppr, "N": N, "cpr_teker": cpr, "ds": ds, "dv": ds / pencere, "dpsi": ds / d, "f_max": cpr * n_max / 60.0}
            )
    return satirlar


def tepe_tork(p: ModelParametreleri, theta0: float, T: float) -> float:
    """Referans toparlanma manevrasının doğrusal olmayan modeldeki tepe toplam torku [N m]."""
    return float(np.max(np.abs(simulasyon.referans_toparlanma(p, theta0, T, n=401)["dogrusal_olmayan"]["u"])))


def rotor_ataleti_esigi(p: ModelParametreleri, theta0: float, T: float, tork_siniri: float, J_ust: float = 0.01) -> float:
    """Referans manevranın tepe toplam torkunu `tork_siniri`na eşitleyen yansıyan rotor ataleti J_m."""
    alt, ust = 0.0, J_ust
    if tepe_tork(p.degistir(J_m=alt), theta0, T) >= tork_siniri:
        return 0.0
    if tepe_tork(p.degistir(J_m=ust), theta0, T) < tork_siniri:
        return math.inf
    for _ in range(40):
        orta = (alt + ust) / 2
        alt, ust = (orta, ust) if tepe_tork(p.degistir(J_m=orta), theta0, T) < tork_siniri else (alt, orta)
    return (alt + ust) / 2


def gereksinimleri_hesapla(tasarim, kutulu: bool = True) -> dict:
    """Motor seçimi için bütün gereksinimleri tek sözlükte toplar.

    A  (önerilen): istenen el hesabı × emniyet katsayısı, referans manevranın tepe devrinde.
    A' (asgari)  : zemine aktarılabilen en büyük tork (çekiş sınırı); yalnız yansıyan rotor
                   ataleti J_m eşiğin altındaysa referans manevrayı emniyet katsayısıyla karşılar.
    B  (seyir)   : seyir tepe hızı × hız payı devrinde, yavaşlama torku × emniyet katsayısı.
    """
    p = tasarim.model(kutulu=kutulu)
    th0 = math.radians(tasarim.d("sartname.toparlanma_acisi"))
    SF = tasarim.d("hedef.emniyet_katsayisi")
    el = toparlanma_torku_el(p, th0, tasarim.d("hedef.el_toparlanma_suresi"))
    T_ref = tasarim.d("hedef.referans_manevra_suresi")
    ref = simulasyon.referans_toparlanma(p, th0, T_ref)
    hareketler = hareket_tablosu(tasarim, p)
    m_top = tasarim.toplam_kutle(kutulu=kutulu)
    cekis = cekis_siniri(p, tasarim.d("zemin.surtunme"), m_top)

    v_ref = float(np.max(np.abs(ref["dogrusal_olmayan"]["xd"])))
    v_seyir = max(h["v_teker"] for h in hareketler)
    i_seyir = max(hareketler, key=lambda h: h["v_teker"])
    n_A = rpm(v_ref, p.r)
    n_B = rpm(tasarim.d("hedef.hiz_payi") * v_seyir, p.r)
    tau_A = SF * el["toplam"] / 2
    tau_B = SF * max(h["tork_motor_basi"] for h in hareketler)
    n_enk = max(n_A, n_B)
    J_aralik = tasarim.kayit("motor.rotor_ataleti_yansimis")["aralik"]
    return {
        "p": p,
        "el": el,
        "SF": SF,
        "tutma_tam": tutma_torku_tam(p, th0),
        "ref": ref,
        "T_ref": T_ref,
        "hareketler": hareketler,
        "v_ref": v_ref,
        "v_seyir": v_seyir,
        "seyir_hareketi": i_seyir["hareket"],
        "nokta_A": (n_A, tau_A),
        "nokta_A0": (n_A, el["toplam"] / 2),
        "nokta_A_asgari": (n_A, cekis / 2),
        "sigorta": tasarim.d("elektrik.sigorta") if "elektrik" in tasarim.veri else None,
        "nokta_B": (n_B, tau_B),
        "J_m_esik": rotor_ataleti_esigi(p, th0, T_ref, cekis / SF),
        "J_m_tablosu": [
            {"J_m": J, "tutma": tutma_torku_tam(p.degistir(J_m=J), th0), "tepe_ref": tepe_tork(p.degistir(J_m=J), th0, T_ref),
             "tepe_agresif": tepe_tork(p.degistir(J_m=J), th0, tasarim.d("hedef.el_toparlanma_suresi")),
             "kutup": model.kararsiz_kutup(p.degistir(J_m=J))}
            for J in sorted({0.0, 5e-4, 1e-3, J_aralik[1]})
        ],
        "cekis_toplam": cekis,
        "m_toplam": m_top,
        "enkoder": enkoder_gereksinimi(
            p.r, p.d, tasarim.d("hedef.hiz_cozunurlugu"), tasarim.d("hedef.hiz_kestirim_penceresi"), n_enk
        ),
        "n_max": n_enk,
    }


# ---------------------------------------------------------------------------
# Motor adayı
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MotorAdayi:
    """Veri sayfası değerleri (redüktör çıkışında, nominal gerilimde)."""

    ad: str
    gerilim: float  # nominal gerilim [V]
    bosta_devir: float  # boşta çıkış devri [dev/dk]
    durma_torku: float  # durma (stall) torku [N m]
    durma_akimi: float  # [A]
    bosta_akim: float = 0.0  # [A]
    reduksiyon: float = float("nan")
    ppr: float = float("nan")  # motor milinde enkoder darbe/devir (tek kanal)
    rotor_ataleti: float = float("nan")  # motor milinde rotor ataleti [kg m^2]

    @property
    def J_m(self) -> float:
        """Teker miline yansıyan rotor ataleti J_rotor·N² [kg m^2]."""
        return self.rotor_ataleti * self.reduksiyon**2

    def motor_modeli(self) -> model.MotorModeli:
        """Veri sayfasından teker milindeki K_t, K_e, R."""
        R = self.gerilim / self.durma_akimi
        K_t = self.durma_torku / (self.durma_akimi - self.bosta_akim)
        K_e = (self.gerilim - self.bosta_akim * R) / (self.bosta_devir * 2 * math.pi / 60)
        return model.MotorModeli(K_t=K_t, K_e=K_e, R=R)

    def egriler(self, gerilim: float) -> tuple[float, float]:
        """Verilen besleme geriliminde (boşta devir, durma torku): ikisi de gerilimle orantılı."""
        oran = gerilim / self.gerilim
        return self.bosta_devir * oran, self.durma_torku * oran

    def tork(self, n: float, gerilim: float) -> float:
        n0, ts = self.egriler(gerilim)
        return max(0.0, ts * (1 - n / n0))

    def akim(self, tau: float) -> float:
        return self.bosta_akim + tau / self.motor_modeli().K_t


def aday_tasarimdan(tasarim) -> MotorAdayi:
    """parametreler.toml'daki [motor_adayi] kaydı."""
    d = lambda k: tasarim.d(f"motor_adayi.{k}")
    return MotorAdayi(d("ad"), d("gerilim"), d("bosta_devir"), d("durma_torku"), d("durma_akimi"), d("bosta_akim"),
                      d("reduksiyon"), d("ppr"))


def seri_adaylari(tasarim) -> list[MotorAdayi]:
    """[motor_serisi] tablosundaki her oran için bir aday (aynı motor gövdesi, aynı gerilim ve PPR)."""
    d = lambda k: tasarim.d(f"motor_serisi.{k}")
    V, ppr = tasarim.d("motor_adayi.gerilim"), tasarim.d("motor_adayi.ppr")
    return [MotorAdayi(f"1:{N:g} ({n0:g} dev/dk)", V, n0, ts * KGFCM, d("durma_akimi"), d("bosta_akim"), N, ppr)
            for N, n0, ts in zip(d("reduksiyon"), d("bosta_devir"), d("durma_torku_kgfcm"))]


def oran_taramasi(adaylar: list[MotorAdayi], gereksinim: dict, gerilim: float) -> list[dict]:
    """Her oranın gereksinim noktalarını verilen besleme geriliminde karşılayıp karşılamadığı."""
    satirlar = []
    for a in adaylar:
        n0, ts = a.egriler(gerilim)
        sonuc = {"aday": a, "n0": n0, "ts": ts, "cpr": 4 * a.ppr * a.reduksiyon}
        for anahtar in ("nokta_A", "nokta_A0", "nokta_A_asgari", "nokta_B"):
            n, tau = gereksinim[anahtar]
            sonuc[anahtar] = (a.tork(n, gerilim), a.tork(n, gerilim) >= tau)
        sonuc["tum_SF"] = sonuc["nokta_A"][1] and sonuc["nokta_B"][1]
        sonuc["tum_SFsiz"] = sonuc["nokta_A0"][1] and sonuc["nokta_B"][1]
        satirlar.append(sonuc)
    return satirlar


def oran_araligi(adaylar: list[MotorAdayi], gereksinim: dict, gerilim: float, anahtar: str = "nokta_A") -> dict:
    """Seriye uydurulan sürekli modelle (τ_s ≈ c·N, n0 ≈ K/N, nominal gerilimde) `anahtar` ve B
    noktalarını birlikte karşılayan oran aralığı. Uygun oran yoksa None döner."""
    N = np.array([a.reduksiyon for a in adaylar])
    ts = np.array([a.durma_torku for a in adaylar])
    n0 = np.array([a.bosta_devir for a in adaylar])
    c = float(N @ ts / (N @ N))  # orijinden geçen en küçük kareler
    K = float(np.mean(n0 * N))
    oran = gerilim / adaylar[0].gerilim
    izgara = np.linspace(1.0, 150.0, 14901)
    uygun = np.ones_like(izgara, bool)
    for k in (anahtar, "nokta_B"):
        n, tau = gereksinim[k]
        n0_g = K / izgara * oran
        uygun &= (c * izgara * oran * np.clip(1 - n / n0_g, 0, None)) >= tau
    if not uygun.any():
        return {"c": c, "K": K, "aralik": None}
    secili = izgara[uygun]
    return {"c": c, "K": K, "aralik": (float(secili.min()), float(secili.max())),
            "devir_12V": (K / float(secili.max()), K / float(secili.min()))}


def gereken_sf(aday: MotorAdayi, gereksinim: dict, gerilim: float) -> float:
    """Adayın A noktasında sağladığı emniyet katsayısı (mevcut tork / katsayısız el hesabı)."""
    n, tau0 = gereksinim["nokta_A0"]
    return aday.tork(n, gerilim) / tau0


def degerlendir(aday: MotorAdayi, gereksinim: dict, gerilimler: dict) -> list[dict]:
    """Adayı gereksinim noktalarına göre batarya min. geriliminde sınar; geçti/kaldı satırları."""
    V = gerilimler["min"]
    n0, ts = aday.egriler(V)
    satirlar = []
    for etiket, (n, tau) in (("A: ±10° toparlanma, el hesabı × SF (önerilen)", gereksinim["nokta_A"]),
                             ("A₀: ±10° toparlanma, el hesabı, katsayısız", gereksinim["nokta_A0"]),
                             (f"A': çekiş sınırı (asgari; J_m ≤ {_s(gereksinim['J_m_esik'], 1, True)} kg·m² ise)", gereksinim["nokta_A_asgari"]),
                             ("B: seyir + hız payı", gereksinim["nokta_B"])):
        mevcut = aday.tork(n, V)
        satirlar.append({"olcut": etiket, "gerek": f"{_s(tau)} N·m @ {n:.0f} dev/dk",
                         "aday": f"{_s(mevcut)} N·m", "sonuc": mevcut >= tau})
    if not math.isnan(aday.ppr) and not math.isnan(aday.reduksiyon):
        cpr = 4 * aday.ppr * aday.reduksiyon
        satirlar.append({"olcut": "Enkoder çözünürlüğü (x4)", "gerek": f"≥ {gereksinim['enkoder']['cpr_min']:.0f} sayım/teker devri",
                         "aday": f"{cpr:.0f}", "sonuc": cpr >= gereksinim["enkoder"]["cpr_min"]})
    if not math.isnan(aday.J_m):
        satirlar.append({"olcut": "Yansıyan rotor ataleti J_rotor·N² (A' için)", "gerek": f"≤ {_s(gereksinim['J_m_esik'], 2, True)} kg·m²",
                         "aday": f"{_s(aday.J_m, 2, True)} kg·m²", "sonuc": aday.J_m <= gereksinim["J_m_esik"]})
    satirlar.append({"olcut": "Aşırı gerilim (batarya max / nominal)", "gerek": "≤ 1,2 [öneri]",
                     "aday": _s(gerilimler['max'] / aday.gerilim, 2), "sonuc": gerilimler["max"] / aday.gerilim <= 1.2})
    i_tepe = aday.akim(min(gereksinim["nokta_A"][1], aday.tork(gereksinim["nokta_A"][0], V)))
    sigorta = gereksinim.get("sigorta")
    satirlar.append({"olcut": "Tepe akım, A noktasında (2 motor toplamı)",
                     "gerek": f"≤ sigorta {_s(sigorta, 1)} A" if sigorta else "Mete: sürücü/sigorta boyutu",
                     "aday": f"{_s(2 * i_tepe, 2)} A (durma: {_s(2 * aday.durma_akimi, 1)} A)",
                     "sonuc": (2 * i_tepe <= sigorta) if sigorta else None})
    satirlar.append({"olcut": f"Batarya min. geriliminde ({_s(V, 1)} V) eğri", "gerek": "-",
                     "aday": f"n0 = {n0:.0f} dev/dk, τs = {_s(ts)} N·m", "sonuc": None})
    return satirlar


def _ana():
    from .parametreler import Tasarim

    ap = argparse.ArgumentParser(description="Motor adayını 3. hafta gereksinimlerine göre değerlendirir.")
    ap.add_argument("--ad", default="Aday")
    ap.add_argument("--dosyadaki-aday", action="store_true", help="parametreler.toml'daki [motor_adayi] kaydını kullan")
    ap.add_argument("--oran-taramasi", action="store_true", help="[motor_serisi] oranlarını da tara")
    ap.add_argument("--gerilim", type=float, help="nominal gerilim [V]")
    ap.add_argument("--bosta-devir", type=float, help="boşta çıkış devri [dev/dk]")
    ap.add_argument("--durma-torku", type=float)
    ap.add_argument("--tork-birimi", choices=["Nm", "kgcm"], default="kgcm")
    ap.add_argument("--durma-akimi", type=float, help="[A]")
    ap.add_argument("--bosta-akim", type=float, default=0.0, help="[A]")
    ap.add_argument("--reduksiyon", type=float, default=float("nan"))
    ap.add_argument("--ppr", type=float, default=float("nan"), help="motor milinde enkoder darbe/devir")
    ap.add_argument("--rotor-ataleti", type=float, default=float("nan"), help="motor milinde rotor ataleti [g·cm²]")
    ap.add_argument("--parametreler", default=None, help="parametre dosyası (varsayılan: parametreler.toml)")
    a = ap.parse_args()
    tasarim = Tasarim.yukle(a.parametreler)
    if a.dosyadaki_aday:
        aday = aday_tasarimdan(tasarim)
    else:
        if None in (a.gerilim, a.bosta_devir, a.durma_torku, a.durma_akimi):
            ap.error("--dosyadaki-aday yoksa --gerilim, --bosta-devir, --durma-torku ve --durma-akimi gerekli")
        tau = a.durma_torku * (KGFCM if a.tork_birimi == "kgcm" else 1.0)
        aday = MotorAdayi(a.ad, a.gerilim, a.bosta_devir, tau, a.durma_akimi, a.bosta_akim, a.reduksiyon, a.ppr, a.rotor_ataleti * 1e-7)
    gerek = gereksinimleri_hesapla(tasarim)
    gerilimler = tasarim.batarya_gerilimleri()
    print(f"\nMotor adayı: {aday.ad}  (batarya {_s(gerilimler['min'], 1)}–{_s(gerilimler['max'], 1)} V, tüm torklar teker milinde)\n")
    print("| Ölçüt | Gereksinim | Aday | Sonuç |\n|---|---|---|---|")
    for s in degerlendir(aday, gerek, gerilimler):
        sonuc = "-" if s["sonuc"] is None else ("GEÇTİ" if s["sonuc"] else "KALDI")
        print(f"| {s['olcut']} | {s['gerek']} | {s['aday']} | {sonuc} |")
    print(f"\nA noktasında sağlanan emniyet katsayısı: {_s(gereken_sf(aday, gerek, gerilimler['min']), 2)} "
          f"(hedef {_s(gerek['SF'], 1)})")
    if a.oran_taramasi:
        print(f"\nOran taraması (batarya min. gerilimi {_s(gerilimler['min'], 1)} V; tork teker milinde, motor başına):\n")
        print("| Oran | n0 [dev/dk] | τs [N·m] | τ @ A [N·m] | A (SF) | A₀ | B | Enkoder sayımı |\n|---|---:|---:|---:|---|---|---|---:|")
        for x in oran_taramasi(seri_adaylari(tasarim), gerek, gerilimler["min"]):
            e = lambda k: "GEÇTİ" if x[k][1] else "KALDI"
            print(f"| {x['aday'].ad} | {x['n0']:.0f} | {_s(x['ts'])} | {_s(x['nokta_A'][0])} | {e('nokta_A')} | {e('nokta_A0')} | {e('nokta_B')} | {x['cpr']:.0f} |")
    print("\nNot: gereksinimler tahmini/site/referans parametrelere dayanır (parametreler.toml).")


if __name__ == "__main__":
    _ana()
