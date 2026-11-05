<!-- Otomatik üretildi (python -m denge). Düzenlemek için docs/sablon/hafta03_ozet.md ve parametreler.toml dosyalarını değiştirin. -->
# 3. Hafta Toplantı Özeti

**Sefa Nurali Uçak (23015008)** · Kontrol ve Otomasyon, Modül A ve E · 19 Ekim 2026 (motor tipi eki: 06.11.2026) · Tam belge: [hafta03_model_tork_km.md](hafta03_model_tork_km.md)

## Danışmanın istediği

"Ters sarkaç matematiksel modeli, motor tork/hız hesapları ve ilaç kutusu yuvasının kütle merkezi analizi dokümanı."

## Ne yaptık

- Robotun hareket denklemlerini çıkardık ve denge, ileri gitme, dönüş için bir bilgisayar modeli kurduk. Model PID, LQR ve MPC'nin üçüne de temel olabilir.
- Parçalar henüz alınmadığı için bütün değerleri tek bir parametre dosyasında, kaynaklarıyla topladık. Malzemeler ön malzeme listesinden alındı; Mete'nin seçimiyle kesinleşecek. Hiçbir değer henüz ölçülmedi.
- Gereken motor torkunu, devri ve enkoder çözünürlüğünü hesapladık, aday DC motoru sınadık, step motor seçeneğini yan yana koyduk.
- İlaç kutusu yuvası için üç konumu karşılaştırdık. Belge ve şekiller tek komutla parametre dosyasından üretiliyor; 113 doğrulama testinin hepsi geçti.

## Ana sonuçlar

1. Robot motorlar çalışmadan dik duramaz: eğim hatası yaklaşık her 88 ms'de 2,7 katına büyür. Saniyede 200 kez çalışan bir denge döngüsü bunun için yeterli. ([§3.6](hafta03_model_tork_km.md#36-transfer-fonksiyonları-ve-açık-çevrim-kutuplar))
2. Motorlar kapalıyken ±10°'den bırakılan robot 0,24–0,40 s içinde düşer. 4. haftanın pasif kararlılık testi (5 s) tasarım gereği geçer. ([§3.7](hafta03_model_tork_km.md#37-açık-çevrim-düşme-simülasyonu-10))
3. ±10°'den toparlanmak için motor başına 0,196 N·m (2,0 kgf·cm, 2 kat emniyetle) gerekir, yaklaşık 111 dev/dk'da. Zemin motor başına 0,146 N·m'den fazlasını aktaramaz, bu yüzden asıl sınırı teker kayması koyar. ([§4.2](hafta03_model_tork_km.md#42-10den-toparlanma-torku-istenen-el-hesabı), [§4.4](hafta03_model_tork_km.md#44-çekiş-sınırı))
4. Enkoder teker turu başına en az 1021 sayım vermeli. ([§4.6](hafta03_model_tork_km.md#46-enkoder-gereksinimi))
5. Kutu robot ağırlığının %3,8'idir ve dengeyi neredeyse değiştirmez (düşme hızı %−1,4 değişir). Aynı ayarlar kutulu ve kutusuz çalışır. ([§5.2](hafta03_model_tork_km.md#52-kutulu-ve-kutusuz-km))
6. Gövde en fazla ileri 58,9°, geri 74,2° eğilebilir; daha fazlasında tekerler dışında bir parça yere değer ve test düşer. ([§5.6](hafta03_model_tork_km.md#56-yere-değme-açısı))

## Öneriler ve kararlar

- **Motor tipi: önce bir motorla ölçüm; geçerse step, geçmezse DC 333 RPM.** Step motor (17HS4401 + DRV8825) boş bataryada 2,19–2,88 kat pay (DC: 1,96) ve yaklaşık 1319 TL tasarruf gösteriyor; sürücüler alındı. Bedeli: toplamda 0,30 kg fazla kütle, ≈ 5,1 yerine 2,2 saat pil, adım kaçarsa robotun düşmesi. Bu motorun tork-hız eğrisi bulunamadı, kardeş motorlardan tahmin edildi; ölçülmeden kesin değildir. Ölçüt: 9,9 V'ta 30–150 dev/dk'da en az 19,6 N·cm. ([§10.11](hafta03_model_tork_km.md#1011-karşılaştırma-ve-öneri))
- **DC seçilirse 333 RPM.** 530 RPM varyantı boş bataryada yalnız 1,60 kat pay bırakır, enkoderi de sınırın altındadır (827 < 1021 sayım). ([§4.7](hafta03_model_tork_km.md#47-aday-motor-jgb37-520-12-v-530-rpm-hall-enkoderli-meteye-öneri))
- **Kutu yuvası: üst plaka.** Tekerlek aksının tam üstünde; kutu yatık ve uzun kenarı yana bakar; boşluk en fazla 2 mm. Kamera kutuyu görür, kutu test başında kolay konur, iç yerleşim değişmez. ([§5.5](hafta03_model_tork_km.md#55-yuva-konumu-karşılaştırması-ve-öneri))

## Bekleyenler

- **Mete'den:** batarya ve BMS kesim gerilimi, kat yerleşimi ve plaka ölçüleri, ölçüm için bir 17HS4401, motor kararından sonra satıcının veri sayfası ve sigorta değeri. ([§7](hafta03_model_tork_km.md#7-meteden-ve-diğer-üyelerden-beklenen-girdiler))
- **Ölçülecek:** 17HS4401'in sargısı ve 12 V / 9,9 V tork-hız eğrisi ([§10.10](hafta03_model_tork_km.md#1010-ölçüm-planı)); DC seçilirse rotor ataleti; aspirin kutusunun (500 mg, 20 tablet) ölçüsü ve kütlesi, bütün parçaların kütleleri.
- **Danışmana sorular:** (1) Şartnamede hareket süresi yok; 1 m'yi 4 s'de almayı hedefledik, uygun mu? (2) Bu hafta donanım olmadığı için 1. ölçütte canlı simülasyon gösterimi kabul edilir mi? (3) IR ile istasyona yanaşma algoritması planda 10. haftada, ama 9. hafta toplantısında bu testin demosu bekleniyor; algoritmaya 8. haftada başlamamız uygun mu?

## Sonraki hafta: pasif kararlılık testi

- Mete ile: motorları ve tekerleri takılı gövde, gövdeye sabitlenmemiş kutu yuvası.
- Motorlar enerjisizken +10° ve −10°'den bırakma; kronometre ve video ile 5 s doğrulaması. Beklenen düşme süresi 0,24–0,40 s; step motorun detent torku düşmeyi engellemez ([§10.9](hafta03_model_tork_km.md#109-pasif-kararlılık-testi-detent-düşmeyi-engeller-mi)).
- Eğim için açıölçer veya eğim şablonu; IMU'nun şasiye montajı; parçaları tartıp parametre dosyasını güncellemek.

## Haftalık rubrik

| Ölçüt | Karşılayan |
|---|---|
| 1. Çalışır çıktı | Canlı: `python -m denge` (belge ve şekiller yeniden üretilir), `python -m denge.motor --dosyadaki-aday --oran-taramasi`, `python -m denge.step` |
| 2. Ölçüm ve doğrulama | `tests/` (113 doğrulama testinin hepsi geçti); Şekil 2 (kutuplar), Şekil 3 (düşme simülasyonu) |
| 3. Sistem entegrasyonu | Mete'den beklenen girdiler (§7), motor seçim diyagramı (Şekil 7), sigorta kontrolü (§4.7) |
| 4. Şartname ve İSG | Pasif test öngörüsü (Şekil 3), 12,6 V ≤ 24 V, yere değme açısı (§5.6), yuva gövdeye vidalanmaz |
| 5. Teknik dokümantasyon | Bu özet, tam belge, `parametreler.toml`, git geçmişi |

*Kaynaklar ve bütün hesaplar tam belgededir.*
