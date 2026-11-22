"""parametreler.toml → MuJoCo modeli (MJCF).

Kütle ve atalet, 2D modelle aynı bileşen kutularından gelir: her bileşen (motor, şasi, elektronik, batarya, acil
durdurma, IR + şarj kontakları, kutu yuvası) görünmez, çarpışmasız, kütleli bir kutu geometrisidir; kütle merkezini ve
atalet tensörünü MuJoCo kendisi hesaplar (testte 2D modelle karşılaştırılır). Görünen parçalar (pleksi katlar,
aralayıcılar, motor gövdeleri, pil, kart, acil durdurma) kütlesizdir. Tekerin ataleti 2D modeldeki gibi verilir
(dönme ekseni J_w = k m r², çap ekseni J_w/2).

Gövde serbest cisimdir (6 serbestlik); tekerler ve rotorlar gövdeye menteşeyle bağlıdır. Rotorun ataleti teker miline
yansıtılmış J_m'dir (MuJoCo "armature"), sürtünmesi K_t·I_0'dır (MuJoCo "frictionloss": kuru sürtünme kısıtı). Rotor
ile teker arasındaki dişli boşluklu bir yaydır; torku kontrol döngüsü uygular (kosucu.py). İlaç kutusu vidalı değildir:
yuvada serbest bir cisimdir, kayabilir ve devrilebilir.

Çarpışma grupları: zemin (contype 1, conaffinity 1), robot (2, 1: yalnız zemine ve kutuya), kutu (4, 3: robota ve zemine).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..ikiz.fizik import Motor

ZEMIN, ROBOT, KUTU = (1, 1), (2, 1), (4, 3)
PLAKA_KALINLIGI = 0.003  # 3 mm pleksi (ön liste)


def _f(x: float) -> str:
    return f"{x:.7g}"


def _v(*xs) -> str:
    return " ".join(_f(x) for x in xs)


@dataclass(frozen=True)
class Geometri:
    """Görsel ve çarpışma geometrisi için parametre dosyasından okunan ölçüler."""

    r: float
    iz: float
    teker_genislik: float
    x_aralik: tuple[float, float]
    z_aralik: tuple[float, float]
    plaka_y: float
    katlar: tuple[float, float, float]  # plakaların üst yüzey yükseklikleri
    yuva_taban: float
    yuva_x: float
    duvar: float
    bosluk: float
    kutu: tuple[float, float, float]


def geometri(t) -> Geometri:
    (x0, x1), (z0, z1) = t.d("govde.zarf.x_aralik"), t.d("govde.zarf.z_aralik")
    katlar = (t.d("yuk.yuva.secenek.alt"), t.d("yuk.yuva.secenek.orta"), t.d("yuk.yuva.secenek.ust"))
    return Geometri(t.d("teker.yaricap"), t.d("teker.iz_genisligi"), t.d("teker.genislik"), (x0, x1), (z0, z1),
                    t.d("govde.sasi.boyut")[1], katlar, t.kutu_merkez_z() - t.d("yuk.kutu.boyut")[2] / 2, t.d("yuk.yuva.x"),
                    t.d("yuk.yuva.duvar_yuksekligi"), t.d("yuk.yuva.bosluk"), tuple(t.d("yuk.kutu.boyut")))


def bakis_xyaxes(konum, hedef) -> str:
    """Sabit kameranın x ve y eksenleri (MJCF xyaxes): `konum`dan `hedef`e bakar, zemin yatay kalır."""
    ileri = [h - k for h, k in zip(hedef, konum)]
    n = math.sqrt(sum(a * a for a in ileri))
    ileri = [a / n for a in ileri]
    x = [ileri[1], -ileri[0], 0.0]  # sağ = ileri × yukarı (yatay)
    nx = math.hypot(x[0], x[1])
    x = [a / nx for a in x]
    zc = [-a for a in ileri]  # kamera −z yönüne bakar
    y = [zc[1] * x[2] - zc[2] * x[1], zc[2] * x[0] - zc[0] * x[2], zc[0] * x[1] - zc[1] * x[0]]  # y = z × x
    return _v(*x, *y)


def mjcf(t, motor: Motor, ay, kutulu: bool = True, theta0: float = 0.0, motor_bagli: bool = True) -> str:
    """MJCF metni. theta0: gövdenin başlangıç (fiziksel) eğimi [rad]; kutu da gövdeyle birlikte döndürülerek yerleştirilir."""
    g = geometri(t)
    r, m_w = g.r, t.d("teker.kutle")
    J_w = t.d("teker.atalet_katsayisi") * m_w * r**2
    mu, mu_k = t.d("zemin.surtunme"), t.d("yuk.kutu.surtunme")
    temas = t.d("ikiz.teker_temas_genisligi")  # çarpışma silindirinin genişliği (görünen teker tam genişlikte)
    dt = t.d("simulasyon.adim_3d")
    solref = f"{_f(t.d('simulasyon.temas_zaman_sabiti'))} 1"
    q = (math.cos(theta0 / 2), 0.0, math.sin(theta0 / 2), 0.0)
    c, s = math.cos(theta0), math.sin(theta0)

    kutle = []
    for b in t.bilesenler(kutulu=False):  # kutu ayrı serbest cisim
        dx, dy, dz = b.boyut
        kutle.append(f'<geom class="kutle" name="kutle_{len(kutle)}" type="box" size="{_v(dx / 2, dy / 2, dz / 2)}" '
                     f'pos="{_v(*b.konum)}" mass="{_f(b.kutle)}"/>')

    # Görünür (kütlesiz) parçalar; plakalar, acil durdurma ve IR modülü aynı zamanda zemine çarpışma geometrisidir
    (x0, x1) = g.x_aralik
    hx, hy, ht = (x1 - x0) / 2, g.plaka_y / 2, PLAKA_KALINLIGI / 2
    gorsel = []
    for i, z_ust in enumerate(g.katlar):
        surt = mu_k if i == 2 else mu
        gorsel.append(f'<geom class="carpisma" name="plaka_{i}" type="box" size="{_v(hx, hy, ht)}" pos="{_v((x0 + x1) / 2, 0, z_ust - ht)}" '
                      f'material="pleksi" friction="{_f(surt)} 0.005 0.0001"/>')
    for x in (x0 + 0.006, x1 - 0.006):
        for y in (-hy + 0.006, hy - 0.006):
            for z_alt, z_ust in ((g.katlar[0], g.katlar[1] - PLAKA_KALINLIGI), (g.katlar[1], g.katlar[2] - PLAKA_KALINLIGI)):
                gorsel.append(f'<geom class="gorsel" type="cylinder" size="0.0025 {_f((z_ust - z_alt) / 2)}" pos="{_v(x, y, (z_alt + z_ust) / 2)}" material="metal"/>')
    mx, my, _ = t.d("govde.motor.konum")
    md = t.d("govde.motor.boyut")
    for isaret in (1, -1):
        gorsel.append(f'<geom class="gorsel" type="cylinder" size="{_v(md[0] / 2, md[1] / 2 - 0.004)}" pos="{_v(mx, isaret * my, 0)}" '
                      f'euler="1.5708 0 0" material="motor"/>')
        gorsel.append(f'<geom class="gorsel" type="box" size="0.02 0.0008 0.024" pos="{_v(0, isaret * (my - md[1] / 2 + 0.002), g.katlar[0] - 0.024 - PLAKA_KALINLIGI)}" material="metal"/>')
    for ad, mat in (("batarya", "pil"), ("elektronik", "pcb")):
        bx, by, bz = t.d(f"govde.{ad}.konum")
        bdx, bdy, bdz = t.d(f"govde.{ad}.boyut")
        gorsel.append(f'<geom class="gorsel" type="box" size="{_v(bdx / 2, bdy / 2, bdz / 2)}" pos="{_v(bx, by, bz)}" material="{mat}"/>')
    ax, ay_, az = t.d("govde.acil_durdurma.konum")
    gorsel.append(f'<geom class="carpisma" name="acil_durdurma" type="cylinder" size="0.012 0.012" pos="{_v(ax, ay_, az)}" material="kirmizi"/>')
    gorsel.append(f'<geom class="gorsel" type="cylinder" size="0.016 0.003" pos="{_v(ax, ay_, az - 0.013)}" material="sari"/>')
    ix, iy, iz = t.d("govde.ir_ve_sarj_kontaklari.konum")
    idx, idy, idz = t.d("govde.ir_ve_sarj_kontaklari.boyut")
    gorsel.append(f'<geom class="carpisma" name="ir_modulu" type="box" size="{_v(idx / 2, idy / 2, idz / 2)}" pos="{_v(ix, iy, iz)}" material="koyu"/>')

    # Kutu yuvası: duvarlar (kütlesiz; yuvanın kütlesi kütle kutularında)
    kx, ky, kz = g.kutu
    ic_x, ic_y = kx / 2 + g.bosluk, ky / 2 + g.bosluk
    kal = 0.0015
    zc = g.yuva_taban + g.duvar / 2
    for ad, (px, py, sx, sy) in {"on": (g.yuva_x + ic_x + kal, 0, kal, ic_y + 2 * kal), "arka": (g.yuva_x - ic_x - kal, 0, kal, ic_y + 2 * kal),
                                 "sol": (g.yuva_x, ic_y + kal, ic_x, kal), "sag": (g.yuva_x, -ic_y - kal, ic_x, kal)}.items():
        gorsel.append(f'<geom class="carpisma" name="yuva_{ad}" type="box" size="{_v(sx, sy, g.duvar / 2)}" pos="{_v(px, py, zc)}" '
                      f'material="yuva" friction="{_f(mu_k)} 0.005 0.0001"/>')

    tekerler = []
    for ad, y in (("R", -g.iz / 2), ("L", g.iz / 2)):
        tekerler.append(f'''
      <body name="teker_{ad}" pos="{_v(0, y, 0)}">
        <joint name="teker_{ad}" type="hinge" axis="0 1 0" damping="{_f(t.d('motor.viskoz_surtunme'))}"/>
        <inertial pos="0 0 0" mass="{_f(m_w)}" diaginertia="{_v(J_w / 2, J_w, J_w / 2)}"/>
        <geom name="teker_{ad}" class="teker" type="cylinder" size="{_v(r, temas / 2)}" euler="1.5708 0 0" rgba="0 0 0 0"/>
        <geom class="gorsel" type="cylinder" size="{_v(r, g.teker_genislik / 2)}" euler="1.5708 0 0" material="lastik"/>
        <geom class="gorsel" type="cylinder" size="{_v(0.6 * r, g.teker_genislik / 2 + 0.0005)}" euler="1.5708 0 0" material="jant"/>
        <geom class="gorsel" type="box" size="{_v(0.55 * r, g.teker_genislik / 2 + 0.001, 0.003)}" material="koyu"/>
      </body>
      <body name="rotor_{ad}" pos="{_v(0, y, 0)}">
        <joint name="rotor_{ad}" type="hinge" axis="0 1 0" armature="{_f(motor.J_m)}" frictionloss="{_f(motor.tau_f)}"/>
        <inertial pos="0 0 0" mass="1e-6" diaginertia="1e-12 1e-12 1e-12"/>
      </body>''')

    kutu_xml = ""
    if kutulu:
        bx, bz = g.yuva_x, t.kutu_merkez_z()
        kutu_xml = f'''
    <body name="kutu" pos="{_v(c * bx + s * bz, 0, r - s * bx + c * bz)}" quat="{_v(*q)}">
      <freejoint name="kutu"/>
      <geom name="kutu" type="box" size="{_v(kx / 2, ky / 2, kz / 2)}" mass="{_f(t.d('yuk.kutu.kutle'))}" material="kutu"
            contype="{KUTU[0]}" conaffinity="{KUTU[1]}" friction="{_f(mu_k)} 0.005 0.0001"/>
      <geom class="gorsel" type="box" size="{_v(kx / 2 + 0.0002, ky / 4, kz / 2 + 0.0002)}" material="kirmizi"/>
    </body>'''

    ex, ez = t.d("imu.konum")
    yan = bakis_xyaxes((0.45, -1.7, 0.32), (0.45, 0.0, 0.12))
    capraz = bakis_xyaxes((1.45, -1.25, 0.85), (0.35, 0.15, 0.08))
    return f'''<mujoco model="denge_robotu">
  <compiler angle="radian" autolimits="true"/>
  <option timestep="{_f(dt)}" integrator="implicitfast" cone="elliptic" impratio="{_f(t.d('simulasyon.impratio'))}" gravity="0 0 {_f(-t.d('sabit.g'))}"/>
  <visual>
    <global offwidth="1920" offheight="1080"/>
    <quality shadowsize="4096"/>
    <headlight ambient="0.38 0.38 0.38" diffuse="0.35 0.35 0.35" specular="0.05 0.05 0.05"/>
  </visual>
  <asset>
    <texture name="gok" type="skybox" builtin="gradient" rgb1="0.93 0.94 0.96" rgb2="0.72 0.76 0.82" width="256" height="256"/>
    <texture name="zemin" type="2d" builtin="checker" rgb1="0.86 0.85 0.82" rgb2="0.78 0.77 0.74" width="512" height="512" mark="edge" markrgb="0.7 0.69 0.66"/>
    <material name="zemin" texture="zemin" texrepeat="10 10" reflectance="0.02" specular="0.1"/>
    <material name="pleksi" rgba="0.75 0.88 0.98 0.45" specular="0.6" shininess="0.8"/>
    <material name="metal" rgba="0.72 0.72 0.75 1" specular="0.7"/>
    <material name="motor" rgba="0.25 0.27 0.30 1" specular="0.5"/>
    <material name="lastik" rgba="0.08 0.08 0.08 1"/>
    <material name="jant" rgba="0.95 0.75 0.10 1"/>
    <material name="koyu" rgba="0.15 0.15 0.18 1"/>
    <material name="pil" rgba="0.16 0.42 0.80 1"/>
    <material name="pcb" rgba="0.10 0.55 0.30 1"/>
    <material name="kirmizi" rgba="0.85 0.12 0.10 1"/>
    <material name="sari" rgba="0.98 0.80 0.10 1"/>
    <material name="yuva" rgba="0.92 0.92 0.95 0.75"/>
    <material name="kutu" rgba="0.97 0.97 0.97 1"/>
  </asset>
  <default>
    <geom solref="{solref}" solimp="0.95 0.99 0.001"/>
    <default class="kutle"><geom contype="0" conaffinity="0" group="3" rgba="0 0 0 0"/></default>
    <default class="gorsel"><geom contype="0" conaffinity="0" group="1" mass="0"/></default>
    <default class="carpisma"><geom contype="{ROBOT[0]}" conaffinity="{ROBOT[1]}" group="1" mass="0" friction="{_f(mu)} 0.005 0.0001"/></default>
    <default class="teker"><geom contype="{ROBOT[0]}" conaffinity="{ROBOT[1]}" mass="0" material="lastik" friction="{_f(mu)} 0.005 0.0001"/></default>
  </default>
  <worldbody>
    <light name="isik" pos="0.6 -0.6 2.2" dir="-0.2 0.25 -1" diffuse="0.6 0.6 0.6" specular="0.1 0.1 0.1" castshadow="true"/>
    <geom name="zemin" type="plane" size="5 5 0.1" material="zemin" contype="{ZEMIN[0]}" conaffinity="{ZEMIN[1]}" friction="{_f(mu)} 0.005 0.0001"/>
    <camera name="yan" pos="0.45 -1.7 0.32" xyaxes="{yan}"/>
    <camera name="capraz" pos="1.45 -1.25 0.85" xyaxes="{capraz}"/>
    <body name="govde" pos="0 0 {_f(r)}" quat="{_v(*q)}">
      <freejoint name="kok"/>
      <site name="imu" pos="{_v(ex, 0, ez)}" size="0.004" rgba="1 0 1 1" group="4"/>
      <site name="kutu_noktasi" pos="{_v(g.yuva_x, 0, t.kutu_merkez_z())}" size="0.004" rgba="1 0.5 0 1" group="4"/>
      {chr(10).join("      " + k for k in kutle).strip()}
      {chr(10).join("      " + k for k in gorsel).strip()}{"".join(tekerler)}
    </body>{kutu_xml}
  </worldbody>
  <sensor>
    <accelerometer name="ivme" site="imu"/>
    <gyro name="jiro" site="imu"/>
    <accelerometer name="kutu_ivme" site="kutu_noktasi"/>
  </sensor>
</mujoco>
'''


def kutle_ozellikleri(m, d, govde_adlari=("govde", "kutu")):
    """MuJoCo modelinden (mj_forward sonrası) verilen gövdelerin toplam kütlesi, kütle merkezi ve KM'deki atalet tensörü,
    'govde' çerçevesinde. 2D modelle karşılaştırma içindir (tekerler hariç)."""
    import mujoco
    import numpy as np

    ig = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "govde")
    R0, p0 = d.xmat[ig].reshape(3, 3), d.xpos[ig]
    kutleler, kmler, ataletler = [], [], []
    for ad in govde_adlari:
        i = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, ad)
        if i < 0:
            continue
        Ri = d.ximat[i].reshape(3, 3)
        I_dunya = Ri @ np.diag(m.body_inertia[i]) @ Ri.T
        kutleler.append(m.body_mass[i])
        kmler.append(R0.T @ (d.xipos[i] - p0))
        ataletler.append(R0.T @ I_dunya @ R0)
    M = float(sum(kutleler))
    km = sum(mi * ci for mi, ci in zip(kutleler, kmler)) / M
    I = np.zeros((3, 3))
    for mi, ci, Ii in zip(kutleler, kmler, ataletler):
        rv = ci - km
        I += Ii + mi * (rv @ rv * np.eye(3) - np.outer(rv, rv))
    return M, km, I
