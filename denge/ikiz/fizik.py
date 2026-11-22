"""Dijital ikizin fizik çekirdeği: doğrusal olmayan hareket denklemleri, teker kayması, redüktör boşluğu, motor ve pil.

Serbest hızlar ν = (v, ψ̇, θ̇, ω_R, ω_L, ω_mR, ω_mL):
    v, ψ̇, θ̇  : aks orta noktasının ileri hızı, sapma hızı, gövde eğim hızı (model.py ile aynı tanımlar)
    ω_R, ω_L : tekerlerin mutlak açısal hızı (kayma olabildiği için v'den bağımsız)
    ω_m      : rotorun teker miline yansıtılmış mutlak açısal hızı; rotorun gövdeye göre hızı ω_m − θ̇
Yanal kaymama kısıtı korunur. Kinetik ve potansiyel enerji model.turet() ile aynıdır; tek fark, kaymadan
yuvarlanma ve dişli kısıtlarının kalıcı değil, "etkin olabilen" kısıtlar olmasıdır:

    teker–zemin  : s = v ± (d/2)ψ̇ − r ω = 0 (tutunma) ya da |F| = μ N (kayma, Coulomb)
    rotor sürtünmesi: ω_m − θ̇ = 0 (motor dönmüyor) ya da |τ_f| = K_t I_0 (boşta akım = Coulomb sürtünmesi)
    dişli boşluğu: δ = φ_m − φ ∈ [−β, +β]; uçta temas (tek yönlü), arada boşluk

Hepsi teker ve dişlinin üçü birden etkinken denklemler model.dinamik ile aynıdır (testte doğrulanır).
Zaman adımlama hız düzeyinde, yarı örtük Euler'dir: her adımda etkin kısıtlarla KKT sistemi çözülür,
sürtünme konisi ve tek yönlü temas koşulları sağlanana kadar etkin küme güncellenir (çarpmalar plastiktir).

Motor: PWM doluluk oranı d → uç gerilimi d·V_bara → akım I = (d·V_bara − K_e ω_rel)/R (endüktans ihmal,
L/R ≪ 1 ms) → tork K_t I. Pil: V_bara = V_açık − R_iç · (Σ d·I + I_lojik).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..model import ModelParametreleri

# Kısıt sıraları: 0/1 teker (sağ/sol), 2/3 rotor sürtünmesi, 4/5 dişli
TEKER, ROTOR, DISLI = (0, 1), (2, 3), (4, 5)


@dataclass(frozen=True)
class Motor:
    """Redüktörlü DC motor, teker milinde eşdeğer sabitler."""

    ad: str
    K_t: float  # tork sabiti [N m/A]
    K_e: float  # zıt EMK sabiti [V s/rad]
    R: float  # sargı direnci [Ω]
    I0: float  # boşta akım [A]; K_t·I0 Coulomb sürtünmesi sayılır
    J_m: float  # yansıyan rotor ataleti J_rotor·N² [kg m²]
    N: float  # redüksiyon oranı
    ppr: float  # motor milinde enkoder darbe/devir

    @property
    def cpr(self) -> float:
        """Teker turu başına sayım (x4 kod çözme)."""
        return 4 * self.ppr * self.N

    @property
    def tau_f(self) -> float:
        return self.K_t * self.I0

    def kararli_devir(self, V: float) -> float:
        """Boşta kararlı devir [rad/s] (teker havada)."""
        return max(0.0, (V - self.I0 * self.R) / self.K_e)


def motor_adaydan(aday, J_rotor: float, ad: str | None = None) -> Motor:
    """motor.MotorAdayi (veri sayfası) → Motor. J_rotor motor milindeki rotor ataletidir [kg m²]."""
    mm = aday.motor_modeli()
    return Motor(ad or aday.ad, mm.K_t, mm.K_e, mm.R, aday.bosta_akim, J_rotor * aday.reduksiyon**2, aday.reduksiyon, aday.ppr)


@dataclass(frozen=True)
class FizikAyarlari:
    mu: float  # teker–zemin sürtünme katsayısı
    bosluk: float  # redüktör boşluğu, teker milinde toplam (2β) [rad]
    R_ic: float  # pil + kablo + BMS iç direnci [Ω]
    I_lojik: float  # lojik devre akımı [A]
    surucu_olu_bolge: float  # bu doluluk oranının altındaki darbeleri sürücü iletmez
    pwm_adimi: float  # PWM doluluk oranı çözünürlüğü (1/(2^bit − 1))
    dt: float  # fizik adımı [s]


def surucu_cikisi(a: FizikAyarlari, d: float) -> float:
    """Sürücü: PWM çözünürlüğü, ölü bölge, ±1 sınırı."""
    d = max(-1.0, min(1.0, d))
    d = round(d / a.pwm_adimi) * a.pwm_adimi
    return 0.0 if abs(d) < a.surucu_olu_bolge else d


def motor_elektrigi(m: Motor, a: FizikAyarlari, dR: float, dL: float, wR: float, wL: float, V_acik: float) -> tuple[float, float, float]:
    """Sürücü çıkışındaki doluluk oranları ve rotorların gövdeye göre hızları → (bara gerilimi, I_R, I_L).

    V_bara = V_açık − R_iç (Σ d_i (d_i V − K_e ω_i)/R + I_lojik) kapalı biçimde çözülür; I = (d V − K_e ω)/R.
    """
    V = (V_acik - a.R_ic * a.I_lojik + a.R_ic * m.K_e * (dR * wR + dL * wL) / m.R) / (1 + a.R_ic * (dR * dR + dL * dL) / m.R)
    return V, (dR * V - m.K_e * wR) / m.R, (dL * V - m.K_e * wL) / m.R


class Robot:
    """İki tekerlekli robotun fiziksel durumu ve bir fizik adımı (dt)."""

    def __init__(self, p: ModelParametreleri, motor: Motor, ayar: FizikAyarlari, theta0: float = 0.0, theta_trim: float = 0.0):
        if motor.J_m <= 0 and ayar.bosluk > 0:
            raise ValueError("Redüktör boşluğu için rotor ataleti J_m > 0 olmalı")
        self.p, self.motor, self.ayar, self.dt = p, motor, ayar, ayar.dt
        self.theta_trim = theta_trim  # gövdenin fiziksel eğimi = θ + theta_trim (θ: KM doğrultusunun eğimi)
        self.beta = ayar.bosluk / 2
        self.q = [0.0, 0.0, theta0, 0.0, 0.0, 0.0, 0.0]  # x, ψ, θ, φ_R, φ_L, φ_mR, φ_mL
        self.nu = [0.0] * 7
        self.X = self.Y = 0.0
        # Etkin kısıtlar. Başta tekerler tutunur, rotorlar durur; boşluk varsa dişli ortada (temassız).
        self.etkin = [True, True, motor.tau_f > 0, motor.tau_f > 0, self.beta == 0, self.beta == 0]
        self.yon = [0.0] * 6  # kayma yönü (sürtünme) ya da temas yönü (dişli, ±1)
        r, d = p.r, p.d
        self.G = np.array([
            [1.0, d / 2, 0.0, -r, 0.0, 0.0, 0.0],
            [1.0, -d / 2, 0.0, 0.0, -r, 0.0, 0.0],
            [0.0, 0.0, -1.0, 0.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, -1.0, 0.0, 0.0, 0.0, 1.0],
            [0.0, 0.0, 0.0, -1.0, 0.0, 1.0, 0.0],
            [0.0, 0.0, 0.0, 0.0, -1.0, 0.0, 1.0],
        ])
        self.M = np.zeros((7, 7))
        self.thdd = self.vd = 0.0
        self.akim = (0.0, 0.0)
        self.tork = (0.0, 0.0)
        self.V_bara = 0.0
        self.F = (0.0, 0.0)  # teker–zemin sürtünme kuvvetleri [N]
        self.N = (0.0, 0.0)  # normal kuvvetler [N]
        self.dongu_asimi = 0  # etkin küme yakınsamadığı adım sayısı (tanılama)

    # -- türetilmiş büyüklükler --------------------------------------------------
    @property
    def theta(self) -> float:
        return self.q[2]

    @property
    def theta_govde(self) -> float:
        """Gövdenin fiziksel eğimi [rad] (IMU'nun gördüğü, yere değme açısının ölçüldüğü açı)."""
        return self.q[2] + self.theta_trim

    def bagil_aci(self, i: int) -> float:
        """Rotorun gövdeye göre açısı, teker milinde [rad]: enkoder bunu sayar (dişli boşluğu dahil)."""
        return self.q[5 + i] - self.q[2]

    def bosluk_konumu(self, i: int) -> float:
        return self.q[5 + i] - self.q[3 + i]

    def kayiyor(self, i: int) -> bool:
        return not self.etkin[TEKER[i]]

    def disli_temasta(self, i: int) -> bool:
        return self.etkin[DISLI[i]]

    # -- elektrik ------------------------------------------------------------------
    def elektrik(self, dR: float, dL: float, V_acik: float) -> tuple[float, float]:
        """PWM doluluk oranları → bara gerilimi, motor akımları ve motor torkları (teker milinde)."""
        m = self.motor
        thd = self.nu[2]
        V, IR, IL = motor_elektrigi(m, self.ayar, dR, dL, self.nu[5] - thd, self.nu[6] - thd, V_acik)
        self.V_bara, self.akim = V, (IR, IL)
        self.tork = (m.K_t * IR, m.K_t * IL)
        return self.tork

    def surucu(self, d: float) -> float:
        """Sürücü: PWM çözünürlüğü, ölü bölge, ±1 sınırı."""
        return surucu_cikisi(self.ayar, d)

    def adim(self, dR: float, dL: float, V_acik: float) -> None:
        """Bir fizik adımı: dR, dL firmware'in istediği PWM doluluk oranları (−1…1)."""
        tR, tL = self.elektrik(self.surucu(dR), self.surucu(dL), V_acik)
        self.mekanik_adim(tR, tL)

    # -- mekanik -------------------------------------------------------------------
    def mekanik_adim(self, tR: float, tL: float) -> None:
        p, m, dt = self.p, self.motor, self.dt
        x, psi, th, phR, phL, pmR, pmL = self.q
        v, w, thd, wR, wL, wmR, wmL = self.nu
        s, c = math.sin(th), math.cos(th)
        A = p.I_xx - p.I_zz + p.m_b * p.l**2
        mbl = p.m_b * p.l
        J_m = m.J_m

        M = self.M
        M[0, 0] = p.m_b + 2 * p.m_w
        M[0, 2] = M[2, 0] = mbl * c
        M[1, 1] = p.I_xx * s * s + p.I_zz * c * c + p.m_b * p.l**2 * s * s + p.m_w * p.d**2 / 2 + 2 * p.K_w
        M[2, 2] = p.I_yy + p.m_b * p.l**2 + 2 * J_m
        M[2, 5] = M[5, 2] = M[2, 6] = M[6, 2] = -J_m
        M[3, 3] = M[4, 4] = p.J_w
        M[5, 5] = M[6, 6] = J_m

        bR, bL = p.b * (wR - thd), p.b * (wL - thd)
        f = np.array([
            mbl * s * (thd * thd + w * w),
            -2 * A * s * c * thd * w - mbl * s * v * w,
            A * s * c * w * w + p.m_b * p.g * p.l * s - (tR + tL) + bR + bL,
            -bR,
            -bL,
            tR,
            tL,
        ])

        # Normal kuvvetler (θ̈ bir önceki adımdan) ve kısıt sınırları
        N = (p.m_b + 2 * p.m_w) * p.g - mbl * (s * self.thdd + c * thd * thd)
        dN = p.m_b * v * w * (p.r + p.l * c) / p.d
        NR, NL = max(0.0, N / 2 + dN), max(0.0, N / 2 - dN)
        self.N = (NR, NL)
        sinir = (self.ayar.mu * NR, self.ayar.mu * NL, m.tau_f, m.tau_f)

        nu = np.array(self.nu)
        sag0 = M @ nu + dt * f
        G = self.G
        etkin, yon = self.etkin, self.yon
        delta = (pmR - phR, pmL - phL)

        # Etkin olmayan sürtünme kısıtlarının kayma yönü: hız sıfır değilse hızın işareti
        for j in range(4):
            if not etkin[j]:
                g = float(G[j] @ nu)
                if abs(g) > 1e-12:
                    yon[j] = math.copysign(1.0, g)

        birakilan = set()  # bu adımda tutunmadan kaymaya geçen sürtünme kısıtları
        for _ in range(10):
            idx = [j for j in range(6) if etkin[j]]
            sag = sag0.copy()
            for j in range(4):
                if not etkin[j] and yon[j] != 0.0:
                    sag -= dt * sinir[j] * yon[j] * G[j]
            n = len(idx)
            K = np.zeros((7 + n, 7 + n))
            K[:7, :7] = M
            b = np.zeros(7 + n)
            b[:7] = sag
            for k, j in enumerate(idx):
                K[:7, 7 + k] = -G[j]
                K[7 + k, :7] = G[j]
                if j >= 4 and self.beta > 0:
                    b[7 + k] = (yon[j] * self.beta - delta[j - 4]) / dt
                elif j >= 4:
                    b[7 + k] = -delta[j - 4] / dt
            cozum = np.linalg.solve(K, b)
            yeni = cozum[:7]
            P = dict(zip(idx, cozum[7:]))

            degisti = False
            for j in range(4):  # sürtünme: tutunma ↔ kayma
                if etkin[j]:
                    # Kaymaya geçip aynı adımda yön değiştiren kısıt adımın içinde durmuştur: tutunmada bırakılır
                    if abs(P[j]) > sinir[j] * dt * (1 + 1e-9) and j not in birakilan:
                        etkin[j], yon[j], degisti = False, -math.copysign(1.0, P[j]), True
                        birakilan.add(j)
                elif sinir[j] > 0.0:  # sınırı sıfır olan kısıt (kalkan teker, sürtünmesiz rotor) tutunamaz
                    g = float(G[j] @ yeni)
                    if yon[j] == 0.0 or g * yon[j] <= 0.0:  # kayma durdu ya da yön değiştirdi
                        etkin[j], degisti = True, True
            if self.beta > 0:
                for j in (4, 5):  # dişli: temas ↔ boşluk
                    if etkin[j]:
                        if P[j] * yon[j] > 0.0:  # kısıt çekiyor: dişliler ayrılır
                            etkin[j], degisti = False, True
                    else:
                        d_yeni = delta[j - 4] + dt * float(G[j] @ yeni)
                        if abs(d_yeni) >= self.beta:
                            etkin[j], yon[j], degisti = True, math.copysign(1.0, d_yeni), True
            if not degisti:
                break
        else:
            self.dongu_asimi += 1

        Fs = []
        for i in (0, 1):
            Fs.append(P[i] / dt if etkin[i] else -sinir[i] * yon[i])
        self.F = tuple(Fs)

        v2, w2, thd2, wR2, wL2, wmR2, wmL2 = (float(z) for z in yeni)
        self.thdd, self.vd = (thd2 - thd) / dt, (v2 - v) / dt
        self.nu = [v2, w2, thd2, wR2, wL2, wmR2, wmL2]
        self.q = [x + dt * v2, psi + dt * w2, th + dt * thd2, phR + dt * wR2, phL + dt * wL2, pmR + dt * wmR2, pmL + dt * wmL2]
        if self.beta > 0:  # sayısal kaçak: δ boşluğun dışına taşmasın
            for i in (0, 1):
                dlt = self.q[5 + i] - self.q[3 + i]
                if abs(dlt) > self.beta:
                    self.q[5 + i] = self.q[3 + i] + math.copysign(self.beta, dlt)
        self.X += dt * v2 * math.cos(psi)
        self.Y += dt * v2 * math.sin(psi)
