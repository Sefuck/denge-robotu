"""Kütle bütçesi, kütle merkezi (KM), atalet tensörü ve kutu yuvası analizi.

Koordinatlar: orijin teker aksının orta noktası; x ileri, y sol, z gövde ekseni boyunca yukarı.
Bileşenler dikdörtgen prizma (kutu) olarak yaklaşılır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq



@dataclass(frozen=True)
class Bilesen:
    ad: str
    kutle: float  # kg
    konum: tuple[float, float, float]  # bileşen KM'si (x, y, z) [m]
    boyut: tuple[float, float, float]  # (dx, dy, dz) [m]
    kategori: str = "gövde"


@dataclass(frozen=True)
class GovdeOzellikleri:
    kutle: float  # kg
    km: np.ndarray  # (x, y, z) [m]
    atalet: np.ndarray  # 3x3, KM etrafında [kg m^2]


def govde_ozellikleri(bilesenler: list[Bilesen]) -> GovdeOzellikleri:
    """Toplam kütle, KM ve KM etrafındaki atalet tensörü (paralel eksen teoremiyle)."""
    m = sum(b.kutle for b in bilesenler)
    km = sum(b.kutle * np.asarray(b.konum, float) for b in bilesenler) / m
    I = np.zeros((3, 3))
    for b in bilesenler:
        dx, dy, dz = b.boyut
        I += b.kutle / 12.0 * np.diag([dy**2 + dz**2, dx**2 + dz**2, dx**2 + dy**2])
        rv = np.asarray(b.konum, float) - km
        I += b.kutle * (rv @ rv * np.eye(3) - np.outer(rv, rv))
    return GovdeOzellikleri(m, km, I)


def denge_acisi(km) -> float:
    """KM'yi aksın tam üstüne getiren gövde eğimi [rad] (pozitif = ileri eğim).

    KM ileride (x_c > 0) ise gövde geriye yatarak dengelenir. Denetleyici bu açıyı
    'denge noktası' (trim) olarak kullanmalıdır.
    """
    return -math.atan2(km[0], km[2])


def nokta_yuksekligi(x_b: float, z_b: float, theta: float, r: float) -> float:
    """Gövdedeki (x_b, z_b) noktasının θ eğiminde zeminden yüksekliği [m]."""
    return r - x_b * math.sin(theta) + z_b * math.cos(theta)


def yere_degme_acisi(x_b: float, z_b: float, r: float, yon: int = +1) -> float:
    """Gövde noktası (x_b, z_b) yere değene kadar gövdenin eğilebileceği açı [rad, ≥ 0].

    yon = +1 ileri eğim, −1 geri eğim. Nokta aksa r'den yakınsa hiç değmez (inf).
    """
    if math.hypot(x_b, z_b) < r:
        return math.inf
    f = lambda a: nokta_yuksekligi(x_b, z_b, yon * a, r)
    izgara = np.linspace(0.0, math.pi, 3601)
    degerler = np.array([f(a) for a in izgara])
    if degerler[0] <= 0:
        return 0.0
    altinda = np.nonzero(degerler <= 0)[0]
    if altinda.size == 0:
        return math.inf
    i = altinda[0]
    return brentq(f, izgara[i - 1], izgara[i])


def vurus_merkezi(p) -> float:
    """Aksa göre vuruş merkezi yüksekliği z_cp = l + I_yy/(m_b l) [m].

    Gövde ekseni üzerindeki bir noktada gövdeye dik özgül kuvvet (b = 0, J_m = 0):
        f_x = (z − z_cp)·θ̈ − τ/(m_b l)
    Kutu z_cp'ye yakınsa θ̈'dan gelen yük sıfıra iner; τ terimi yükseklikten bağımsızdır.
    """
    return p.l + p.I_yy / (p.m_b * p.l)


def ozgul_kuvvet(x_dd, th, th_d, th_dd, x_b: float, z_b: float, g: float):
    """Gövdedeki (x_b, z_b) noktasında gövde eksenlerinde özgül kuvvet (a − g) [m/s^2].

    Dönen (f_x, f_z): f_x gövdeye dik (ileri), f_z gövde ekseni boyunca. Kutunun
    yuvada hissettiği 'görünür yerçekimi' −f'dir; α = atan2(f_x, f_z) kutuya göre
    görünür eğimdir.
    """
    s, c = np.sin(th), np.cos(th)
    X_dd = x_dd + (-x_b * s + z_b * c) * th_dd + (-x_b * c - z_b * s) * th_d**2
    Z_dd = (-x_b * c - z_b * s) * th_dd + (x_b * s - z_b * c) * th_d**2
    f_x = X_dd * c - (Z_dd + g) * s
    f_z = X_dd * s + (Z_dd + g) * c
    return f_x, f_z


def yere_degme_acilari(tasarim) -> dict:
    """Gövdenin her dış noktası için ileri/geri yere değme açısı ve en küçükleri [rad]."""
    r = tasarim.d("teker.yaricap")
    satirlar = [(ad, yere_degme_acisi(x, z, r, +1), yere_degme_acisi(x, z, r, -1)) for ad, (x, z) in tasarim.govde_noktalari().items()]
    return {"noktalar": satirlar, "ileri": min(s[1] for s in satirlar), "geri": min(s[2] for s in satirlar)}
