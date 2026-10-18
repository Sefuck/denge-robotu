"""Açık çevrim düşme simülasyonu ve kontrolcüden bağımsız referans manevralar.

Referans manevralar doğrusal modelin düz çıkışı (flat output) ile kurulur:
    F = c1·x + c2·θ,   c1 = M_x r + a12,   c2 = a12 r + a22,   F̈ = m_b g l θ
(Motor torku ve sürtünme teker ile gövde arasında iç kuvvet olduğundan F'nin denkleminden düşer.)
F için uç koşulları sağlayan 7. derece polinom seçilince x(t), θ(t) ve u(t) cebirsel olarak bulunur.
Bu manevralar bir kontrolcü değildir; motor tork/devir gereksinimini kontrol yöntemi seçilmeden
sınırlamak için kullanılır. Torklar ayrıca doğrusal olmayan modelin ters dinamiğiyle doğrulanır.
"""

from __future__ import annotations

import math

import numpy as np
from numpy.polynomial import polynomial as P
from scipy.integrate import solve_ivp
from scipy.linalg import expm
from scipy.optimize import minimize_scalar

from . import model
from .model import ModelParametreleri


# ---------------------------------------------------------------------------
# Açık çevrim düşme (u = 0, motorlar enerjisiz)
# ---------------------------------------------------------------------------
def acik_cevrim_dusme(
    p: ModelParametreleri,
    theta0: float,
    t_son: float = 1.5,
    mod: str = "serbest",
    yere_degme: tuple[float, float] = (math.pi / 2, math.pi / 2),
    n: int = 3001,
) -> dict:
    """θ0'dan [rad] durağan bırakılan robotun doğrusal olmayan düşmesi.

    mod = 'serbest': tekerler serbest döner (redüktör geri sürülebilir), u = 0.
    mod = 'kilitli': tekerler gövdeye kilitli (redüktör geri sürülemez), robot tek parça yuvarlanır.
    yere_degme = (ileri, geri) yere değme açıları [rad]; gövde yere değince simülasyon durur.
    """
    ileri, geri = yere_degme
    i_th = 2 if mod == "serbest" else 0

    def olay(t, y):
        th = y[i_th]
        return ileri - th if th >= 0 else th + geri

    olay.terminal, olay.direction = True, -1
    if mod == "serbest":
        f, y0 = (lambda t, y: model.dinamik(p, y)), [0.0, 0.0, theta0, 0.0, 0.0, 0.0]
    elif mod == "kilitli":
        f, y0 = (lambda t, y: model.kilitli_dinamik(p, y)), [theta0, 0.0]
    else:
        raise ValueError(mod)
    cozum = solve_ivp(f, (0.0, t_son), y0, method="DOP853", rtol=1e-10, atol=1e-12, events=olay, dense_output=True)
    t_degme = float(cozum.t_events[0][0]) if cozum.t_events[0].size else None
    t = np.linspace(0.0, t_degme if t_degme is not None else t_son, n)
    y = cozum.sol(t)
    if mod == "serbest":
        return {"t": t, "x": y[0], "v": y[1], "theta": y[2], "theta_d": y[3], "t_degme": t_degme, "durum": y}
    # Kilitli: robot teker üzerinde yuvarlanır, x = r(θ − θ0)
    return {"t": t, "x": p.r * (y[0] - theta0), "theta": y[0], "theta_d": y[1], "t_degme": t_degme}


def dogrusal_serbest_yanit(A: np.ndarray, x0, t: np.ndarray) -> np.ndarray:
    """u = 0 için doğrusal model yanıtı x(t) = e^{At} x0 (satırlar: zaman)."""
    return np.array([expm(A * ti) @ np.asarray(x0, float) for ti in t])


def esige_ulasma_suresi(theta0: float, esik: float, p_kararsiz: float) -> float:
    """Doğrusal yaklaşımla θ0'dan |θ| = eşik'e ulaşma süresi (θ = θ0 cosh(p t))."""
    return math.acosh(esik / theta0) / p_kararsiz


# ---------------------------------------------------------------------------
# Düz çıkış ile referans manevralar
# ---------------------------------------------------------------------------
def duz_cikis_katsayilari(p: ModelParametreleri) -> tuple[float, float, float]:
    k = model.dogrusal_katsayilar(p)
    return k["M_x"] * p.r + k["a12"], k["a12"] * p.r + k["a22"], k["mgl"]


def polinom_7(bas: list[float], son: list[float], T: float) -> np.ndarray:
    """[F, Ḟ, F̈, F⃛] uç koşullarını t = 0 ve t = T'de sağlayan 7. derece polinom (artan katsayılar)."""
    M = np.zeros((8, 8))
    for k in range(4):
        for i in range(k, 8):
            carpan = math.factorial(i) / math.factorial(i - k)
            M[k, i] = carpan if i == k else 0.0
            M[4 + k, i] = carpan * T ** (i - k)
    return np.linalg.solve(M, np.concatenate([bas, son]))


def duz_yorunge(p: ModelParametreleri, F: np.ndarray, t: np.ndarray) -> dict:
    """F(t) polinomundan doğrusal model durumları ve girişi."""
    c1, c2, mgl = duz_cikis_katsayilari(p)
    k = model.dogrusal_katsayilar(p)
    Fk = [P.polyval(t, P.polyder(F, m)) for m in range(5)]
    th, thd, thdd = Fk[2] / mgl, Fk[3] / mgl, Fk[4] / mgl
    x, xd, xdd = (Fk[0] - c2 * th) / c1, (Fk[1] - c2 * thd) / c1, (Fk[2] - c2 * thdd) / c1
    u = p.r * (k["M_x"] * xdd + k["a12"] * thdd) + 2 * p.b * (xd / p.r - thd)
    return {"t": t, "x": x, "xd": xd, "xdd": xdd, "theta": th, "theta_d": thd, "theta_dd": thdd, "u": u, "F": F}


def ters_dinamik(p: ModelParametreleri, yorunge: dict) -> dict:
    """θ(t) yörüngesi doğrusal olmayan modelde izlenirse gereken tork τ(t) ve oluşan x(t).

    θ, θ̇, θ̈ polinomdan alınır; ẍ ve τ doğrusal olmayan ileri + eğim denklemlerinden çözülür.
    """
    M_f, h_f, *_ = model._sayisal_fonksiyonlar()
    par = p.dizi()
    _, _, mgl = duz_cikis_katsayilari(p)
    F = yorunge["F"]
    dF = [P.polyder(F, m) for m in (2, 3, 4)]

    def ivme_ve_tork(t, xd):
        th, thd, thdd = (P.polyval(t, c) / mgl for c in dF)
        M = np.asarray(M_f(th, *par), float)
        h0 = np.asarray(h_f(xd, 0.0, th, thd, 0.0, 0.0, *par), float).ravel()  # τ = 0 iken
        # M00 ẍ − τ/r = −M02 θ̈ − h0[0]  ;  M20 ẍ + τ = −M22 θ̈ − h0[2]
        Ms = np.array([[M[0, 0], -1.0 / p.r], [M[2, 0], 1.0]])
        sag = np.array([-M[0, 2] * thdd - h0[0], -M[2, 2] * thdd - h0[2]])
        return np.linalg.solve(Ms, sag)

    t = yorunge["t"]
    cozum = solve_ivp(
        lambda ti, y: [y[1], ivme_ve_tork(ti, y[1])[0]],
        (t[0], t[-1]),
        [yorunge["x"][0], yorunge["xd"][0]],
        t_eval=t,
        rtol=1e-10,
        atol=1e-12,
    )
    tau = np.array([ivme_ve_tork(ti, xdi)[1] for ti, xdi in zip(t, cozum.y[1])])
    return {"x": cozum.y[0], "xd": cozum.y[1], "u": tau}


def referans_toparlanma(p: ModelParametreleri, theta0: float, T: float, n: int = 801) -> dict:
    """θ0'dan [rad] durağan başlayıp T sürede θ = 0'da durağan biten manevra.

    Son konum x_f serbesttir; ∫u² dt'yi en küçük yapacak şekilde seçilir.
    """
    c1, c2, mgl = duz_cikis_katsayilari(p)
    t = np.linspace(0.0, T, n)

    def yorunge(x_f):
        return duz_yorunge(p, polinom_7([c2 * theta0, 0.0, mgl * theta0, 0.0], [c1 * x_f, 0.0, 0.0, 0.0], T), t)

    x_f = minimize_scalar(lambda xf: np.trapezoid(yorunge(xf)["u"] ** 2, t)).x
    y = yorunge(x_f)
    y["x_f"] = x_f
    y["dogrusal_olmayan"] = ters_dinamik(p, y)
    return y


def referans_oteleme(p: ModelParametreleri, mesafe: float, T: float, n: int = 801) -> dict:
    """Durağandan durağana, θ = 0'da başlayıp biten `mesafe` [m] öteleme (Ö1/Ö2)."""
    c1, _, _ = duz_cikis_katsayilari(p)
    t = np.linspace(0.0, T, n)
    y = duz_yorunge(p, polinom_7([0.0] * 4, [c1 * mesafe, 0.0, 0.0, 0.0], T), t)
    y["dogrusal_olmayan"] = ters_dinamik(p, y)
    return y


def toparlanma_taramasi(p: ModelParametreleri, theta0: float, sureler) -> dict:
    """Manevra süresine göre tepe tork (doğrusal / doğrusal olmayan) ve tepe hız."""
    sonuc = {"T": np.asarray(sureler, float), "u_dogrusal": [], "u_dogrusal_olmayan": [], "v_tepe": [], "x_f": []}
    for T in sureler:
        y = referans_toparlanma(p, theta0, T, n=401)
        sonuc["u_dogrusal"].append(np.max(np.abs(y["u"])))
        sonuc["u_dogrusal_olmayan"].append(np.max(np.abs(y["dogrusal_olmayan"]["u"])))
        sonuc["v_tepe"].append(np.max(np.abs(y["dogrusal_olmayan"]["xd"])))
        sonuc["x_f"].append(y["x_f"])
    return {k: np.asarray(v) for k, v in sonuc.items()}
