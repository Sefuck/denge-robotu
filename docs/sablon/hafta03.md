<!-- Bu dosya bir şablondur. Doküman `python -m denge` ile docs/hafta03_model_tork_km.md olarak üretilir; doğrudan çıktıyı düzenlemeyin. -->
# 3. Hafta: Ters Sarkaç Modeli, Motor Tork/Devir Hesapları ve İlaç Kutusu Yuvası Kütle Merkezi Analizi

| | |
|---|---|
| **Proje** | YTÜ EEF Çok Disiplinli Tasarım Projesi, 2026-2027 Güz: İki Tekerlekli Ev İçi Hasta Destek Robotu |
| **Hazırlayan** | Sefa Nurali Uçak (23015008), Kontrol ve Otomasyon Mühendisliği, Modül A ve E |
| **Toplantı** | 3. hafta danışman toplantısı, 19 Ekim 2026 (Parça Seçimi, Mimari ve Tasarım Toplantısı) |
| **Belge** | Parametre sürümü @@surum@@, üretim @@tarih@@. `parametreler.toml` dosyasından `python -m denge` ile üretilir. |

> **Danışman planındaki teslimat:** "Ters sarkaç matematiksel modeli, motor tork/hız hesapları ve ilaç kutusu yuvasının kütle merkezi analizi dokümanı."
>
> **Durum:** Motor, teker ve batarya henüz alınmadı; **hiçbir fiziksel parametre ölçülmedi** (§2). Ön malzeme listesi, cdtp-robot.netlify.app'teki referans malzeme listesinden derlendi; Mete'nin seçimiyle kesinleşecek. Bu değerler belgede "ön liste" diye işaretlidir. Motor veri sayfası değerleri rcdrone referans tablosundan alındı ("[doğrulanamadı]"); listede olmayan değerler tahmini kaldı. Her değerin kaynağı ve makul aralığı parametre dosyasında yazılıdır. Parçalar gelince değerler ölçülecek, dosya güncellenecek ve belge aynı komutla yeniden üretilecek. Kontrolcü tasarlanmadı: kontrol yöntemi 6. haftada seçilecek. Model PID, LQR ve MPC'nin üçüne de temel olacak biçimde verilmiştir.

## Özet

| Büyüklük | Değer | Bölüm |
|---|---|---|
| Toplam kütle (kutulu / kutusuz) | @@m_toplam@@ / @@m_toplam_kutusuz@@ kg | §2 |
| Aks → KM uzaklığı $l$ (kutusuz / kutulu, üst yuva) | @@l0@@ / @@l1@@ mm | §5.2 |
| Açık çevrim kararsız kutup (kutulu) | +@@p@@ 1/s (zaman sabiti @@tau_zaman@@ ms) | §3.6 |
| ±10°'den bırakılınca gövdenin yere değmesi (motorlar enerjisiz) | @@t_hepsi_min@@–@@t_hepsi_max@@ s (serbest/kilitli teker, ileri/geri) | §3.7 |
| ±10° toparlanma torku, istenen el hesabı (iki motor toplamı) | @@el_toplam@@ N·m | §4.2 |
| Aynı iş, tam model, $T$ = @@T_ref@@ s referans manevra ($J_m$ = 0 … @@jm_ust@@ kg·m²) | @@tepe_ref@@ … @@tepe_ref_jm_ust@@ N·m | §4.3 |
| **Önerilen motor gereksinimi** (motor başına, teker milinde, batarya min. geriliminde) | **≥ @@tA@@ N·m (@@tA_kgfcm@@ kgf·cm) @ @@nA@@ dev/dk; boşta devir > @@nB@@ dev/dk** | §4.5 |
| Enkoder | ≥ @@cpr_min@@ sayım / teker devri (x4 kod çözme sonrası) | §4.6 |
| **Aday motor (ön liste): @@aday_ad@@** | Katsayısız @@aday_gecer_SFsiz@@, SF = @@SF@@ ile @@aday_gecer_SF@@ (boş bataryada SF @@sf_min@@); öneri: **@@en_iyi_ad@@** (SF @@en_iyi_sf@@) | §4.7 |
| **Motor tipi: step seçeneği** (geçici eğri, [doğrulanamadı]) | Boş bataryada SF @@st_sf_alt@@–@@st_sf_ust@@ (DC 333 RPM: @@st_sf_dc@@); +@@st_dm@@ kg; pil ≈ @@st_h@@ saat (DC: ≈ @@st_h_dc@@); ≈ @@st_c_fark@@ TL ucuz. Öneri: bir motorla ölç, geçerse step + AS5600 | §10 |
| **Önerilen yuva** | Üst plakada, aksın tam üstünde ($x = y = 0$), kutu yatık ve uzun kenarı yanal; boşluk ≤ @@bosluk@@ mm, duvar ≈ @@duvar@@ mm | §5.5 |

**Öne çıkan bulgular**

1. **El hesabı ($m g l \sin 10° + J_O\ddot\theta$) muhafazakârdır, ama ne kadar muhafazakâr olduğu bilinmeyen motora bağlıdır.** Rotor ataleti ihmal edilirse ($J_m = 0$) tam modelde 10°'de tutma torku $m g l \sin 10°$'nin yalnızca %@@tutma_oran@@'idir, çünkü tekeri ileri iten tork gövdeyi de doğrultur. Ancak teker miline yansıyan rotor ataleti $J_m = J_\text{rotor} N^2$ arttıkça bu etki kaybolur: $J_m$ = @@jm_ust@@ kg·m²'de tutma torku @@tutma_jm_kat@@ katına çıkar ve referans manevra @@jm_karsilastirma@@. Motor seçilene kadar el hesabı × emniyet katsayısı tasarım değeri olarak tutuldu (§4.3).
2. **Çekiş sınırı:** Zemine aktarılabilecek en büyük toplam tork ≈ @@cekis@@ N·m'dir (μ = @@mu@@). Önerilen motor gereksinimi bunun üstündedir. Bu, böyle bir motorda tork darboğazı olmayacağı, sınırı zeminin koyacağı anlamına gelir. Kontrolcünün tork doyumu çekiş sınırına göre ayarlanmalıdır [öneri].
3. **$\sqrt{g/l}$ bu robot için yanıltıcıdır.** Tekerler hafif olduğundan serbest tekerli açık çevrim kutbu KM yüksekliğiyle monoton değişmez: batarya @@bt_z_min@@ → @@bt_z_max@@ cm taşınınca kutup @@bt_p_min@@ … @@bt_p_max@@ 1/s aralığında kalır. $\sqrt{g/l}$ ise @@bt_kok_max@@ → @@bt_kok_min@@ 1/s düşüş öngörür. Buna karşılık 10°'deki statik tork %@@bt_tau_artis@@ artar (§5.4).
4. **Kutunun dengeye etkisi küçüktür.** Kutu (@@kutu_kutle@@ g, tahmini) toplam kütlenin %@@kutu_orani@@'idir. Üst yuvada kutu eklenince $l$ @@dl_oner@@ mm artar, kutup %@@dp_oner@@ değişir. Bu yüzden aynı kazançlar kutulu ve kutusuz çalışmalıdır. Final testlerinin hepsi kutulu olduğundan kazançlar yine de kutuyla ayarlanmalıdır [öneri] (§5.2).
5. **Yere değme açısı ileri @@temas@@°, geri @@temas_geri@@°'dir.** İleride sınırı @@temas_nokta@@ belirler. Toparlanmadaki aşım bu açıya yaklaşırsa iki teker dışında bir parça yere değer ve alt test düşer (şartname §7). Aksa teker yarıçapından yakın parçalar hiç değmez (motor braketleri böyle) [öneri] (§5.6).
6. **Pasif kararlılık ön testi tasarım gereği sağlanır.** KM aksın üstünde olduğu sürece robot enerjisizken ±10°'den @@t_hepsi_min@@–@@t_hepsi_max@@ s içinde düşer, yani 5 s sınırının yaklaşık @@pasif_kat@@ katı payla. KM aksın altına inerse robot pasif kararlı olur ve şartname §4.1 ihlal edilir; bu durum testlerde yakalanır (§3.7).
7. **Ön listedeki aday motor (@@aday_ad@@) katsayısız yeterli, SF = @@SF@@ ile değil.** Boş bataryada (@@V_min@@ V) A noktasında @@aday_tauA@@ N·m verir; katsayısız gereksinim @@tA0@@, SF'li @@tA@@ N·m. Sağladığı katsayı @@sf_min@@ (nominal gerilimde @@sf_nom@@). Aynı fiyattaki @@en_iyi_ad@@ varyantı boş bataryada SF @@en_iyi_sf@@ (nominalde @@en_iyi_sf_nom@@) sağlar, enkoder çözünürlüğünü de karşılar. Mete'ye öneri §4.7'de.
8. **Step motor hesapta yeterli görünüyor, ama eğrisi ölçülmedi.** 17HS4401'in pull-out eğrisi bulunamadı; kardeş motorlardan türetilen geçici eğriyle boş bataryada SF @@st_sf_alt@@–@@st_sf_ust@@ çıkar, rezonans çukuruna denk gelirse @@st_sf_rez@@. Giriş teker ivmesi olunca hareket modeli bilinmeyen motor parametrelerine bağlı kalmaz. Bedeli +@@st_dm@@ kg ve ≈ @@st_h@@ saat pil süresidir. DRV8825'in @@st_I@@ A limiti tepe değer olduğu için motor etiket torkunun %@@st_I_tam@@'ini verir. Karar eşiği ve ölçüm planı §10.10–10.11'de.

---

## 1. Kapsam, kaynaklar ve varsayımlar

**Kaynak önceliği.** Haftalık görev ve teslimatlar için danışmanın ekip iş planı, teknik kısıtlar için teknik şartname TR v14 (24 Eylül 2026) esas alındı. Bu belgede kullanılan şartname maddeleri:

| Madde | İçerik | Bu belgede |
|---|---|---|
| §4.1 Mekanik düzen | Yalnız iki ana teker; üçüncü teker veya destek yok | Model iki tekerli; yere değme açısı §5.6 |
| §4.1 Aktif denge, pasif kararlılık ön testi | Enerjisizken ±10°'den bırakılınca 5 s içinde dik konuma dönmemeli, pasif dik kalmamalı | §3.7 |
| §4.1 Güç | Ana besleme ≤ 24 V DC | §4.5 batarya tablosu |
| §4.1 Yük | İlaç kutusu görev boyunca sabit kalır, gövdeye monte edilmez | §5 |
| §7 Ortak test protokolü | Düz, sert, kuru zemin; kutu bütün testlerde taşınır; iki teker dışı temas alt testi düşürür | §4.4, §5 |
| §8 Ö1 | 30 s denge; ≈1 m ileri/geri + 3 s dur; ±10°'den 10 s içinde toparlanma | §4.1–4.3 |
| §8 Ö2 | ≈0,5 m ileri/geri, ≈90° dönüş, 2 s içinde tepki | §4.1 |

**Şartnamede hız veya süre sınırı yoktur.** Ö1/Ö2 hareketleri için süre yalnız tepki (2 s) ve bekleme (3 s) olarak tanımlıdır. Bu yüzden hareket süreleri bu belgede tasarım hedefi olarak seçildi ve [öneri] diye işaretlendi (§2.4).

**Varsayımlar.** Rijit gövde; tekerler kaymadan yuvarlanır ve yanal kaymaz; zemin düz ve yataydır (§7); tekerler ince disktir; motor endüktansı ihmal edilir; kutu yuvada gövdeyle birlikte hareket eder (kayma etkisi §5.3'te ayrıca ele alındı).

**Etiketler.** *tahmini*: ölçülmemiş fiziksel değer. *[öneri]*: danışman planında veya şartnamede bulunmayan, bu belgenin önerdiği seçim. *[doğrulanamadı]*: kaynaklarda doğrulanamayan bilgi.

## 2. Parametreler

### 2.1 Robotun fiziksel parametreleri (hiçbiri ölçülmedi)

Aşağıdaki @@n_fiziksel@@ parametre `parametreler.toml` dosyasından otomatik alınmıştır. Durumlar: **ön liste** = ön malzeme listesi (cdtp-robot.netlify.app'teki referans malzeme listesinden derlendi; Mete'nin seçimiyle kesinleşecek), **[doğrulanamadı]** = rcdrone satıcı referans tablosu (ürünle eşleştiği doğrulanamadı), **tahmini** = listede olmayan, mühendislik tahmini. Testler, fiziksel bir parametrenin bu üçü ve "ölçülmüş" dışında bir durumla girilmesini engeller.

@@tablo_fiziksel@@

### 2.2 Kütle bütçesi ve yerleşim

Gövde, tahmini bileşenlerin kütle ve konumlarından kurulmuştur (Şekil 1). Bileşenler dikdörtgen prizma olarak alınmış, atalet tensörü paralel eksen teoremiyle hesaplanmıştır.

@@tablo_butce@@

![Şekil 1](sekiller/sekil_01_yerlesim.png)

*Şekil 1: Tahmini yerleşim, yan ve ön görünüş. Koordinat orijini teker aksının orta noktasıdır; x ileri, z gövde ekseni boyunca yukarıdır. Turuncu: ilaç kutusu (önerilen üst yuvada). Siyah noktalar kutusuz ve kutulu kütle merkezi; mavi çizgi vuruş merkezi (§5.5). Soldaki işaretler değerlendirilen üç yuva yüksekliğidir.*

### 2.3 Modele giren türetilmiş parametreler

@@tablo_model_par@@

### 2.4 Şartname değerleri ve tasarım hedefleri

@@tablo_hedef@@

## 3. Matematiksel model

### 3.1 Koordinatlar

Genelleştirilmiş koordinatlar $q = (X, Y, \psi, \theta, \varphi_R, \varphi_L)$:

- $X, Y$: aks orta noktasının zemindeki konumu; $x$: yön boyunca alınan yol ($\dot x = v$),
- $\psi$: sapma (yaw), sola dönüş pozitif,
- $\theta$: gövde eğimi (pitch), **ileri eğim pozitif** (KM aksın önüne geçer),
- $\varphi_R, \varphi_L$: sağ/sol teker dönüş açısı.

Girişler teker millerindeki motor torklarıdır: $\tau_R, \tau_L$. Motor torku teker ile gövde arasında etkir, yani tepkisi gövdeye gelir. Tekerler kaymadan yuvarlanır ve yanal kaymaz:

$$
r\dot\varphi_R = v + \tfrac{d}{2}\dot\psi,\qquad r\dot\varphi_L = v - \tfrac{d}{2}\dot\psi,\qquad -\dot X\sin\psi + \dot Y\cos\psi = 0 .
$$

Bu kısıtlar holonom değildir. Bu yüzden Lagrange denklemleri tüm koordinatlarda yazılır ve kısıtlara uyan serbest hızlar $\nu = (v, \dot\psi, \dot\theta)$ üzerine izdüşürülür. Bu yöntem Lagrange–d'Alembert ilkesidir: kısıt kuvvetleri iş yapmadığı için izdüşümde düşer.

### 3.2 Lagrange formülasyonu

Gövde KM'si $(X + l\sin\theta\cos\psi,\; Y + l\sin\theta\sin\psi,\; r + l\cos\theta)$ noktasındadır. Gövdenin açısal hızı gövde eksenlerinde $(-\dot\psi\sin\theta,\; \dot\theta,\; \dot\psi\cos\theta)$ olur. Kinetik ve potansiyel enerji:

$$
T = \tfrac12 m_b \lVert \dot{\mathbf p}_b \rVert^2 + \tfrac12\left(I_{xx}\dot\psi^2\sin^2\theta + I_{yy}\dot\theta^2 + I_{zz}\dot\psi^2\cos^2\theta\right)
 + \sum_{i=R,L}\left[\tfrac12 m_w \lVert \dot{\mathbf p}_i \rVert^2 + \tfrac12 J_w\dot\varphi_i^2 + \tfrac12 K_w\dot\psi^2 + \tfrac12 J_m(\dot\varphi_i - \dot\theta)^2\right]
$$

$$
V = m_b g\, l\cos\theta, \qquad \mathcal L = T - V .
$$

Son terim, rotor ataletinin teker miline yansımasıdır ($J_m = J_\text{rotor}N^2$). Motor ve redüktör sürtünmesi ($b$) teker–gövde bağıl hızıyla orantılıdır. Genelleştirilmiş kuvvetler:

$$
Q_{\varphi_i} = \tau_i - b(\dot\varphi_i - \dot\theta), \qquad Q_\theta = -\sum_i\left[\tau_i - b(\dot\varphi_i - \dot\theta)\right].
$$

Türetim `denge/model.py` içinde sembolik olarak (sympy) yapılmış ve aşağıdaki el ile yazılmış biçimle birebir eşleştirilmiştir (test: `test_sembolik_turetim_el_ile_yazilan_denklemlerle_ayni`).

### 3.3 Doğrusal olmayan hareket denklemleri

Kısaltmalar:

$$
M_x = m_b + 2m_w + \frac{2(J_w + J_m)}{r^2},\quad
a_{12}(\theta) = m_b l\cos\theta - \frac{2J_m}{r},\quad
a_{22} = I_{yy} + m_b l^2 + 2J_m,
$$

$$
J_\psi(\theta) = I_{xx}\sin^2\theta + I_{zz}\cos^2\theta + m_b l^2\sin^2\theta + 2K_w + \frac{m_w d^2}{2} + \frac{(J_w + J_m)\,d^2}{2r^2},
\qquad \omega_b = \frac{v}{r} - \dot\theta .
$$

**İleri hareket ($v$):**

$$
M_x\dot v + a_{12}(\theta)\ddot\theta - m_b l\sin\theta\,(\dot\theta^2 + \dot\psi^2) = \frac{\tau_R + \tau_L}{r} - \frac{2b}{r}\,\omega_b
$$

**Sapma ($\psi$):**

$$
J_\psi(\theta)\ddot\psi + 2(I_{xx} - I_{zz} + m_b l^2)\sin\theta\cos\theta\,\dot\theta\dot\psi + m_b l\sin\theta\, v\dot\psi = \frac{d}{2r}(\tau_R - \tau_L) - \frac{b\,d^2}{2r^2}\dot\psi
$$

**Eğim ($\theta$):**

$$
a_{12}(\theta)\dot v + a_{22}\ddot\theta - (I_{xx} - I_{zz} + m_b l^2)\sin\theta\cos\theta\,\dot\psi^2 - m_b g l\sin\theta = -(\tau_R + \tau_L) + 2b\,\omega_b
$$

İleri denklemdeki $m_b l\sin\theta\,\dot\psi^2$ ve sapma denklemindeki $m_b l\sin\theta\, v\dot\psi$ terimleri holonom olmayan kısıttan gelir: dönerken öne eğik KM bir çember üzerinde hareket eder. Bu terimler naif Lagrange yazımında (x'i sıradan koordinat sayınca) kaybolur.

Tekerler gövdeye kilitliyse (redüktör geri sürülemezse) robot tek parça yuvarlanır ve tek serbestlik dereceli olur:

$$
\left[I_{yy} + 2J_w + m_b(l^2 + 2lr\cos\theta + r^2) + 2m_w r^2\right]\ddot\theta - m_b l r\sin\theta\,\dot\theta^2 - m_b g l\sin\theta = 0 .
$$

### 3.4 θ = 0 civarında doğrusallaştırma

$\theta \approx 0$, $\dot\theta \approx 0$, $v \approx 0$, $\dot\psi \approx 0$ için $\sin\theta \approx \theta$, $\cos\theta \approx 1$ alınır ve ikinci dereceden terimler atılır. Bu durumda eğim/ileri ile sapma **ayrışır**:

$$
\underbrace{\begin{bmatrix} M_x & a_{12} \\ a_{12} & a_{22}\end{bmatrix}}_{\mathbf M}\begin{bmatrix}\ddot x \\ \ddot\theta\end{bmatrix}
= \begin{bmatrix} 0 \\ m_b g l \end{bmatrix}\theta
+ 2b\begin{bmatrix} -1/r^2 & 1/r \\ 1/r & -1 \end{bmatrix}\begin{bmatrix}\dot x \\ \dot\theta\end{bmatrix}
+ \begin{bmatrix} 1/r \\ -1 \end{bmatrix} u,
\qquad J_{\psi 0}\,\ddot\psi = \frac{d}{2r}u_\psi - \frac{b\,d^2}{2r^2}\dot\psi
$$

Burada $u = \tau_R + \tau_L$ (ortak tork), $u_\psi = \tau_R - \tau_L$ (fark tork), $a_{12} = m_b l - 2J_m/r$ ve $J_{\psi 0} = J_\psi(0)$'dır. Motorlara verilecek komut $\tau_{R,L} = (u \pm u_\psi)/2$ olur. Doğrusallaştırmanın doğruluğu, doğrusal olmayan modelin sayısal Jakobiyeniyle karşılaştırılarak test edilmiştir ($b \neq 0$, $J_m \neq 0$ dahil).

Nominal (kutulu) değerler: $M_x = @@M_x@@$ kg, $a_{12} = @@a12@@$ kg·m, $a_{22} = @@a22@@$ kg·m², $\Delta = M_x a_{22} - a_{12}^2 = @@Delta@@$ kg²·m², $m_b g l = @@mgl@@$ N·m, $J_{\psi 0} = @@J_psi@@$ kg·m².

### 3.5 Durum-uzay modeli (A, B, C, D)

**Eğim + ileri alt sistemi.** Durum $\mathbf x = [x,\ \dot x,\ \theta,\ \dot\theta]^\mathsf{T}$, giriş $u = \tau_R + \tau_L$ [N·m]. $b = 0$ için kapalı biçim:

$$
A = \begin{bmatrix} 0 & 1 & 0 & 0 \\ 0 & 0 & -\dfrac{a_{12}\,m_b g l}{\Delta} & 0 \\ 0 & 0 & 0 & 1 \\ 0 & 0 & \dfrac{M_x\, m_b g l}{\Delta} & 0 \end{bmatrix},\qquad
B = \begin{bmatrix} 0 \\ \dfrac{a_{22} + a_{12} r}{r\Delta} \\ 0 \\ -\dfrac{M_x r + a_{12}}{r\Delta} \end{bmatrix},\qquad
C = I_4,\qquad D = 0_{4\times 1}.
$$

Sayısal (kutulu, nominal, SI birimler):

$$
A = @@A@@,\qquad B = @@B@@ .
$$

$C = I_4$ seçimi, durumların hepsinin ölçüldüğünü varsayar: $x, \dot x$ enkoderden, $\theta$ 5. haftanın filtresinden, $\dot\theta$ jiroskoptan gelir. $B_4 < 0$ olması şu demektir: ileri tork gövdeye geri yönde tepki uygular.

**Sapma alt sistemi.** Durum $[\psi,\ \dot\psi]^\mathsf{T}$, giriş $u_\psi = \tau_R - \tau_L$:

$$
A_\psi = @@Ap@@,\qquad B_\psi = @@Bp@@,\qquad C_\psi = I_2,\qquad D_\psi = 0 .
$$

**Ayrık model (MPC veya ayrık LQR için).** Sıfırıncı derece tutucu (ZOH), $T_s$ = @@Ts_ms@@ ms (@@f_kontrol@@ Hz [öneri]):

$$
A_d = @@Ad@@,\qquad B_d = @@Bd@@ .
$$

**Kontrol edilebilirlik ve gözlenebilirlik.** $(A, B)$ kontrol edilebilirlik rangı @@rank_c@@/4'tür, yani tam. $C = [x;\ \theta]$ ile (enkoder + IMU) gözlenebilirlik rangı @@rank_o2@@/4'tür. Yalnız $\theta$ ölçülürse rang @@rank_o1@@/4'e düşer: konum ve hız gözlenemez, bu yüzden enkoder şarttır (§4.6).

**Motor seçilince gerilim girişi.** Endüktans ihmal edilirse redüktörlü DC motor teker milinde $\tau = (K_t/R)V - (K_t K_e/R)\,\omega_b$ verir. İki motora aynı $V$ uygulanırsa model, $b \to b + K_tK_e/R$ ve $B \to B\cdot 2K_t/R$ değişiklikleriyle aynı kalır (`model.gerilim_girisli_durum_uzay`). $K_t, K_e, R$ değerleri veri sayfasından hesaplanır (`motor.MotorAdayi.motor_modeli`).

### 3.6 Transfer fonksiyonları ve açık çevrim kutuplar

$b = 0$ için kapalı biçimler:

$$
G_\theta(s) = \frac{\Theta(s)}{U(s)} = \frac{-K_\theta}{s^2 - p^2},\qquad
K_\theta = \frac{M_x r + a_{12}}{r\Delta},\qquad p^2 = \frac{M_x\, m_b g l}{\Delta}
$$

$$
G_x(s) = \frac{X(s)}{U(s)} = \frac{K_x\,(s^2 - z^2)}{s^2\,(s^2 - p^2)},\qquad
K_x = \frac{a_{22} + a_{12} r}{r\Delta},\qquad z^2 = \frac{m_b g l}{a_{22} + a_{12} r},
\qquad
G_\psi(s) = \frac{\Psi(s)}{U_\psi(s)} = \frac{d/(2rJ_{\psi 0})}{s^2}
$$

Sayısal (kutulu):

$$
G_\theta(s) = \frac{-@@K_theta@@}{s^2 - @@p2@@} = \frac{-@@K_theta@@}{(s - @@p_m@@)(s + @@p_m@@)},\qquad
G_x(s) = \frac{@@K_x@@\,(s^2 - @@z2@@)}{s^2\,(s^2 - @@p2@@)},\qquad
G_\psi(s) = \frac{@@K_psi@@}{s^2}
$$

@@tablo_kutup@@

![Şekil 2](sekiller/sekil_02_kutuplar.png)

*Şekil 2: Eğim alt sisteminin açık çevrim kutupları. Sağ yarı düzlemde bir kutup (+@@p@@ 1/s) vardır, yani sistem açık çevrimde kararsızdır (test: `test_en_az_bir_kutup_sag_yari_duzlemde`). Turuncu: bilinmeyen rotor ataleti için örnek $J_m$ = @@Jm_ornek@@ kg·m². Halkalar $X/U$'nun sıfırlarıdır.*

**Yorum ve kontrol tasarımına etkisi:**

- Kararsız kutup +@@p@@ 1/s'dir, yani eğim hatası her @@tau_zaman@@ ms'de $e$ katına büyür. Önerilen @@f_kontrol@@ Hz döngü frekansı ($2\pi f$ = kutbun @@bant_orani@@ katı) bunun için rahat bir paydır [öneri].
- $G_x$'te sağ yarı düzlemde bir sıfır vardır ($z$ = +@@z@@ 1/s). Robot ileri gitmek için önce tekeri geri kaçırıp gövdeyi öne yatırmak zorundadır; bu, minimum fazlı olmayan davranıştır ve konum döngüsünün bant genişliğini sınırlar. Ö1'deki 1 m harekette bu geri kaçış milimetre düzeyindedir (§4.1).
- **PID:** iç döngü $G_\theta$, dış döngü (konum/hız) $G_x$. **LQR:** $(A, B)$ ve $C = I_4$; sapma için ayrıca $(A_\psi, B_\psi)$. **MPC:** $(A_d, B_d)$ ile tork sınırı (§4.4 çekiş sınırı) ve eğim sınırı (§5.6 yere değme açısı) kısıt olarak girilebilir.

### 3.7 Açık çevrim düşme simülasyonu (±10°)

Robot durağan hâlde ±10°'den bırakılır ve motorlar enerjisizdir ($u = 0$). Redüktörün geri sürülebilirliği motor seçilmeden bilinmediği için iki uç durum simüle edildi: **serbest teker** (redüktör serbest döner) ve **kilitli teker** (redüktör geri sürülemez, robot tek parça yuvarlanır). Simülasyon gövde yere değince durur (yere değme açısı ileri @@temas@@°, geri @@temas_geri@@°, §5.6).

![Şekil 3](sekiller/sekil_03_dusme.png)

*Şekil 3: ±10°'den açık çevrim düşme. Kesikli çizgi doğrusal model. İleri düşüşte gövde serbest tekerde @@t_serbest@@ s'de, kilitli tekerde @@t_kilitli@@ s'de yere değer; geri düşüş, yere değme açısı farklı olduğu için biraz daha uzun sürer. Dinamik olarak ±10° düşmeler birbirinin aynadaki görüntüsüdür (test edildi).*

| Durum | Yere değme süresi | Aks yer değiştirmesi |
|---|---:|---:|
| Doğrusal olmayan, serbest teker | @@t_serbest3@@ s | @@x_serbest@@ cm (gövdenin tersine) |
| Doğrusal olmayan, kilitli teker | @@t_kilitli3@@ s | @@x_kilitli@@ cm (gövdeyle aynı yöne yuvarlanır) |
| Doğrusal model ($\theta_0\cosh pt$), serbest teker | @@t_lin@@ s | - |

**4. hafta pasif kararlılık ön testi için öngörü:** Hem serbest hem kilitli teker durumunda, iki yönde de robot 5 s sınırının çok altında (@@t_hepsi_min@@–@@t_hepsi_max@@ s) düşer ve dikliğe hiç yaklaşmaz. Bu sonuç $l > 0$ olduğu sürece geçerlidir. Model, KM aksın altına indirildiğinde ($l < 0$) kararsız kutbun kaybolduğunu ve robotun pasif kararlı hâle geldiğini de gösterir (test: `test_km_aks_altindaysa_robot_pasif_kararli_olur`). Bu yüzden ağır parçaların (batarya) aksın altına taşınmaması gerekir. 4. hafta toplantısında kronometreyle ölçülecek düşme süresi bu öngörüyle karşılaştırılacaktır [öneri].

Doğrusal model yere değme süresini %@@t_lin_fark@@ kısa öngörür; ±10° civarında iki model örtüşür (Şekil 3), yani bu bölgede doğrusal model kontrol tasarımı için yeterlidir.

### 3.8 Bilinmeyen motor parametrelerinin kutba etkisi

Motor seçilmediği için yansıyan rotor ataleti $J_m$ ve sürtünme $b$ nominalde ihmal edildi. İkisi de kutbu belirgin biçimde yavaşlatır:

@@tablo_jm@@

Gerilim kontrollü bir sürücüde zıt EMK eşdeğer bir $b$ ekler ($K_tK_e/R$), bu da kutbu kilitli teker değerine doğru çeker. Bu yüzden motor geldiğinde ilk tanılanacak parametreler $J_m$ ve $b$'dir. Yöntem serbest yavaşlama (coast-down) deneyi ve veri sayfasıdır [öneri].

## 4. Motor tork/devir hesapları

Bütün torklar **teker milinde** (redüktör çıkışında) verilmiştir. "Toplam" iki motorun toplamı, "motor başı" tek motor içindir.

### 4.1 Ö1/Ö2 hareketleri için teker hızı ve devir

Simetrik trapez hız profili kullanıldı: sürenin oranı $\rho$ = 0,25 hızlanma, $\rho$ = 0,25 yavaşlama [öneri]. Mesafe $D$, süre $T$ için:

$$
v_\text{tepe} = \frac{D}{(1-\rho)T},\qquad a = \frac{v_\text{tepe}}{\rho T},\qquad n = \frac{60\, v}{2\pi r}\ \text{[dev/dk]},\qquad
\text{yerinde dönüşte } v = \frac{d}{2}\dot\psi .
$$

Sabit ivmede ($\ddot\theta = 0$) gereken toplam tork $\tau_R + \tau_L = M_x r a$, yerinde dönüşte fark torku $\tau_R - \tau_L = (2r/d)J_{\psi 0}\ddot\psi$'dir.

@@tablo_hareket@@

Hareket için gereken tork, toparlanma torkunun yanında ihmal edilebilecek kadar küçüktür. Motor seçimini belirleyen hız değil, ±10° toparlanmasıdır.

![Şekil 4](sekiller/sekil_04_oteleme.png)

*Şekil 4: Ö1 için 1 m / @@o1_sure@@ s referans öteleme (düz çıkış ile, dinamik olarak tutarlı). Robot önce @@ot_geri@@ mm geri kaçar (minimum fazlı olmayan sıfır), hızlanmak için @@ot_th@@°'ye kadar öne yatar. Yumuşak polinom profilin tepe hızı @@ot_v@@ m/s'dir (@@ot_rpm@@ dev/dk), yani trapezin @@ot_oran@@ katı. Devir tablosundaki hız payı (×@@hiz_payi@@) bu farkı kapsar.*

### 4.2 ±10°'den toparlanma torku: istenen el hesabı

İstenen biçim, statik terim ile dinamik payın toplamıdır (iki motor toplamı):

$$
\tau_\text{top} = \underbrace{m_b g l\sin\theta_0}_{\text{statik}} + \underbrace{J_O\,\ddot\theta_r}_{\text{dinamik pay}},\qquad
J_O = I_{yy} + m_b l^2,\qquad \ddot\theta_r = \frac{4\theta_0}{t_r^2}
$$

Burada $m_b$ ve $l$ gövdeye aittir: tekerlerin ağırlığı aksta etkir ve moment üretmez. $\ddot\theta_r$, gövdenin $\theta_0$ = 10°'den 0°'a $t_r$ sürede dönmesi için gereken açısal ivmedir: sürenin yarısında hızlanır, yarısında yavaşlar ($t_r$ = @@t_r@@ s [öneri]).

| Terim | Değer |
|---|---:|
| Statik: $m_b g l\sin 10°$ | @@statik@@ N·m |
| $J_O$ (aks etrafında) | @@J_O_s@@ g·m² |
| $\ddot\theta_r$ | @@thdd@@ rad/s² |
| Dinamik pay: $J_O\ddot\theta_r$ | @@dinamik@@ N·m |
| **Toplam (iki motor)** | **@@el_toplam@@ N·m** |
| Motor başına | @@el_motor@@ N·m (@@el_motor_kgfcm@@ kgf·cm) |
| **Motor başına × emniyet katsayısı @@SF@@ [öneri]** | **@@tA@@ N·m (@@tA_kgfcm@@ kgf·cm)** |

Dönüş süresinin etkisi:

@@tablo_tr@@

### 4.3 Tam modelle kontrol

**Tutma torku.** $\theta$'da $\dot\theta = 0$ iken $\ddot\theta = 0$ tutmak için gereken toplam tork, doğrusal olmayan denklemlerden kapalı biçimde çıkar:

$$
\tau_\text{tutma} = \frac{m_b g l\sin\theta}{1 + a_{12}(\theta)/(M_x r)}
$$

Payda 1'den büyüktür, çünkü tekeri ileri iten tork tekeri ivmelendirir ve bu ivme de gövdeyi doğrultur. Nominal değerlerde ($J_m$ = 0) çarpan @@tutma_carpan@@'tür, yani $\tau_\text{tutma}$ = @@tutma@@ N·m = el hesabının statik teriminin %@@tutma_oran@@'i (test: tutma torku uygulanınca doğrusal olmayan modelde $\ddot\theta = 0$).

**Referans toparlanma manevrası (kontrolcü değildir).** Kontrol yöntemi henüz seçilmediği için torku sınırlamak amacıyla doğrusal modelin **düz çıkışı** kullanıldı:

$$
F = (M_x r + a_{12})\,x + (a_{12} r + a_{22})\,\theta,\qquad \ddot F = m_b g l\,\theta .
$$

Motor torku ve sürtünme teker ile gövde arasında iç kuvvet olduğundan $F$'nin denkleminden düşer. $F$ için uç koşulları sağlayan (+10°'de durağan → 0°'da durağan, $T$ sürede) 7. derece polinom seçilince $x(t)$, $\theta(t)$ ve $u(t)$ cebirsel olarak bulunur. Son konum ∫u² dt'yi en küçük yapacak şekilde seçildi. Aynı $\theta(t)$ doğrusal olmayan modelde ters dinamikle izlenerek gerçek tork hesaplandı.

![Şekil 5](sekiller/sekil_05_toparlanma.png)

*Şekil 5: $T$ = @@T_ref@@ s referans toparlanma. Gövde aşımla −@@th_min_ref@@°'ye kadar geri yatar, aks @@x_f@@ cm ilerler, tepe hız @@v_ref@@ m/s'dir. Tepe tork @@tepe_ref@@ N·m'dir (doğrusal model @@tepe_ref_lin@@). Doğrusal olmayan modelde son hız @@xd_son@@ mm/s'ye iner.*

![Şekil 6](sekiller/sekil_06_tork_sure.png)

*Şekil 6: Manevra süresine göre tepe tork ve tepe teker devri. Süre uzadıkça tork tutma torkuna iner, ama robotun gittiği yol ve tepe hız artar. Kısa manevralar torku, uzun manevralar devri zorlar.*

@@tablo_tarama@@

**Rotor ataleti hesabı değiştirir.** Yukarıdaki sonuçlar $J_m = 0$ içindir. Teker miline yansıyan rotor ataleti büyüdükçe motor torkunun bir kısmı rotoru hızlandırmaya harcanır ve gövdeye etkiyen tepki azalır, yani tork gereksinimi artar:

@@tablo_jm_tork@@

**Sonuç.** $J_m = 0$'da el hesabı referans manevranın @@el_kat@@ katıdır. $J_m$ = @@jm_ust@@ kg·m²'de ise referans manevra @@tepe_ref_jm_ust@@ N·m ister ve @@jm_karsilastirma@@. Aynı $J_m$'de $T$ = @@t_r@@ s'lik agresif bir toparlanma @@tepe_agr_jm_ust@@ N·m ister; bu çekiş sınırının üstündedir, yani fiziksel olarak yapılamaz. Motor seçilene kadar **el hesabı × emniyet katsayısı tasarım değeri olarak tutuldu**. Emniyet katsayılı değer (@@SF@@ × @@el_toplam@@ N·m), referans manevrayı $J_m$'nin bütün tahmini aralığında @@jm_sf_yeter@@. Yüksek redüksiyon oranı $J_m$'yi $N^2$ ile büyüttüğü için redüksiyon seçimi yalnız devir ve tork açısından değil, bu açıdan da değerlendirilmelidir [öneri].

### 4.4 Çekiş sınırı

Teker kaymadan zemine aktarılabilecek en büyük toplam tork yaklaşık şudur:

$$
\tau_\text{max} \approx \mu\, m_\text{top}\, g\, r
$$

Tahmini μ = @@mu@@ ile bu değer @@cekis@@ N·m (toplam), yani motor başına @@cekis_motor@@ N·m'dir.

Referans manevra (@@T_ref@@ s, $J_m$ = 0) yalnız μ ≥ @@mu_gerek_ref@@ ister ve rahattır. El hesabının emniyet katsayılı değeri ise μ ≥ @@mu_gerek_el@@ gerektirir, yani çekiş sınırını aşar. Bu tutarsızlık değildir: önerilen motorun torku zemine tamamen aktarılamaz, bu yüzden toparlanmada sınırı motor değil zemin koyar. Kontrolcünün tork doyumu çekiş sınırının altına ayarlanmalıdır, aksi hâlde teker kayar ve enkoder hız kestirimi bozulur [öneri].

### 4.5 Motor seçim gereksinimi (Mete'nin adayıyla karşılaştırma)

Gereksinim noktaları motor başına ve teker milindedir:

| Nokta | Tork | Devir | Anlamı |
|---|---:|---:|---|
| **A (önerilen)** | @@tA@@ N·m (@@tA_kgfcm@@ kgf·cm) | @@nA@@ dev/dk | El hesabı × SF (@@SF@@). Devir, @@T_ref@@ s referans toparlanmanın tepe hızından gelir. |
| A' (asgari) | @@tA2@@ N·m (@@tA2_kgfcm@@ kgf·cm) | @@nA2@@ dev/dk | Çekiş sınırı: bundan güçlü motorun fazlası kullanılamaz. Yalnız $J_m$ ≤ @@jm_esik_s@@ kg·m² ise referans manevrayı SF ile karşılar. |
| B (seyir) | @@tB@@ N·m | @@nB@@ dev/dk | @@seyir_hareketi@@ tepe hızı (@@v_seyir@@ m/s) × hız payı @@hiz_payi@@ [öneri]; yavaşlama torku × SF. |

Doğrusal tork-devir eğrili bir DC motorun ($\tau(n) = \tau_s(1 - n/n_0)$) noktaların hepsinin üstünde kalması için şu koşul gerekir:

$$
\tau_s \ \ge\ \max_i \frac{\tau_i}{1 - n_i/n_0}\qquad (n_0 > n_i) .
$$

Boşta devir ($n_0$) ve durma torku ($\tau_s$) gerilimle orantılıdır. Bu yüzden aday, veri sayfasındaki nominal gerilimden **batarya minimum gerilimine** ölçeklenerek sınanır. Seçilen tahmini paket @@n_hucre@@S Li-ion: @@V_min@@ V (boş) / @@V_nom@@ V (nominal) / @@V_max@@ V (tam dolu).

![Şekil 7](sekiller/sekil_07_motor_secim.png)

*Şekil 7: Solda gereksinim noktaları ve sınırdaki doğrusal motor eğrileri. Sağda seçim diyagramı: adayın (batarya min. gerilimindeki) $(n_0, \tau_s)$ noktası mavi eğrinin üstünde olmalıdır.*

Sınırdaki motorlar (batarya min. geriliminde):

@@tablo_min_motor@@

Ön listedeki batarya paketinin şartname §4.1 ile uyumu:

@@tablo_batarya@@

**Mete için karşılaştırma şablonu.** Adayın veri sayfası değerleri komut satırına girilir; araç adayı batarya min. geriliminde A, A', B noktalarına, enkoder çözünürlüğüne ve aşırı gerilime göre sınar, sürücü ve sigorta boyutu için tepe akımı verir:

```
python -m denge.motor --ad "Aday-1" --gerilim 12 --bosta-devir <dev/dk> --durma-torku <kgf·cm> \
    --durma-akimi <A> --bosta-akim <A> --reduksiyon <N> --ppr <darbe/devir> [--rotor-ataleti <g·cm²>]
```

| Veri sayfası alanı | Aday 1 | Aday 2 | Neden gerekli |
|---|---|---|---|
| Nominal gerilim [V] | | | $n_0$, $\tau_s$ ölçeklemesi; aşırı gerilim kontrolü |
| Boşta çıkış devri [dev/dk] | | | B noktası, hız payı |
| Durma torku [kgf·cm] | | | A noktası |
| Durma / boşta akım [A] | | | $K_t$, $R$, tepe akım → sürücü ve sigorta (Mete) |
| Redüksiyon oranı $N$ | | | Enkoder sayımı, $J_m = J_\text{rotor}N^2$ |
| Enkoder PPR (motor milinde) | | | §4.6 |
| Rotor ataleti [g·cm²] (varsa) | | | $J_m$ (§3.8, §4.3) |
| Kütle [g] | | | Kütle bütçesi, KM (§5) |

### 4.6 Enkoder gereksinimi

Hız, enkoder sayımının $T_v$ penceresindeki farkından kestirilir. Bir sayımlık nicemleme adımının hız karşılığı $\Delta v = 2\pi r / (\text{CPR}\cdot T_v)$'dir. Hedef $\Delta v \le$ @@dv_hedef@@ m/s ve $T_v$ = @@pencere_ms@@ ms [öneri]; bu hedef, Ö1'deki 3 s durmada hız kestiriminin gürültüsüz olması için seçildi:

$$
\text{CPR}_\text{teker} \ \ge\ \frac{2\pi r}{\Delta v\, T_v} = @@cpr_min@@\ \text{sayım/teker devri},\qquad
\text{CPR}_\text{teker} = 4\cdot\text{PPR}_\text{motor}\cdot N\ \ (\text{x4 kuadratür}) .
$$

Tepe devirde (@@n_max@@ dev/dk) sayım frekansı ≈ @@f_sayim@@ kHz'dir. Bir sayımın yol karşılığı ≤ @@ds_max@@ mm, sapma karşılığı ≤ @@dpsi@@°'dir.

@@tablo_enkoder@@

**Notlar:**

1. **Enkoder tekerin gövdeye göre açısını ölçer** (stator gövdeye bağlıdır). Gerçek teker dönüşü $\varphi = \varphi_\text{enk} + \theta$ olduğundan $x = r(\varphi_\text{enk} + \theta)$, $\dot x = r(\dot\varphi_\text{enk} + \dot\theta)$ olur. Bu düzeltme yapılmazsa 10°'de @@hata_x@@ mm konum, $\dot\theta$ = 1 rad/s'de @@hata_v@@ cm/s hız hatası oluşur. Bu düzeltme 5. haftanın durum kestiricisine eklenmelidir [öneri].
2. Sapma açısı iki tekerin farkından $\psi = r(\varphi_R - \varphi_L)/d$ olarak hesaplanır. Fark alındığında $\theta$ terimi sadeleşir.
3. Kuadratür sayımı için donanım sayacı (STM32 zamanlayıcı enkoder kipi veya ESP32 PCNT gibi) önerilir. Tablodaki frekanslar kesme tabanlı sayım için de düşüktür, ama donanım sayacı işlemci yükünü sıfırlar [öneri].

### 4.7 Aday motor: @@aday_ad@@ (Mete'ye öneri)

Ön malzeme listesinde motor olarak JGB37-520 12 V 530 RPM, Hall enkoderli model yer alıyor. Veri sayfası değerleri listede yok; rcdrone listesindeki referans tablodan alındı ve **[doğrulanamadı]** olarak işaretlendi: oran 1:@@aday_N@@, boşta @@aday_n0@@ dev/dk, durma torku @@aday_ts_kgfcm@@ kgf·cm (@@aday_ts@@ N·m), durma akımı 2,4 A, boşta akım 0,15 A, 12 V'ta. Satıcı bu tabloyu "yalnız referans" diye veriyor. Aday, `python -m denge.motor --dosyadaki-aday --oran-taramasi` ile sınandı. Aday batarya min. geriliminde (@@V_min@@ V, ön listedeki boş pil gerilimi) değerlendirildi; tork ve devir gerilimle orantılı ölçeklendi.

@@tablo_aday@@

A noktasında adayın sağladığı emniyet katsayısı (mevcut tork / katsayısız el hesabı): boş batarya @@sf_min@@, nominal @@sf_nom@@, tam dolu @@sf_max@@.

**Oran taraması.** Aynı motor gövdesinin rcdrone referans serisindeki diğer oranları, boş batarya geriliminde aynı gereksinime karşı sınandı:

@@tablo_oran@@

Seriye uydurulan sürekli model (12 V'ta $\tau_s \approx$ @@fit_c@@ kgf·cm × N, $n_0 \approx$ @@fit_K@@ / N dev/dk) ile A (SF) ve B noktalarını birlikte karşılayan oran aralığı:

- Boş batarya (@@V_min@@ V): @@oran_araligi_min@@.
- Nominal (@@V_nom@@ V): @@oran_araligi_nom@@.

**Mete'ye öneri [öneri]:**

1. **530 RPM varyantı çalışır ama emniyet payı düşüktür.** ±10° toparlanma torkunu katsayısız karşılar; 2 emniyet katsayısıyla karşılamaz (boş bataryada @@sf_min@@, nominalde @@sf_nom@@). Bu torkla bile teker zeminin aktarabileceği torku (çekiş sınırı @@cekis_motor@@ N·m/motor) aşabildiği için toparlanmayı motor değil zemin sınırlar. Ancak bu, yansıyan rotor ataleti $J_m$ ≤ @@jm_esik_s@@ kg·m² ise geçerlidir ve $J_m$ henüz bilinmiyor. Enkoder 4 × 11 × @@aday_N@@ = @@cpr_aday@@ sayım/teker devri verir; @@cpr_min@@ hedefinin altındadır. Bu varyant alınırsa hız kestirim penceresi en az @@pencere_gerek@@ ms'ye çıkarılmalıdır (yazılımda; 200 Hz'de 3 örnek = 15 ms).
2. **Tercih: aynı fiyattaki @@en_iyi_ad@@ varyantı.** Boş bataryada A noktasında @@en_iyi_tau@@ N·m verir: SF @@en_iyi_sf@@, yani hedefin %@@en_iyi_eksik@@ altında; nominal gerilimde SF @@en_iyi_sf_nom@@ ile karşılar. Referans serisinde boş bataryada hedefe en yakın oran budur; B noktasında yeterli hız payı bırakır ($n_0$ = @@en_iyi_n0@@ ≥ @@nB@@ dev/dk); enkoder @@en_iyi_cpr@@ sayım ile hedefi karşılar. Ön liste de bu varyantı "daha çok tork" için alternatif olarak gösteriyor.
3. **Bedeli:** Yansıyan rotor ataleti oranın karesiyle büyür (530 RPM'e göre ×@@en_iyi_oran2@@). $J_m$, kutbu yavaşlatır ama gereken torku artırır (§4.3). Motor gelince ilk iş serbest yavaşlama deneyiyle $J_m$'yi ölçmektir.
4. **Sürekli yük düşüktür:** Dengede ortalama tork, 10°'deki tutma torkunun bile altındadır (@@tutma_motor@@ N·m/motor). Bu değer iki varyantın en yüksek verim noktası torkunun (530 RPM: @@aday_verim@@, önerilen: @@en_iyi_verim@@ N·m) altındadır. Satıcının "durma torkuna yakın sürekli çalıştırmayın" uyarısı yalnız kısa toparlanma tepelerinde zorlanır.
5. **Sigorta:** A noktasında iki motorun tepe akımı 5 A sigortanın altında kalır; iki motor aynı anda kilitlenirse durma akımı 2 × 2,4 = 4,8 A ile sınıra yaklaşır (ön listede de "ölç" notu var). Motor gelince teker elle tutulup akım ölçülmelidir.

**Gerilim sürüşünde model.** Referans değerlerden teker milinde $K_t$ = @@Kt@@ N·m/A, $K_e$ = @@Ke@@ V·s/rad, $R$ = @@Ra@@ Ω çıkar [doğrulanamadı]. Sürücü gerilim kontrollü kullanılırsa zıt EMK motor başına $b$ ≈ @@b_emf@@ N·m·s/rad sönüm ekler ve açık çevrim kararsız kutup +@@p@@'den +@@p_gerilim@@ 1/s'ye iner (`model.gerilim_girisli_durum_uzay`).

## 5. İlaç kutusu yuvası kütle merkezi analizi

### 5.1 Yöntem

Kutu ve yuva, kütle bütçesine (§2.2) bileşen olarak eklendi. Her yuva seçeneği için kutusuz ve kutulu gövdenin KM'si, atalet tensörü, model kutupları, torkları ve düşme süresi yeniden hesaplandı. Yatay ofset $x_c$'nin etkisi denge (trim) açısıyla ifade edildi. KM aksın tam üstüne gelsin diye gövdenin alması gereken eğim şudur:

$$
\theta_\text{trim} = -\arctan\frac{x_c}{z_c}.
$$

### 5.2 Kutulu ve kutusuz KM

@@tablo_com@@

@@tablo_kutu_etkisi@@

**Yorum.** Bütün seçeneklerde kutu KM'yi en fazla @@dl_max@@ mm oynatır ve kutbu en fazla %@@dp_max@@ değiştirir. Yatay ofset ($x_c$ = @@xc@@ mm, trim @@trim@@°) kutudan değil, öne yerleştirildiği varsayılan IR/şarj kontağı modülünden gelir. Kutu aksın tam üstünde olduğu için takılıp çıkarılması trimi neredeyse değiştirmez. Trim açısı 5./6. haftada IMU montaj hatasıyla birlikte kalibre edilecektir [öneri].

### 5.3 Kutunun yuvadaki boşluk kadar kayması

Kutu yuvada ±δ kayabilir. Kayma KM'yi $\Delta x_c = m_\text{kutu}\,\delta / m_b$ kadar öteler ve trim açısını değiştirir. Kutu karşı duvara $2\delta$ yol alarak çarparsa gövdeye küçük bir açısal itme verir. Çarpma hızı, yuvadaki en büyük özgül kuvvetle (§5.5, @@fx_max@@ m/s²) hesaplandı.

@@tablo_kayma@@

En ağır tahmini kutuda (@@kutu_agir@@ g) bile @@bosluk@@ mm boşluk trimi @@dtrim_agir@@° değiştirir. Bu değer IMU ölçüm gürültüsü mertebesindedir. **Boşluğun asıl riski dengeye değil, kutunun tutulmasına ilişkindir.** Bu yüzden boşluk ≤ @@bosluk@@ mm önerilir [öneri].

### 5.4 KM yüksekliğinin düşme hızına ve torka etkisi

En ağır taşınabilir bileşen batarya olduğundan KM yüksekliği bataryanın konumuyla tarandı (z = @@bt_z_min@@ → @@bt_z_max@@ cm, $l$ = @@bt_l_min@@ → @@bt_l_max@@ mm). Kütle bütçesi tutarlı kaldığı için hem $l$ hem $I_{yy}$ birlikte değişir.

![Şekil 8](sekiller/sekil_08_km_yuksekligi.png)

*Şekil 8: KM yüksekliğinin etkisi. Solda kararsız kutup: tam model (serbest ve kilitli teker) ile noktasal kütle yaklaşımı $\sqrt{g/l}$. Ortada 10°'deki tork, sağda 10°'den yere değme süresi.*

- **Düşme hızı.** Noktasal kütle ve sabit pivot için $p = \sqrt{g/l}$ olur ve KM yükseldikçe düşme yavaşlar. Bu formül modelde doğru sınır olarak çıkar (test: teker ataleti çok büyük ve $I_{yy} \to 0$ iken $p \to \sqrt{g/l}$). Bu robotta ise tekerler hafiftir ve $u = 0$ iken gövde kabaca kendi KM'si etrafında döner. Bu durumda $p \approx \sqrt{m_b g l / I_{yy}}$ olur ve $l$ ile birlikte $I_{yy}$ de değiştiği için kutup monoton değişmez, dar bir aralıkta (@@bt_p_min@@–@@bt_p_max@@ 1/s) kalır. Kilitli teker kutbu da benzer biçimde düzdür. **Sonuç: KM'yi yükseltmek bu tasarımda kontrolü belirgin kolaylaştırmaz.**
- **Tork.** $m_b g l\sin 10°$, $l$ ile doğrusal artar (@@bt_tau_min@@ → @@bt_tau_max@@ N·m, +%@@bt_tau_artis@@). Tam modeldeki tutma torku da aynı yönde, daha az artar.
- **Düşme süresi.** 10°'den yere değme süresi @@bt_t_min@@–@@bt_t_max@@ ms arasında kalır. Pasif test her yükseklikte sağlanır.
- **Öneri:** Batarya orta katta tutulmalıdır. Aşağı indirmek torku azaltır ama aksın altına inmemelidir (§3.7, pasif test). Yukarı taşımak kontrol açısından kazanç sağlamadan torku artırır [öneri].

### 5.5 Yuva konumu karşılaştırması ve öneri

Kutunun yuvada hissettiği yük için gövde ekseni üzerindeki bir noktada gövdeye dik özgül kuvvet ($b = 0$, $J_m = 0$) şöyle yazılır:

$$
f_x = (z - z_{cp})\,\ddot\theta - \frac{u}{m_b l},\qquad z_{cp} = l + \frac{I_{yy}}{m_b l} = @@z_cp@@\ \text{mm (vuruş merkezi)}
$$

Bu özdeşlik doğrusal olmayan yörüngede test edildi. Kutu yüksekliği yalnız $\ddot\theta$ terimini etkiler, tork terimi yükseklikten bağımsızdır. Kutunun görünür eğimi $\alpha = \arctan(f_x / f_z)$ referans manevralarda hesaplandı (Şekil 9). Kutu, yuva tabanında sürtünmeyle kaymadan durabilmek için $\alpha < \arctan\mu_k$ = @@surtunme_acisi@@° koşulunu sağlamalıdır (μ_k = @@mu_k@@, tahmini).

![Şekil 9](sekiller/sekil_09_kutu_yuvasi.png)

*Şekil 9: Kutu yüksekliğinin etkisi. Solda kutu eklenince KM değişimi (yuva aynı yerde), sağda yuvada en büyük görünür eğim. Dikey çizgiler değerlendirilen üç yuva yüksekliğidir; turuncu olan önerilen seçenektir.*

@@tablo_secenek@@

**Öneri: üst plaka yuvası [öneri].**

1. **Konum:** Üst plakada, aksın tam üstünde ($x = 0$) ve yanal merkezde ($y = 0$). Böylece kutu takılıp çıkarılınca trim değişmez ve 90° dönüşlerde kutu dönme ekseni üzerinde kaldığı için merkezkaç yükü almaz.
2. **Dinamik bedeli küçüktür:** Kutu eklenince kutup %@@dp_oner@@, statik tork %@@dtau_oner@@ değişir. Yuvadaki en büyük görünür eğim @@alfa_oner@@°'dir ve kayma sınırının (@@surtunme_acisi@@°) @@alfa_oran@@ katı paya sahiptir. Duvarsız bir tabla bile kutuyu sürtünmeyle tutabilir; duvarlar darbe ve çarpışmalara karşı güvencedir.
3. **Sistem gerekçesi:** Mobil uygulama "taşınan eşyanın durumu"nu kameradan değerlendirir (şartname §5.2; Oytun'un 5. hafta görevi: kutunun kamerada tespiti). Üst yuva kutuyu kameraya açık tutar, her testin başında kutunun konmasını kolaylaştırır ve iç yerleşime dokunmaz.
4. **Yuva geometrisi:** Kutu yatık (en geniş yüzü altta) ve uzun kenarı yanal. Bu hâlde devrilme için $\alpha$ > @@devrilme_acisi@@° gerekir. Boşluk her yönde ≤ @@bosluk@@ mm. Duvar yüksekliği ≈ @@duvar@@ mm, yani kutu yüksekliğinin (@@kutu_y@@ mm) yaklaşık %80'i; böylece kutunun KM'si duvar üst kenarının altında kalır. Yuva gövdeye sabitlenir, kutu yuvaya **sabitlenmez** (şartname §4.1).
5. **Alternatif:** Alt yuva yükleri en aza indirir ($\alpha$ en küçük, statik tork en az artar), ama kutu kameraya kapalı kalır, yerleştirmesi zordur ve elektronik katıyla çakışır. Testlerde üst yuvada kutu tutma sorunu çıkarsa (9. hafta, Mete) ikinci seçenek orta kattır.

### 5.6 Yere değme açısı

İki teker dışında bir parçanın yere değmesi alt testi düşürür (şartname §7). Gövdedeki $(x_b, z_b)$ noktası, $r - x_b\sin\theta + z_b\cos\theta = 0$ olduğunda yere değer. Aksa uzaklığı $r$'den küçük olan noktalar hiç değmez.

@@tablo_temas@@

Toparlanma ±10°'den başlar ve aşım yapabilir. Önerilen alt sınır ≥ @@yere_degme_min@@°'dir [öneri]; tahmini gövdede en küçük açılar ileri @@temas@@° (@@temas_nokta@@) ve geri @@temas_geri@@° (@@temas_nokta_geri@@) ile bu sağlanır. Alçak ve öne taşan parçalar (IR alıcıları, şarj kontakları) sınırı küçültür. Mete'nin şasi çiziminde ve Ömer Faruk'un kontak yerleşiminde bu açı kontrol edilmelidir.

## 6. Belirsizlik: hangi tahmin sonucu en çok değiştiriyor?

Aralığı tanımlı her fiziksel parametre, diğerleri nominalde tutularak aralığın iki ucuna çekildi. Nominal değerler: @@duyarlilik_taban@@.

@@tablo_duyarlilik@@

**Ölçüm önceliği:** (1) yansıyan rotor ataleti ve sürtünme (motor seçilince tanılama), (2) kutu, şasi ve batarya kütleleri (tartı), (3) teker yarıçapı. El hesabı rotor ataletine ve teker yarıçapına bağlı değildir. Tam model ise bu ikisine duyarlıdır; el hesabının tasarım değeri olarak tutulmasının bir nedeni de budur.

## 7. Mete'den ve diğer üyelerden beklenen girdiler

| Girdi | Kimden | Neden gerekli / hangi sonucu değiştirir | Ne zaman |
|---|---|---|---|
| Batarya: ön liste 3S (3 × Orion 18650P) diyor; bizim ekibin seçimi ve BMS kesim gerilimi | Mete Özgen | Gerilim aralığı → motor $n_0$, $\tau_s$ ölçeklemesi (§4.5, §4.7); boş batarya gerilimi aday motorun emniyet payını belirler | 3. hafta (Mete'nin BOM'u) |
| Batarya kütlesi ve boyutu | Mete Özgen | KM ve $I_{yy}$ (§5); duyarlılık tablosunda @@sira_batarya@@. sırada (§6) | 3. hafta |
| Yerleşim: kat yükseklikleri, bataryanın ve elektroniğin konumu, şasi malzemesi ve zarf ölçüleri | Mete Özgen | KM yüksekliği (§5.4); yere değme açısı (§5.6); pasif test için KM aksın üstünde olmalı | 3.–4. hafta |
| Motor kararı: 530 RPM mı 333 RPM mi (§4.7 öneri); satıcının veri sayfası (oran, durma torku/akımı, varsa rotor ataleti) | Mete Özgen | Şu anki değerler rcdrone referansı [doğrulanamadı]; A/A'/B noktaları, enkoder, $J_m$ | 3. hafta |
| Motor tipi kararı (§10.11): bir adet 17HS4401 alınması, faz direnci/endüktansı ve pull-out ölçümü (12 V, @@V_min@@ V) | Mete Özgen, Sefa Nurali Uçak | Step motorun tork payı şu an [doğrulanamadı] geçici eğriye dayanıyor; karar eşiği §10.11 | Motor kararından önce |
| Step seçilirse: çift milli motor bulunup bulunmadığı, 5 mm mil–teker bağlantısı, braket köşeleri, AS5600 mıknatısı ve montajı | Mete Özgen | §10.8 montaj seçenekleri; yerden pay yalnız @@st_kose_pay@@ mm | Motor kararıyla |
| Motor sürücüsü: sürekli/tepe akım, akım sınırı, enerjisizken serbest mi frenli mi | Mete Özgen | Tork sınırı; pasif testte serbest/kilitli teker durumu (§3.7) | 3.–4. hafta |
| Ana hat sigortası: ön liste 5 A diyor | Mete Özgen | A noktasındaki tepe akım sigortanın altında; iki motor kilitlenmesi (4,8 A) sınırda, ölçülmeli | 4. hafta |
| Teker: ön liste 65 mm diyor; teker kütlesi ve iz genişliği | Mete Özgen | Devir (∝ 1/r), çekiş sınırı, enkoder CPR (∝ r), sapma modeli | 3. hafta |
| Kutu yuvası iç ölçüsü, boşluk, duvar yüksekliği, kütlesi | Mete Özgen | §5.3 ve §5.5; yuva üretimi 4. hafta, iyileştirme 9. hafta | 4. hafta |
| IR alıcı + şarj kontağı modülünün kütlesi, konumu (ön/arka) ve yüksekliği | Ömer Faruk Arslan | Trim açısı (şu an @@trim@@°), yere değme açısı (§5.6) | 3.–4. hafta |
| İlaç kutusunun seçimi: ölçü ve kütle | Ekip | Yuva boyutu; kutu kütlesi duyarlılık tablosunda @@sira_kutu@@. sırada (§6) | 4. hafta öncesi |
| Kameranın kutuyu hangi açıdan göreceği | Oytun Utkan Yeşilyurt | Üst yuva önerisinin doğrulanması (§5.5) | 5. hafta |
| Telemetrideki eğim açısının işaret ve birim tanımı | Ousmane Dicko, Oytun Utkan Yeşilyurt | Bu modeldeki tanım (ileri eğim pozitif, derece) uygulamada da kullanılmalı [öneri] | 6. hafta |

## 8. Doğrulama

Testler `pytest` ile çalıştırılır. Bu belge üretilirken alınan sonuç:

> **@@pytest@@**

| İstenen kontrol | Nasıl yapıldı | Test dosyası |
|---|---|---|
| Simülasyon çalışıyor; en az bir kutup sağ yarı düzlemde | Kutulu ve kutusuz için $\max\operatorname{Re}(\lambda) > 0$; ±10° düşme simülasyonu | `test_model.py`, `test_simulasyon.py` |
| Model doğru türetildi | Sembolik türetim = el ile yazılan denklemler; doğrusallaştırma = doğrusal olmayan modelin sayısal Jakobiyeni; $u = 0$, $b = 0$'da toplam enerji korunur (bağıl sapma < 10⁻⁸); ±10° simetrisi; küçük açıda doğrusal ve doğrusal olmayan model örtüşür | `test_model.py`, `test_simulasyon.py` |
| Birimler | Formüller `pint` ile birimli büyüklüklerle yeniden hesaplanır; boyut ve değer karşılaştırılır ($p^2$ [1/s²], $K_\theta$ [1/(kg·m²)], torklar [N·m], devir, kgf·cm dönüşümü, enkoder) | `test_birimler.py` |
| Parametre değişince sonuçlar mantıklı değişiyor | Bütün kütleler ×2 → KM ve kutup aynı, torklar ×2; $g$ ×4 → kutup ×2; sabit pivot + noktasal kütle → $\sqrt{g/l}$; batarya yukarı → $l$ ve statik tork artar; $r$ büyür → devir ∝ 1/r, CPR ∝ r; süre yarıya → devir ×2; $t_r$ yarıya → dinamik pay ×4; SF → tork doğrusal; $J_m$, $b$ artar → kutup yavaşlar; kutu ağırlaşır → Δl artar; kayma δ → trim doğrusal | `test_duyarlilik.py` |
| Şartname kısıtları | Pasif test: ±10°'den 5 s içinde dikleşmez; KM aksın altına inerse ihlal yakalanır; batarya ≤ 24 V | `test_simulasyon.py`, `test_parametreler.py` |
| Parametre dosyasının bütünlüğü | Her parametrede birim/durum/kaynak var; fiziksel parametrelerin hepsi "tahmini"; hatalı dosya reddedilir | `test_parametreler.py` |
| Step motor seçeneği | DC değerleri sürüm 0.2 ile aynı; ivme girişli kutup = tork modelindeki $X/U$ sıfırı, bağıl ivme girişli kutup = kilitli teker kutbu; $J_m$, $b$ ivme girişli modeli değiştirmez; $a(t)$ tam modelle tutarlı; eğri devirle artmaz, gerilimle düşmez; ölçüm girilince geçici eğri kullanılmaz; detent düşmeyi engellemez; birimler (`pint`) | `test_step.py` |
| Motor hesapları | Tutma torku doğrusal olmayan modelde $\ddot\theta = 0$ verir; tutma ≤ referans manevra ≤ el hesabı; uzun manevrada tepe tork → tutma torku; sınır motor eğrisi noktalara teğet | `test_motor.py` |

## 9. Sınırlamalar ve sonraki adımlar

**Sınırlamalar.** Bütün fiziksel değerler tahminidir. Motor elektrik dinamiği, teker kayması, zemin eğimi ve esnek yapı modellenmedi. Referans manevralar kontrolcü değildir; gerçek kontrolcünün tepe torku başlangıçta daha yüksek olabilir. Emniyet katsayısı bunun için konmuştur. Kutu yuvada rijit kabul edildi (kayma ayrıca incelendi).

**Sonraki adımlar.**

1. **4. hafta (Mete ile):** Şasi ve motorlar takılınca bileşenleri tartıp `parametreler.toml`'u güncellemek, belgeyi yeniden üretmek. Pasif kararlılık ön testinde düşme süresini (öngörü @@t_hepsi_min@@–@@t_hepsi_max@@ s) video ve kronometreyle ölçmek. IMU'yu şasiye monte etmek.
2. **Motor gelince:** Serbest yavaşlama deneyiyle $J_m$ ve $b$'yi tanılamak; durma torkunu, durma akımını ve boşta devri batarya geriliminde ölçüp rcdrone referans değerlerinin ([doğrulanamadı]) yerine koymak.
3. **5. hafta:** Kalman veya tamamlayıcı filtre. Enkoder bağıl açı düzeltmesi $x = r(\varphi_\text{enk} + \theta)$ ve trim kalibrasyonu da buraya eklenecek.
4. **6. hafta:** Kontrol yöntemi seçimi (PID, LQR veya MPC). Bu belgedeki $(A, B, C, D)$, $G_\theta$, $G_x$ ve $(A_d, B_d)$ doğrudan kullanılır. Tork doyumu çekiş sınırına göre ayarlanır. Step motor seçilirse giriş ivme olur (§10.3) ve doyum yerine ivme ve devir sınırı kullanılır (§10.5).
5. **Motor tipi kararı:** Bir adet 17HS4401 ile §10.10'daki ölçüm; karar eşiği §10.11.

## 10. Step motor seçeneği ve DC ile karşılaştırma

> **Durum (@@tarih@@).** Ekip 2 adet DRV8825 ve 2 adet AS5600 aldı, motor alınmadı. Karar DC (JGB37-520 333 RPM + BTS7960) ile step motor (Nema 17 17HS4401 + DRV8825) arasındadır. Motor tipi parametre oldu (`tahrik.tip`); §1–§9'daki DC sonuçları sayısal olarak değişmedi. **17HS4401'in kendi pull-out eğrisi bulunamadı.** Bu bölümdeki tork payları, kardeş motorlardan türetilen geçici eğriye dayanır ve **[doğrulanamadı]** sayılır. Kesin karar, bir motorla yapılacak ölçüme bağlıdır (§10.10). Eğrinin durumu: @@st_egri_durumu@@.

### 10.1 Motor verileri

"17HS4401" adı tek bir ürünü göstermiyor; satışta en az iki farklı sargı var. robo90'ın verdiği değerler (1,5 A, 1,8 Ω, 300 g, 38 mm) samm sayfasıyla eşleşiyor; eksikleri samm'dan tamamlandı, ama aynı ürün oldukları doğrulanamadı. MotionKing kataloğunun 17HS4401 satırı ise 1,7 A ve 1,5 Ω'dur. Bütün değerler [doğrulanamadı]. Motor gelince faz direnci ve endüktansı ölçülerek hangi sargının geldiği anlaşılır. Tork alt sınırı iki sargıyı da kapsar.

@@tablo_st_sargi@@

Redüktör yoktur, teker doğrudan mile bağlanır. Bu yüzden rotor ataleti teker miline olduğu gibi yansır ($N = 1$, $J_m$ = @@st_Jm@@ g·cm²). DC motorda bu değer bilinmiyordu ve $N^2$ ile büyüyordu (§3.8, §4.3).

### 10.2 Geçici pull-out eğrisi

Türkçe, İngilizce ve Çince kaynaklarda, üretici ve satıcı sayfalarında ve forum ölçümlerinde 17HS4401 için pull-out eğrisi bulunamadı; 12 V eğrisi bu sınıftaki hiçbir motor için çıkmadı. En yakın veri, aynı sınıftan iki kardeş motorun 24 V eğrisidir (PDF'teki şekilden okundu, hata ±0,5 N·cm):

@@tablo_st_kardes@@

Geçici eğri bu verilerden şu kuralla türetildi [öneri]:

1. Sürücü, $I$ tepe akımını ancak yeterli gerilim payı varsa basabilir. Payın bittiği devir $n_b$, zıt EMK, direnç düşümü ve endüktans geriliminden çıkar:

   $$
   \left(K_t\,\omega_b + I(R + R_s)\right)^2 + \left(50\,\omega_b L I\right)^2 = V^2,\qquad K_t = \frac{T_\text{tutma}}{\sqrt{2}\,I_\text{anma}},\qquad n_b = \frac{60\,\omega_b}{2\pi}
   $$

   Burada 50, 1,8°'lik motorun kutup çifti sayısı, $R_s$ DRV8825'in iç direncidir (üst + alt FET, @@st_Rds@@ Ω).

2. Kardeş eğriler $n/n_b$ eksenine taşınınca aynı biçime oturur (Şekil 10): ikisi de $n_b$'de %@@st_kayip_nb@@ tork kaybeder, biri diğerinin biçimini en çok %@@st_capraz@@ hatayla öngörür.

3. 17HS4401 için tork şöyle alındı: $h$, kardeş motorun torku bölü tutma torkudur.

   $$
   T(n;\,V, I) = K_t\, I\; h\!\left(\frac{n}{n_b(V, I)}\right)
   $$

   Alt sınır iki sargının ve iki kardeşin en kötüsü, üst sınır en iyisidir. Bu eğri ölçülünce parametre dosyasındaki `step_egri.olcum` alanları doldurulur ve onun yerine ölçüm kullanılır.

**DRV8825 bu ayarda etiket torkunu vermez.** Sürücünün akım limiti faz başına *tepe* değerdir; etiketteki tutma torku ise iki fazda anma akımı içindir (bu satıcı sayfalarında yazmıyor, yaygın tanım kabul edildi). Kardeş eğriler bunu destekliyor: 1,69 A *etkin* akımda (DM542T tablosunda 2,37 A tepe) düşük hız torku etiket torkuna yakındır. Bu yüzden @@st_I@@ A limitte faz başına etkin akım @@st_I_etkin@@ A olur ve 1,5 A'lik sargı etiket torkunun %@@st_I_tam@@'ini verir: @@st_T_etiket@@ N·cm yerine @@st_T_a@@ N·cm (1,7 A'lik sargıda @@st_T_b@@ N·cm).

![Şekil 10](sekiller/sekil_10_step_kardes.png)

*Şekil 10: Solda kardeş motorların yayımlanmış 24 V eğrileri; bunlar 17HS4401'in eğrisi değildir. Sağda aynı eğriler gerilim payı devrine göre normalleştirilmiş hâlde; gri alan geçici eğrinin alt–üst sınırıdır.*

Motor başına geçici pull-out torku, @@st_I@@ A limit:

@@tablo_st_egri@@

Payın bittiği devir $n_b$: 1,5 A'lik sargıda 12 V'ta @@st_nb_a_12@@, @@V_min@@ V'ta @@st_nb_a_9@@ dev/dk; 1,7 A'lik sargıda 12 V'ta @@st_nb_b_12@@, @@V_min@@ V'ta @@st_nb_b_9@@ dev/dk.

**Bu eğrinin sınırları.** Biçim kuralı yalnız iki motorla ve yalnız 24 V'ta sınandı. 24 V'tan 12 V'a ölçekleme hiçbir veriyle doğrulanmadı; kardeş eğrilerde kullanılan sürücü de DRV8825 değildir. Ayrıca iki başka eğride (17HS16-2004S1 yarım adım, JK42HS40-1004AC tam adım) düşük hızda rezonans çukuru vardır ve tork yaklaşık @@st_rezonans@@ katına iner. 1/16 mikro adımda bu çukurun daha küçük olması beklenir, ama ölçülmedi. Bu yüzden tablolarda ayrı bir kötü durum sütunu olarak verildi.

### 10.3 Step motorlu model: giriş teker ivmesi

Pull-out sınırı aşılmadığı sürece step motor konum kaynağı gibi davranır. Tork artık seçilen giriş değil, hareketin sonucudur. Tork, iki hareket denkleminden elenince (§4.3'teki düz çıkış denklemi) şu kalır:

$$
c_1\,\ddot x + c_2\,\ddot\theta = m_b g l\,\theta,\qquad c_1 = M_x r + a_{12} = @@st_c1@@\ \text{kg·m},\qquad c_2 = a_{12} r + a_{22} = @@st_c2@@\ \text{kg·m²}
$$

$J_m$ ve $b$ bu katsayılarda sadeleşir. **Yani hareket denklemi bilinmeyen motor parametrelerine bağlı değildir;** bu parametreler yalnız motordan istenen torku değiştirir (test: `test_ivme_girisli_model_bilinmeyen_motora_bagli_degil`). Giriş $a = \ddot x$ [m/s²], durum $[x,\ \dot x,\ \theta,\ \dot\theta]^\mathsf{T}$, $C = I_4$, $D = 0$:

$$
A_a = \begin{bmatrix} 0&1&0&0\\0&0&0&0\\0&0&0&1\\0&0&m_b g l/c_2&0\end{bmatrix} = @@st_Aa@@,\qquad
B_a = \begin{bmatrix}0\\1\\0\\-c_1/c_2\end{bmatrix} = @@st_Ba@@
$$

$$
\frac{\Theta(s)}{A(s)} = \frac{-@@st_K_a@@}{s^2 - @@st_z2@@} = \frac{-@@st_K_a@@}{(s - @@st_z_m@@)(s + @@st_z_m@@)},\qquad \frac{X(s)}{A(s)} = \frac{1}{s^2}
$$

**Açık çevrim kutbu** seçilen giriş tanımına göre değişir, ama sağ yarı düzlemde kalır:

| Girişi sıfır tutmak ne demek | Kararsız kutup [1/s] |
|---|---:|
| Teker merkezi ivmesiz, $a = 0$ (DC modeldeki $X/U$ sıfırıyla aynı) | +@@st_z@@ (zaman sabiti @@st_zaman@@ ms) |
| Motor enerjili ve adım atmıyor, $\alpha = 0$: robot tek parça yuvarlanır (kilitli teker kutbu) | +@@st_pk@@ |
| Karşılaştırma: tork girişi, mil serbest (aynı kütlede) | +@@st_pu@@ |

**Sürücünün gerçek girişi.** Step sürücü, milin *gövdeye göre* dönüşünü komutlar: $\alpha = \ddot x/r - \ddot\theta$. Bu girişle $A_\alpha = @@st_Aal@@$, $B_\alpha = @@st_Bal@@$ olur (`model.bagil_ivme_girisli_durum_uzay`; $J_k = c_2 + c_1 r = @@st_Jk@@$ kg·m²). Pratikte kontrolcü $\dot x_k$ hızını üretir ve jiroskoptan gelen $\dot\theta$ ile adım frekansına çevrilir ($\mu$: mikro adım çarpanı):

$$
f_\text{step} = \frac{200\,\mu}{2\pi}\left(\frac{\dot x_k}{r} - \dot\theta\right)
$$

Sapma için $\ddot\psi = (a_R - a_L)/d$ olur, yani girişi fark ivmesi olan bir çift integratördür.

**±10° toparlanma.** §4.3'teki referans manevra aynı kaldı; giriş $a(t)$ doğrusal olmayan denklemden cebirsel olarak bulundu. Bu $a(t)$ doğrusal olmayan modele uygulanınca $\theta(t)$ referansı izler (en büyük fark @@st_ileri_hata@@°). Tepe ivme @@st_a_tepe@@ m/s², tepe motor devri @@st_n_tepe@@ dev/dk, motor başına tepe tork @@st_tau_tepe@@ N·cm'dir; aks @@st_x_f@@ cm ilerler. Motor devri $\dot x/r - \dot\theta$ olduğu için gövdenin dönüşünü de içerir.

![Şekil 11](sekiller/sekil_11_step_toparlanma.png)

*Şekil 11: İvme girişli ±10° toparlanma, T = @@st_T_ref@@ s (+10° gösterildi; kontrolcü değildir). Üstte eğim ve giriş; altta girişin sonucu olan devir ve tork. Bu devir ve tork §10.5'te pull-out eğrisiyle karşılaştırılır.*

### 10.4 Motor kütlesinin etkisi

Değerler parametre dosyasından hesaplandı. Motor başına kütle 150 g'dan 300 g'a çıkar; elektronik kütlesi değiştirilmedi (BTS7960'tan DRV8825'e geçiş biraz hafifletir, hesaba katılmadı).

@@tablo_st_kutle@@

Motorlar aks üstünde olduğu için (z = 0) $m_b l$ çarpımı değişmez. Bu yüzden statik tork ve el hesabı aynı kalır, KM ise @@st_l_dc@@ mm'den @@st_l@@ mm'ye iner. Toplam kütle arttığı için çekiş sınırı da artar (motor başına @@st_cekis_motor@@ N·cm). Pasif test öngörüsü pek değişmez. KM aksın üstünde kaldığı için şartname §4.1 etkilenmez.

### 10.5 Adım kaçırma kontrolü

Pay, pull-out torkunun motordan istenen torka oranıdır; manevra boyunca en küçük değer alındı. Devir, milin gövdeye göre devridir. Torklar motor başınadır.

@@tablo_st_pay@@

![Şekil 12](sekiller/sekil_12_step_cekme.png)

*Şekil 12: Geçici pull-out eğrisi (gri: alt–üst sınır, kesikli: alt sınır × rezonans düşümü) ile motordan istenen tork-devir yolları. Noktalar §4.5'teki gereksinimlerin step motorlu kütleyle yeniden hesaplanmış hâlidir. Kardeş verisinin bittiği devirde çizim durur; ötesi bilinmiyor. Bu eğri ölçüm değildir.*

**Yorum:**

- **Referans manevraların hepsi rahat.** Boş bataryada alt sınırda en küçük pay @@st_pay_man_min@@, rezonans düşümüyle @@st_pay_man_rez@@'tür. Bu manevralarda adım kaçması öngörülmüyor.
- **El hesabı daha zorlayıcıdır.** İki kat emniyetli A noktası boş bataryada @@st_pay_A_alt@@–@@st_pay_A_ust@@ payla geçer; ama rezonans çukuruna denk gelirse @@st_pay_A_rez@@'e düşer. Katsayısız el hesabı (A₀) rezonansla da geçer. Sağlanan emniyet katsayısı @@st_sf_alt@@–@@st_sf_ust@@, rezonansla @@st_sf_rez@@'dir. DC 333 RPM aynı ölçüde @@st_sf_dc@@ verir.
- **Bu devirlerde sınırı çoğunlukla zemin koyar.** Alt eğri @@st_nA@@ dev/dk'da çekiş sınırının @@st_pay_A2_alt@@ katıdır. Yani rezonans yoksa teker, adım kaçmadan önce kayar.
- **Boş batarya bu devirlerde az etkilidir, yüksek hızı keser.** Gereken devirler $n_b$'nin altındadır. İki kat emniyetli tork (@@st_tA@@ N·cm) 12 V'ta @@st_n_sf12@@, @@V_min@@ V'ta @@st_n_sf@@ dev/dk'ya kadar alınır; katsayısız tork (@@st_tA0@@ N·cm) 12 V'ta @@st_n_a012@@, @@V_min@@ V'ta @@st_n_a0@@ dev/dk'ya kadar.

**Yazılım sınırları [öneri].** Adım kaçırmak robotu düşürdüğü için komut üzerinde sınır gerekir: devir ≤ @@st_n_sf@@ dev/dk (@@st_v_sf@@ m/s) ve ivme ≤ @@st_a_tavan@@ m/s² (alt eğrideki torkun 2 kat emniyetli karşılığı; çekiş sınırı @@st_mug@@ m/s²). Ölçüm gelince bu değerler güncellenecektir.

**Konum kaynağı varsayımının sınırı.** Rotor komuta rijit bağlı değildir, manyetik bir yay üstünde durur. Yük ataleti rotor ataletinin yaklaşık @@st_J_orani@@ katıdır ve bu sistemin doğal frekansı yaklaşık @@st_f_burulma@@ Hz çıkar (tam adımda ≈ @@st_n_burulma@@ dev/dk). İvme girişli model bu frekansın altında geçerlidir. Sönümü düşük olabileceği için kontrol bant genişliği bundan uzak tutulmalıdır [öneri]. Bu mod ölçülmedi.

### 10.6 Adım frekansı ve ESP32

@@tablo_st_mikro@@

**Mikro adım önerisi: @@st_mikro@@ [öneri].** @@st_cpr@@ adım/teker devri, §4.6'daki hız çözünürlüğü hedefini karşılar. 1/4 ve altı karşılamaz. 1/32'nin ek bir hesap kazancı yoktur.

**ESP32 üretebilir mi? Evet.** Yazılımda sınırlanan @@st_n_sf@@ dev/dk'da @@st_mikro@@ ile en çok @@st_f_sf@@ kHz gerekir. DRV8825 sınırı @@st_f_max@@ kHz'dir (STEP darbesi en az 1,9 µs). FastAccelStepper kütüphanesi ESP32'de MCPWM/PCNT veya RMT birimleriyle 200 kHz'e kadar adım üretir.

**FastAccelStepper uygun mu? Uygun görünüyor, üç noktaya dikkatle.** Bunların hiçbiri henüz donanımda denenmedi.

1. `moveByAcceleration()` ve `applySpeedAcceleration()` hareket sırasında ivme ve hız değiştirir. Bu, ivme girişli modele uyar.
2. Komutlar bir kuyruktan geçer. Varsayılan ileri planlama 20 ms'dir ve kütüphane açıklaması 8 ms'yi ideal sayar (ayar yalnız motor dururken değişir). @@f_kontrol@@ Hz döngüyle toplam gecikme @@st_gecikme@@ ms olur, varsayılanda @@st_gecikme_var@@ ms. Bunun kararsız kutupla çarpımı @@st_pt@@ (varsayılanda @@st_pt_var@@) çıkar. Bu çarpım küçük olmalıdır; bu yüzden @@st_plan@@ ms önerilir [öneri].
3. `getCurrentPosition()` darbeleri önden gider, yani kuyruğa alınmış adımları da sayar. AS5600 karşılaştırmasında bu fark düzeltilmelidir.

### 10.7 DRV8825 akım ayarı, ısınma, pil süresi ve sigorta

**Ayar.** Akım limiti = 2 × VREF (0,100 Ω algılama direnci), yani @@st_I@@ A için VREF = @@st_vref@@ V. Klon kartta direncin değeri okunmalıdır. TI, VREF 1 V'un altında doğruluğun düştüğünü belirtir; bu yüzden ayardan sonra faz akımı ölçülmelidir: tam adım kipinde faz başına ≈ @@st_I_etkin@@ A beklenir.

@@tablo_st_akim@@

Tork sütunu iki sargıyı da kapsar; kayıp, pil ve ısınma sütunları 1,5 A'lik sargı içindir. Pil akımı @@st_P_l@@ W lojik gücü de içerir (tahmini). Kayıplar anma direnci ve @@st_Rds@@ Ω sürücü direnciyle hesaplandı, sıcakken biraz artar. @@st_I@@ A'nın altında tork payı hızla erir, bu yüzden daha düşük bir ayar önerilmedi.

**Isınma.** Sürücü başına @@st_P_s@@ W kayıp, TI'ın kart varsayımıyla (@@st_r_th@@ °C/W) yaklaşık @@st_dT_s@@ °C artış verir. Küçük kartta daha kötüdür ve Pololu da soğutmasız üst sınırı ≈ 1,5 A verir. Yani bu ayar sınırdadır ve akım sürekli aktığı için küçük bir soğutucu ve hava yolu önerilir [öneri]. Isıl kapanma en az @@st_tsd@@ °C'dedir. Motor yaklaşık @@st_dT_m@@ °C ısınır (katalogdaki 80 °C sınırına göre kaba hesap): metal brakete bağlanmalı, kutu ve pil motora değmemelidir [öneri]. @@st_I2@@ A seçeneği torku @@st_I_oran@@ katına çıkarır, ama soğutucu + fan ister, motor ≈ @@st_dT_m2@@ °C ısınır ve pil süresi @@st_h2@@ saate iner. Yalnız ölçüm düşük çıkarsa düşünülmelidir.

**Dururken akım.** Step motor dururken de tam akım çeker; dengede motorlar kapatılamaz. Bu, DC ile en büyük farktır:

@@tablo_st_guc@@

DC'nin dengedeki akımı boşta akımdan alındı ve ölçülmedi. Pil süreleri nominal enerjiden hesaplandı; kesim gerilimi ve yaşlanma payı yoktur.

**Sigorta ve besleme.** 5 A sigorta step motor için yeterlidir: en kötü durumda pil akımı @@st_I_bat_max@@ A'dir ve akım sürücüde sınırlı olduğu için kilitlenmede artmaz. DRV8825 en az @@st_V_min_s@@ V ister; boş bataryada @@st_V_pay@@ V pay kalır. Gerilim bu değerin altına düşerse sürücü kapanır ve robot düşer, bu yüzden Mete'nin BMS kesim gerilimi önemlidir. Pololu, motor beslemesine en az 47 µF elektrolitik kondansatör önerir.

### 10.8 Enkoder yerine adım sayımı ve AS5600

@@tablo_st_coz@@

**Adım sayımı.** @@st_cpr@@ adım, @@cpr_min@@ sayım hedefini karşılar ve DC enkoderinden (@@st_dc_cpr@@) daha incedir. Hız kestirmeye de gerek kalmaz, çünkü hız komutun kendisidir. Ama bu sayım gerçek konum değildir: rotor yük altında komutun gerisinde kalır (dengede ≈ @@st_lag_t@@°, A torkunda ≈ @@st_lag_A@@° = @@st_lag_A_mm@@ mm). Asıl sorun, adım kaçarsa sayımın bunu bilmemesidir: konum ve sapma kestirimi sessizce bozulur. §4.6'daki bağıl açı düzeltmesi $x = r(\varphi + \theta)$ burada da geçerlidir.

**AS5600 adım kaçırmayı yakalar mı? Evet.** Adım kaybı 4 tam adım demektir: @@st_kayip_der@@° = @@st_kayip_lsb@@ sayım. Sensörün çözünürlüğü @@st_as_lsb@@°'dir. Komut ile ölçülen açı arasındaki fark @@st_esik_der@@°'yi (@@st_esik_lsb@@ sayım) aşarsa kayıp sayılabilir [öneri]; normal yük gecikmesi bir tam adımın altındadır. Sensör gecikmesi @@st_as_gec@@ ms'de (SF = 10) @@st_n_o1@@ dev/dk'daki açı farkı @@st_as_gec_der@@°'dir, yani eşiğin çok altındadır. Sensör gövdeye göre açıyı ölçtüğü için step komutuyla aynı referanstadır. Kayıp yakalanınca sayaç düzeltilir, ama robot bu sırada zaten devriliyor olabilir (zaman sabiti @@st_zaman@@ ms). Yani AS5600 kaybı önlemez; kestirimi korur, güvenli duruşu tetikler ve §10.10'daki ölçümde adım kaçtığı anı gösterir.

**Bağlantı.** AS5600'ün I²C adresi 0x36 ve sabittir; iki sensör aynı hatta olamaz. ESP32'nin iki donanım I²C birimi vardır: her sensör ayrı hatta bağlanır, MPU6050 (adres farklı) bunlardan biriyle paylaşılabilir [öneri]. 400 kHz'te bir okuma yaklaşık 0,11 ms sürer, yani @@f_kontrol@@ Hz döngüde sorun olmaz.

**Montaj.** AS5600, mil ekseninde duran diyametral mıknatıs ister: Ø6 mm, hava aralığı 0,5–3 mm, eksen kayması en çok 0,25 mm. Listedeki motor tek millidir ve ön mil tekere gider. Seçenekler:

| Seçenek | Nasıl | Artı / eksi |
|---|---|---|
| **1. Çift milli motor, arka mil [öneri]** | Mıknatıs arka mile, sensör motorun arkasına, gövde içinde bir plakaya | Korunaklı ve temiz. Motor henüz alınmadığı için mümkün; Türkiye'de stoğu ve bu sargıyla bulunup bulunmadığı doğrulanmadı |
| 2. Ön mil ucu, tekerin dış yüzü | Mıknatıs mil ucuna ya da göbeğe, sensör tekerin üstünden dolanan bir kolla gövdeye | Tek milli motorla olur. Kol dışarıda ve darbeye açık; iz genişliğini artırır; yere değme açısı (§5.6) ve kolun rijitliği kontrol edilmeli |
| 3. Arka kapağı delmek | - | Önerilmez: motoru bozma riski, talaş |

Motorun kaçak manyetik alanı sensöre yakındır. ams homojen dış alanın bastırıldığını belirtir, ama motor alanı homojen olmayabilir; ilk iş AGC ve MD bitlerini okuyup motor akımı açıkken açının kaymadığını doğrulamaktır [öneri]. AS5600 modüllerinin mıknatısla gelip gelmediği de kontrol edilmelidir.

### 10.9 Pasif kararlılık testi: detent düşmeyi engeller mi?

**Hayır.** Detent, milin gövdeye göre dönmesine karşı koyar, zemine karşı değil. Mil tamamen kilitli olsa bile robot tek parça olarak teker üstünde yuvarlanır ve KM aksın üstünde olduğu için düşer (§3.3, kilitli teker denklemi). Detent en kötü durum olarak sürekli sürtünme sayıldı (gerçekte konuma bağlıdır, ortalaması sıfırdır, yani daha az etkilidir):

@@tablo_st_detent@@

Robot @@st_t_min@@–@@st_t_max@@ s içinde yere değer, yani 5 s sınırının çok altında. Detent (toplam @@st_T_d_top@@ N·cm) düşmeyi yalnız biraz yavaşlatır. Dik kalması için zeminden gelen yuvarlanma direncinin @@st_statik@@ N·cm'lik gravite momentini dengelemesi gerekirdi; bu da yuvarlanma direnci katsayısının yaklaşık @@st_crr@@ olması demektir. Sert zeminde kauçuk teker için bu katsayı bunun çok altındadır. Sonuç: **step motorla da pasif test tasarım gereği geçilir**. Yine de 4. haftadaki gibi kronometre ve videoyla ölçülmelidir. Sürücü enerjisizken zıt EMK'nın sürücü diyotları üstünden frenleme yapıp yapmadığı da böylece görülür [öneri].

### 10.10 Ölçüm planı

Bir motor ve bir DRV8825 yeter [öneri]:

1. **Kimlik:** Faz direnci (multimetre, kablo direnci çıkarılarak), 1 kHz'de endüktans (LCR metre), kütle, gövde boyu, mil çapı ve biçimi. Sonuca göre `step_adayi.sargi` seçilir.
2. **Akım ayarı:** VREF = @@st_vref@@ V, tam adım kipinde faz başına ≈ @@st_I_etkin@@ A doğrulanır.
3. **Pull-out eğrisi:** Ayarlı güç kaynağından 12,0 V ve @@V_min@@ V (motor girişinde ölçülür), @@st_mikro@@ mikro adım. Devirler 30, 60, 90, 105, 120, 150, 180, 210, 250, 300 dev/dk. Mile makara takılır, ip ve iki el dinamometresiyle frenlenir: $T = (F_1 - F_2)\,r_\text{makara}$. Yük yavaşça artırılır; adım kaçmadan önceki son değer yazılır. Her nokta 3 tekrar. Adım kaçırma AS5600 ile (fark > @@st_esik_der@@°) ya da milin işaretiyle yakalanır. Motor ısınırken de bir tekrar yapılır.
4. **Rezonans:** 30–150 dev/dk aralığında 5 dev/dk adımla çukur aranır. Çukur varsa karar eşiği en kötü noktaya uygulanır.
5. **Detent torku:** Enerjisiz motorda mile bilinen uzunlukta kol takılır, dönmeye başladığı kuvvet okunur.
6. **Isınma:** @@st_I@@ A'de 30 dakika, motor ve sürücü sıcaklığı.
7. **Sonuç:** `step_egri.olcum` alanları doldurulur, durum "ölçülmüş" yapılır, `python -m denge` ile bu bölüm ölçümle yeniden üretilir.

### 10.11 Karşılaştırma ve öneri

Step motor sütunundaki tork ve hız değerleri geçici eğriye dayanır. Fiyatlar 5 Kasım 2026 tarihli satıcı sayfalarındandır ve [doğrulanamadı] sayılır. İki motorun veri sayfası değerleri de ölçülmedi.

@@tablo_st_karsilastirma@@

**Öneri [öneri]: önce bir adet 17HS4401 alıp ölçmek. Ölçüm geçerse step + AS5600; geçmezse DC 333 RPM.** Şu anda motor alınmadığı için bu ölçüm yaklaşık @@st_motor_tl@@ TL'ye kararı netleştirir.

**Step motor neden önde?** Rezonans çukuru yoksa hesapta tork payı DC'den az değildir (@@st_sf_alt@@–@@st_sf_ust@@, DC: @@st_sf_dc@@; çukur varsa @@st_sf_rez@@). Yaklaşık @@st_c_fark@@ TL daha ucuzdur, çünkü sürücüler alındı. Redüktör boşluğu ve ölü bölge yoktur; DC'de bilinmeyen $J_m$ ve $b$ burada hareket modelini etkilemez. Küçük ve hassas hareketlerde (istasyona yanaşma) adım konumu avantajdır.

**Neden şartlı?** Üç şey ölçülmeden iddia edilemez: 12 V eğrisi (hiçbir kaynakta yok), rezonans çukuru ve ≈ @@st_f_burulma@@ Hz modu. Ayrıca adım kaçırmanın bedeli DC'deki aşırı yükten büyüktür: DC yavaşlar, step motor senkron kaybedip robotu düşürür. Final 4 bağımsız tekrar istediği için bu risk ciddidir.

**Step motorun bedeli:** +@@st_dm@@ kg, pil süresi ≈ @@st_h_dc@@ yerine @@st_h@@ saat (testler için yine de yeterli görünüyor), sürekli ısınma, AS5600 montajı, IMU'ya gelen adım titreşimi (5. hafta filtresinde ölçülecek) ve 5 mm mil–teker bağlantısı. Teker başına radyal yük ≈ @@st_radyal@@ N, benzer motorda sınır @@st_radyal_sinir@@ N'dur [doğrulanamadı]. Motor köşesi aksa @@st_kose@@ mm uzaklıkta, teker yarıçapı @@st_r@@ mm: yerden yalnız @@st_kose_pay@@ mm pay kalır, bu yüzden braket köşeleri motor köşesini aşmamalıdır.

**Karar eşiği** (motor başına, @@V_min@@ V, @@st_I@@ A limit, 30–150 dev/dk aralığındaki en kötü nokta):

| Ölçülen pull-out torku | Karar |
|---|---|
| ≥ @@st_esik_gecer@@ N·cm | Step + AS5600 |
| @@st_esik_sinir@@–@@st_esik_gecer@@ N·cm | @@st_I2@@ A ve soğutmayla tekrar ölç. ≥ @@st_esik_gecer@@ N·cm olursa step, pil süresi @@st_h2@@ saat |
| < @@st_esik_sinir@@ N·cm | DC 333 RPM (§4.7) |

Step seçilirse 6. haftanın "motor ölü bölgesi telafisi" görevi kalkar, yerine adım üreteci, ivme ve devir sınırı ve adım kaybı yakalama gelir.

## Ek A: Dosyalar ve yeniden üretim

```
parametreler.toml        Bütün parametreler (değer, birim, durum, kaynak, aralık)
denge/model.py           Lagrange türetimi, doğrusallaştırma, durum-uzay, transfer fonksiyonu
denge/simulasyon.py      Açık çevrim düşme, referans manevralar (düz çıkış), ters dinamik
denge/motor.py           Devir, tork, çekiş, enkoder; aday motor aracı (python -m denge.motor)
denge/step.py            Step motor: geçici pull-out eğrisi, adım kaçırma, güç (python -m denge.step)
denge/kutle_merkezi.py   KM, atalet, yere değme açısı, yuvadaki özgül kuvvet
denge/yuva_analizi.py    Kutulu/kutusuz KM, kayma, KM yüksekliği ve yuva karşılaştırması
denge/rapor.py           Bu belgeyi ve şekilleri üretir (python -m denge)
tests/                   Doğrulama testleri (pytest)
```

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m denge          # şekiller + bu belge + test özeti
.venv/bin/python -m pytest -q      # testler
```

## Kaynaklar

1. Danışman ekip iş planı (`Danisman_Is_Plani.pdf`): Sefa Nurali Uçak 3. hafta görevi; 3. hafta toplantı teslimatı; haftalık bireysel değerlendirme rubriği; ortak kontrol noktaları.
2. YTÜ EEF ÇDTP, *İki Tekerlekli Ev İçi Hasta Destek Robotu, Güncel Proje Teknik Şartnamesi*, TR v14, 24 Eylül 2026: §4.1, §4.2, §5.2, §5.3, §7, §8.
3. cdtp-robot.netlify.app, *ÇDTP · Hasta Destek Robotu Proje Ortamı*, Malzeme ve Şema bölümleri (18 Ekim 2026'da okundu). Ön malzeme listesi bu referans listeden derlendi; Mete'nin seçimiyle kesinleşecek.
4. rcdrone.top, *JGB37-520 DC Gear Motor with Hall Encoder*, "12V — 10000RPM Before Reduction (Reference Only)" tablosu (18 Ekim 2026'da okundu). Satıcı tabloyu yalnız referans olarak verir; değerler [doğrulanamadı].
5. robo90.com, *17HS4401 Nema 17 Step Motor* ve market.samm.com, *17HS4401 Nema17 Step Motor* (5 Kasım 2026'da okundu). MotionKing, *HB Stepper Motor Catalog* MK1106 Rev.04 (datasheetcafe.com kopyası) ve direnc.net 17HS4401 veri sayfası. Handson Technology, *17HS4401S Data Specs*. Değerler [doğrulanamadı].
6. StepperOnline (omc-stepperonline.com, web.archive.org kopyaları): *17HS15-1504S* ve *17HS15-1684S* çizimleri ve *Torque Curve* PDF'leri, *17HS16-2004S1 Torque Curve*. Eckstein/JKongmotor, *JK42HS40-1004AC* veri sayfası (youmaketech.com kopyası). DM542T akım tablosu. Bunlar kardeş motorlardır; 17HS4401'in eğrisi değildir.
7. Texas Instruments, *DRV8825 Stepper Motor Controller IC*, SLVSA73F, Temmuz 2014. Pololu, *DRV8825 Stepper Motor Driver Carrier* (#2133).
8. FastAccelStepper (github.com/gin66/FastAccelStepper): README ve `src/FastAccelStepper.h` (5 Kasım 2026'da okundu).
9. ams, *AS5600 Datasheet*, v1-06, 20 Haziran 2018.
10. Fiyatlar: direnc.net JGB37-520 12V 333RPM Enkoderli Motor; robo90.com BTS7960B ve 17HS4401 sayfaları (5 Kasım 2026'da okundu). Değerler [doğrulanamadı].
11. Hareket denklemleri bu çalışmada temel ilkelerden (Lagrange–d'Alembert) türetilmiş ve sembolik olarak doğrulanmıştır (`denge/model.py`, `tests/test_model.py`).
