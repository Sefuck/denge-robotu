"""Step motor seçeneği (17HS4401 + DRV8825): geçici pull-out eğrisi, adım kaçırma ve pratik hesaplar.

17HS4401'in kendi pull-out eğrisi bulunamadı. Geçici eğri, aynı sınıftan iki kardeş motorun 24 V eğrisinden
gerilim payı kuralıyla türetilir ve [doğrulanamadı] sayılır. Ölçüm gelince `step_egri.olcum` doldurulur; o
zaman ölçülen eğri kullanılır. Bütün torklar motor başına ve milde (redüktör yok, teker milde) verilir.
Komut satırı:  python -m denge.step
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from . import model, motor, simulasyon

KUTUP_CIFTI = 50  # 1,8° hibrit motor: 200 adım = 50 kutup çifti
MIKRO_ADIMLAR = (1, 2, 4, 8, 16, 32)


# ---------------------------------------------------------------------------
# Sargı ve gerilim payı
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Sargi:
    ad: str
    I_anma: float  # faz başına anma akımı, etkin [A]
    R: float  # [Ω]
    L: float  # [H]
    T_tutma: float  # iki faz anma akımındayken tutma torku [N m]
    T_detent: float = 0.0  # [N m]
    J_rotor: float = 0.0  # [kg m²]
    kutle: float = 0.0  # [kg]

    @property
    def K_t(self) -> float:
        """Faz başına tepe akım başına tork [N m/A]; tepe zıt EMK = K_t ω [V, rad/s]."""
        return self.T_tutma / (math.sqrt(2) * self.I_anma)


def sargi_tasarimdan(tasarim, ad: str) -> Sargi:
    d = lambda k: tasarim.d(f"step_sargi.{ad}.{k}")
    return Sargi(ad, d("faz_akimi"), d("faz_direnci"), d("enduktans"), d("tutma_torku"), d("detent_torku"), d("rotor_ataleti"), d("kutle"))


def gerilim_payi_devri(V: float, I_tepe: float, K_t: float, R: float, L: float, R_surucu: float = 0.0) -> float:
    """Sürücünün I_tepe sinüs akımını basmaya yettiği en yüksek devir [dev/dk].

    Gereken gerilim: (K_t ω + I(R + R_s))² + (p ω L I)² = V². Bu devrin üstünde akım, dolayısıyla tork düşer.
    """
    IR = I_tepe * (R + R_surucu)
    if V <= IR:
        return 0.0
    X = KUTUP_CIFTI * L * I_tepe
    a, b, c = K_t**2 + X**2, 2 * K_t * IR, IR**2 - V**2
    return (-b + math.sqrt(b**2 - 4 * a * c)) / (2 * a) * 60 / (2 * math.pi)


@dataclass(frozen=True)
class KardesEgri:
    """Kardeş motorun yayımlanmış eğrisi. Test akımı faz başına etkin kabul edilir (tepe = √2 × etkin)."""

    ad: str
    V: float
    I_etkin: float
    R: float
    L: float
    T_tutma: float
    devir: np.ndarray
    tork: np.ndarray

    @property
    def n_b(self) -> float:
        return gerilim_payi_devri(self.V, math.sqrt(2) * self.I_etkin, self.T_tutma / (math.sqrt(2) * self.I_etkin), self.R, self.L)

    @property
    def plato(self) -> float:
        return float(self.tork.max())

    @property
    def s(self) -> np.ndarray:
        """Gerilim payı devrine göre normal hız."""
        return self.devir / self.n_b

    @property
    def g(self) -> np.ndarray:
        """Eğrinin biçimi: tork / düşük hız torku."""
        return self.tork / self.plato

    @property
    def h(self) -> np.ndarray:
        """Tork / tutma torku: geçici eğrinin ölçeklendiği büyüklük."""
        return self.tork / self.T_tutma


def kardes_tasarimdan(tasarim, ad: str) -> KardesEgri:
    d = lambda k: tasarim.d(f"step_egri.{ad}.{k}")
    return KardesEgri(ad, d("gerilim"), d("akim"), d("faz_direnci"), d("enduktans"), d("tutma_torku"),
                      np.asarray(d("devir"), float), np.asarray(d("tork"), float))


class PullOut:
    """Motor başına pull-out torku [N m]; alt ve üst sınır. Ölçüm varsa ikisi de ölçüm eğrisidir.

    Geçici eğri: T(n; V, I) = K_t I h(n / n_b(V, I)). h(s), kardeş eğrinin torku / tutma torkudur; alt sınır iki
    kardeşin küçüğü, üst sınır büyüğüdür (en çok 1). İkisi de devirle azalır, yani gerilim artınca tork düşmez.
    """

    def __init__(self, tasarim):
        self.sargilar = [sargi_tasarimdan(tasarim, ad) for ad in ("robo90", "katalog")]
        self.kardesler = [kardes_tasarimdan(tasarim, ad) for ad in ("hs15_1504s", "hs15_1684s")]
        self.rezonans = tasarim.d("step_egri.rezonans_carpani")
        self.rds_alt, self.rds_ust = tasarim.kayit("surucu.drv8825.rds_toplam")["aralik"]
        d = lambda k: np.asarray(tasarim.d(f"step_egri.olcum.{k}"), float)
        self.olcum = (d("devir"), d("tork_9v9"), d("tork_12v")) if len(tasarim.d("step_egri.olcum.devir")) else None
        self.V_olcum = (9.9, 12.0)
        s_izgara = np.unique(np.concatenate([k.s for k in self.kardesler]))
        yigin = np.array([np.interp(s_izgara, k.s, k.h, left=k.h[0], right=np.nan) for k in self.kardesler])
        self._s = s_izgara
        self._h_alt = np.minimum.accumulate(np.nanmin(yigin, axis=0))
        self._h_ust = np.minimum(1.0, np.maximum.accumulate(np.nanmax(yigin, axis=0)[::-1])[::-1])

    def h_alt(self, s) -> np.ndarray:
        return np.interp(s, self._s, self._h_alt, right=0.0)  # kardeş verisinin ötesi bilinmiyor: tork sıfır sayılır

    def h_ust(self, s) -> np.ndarray:
        return np.interp(s, self._s, self._h_ust, right=0.0)

    def _olculen(self, n, V) -> np.ndarray:
        devir, t9, t12 = self.olcum
        w = np.clip((V - self.V_olcum[0]) / (self.V_olcum[1] - self.V_olcum[0]), 0.0, 1.0)
        return (1 - w) * np.interp(n, devir, t9, right=0.0) + w * np.interp(n, devir, t12, right=0.0)

    def alt(self, n, V: float, I: float) -> np.ndarray:
        """Kötü durum: iki sargının ve iki kardeş eğrinin en kötüsü."""
        n = np.atleast_1d(np.asarray(n, float))
        if self.olcum is not None:
            return self._olculen(n, V)
        return np.min([s.K_t * I * self.h_alt(n / gerilim_payi_devri(V, I, s.K_t, s.R, s.L, self.rds_ust)) for s in self.sargilar], axis=0)

    def ust(self, n, V: float, I: float) -> np.ndarray:
        """İyi durum: iki sargının ve iki kardeş eğrinin en iyisi."""
        n = np.atleast_1d(np.asarray(n, float))
        if self.olcum is not None:
            return self._olculen(n, V)
        return np.max([s.K_t * I * self.h_ust(n / gerilim_payi_devri(V, I, s.K_t, s.R, s.L, self.rds_alt)) for s in self.sargilar], axis=0)

    def capraz_hata(self) -> float:
        """Kural sınaması: 1504S'in eğri biçimi 1684S'inkinden öngörülür; ortak aralıktaki en büyük bağıl hata."""
        a, b = self.kardesler
        ongoru = np.interp(a.s, b.s, b.g)
        return float(np.max(np.abs(ongoru - a.g) / a.g))


def devir_siniri(egri: PullOut, tau: float, V: float, I: float) -> float:
    """Alt eğrinin tork gereksinimini karşıladığı en yüksek devir [dev/dk]."""
    n = np.linspace(0.0, 1500.0, 3001)
    uygun = egri.alt(n, V, I) >= tau
    return float(n[uygun].max()) if uygun.any() else 0.0


# ---------------------------------------------------------------------------
# Manevralar ve adım kaçırma
# ---------------------------------------------------------------------------
def manevralar(tasarim_step) -> list[dict]:
    """Toparlanma ve Ö1/Ö2 manevralarında motordan istenen (devir, tork) yörüngeleri, motor başına."""
    p = tasarim_step.model(kutulu=True)
    th0 = math.radians(tasarim_step.d("sartname.toparlanma_acisi"))
    T_ref, T_agr = tasarim_step.d("hedef.referans_manevra_suresi"), tasarim_step.d("hedef.el_toparlanma_suresi")
    D1, T1 = tasarim_step.d("sartname.o1_mesafe"), tasarim_step.d("hedef.o1_sure")
    D2, T2 = tasarim_step.d("sartname.o2_mesafe"), tasarim_step.d("hedef.o2_sure")
    v = lambda x: f"{x:g}".replace(".", ",")
    tanim = [
        (f"±10° toparlanma, T = {v(T_ref)} s", simulasyon.referans_toparlanma(p, th0, T_ref)),
        (f"±10° toparlanma, T = {v(T_agr)} s (agresif)", simulasyon.referans_toparlanma(p, th0, T_agr)),
        (f"Ö1: {v(D1)} m / {v(T1)} s", simulasyon.referans_oteleme(p, D1, T1)),
        (f"Ö2: {v(D2)} m / {v(T2)} s", simulasyon.referans_oteleme(p, D2, T2)),
    ]
    sonuc = []
    for ad, y in tanim:
        st = simulasyon.ivme_girisli_yorunge(p, y)
        sonuc.append({"ad": ad, "n": np.abs(st["w_b"]) * 60 / (2 * math.pi), "tau": np.abs(st["u"]) / 2, "yorunge": st})
    h = motor.hareket_tablosu(tasarim_step, p)[2]
    sonuc.append({"ad": f"Ö2: 90° / {tasarim_step.d('hedef.donus_sure'):g} s yerinde dönüş",
                  "n": np.array([h["rpm"]]), "tau": np.array([h["tork_motor_basi"]]), "yorunge": None})
    return sonuc


def pay(egri: PullOut, man: dict, V: float, I: float) -> dict:
    """Yörünge boyunca pull-out torku / istenen tork oranının en küçüğü (alt, üst, alt + rezonans)."""
    tau = np.maximum(man["tau"], 1e-9)
    alt = egri.alt(man["n"], V, I) / tau
    ust = egri.ust(man["n"], V, I) / tau
    return {"alt": float(alt.min()), "ust": float(ust.min()), "rezonans": float((egri.rezonans * alt).min())}


def ivme_siniri(p, tau_motor: float, mu: float) -> float:
    """Motor başına tork sınırının izin verdiği teker ivmesi [m/s²], çekiş sınırıyla birlikte."""
    M_x = model.dogrusal_katsayilar(p)["M_x"]
    return min(2 * tau_motor / (p.r * M_x), mu * p.g)


def burulma_modu(p, tau_tepe: float) -> dict:
    """Milin manyetik yayı (k = 50 T_tepe) üstündeki yük ataleti: rijit konum kaynağı varsayımının sınırı."""
    k = KUTUP_CIFTI * tau_tepe
    J = model.dogrusal_katsayilar(p)["M_x"] * p.r**2 / 2
    return {"k": k, "J_yuk": J, "f": math.sqrt(k / J) / (2 * math.pi)}


def yuk_gecikmesi(tau: float, tau_tepe: float) -> float:
    """Tork altında rotorun komuttan geri kalma açısı [rad]."""
    return math.asin(min(1.0, tau / tau_tepe)) / KUTUP_CIFTI


# ---------------------------------------------------------------------------
# Adım frekansı, çözünürlük
# ---------------------------------------------------------------------------
def adim_frekansi(n: float, mikro: int, adim: int = 200) -> float:
    """n [dev/dk] için STEP frekansı [Hz]."""
    return n / 60 * adim * mikro


def mikro_adim_tablosu(r: float, pencere: float, n_listesi: tuple[float, float], f_kontrol: float, adim: int = 200) -> list[dict]:
    satirlar = []
    for mikro in MIKRO_ADIMLAR:
        cpr = adim * mikro
        ds = 2 * math.pi * r / cpr
        satirlar.append({"mikro": mikro, "cpr": cpr, "ds": ds, "dv": ds / pencere, "f1": adim_frekansi(n_listesi[0], mikro, adim),
                         "f2": adim_frekansi(n_listesi[1], mikro, adim), "adim_cevrim": adim_frekansi(n_listesi[0], mikro, adim) / f_kontrol})
    return satirlar


# ---------------------------------------------------------------------------
# Güç, ısınma, pil süresi
# ---------------------------------------------------------------------------
def step_guc(s: Sargi, I: float, V: float, R_ds: float, P_lojik: float, tau: float = 0.0, n: float = 0.0) -> dict:
    """I: faz başına tepe akım. İki fazın toplam bakır kaybı I²R'dir (cos² + sin² = 1); akım motor dururken de akar."""
    P_bakir = I**2 * s.R
    P_surucu = I**2 * R_ds
    P_mek = tau * n * 2 * math.pi / 60
    P_top = 2 * (P_bakir + P_surucu + P_mek) + P_lojik
    return {"P_bakir": P_bakir, "P_surucu": P_surucu, "P_mek": P_mek, "P_top": P_top, "I_bat": P_top / V}


def pil_suresi(kapasite_Ah: float, V_nom: float, P_top: float) -> float:
    """Saat; pilin nominal enerjisine göre, kesim ve yaşlanma payı yok."""
    return kapasite_Ah * V_nom / P_top


def motor_isinmasi(s: Sargi, I: float, sinir: float) -> float:
    """Sıcaklık artışı [°C], kaba: katalog sınırı (iki faz anma akımında) × kayıp oranı."""
    return sinir * I**2 / (2 * s.I_anma**2)


def surucu_isinmasi(P_surucu: float, r_theta: float) -> float:
    return P_surucu * r_theta


# ---------------------------------------------------------------------------
def _ana():
    from .parametreler import Tasarim

    t = Tasarim.yukle()
    st = t.tahrik_tasarimi("step")
    egri = PullOut(t)
    V = t.batarya_gerilimleri()
    I = t.d("step_hedef.akim_limiti")
    g = motor.gereksinimleri_hesapla(st)
    durum = "ölçülmüş" if egri.olcum is not None else "geçici, kardeş motorlardan türetildi [doğrulanamadı]"
    print(f"\n{t.d('step_adayi.ad')}: akım limiti {I} A, eğri {durum}. Torklar motor başına, N·cm.\n")
    print("| Nokta / manevra | Devir | Tork | Pay 12 V (alt–üst) | Pay 9,9 V (alt–üst) | Pay 9,9 V alt + rezonans |\n|---|---:|---:|---:|---:|---:|")
    satirlar = [{"ad": ad, "n": np.array([g[k][0]]), "tau": np.array([g[k][1]])}
                for ad, k in (("A: toparlanma × SF", "nokta_A"), ("A₀: toparlanma", "nokta_A0"), ("A': çekiş sınırı", "nokta_A_asgari"), ("B: seyir", "nokta_B"))]
    for m in satirlar + manevralar(st):
        a, b = pay(egri, m, 12.0, I), pay(egri, m, V["min"], I)
        print(f"| {m['ad']} | {m['n'].max():.0f} | {100 * m['tau'].max():.1f} | {a['alt']:.2f}–{a['ust']:.2f} | {b['alt']:.2f}–{b['ust']:.2f} | {b['rezonans']:.2f} |")
    print("\nNot: eğri bu motorun ölçülmüş eğrisi değildir; 12 V ve 9,9 V ölçümü gereklidir (belge §10.10).")


if __name__ == "__main__":
    _ana()
