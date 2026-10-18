import math

import numpy as np
import pytest

from denge import model, motor
from denge import simulasyon as sim


def test_rpm():
    r = 0.04
    assert motor.rpm(2 * math.pi * r, r) == pytest.approx(60.0)  # saniyede bir tur


def test_trapez_profil_mesafeyi_saglar():
    v, a = motor.trapez_profil(1.0, 4.0, 0.25)
    t_a = v / a
    assert v * (4.0 - t_a) == pytest.approx(1.0) and t_a == pytest.approx(1.0)


def test_el_hesabi_formulu(p):
    th0 = math.radians(10)
    el = motor.toparlanma_torku_el(p, th0, 0.5)
    assert el["statik"] == pytest.approx(p.m_b * p.g * p.l * math.sin(th0))
    assert el["dinamik"] == pytest.approx((p.I_yy + p.m_b * p.l**2) * 4 * th0 / 0.25)
    assert el["toplam"] == pytest.approx(el["statik"] + el["dinamik"])


def test_tutma_torku_dogrusal_olmayan_modelde_ivmeyi_sifirlar(p):
    th0 = math.radians(10)
    tau = motor.tutma_torku_tam(p, th0)
    turev = model.dinamik(p, [0, 0, th0, 0, 0, 0], tau / 2, tau / 2)
    assert abs(turev[3]) < 1e-10  # θ̈ = 0
    assert tau < p.m_b * p.g * p.l * math.sin(th0)  # el hesabının statik teriminden küçük


def test_tork_siralamasi(p):
    """tutma (tam) ≤ referans manevra tepe torku ≤ el hesabı."""
    th0 = math.radians(10)
    ref = sim.referans_toparlanma(p, th0, 2.0)
    tepe = np.max(np.abs(ref["dogrusal_olmayan"]["u"]))
    assert motor.tutma_torku_tam(p, th0) <= tepe <= motor.toparlanma_torku_el(p, th0, 0.5)["toplam"]


def test_uzun_manevrada_tepe_tork_tutma_torkuna_yaklasir(p):
    th0 = math.radians(10)
    tar = sim.toparlanma_taramasi(p, th0, [1.0, 2.0, 4.0, 8.0])
    assert np.all(np.diff(tar["u_dogrusal"]) < 0)
    assert tar["u_dogrusal"][-1] == pytest.approx(motor.tutma_torku_tam(p, th0), rel=0.05)


def test_min_durma_torku():
    noktalar = [(100.0, 0.3), (150.0, 0.05)]
    n0 = np.array([90.0, 160.0, 200.0, 400.0])
    ts = motor.min_durma_torku(n0, noktalar)
    assert np.isinf(ts[0])
    assert ts[2] == pytest.approx(max(0.3 / (1 - 100 / 200), 0.05 / (1 - 150 / 200)))
    assert np.all(np.diff(ts[1:]) < 0)
    # Sınırdaki motorun doğrusal eğrisi en az bir noktaya teğet, hiçbirinin altında değil
    for n0_i, ts_i in zip(n0[1:], ts[1:]):
        bosluk = [ts_i * (1 - n / n0_i) - t for n, t in noktalar]
        assert min(bosluk) == pytest.approx(0.0, abs=1e-12)


def test_motor_adayi_degerlendirme(tasarim):
    gerek = motor.gereksinimleri_hesapla(tasarim)
    V = tasarim.batarya_gerilimleri()
    # Test için yapay adaylar (gerçek ürün değil)
    guclu = motor.MotorAdayi("güçlü", 12.0, 400.0, 1.5, 4.0, 0.2, 30, 11)
    zayif = motor.MotorAdayi("zayıf", 12.0, 100.0, 0.1, 1.0, 0.1, 30, 3)
    s_guclu = {s["olcut"]: s["sonuc"] for s in motor.degerlendir(guclu, gerek, V)}
    s_zayif = {s["olcut"]: s["sonuc"] for s in motor.degerlendir(zayif, gerek, V)}
    assert all(v for k, v in s_guclu.items() if v is not None)
    assert not any(v for k, v in s_zayif.items() if v is not None and "gerilim" not in k)


def test_veri_sayfasindan_motor_modeli():
    a = motor.MotorAdayi("x", 12.0, 300.0, 0.8, 3.0, 0.2)
    m = a.motor_modeli()
    w0 = 300 * 2 * math.pi / 60
    assert m.K_t * (a.durma_akimi - a.bosta_akim) == pytest.approx(0.8)  # durma torku geri bulunur
    assert a.bosta_akim * m.R + m.K_e * w0 == pytest.approx(12.0)  # boşta gerilim dengesi


def test_enkoder_gereksinimi():
    e = motor.enkoder_gereksinimi(r=0.04, d=0.2, dv_hedef=0.02, pencere=0.01, n_max=120)
    assert e["cpr_min"] == pytest.approx(2 * math.pi * 0.04 / 0.0002)
    satir = motor.enkoder_tablosu(0.04, 0.2, 0.01, 120, [11], [30])[0]
    assert satir["cpr_teker"] == 4 * 11 * 30
    assert satir["dv"] == pytest.approx(2 * math.pi * 0.04 / 1320 / 0.01)
