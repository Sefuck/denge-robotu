import math

import numpy as np
import pytest
import sympy as sp

from denge import model


def test_sembolik_turetim_el_ile_yazilan_denklemlerle_ayni():
    D = model.turet()
    for turetilen, el in zip(D["denklemler"], model.el_ile_yazilmis_denklemler()):
        assert sp.simplify(sp.expand(turetilen - el)) == 0


@pytest.mark.parametrize("durum", ["p", "p_kutusuz"])
def test_en_az_bir_kutup_sag_yari_duzlemde(durum, request):
    p = request.getfixturevalue(durum)
    kutuplar = model.kutuplar(p)["egim"]
    assert np.sum(kutuplar.real > 1e-6) >= 1
    assert model.kararsiz_kutup(p) > 0


def test_kutup_yapisi(p):
    """b = 0: eğimde ±p ve iki sıfır kutup (x, ẋ çift integratör), sapmada iki sıfır kutup."""
    k = np.sort_complex(model.kutuplar(p)["egim"])
    p_k = math.sqrt(model.transfer_fonksiyonu_analitik(p)["p2"])
    assert np.allclose(k, [-p_k, 0, 0, p_k], atol=1e-6)
    assert np.allclose(model.kutuplar(p)["donus"], 0)


def _sayisal_jakobiyen(f, x0, eps=1e-7):
    x0 = np.asarray(x0, float)
    return np.column_stack([(f(x0 + eps * e) - f(x0 - eps * e)) / (2 * eps) for e in np.eye(len(x0))])


@pytest.mark.parametrize("b, J_m", [(0.0, 0.0), (0.01, 1e-3)])
def test_dogrusallastirma_dogrusal_olmayan_modelin_jakobiyeni(p, b, J_m):
    p = p.degistir(b=b, J_m=J_m)
    A, B, _, _ = model.durum_uzay(p)
    Ap, Bp, _, _ = model.donus_durum_uzay(p)
    f = lambda s: model.dinamik(p, s)
    J = _sayisal_jakobiyen(f, np.zeros(6))
    i = [0, 1, 2, 3]
    assert np.allclose(J[np.ix_(i, i)], A, rtol=1e-5, atol=1e-6)
    assert np.allclose(J[np.ix_([4, 5], [4, 5])], Ap, rtol=1e-5, atol=1e-6)
    # Doğrusallaştırılmış modelde eğim ve sapma ayrışır
    assert np.allclose(J[np.ix_(i, [4, 5])], 0, atol=1e-6) and np.allclose(J[np.ix_([4, 5], i)], 0, atol=1e-6)
    Ju = _sayisal_jakobiyen(lambda u: model.dinamik(p, np.zeros(6), u[0] / 2 + u[1] / 2, u[0] / 2 - u[1] / 2), [0.0, 0.0])
    assert np.allclose(Ju[i, 0], B[:, 0], rtol=1e-5)  # u = τ_R + τ_L
    assert np.allclose(Ju[[4, 5], 1], Bp[:, 0], rtol=1e-5)  # u_ψ = τ_R − τ_L


def test_transfer_fonksiyonlari_analitik_formla_ayni(p):
    a = model.transfer_fonksiyonu_analitik(p)
    pay, payda = model.transfer_fonksiyonu(p, "theta")
    assert np.allclose(pay, [-a["K_theta"]], rtol=1e-8)
    assert np.allclose(payda, [1, 0, -a["p2"]], rtol=1e-8, atol=1e-8)
    pay_x, payda_x = model.transfer_fonksiyonu(p, "x")
    assert np.allclose(pay_x, a["K_x"] * np.array([1, 0, -a["z2"]]), rtol=1e-6, atol=1e-6)
    assert np.allclose(payda_x, [1, 0, -a["p2"], 0, 0], rtol=1e-8, atol=1e-6)


def test_x_u_transfer_fonksiyonunda_sag_yari_duzlem_sifiri(p):
    """Minimum fazlı olmayan sıfır: ileri gitmek için teker önce geri kaçar; 0 < z < p."""
    a = model.transfer_fonksiyonu_analitik(p)
    assert 0 < a["z2"] < a["p2"]


def test_theta_u_kazanci_negatif(p):
    """İleri tork (u > 0) gövdeye ters tepki uygular: θ̈ < 0."""
    _, B, _, _ = model.durum_uzay(p)
    assert B[3, 0] < 0 < B[1, 0]


def test_kontrol_edilebilirlik_ve_gozlenebilirlik(p):
    A, B, _, _ = model.durum_uzay(p)
    assert model.kontrol_edilebilirlik_rangi(A, B) == 4
    C_enkoder_imu = np.array([[1, 0, 0, 0], [0, 0, 1, 0]])
    assert model.gozlenebilirlik_rangi(A, C_enkoder_imu) == 4
    # Yalnız θ ölçülürse konum ve hız gözlenemez: enkoder şart
    assert model.gozlenebilirlik_rangi(A, np.array([[0, 0, 1, 0]])) < 4
    Ap, Bp, _, _ = model.donus_durum_uzay(p)
    assert model.kontrol_edilebilirlik_rangi(Ap, Bp) == 2


def test_ayrik_model_ozdegerleri(p):
    Ts = 0.005
    A, B, C, D = model.durum_uzay(p)
    Ad, *_ = model.ayriklastir(A, B, C, D, Ts)
    assert np.allclose(np.sort(np.abs(np.linalg.eigvals(Ad))), np.sort(np.abs(np.exp(np.linalg.eigvals(A) * Ts))))


def test_gerilim_girisli_model_zit_emk_sonumu(p):
    motor = model.MotorModeli(K_t=0.25, K_e=0.3, R=4.0)  # test için yapay değerler
    A_V, B_V, _, _ = model.gerilim_girisli_durum_uzay(p, motor)
    A_t, B_t, _, _ = model.durum_uzay(p.degistir(b=motor.K_t * motor.K_e / motor.R))
    assert np.allclose(A_V, A_t) and np.allclose(B_V, B_t * 2 * motor.K_t / motor.R)
    # Sönüm kararsız kutbu yavaşlatır ama sistem kararsız kalır
    p_V = np.max(np.linalg.eigvals(A_V).real)
    assert 0 < p_V < model.kararsiz_kutup(p)


def test_kilitli_teker_kutbu_kapali_bicim(p):
    J = p.I_yy + 2 * p.J_w + p.m_b * (p.l + p.r) ** 2 + 2 * p.m_w * p.r**2
    assert model.kilitli_kutup(p) == pytest.approx(math.sqrt(p.m_b * p.g * p.l / J), rel=1e-5)
