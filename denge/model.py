"""İki tekerlekli ters sarkaç: Lagrange türetimi, doğrusallaştırma, durum-uzay, transfer fonksiyonu.

Genelleştirilmiş koordinatlar q = (X, Y, ψ, θ, φ_R, φ_L):
    X, Y  : aks orta noktasının zemindeki konumu
    ψ     : sapma (yaw), sola dönüş pozitif
    θ     : gövde eğimi (pitch), ileri eğim pozitif (KM aksın önüne geçer)
    φ_R/L : sağ/sol teker dönüş açısı
Kaymadan yuvarlanma ve yanal kaymama kısıtları holonom değildir; bu yüzden denklemler
Lagrange–d'Alembert ilkesiyle (kısıtlı Lagrange) serbest hızlar ν = (v, ψ̇, θ̇) üzerine
izdüşürülür. Giriş: teker millerindeki motor torkları τ_R, τ_L (motor tepkisi gövdeye).
"""

from __future__ import annotations

import math
from dataclasses import astuple, dataclass, fields, replace
from functools import lru_cache

import numpy as np
import sympy as sp
from scipy import signal


@dataclass(frozen=True)
class ModelParametreleri:
    m_b: float  # gövde kütlesi (tekerler hariç, motor statoru dahil) [kg]
    l: float  # aks → gövde KM uzaklığı [m]
    I_xx: float  # gövdenin KM'deki yuvarlanma (roll) ataleti [kg m^2]
    I_yy: float  # gövdenin KM'deki yunuslama (pitch) ataleti [kg m^2]
    I_zz: float  # gövdenin KM'deki sapma (yaw) ataleti [kg m^2]
    m_w: float  # bir tekerin kütlesi [kg]
    J_w: float  # bir tekerin dönme ekseni ataleti [kg m^2]
    K_w: float  # bir tekerin çap ekseni ataleti [kg m^2]
    r: float  # teker yarıçapı [m]
    d: float  # iz genişliği (teker merkezleri arası) [m]
    J_m: float = 0.0  # rotor ataletinin teker miline yansıması J_rotor·N², bir taraf [kg m^2]
    b: float = 0.0  # teker–gövde arası viskoz sürtünme, bir taraf [N m s/rad]
    g: float = 9.80665  # [m/s^2]

    def degistir(self, **degerler) -> ModelParametreleri:
        return replace(self, **degerler)

    def dizi(self) -> tuple:
        return astuple(self)


PARAMETRE_ADLARI = tuple(f.name for f in fields(ModelParametreleri))
DURUM_ADLARI = ("x", "v", "theta", "theta_d", "psi", "psi_d")


# ---------------------------------------------------------------------------
# Sembolik türetim
# ---------------------------------------------------------------------------
def sadelestir(ifade, *acilar):
    """Açar ve sin²a → 1 − cos²a yazar. sp.simplify'ın aksine süresi Python hash
    tohumuna (PYTHONHASHSEED) bağlı değildir; simplify bazı tohumlarda dakikalarca sürüyordu."""
    ifade = sp.expand(ifade)
    for a in acilar:
        ifade = sp.expand(ifade.subs(sp.sin(a) ** 2, 1 - sp.cos(a) ** 2))
    return ifade


@lru_cache(maxsize=None)
def turet() -> dict:
    """Doğrusal olmayan hareket denklemlerini sembolik olarak türetir.

    Dönen sözlükte 'denklemler' üç ifade içerir (her biri = 0):
        [0] ileri (v),  [1] sapma (ψ),  [2] eğim (θ)
    'M' ivmelere göre kütle matrisi (ν̇ = [v̇, ψ̈, θ̈]), 'h' kalan terimler: M·ν̇ + h = 0.
    'kilitli' tekerler gövdeye kilitliyken (redüktör geri sürülemiyorsa) tek serbestlik
    dereceli denklemi verir.
    """
    t = sp.Symbol("t")
    P = {ad: sp.Symbol(ad, positive=True) for ad in PARAMETRE_ADLARI}
    P["l"] = sp.Symbol("l", real=True)  # KM aksın altına da düşebilir (pasif test analizi)
    for ad in ("J_m", "b"):
        P[ad] = sp.Symbol(ad, nonnegative=True)
    m_b, l, I_xx, I_yy, I_zz, m_w, J_w, K_w, r, d, J_m, b, g = (P[ad] for ad in PARAMETRE_ADLARI)
    tau_R, tau_L = sp.symbols("tau_R tau_L", real=True)

    X, Y, psi, th, phR, phL = (sp.Function(ad)(t) for ad in ("X", "Y", "psi", "theta", "phi_R", "phi_L"))
    q = [X, Y, psi, th, phR, phL]
    qd = [sp.diff(qi, t) for qi in q]
    psid, thd = qd[2], qd[3]

    # Kinetik enerji
    P_govde = sp.Matrix([X + l * sp.sin(th) * sp.cos(psi), Y + l * sp.sin(th) * sp.sin(psi), r + l * sp.cos(th)])
    v_govde = P_govde.diff(t)
    # Gövde açısal hızı gövde eksenlerinde: (−ψ̇ sinθ, θ̇, ψ̇ cosθ)
    T_govde = m_b / 2 * v_govde.dot(v_govde) + (
        I_xx * (psid * sp.sin(th)) ** 2 + I_yy * thd**2 + I_zz * (psid * sp.cos(th)) ** 2
    ) / 2
    W_R = sp.Matrix([X + d / 2 * sp.sin(psi), Y - d / 2 * sp.cos(psi)])
    W_L = sp.Matrix([X - d / 2 * sp.sin(psi), Y + d / 2 * sp.cos(psi)])
    T_teker = (
        m_w / 2 * (W_R.diff(t).dot(W_R.diff(t)) + W_L.diff(t).dot(W_L.diff(t)))
        + J_w / 2 * (qd[4] ** 2 + qd[5] ** 2)
        + K_w * psid**2
    )
    T_rotor = J_m / 2 * ((qd[4] - thd) ** 2 + (qd[5] - thd) ** 2)
    T = T_govde + T_teker + T_rotor
    V = m_b * g * l * sp.cos(th)
    L = T - V

    # Genelleştirilmiş kuvvetler: motor torku ve sürtünme teker ile gövde arasında etkir
    bagil_R, bagil_L = qd[4] - thd, qd[5] - thd
    Q = [0, 0, 0, -(tau_R + tau_L) + b * (bagil_R + bagil_L), tau_R - b * bagil_R, tau_L - b * bagil_L]
    E = [sp.diff(sp.diff(L, qd[i]), t) - sp.diff(L, q[i]) - Q[i] for i in range(6)]

    # Serbest hızlar ν = (v, ψ̇, θ̇): q̇ = S(q)·ν
    v, w = sp.Function("v")(t), sp.Function("w")(t)
    S = sp.Matrix(
        [[sp.cos(psi), 0, 0], [sp.sin(psi), 0, 0], [0, 1, 0], [0, 0, 1], [1 / r, d / (2 * r), 0], [1 / r, -d / (2 * r), 0]]
    )
    sym = dict(zip(("v", "w", "theta", "theta_d", "v_d", "w_d", "theta_dd"), sp.symbols("v w theta theta_d v_d w_d theta_dd", real=True)))

    def izdusur(ifadeler, S_kisit, nu):
        qd_k = S_kisit * nu
        qdd_k = qd_k.diff(t)
        ikinci = {sp.diff(q[i], t, 2): qdd_k[i] for i in (0, 1, 2, 4, 5)}
        birinci = {qd[i]: qd_k[i] for i in (0, 1, 2, 4, 5)}
        izdusum = S_kisit.T * sp.Matrix([e.subs(ikinci).subs(birinci) for e in ifadeler])
        return [duzlestir(e) for e in izdusum]

    def duzlestir(e):
        e = e.subs({sp.diff(v, t): sym["v_d"], sp.diff(w, t): sym["w_d"], sp.diff(th, t, 2): sym["theta_dd"]})
        e = e.subs({v: sym["v"], w: sym["w"], sp.diff(th, t): sym["theta_d"]}).subs(th, sym["theta"])
        e = sadelestir(e, psi, sym["theta"])
        if e.has(psi):  # dönme simetrisi: denklemler sapma açısına bağlı olamaz
            raise RuntimeError("Hareket denklemlerinde ψ kaldı; türetim hatalı")
        return e

    denklemler = izdusur(E, S, sp.Matrix([v, w, thd]))
    ivmeler = [sym["v_d"], sym["w_d"], sym["theta_dd"]]
    M = sp.Matrix(denklemler).jacobian(ivmeler)
    h = sp.Matrix([sp.expand(e.subs({a: 0 for a in ivmeler})) for e in denklemler])

    birinci = {qd[i]: (S * sp.Matrix([v, w, thd]))[i] for i in (0, 1, 2, 4, 5)}
    T_nu = duzlestir(T.subs(birinci))
    V_nu = V.subs(th, sym["theta"])

    # Tekerler gövdeye kilitli: φ̇ = θ̇, v = r·θ̇, ψ̇ = 0
    S_kilit = sp.Matrix([r * sp.cos(psi), r * sp.sin(psi), 0, 1, 1, 1])
    kilitli = izdusur(E, S_kilit, sp.Matrix([thd]))[0]

    return {
        "P": P,
        "tau_R": tau_R,
        "tau_L": tau_L,
        **sym,
        "denklemler": denklemler,
        "M": M.applyfunc(lambda e: sadelestir(e, sym["theta"])),
        "h": h,
        "T": T_nu,
        "V": V_nu,
        "kilitli": kilitli,
    }


def el_ile_yazilmis_denklemler() -> list:
    """Dokümandaki (el ile yazılmış) denklemler; `turet()` sonucuyla aynı olmalı (test edilir)."""
    D = turet()
    m_b, l, I_xx, I_yy, I_zz, m_w, J_w, K_w, r, d, J_m, b, g = (D["P"][ad] for ad in PARAMETRE_ADLARI)
    v, w, th, thd, vd, wd, thdd = (D[k] for k in ("v", "w", "theta", "theta_d", "v_d", "w_d", "theta_dd"))
    tR, tL = D["tau_R"], D["tau_L"]
    s, c = sp.sin(th), sp.cos(th)
    M_x = m_b + 2 * m_w + 2 * (J_w + J_m) / r**2
    a12 = m_b * l * c - 2 * J_m / r
    a22 = I_yy + m_b * l**2 + 2 * J_m
    J_psi = I_xx * s**2 + I_zz * c**2 + m_b * l**2 * s**2 + 2 * K_w + m_w * d**2 / 2 + (J_w + J_m) * d**2 / (2 * r**2)
    kayma = v / r - thd  # tekerin gövdeye göre bağıl açısal hızı
    ileri = M_x * vd + a12 * thdd - m_b * l * s * (thd**2 + w**2) - (tR + tL) / r + 2 * b / r * kayma
    sapma = (
        J_psi * wd
        + 2 * (I_xx - I_zz + m_b * l**2) * s * c * thd * w
        + m_b * l * s * v * w
        - d / (2 * r) * (tR - tL)
        + b * d**2 / (2 * r**2) * w
    )
    egim = a12 * vd + a22 * thdd - (I_xx - I_zz + m_b * l**2) * s * c * w**2 - m_b * g * l * s + (tR + tL) - 2 * b * kayma
    return [ileri, sapma, egim]


# ---------------------------------------------------------------------------
# Sayısal doğrusal olmayan model
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _sayisal_fonksiyonlar():
    D = turet()
    par = [D["P"][ad] for ad in PARAMETRE_ADLARI]
    durum = [D[k] for k in ("v", "w", "theta", "theta_d")]
    M_f = sp.lambdify([D["theta"], *par], D["M"], "numpy")
    h_f = sp.lambdify([*durum, D["tau_R"], D["tau_L"], *par], D["h"], "numpy")
    E_f = sp.lambdify([*durum, *par], D["T"] + D["V"], "numpy")
    kilitli = D["kilitli"]
    J_k = sp.diff(kilitli, D["theta_dd"])
    h_k = sp.expand(kilitli - J_k * D["theta_dd"])
    Jk_f = sp.lambdify([D["theta"], *par], J_k, "numpy")
    hk_f = sp.lambdify([D["theta"], D["theta_d"], *par], h_k, "numpy")
    return M_f, h_f, E_f, Jk_f, hk_f


def dinamik(p: ModelParametreleri, durum, tau_R: float = 0.0, tau_L: float = 0.0) -> np.ndarray:
    """Doğrusal olmayan model: durum = [x, v, θ, θ̇, ψ, ψ̇] → türevi.

    x, aks orta noktasının yön boyunca aldığı yoldur (∫v dt).
    """
    M_f, h_f, *_ = _sayisal_fonksiyonlar()
    _, v, th, thd, _, w = durum
    par = p.dizi()
    M = np.asarray(M_f(th, *par), float)
    h = np.asarray(h_f(v, w, th, thd, tau_R, tau_L, *par), float).ravel()
    vd, wd, thdd = np.linalg.solve(M, -h)
    return np.array([v, vd, thd, thdd, w, wd])


def kilitli_dinamik(p: ModelParametreleri, durum) -> np.ndarray:
    """Tekerler gövdeye kilitli (redüktör geri sürülemez) iken durum = [θ, θ̇] → türevi."""
    *_, Jk_f, hk_f = _sayisal_fonksiyonlar()
    th, thd = durum
    par = p.dizi()
    return np.array([thd, -float(hk_f(th, thd, *par)) / float(Jk_f(th, *par))])


def enerji(p: ModelParametreleri, durum) -> float:
    """Toplam mekanik enerji T + V [J] (potansiyel sıfırı aks yüksekliğinde)."""
    _, _, E_f, *_ = _sayisal_fonksiyonlar()
    _, v, th, thd, _, w = durum
    return float(E_f(v, w, th, thd, *p.dizi()))


# ---------------------------------------------------------------------------
# θ = 0 civarında doğrusallaştırma
# ---------------------------------------------------------------------------
def dogrusal_katsayilar(p: ModelParametreleri) -> dict:
    """Doğrusal modelin kütle matrisi elemanları ve türetilen büyüklükler."""
    M_x = p.m_b + 2 * p.m_w + 2 * (p.J_w + p.J_m) / p.r**2
    a12 = p.m_b * p.l - 2 * p.J_m / p.r
    a22 = p.I_yy + p.m_b * p.l**2 + 2 * p.J_m
    Delta = M_x * a22 - a12**2
    mgl = p.m_b * p.g * p.l
    J_psi = p.I_zz + 2 * p.K_w + p.m_w * p.d**2 / 2 + (p.J_w + p.J_m) * p.d**2 / (2 * p.r**2)
    return {"M_x": M_x, "a12": a12, "a22": a22, "Delta": Delta, "mgl": mgl, "J_psi": J_psi}


def durum_uzay(p: ModelParametreleri):
    """Eğim + ileri alt sistemi: durum [x, ẋ, θ, θ̇], giriş u = τ_R + τ_L [N m].

    C = I (x, ẋ enkoderden; θ filtreden; θ̇ jiroskoptan), D = 0.
    """
    k = dogrusal_katsayilar(p)
    M = np.array([[k["M_x"], k["a12"]], [k["a12"], k["a22"]]])
    Minv = np.linalg.inv(M)
    # [v̇; θ̈] = M⁻¹ (K_v v + K_θ θ + K_θ̇ θ̇ + E u)
    K_v = np.array([-2 * p.b / p.r**2, 2 * p.b / p.r])
    K_th = np.array([0.0, k["mgl"]])
    K_thd = np.array([2 * p.b / p.r, -2 * p.b])
    E = np.array([1 / p.r, -1.0])
    A = np.zeros((4, 4))
    A[0, 1] = A[2, 3] = 1.0
    A[[1, 3], 1] = Minv @ K_v
    A[[1, 3], 2] = Minv @ K_th
    A[[1, 3], 3] = Minv @ K_thd
    B = np.zeros((4, 1))
    B[[1, 3], 0] = Minv @ E
    return A, B, np.eye(4), np.zeros((4, 1))


def donus_durum_uzay(p: ModelParametreleri):
    """Sapma alt sistemi: durum [ψ, ψ̇], giriş u_ψ = τ_R − τ_L [N m]."""
    J_psi = dogrusal_katsayilar(p)["J_psi"]
    A = np.array([[0.0, 1.0], [0.0, -p.b * p.d**2 / (2 * p.r**2 * J_psi)]])
    B = np.array([[0.0], [p.d / (2 * p.r * J_psi)]])
    return A, B, np.eye(2), np.zeros((2, 1))


def kutuplar(p: ModelParametreleri) -> dict:
    return {
        "egim": np.linalg.eigvals(durum_uzay(p)[0]),
        "donus": np.linalg.eigvals(donus_durum_uzay(p)[0]),
    }


def kararsiz_kutup(p: ModelParametreleri) -> float:
    """Eğim alt sisteminin en büyük reel kısımlı kutbu [1/s] (> 0 ise açık çevrim kararsız)."""
    return float(np.max(np.linalg.eigvals(durum_uzay(p)[0]).real))


def kilitli_kutup(p: ModelParametreleri) -> float:
    """Tekerler gövdeye kilitliyken doğrusallaştırılmış kutup [1/s] (KM aksın altındaysa 0)."""
    *_, Jk_f, hk_f = _sayisal_fonksiyonlar()
    par = p.dizi()
    eps = 1e-6
    k = -float(hk_f(eps, 0.0, *par)) / eps / float(Jk_f(0.0, *par))  # θ̈ = k θ
    return float(np.sqrt(k)) if k > 0 else 0.0


# ---------------------------------------------------------------------------
# Step motor: giriş teker ivmesi (motor konum kaynağı gibi davranır)
# ---------------------------------------------------------------------------
def ivme_katsayilari(p: ModelParametreleri) -> dict:
    """Tork denkleminden elenince kalan katsayılar: c1 ẍ + c2 θ̈ = m_b g l θ (θ = 0 civarı).

    Motor torku ve sürtünme iç kuvvet olduğundan düşer; J_m de sadeleşir. J_k = c2 + c1 r, teker
    gövdeye kilitliyken robotun zemin temas noktası etrafındaki ataletidir.
    """
    k = dogrusal_katsayilar(p)
    c1 = k["M_x"] * p.r + k["a12"]
    c2 = k["a12"] * p.r + k["a22"]
    return {"c1": c1, "c2": c2, "mgl": k["mgl"], "J_k": c2 + c1 * p.r}


def ivme_girisli_durum_uzay(p: ModelParametreleri):
    """Durum [x, ẋ, θ, θ̇], giriş a = ẍ [m/s²] (teker merkezi ivmesi). C = I, D = 0."""
    k = ivme_katsayilari(p)
    A = np.zeros((4, 4))
    A[0, 1] = A[2, 3] = 1.0
    A[3, 2] = k["mgl"] / k["c2"]
    B = np.array([[0.0], [1.0], [0.0], [-k["c1"] / k["c2"]]])
    return A, B, np.eye(4), np.zeros((4, 1))


def bagil_ivme_girisli_durum_uzay(p: ModelParametreleri):
    """Durum [x, ẋ, θ, θ̇], giriş α = ẍ/r − θ̈ [rad/s²]: step sürücüsünün doğrudan ürettiği, milin gövdeye göre ivmesi.

    α = 0, enerjili motorun adım atmadan durmasıdır: robot tek parça yuvarlanır (kutup = kilitli teker kutbu).
    """
    k = ivme_katsayilari(p)
    A = np.zeros((4, 4))
    A[0, 1] = A[2, 3] = 1.0
    A[3, 2] = k["mgl"] / k["J_k"]
    A[1, 2] = p.r * A[3, 2]
    b_th = -k["c1"] * p.r / k["J_k"]
    B = np.array([[0.0], [p.r * (1 + b_th)], [0.0], [b_th]])
    return A, B, np.eye(4), np.zeros((4, 1))


def ivme_girisli_kutup(p: ModelParametreleri) -> float:
    """a = 0 iken eğim kutbu [1/s]; tork girişli modeldeki X/U sıfırıyla aynıdır."""
    k = ivme_katsayilari(p)
    return math.sqrt(k["mgl"] / k["c2"]) if k["mgl"] > 0 else 0.0


def ivme_transfer_fonksiyonu(p: ModelParametreleri) -> dict:
    """Θ(s)/A(s) = −K_a / (s² − z²), X(s)/A(s) = 1/s²."""
    k = ivme_katsayilari(p)
    return {"K_a": k["c1"] / k["c2"], "z2": k["mgl"] / k["c2"]}


def _ivme_katsayilari_theta(p: ModelParametreleri, th):
    c = np.cos(th)
    c1 = (p.m_b + 2 * p.m_w) * p.r + 2 * p.J_w / p.r + p.m_b * p.l * c
    c2 = p.I_yy + p.m_b * p.l**2 + p.m_b * p.l * p.r * c
    return c1, c2


def ivme_girisli_dinamik(p: ModelParametreleri, durum, a: float) -> np.ndarray:
    """Doğrusal olmayan model (ψ̇ = 0): durum [x, ẋ, θ, θ̇], giriş a = ẍ."""
    _, xd, th, thd = durum
    c1, c2 = _ivme_katsayilari_theta(p, th)
    s = math.sin(th)
    thdd = (p.m_b * p.g * p.l * s + p.m_b * p.l * p.r * s * thd**2 - c1 * a) / c2
    return np.array([xd, a, thd, thdd])


def theta_yorungesinden_ivme(p: ModelParametreleri, th, thd, thdd):
    """θ(t) izlenecekse gereken teker ivmesi a(t) (doğrusal olmayan, cebirsel)."""
    c1, c2 = _ivme_katsayilari_theta(p, th)
    s = np.sin(th)
    return (p.m_b * p.g * p.l * s + p.m_b * p.l * p.r * s * thd**2 - c2 * thdd) / c1


def ivmeden_tork(p: ModelParametreleri, th, thd, thdd, a, xd):
    """Girişi a olan robotta motorların toplam torku u = τ_R + τ_L [N m]: çıktıdır, adım kaçırma kontrolüne gider."""
    k = dogrusal_katsayilar(p)
    a12 = p.m_b * p.l * np.cos(th) - 2 * p.J_m / p.r
    return p.r * (k["M_x"] * a + a12 * thdd - p.m_b * p.l * np.sin(th) * thd**2) + 2 * p.b * (xd / p.r - thd)


def _bastaki_sifirlari_at(c, tol=1e-9):
    c = np.atleast_1d(np.real_if_close(c)).astype(float)
    c[np.abs(c) < tol * np.max(np.abs(c))] = 0.0
    return np.trim_zeros(c, "f")


def _ortak_kokleri_sadelestir(pay, payda, tol=1e-6):
    pay, payda = _bastaki_sifirlari_at(pay), _bastaki_sifirlari_at(payda)
    kz, kp = list(np.roots(pay)), list(np.roots(payda))
    for z in list(kz):
        for i, pk in enumerate(kp):
            if abs(z - pk) < tol * max(1.0, abs(pk)):
                kz.remove(z)
                kp.pop(i)
                break
    kazanc = pay[0] / payda[0]
    return np.real(kazanc * np.poly(kz)), np.real(np.poly(kp))


def transfer_fonksiyonu(p: ModelParametreleri, cikis: str = "theta"):
    """Tek giriş u = τ_R + τ_L için transfer fonksiyonu (pay, payda), ortak kökler sadeleşmiş.

    cikis: 'theta' → Θ(s)/U(s), 'x' → X(s)/U(s).
    """
    A, B, C, D = durum_uzay(p)
    i = {"x": 0, "theta": 2}[cikis]
    pay, payda = signal.ss2tf(A, B, C[i : i + 1], D[i : i + 1])
    return _ortak_kokleri_sadelestir(pay[0], payda)


def transfer_fonksiyonu_analitik(p: ModelParametreleri) -> dict:
    """b = 0 için kapalı biçim: Θ/U = −K_θ/(s² − p²),  X/U = K_x (s² − z²)/(s² (s² − p²))."""
    k = dogrusal_katsayilar(p)
    return {
        "K_theta": (k["M_x"] * p.r + k["a12"]) / (p.r * k["Delta"]),
        "p2": k["M_x"] * k["mgl"] / k["Delta"],
        "K_x": (k["a22"] + k["a12"] * p.r) / (p.r * k["Delta"]),
        "z2": k["mgl"] / (k["a22"] + k["a12"] * p.r),
        "K_psi": p.d / (2 * p.r * k["J_psi"]),
    }


def ayriklastir(A, B, C, D, Ts: float):
    """Sıfırıncı derece tutucu (ZOH) ile ayrık zaman modeli (MPC / ayrık LQR için)."""
    Ad, Bd, Cd, Dd, _ = signal.cont2discrete((A, B, C, D), Ts, method="zoh")
    return Ad, Bd, Cd, Dd


def kontrol_edilebilirlik_rangi(A, B) -> int:
    n = A.shape[0]
    return int(np.linalg.matrix_rank(np.hstack([np.linalg.matrix_power(A, i) @ B for i in range(n)])))


def gozlenebilirlik_rangi(A, C) -> int:
    n = A.shape[0]
    return int(np.linalg.matrix_rank(np.vstack([C @ np.linalg.matrix_power(A, i) for i in range(n)])))


# ---------------------------------------------------------------------------
# Motor seçilince: gerilim girişli model
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MotorModeli:
    """Redüktörlü DC motorun teker milindeki eşdeğer sabitleri (endüktans ihmal)."""

    K_t: float  # tork sabiti [N m/A]
    K_e: float  # zıt EMK sabiti [V s/rad]
    R: float  # sargı direnci [Ω]


def gerilim_girisli_durum_uzay(p: ModelParametreleri, motor: MotorModeli):
    """İki motora aynı gerilim V uygulandığında eğim alt sistemi: giriş V [V].

    τ = (K_t/R)·V − (K_t K_e/R)·(teker bağıl hızı): zıt EMK viskoz sürtünmeye eklenir.
    """
    b_toplam = p.b + motor.K_t * motor.K_e / motor.R
    A, B, C, D = durum_uzay(p.degistir(b=b_toplam))
    return A, B * 2 * motor.K_t / motor.R, C, D
