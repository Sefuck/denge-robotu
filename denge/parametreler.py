"""parametreler.toml dosyasını okur, doğrular ve model/kütle merkezi nesnelerine çevirir."""

from __future__ import annotations

import copy
import math
import tomllib
from pathlib import Path

from .kutle_merkezi import Bilesen, GovdeOzellikleri, govde_ozellikleri
from .model import ModelParametreleri

KOK = Path(__file__).resolve().parent.parent
VARSAYILAN_YOL = KOK / "parametreler.toml"
GECERLI_DURUMLAR = {"tahmini", "site", "doğrulanamadı", "ölçülmüş", "şartname", "öneri", "sabit"}
# Robotun kendisine ait fiziksel parametreler: ölçülene kadar ölçülmüş sayılamaz.
# "site": başka bir grubun malzeme listesi (bağlayıcı değil); "doğrulanamadı": satıcı referans tablosu.
FIZIKSEL_BOLUMLER = ("teker", "motor", "batarya", "govde", "yuk.kutu", "yuk.yuva.kutle", "zemin", "elektrik", "motor_adayi", "motor_serisi")
FIZIKSEL_DURUMLAR = ("tahmini", "site", "doğrulanamadı", "ölçülmüş")

BILESEN_ADLARI = {
    "motor": "Motor + redüktör + enkoder",
    "sasi": "Şasi yapısı",
    "elektronik": "Elektronik (MCU, IMU, sürücü, BMS)",
    "batarya": "Batarya paketi",
    "acil_durdurma": "Acil durdurma anahtarı",
    "ir_ve_sarj_kontaklari": "IR alıcı + şarj kontakları",
}


def fiziksel_mi(yol: str) -> bool:
    """Robotun kendisine ait (ölçülene kadar tahmini) bir parametre mi?"""
    return any(yol == b or yol.startswith(b + ".") for b in FIZIKSEL_BOLUMLER)


def parametre_kayitlari(veri: dict, onek: str = "") -> list[tuple[str, dict]]:
    """İçinde 'deger' anahtarı olan her tabloyu (yaprak parametre) noktalı yoluyla döndürür."""
    kayitlar = []
    for anahtar, deger in veri.items():
        if isinstance(deger, dict):
            yol = f"{onek}.{anahtar}" if onek else anahtar
            if "deger" in deger:
                kayitlar.append((yol, deger))
            else:
                kayitlar.extend(parametre_kayitlari(deger, yol))
    return kayitlar


def dogrula(veri: dict) -> None:
    """Her parametrede birim/durum/kaynak var mı, durum geçerli mi, değer aralıkta mı?"""
    hatalar = []
    for yol, k in parametre_kayitlari(veri):
        for alan in ("birim", "durum", "kaynak"):
            if not str(k.get(alan, "")).strip():
                hatalar.append(f"{yol}: '{alan}' alanı eksik")
        if k.get("durum") not in GECERLI_DURUMLAR:
            hatalar.append(f"{yol}: geçersiz durum {k.get('durum')!r}")
        if fiziksel_mi(yol) and k.get("durum") not in FIZIKSEL_DURUMLAR:
            hatalar.append(f"{yol}: fiziksel parametrenin durumu {FIZIKSEL_DURUMLAR} içinden olmalı")
        if k.get("durum") == "doğrulanamadı" and "[doğrulanamadı]" not in k.get("kaynak", ""):
            hatalar.append(f"{yol}: 'doğrulanamadı' durumundaki kaynakta [doğrulanamadı] etiketi olmalı")
        if k.get("durum") == "site" and "site" not in k.get("kaynak", "").lower():
            hatalar.append(f"{yol}: 'site' durumundaki kaynak siteyi anmalı")
        if "aralik" in k and isinstance(k["deger"], (int, float)):
            alt, ust = k["aralik"]
            if not alt <= k["deger"] <= ust:
                hatalar.append(f"{yol}: {k['deger']} aralık dışında {k['aralik']}")
    if hatalar:
        raise ValueError("Parametre dosyası hatalı:\n  " + "\n  ".join(hatalar))


class Tasarim:
    """Parametre dosyasının doğrulanmış hâli ve ondan türetilen büyüklükler."""

    def __init__(self, veri: dict):
        dogrula(veri)
        self.veri = veri

    @classmethod
    def yukle(cls, yol: str | Path | None = None) -> Tasarim:
        with open(yol or VARSAYILAN_YOL, "rb") as f:
            return cls(tomllib.load(f))

    def kayit(self, yol: str) -> dict:
        dugum = self.veri
        for parca in yol.split("."):
            dugum = dugum[parca]
        return dugum

    def d(self, yol: str):
        """Parametrenin değeri, ör. d('teker.yaricap')."""
        return self.kayit(yol)["deger"]

    def kayitlar(self) -> list[tuple[str, dict]]:
        return parametre_kayitlari(self.veri)

    def degistir(self, degisiklikler: dict) -> Tasarim:
        """Bazı değerleri değiştirilmiş yeni bir Tasarim (duyarlılık analizi için)."""
        yeni = copy.deepcopy(self.veri)
        for yol, deger in degisiklikler.items():
            dugum = yeni
            for parca in yol.split("."):
                dugum = dugum[parca]
            dugum["deger"] = deger
            dugum.pop("aralik", None)
        return Tasarim(yeni)

    # -- yük ve yuva ----------------------------------------------------------
    def kutu_merkez_z(self, yuva: str | None = None) -> float:
        yuva = yuva or self.d("yuk.yuva.onerilen")
        return self.d(f"yuk.yuva.secenek.{yuva}") + self.d("yuk.kutu.boyut")[2] / 2

    def bilesenler(
        self,
        kutulu: bool = True,
        yuva: str | None = None,
        z_kutu: float | None = None,
        kayma: tuple[float, float] = (0.0, 0.0),
        z_batarya: float | None = None,
    ) -> list[Bilesen]:
        """Gövde bileşen listesi (tekerler hariç).

        yuva    : 'ust' | 'orta' | 'alt' (varsayılan: önerilen seçenek)
        z_kutu  : kutu merkezinin yüksekliğini doğrudan verir (tarama için)
        kayma   : kutunun yuvada (x, y) kayması [m]
        z_batarya: bataryanın yüksekliğini değiştirir (tarama için)
        """
        liste = []
        for ad, etiket in BILESEN_ADLARI.items():
            b = self.veri["govde"][ad]
            x, y, z = b["konum"]["deger"]
            if ad == "batarya" and z_batarya is not None:
                z = z_batarya
            boyut = tuple(b["boyut"]["deger"])
            m = b["kutle"]["deger"]
            if b.get("simetrik_y"):
                liste.append(Bilesen(f"{etiket} (sol)", m, (x, y, z), boyut, ad))
                liste.append(Bilesen(f"{etiket} (sağ)", m, (x, -y, z), boyut, ad))
            else:
                liste.append(Bilesen(etiket, m, (x, y, z), boyut, ad))

        kx, ky, kz = self.d("yuk.kutu.boyut")
        zk = z_kutu if z_kutu is not None else self.kutu_merkez_z(yuva)
        z_taban = zk - kz / 2
        x_yuva = self.d("yuk.yuva.x")
        h_duvar = self.d("yuk.yuva.duvar_yuksekligi")
        pay = 2 * self.d("yuk.yuva.bosluk") + 0.006  # boşluk + 3 mm duvar kalınlığı (her iki yanda)
        liste.append(
            Bilesen("Kutu yuvası", self.d("yuk.yuva.kutle"), (x_yuva, 0.0, z_taban + h_duvar / 2), (kx + pay, ky + pay, h_duvar), "yuva")
        )
        if kutulu:
            liste.append(Bilesen("İlaç kutusu", self.d("yuk.kutu.kutle"), (x_yuva + kayma[0], kayma[1], zk), (kx, ky, kz), "kutu"))
        return liste

    def govde(self, **kw) -> GovdeOzellikleri:
        return govde_ozellikleri(self.bilesenler(**kw))

    def model(self, **kw) -> ModelParametreleri:
        """Bileşen bütçesinden model parametreleri (kw → bilesenler())."""
        g = self.govde(**kw)
        r = self.d("teker.yaricap")
        m_w = self.d("teker.kutle")
        J_w = self.d("teker.atalet_katsayisi") * m_w * r**2
        return ModelParametreleri(
            m_b=g.kutle,
            l=math.hypot(g.km[0], g.km[2]) * (1 if g.km[2] >= 0 else -1),
            I_xx=g.atalet[0, 0],
            I_yy=g.atalet[1, 1],
            I_zz=g.atalet[2, 2],
            m_w=m_w,
            J_w=J_w,
            K_w=J_w / 2,  # ince disk: çap ekseni ataleti dönme ekseninin yarısı
            r=r,
            d=self.d("teker.iz_genisligi"),
            J_m=self.d("motor.rotor_ataleti_yansimis"),
            b=self.d("motor.viskoz_surtunme"),
            g=self.d("sabit.g"),
        )

    def toplam_kutle(self, **kw) -> float:
        return self.govde(**kw).kutle + 2 * self.d("teker.kutle")

    def batarya_gerilimleri(self) -> dict:
        n = self.d("batarya.seri_hucre")
        return {
            "min": n * self.d("batarya.hucre_gerilimi_min"),
            "nominal": n * self.d("batarya.hucre_gerilimi_nominal"),
            "max": n * self.d("batarya.hucre_gerilimi_max"),
        }

    def govde_noktalari(self) -> dict[str, tuple[float, float]]:
        """Yere değme açısı için gövdenin dış noktaları (x, z)."""
        (x0, x1), (z0, z1) = self.d("govde.zarf.x_aralik"), self.d("govde.zarf.z_aralik")
        noktalar = {
            "Gövde alt-ön köşe": (x1, z0),
            "Gövde alt-arka köşe": (x0, z0),
            "Gövde üst-ön köşe": (x1, z1),
            "Gövde üst-arka köşe": (x0, z1),
        }
        b = self.veri["govde"]["ir_ve_sarj_kontaklari"]
        x, _, z = b["konum"]["deger"]
        dx, _, dz = b["boyut"]["deger"]
        noktalar["IR/kontak modülü alt köşe"] = (x + dx / 2, z - dz / 2)
        noktalar["IR/kontak modülü üst köşe"] = (x + dx / 2, z + dz / 2)
        if "braket_alt_kose" in self.veri["govde"]:
            bx, bz = self.d("govde.braket_alt_kose")
            noktalar["Motor braketi alt-ön köşe"] = (bx, bz)
            noktalar["Motor braketi alt-arka köşe"] = (-bx, bz)
        return noktalar
