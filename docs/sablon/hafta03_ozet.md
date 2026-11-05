<!-- Bu dosya bir şablondur. Özet `python -m denge` ile docs/hafta03_toplanti_ozeti.md olarak üretilir; doğrudan çıktıyı düzenlemeyin. -->
# 3. Hafta Toplantı Özeti

**Sefa Nurali Uçak (23015008)** · Kontrol ve Otomasyon, Modül A ve E · 19 Ekim 2026 (motor tipi eki: @@tarih@@) · Tam belge: [hafta03_model_tork_km.md](hafta03_model_tork_km.md)

## Danışmanın istediği

"Ters sarkaç matematiksel modeli, motor tork/hız hesapları ve ilaç kutusu yuvasının kütle merkezi analizi dokümanı."

## Ne yaptık

- Robotun hareket denklemlerini çıkardık ve denge, ileri gitme, dönüş için bir bilgisayar modeli kurduk. Model PID, LQR ve MPC'nin üçüne de temel olabilir.
- Parçalar henüz alınmadığı için bütün değerleri tek bir parametre dosyasında, kaynaklarıyla topladık. Malzemeler ön malzeme listesinden alındı; Mete'nin seçimiyle kesinleşecek. Hiçbir değer henüz ölçülmedi.
- Gereken motor torkunu, devri ve enkoder çözünürlüğünü hesapladık, aday DC motoru sınadık, step motor seçeneğini yan yana koyduk.
- İlaç kutusu yuvası için üç konumu karşılaştırdık. Belge ve şekiller tek komutla parametre dosyasından üretiliyor; @@pytest_kisa@@.

## Ana sonuçlar

1. Robot motorlar çalışmadan dik duramaz: eğim hatası yaklaşık her @@tau_zaman@@ ms'de 2,7 katına büyür. Saniyede 200 kez çalışan bir denge döngüsü bunun için yeterli. ([§3.6](@@bag_3_6@@))
2. Motorlar kapalıyken ±10°'den bırakılan robot @@t_hepsi_min@@–@@t_hepsi_max@@ s içinde düşer. 4. haftanın pasif kararlılık testi (5 s) tasarım gereği geçer. ([§3.7](@@bag_3_7@@))
3. ±10°'den toparlanmak için motor başına @@tA@@ N·m (@@tA_kgfcm@@ kgf·cm, 2 kat emniyetle) gerekir, yaklaşık @@nA@@ dev/dk'da. Zemin motor başına @@cekis_motor@@ N·m'den fazlasını aktaramaz, bu yüzden asıl sınırı teker kayması koyar. ([§4.2](@@bag_4_2@@), [§4.4](@@bag_4_4@@))
4. Enkoder teker turu başına en az @@cpr_min@@ sayım vermeli. ([§4.6](@@bag_4_6@@))
5. Kutu robot ağırlığının %@@kutu_orani@@'idir ve dengeyi neredeyse değiştirmez (düşme hızı %@@dp_oner@@ değişir). Aynı ayarlar kutulu ve kutusuz çalışır. ([§5.2](@@bag_5_2@@))
6. Gövde en fazla ileri @@temas@@°, geri @@temas_geri@@° eğilebilir; daha fazlasında tekerler dışında bir parça yere değer ve test düşer. ([§5.6](@@bag_5_6@@))

## Öneriler ve kararlar

- **Motor tipi: önce bir motorla ölçüm; geçerse step, geçmezse DC 333 RPM.** Step motor (17HS4401 + DRV8825) boş bataryada @@st_sf_alt@@–@@st_sf_ust@@ kat pay (DC: @@st_sf_dc@@) ve yaklaşık @@st_c_fark@@ TL tasarruf gösteriyor; sürücüler alındı. Bedeli: toplamda @@st_dm@@ kg fazla kütle, ≈ @@st_h_dc@@ yerine @@st_h@@ saat pil, adım kaçarsa robotun düşmesi. Bu motorun tork-hız eğrisi bulunamadı, kardeş motorlardan tahmin edildi; ölçülmeden kesin değildir. Ölçüt: @@V_min@@ V'ta 30–150 dev/dk'da en az @@st_esik_gecer@@ N·cm. ([§10.11](@@bag_10_11@@))
- **DC seçilirse 333 RPM.** 530 RPM varyantı boş bataryada yalnız @@sf_min@@ kat pay bırakır, enkoderi de sınırın altındadır (@@cpr_aday@@ < @@cpr_min@@ sayım). ([§4.7](@@bag_4_7@@))
- **Kutu yuvası: üst plaka.** Tekerlek aksının tam üstünde; kutu yatık ve uzun kenarı yana bakar; boşluk en fazla @@bosluk@@ mm. Kamera kutuyu görür, kutu test başında kolay konur, iç yerleşim değişmez. ([§5.5](@@bag_5_5@@))

## Bekleyenler

- **Mete'den:** batarya ve BMS kesim gerilimi, kat yerleşimi ve plaka ölçüleri, ölçüm için bir 17HS4401, motor kararından sonra satıcının veri sayfası ve sigorta değeri. ([§7](@@bag_7@@))
- **Ölçülecek:** 17HS4401'in sargısı ve 12 V / @@V_min@@ V tork-hız eğrisi ([§10.10](@@bag_10_10@@)); DC seçilirse rotor ataleti; aspirin kutusunun (500 mg, 20 tablet) ölçüsü ve kütlesi, bütün parçaların kütleleri.
- **Danışmana sorular:** (1) Şartnamede hareket süresi yok; 1 m'yi @@o1_sure@@ s'de almayı hedefledik, uygun mu? (2) Bu hafta donanım olmadığı için 1. ölçütte canlı simülasyon gösterimi kabul edilir mi? (3) IR ile istasyona yanaşma algoritması planda 10. haftada, ama 9. hafta toplantısında bu testin demosu bekleniyor; algoritmaya 8. haftada başlamamız uygun mu?

## Sonraki hafta: pasif kararlılık testi

- Mete ile: motorları ve tekerleri takılı gövde, gövdeye sabitlenmemiş kutu yuvası.
- Motorlar enerjisizken +10° ve −10°'den bırakma; kronometre ve video ile 5 s doğrulaması. Beklenen düşme süresi @@t_hepsi_min@@–@@t_hepsi_max@@ s; step motorun detent torku düşmeyi engellemez ([§10.9](@@bag_10_9@@)).
- Eğim için açıölçer veya eğim şablonu; IMU'nun şasiye montajı; parçaları tartıp parametre dosyasını güncellemek.

## Haftalık rubrik

| Ölçüt | Karşılayan |
|---|---|
| 1. Çalışır çıktı | Canlı: `python -m denge` (belge ve şekiller yeniden üretilir), `python -m denge.motor --dosyadaki-aday --oran-taramasi`, `python -m denge.step` |
| 2. Ölçüm ve doğrulama | `tests/` (@@pytest_kisa@@); Şekil 2 (kutuplar), Şekil 3 (düşme simülasyonu) |
| 3. Sistem entegrasyonu | Mete'den beklenen girdiler (§7), motor seçim diyagramı (Şekil 7), sigorta kontrolü (§4.7) |
| 4. Şartname ve İSG | Pasif test öngörüsü (Şekil 3), 12,6 V ≤ 24 V, yere değme açısı (§5.6), yuva gövdeye vidalanmaz |
| 5. Teknik dokümantasyon | Bu özet, tam belge, `parametreler.toml`, git geçmişi |

*Kaynaklar ve bütün hesaplar tam belgededir.*
