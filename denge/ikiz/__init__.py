"""Dijital ikiz: robotun kapalı çevrim simülasyonu (belge §12).

Modüller:
    ayarlar    : parametreler.toml'dan ikizin bütün ayarlarını okur (fizik, motor, sensör, zamanlama, kontrol)
    fizik      : doğrusal olmayan hareket denklemleri; teker kayması, redüktör boşluğu, DC motor ve pil modeli
    sensorler  : MPU6050 (gürültü, sapma, alçak geçiren süzgeç, nicemleme) ve enkoder (sayım nicemlemesi)
    kestirim   : tamamlayıcı süzgeç ve Kalman süzgeci (ESP32'ye taşınabilir, sabit adımlı)
    kontrol    : PID ve LQR (aynı arayüz), referans üreteci, çıkış katı (tork → PWM); LQR tasarım aracı
    senaryolar : şartname testleri (Ö1-1 … Ö2), çalıştırıcı, ölçütler, geçti/kaldı ve düşme nedeni
    cizim      : zaman grafikleri ve 2D animasyon (GIF)
    rapor_bolumu: belge §12 için tablolar, şekiller ve yer tutucular

Komut satırı: python -m denge.ikiz --help
"""
