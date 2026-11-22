"""Kontrolcüler (PID ve LQR, aynı arayüz), referans üreteci ve çıkış katı; LQR tasarım aracı.

ESP32'ye taşınabilir yazıldı: her sınıf bir C yapısına karşılık gelir (__slots__, sabit alanlar), adım
fonksiyonları sabit periyotla çağrılır, çalışma sırasında bellek ayrılmaz ve numpy kullanılmaz. Kazançlar
parametre dosyasından okunur (KontrolAyarlari). Yalnız `lqr_tasarla` çevrim dışı bir tasarım aracıdır
(numpy/scipy kullanır, firmware'e girmez).

Arayüz: hesapla(s, ref) → (τ_toplam, τ_fark)
    s   = [x, v, θ, θ̇, ψ, ψ̇]  (kestirim; θ gövdenin fiziksel eğimi)
    ref = [x_ref, ẋ_ref, ẍ_ref, ψ_ref, ψ̇_ref, ψ̈_ref]
İleri besleme (isteğe bağlı): sabit ivmede gövde θ_ff = (c1/mgl)·ẍ kadar eğilmeli ve τ_ff = M_x r ẍ gerekir;
dönüşte τ_fark,ff = (2r/d) J_ψ ψ̈. Katsayılar doğrusal modelden (parametre dosyası) gelir.
    τ_toplam = τ_R + τ_L (ileri + denge), τ_fark = τ_R − τ_L (dönüş) [N·m, teker milinde]
Çıkış katı torku motor modeliyle PWM'e çevirir; böylece aynı kazançlar her motorla kullanılabilir.
"""

from __future__ import annotations

import math

from .ayarlar import KontrolAyarlari


def _sinirla(x: float, alt: float, ust: float) -> float:
    return alt if x < alt else (ust if x > ust else x)


# ---------------------------------------------------------------------------
# Referans üreteci: trapez hız profili (doğrusal ve açısal eksen ayrı)
# ---------------------------------------------------------------------------
class Profil:
    __slots__ = ("t0", "T", "ta", "a", "v_tepe", "bas", "miktar")

    def __init__(self):
        self.t0, self.T, self.ta, self.a, self.v_tepe, self.bas, self.miktar = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0

    def baslat(self, t: float, bas: float, miktar: float, sure: float, ivme_orani: float) -> None:
        self.t0, self.T, self.bas, self.miktar = t, sure, bas, miktar
        self.ta = ivme_orani * sure
        self.v_tepe = miktar / (sure - self.ta)
        self.a = self.v_tepe / self.ta

    def deger(self, t: float) -> tuple[float, float]:
        tau = t - self.t0
        if self.T <= 0.0 or tau >= self.T:
            return self.bas + self.miktar, 0.0
        if tau <= 0.0:
            return self.bas, 0.0
        if tau < self.ta:
            return self.bas + 0.5 * self.a * tau * tau, self.a * tau
        if tau < self.T - self.ta:
            return self.bas + 0.5 * self.a * self.ta * self.ta + self.v_tepe * (tau - self.ta), self.v_tepe
        k = self.T - tau
        return self.bas + self.miktar - 0.5 * self.a * k * k, self.a * k

    def bitis(self) -> float:
        return self.t0 + self.T


class Suzgec2:
    """Kritik sönümlü ikinci dereceden durum değişkenli süzgeç: y'' = (u − y − 2τ y')/τ². Çıkış (y, y', y'')."""

    __slots__ = ("tau", "T", "y", "yd", "ydd")

    def __init__(self, tau: float, T: float):
        self.tau, self.T = tau, T
        self.y = self.yd = self.ydd = 0.0

    def adim(self, u: float) -> None:
        if self.tau <= 0.0:
            self.ydd, self.yd, self.y = 0.0, 0.0, u
            return
        self.ydd = (u - self.y - 2.0 * self.tau * self.yd) / (self.tau * self.tau)
        self.yd += self.T * self.ydd
        self.y += self.T * self.yd


class Referans:
    """Eldiven komutları → ref = [x, ẋ, ẍ, ψ, ψ̇, ψ̈]. Komutlar: 'ileri', 'geri' (m), 'sol', 'sag' (rad), 'dur'.

    Trapez profil (şartnamedeki mesafe, hedef süre) ikinci dereceden süzgeçten geçer: ivme sürekli olur ve
    kontrolcünün ileri beslemesine verilebilir.
    """

    __slots__ = ("dogrusal", "acisal", "ivme_orani", "sx", "spsi", "cikti")

    def __init__(self, ivme_orani: float, T: float = 0.005, tau: float = 0.1):
        self.dogrusal, self.acisal, self.ivme_orani = Profil(), Profil(), ivme_orani
        self.sx, self.spsi = Suzgec2(tau, T), Suzgec2(tau, T)
        self.cikti = [0.0] * 6

    def komut(self, t: float, tur: str, miktar: float = 0.0, sure: float = 0.0) -> None:
        x, _ = self.dogrusal.deger(t)
        psi, _ = self.acisal.deger(t)
        if tur in ("ileri", "geri"):
            self.dogrusal.baslat(t, x, miktar if tur == "ileri" else -miktar, sure, self.ivme_orani)
        elif tur in ("sol", "sag"):
            self.acisal.baslat(t, psi, miktar if tur == "sol" else -miktar, sure, self.ivme_orani)
        elif tur == "dur":
            self.dogrusal.baslat(t, x, 0.0, 0.0, self.ivme_orani)
            self.acisal.baslat(t, psi, 0.0, 0.0, self.ivme_orani)
        else:
            raise ValueError(tur)

    def hesapla(self, t: float) -> list:
        """Her kontrol periyodunda bir kez çağrılır (süzgeç adımı)."""
        self.sx.adim(self.dogrusal.deger(t)[0])
        self.spsi.adim(self.acisal.deger(t)[0])
        c = self.cikti
        c[0], c[1], c[2] = self.sx.y, self.sx.yd, self.sx.ydd
        c[3], c[4], c[5] = self.spsi.y, self.spsi.yd, self.spsi.ydd
        return c


# ---------------------------------------------------------------------------
# Kontrolcüler
# ---------------------------------------------------------------------------
class LQRKontrolcu:
    """Konum integralli LQR (LQI): u = −K [x − x_ref, ẋ − ẋ_ref, θ − θ_ref, θ̇, z], z = ∫(x − x_ref) dt; dönüş için 2 kazanç.

    İntegral, motor sürtünmesinin (K_t·I_0) yarattığı konum ölü bölgesini kapatır; doyumda dondurulur ve sınırlanır.
    """

    __slots__ = ("K1", "K2", "K3", "K4", "K5", "Kp1", "Kp2", "denge", "k_egim", "k_tork", "k_donus", "T", "z", "z_siniri", "doyumda",
                 "Kpi", "zp", "zp_siniri")

    def __init__(self, a: KontrolAyarlari, T: float):
        self.K1, self.K2, self.K3, self.K4, self.K5 = a.lqr_K
        self.Kp1, self.Kp2 = a.lqr_K_donus
        self.denge = a.denge_acisi
        self.k_egim, self.k_tork, self.k_donus = a.ileri_besleme if a.ileri_besleme_acik else (0.0, 0.0, 0.0)
        self.T, self.z = T, 0.0
        self.z_siniri = a.integral_siniri / abs(self.K5) if self.K5 != 0.0 else 0.0  # integral katkısı ≤ integral_siniri
        self.doyumda = False
        self.Kpi, self.zp = a.donus_integrali, 0.0  # dönüş integrali (0 = kapalı)
        self.zp_siniri = a.integral_siniri / self.Kpi if self.Kpi > 0.0 else 0.0

    def sifirla(self) -> None:
        self.z, self.zp, self.doyumda = 0.0, 0.0, False

    def doyum_bildir(self, doyumda: bool) -> None:
        self.doyumda = doyumda

    def hesapla(self, s, ref) -> tuple[float, float]:
        ex = s[0] - ref[0]
        if not self.doyumda:
            self.z = _sinirla(self.z + ex * self.T, -self.z_siniri, self.z_siniri)
        th_ref = self.denge + self.k_egim * ref[2]
        u = self.k_tork * ref[2] - (self.K1 * ex + self.K2 * (s[1] - ref[1]) + self.K3 * (s[2] - th_ref) + self.K4 * s[3]
                                    + self.K5 * self.z)
        u_psi = self.k_donus * ref[5] - (self.Kp1 * (s[4] - ref[3]) + self.Kp2 * (s[5] - ref[4]))
        if self.Kpi > 0.0:
            if not self.doyumda:
                self.zp = _sinirla(self.zp + (s[4] - ref[3]) * self.T, -self.zp_siniri, self.zp_siniri)
            u_psi -= self.Kpi * self.zp
        return u, u_psi


class PIDKontrolcu:
    """Kademeli PID: dış döngü PD (konum, hız) eğim komutu üretir; iç döngü PID eğimi bu komuta getirir; dönüş PD."""

    __slots__ = ("Kp", "Ki", "Kd", "Kpx", "Kdx", "Kpp", "Kdp", "komut_siniri", "integral_siniri", "denge", "T",
                 "integral", "doyumda", "aci_komutu", "k_egim", "k_tork", "k_donus", "Kpi", "zp", "zp_siniri")

    def __init__(self, a: KontrolAyarlari, T: float):
        self.Kp, self.Ki, self.Kd = a.pid_aci
        self.Kpx, self.Kdx = a.pid_konum
        self.Kpp, self.Kdp = a.pid_donus
        self.komut_siniri, self.integral_siniri = a.aci_komut_siniri, a.integral_siniri
        self.denge, self.T = a.denge_acisi, T
        self.integral = 0.0
        self.doyumda = False
        self.aci_komutu = a.denge_acisi
        self.k_egim, self.k_tork, self.k_donus = a.ileri_besleme if a.ileri_besleme_acik else (0.0, 0.0, 0.0)
        self.Kpi, self.zp = a.donus_integrali, 0.0
        self.zp_siniri = a.integral_siniri / self.Kpi if self.Kpi > 0.0 else 0.0

    def sifirla(self) -> None:
        self.integral, self.zp, self.doyumda = 0.0, 0.0, False

    def doyum_bildir(self, doyumda: bool) -> None:
        self.doyumda = doyumda

    def hesapla(self, s, ref) -> tuple[float, float]:
        egim = self.Kpx * (ref[0] - s[0]) + self.Kdx * (ref[1] - s[1]) + self.k_egim * ref[2]
        self.aci_komutu = self.denge + _sinirla(egim, -self.komut_siniri, self.komut_siniri)
        e = s[2] - self.aci_komutu
        if not self.doyumda:  # koşullu integral: doyumda birikme yok
            self.integral = _sinirla(self.integral + self.Ki * e * self.T, -self.integral_siniri, self.integral_siniri)
        u = self.k_tork * ref[2] + self.Kp * e + self.integral + self.Kd * s[3]
        u_psi = self.k_donus * ref[5] + self.Kpp * (ref[3] - s[4]) + self.Kdp * (ref[4] - s[5])
        if self.Kpi > 0.0:
            if not self.doyumda:
                self.zp = _sinirla(self.zp + (ref[3] - s[4]) * self.T, -self.zp_siniri, self.zp_siniri)
            u_psi += self.Kpi * self.zp
        return u, u_psi


def kontrolcu_olustur(a: KontrolAyarlari, T: float, yontem: str | None = None):
    yontem = yontem or a.yontem
    return {"lqr": LQRKontrolcu, "pid": PIDKontrolcu}[yontem](a, T)


# ---------------------------------------------------------------------------
# Çıkış katı: tork → PWM
# ---------------------------------------------------------------------------
class CikisKati:
    """İstenen torkları iki motorun PWM doluluk oranına çevirir.

    I* = τ/K_t (akım sınırıyla kırpılır), V* = R I* + K_e ω̂ (zıt EMK telafisi), d = V*/V̂_pil,
    ölü bölge telafisi: d += k · d_0 · sınırla(d/d_0, −1, 1), d_0 = I_0 R / V̂_pil (motoru döndürmeye başlatan PWM);
    sıfır civarında doğrusal geçiş, işaret değişiminde PWM sıçramasın diye. |d| ≤ 1. V̂_pil süzülmüş ölçümdür.
    """

    __slots__ = ("K_t", "K_e", "R", "I0", "I_max", "telafi", "zit_emk", "a_pil", "V_pil", "doyum_pwm", "doyum_akim", "d")

    def __init__(self, motor, a: KontrolAyarlari, T: float, pil_tau: float = 0.2):
        self.K_t, self.K_e, self.R, self.I0 = motor.K_t, motor.K_e, motor.R, motor.I0
        self.I_max, self.telafi, self.zit_emk = a.akim_siniri, a.olu_bolge_telafisi, a.zit_emk_telafisi
        self.a_pil = T / (pil_tau + T)
        self.V_pil = 0.0
        self.doyum_pwm = self.doyum_akim = False
        self.d = [0.0, 0.0]

    def pil_olcumu(self, V: float) -> None:
        self.V_pil = V if self.V_pil == 0.0 else self.V_pil + self.a_pil * (V - self.V_pil)

    def _motor(self, tau: float, w: float) -> float:
        I = tau / self.K_t
        if I > self.I_max or I < -self.I_max:
            I = _sinirla(I, -self.I_max, self.I_max)
            self.doyum_akim = True
        V = self.R * I + (self.K_e * w if self.zit_emk else 0.0)
        d = V / self.V_pil
        if not self.zit_emk:  # akım sınırını gerilim üzerinden uygula
            d_ust = (self.I_max * self.R + self.K_e * w) / self.V_pil
            d_alt = (-self.I_max * self.R + self.K_e * w) / self.V_pil
            d = _sinirla(d, d_alt, d_ust)
        d0 = self.I0 * self.R / self.V_pil
        if d0 > 0.0:
            d += self.telafi * d0 * _sinirla(d / d0, -1.0, 1.0)
        if d > 1.0 or d < -1.0:
            d = _sinirla(d, -1.0, 1.0)
            self.doyum_pwm = True
        return d

    def hesapla(self, tau_top: float, tau_fark: float, wR: float, wL: float) -> list:
        self.doyum_pwm = self.doyum_akim = False
        self.d[0] = self._motor(0.5 * (tau_top + tau_fark), wR)
        self.d[1] = self._motor(0.5 * (tau_top - tau_fark), wL)
        return self.d


# ---------------------------------------------------------------------------
# Çevrim dışı LQR tasarımı (firmware'e girmez)
# ---------------------------------------------------------------------------
def lqi_modeli(p, Ts: float):
    """Konum integraliyle artırılmış ayrık model: durum [x, ẋ, θ, θ̇, z], z_{k+1} = z_k + T x_k."""
    import numpy as np

    from .. import model

    Ad, Bd, _, _ = model.ayriklastir(*model.durum_uzay(p), Ts)
    A = np.zeros((5, 5))
    A[:4, :4] = Ad
    A[4, 0], A[4, 4] = Ts, 1.0
    B = np.zeros((5, 1))
    B[:4] = Bd
    return A, B


def lqr_tasarla(p, Q, R, Ts: float):
    """Ayrık LQR (Q 4 elemanlı) ya da LQI (Q 5 elemanlı, son eleman konum integrali): giriş τ_R + τ_L → K."""
    import numpy as np
    from scipy.linalg import solve_discrete_are

    from .. import model

    if len(Q) == 5:
        Ad, Bd = lqi_modeli(p, Ts)
    else:
        Ad, Bd, _, _ = model.ayriklastir(*model.durum_uzay(p), Ts)
    Qm, Rm = np.diag(Q), np.atleast_2d(R)
    P = solve_discrete_are(Ad, Bd, Qm, Rm)
    return np.linalg.solve(Rm + Bd.T @ P @ Bd, Bd.T @ P @ Ad).ravel()


def donus_lqr_tasarla(p, Q, R, Ts: float):
    """Dönüş alt sistemi (giriş τ_R − τ_L) için ayrık LQR → K_ψ (2,)."""
    import numpy as np
    from scipy.linalg import solve_discrete_are

    from .. import model

    Ad, Bd, _, _ = model.ayriklastir(*model.donus_durum_uzay(p), Ts)
    Qm, Rm = np.diag(Q), np.atleast_2d(R)
    P = solve_discrete_are(Ad, Bd, Qm, Rm)
    return np.linalg.solve(Rm + Bd.T @ P @ Bd, Bd.T @ P @ Ad).ravel()


def motora_gore_tasarla(a: KontrolAyarlari, p, Ts: float) -> KontrolAyarlari:
    """Aynı Q ve R ağırlıklarıyla, verilen modele (ör. başka bir motorun yansıyan rotor ataleti) göre LQR ve ileri besleme.

    Aday motorları adil karşılaştırmak için: her motor kendi modeline göre ayarlanmış kontrolcüyle sınanır.
    """
    from dataclasses import replace

    from .ayarlar import ileri_besleme_katsayilari

    K = tuple(float(k) for k in lqr_tasarla(p, a.lqr_Q, a.lqr_R, Ts))
    Kp = tuple(float(k) for k in donus_lqr_tasarla(p, a.lqr_Q_donus, a.lqr_R_donus, Ts))
    return replace(a, lqr_K=K, lqr_K_donus=Kp, ileri_besleme=ileri_besleme_katsayilari(p))


def kapali_cevrim_ozdegerleri(p, K, Ts: float, gecikme_adimi: int = 0):
    """u = −K x ile ayrık kapalı çevrimin özdeğerleri; gecikme_adimi kadar örnek gecikmeli giriş (artırılmış durum)."""
    import numpy as np

    from .. import model

    K = np.atleast_2d(K)
    if K.shape[1] == 5:
        Ad, Bd = lqi_modeli(p, Ts)
    else:
        Ad, Bd, _, _ = model.ayriklastir(*model.durum_uzay(p), Ts)
    if gecikme_adimi == 0:
        return np.linalg.eigvals(Ad - Bd @ K)
    n, m = Ad.shape[0], gecikme_adimi
    A = np.zeros((n + m, n + m))
    A[:n, :n] = Ad
    A[:n, n:n + 1] = Bd
    for i in range(m - 1):
        A[n + i, n + i + 1] = 1.0
    A[n + m - 1, :n] = -K
    return np.linalg.eigvals(A)
