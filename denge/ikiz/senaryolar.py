"""Şartname testlerinin senaryoları, kapalı çevrim çalıştırıcı, ölçütler, geçti/kaldı ve düşme nedeni.

Senaryolar (şartname TR v14 §8):
    O1-1   30 s statik denge
    O1-23  ≈1 m ileri + 3 s dur (Ö1-2), ≈1 m geri + 3 s dur (Ö1-3)
    O1-4+  +10°'den 10 s içinde toparlanma;  O1-4-  −10°'den (Ö1-4 ikisi birlikte sağlanınca geçer)
    O2     ≈0,5 m ileri, ≈0,5 m geri, ≈90° sola, ≈90° sağa; her komuttan sonra dur; 2 s içinde tepki
Kurulum: motor (1000 / 530 / 333 RPM), kutu takılı ya da değil, pil dolu (12,6 V) ya da boş (9,9 V),
kontrolcü (lqr / pid), kestirici (kalman / tamamlayici).

Zamanlama: kontrol döngüsü T = 1/200 s. Her periyodun başında sensörler okunur, kestirim ve kontrol hesaplanır,
PWM hesaplama gecikmesi kadar sonra uygulanır (fizik adımı dt'nin katı). Eldiven komutları komut gecikmesi kadar
geç ulaşır. Gürültü tohumu senaryo ve yük/pil durumundan türetilir: kontrolcü, kestirici ve motor karşılaştırmaları
aynı gürültüyle yapılır.
"""

from __future__ import annotations

import math
import zlib
from dataclasses import asdict, dataclass, field

import numpy as np

from ..kutle_merkezi import ozgul_kuvvet
from .ayarlar import DERECE, Govde, IkizAyarlari, govde, ikiz_ayarlari, motorlar
from .fizik import Robot
from .kestirim import DurumKestirici, KalmanSuzgeci, TamamlayiciSuzgec
from .kontrol import CikisKati, Referans, kontrolcu_olustur, motora_gore_tasarla
from .sensorler import IMU, PilOlcumu, enkoder_sayimi

KANALLAR = ("t", "x", "v", "theta", "theta_d", "psi", "psi_d", "X", "Y", "x_k", "v_k", "theta_k", "psi_k",
            "x_ref", "v_ref", "psi_ref", "d_R", "d_L", "I_R", "I_L", "I_bara", "I_tepe", "V_bara", "doyum_pwm",
            "doyum_akim", "kayma", "bosluk", "alfa_kutu", "fz_kutu", "N_min")
K = {ad: i for i, ad in enumerate(KANALLAR)}
SENARYO_KODLARI = ("O1-1", "O1-23", "O1-4+", "O1-4-", "O2")
SENARYO_ADLARI = {"O1-1": "Ö1-1 statik denge (30 s)", "O1-23": "Ö1-2/3 ≈1 m ileri/geri + 3 s dur",
                  "O1-4+": "Ö1-4 +10°'den toparlanma", "O1-4-": "Ö1-4 −10°'den toparlanma",
                  "O2": "Ö2 0,5 m ileri/geri, 90° sol/sağ"}


SATIN_ALINAN = "1000"  # kazançları parametre dosyasından okunan motor


@dataclass(frozen=True)
class Kurulum:
    motor: str = SATIN_ALINAN
    kutulu: bool = True
    pil: str = "bos"  # "dolu" | "bos"
    kontrolcu: str = "lqr"
    kestirici: str = "kalman"  # "kalman" | "tamamlayici" | "ideal" (yalnız tanılama: gerçek durum)

    def etiket(self) -> str:
        return (f"{self.motor} RPM, {'kutulu' if self.kutulu else 'kutusuz'}, {'dolu' if self.pil == 'dolu' else 'boş'} pil, "
                f"{self.kontrolcu.upper()} + {'Kalman' if self.kestirici == 'kalman' else 'tamamlayıcı'}")


@dataclass(frozen=True)
class AltTest:
    ad: str  # "Ö1-2", "Ö2 ileri" ...
    tur: str  # "statik" | "oteleme" | "donus" | "toparlanma"
    t_komut: float = 0.0  # komutun eldivenden çıktığı an
    pencere: tuple[float, float] = (0.0, 0.0)  # durma/değerlendirme penceresi
    beklenen: float = 0.0  # m ya da rad (işaretli)


@dataclass(frozen=True)
class Senaryo:
    kod: str
    sure: float
    theta0: float  # başlangıç eğimi [rad]
    theta0_bagil: bool  # True: dik duruşa göre; False: düşeye göre (fiziksel)
    komutlar: tuple = ()  # (t_gönderim, tür, miktar, süre)
    alt_testler: tuple = ()


def senaryolar(ay: IkizAyarlari) -> dict[str, Senaryo]:
    sa, gec = ay.senaryo, ay.zaman.komut_gecikmesi
    y = sa.yerlesme_suresi
    out = {"O1-1": Senaryo("O1-1", sa.statik_sure + 0.5, sa.baslangic_egimi, True,
                           alt_testler=(AltTest("Ö1-1", "statik", 0.0, (0.0, sa.statik_sure)),))}
    # Ö1-2/3
    t1 = 1.0
    b1 = t1 + gec + sa.o1_sure + y
    t2 = b1 + sa.o1_bekleme + 0.3
    b2 = t2 + gec + sa.o1_sure + y
    out["O1-23"] = Senaryo("O1-23", b2 + sa.o1_bekleme + 0.3, sa.baslangic_egimi, True,
                           ((t1, "ileri", sa.o1_mesafe, sa.o1_sure), (t2, "geri", sa.o1_mesafe, sa.o1_sure)),
                           (AltTest("Ö1-2", "oteleme", t1, (b1, b1 + sa.o1_bekleme), sa.o1_mesafe),
                            AltTest("Ö1-3", "oteleme", t2, (b2, b2 + sa.o1_bekleme), -sa.o1_mesafe)))
    for kod, isaret in (("O1-4+", 1.0), ("O1-4-", -1.0)):
        out[kod] = Senaryo(kod, sa.toparlanma_suresi + 2.0, isaret * sa.toparlanma_acisi_baslangic, False,
                           alt_testler=(AltTest(f"Ö1-4 ({'+' if isaret > 0 else '−'}10°)", "toparlanma", 0.0,
                                                (0.0, sa.toparlanma_suresi)),))
    # Ö2: her komuttan sonra yerleşme + 1 s dur
    t, komutlar, alt = 1.0, [], []
    for ad, tur, miktar, sure in (("Ö2 ileri", "ileri", sa.o2_mesafe, sa.o2_sure), ("Ö2 geri", "geri", sa.o2_mesafe, sa.o2_sure),
                                  ("Ö2 sol 90°", "sol", sa.o2_donus, sa.donus_sure), ("Ö2 sağ 90°", "sag", sa.o2_donus, sa.donus_sure)):
        b = t + gec + sure + y
        komutlar.append((t, tur, miktar, sure))
        alt.append(AltTest(ad, "oteleme" if tur in ("ileri", "geri") else "donus", t, (b, b + 1.0),
                           miktar if tur in ("ileri", "sol") else -miktar))
        t = b + 1.0
    out["O2"] = Senaryo("O2", t + 0.5, sa.baslangic_egimi, True, tuple(komutlar), tuple(alt))
    return out


def tohum(ay: IkizAyarlari, kod: str, k: Kurulum) -> int:
    return zlib.crc32(f"{ay.tohum}|{kod}|{k.kutulu}|{k.pil}".encode())


# ---------------------------------------------------------------------------
# Çalıştırıcı
# ---------------------------------------------------------------------------
@dataclass
class Kayit:
    kod: str
    kurulum: Kurulum
    veri: np.ndarray  # (n, len(KANALLAR))
    dustu: bool
    t_dusme: float | None
    motor_kesildi: float | None  # firmware düşme eşiğinin aşıldığı an
    gv: dict = field(default_factory=dict)  # gövde bilgisi (trim, yere değme, kutu açıları)
    dongu_asimi: int = 0

    def k(self, ad: str) -> np.ndarray:
        return self.veri[:, K[ad]]


def calistir(t, kod: str, k: Kurulum, ay: IkizAyarlari | None = None, mot=None, sure: float | None = None,
             theta0: float | None = None) -> Kayit:
    """Bir senaryoyu bir kurulumla koşturur. t: parametreler.Tasarim."""
    ay = ay or ikiz_ayarlari(t)
    mot = mot or motorlar(t, ay.J_rotor)[k.motor]
    sen = senaryolar(ay)[kod]
    gv: Govde = govde(t, k.kutulu, mot)
    p, Ts, dt = gv.p, ay.zaman.Ts, ay.fizik.dt
    if k.motor != SATIN_ALINAN:  # aday motor: LQR aynı Q/R ile o motorun (kutulu) modelinden tasarlanır
        ay = ay.degistir(kontrol=motora_gore_tasarla(ay.kontrol, govde(t, True, mot).p, Ts))
    rng = np.random.default_rng(tohum(ay, kod, k))
    th0 = theta0 if theta0 is not None else (sen.theta0 + (gv.theta_trim if sen.theta0_bagil else 0.0))
    robot = Robot(p, mot, ay.fizik, theta0=th0 - gv.theta_trim, theta_trim=gv.theta_trim)
    imu = IMU(ay.sensor, dt, rng, p.g)
    pil = PilOlcumu(ay.sensor.pil_olcum_hatasi, rng)
    egim = (KalmanSuzgeci(ay.kestirim.q_aci, ay.kestirim.q_sapma, ay.kestirim.r_olcum, Ts) if k.kestirici == "kalman"
            else TamamlayiciSuzgec(ay.kestirim.tau_tamamlayici, Ts))
    kest = DurumKestirici(egim, p.r, p.d, mot.cpr, Ts, ay.zaman.hiz_penceresi, ay.kestirim.hiz_tau,
                          ay.kestirim.ivme_telafisi, ay.sensor.imu_konum[1], ay.kestirim.ivme_tau)
    ktr = kontrolcu_olustur(ay.kontrol, Ts, k.kontrolcu)
    cikis = CikisKati(mot, ay.kontrol, Ts)
    ref = Referans(ay.senaryo.profil_ivme_orani, Ts, ay.kontrol.referans_suzgeci)
    V_acik = ay.pil[k.pil]
    yd_i, yd_g = gv.yere_degme
    xk_b, zk_b = gv.kutu_konum

    n_alt = max(1, round(Ts / dt))
    n_gec = min(n_alt - 1, round(ay.zaman.hesaplama_gecikmesi / dt))
    kuyruk = sorted((tg + ay.zaman.komut_gecikmesi, tur, m, s) for tg, tur, m, s in sen.komutlar)
    sure = sen.sure if sure is None else sure
    N = int(round(sure / Ts))
    veri = np.zeros((N, len(KANALLAR)))

    imu.guncelle(robot.theta_govde, 0.0, 0.0, 0.0)
    g0, ax0, az0 = imu.oku()
    cpr = mot.cpr
    kest.baslat(ax0, az0, enkoder_sayimi(robot.bagil_aci(0), cpr), enkoder_sayimi(robot.bagil_aci(1), cpr))
    robot.elektrik(0.0, 0.0, V_acik)
    duty = [0.0, 0.0]
    dustu, t_dusme, kesildi = False, None, None
    n = 0
    for i in range(N):
        tk = i * Ts
        while kuyruk and kuyruk[0][0] <= tk + 1e-9:
            _, tur, m, s = kuyruk.pop(0)
            ref.komut(tk, tur, m, s)
        gyro, ax, az = imu.oku()
        s_k = kest.guncelle(gyro, ax, az, enkoder_sayimi(robot.bagil_aci(0), cpr), enkoder_sayimi(robot.bagil_aci(1), cpr))
        if k.kestirici == "ideal":  # yalnız tanılama: kestirim yerine gerçek durum
            s_k = [robot.q[0], robot.nu[0], robot.theta_govde, robot.nu[2], robot.q[1], robot.nu[1]]
        cikis.pil_olcumu(pil.oku(robot.V_bara))
        r = ref.hesapla(tk)
        if kesildi is None and abs(s_k[2]) > ay.kontrol.dusme_esigi:
            kesildi = tk
        if kesildi is not None:
            yeni, d_pwm, d_akim = (0.0, 0.0), False, False
        else:
            tau, tau_f = ktr.hesapla(s_k, r)
            wR, wL = kest.bagil_hizlar()
            d = cikis.hesapla(tau, tau_f, wR, wL)
            yeni, d_pwm, d_akim = (d[0], d[1]), cikis.doyum_pwm, cikis.doyum_akim
            ktr.doyum_bildir(d_pwm or d_akim)

        v0, thd0 = robot.nu[0], robot.nu[2]
        I_bara = I_tepe = kayma = bosluk = 0.0
        N_min = 1e9
        for j in range(n_alt):
            if j == n_gec:
                duty[0], duty[1] = yeni
            robot.adim(duty[0], duty[1], V_acik)
            imu.guncelle(robot.theta_govde, robot.nu[2], robot.thdd, robot.vd)
            IR, IL = robot.akim
            I_bara += robot.surucu(duty[0]) * IR + robot.surucu(duty[1]) * IL
            I_tepe = max(I_tepe, abs(IR) + abs(IL))
            kayma += robot.kayiyor(0) or robot.kayiyor(1)
            bosluk += (not robot.disli_temasta(0)) or (not robot.disli_temasta(1))
            N_min = min(N_min, robot.N[0], robot.N[1])
            thb = robot.theta_govde
            if thb >= yd_i or thb <= -yd_g:
                dustu, t_dusme = True, tk + (j + 1) * dt
                break
        nj = j + 1
        q, nu = robot.q, robot.nu
        thb = robot.theta_govde
        vd_ort, thdd_ort = (nu[0] - v0) / (nj * dt), (nu[2] - thd0) / (nj * dt)
        fx, fz = ozgul_kuvvet(vd_ort, thb, nu[2], thdd_ort, xk_b, zk_b, p.g)
        veri[i] = (tk + nj * dt, q[0], nu[0], thb, nu[2], q[1], nu[1], robot.X, robot.Y, s_k[0], s_k[1], s_k[2], s_k[4],
                   r[0], r[1], r[3], duty[0], duty[1], robot.akim[0], robot.akim[1], I_bara / nj, I_tepe, robot.V_bara,
                   d_pwm, d_akim, kayma / nj, bosluk / nj, math.atan2(fx, fz), fz, N_min)
        n = i + 1
        if dustu:
            break
    gvd = {"theta_trim": gv.theta_trim, "yere_degme": gv.yere_degme, "kutu_surtunme_acisi": gv.kutu_surtunme_acisi,
           "kutu_devrilme_acisi": gv.kutu_devrilme_acisi, "kutulu": gv.kutulu, "durma_akimi": V_acik / mot.R, "d_yari": p.d / 2}
    return Kayit(kod, k, veri[:n], dustu, t_dusme, kesildi, gvd, robot.dongu_asimi)


# ---------------------------------------------------------------------------
# Değerlendirme
# ---------------------------------------------------------------------------
def _deg(x):
    return math.degrees(x)


def _ilk_indeks(maske: np.ndarray):
    i = np.flatnonzero(maske)
    return int(i[0]) if i.size else None


def ortak_olcutler(kay: Kayit, Ts: float) -> dict:
    t, th = kay.k("t"), kay.k("theta")
    yd_i, yd_g = kay.gv["yere_degme"]
    pay = np.where(th >= 0, yd_i - th, yd_g + th)
    I_bara = kay.k("I_bara")
    n1 = max(1, int(round(1.0 / Ts)))
    rms1 = np.sqrt(np.convolve(I_bara**2, np.ones(n1) / n1, mode="valid")) if len(I_bara) >= n1 else np.sqrt(np.mean(I_bara**2))
    doyum = (kay.k("doyum_pwm") > 0) | (kay.k("doyum_akim") > 0)
    n01 = max(1, min(len(t), int(round(0.1 / Ts))))
    return {
        "en_buyuk_egim": _deg(float(np.max(np.abs(th)))),
        "yere_degme_payi": _deg(float(np.min(pay))),
        "doyum_suresi": float(np.sum(doyum) * Ts),
        "pwm_doyum_suresi": float(np.sum(kay.k("doyum_pwm") > 0) * Ts),
        "tepe_akim": float(np.max(kay.k("I_tepe"))) if len(t) else 0.0,
        "rms1_akim": float(np.max(rms1)) if np.size(rms1) else 0.0,
        "kayma_suresi": float(np.sum(kay.k("kayma")) * Ts),
        "bosluk_orani": float(np.mean(kay.k("bosluk"))) if len(t) else 0.0,
        # Kutunun kayması ve devrilmesi bir süre isteyen olaylardır: dişli çarpmalarının ms'lik darbeleri sayılmaz,
        # görünür eğim 0,1 s kayan ortalamayla değerlendirilir [öneri]. Anlık tepe ayrıca raporlanır.
        "kutu_alfa": _deg(float(np.max(np.abs(np.convolve(kay.k("alfa_kutu"), np.ones(n01) / n01, mode="same"))))) if kay.gv["kutulu"] else float("nan"),
        "kutu_alfa_anlik": _deg(float(np.max(np.abs(kay.k("alfa_kutu"))))) if kay.gv["kutulu"] else float("nan"),
        "kutu_fz_min": float(np.min(kay.k("fz_kutu"))),
        "kestirim_hatasi": _deg(float(np.sqrt(np.mean((kay.k("theta_k") - th) ** 2)))),
        "x_sapma": float(np.max(np.abs(kay.k("x")))),
        "sure": float(t[-1]) if len(t) else 0.0,
    }


def dusme_nedeni(kay: Kayit, Ts: float) -> str:
    """Düşmeden önceki 1 s'ye bakarak en olası nedeni yazar."""
    t = kay.k("t")
    t_son = kay.t_dusme if kay.t_dusme is not None else t[-1]
    t_bas = (kay.motor_kesildi if kay.motor_kesildi is not None else t_son) - 1.0
    w = (t >= t_bas) & (t <= t_son)
    if kay.motor_kesildi is not None:
        w &= t <= kay.motor_kesildi
    if not np.any(w):
        w = t <= t_son
    doyum = float(np.mean((kay.k("doyum_pwm")[w] > 0) | (kay.k("doyum_akim")[w] > 0)))
    kayma = float(np.mean(kay.k("kayma")[w]))
    hata = _deg(float(np.max(np.abs(kay.k("theta_k")[w] - kay.k("theta")[w]))))
    yon = "ileri" if kay.k("theta")[-1] > 0 else "geri"
    on = f"{t_son:.2f} s'de gövde {yon} yere değdi".replace(".", ",")
    if kay.motor_kesildi is not None:
        on += f" (firmware {kay.motor_kesildi:.2f} s'de düşme eşiğini aştığı için motorları kesti)".replace(".", ",")
    if doyum > 0.3:
        I = np.abs(kay.k("I_R")[w]) + np.abs(kay.k("I_L")[w])
        devir = float(np.mean(I)) < 0.5 * 2 * kay.gv["durma_akimi"]
        tur = "devir sınırı: zıt EMK yüzünden akım düştü, motor yeterince hızlı dönemiyor" if devir else \
              "tork sınırı: akım durma akımına yakın, motor torku yetmiyor"
        return f"{on}. Neden: motor doyumu (son 1 s'nin %{100 * doyum:.0f}'inde PWM %100 ya da akım sınırında; {tur})."
    if kayma > 0.2:
        return f"{on}. Neden: teker kaydı (son 1 s'nin %{100 * kayma:.0f}'inde çekiş sınırı aşıldı)."
    if hata > 3.0:
        return f"{on}. Neden: eğim kestirimi hatalı (en büyük fark {hata:.1f}°).".replace(".", ",", 1)
    return f"{on}. Neden: kontrolcü kararsızlığı (doyum ve kayma yok; kazançlar, gecikme ya da gürültü)."


def degerlendir(kay: Kayit, ay: IkizAyarlari) -> dict:
    """Alt test sonuçları (geçti/kaldı, değer, ölçüt), ortak ölçütler, genel sonuç ve kalma nedeni."""
    Ts, sa = ay.zaman.Ts, ay.senaryo
    sen = senaryolar(ay)[kay.kod]
    t, x, v, psi, w, th = (kay.k(a) for a in ("t", "x", "v", "psi", "psi_d", "theta"))
    n_ort = max(1, int(round(0.5 / Ts)))  # durma ölçütü: 0,5 s kayan ortalama hız
    v_ort = np.convolve(v, np.ones(n_ort) / n_ort, mode="same")
    w_ort = np.convolve(w, np.ones(n_ort) / n_ort, mode="same")
    o = ortak_olcutler(kay, Ts)
    t_bitti = kay.t_dusme if kay.dustu else (kay.motor_kesildi if kay.motor_kesildi is not None else math.inf)
    kutu_dustu = kay.gv["kutulu"] and (o["kutu_alfa"] > _deg(kay.gv["kutu_devrilme_acisi"]) or o["kutu_fz_min"] <= 0)
    kutu_kaydi = kay.gv["kutulu"] and o["kutu_alfa"] > _deg(kay.gv["kutu_surtunme_acisi"])
    sigorta = o["rms1_akim"] <= sa.sigorta
    sonuclar = []

    def deger_at(tq):
        i = min(len(t) - 1, int(np.searchsorted(t, tq)))
        return i

    for a in sen.alt_testler:
        kosullar, notlar = [], []
        bitis = a.pencere[1]
        if t_bitti <= bitis + 1e-9:
            kosullar.append(("Denge korunur", False, "düştü"))
        if a.tur == "statik":
            kosullar.append(("30 s düşmeden durur", not kay.dustu and kay.motor_kesildi is None and t[-1] >= sa.statik_sure - 1e-6,
                             f"{min(t[-1], sa.statik_sure):.1f} s"))
            deger = f"en çok {o['x_sapma']:.2f} m uzaklaştı"
            if o["x_sapma"] > sa.statik_kayma_siniri:
                notlar.append(f"başlangıçtan {o['x_sapma']:.2f} m uzaklaştı (uyarı eşiği {sa.statik_kayma_siniri:.2f} m)")
        elif a.tur == "toparlanma":
            band = np.abs(th - kay.gv["theta_trim"]) <= sa.toparlanma_acisi
            disari = np.flatnonzero(~band)
            if kay.dustu or kay.motor_kesildi is not None:
                t_r = math.inf
            elif disari.size == 0:
                t_r = 0.0
            elif disari[-1] == len(t) - 1:
                t_r = math.inf
            else:
                t_r = float(t[disari[-1] + 1])
            kosullar.append((f"{sa.toparlanma_suresi:.0f} s içinde toparlanır", t_r <= sa.toparlanma_suresi,
                             "toparlanmadı" if math.isinf(t_r) else f"{t_r:.2f} s"))
            deger = "toparlanmadı" if math.isinf(t_r) else f"{t_r:.2f} s"
            if not math.isinf(t_r):
                v_son = float(np.max(np.abs(v_ort[int(np.searchsorted(t, t_r)):]))) if t_r < t[-1] else 0.0
                if v_son > 2 * sa.durma_hizi:
                    notlar.append(f"toparlandıktan sonra yavaş salınım: ortalama hız {v_son:.2f} m/s'ye çıkıyor")
        else:
            i0 = deger_at(a.t_komut)
            buyukluk = x if a.tur == "oteleme" else psi
            esik = sa.tepki_esigi if a.tur == "oteleme" else 2 * DERECE
            hareket = np.abs(buyukluk - buyukluk[i0]) > esik
            hareket[:i0] = False
            j = _ilk_indeks(hareket)
            tepki = (t[j] - a.t_komut) if j is not None else math.inf
            ib0, ib1 = deger_at(a.pencere[0]), deger_at(a.pencere[1])
            yapilan = float(buyukluk[ib1] - buyukluk[i0]) if ib1 > i0 else 0.0
            if a.tur == "oteleme":
                tol = sa.mesafe_toleransi * abs(a.beklenen)
                miktar_ok = abs(yapilan - a.beklenen) <= tol
                hiz = np.abs(v_ort[ib0:ib1 + 1])
                dur_ok = bool(hiz.size) and float(np.max(hiz)) <= sa.durma_hizi
                kosullar.append((f"≈{abs(a.beklenen):.1f} m (±%{100 * sa.mesafe_toleransi:.0f})", miktar_ok, f"{yapilan:+.3f} m"))
                bekleme = a.pencere[1] - a.pencere[0]
                kosullar.append((f"{bekleme:.0f} s durur (ortalama |v| ≤ {sa.durma_hizi:.2f} m/s)", dur_ok,
                                 f"en çok {float(np.max(hiz)) if hiz.size else float('nan'):.3f} m/s"))
                deger = f"{yapilan:+.3f} m"
            else:
                miktar_ok = abs(yapilan - a.beklenen) <= sa.aci_toleransi
                hiz = np.abs(w_ort[ib0:ib1 + 1]) * kay.gv["d_yari"]
                dur_ok = bool(hiz.size) and float(np.max(hiz)) <= sa.durma_hizi
                kosullar.append((f"≈{_deg(abs(a.beklenen)):.0f}° (±{_deg(sa.aci_toleransi):.0f}°)", miktar_ok, f"{_deg(yapilan):+.1f}°"))
                kosullar.append(("Durur (teker hızı ≤ durma hızı)", dur_ok, f"en çok {float(np.max(hiz)) if hiz.size else float('nan'):.3f} m/s"))
                deger = f"{_deg(yapilan):+.1f}°"
            if a.ad.startswith("Ö2"):
                kosullar.append((f"Tepki ≤ {sa.komut_tepki_suresi:.0f} s", tepki <= sa.komut_tepki_suresi,
                                 "yok" if math.isinf(tepki) else f"{tepki:.2f} s"))
        if kay.gv["kutulu"]:
            kosullar.append(("Kutu düşmez", not kutu_dustu, f"görünür eğim en çok {o['kutu_alfa']:.1f}° (0,1 s ortalama)"))
            if kutu_kaydi and not kutu_dustu:
                notlar.append(f"kutu yuvada kayar (görünür eğim {o['kutu_alfa']:.1f}° > sürtünme açısı "
                              f"{_deg(kay.gv['kutu_surtunme_acisi']):.1f}°), duvar tutar")
        kosullar.append(("Sigorta atmaz (1 s etkin akım)", sigorta, f"{o['rms1_akim']:.2f} A"))
        gecti = all(k[1] for k in kosullar)
        neden = None
        if not gecti:
            if t_bitti <= bitis + 1e-9:
                neden = dusme_nedeni(kay, Ts)
            else:
                neden = "; ".join(f"{ad}: {deg}" for ad, ok, deg in kosullar if not ok)
        sonuclar.append({"ad": a.ad, "gecti": gecti, "deger": deger, "kosullar": kosullar, "notlar": notlar, "neden": neden})
    return {"kod": kay.kod, "kurulum": asdict(kay.kurulum), "alt": sonuclar, "olcutler": o,
            "gecti": all(s["gecti"] for s in sonuclar), "dustu": kay.dustu, "dongu_asimi": kay.dongu_asimi}
