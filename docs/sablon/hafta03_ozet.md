<!-- Bu dosya bir şablondur. Özet `python -m denge` ile docs/hafta03_toplanti_ozeti.md olarak üretilir; doğrudan çıktıyı düzenlemeyin. -->
# 3. Hafta Toplantı Özeti

**Sefa Nurali Uçak (23015008)** · Kontrol ve Otomasyon, Modül A ve E · 19 Ekim 2026 (ekler: step motor §10, satın alınan motor §11, simülasyon §12, @@tarih@@) · Tam belge: [hafta03_model_tork_km.md](hafta03_model_tork_km.md)

## Danışmanın istediği

"Ters sarkaç matematiksel modeli, motor tork/hız hesapları ve ilaç kutusu yuvasının kütle merkezi analizi dokümanı."

## Ne yaptık

- Robotun hareket denklemlerini çıkardık ve denge, ileri gitme, dönüş için bir bilgisayar modeli kurduk. Model PID, LQR ve MPC'nin üçüne de temel olabilir.
- Bütün değerleri tek bir parametre dosyasında, kaynaklarıyla topladık. Malzemeler ön malzeme listesinden alındı; Mete'nin seçimiyle kesinleşecek. Motorlar alındı, ama hiçbir değer henüz ölçülmedi.
- Gereken motor torkunu, devri ve enkoder çözünürlüğünü hesapladık; aday motorları, step seçeneğini ve satın alınan 1000 RPM motoru sınadık.
- Modelin üstüne kapalı çevrim bir simülasyon (dijital ikiz) kurduk: motor, pil, teker kayması, dişli boşluğu, IMU ve enkoder modeli, 200 Hz döngü, gecikmeler; PID ve LQR, Kalman ve tamamlayıcı süzgeç; şartnamedeki testler otomatik geçti/kaldı ile. Kontrolcü kodu ESP32'ye taşınabilir yazıldı.
- İlaç kutusu yuvası için üç konumu karşılaştırdık. Belge ve şekiller tek komutla parametre dosyasından üretiliyor; @@pytest_kisa@@.

## Ana sonuçlar

1. Robot motorlar çalışmadan dik duramaz: eğim hatası yaklaşık her @@tau_zaman@@ ms'de 2,7 katına büyür. Saniyede 200 kez çalışan bir denge döngüsü bunun için yeterli. ([§3.6](@@bag_3_6@@))
2. Motorlar kapalıyken ±10°'den bırakılan robot @@t_hepsi_min@@–@@t_hepsi_max@@ s içinde düşer. 4. haftanın pasif kararlılık testi (5 s) tasarım gereği geçer. ([§3.7](@@bag_3_7@@))
3. ±10°'den toparlanmak için motor başına @@tA@@ N·m (@@tA_kgfcm@@ kgf·cm, 2 kat emniyetle) gerekir, yaklaşık @@nA@@ dev/dk'da. Zemin motor başına @@cekis_motor@@ N·m'den fazlasını aktaramaz, bu yüzden asıl sınırı teker kayması koyar. ([§4.2](@@bag_4_2@@), [§4.4](@@bag_4_4@@))
4. Enkoder teker turu başına en az @@cpr_min@@ sayım vermeli. ([§4.6](@@bag_4_6@@))
5. Kutu robot ağırlığının %@@kutu_orani@@'idir ve dengeyi neredeyse değiştirmez (düşme hızı %@@dp_oner@@ değişir). Aynı ayarlar kutulu ve kutusuz çalışır. ([§5.2](@@bag_5_2@@))
6. Gövde en fazla ileri @@temas@@°, geri @@temas_geri@@° eğilebilir; daha fazlasında tekerler dışında bir parça yere değer ve test düşer. ([§5.6](@@bag_5_6@@))
7. Simülasyonda satın alınan motor, kutulu/kutusuz ve dolu/boş pilde final testlerinin @@ik_gecen_ana@@'ini geçti; ±10° yerine boş pilde @@ik_pay_1000_bos@@°'ye kadar toparlanıyor. Eğimi doğru ölçmek için ivmeölçerden robotun kendi ivmesini çıkarmak gerekiyor; çıkarılmazsa hareketli testler kalıyor. ([§12.7](@@bag_12_7@@), [§12.4](@@bag_12_4@@))

## Öneriler ve kararlar

- **Satın alınan 1000 RPM motor: @@sa_karar_kucuk@@** (el hesabı: boş pilde 2 kat yerine @@sa_sf_min@@ kat pay). **Simülasyon bu kararı yumuşattı:** 1000 RPM testleri geçiyor, 333 RPM ise daha fazla pay sağlamıyor (@@ik_pay_333_bos@@° / @@ik_pay_1000_bos@@°), çünkü yüksek oranda rotor ataleti ve sürtünme büyüyor. **Öneri: değişimi askıya alıp satın alınan motorla devam etmek ve önce ölçmek.** Step motor seçeneği §10'da duruyor. ([§11.6](@@bag_11_6@@), [§12.8](@@bag_12_8@@))
- **Kutu yuvası: üst plaka.** Tekerlek aksının tam üstünde; kutu yatık ve uzun kenarı yana bakar; boşluk en fazla @@bosluk@@ mm. Kamera kutuyu görür, kutu test başında kolay konur, iç yerleşim değişmez. ([§5.5](@@bag_5_5@@))

## Bekleyenler

- **Mete'den:** motor değişimi mümkün mü; değilse 1:3 kayışın mekaniği; batarya ve BMS kesim gerilimi, kat yerleşimi, sigorta değeri. ([§7](@@bag_7@@))
- **Ölçülecek (motorlar elimizde):** teker turu başına enkoder sayımı, boşta devir ve akım, @@V_min@@ V'ta kilitlenme torku (kol + mutfak tartısı) ve akımı, rotor ataleti (serbest yavaşlama) ve dişli boşluğu; değerler girilince karar ve simülasyon yeniden üretilir ([§11.5](@@bag_11_5@@), [§12.10](@@bag_12_10@@)). Ayrıca aspirin kutusunun ölçüsü ve kütlesi, parçaların kütleleri.
- **Ousmane ve Mohamad'dan:** eldivenden robota komut gecikmesinin ölçülmüş değeri (simülasyonda @@ik_gec_komut@@ s varsayıldı).
- **Danışmana sorular:** (1) Şartnamede hareket süresi yok; 1 m'yi @@o1_sure@@ s'de almayı hedefledik, uygun mu? (2) Bu hafta donanım olmadığı için 1. ölçütte canlı simülasyon gösterimi kabul edilir mi? (3) IR ile istasyona yanaşma algoritması planda 10. haftada, ama 9. hafta toplantısında bu testin demosu bekleniyor; algoritmaya 8. haftada başlamamız uygun mu?

## Sonraki hafta: pasif kararlılık testi

- Mete ile: motorları ve tekerleri takılı gövde, gövdeye sabitlenmemiş kutu yuvası.
- Motorlar enerjisizken +10° ve −10°'den bırakma; kronometre ve video ile 5 s doğrulaması. Beklenen düşme süresi @@t_hepsi_min@@–@@t_hepsi_max@@ s; step motorun detent torku düşmeyi engellemez ([§10.9](@@bag_10_9@@)).
- Eğim için açıölçer veya eğim şablonu; IMU'nun şasiye montajı; parçaları tartıp parametre dosyasını güncellemek.

## Haftalık rubrik

| Ölçüt | Karşılayan |
|---|---|
| 1. Çalışır çıktı | Canlı: `python -m denge.ikiz --senaryo O1-4+ --gif o.gif` (simülasyon ve animasyon), `python -m denge` (belge ve şekiller yeniden üretilir), `python -m denge.motor --satin-alinan --yan-yana` |
| 2. Ölçüm ve doğrulama | `tests/` (@@pytest_kisa@@); Şekil 3 (düşme), Şekil 14–18 ve `docs/simulasyon/sonuclar.csv` (simülasyon, geçti/kaldı) |
| 3. Sistem entegrasyonu | Mete'den beklenen girdiler (§7), motor seçim diyagramı (Şekil 7), sigorta kontrolü (§4.7) |
| 4. Şartname ve İSG | Pasif test öngörüsü (Şekil 3), 12,6 V ≤ 24 V, yere değme açısı (§5.6), yuva gövdeye vidalanmaz |
| 5. Teknik dokümantasyon | Bu özet, tam belge, `parametreler.toml`, git geçmişi |

*Kaynaklar ve bütün hesaplar tam belgededir.*
