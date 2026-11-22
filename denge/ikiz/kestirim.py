"""Durum kestirimi: tamamlayıcı süzgeç, Kalman süzgeci ve enkoderden konum/hız.

ESP32'ye taşınabilir yazıldı: her sınıf bir C yapısına (struct) karşılık gelir; alanlar __slots__ ile sabittir,
bütün diziler kurulurken bir kez ayrılır, adım fonksiyonları sabit periyotla (T) çağrılır, numpy kullanılmaz.
Açılar radyan; eğim gövdenin fiziksel eğimidir (IMU'nun gördüğü).
"""

from __future__ import annotations

import math


def ivme_acisi(ax: float, az: float) -> float:
    """İvmeölçerden eğim: durağanken a_x = −g sinθ, a_z = g cosθ."""
    return math.atan2(-ax, az)


class TamamlayiciSuzgec:
    """θ ← α (θ + ω T) + (1 − α) θ_ivme,  α = τ / (τ + T)."""

    __slots__ = ("T", "alfa", "aci", "hiz")

    def __init__(self, tau: float, T: float):
        self.T = T
        self.alfa = tau / (tau + T)
        self.aci = 0.0
        self.hiz = 0.0

    def baslat(self, aci: float) -> None:
        self.aci, self.hiz = aci, 0.0

    def guncelle(self, gyro: float, aci_ivme: float) -> float:
        self.hiz = gyro
        self.aci = self.alfa * (self.aci + gyro * self.T) + (1.0 - self.alfa) * aci_ivme
        return self.aci


class KalmanSuzgeci:
    """İki durumlu Kalman: durum [θ, jiroskop sapması b], giriş jiroskop, ölçüm ivmeölçer açısı.

    Tahmin:   θ ← θ + T (ω − b);  P ← F P Fᵀ + Q T,  F = [[1, −T], [0, 1]]
    Düzeltme: K = P Hᵀ / (H P Hᵀ + R),  H = [1, 0]
    """

    __slots__ = ("T", "q_aci", "q_sapma", "r", "aci", "sapma", "hiz", "P00", "P01", "P10", "P11")

    def __init__(self, q_aci: float, q_sapma: float, r: float, T: float):
        self.T, self.q_aci, self.q_sapma, self.r = T, q_aci, q_sapma, r
        self.aci = self.sapma = self.hiz = 0.0
        self.P00 = self.P11 = 1.0
        self.P01 = self.P10 = 0.0

    def baslat(self, aci: float) -> None:
        """Robot elde durağan tutulurken: ivmeölçer açısına güvenilir (küçük P00), sapma bilinmiyor."""
        self.aci, self.sapma, self.hiz = aci, 0.0, 0.0
        self.P00, self.P01, self.P10, self.P11 = 1e-4, 0.0, 0.0, 1e-4

    def guncelle(self, gyro: float, aci_ivme: float) -> float:
        T = self.T
        self.hiz = gyro - self.sapma
        self.aci += T * self.hiz
        self.P00 += T * (T * self.P11 - self.P01 - self.P10 + self.q_aci)
        self.P01 -= T * self.P11
        self.P10 -= T * self.P11
        self.P11 += self.q_sapma * T
        S = self.P00 + self.r
        K0, K1 = self.P00 / S, self.P10 / S
        y = aci_ivme - self.aci
        self.aci += K0 * y
        self.sapma += K1 * y
        P00, P01 = self.P00, self.P01
        self.P00 -= K0 * P00
        self.P01 -= K0 * P01
        self.P10 -= K1 * P00
        self.P11 -= K1 * P01
        return self.aci


class DurumKestirici:
    """IMU + iki enkoder → s = [x, v, θ, θ̇, ψ, ψ̇] (θ gövdenin fiziksel eğimi).

    Teker açısı (zemine göre) = enkoderin ölçtüğü bağıl açı + gövde eğimi; x = r · ortalama teker açısı.
    Hız, `n_pencere` örneklik sayım farkından bulunur ve birinci dereceden süzgeçten geçer.
    İvme telafisi: robot hızlanırken ivmeölçer a_x ≈ a cosθ − g sinθ ölçer ve eğimi a/g kadar yanlış gösterir.
    Enkoder hızının türevinden bulunan ileri ivme a ile IMU'nun aks üstündeki yüksekliğinden (z_imu) gelen
    teğetsel (z θ̈) ve merkezcil (z θ̇²) terimler ölçümden çıkarılır.
    """

    __slots__ = ("T", "r", "d", "k_sayim", "egim", "n_pencere", "gecmis_R", "gecmis_L", "i", "a_hiz",
                 "x0", "s", "hazir", "telafi", "z_imu", "a_ivme", "v_onceki", "ivme", "gyro_onceki", "aci_ivmesi")

    def __init__(self, egim, r: float, d: float, cpr: float, T: float, pencere: float, hiz_tau: float,
                 telafi: bool = False, z_imu: float = 0.0, ivme_tau: float = 0.02):
        self.T, self.r, self.d = T, r, d
        self.k_sayim = 2.0 * math.pi / cpr  # bir sayımın teker milindeki açısı [rad]
        self.egim = egim  # TamamlayiciSuzgec ya da KalmanSuzgeci
        self.n_pencere = max(1, round(pencere / T))
        self.gecmis_R = [0] * (self.n_pencere + 1)  # halka tampon (C'de sabit dizi)
        self.gecmis_L = [0] * (self.n_pencere + 1)
        self.i = 0
        self.a_hiz = T / (hiz_tau + T) if hiz_tau > 0 else 1.0
        self.x0 = 0.0
        self.s = [0.0] * 6
        self.hazir = False
        self.telafi, self.z_imu = telafi, z_imu
        self.a_ivme = T / (ivme_tau + T)
        self.v_onceki = self.ivme = self.gyro_onceki = self.aci_ivmesi = 0.0

    def baslat(self, ax: float, az: float, sayim_R: int, sayim_L: int) -> None:
        aci = ivme_acisi(ax, az)
        self.egim.baslat(aci)
        for k in range(self.n_pencere + 1):
            self.gecmis_R[k], self.gecmis_L[k] = sayim_R, sayim_L
        self.x0 = self.r * (0.5 * (sayim_R + sayim_L) * self.k_sayim + aci)
        self.s[0] = self.s[1] = self.s[4] = self.s[5] = 0.0
        self.s[2], self.s[3] = aci, 0.0
        self.v_onceki = self.ivme = self.aci_ivmesi = 0.0
        self.hazir = True

    def guncelle(self, gyro: float, ax: float, az: float, sayim_R: int, sayim_L: int) -> list:
        if self.telafi:
            # ileri ivme (bir önceki adımın süzülmüş hızından) ve eğim ivmesi (jiroskop türevi), süzülmüş
            self.ivme += self.a_ivme * ((self.s[1] - self.v_onceki) / self.T - self.ivme)
            self.v_onceki = self.s[1]
            self.aci_ivmesi += self.a_ivme * ((gyro - self.gyro_onceki) / self.T - self.aci_ivmesi)
            self.gyro_onceki = gyro
            c, sn = math.cos(self.s[2]), math.sin(self.s[2])
            ax = ax - self.ivme * c - self.z_imu * self.aci_ivmesi
            az = az - self.ivme * sn + self.z_imu * gyro * gyro
        aci = self.egim.guncelle(gyro, ivme_acisi(ax, az))
        aci_hizi = self.egim.hiz
        n = self.n_pencere + 1
        self.i = (self.i + 1) % n
        self.gecmis_R[self.i], self.gecmis_L[self.i] = sayim_R, sayim_L
        eski = (self.i + 1) % n  # n_pencere örnek önceki sayım
        k = self.k_sayim
        dR = (sayim_R - self.gecmis_R[eski]) * k / (self.n_pencere * self.T)  # bağıl teker hızı [rad/s]
        dL = (sayim_L - self.gecmis_L[eski]) * k / (self.n_pencere * self.T)
        v_ham = self.r * (0.5 * (dR + dL) + aci_hizi)
        w_ham = self.r * (dR - dL) / self.d
        s = self.s
        s[0] = self.r * (0.5 * (sayim_R + sayim_L) * k + aci) - self.x0
        s[1] += self.a_hiz * (v_ham - s[1])
        s[2], s[3] = aci, aci_hizi
        s[4] = self.r * (sayim_R - sayim_L) * k / self.d
        s[5] += self.a_hiz * (w_ham - s[5])
        return s

    def bagil_hizlar(self) -> tuple[float, float]:
        """Motor başına rotorun gövdeye göre hızı [rad/s, teker milinde] (zıt EMK telafisi için), süzülmüş."""
        v, w = self.s[1], self.s[5]
        ort = v / self.r - self.s[3]
        fark = w * self.d / (2 * self.r)
        return ort + fark, ort - fark
