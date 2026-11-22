"""3D ikizin kontrol döngüsü: MuJoCo fiziği + 2D ikizin motor, sensör, kestirici ve kontrolcü kodu.

Her fizik adımında (MuJoCo, dt = simulasyon.adim_3d):
    rotor hızları → motor_elektrigi (2D ikizle aynı fonksiyon: PWM → bara gerilimi → akım) → K_t·I rotor eklemine;
    dişli: δ = q_rotor − q_teker, boşluğun dışında k·(|δ| − β) + c·δ̇ yayı (teker eklemine +, rotora −);
    rotor sürtünmesi MuJoCo frictionloss kısıtıyla (K_t·I_0), tekerin viskoz sürtünmesi eklem sönümüyle.
MuJoCo'nun ivmeölçer ve jiroskop sensörleri 2D ikizin IMU sınıfına (gürültü, sapma, DLPF, nicemleme) verilir; enkoder
rotor eklem açısını sayar. Kontrol periyodu, hesaplama ve komut gecikmeleri, kestirici, kontrolcü ve çıkış katı
2D ikizdekinin aynısıdır. Kayıt 2D ikizin kanallarıyla tutulur; değerlendirme `senaryolar.degerlendir` ile yapılır,
yalnız kutunun gerçek hareketi (serbest cisim) ek bir koşul olarak eklenir.

Gövde yere değerse (çarpışma geometrisi zemine temas ederse) robot düşmüş sayılır: bu, 2D'deki geometrik yere değme
açısının bağımsız bir sınamasıdır.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from ..ikiz.ayarlar import IkizAyarlari, govde, ikiz_ayarlari, motorlar
from ..ikiz.fizik import motor_elektrigi, surucu_cikisi
from ..ikiz.kestirim import DurumKestirici, KalmanSuzgeci, TamamlayiciSuzgec
from ..ikiz.kontrol import CikisKati, Referans, kontrolcu_olustur, motora_gore_tasarla
from ..ikiz.senaryolar import KANALLAR, SATIN_ALINAN, Kayit, Kurulum, degerlendir, senaryolar, tohum
from ..ikiz.sensorler import IMU, PilOlcumu, enkoder_sayimi
from . import mjcf

KUTU_CIKIS_KAYMA = 0.03  # m: kutunun yuvadaki konumu bundan fazla değişirse yuvadan çıkmış sayılır [öneri]
KUTU_CIKIS_EGIM = math.radians(45)  # kutu gövdeye göre bundan fazla dönerse devrilmiş sayılır [öneri]


@dataclass
class Kayit3D(Kayit):
    kareler: list = field(default_factory=list)  # (t, qpos, ek bilgi) video için
    temas_aci: float | None = None  # gövdenin zemine değdiği andaki eğim [rad]


def _idler(m):
    import mujoco

    adr = lambda ad: m.jnt_qposadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, ad)]
    dof = lambda ad: m.jnt_dofadr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_JOINT, ad)]
    geom = lambda ad: mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, ad)
    sensor = lambda ad: m.sensor_adr[mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_SENSOR, ad)]
    robot = {geom(a) for a in ("plaka_0", "plaka_1", "plaka_2", "acil_durdurma", "ir_modulu", "yuva_on", "yuva_arka", "yuva_sol", "yuva_sag")}
    return {
        "q_teker": (adr("teker_R"), adr("teker_L")), "q_rotor": (adr("rotor_R"), adr("rotor_L")),
        "v_teker": (dof("teker_R"), dof("teker_L")), "v_rotor": (dof("rotor_R"), dof("rotor_L")),
        "govde": mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "govde"), "kutu": mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_BODY, "kutu"),
        "zemin": geom("zemin"), "robot": robot, "ivme": sensor("ivme"), "jiro": sensor("jiro"), "kutu_ivme": sensor("kutu_ivme"),
    }


def model_kur(t, k: Kurulum, ay: IkizAyarlari, mot, theta0: float, motor_bagli: bool = True):
    import mujoco

    m = mujoco.MjModel.from_xml_string(mjcf.mjcf(t, mot, ay, k.kutulu, theta0))
    d = mujoco.MjData(m)
    mujoco.mj_forward(m, d)
    return m, d


def _kutu_goreli(d, ids, R0, p0):
    ib = ids["kutu"]
    p = R0.T @ (d.xpos[ib] - p0)
    Rk = R0.T @ d.xmat[ib].reshape(3, 3)
    egim = math.acos(max(-1.0, min(1.0, Rk[2, 2])))
    return p, egim


def calistir3d(t, kod: str, k: Kurulum, ay: IkizAyarlari | None = None, sure: float | None = None, theta0: float | None = None,
               video_fps: float | None = None, motor_bagli: bool = True, geri_cagir=None) -> Kayit3D:
    """Bir senaryoyu MuJoCo'da koşturur. video_fps verilirse o hızda qpos kaydı tutulur (video için).

    geri_cagir(m, d, t_sim) her kontrol periyodunun sonunda çağrılır (canlı izleme); True dönerse koşu durur.
    """
    import mujoco

    ay = ay or ikiz_ayarlari(t)
    mot = motorlar(t, ay.J_rotor)[k.motor]
    sen = senaryolar(ay)[kod]
    gv = govde(t, k.kutulu, mot)  # 2D modelin geometrisi: dik duruş açısı, yere değme açıları (karşılaştırma için)
    Ts = ay.zaman.Ts
    if k.motor != SATIN_ALINAN:
        ay = ay.degistir(kontrol=motora_gore_tasarla(ay.kontrol, govde(t, True, mot).p, Ts))
    th0 = theta0 if theta0 is not None else (sen.theta0 + (gv.theta_trim if sen.theta0_bagil else 0.0))
    m, d = model_kur(t, k, ay, mot, th0)
    dt = m.opt.timestep
    ids = _idler(m)
    r, iz = t.d("teker.yaricap"), t.d("teker.iz_genisligi")
    k_g, c_g = t.d("ikiz.disli_rijitligi"), t.d("ikiz.disli_sonumu")
    beta = ay.fizik.bosluk / 2
    esik_kayma = t.d("simulasyon.kayma_esigi_3d")

    rng = np.random.default_rng(tohum(ay, kod, k))
    jiro_z = ay.kestirim.sapma_jiroskopla
    imu = IMU(ay.sensor, dt, rng, t.d("sabit.g"), np.random.default_rng(tohum(ay, kod, k) + 1))
    pil = PilOlcumu(ay.sensor.pil_olcum_hatasi, rng)
    egim = (KalmanSuzgeci(ay.kestirim.q_aci, ay.kestirim.q_sapma, ay.kestirim.r_olcum, Ts) if k.kestirici == "kalman"
            else TamamlayiciSuzgec(ay.kestirim.tau_tamamlayici, Ts))
    kest = DurumKestirici(egim, r, iz, mot.cpr, Ts, ay.zaman.hiz_penceresi, ay.kestirim.hiz_tau,
                          ay.kestirim.ivme_telafisi, ay.sensor.imu_konum[1], ay.kestirim.ivme_tau, jiro_z)
    ktr = kontrolcu_olustur(ay.kontrol, Ts, k.kontrolcu)
    cikis = CikisKati(mot, ay.kontrol, Ts)
    ref = Referans(ay.senaryo.profil_ivme_orani, Ts, ay.kontrol.referans_suzgeci)
    V_acik = ay.pil[k.pil]

    n_alt = max(1, round(Ts / dt))
    n_gec = min(n_alt - 1, round(ay.zaman.hesaplama_gecikmesi / dt))
    kuyruk = sorted((tg + ay.zaman.komut_gecikmesi, tur, mm, s) for tg, tur, mm, s in sen.komutlar)
    sure = sen.sure if sure is None else sure
    N = int(round(sure / Ts))
    veri = np.zeros((N, len(KANALLAR)))
    qT, qR, vT, vR = ids["q_teker"], ids["q_rotor"], ids["v_teker"], ids["v_rotor"]
    ia, ij, ik = ids["ivme"], ids["jiro"], ids["kutu_ivme"]
    ig = ids["govde"]

    def poz():
        R = d.xmat[ig].reshape(3, 3)
        return R, d.xpos[ig].copy()

    def aci_hiz(R):
        th = math.asin(max(-1.0, min(1.0, -R[2, 0])))
        psi = math.atan2(R[1, 0], R[0, 0])
        w_l = d.qvel[3:6]
        return th, psi, float(w_l[1]), float((R @ w_l)[2])

    # Açılış: IMU durağan ölçümü, kestirici başlatma
    imu.olcum_ekle(float(d.sensordata[ij + 1]), float(d.sensordata[ia]), float(d.sensordata[ia + 2]), float(d.sensordata[ij + 2]))
    _, ax0, az0 = imu.oku()
    cpr = mot.cpr
    kest.baslat(ax0, az0, enkoder_sayimi(d.qpos[qR[0]], cpr), enkoder_sayimi(d.qpos[qR[1]], cpr))
    V_bara = V_acik
    IR = IL = 0.0
    R0, p0 = poz()
    kutu_p0 = _kutu_goreli(d, ids, R0, p0)[0] if k.kutulu else None
    psi_onceki = math.atan2(R0[1, 0], R0[0, 0])
    psi_sur = psi_onceki
    x_yol = 0.0
    duty = [0.0, 0.0]
    dustu, t_dusme, kesildi, temas_aci = False, None, None, None
    kutu_kayma = kutu_egim = 0.0
    kutu_cikti = None
    kareler = []
    t_kare = 0.0
    n = 0
    for i in range(N):
        tk = i * Ts
        while kuyruk and kuyruk[0][0] <= tk + 1e-9:
            _, tur, mm, s = kuyruk.pop(0)
            ref.komut(tk, tur, mm, s)
        gyro, ax, az = imu.oku()
        s_k = kest.guncelle(gyro, ax, az, enkoder_sayimi(d.qpos[qR[0]], cpr), enkoder_sayimi(d.qpos[qR[1]], cpr),
                            imu.oku_z() if jiro_z else 0.0)
        cikis.pil_olcumu(pil.oku(V_bara))
        rr = ref.hesapla(tk)
        if kesildi is None and abs(s_k[2]) > ay.kontrol.dusme_esigi:
            kesildi = tk
        if kesildi is not None:
            yeni, d_pwm, d_akim = (0.0, 0.0), False, False
        else:
            tau, tau_f = ktr.hesapla(s_k, rr)
            wRk, wLk = kest.bagil_hizlar()
            dd = cikis.hesapla(tau, tau_f, wRk, wLk)
            yeni, d_pwm, d_akim = (dd[0], dd[1]), cikis.doyum_pwm, cikis.doyum_akim
            ktr.doyum_bildir(d_pwm or d_akim)

        I_bara = I_tepe = kayma = bosluk = fxk = fzk = 0.0
        for j in range(n_alt):
            if j == n_gec:
                duty[0], duty[1] = yeni
            sR, sL = surucu_cikisi(ay.fizik, duty[0]), surucu_cikisi(ay.fizik, duty[1])
            wR, wL = float(d.qvel[vR[0]]), float(d.qvel[vR[1]])
            V_bara, IR, IL = motor_elektrigi(mot, ay.fizik, sR, sL, wR, wL, V_acik)
            for e, tau_m in ((0, mot.K_t * IR), (1, mot.K_t * IL)):
                dlt = float(d.qpos[qR[e]] - d.qpos[qT[e]])
                tg = 0.0
                if motor_bagli:
                    asim = abs(dlt) - beta
                    if asim > 0.0:
                        tg = math.copysign(k_g * asim, dlt) + c_g * float(d.qvel[vR[e]] - d.qvel[vT[e]])
                    else:
                        bosluk += 0.5
                d.qfrc_applied[vR[e]] = tau_m - tg
                d.qfrc_applied[vT[e]] = tg
            mujoco.mj_step(m, d)
            imu.olcum_ekle(float(d.sensordata[ij + 1]), float(d.sensordata[ia]), float(d.sensordata[ia + 2]), float(d.sensordata[ij + 2]))
            fxk += float(d.sensordata[ik])
            fzk += float(d.sensordata[ik + 2])
            I_bara += sR * IR + sL * IL
            I_tepe = max(I_tepe, abs(IR) + abs(IL))
            R, p = poz()
            th, psi, thd, psid = aci_hiz(R)
            dpsi = (psi - psi_onceki + math.pi) % (2 * math.pi) - math.pi
            psi_onceki = psi
            psi_sur += dpsi
            v = float(d.qvel[0] * math.cos(psi) + d.qvel[1] * math.sin(psi))
            x_yol += v * dt
            for e, isaret in ((0, 1.0), (1, -1.0)):
                kayma_hizi = v + isaret * iz / 2 * psid - r * (float(d.qvel[vT[e]]) + thd)
                if abs(kayma_hizi) > esik_kayma:
                    kayma += 0.5
            if video_fps and d.time + 1e-12 >= t_kare:
                kareler.append((d.time, d.qpos.copy(), {"theta": th, "x": x_yol, "psi": psi_sur}))
                t_kare += 1.0 / video_fps
        # Zemin teması (gövde)
        if not dustu:
            for c in d.contact[: d.ncon]:
                g1, g2 = c.geom1, c.geom2
                if (g1 == ids["zemin"] and g2 in ids["robot"]) or (g2 == ids["zemin"] and g1 in ids["robot"]):
                    dustu, t_dusme, temas_aci = True, d.time, th
                    break
        if k.kutulu:
            pk, eg = _kutu_goreli(d, ids, R, p)
            kayma_k = float(np.linalg.norm(pk - kutu_p0))
            kutu_kayma, kutu_egim = max(kutu_kayma, kayma_k), max(kutu_egim, eg)
            if kutu_cikti is None and (kayma_k > KUTU_CIKIS_KAYMA or eg > KUTU_CIKIS_EGIM):
                kutu_cikti = d.time
        veri[i] = (d.time, x_yol, v, th, thd, psi_sur, psid, p[0], p[1], s_k[0], s_k[1], s_k[2], s_k[4],
                   rr[0], rr[1], rr[3], duty[0], duty[1], IR, IL, I_bara / n_alt, I_tepe, V_bara, d_pwm, d_akim,
                   kayma / n_alt, bosluk / n_alt, math.atan2(fxk, fzk), fzk / n_alt, 0.0)
        n = i + 1
        if geri_cagir is not None and geri_cagir(m, d, d.time):
            break
        if dustu:
            break
    gvd = {"theta_trim": gv.theta_trim, "yere_degme": gv.yere_degme, "kutu_surtunme_acisi": gv.kutu_surtunme_acisi,
           "kutu_devrilme_acisi": gv.kutu_devrilme_acisi, "kutulu": gv.kutulu, "durma_akimi": V_acik / mot.R, "d_yari": iz / 2,
           "kutu3d": {"kayma": kutu_kayma, "egim": kutu_egim, "cikti": kutu_cikti} if k.kutulu else None}
    kay = Kayit3D(kod, k, veri[:n], dustu, t_dusme, kesildi, gvd, 0, kareler=kareler, temas_aci=temas_aci)
    return kay


def degerlendir3d(kay: Kayit3D, ay: IkizAyarlari) -> dict:
    """2D değerlendirici + kutunun gerçek hareketi (3D'de serbest cisim): yuvadan çıkmamalı, devrilmemeli."""
    d = degerlendir(kay, ay)
    k3 = kay.gv.get("kutu3d")
    if k3 is not None:
        for a in d["alt"]:
            ok = k3["cikti"] is None
            a["kosullar"].append(("Kutu yuvada kalır (3D serbest cisim)", ok,
                                  f"en çok {1000 * k3['kayma']:.1f} mm kaydı, {math.degrees(k3['egim']):.1f}° döndü"))
            if not ok:
                a["gecti"] = False
                ek = f"kutu {k3['cikti']:.2f} s'de yuvadan çıktı/devrildi"
                a["neden"] = f"{a['neden']}; {ek}" if a["neden"] else ek
        d["gecti"] = all(a["gecti"] for a in d["alt"])
    d["kutu3d"] = k3
    d["temas_aci"] = kay.temas_aci
    return d
