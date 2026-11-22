"""3D ikiz (MuJoCo, belge §12.11): model 2D ile aynı kütle özelliklerinde, aynı kontrol kodu, senaryolar ve video."""

import math
import shutil
from dataclasses import replace

import numpy as np
import pytest

mujoco = pytest.importorskip("mujoco")

from denge import simulasyon as sim  # noqa: E402
from denge.ikiz import ayarlar, fizik, kestirim, kontrol, senaryolar as S, sensorler  # noqa: E402
from denge.ikiz3d import karsilastirma, kosucu, mjcf, video  # noqa: E402
from denge.kutle_merkezi import yere_degme_acilari  # noqa: E402


@pytest.fixture(scope="module")
def ay(tasarim):
    return ayarlar.ikiz_ayarlari(tasarim)


@pytest.fixture(scope="module")
def mot(tasarim, ay):
    return ayarlar.motorlar(tasarim, ay.J_rotor)["1000"]


def _model(tasarim, mot, ay, kutulu=True, theta0=0.0):
    m = mujoco.MjModel.from_xml_string(mjcf.mjcf(tasarim, mot, ay, kutulu, theta0))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    return m, d


@pytest.mark.parametrize("kutulu", [True, False])
def test_mjcf_kutle_km_ve_atalet_2d_modelle_ayni(tasarim, mot, ay, kutulu):
    """Kütleyi ve ataleti MuJoCo bileşen kutularından kendisi hesaplar; 2D modelin govde_ozellikleri ile aynı çıkmalı."""
    m, d = _model(tasarim, mot, ay, kutulu)
    M, km, I = mjcf.kutle_ozellikleri(m, d)
    g = tasarim.govde(kutulu=kutulu)
    assert M == pytest.approx(g.kutle, rel=1e-12)
    assert np.allclose(km, g.km, atol=1e-12)
    assert np.allclose(I, g.atalet, rtol=1e-9, atol=1e-15)
    toplam = sum(m.body_mass) - 2e-6  # iki rotor gövdesinin 1 mg'lık kütlesi
    assert toplam == pytest.approx(tasarim.toplam_kutle(kutulu=kutulu), rel=1e-9)


def test_teker_ataleti_ve_kutu_serbest_cisim(tasarim, mot, ay):
    m, d = _model(tasarim, mot, ay)
    r, m_w = tasarim.d("teker.yaricap"), tasarim.d("teker.kutle")
    J_w = tasarim.d("teker.atalet_katsayisi") * m_w * r**2
    it = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "teker_R")
    assert m.body_mass[it] == pytest.approx(m_w) and np.allclose(m.body_inertia[it], [J_w / 2, J_w, J_w / 2])
    ik = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "kutu")
    assert m.jnt_type[m.body_jntadr[ik]] == mujoco.mjtJoint.mjJNT_FREE  # vidalı değil
    assert m.body_parentid[ik] == 0  # gövdenin çocuğu değil, dünyaya bağlı serbest cisim
    # Yuva iç boşluğu: kutu ile ön duvar arası = yuk.yuva.bosluk
    on = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "yuva_on")
    kx = tasarim.d("yuk.kutu.boyut")[0]
    bosluk = m.geom_pos[on][0] - m.geom_size[on][0] - (tasarim.d("yuk.yuva.x") + kx / 2)
    assert bosluk == pytest.approx(tasarim.d("yuk.yuva.bosluk"))
    # Rotor: yansıyan atalet ve sürtünme
    jr = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, "rotor_R")
    assert m.dof_armature[m.jnt_dofadr[jr]] == pytest.approx(mot.J_m) and m.dof_frictionloss[m.jnt_dofadr[jr]] == pytest.approx(mot.tau_f)


def test_3d_ve_2d_ayni_motor_sensor_kestirici_kontrol_kodunu_kullanir():
    assert kosucu.motor_elektrigi is fizik.motor_elektrigi and kosucu.surucu_cikisi is fizik.surucu_cikisi
    assert kosucu.IMU is sensorler.IMU and kosucu.enkoder_sayimi is sensorler.enkoder_sayimi
    assert kosucu.KalmanSuzgeci is kestirim.KalmanSuzgeci and kosucu.DurumKestirici is kestirim.DurumKestirici
    assert kosucu.CikisKati is kontrol.CikisKati and kosucu.kontrolcu_olustur is kontrol.kontrolcu_olustur
    assert kosucu.degerlendir is S.degerlendir


def test_kontrolsuz_dusme_2d_yere_degme_acisina_yakin(tasarim, ay):
    """Kontrol ve dişli yok (teker serbest): gövde zemine 2D'nin geometrik yere değme açısına yakın açıda ve yakın sürede değer."""
    sifir = ay.degistir(kontrol=replace(ay.kontrol, lqr_K=(0.0,) * 5, ileri_besleme_acik=False, olu_bolge_telafisi=0.0))
    kay = kosucu.calistir3d(tasarim, "O1-4+", S.Kurulum(), sifir, sure=2.0, motor_bagli=False)
    assert kay.dustu
    yd = yere_degme_acilari(tasarim)
    assert math.degrees(kay.temas_aci) == pytest.approx(math.degrees(yd["ileri"]), abs=4.0)
    p = tasarim.model(kutulu=True)
    ref = sim.acik_cevrim_dusme(p, math.radians(10), yere_degme=(yd["ileri"], yd["geri"]))
    assert kay.t_dusme == pytest.approx(ref["t_degme"], rel=0.15)


def test_3d_toparlanma_gecer_ve_kutu_yuvada_kalir(tasarim, ay):
    kay = kosucu.calistir3d(tasarim, "O1-4-", S.Kurulum(pil="dolu"), ay)
    d = kosucu.degerlendir3d(kay, ay)
    assert d["gecti"], [a["neden"] for a in d["alt"]]
    assert d["kutu3d"]["cikti"] is None and d["kutu3d"]["kayma"] <= tasarim.d("yuk.yuva.bosluk") + 0.001
    assert any(k[0].startswith("Kutu yuvada kalır") for k in d["alt"][0]["kosullar"])


def test_3d_donus_varsayilanda_kisa_kalir_oneriyle_gecer(tasarim, ay):
    """§12.11'in ana bulgusu: geniş teker yerinde dönerken kayar; z jiroskobu + dönüş integrali farkı kapatır."""
    d0 = kosucu.degerlendir3d(kosucu.calistir3d(tasarim, "O2", S.Kurulum(), ay), ay)
    sol0 = next(a for a in d0["alt"] if a["ad"] == "Ö2 sol 90°")
    assert not sol0["gecti"] and float(sol0["deger"].rstrip("°")) < 80
    oneri = karsilastirma.oneri_ayarlari(ay)
    d1 = kosucu.degerlendir3d(kosucu.calistir3d(tasarim, "O2", S.Kurulum(), oneri), oneri)
    assert d1["gecti"], [a["neden"] for a in d1["alt"]]


def test_kutu_yuvadan_cikarsa_alt_test_kalir(tasarim, ay):
    kay = kosucu.calistir3d(tasarim, "O1-4+", S.Kurulum(), ay, sure=0.5)
    kay.gv["kutu3d"] = {"kayma": 0.05, "egim": 0.1, "cikti": 0.3}
    d = kosucu.degerlendir3d(kay, ay)
    assert not d["gecti"] and "yuvadan çıktı" in d["alt"][0]["neden"]


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg yok")
def test_video_yazilir(tasarim, mot, ay, tmp_path):
    kay = kosucu.calistir3d(tasarim, "O1-1", S.Kurulum(), ay, sure=0.4, video_fps=10)
    m, _ = _model(tasarim, mot, ay)
    yol = tmp_path / "v.mp4"
    n = video.mp4_yaz(yol, m, kay.kareler, "deneme", "kısa", "GEÇTİ", fps=10, genislik=320, yukseklik=180)
    assert n >= 4 and yol.stat().st_size > 1000
