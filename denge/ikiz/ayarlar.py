"""parametreler.toml'dan dijital ikizin ayarlarını okur: fizik, motorlar, sensörler, zamanlama, kestirim, kontrol, senaryo."""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from .. import motor as motor_modulu
from .. import satin_alinan
from ..kutle_merkezi import denge_acisi, yere_degme_acilari
from ..model import ModelParametreleri
from .fizik import FizikAyarlari, Motor, motor_adaydan

G0 = 9.80665
DERECE = math.pi / 180


@dataclass(frozen=True)
class SensorAyarlari:
    gyro_gurultu: float  # [rad/s/√Hz]
    gyro_sapma: float  # [rad/s]
    ivme_gurultu: float  # [m/s²/√Hz]
    ivme_sapma: float  # [m/s²]
    gyro_lsb: float  # bir sayımın karşılığı [rad/s]
    ivme_lsb: float  # [m/s²]
    suzgec_hz: float  # iç alçak geçiren süzgeç (DLPF) bant genişliği [Hz]
    imu_konum: tuple[float, float]  # IMU'nun gövdedeki (x, z) konumu [m]
    pil_olcum_hatasi: float  # oran


@dataclass(frozen=True)
class Zamanlama:
    Ts: float  # kontrol periyodu [s]
    hesaplama_gecikmesi: float  # örnekleme → PWM [s]
    komut_gecikmesi: float  # eldiven → robot [s]
    hiz_penceresi: float  # enkoder hız kestirim penceresi [s]


@dataclass(frozen=True)
class KestirimAyarlari:
    yontem: str  # "kalman" | "tamamlayici"
    tau_tamamlayici: float
    q_aci: float
    q_sapma: float
    r_olcum: float
    hiz_tau: float
    ivme_telafisi: bool
    ivme_tau: float


@dataclass(frozen=True)
class KontrolAyarlari:
    yontem: str  # "lqr" | "pid"
    denge_acisi: float  # [rad], gövdenin fiziksel eğimi
    dusme_esigi: float  # [rad]
    akim_siniri: float  # motor başına [A]
    olu_bolge_telafisi: float
    zit_emk_telafisi: bool
    pid_aci: tuple[float, float, float]
    pid_konum: tuple[float, float]
    aci_komut_siniri: float  # [rad]
    integral_siniri: float  # [N m]
    pid_donus: tuple[float, float]
    lqr_K: tuple[float, float, float, float, float]
    lqr_K_donus: tuple[float, float]
    lqr_Q: tuple[float, float, float, float, float]
    lqr_R: float
    lqr_Q_donus: tuple[float, float]
    lqr_R_donus: float
    ileri_besleme_acik: bool
    ileri_besleme: tuple[float, float, float]  # (c1/mgl [rad/(m/s²)], M_x r [N m/(m/s²)], 2 r J_ψ/d [N m/(rad/s²)])
    referans_suzgeci: float  # [s]


@dataclass(frozen=True)
class SenaryoAyarlari:
    baslangic_egimi: float  # [rad]
    mesafe_toleransi: float
    aci_toleransi: float  # [rad]
    durma_hizi: float  # [m/s]
    toparlanma_acisi: float  # [rad]
    statik_kayma_siniri: float  # [m]
    tepki_esigi: float  # [m]
    yerlesme_suresi: float  # [s] hareket profili bitince durmaya verilen süre [öneri]
    o1_mesafe: float
    o1_bekleme: float
    o1_sure: float
    o2_mesafe: float
    o2_sure: float
    o2_donus: float  # [rad]
    donus_sure: float
    profil_ivme_orani: float
    toparlanma_acisi_baslangic: float  # [rad] Ö1-4'te ±10°
    toparlanma_suresi: float  # [s]
    statik_sure: float  # Ö1-1 [s]
    komut_tepki_suresi: float  # [s]
    sigorta: float  # [A]


@dataclass(frozen=True)
class IkizAyarlari:
    fizik: FizikAyarlari
    sensor: SensorAyarlari
    zaman: Zamanlama
    kestirim: KestirimAyarlari
    kontrol: KontrolAyarlari
    senaryo: SenaryoAyarlari
    J_rotor: float  # motor milinde rotor ataleti [kg m²]
    tohum: int
    pil: dict  # {"dolu": V, "bos": V}

    def degistir(self, **kw) -> IkizAyarlari:
        return replace(self, **kw)


def _d(t, yol):
    return t.d(yol)


def ileri_besleme_katsayilari(p: ModelParametreleri) -> tuple[float, float, float]:
    """Doğrusal modelden: sabit ivmede eğim (c1/mgl), tork (M_x r) ve dönüş torku (2 r J_ψ / d) katsayıları."""
    from ..model import dogrusal_katsayilar

    k = dogrusal_katsayilar(p)
    c1 = k["M_x"] * p.r + k["a12"]
    return c1 / k["mgl"], k["M_x"] * p.r, 2 * p.r * k["J_psi"] / p.d


def ikiz_ayarlari(t) -> IkizAyarlari:
    """Tasarim → IkizAyarlari (birimler SI'ya çevrilir)."""
    V = t.batarya_gerilimleri()
    fizik = FizikAyarlari(
        mu=_d(t, "zemin.surtunme"),
        bosluk=_d(t, "ikiz.reduktor_boslugu"),
        R_ic=_d(t, "ikiz.pil_ic_direnci"),
        I_lojik=_d(t, "guc.lojik_gucu") / V["nominal"],
        surucu_olu_bolge=_d(t, "ikiz.surucu_olu_bolge"),
        pwm_adimi=1 / 1023,  # ESP32 LEDC, 10 bit, 20 kHz [öneri]
        dt=_d(t, "simulasyon.fizik_adimi"),
    )
    ex, ez = _d(t, "imu.konum")
    sensor = SensorAyarlari(
        gyro_gurultu=_d(t, "imu.jiroskop_gurultu_yogunlugu") * DERECE,
        gyro_sapma=_d(t, "imu.jiroskop_kalan_sapma") * DERECE,
        ivme_gurultu=_d(t, "imu.ivme_gurultu_yogunlugu") * 1e-6 * G0,
        ivme_sapma=_d(t, "imu.ivme_kalan_sapma") * 1e-3 * G0,
        gyro_lsb=DERECE / _d(t, "imu.jiroskop_olcegi"),
        ivme_lsb=G0 / _d(t, "imu.ivme_olcegi"),
        suzgec_hz=_d(t, "kestirim.imu_suzgeci"),
        imu_konum=(ex, ez),
        pil_olcum_hatasi=_d(t, "ikiz.pil_olcum_hatasi"),
    )
    zaman = Zamanlama(
        Ts=1 / _d(t, "hedef.kontrol_frekansi"),
        hesaplama_gecikmesi=_d(t, "zamanlama.hesaplama_gecikmesi"),
        komut_gecikmesi=_d(t, "zamanlama.komut_gecikmesi"),
        hiz_penceresi=_d(t, "hedef.hiz_kestirim_penceresi"),
    )
    kestirim = KestirimAyarlari(
        yontem=_d(t, "kestirim.yontem"),
        tau_tamamlayici=_d(t, "kestirim.tamamlayici_zaman_sabiti"),
        q_aci=_d(t, "kestirim.kalman_q_aci"),
        q_sapma=_d(t, "kestirim.kalman_q_sapma"),
        r_olcum=_d(t, "kestirim.kalman_r"),
        hiz_tau=_d(t, "kestirim.hiz_suzgec_zaman_sabiti"),
        ivme_telafisi=bool(_d(t, "kestirim.ivme_telafisi")),
        ivme_tau=_d(t, "kestirim.ivme_suzgec_zaman_sabiti"),
    )
    kontrol = KontrolAyarlari(
        yontem=_d(t, "kontrol.yontem"),
        denge_acisi=_d(t, "kontrol.denge_acisi") * DERECE,
        dusme_esigi=_d(t, "kontrol.dusme_esigi") * DERECE,
        akim_siniri=_d(t, "kontrol.akim_siniri"),
        olu_bolge_telafisi=_d(t, "kontrol.olu_bolge_telafisi"),
        zit_emk_telafisi=bool(_d(t, "kontrol.zit_emk_telafisi")),
        pid_aci=tuple(_d(t, "kontrol.pid.aci")),
        pid_konum=tuple(_d(t, "kontrol.pid.konum")),
        aci_komut_siniri=_d(t, "kontrol.pid.aci_komut_siniri") * DERECE,
        integral_siniri=_d(t, "kontrol.pid.integral_siniri"),
        pid_donus=tuple(_d(t, "kontrol.pid.donus")),
        lqr_K=tuple(_d(t, "kontrol.lqr.K")),
        lqr_K_donus=tuple(_d(t, "kontrol.lqr.K_donus")),
        lqr_Q=tuple(_d(t, "kontrol.lqr.Q")),
        lqr_R=_d(t, "kontrol.lqr.R"),
        lqr_Q_donus=tuple(_d(t, "kontrol.lqr.Q_donus")),
        lqr_R_donus=_d(t, "kontrol.lqr.R_donus"),
        ileri_besleme_acik=bool(_d(t, "kontrol.ileri_besleme")),
        ileri_besleme=ileri_besleme_katsayilari(t.model(kutulu=True).degistir(J_m=_d(t, "ikiz.rotor_ataleti_motor") * satin_alinan.aday(t).reduksiyon**2)),
        referans_suzgeci=_d(t, "kontrol.referans_suzgeci"),
    )
    senaryo = SenaryoAyarlari(
        baslangic_egimi=_d(t, "senaryo.baslangic_egimi") * DERECE,
        mesafe_toleransi=_d(t, "senaryo.mesafe_toleransi"),
        aci_toleransi=_d(t, "senaryo.aci_toleransi") * DERECE,
        durma_hizi=_d(t, "senaryo.durma_hizi"),
        toparlanma_acisi=_d(t, "senaryo.toparlanma_acisi") * DERECE,
        statik_kayma_siniri=_d(t, "senaryo.statik_kayma_siniri"),
        tepki_esigi=_d(t, "senaryo.tepki_esigi"),
        yerlesme_suresi=1.0,
        o1_mesafe=_d(t, "sartname.o1_mesafe"),
        o1_bekleme=_d(t, "sartname.o1_bekleme"),
        o1_sure=_d(t, "hedef.o1_sure"),
        o2_mesafe=_d(t, "sartname.o2_mesafe"),
        o2_sure=_d(t, "hedef.o2_sure"),
        o2_donus=_d(t, "sartname.o2_donus") * DERECE,
        donus_sure=_d(t, "hedef.donus_sure"),
        profil_ivme_orani=_d(t, "hedef.profil_ivme_orani"),
        toparlanma_acisi_baslangic=_d(t, "sartname.toparlanma_acisi") * DERECE,
        toparlanma_suresi=_d(t, "sartname.toparlanma_suresi"),
        statik_sure=30.0,  # şartname §8 Ö1-1
        komut_tepki_suresi=_d(t, "sartname.komut_tepki_suresi"),
        sigorta=_d(t, "elektrik.sigorta"),
    )
    return IkizAyarlari(fizik, sensor, zaman, kestirim, kontrol, senaryo, _d(t, "ikiz.rotor_ataleti_motor"),
                        int(_d(t, "simulasyon.tohum")), {"dolu": V["max"], "bos": V["min"]})


# ---------------------------------------------------------------------------
# Motorlar: satın alınan (ölçüm varsa ölçümle) ve satıcı serisindeki 530 / 333 RPM adayları
# ---------------------------------------------------------------------------
MOTOR_ADLARI = {"1000": "1000 RPM (1:10), satın alınan", "530": "530 RPM (1:19)", "333": "333 RPM (1:30)"}


def motorlar(t, J_rotor: float | None = None) -> dict[str, Motor]:
    J = t.d("ikiz.rotor_ataleti_motor") if J_rotor is None else J_rotor
    seri = {round(x.reduksiyon): x for x in motor_modulu.satici_serisi_adaylari(t)}
    return {
        "1000": motor_adaydan(satin_alinan.aday(t), J, MOTOR_ADLARI["1000"]),
        "530": motor_adaydan(seri[19], J, MOTOR_ADLARI["530"]),
        "333": motor_adaydan(seri[30], J, MOTOR_ADLARI["333"]),
    }


@dataclass(frozen=True)
class Govde:
    """Bir yük durumunun (kutulu/kutusuz) ikiz için gereken bütün geometrisi."""

    p: ModelParametreleri  # J_m motora göre ayarlanır
    theta_trim: float  # gövdenin dik duruş (KM aksın üstünde) eğimi [rad]
    yere_degme: tuple[float, float]  # (ileri, geri) [rad], gövde eğimi cinsinden
    kutulu: bool
    kutu_konum: tuple[float, float]  # kutu merkezinin gövdedeki (x, z) konumu [m]
    kutu_surtunme_acisi: float  # [rad]
    kutu_devrilme_acisi: float  # [rad]


def govde(t, kutulu: bool, motor: Motor) -> Govde:
    p = t.model(kutulu=kutulu).degistir(J_m=motor.J_m)
    yd = yere_degme_acilari(t)
    kx, _, kz = t.d("yuk.kutu.boyut")
    return Govde(p, denge_acisi(t.govde(kutulu=kutulu).km), (yd["ileri"], yd["geri"]), kutulu,
                 (t.d("yuk.yuva.x"), t.kutu_merkez_z()), math.atan(t.d("yuk.kutu.surtunme")), math.atan(kx / kz))
