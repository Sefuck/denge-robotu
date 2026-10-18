"""Birim tutarlılığı: formüller pint büyüklükleriyle yeniden hesaplanır, boyut ve değer karşılaştırılır."""

import math

import pint
import pytest

from denge import model, motor

u = pint.UnitRegistry()


@pytest.fixture(scope="module")
def p_birimli(p):
    """Nominal parametrelerin birimli kopyası (yalnız aritmetik kullanan fonksiyonlar için)."""
    birimler = dict(m_b="kg", l="m", I_xx="kg*m^2", I_yy="kg*m^2", I_zz="kg*m^2", m_w="kg", J_w="kg*m^2",
                    K_w="kg*m^2", r="m", d="m", J_m="kg*m^2", b="N*m*s", g="m/s^2")
    return model.ModelParametreleri(**{ad: getattr(p, ad) * u(b) for ad, b in birimler.items()})


def _ayni(birimli, sayi, birim):
    assert birimli.check(u(birim).dimensionality), f"{birimli.units} ≠ {birim}"
    assert birimli.to(birim).magnitude == pytest.approx(sayi, rel=1e-12)


def test_dogrusal_model_katsayilarinin_birimleri(p, p_birimli):
    a, ab = model.transfer_fonksiyonu_analitik(p), model.transfer_fonksiyonu_analitik(p_birimli)
    _ayni(ab["p2"], a["p2"], "1/s^2")  # kutup²
    _ayni(ab["z2"], a["z2"], "1/s^2")
    _ayni(ab["K_theta"], a["K_theta"], "1/(kg*m^2)")  # (rad/s²)/(N·m)
    _ayni(ab["K_x"], a["K_x"], "1/(kg*m)")  # X/U [m/(N·m)] = K_x·s²/(s²(s²−p²))… → K_x [1/(kg·m)]
    _ayni(ab["K_psi"], a["K_psi"], "1/(kg*m^2)")


def test_tork_formullerinin_birimleri(p, p_birimli):
    th0 = math.radians(10)
    el, elb = motor.toparlanma_torku_el(p, th0, 0.5), motor.toparlanma_torku_el(p_birimli, th0, 0.5 * u.s)
    for k in ("statik", "dinamik", "toplam"):
        _ayni(elb[k], el[k], "N*m")
    _ayni(motor.tutma_torku_tam(p_birimli, th0), motor.tutma_torku_tam(p, th0), "N*m")
    _ayni(motor.cekis_siniri(p_birimli, 0.7, 1.5 * u.kg), motor.cekis_siniri(p, 0.7, 1.5), "N*m")


def test_kutup_ve_devir_birimleri(p):
    l, g, r = p.l * u.m, p.g * u("m/s^2"), p.r * u.m
    _ayni((g / l) ** 0.5, math.sqrt(p.g / p.l), "1/s")
    v = 0.5 * u("m/s")
    assert (v / r).to("rpm").magnitude == pytest.approx(motor.rpm(0.5, p.r))


def test_kgfcm_donusumu():
    assert (1 * u.kgf * u.cm).to("N*m").magnitude == pytest.approx(motor.KGFCM)


def test_enkoder_birimleri():
    r, dv, T = 0.04 * u.m, 0.02 * u("m/s"), 0.01 * u.s
    cpr = (2 * math.pi * r / (dv * T)).to("dimensionless")
    assert cpr.magnitude == pytest.approx(motor.enkoder_gereksinimi(0.04, 0.2, 0.02, 0.01, 100)["cpr_min"])
