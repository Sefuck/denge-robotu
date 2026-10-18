import math

import numpy as np
import pytest

from denge import kutle_merkezi as km
from denge import model
from denge import simulasyon as sim


@pytest.fixture(scope="module")
def temas(tasarim):
    t = km.yere_degme_acilari(tasarim)
    return t["ileri"], t["geri"]


def test_enerji_korunur(p, temas):
    """u = 0, b = 0: Lagrange modelinin toplam enerjisi düşme boyunca sabit."""
    s = sim.acik_cevrim_dusme(p, math.radians(10), yere_degme=temas)
    E = np.array([model.enerji(p, s["durum"][:, i]) for i in range(0, s["durum"].shape[1], 50)])
    assert np.ptp(E) / abs(E[0]) < 1e-8


@pytest.mark.parametrize("mod", ["serbest", "kilitli"])
def test_arti_eksi_10_derece_dusmeleri_simetrik(p, temas, mod):
    a = sim.acik_cevrim_dusme(p, math.radians(10), mod=mod, yere_degme=temas)
    b = sim.acik_cevrim_dusme(p, math.radians(-10), mod=mod, yere_degme=temas)
    assert a["t_degme"] == pytest.approx(b["t_degme"], rel=1e-6)
    assert np.allclose(a["theta"], -b["theta"], atol=1e-8)


@pytest.mark.parametrize("mod", ["serbest", "kilitli"])
def test_pasif_kararlilik_on_testi_saglanir(p, temas, mod, tasarim):
    """Şartname §4.1: enerjisizken ±10°'den bırakılan robot 5 s içinde dik konuma dönmemeli."""
    for isaret in (+1, -1):
        s = sim.acik_cevrim_dusme(p, isaret * math.radians(10), mod=mod, yere_degme=temas, t_son=5.0)
        assert s["t_degme"] is not None and s["t_degme"] < tasarim.d("sartname.pasif_test_suresi")
        assert np.all(isaret * s["theta"] >= math.radians(10) - 1e-9)  # dikliğe hiç yaklaşmaz


def test_km_aks_altindaysa_robot_pasif_kararli_olur(p):
    """KM aksın altına inerse kararsız kutup kaybolur: şartname §4.1 ihlali yakalanır."""
    p_alt = p.degistir(l=-0.02)
    assert model.kararsiz_kutup(p_alt) <= 1e-9
    s = sim.acik_cevrim_dusme(p_alt, math.radians(10), t_son=5.0)
    assert s["t_degme"] is None and np.max(np.abs(s["theta"])) <= math.radians(10) + 1e-6


def test_kucuk_acida_dogrusal_model_ile_ortusur(p):
    th0 = math.radians(0.5)
    s = sim.acik_cevrim_dusme(p, th0, t_son=0.2)  # θ ≈ 2°'de kalır
    A, *_ = model.durum_uzay(p)
    lin = sim.dogrusal_serbest_yanit(A, [0, 0, th0, 0], s["t"])
    assert np.allclose(s["theta"], lin[:, 2], rtol=2e-3, atol=1e-7)
    assert np.allclose(s["x"], lin[:, 0], rtol=5e-3, atol=1e-7)


def test_duz_cikis_yorungesi_dogrusal_denklemleri_saglar(p):
    pb = p.degistir(b=0.01, J_m=5e-4)
    y = sim.referans_toparlanma(pb, math.radians(10), 2.0)
    k = model.dogrusal_katsayilar(pb)
    kayma = y["xd"] / pb.r - y["theta_d"]
    e1 = k["M_x"] * y["xdd"] + k["a12"] * y["theta_dd"] - y["u"] / pb.r + 2 * pb.b / pb.r * kayma
    e2 = k["a12"] * y["xdd"] + k["a22"] * y["theta_dd"] - k["mgl"] * y["theta"] + y["u"] - 2 * pb.b * kayma
    assert np.max(np.abs(e1)) < 1e-9 and np.max(np.abs(e2)) < 1e-9


def test_toparlanma_manevrasi_uc_kosullari(p):
    th0, T = math.radians(10), 2.0
    y = sim.referans_toparlanma(p, th0, T)
    assert y["theta"][0] == pytest.approx(th0) and abs(y["theta"][-1]) < 1e-9
    assert abs(y["theta_d"][0]) < 1e-9 and abs(y["xd"][0]) < 1e-9 and abs(y["xd"][-1]) < 1e-9
    assert y["x_f"] > 0  # ileri eğik gövdenin altına girmek için ileri gider
    assert abs(y["dogrusal_olmayan"]["xd"][-1]) < 0.01  # doğrusal olmayan modelde de neredeyse durur


def test_kucuk_acida_ters_dinamik_dogrusal_torka_esit(p):
    y = sim.referans_toparlanma(p, math.radians(0.5), 2.0)
    assert np.allclose(y["dogrusal_olmayan"]["u"], y["u"], rtol=1e-3, atol=1e-6)


def test_oteleme_hedef_mesafeye_varir_ve_once_geri_kacar(p):
    y = sim.referans_oteleme(p, 1.0, 4.0)
    assert y["x"][-1] == pytest.approx(1.0) and y["dogrusal_olmayan"]["x"][-1] == pytest.approx(1.0, abs=5e-3)
    assert y["x"].min() < 0  # minimum fazlı olmayan sıfırın imzası


def test_ozgul_kuvvet_vurus_merkezi_ozdesligi(p):
    """f_x = (z − z_cp)·θ̈ − τ/(m_b l) (b = 0, J_m = 0) doğrusal olmayan yörüngede sağlanır."""
    y = sim.referans_toparlanma(p, math.radians(10), 2.0)
    nl = y["dogrusal_olmayan"]
    xdd = np.gradient(nl["xd"], y["t"])
    z = 0.2
    fx, _ = km.ozgul_kuvvet(xdd, y["theta"], y["theta_d"], y["theta_dd"], 0.0, z, p.g)
    beklenen = (z - km.vurus_merkezi(p)) * y["theta_dd"] - nl["u"] / (p.m_b * p.l)
    assert np.allclose(fx[5:-5], beklenen[5:-5], atol=2e-3)
