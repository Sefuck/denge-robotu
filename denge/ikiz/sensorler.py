"""Sensör modelleri: MPU6050 (jiroskop + ivmeölçer) ve Hall enkoder; pil gerilimi ölçümü.

MPU6050: beyaz gürültü (veri sayfası yoğunluğu), açılış kalibrasyonundan sonra kalan sabit sapma (büyüklük
parametre dosyasından, işaret rastgele), iç alçak geçiren süzgeç (DLPF, birinci dereceden yaklaşım) ve 16 bit
nicemleme. İvmeölçer, IMU'nun bulunduğu noktadaki özgül kuvveti ölçer: gövde ileri ivmelendikçe ya da eğim
ivmesi oluştukça ivme açısı bozulur (kestiricilerin asıl zorluğu budur).
Enkoder: rotorun gövdeye göre açısı (dişli boşluğu dahil) teker turu başına `cpr` sayımla tamsayıya kesilir.
"""

from __future__ import annotations

import math

import numpy as np

from ..kutle_merkezi import ozgul_kuvvet
from .ayarlar import SensorAyarlari


class IMU:
    def __init__(self, ayar: SensorAyarlari, dt: float, rng: np.random.Generator, g: float):
        self.a, self.dt, self.rng, self.g = ayar, dt, rng, g
        isaret = lambda: 1.0 if rng.random() < 0.5 else -1.0
        self.gyro_sapma = isaret() * ayar.gyro_sapma
        self.ivme_sapma = isaret() * ayar.ivme_sapma
        fs = 1 / dt
        self.gyro_std = ayar.gyro_gurultu * math.sqrt(fs / 2)  # beyaz gürültü, Nyquist bandına yayılmış
        self.ivme_std = ayar.ivme_gurultu * math.sqrt(fs / 2)
        self.k = 1 - math.exp(-2 * math.pi * ayar.suzgec_hz * dt)  # DLPF
        self.gyro = self.ax = self.az = None
        # Gürültü önceden üretilir (hız için): blok blok
        self._blok = np.empty((0, 3))
        self._i = 0

    def _gurultu(self):
        if self._i >= len(self._blok):
            self._blok = self.rng.standard_normal((4096, 3))
            self._i = 0
        z = self._blok[self._i]
        self._i += 1
        return z

    def guncelle(self, theta: float, theta_d: float, theta_dd: float, x_dd: float) -> None:
        """Her fizik adımında çağrılır: gerçek hareketten ham ölçümü üretir, DLPF'den geçirir."""
        x_b, z_b = self.a.imu_konum
        f_x, f_z = ozgul_kuvvet(x_dd, theta, theta_d, theta_dd, x_b, z_b, self.g)
        n = self._gurultu()
        gyro = theta_d + self.gyro_sapma + self.gyro_std * n[0]
        ax = f_x + self.ivme_sapma + self.ivme_std * n[1]
        az = f_z + self.ivme_std * n[2]
        if self.gyro is None:
            self.gyro, self.ax, self.az = gyro, ax, az
        else:
            k = self.k
            self.gyro += k * (gyro - self.gyro)
            self.ax += k * (ax - self.ax)
            self.az += k * (az - self.az)

    def oku(self) -> tuple[float, float, float]:
        """Firmware'in okuduğu nicemlenmiş değerler: (jiroskop [rad/s], a_x, a_z [m/s²])."""
        a = self.a
        return (round(self.gyro / a.gyro_lsb) * a.gyro_lsb, round(self.ax / a.ivme_lsb) * a.ivme_lsb,
                round(self.az / a.ivme_lsb) * a.ivme_lsb)


def enkoder_sayimi(bagil_aci: float, cpr: float) -> int:
    """Rotorun gövdeye göre açısı [rad, teker milinde] → x4 sayım."""
    return math.floor(bagil_aci * cpr / (2 * math.pi))


class PilOlcumu:
    """ESP32 ADC ile pil gerilimi: sabit kazanç hatası (işaret rastgele)."""

    def __init__(self, hata: float, rng: np.random.Generator):
        self.carpan = 1 + (hata if rng.random() < 0.5 else -hata)

    def oku(self, V_bara: float) -> float:
        return V_bara * self.carpan
