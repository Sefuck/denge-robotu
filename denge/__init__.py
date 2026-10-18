"""İki tekerlekli ev içi hasta destek robotu: Modül A & E dinamik modeli ve tasarım hesapları.

Modüller:
    parametreler  : parametreler.toml'u okur, doğrular, model parametrelerine çevirir
    kutle_merkezi : kütle merkezi, atalet, yere değme açısı, yuvadaki özgül kuvvet
    model         : Lagrange türetimi, doğrusallaştırma, durum-uzay, transfer fonksiyonları
    simulasyon    : açık çevrim düşme, referans manevralar (kontrolcüden bağımsız)
    motor         : tork/devir/enkoder gereksinimleri ve motor adayı değerlendirme
    yuva_analizi  : kutulu/kutusuz KM, kutu kayması, KM yüksekliği ve yuva konumu karşılaştırması
    rapor         : şekilleri ve 3. hafta dokümanını üretir (`python -m denge`)
"""
