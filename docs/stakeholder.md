# AI Translation API — Dokumen Stakeholder

> **Audiens**: Manajemen, kepala departemen, dan tim IT/operasional PT. Integrity Indonesia.
> **Tujuan**: Memberikan gambaran utuh tentang apa yang sudah dibangun, manfaatnya bagi setiap departemen, dan apa yang dibutuhkan sebelum dipakai produksi.
> **Status**: MVP selesai. Siap pilot internal.
> **Versi**: 2026-05-20.

Detail teknis ada di `docs/technical.md`. Dokumen ini sengaja fokus ke implikasi bisnis.

---

## 1. Ringkasan Eksekutif

**Masalah.** Sebagai perusahaan jasa investigasi yang melayani klien lokal dan internasional, Integrity Indonesia setiap hari berurusan dengan dokumen, laporan, dan komunikasi multi-bahasa — dari laporan background screening, due diligence, sampai intake whistleblower. Penerjemah profesional mahal dan lambat untuk volume besar; layanan umum seperti Google Translate dan DeepL tidak mengerti terminologi investigasi/legal kita, tidak konsisten antar departemen, dan menimbulkan pertanyaan serius soal privasi data klien.

**Solusi.** Kami membangun **AI Translation API** yang setiap departemen bisa konfigurasi sendiri terminologinya — tanpa coding, tanpa perlu IT setiap kali ada perubahan. Sistem ini juga punya komponen kedua: **JavaScript SDK** yang bisa menerjemahkan halaman web internal (knowledge base, portal training) secara langsung dengan menambah satu baris script.

**Status.** MVP teknis selesai (7 fase pembangunan tuntas, diverifikasi 2026-05-20). Sistem berjalan end-to-end di lingkungan development. **Belum siap produksi**: butuh autentikasi user, hardening keamanan, dan pilot di 1–2 departemen dulu.

**Manfaat utama:**
- Terjemahan dengan **terminologi internal yang konsisten** per departemen (mis. istilah "predicate offense" untuk tim Anti-Bribery, "subject of investigation" untuk Background Screening) — diatur sekali, dipakai semua orang.
- **Biaya turun drastis** untuk konten berulang: terjemahan disimpan dan dipakai ulang otomatis, request berikutnya hampir gratis.
- **Tidak bergantung satu vendor AI** — sistem dirancang agar bisa pindah dari Claude ke vendor lain tanpa rewrite besar (proteksi vendor lock-in).
- **Audit-friendly**: setiap perubahan konfigurasi terjemahan tersimpan versinya, biaya per departemen bisa dilacak.

---

## 2. Latar Belakang & Masalah

### Konteks bisnis Integrity Indonesia

Lini produk kami melayani klien yang membutuhkan terjemahan dokumen sebagai bagian dari deliverable atau workflow:

- **Background Screening** — laporan investigasi untuk klien multinasional (sering EN ↔ ID, kadang JA/ZH untuk klien Jepang/Tionghoa).
- **Whistleblowing System** — pelapor bisa berasal dari berbagai bahasa; intake harus akurat sebelum di-handle.
- **Due Diligence** — investigasi korporat lintas yurisdiksi; ringkasan temuan sering perlu di-translate untuk legal counsel klien.
- **Brand Protection** — bukti pelanggaran merek dari pasar luar negeri (mis. listing e-commerce dalam bahasa Mandarin, Korea, Jepang).
- **Claim Protection** — komunikasi dengan klien asuransi internasional.
- **Know Your Customer (KYC)** — dokumen identitas dan korporat asing.
- **Anti-Bribery Management System (ABMS)** — materi training dan policy untuk klien multinasional.

### Kekurangan solusi umum (Google Translate, DeepL)

| Aspek | Layanan umum | Kebutuhan kita |
|---|---|---|
| Terminologi internal | Generic — "subject of investigation" jadi "subjek investigasi" (tidak natural) | Bisa diatur per departemen (mis. "individu yang diinvestigasi") |
| Konsistensi antar dokumen | Tergantung mood model | Glossary fixed — sekali set, selalu konsisten |
| Privasi data klien | Data mungkin di-log dan dipakai untuk training model | Bisa di-kontrol (pilihan vendor, retention policy, audit) |
| Embed di portal internal | Manual copy-paste | Drop-in script — auto-translate halaman web |
| Akuntabilitas perubahan | Tidak ada — model di-update kapan saja oleh vendor | Versi profile tersimpan, perubahan auditable |

### Hipotesis kami

Kalau **setiap departemen bisa konfigurasi terjemahannya sendiri tanpa coding** — termasuk glossary istilah, tone, dan contoh gaya bahasa — maka kualitas terjemahan naik signifikan dan adopsi internal jadi feasible. Tidak perlu lagi "AI tools yang dibeli tapi tidak dipakai" karena tidak cocok dengan workflow tim.

---

## 3. Apa yang Dibangun (Product Overview)

Sistem ini terdiri dari **dua produk yang saling melengkapi**.

### Produk A — Translation API Domain-Aware

Inti sistem. Setiap departemen punya **"profile"** sendiri:

- **Glossary** — daftar istilah khusus departemen dan cara penerjemahannya (mis. tim Background Screening: "criminal record" → "catatan kriminal", "civil litigation" → "perkara perdata"; bukan terjemahan generik).
- **Style examples** — contoh kalimat sumber + terjemahan yang disukai, sebagai panduan gaya.
- **Tone & target audience** — mis. "formal-legal untuk laporan klien" atau "ringkas untuk briefing internal".
- **Inheritance (pewarisan)** — profile bisa "mewarisi" profile lain. Contoh struktur untuk Integrity Indonesia:

```
investigasi-umum         (istilah forensik dasar, dipakai semua departemen investigasi)
├── due-diligence        (mewarisi semua di atas, plus istilah DD spesifik)
│   └── due-diligence-corporate   (mewarisi DD, plus istilah investigasi korporat)
├── background-screening
├── brand-protection
└── kyc

abms-umum                (istilah anti-bribery & compliance)
└── abms-training        (mewarisi ABMS, plus tone training)
```

Tim Due Diligence Corporate cukup atur istilah CS-spesifik mereka — sisanya **inherit otomatis** dari `due-diligence` dan `investigasi-umum`. Kalau profile umum berubah, semua child profile ikut update.

- **Update kapan saja, tanpa downtime.** Perubahan glossary atau tone langsung berlaku ke request berikutnya.

**Alur sederhana:**

```
Tim CS klik "Translate" di tool internal
        │
        ▼
   API menerima request + profile_slug "background-screening"
        │
        ▼
   Sistem cek cache: pernah translate teks ini sebelumnya?
        │
        ├── YA → return hasil cache (instan, hampir gratis)
        │
        └── TIDAK → build prompt dengan glossary departemen
                    │
                    ▼
                kirim ke AI provider (Claude)
                    │
                    ▼
                cek hasil: glossary terms dipakai?
                    │
                    ▼
                simpan ke cache + return ke user
```

### Produk B — Live Webpage Translator (JavaScript SDK)

Untuk portal internal (knowledge base, training materials, intranet):

- **Drop-in:** tambah satu baris `<script src="...">` di halaman, halaman langsung bisa di-translate.

```html
<script src="https://internal.integrity.id/sdk/translator.js"></script>
```

- **Tidak merusak layout, link, atau form.** Sistem hanya mengganti teks, tidak menyentuh struktur HTML.
- **Bagian sensitif bisa di-skip** lewat atribut HTML — mis. nama produk, kode contoh, atau bagian yang sengaja tidak boleh diterjemahkan.
- **Cache di browser:** kunjungan berikutnya ke halaman yang sama hampir instan dan tidak menambah biaya API.
- **Mengikuti perubahan halaman:** kalau ada notifikasi/popup muncul belakangan, juga ikut di-translate otomatis.

**Alur sederhana:**

```
User buka portal → SDK aktif → scan teks di halaman
        │
        ▼
   Cek cache browser: sudah pernah translate?
        │
        ├── YA → tampilkan instan dari cache
        │
        └── TIDAK → kirim batch ke API
                    │
                    ▼
                terima hasil → ganti teks di halaman
                    │
                    ▼
                simpan ke cache browser untuk kunjungan berikutnya
```

---

## 4. Use Case Konkret per Departemen

Lima use case prioritas, plus dua use case cross-cutting yang relevan untuk seluruh kantor:

| Siapa | Input | Output | Nilai vs cara lama |
|---|---|---|---|
| **Background Screening** | Draft laporan investigasi EN dengan temuan kandidat | Versi ID untuk klien lokal, atau EN untuk klien internasional, dengan istilah forensik konsisten | Cara lama: analyst terjemahkan manual atau pakai Google Translate lalu edit (1–2 jam per laporan). Cara baru: draft jadi dalam menit, analyst tinggal review. |
| **Whistleblowing System** | Laporan masuk dari pelapor dalam bahasa Indonesia/daerah/Inggris | Ringkasan terstandarisasi (EN) untuk case manager + ringkasan ID untuk follow-up internal | Cara lama: case manager handle laporan asing dengan kesulitan, atau panggil penerjemah ad-hoc (lambat, mahal). Cara baru: triage cepat tanpa kompromi confidentiality. |
| **Due Diligence** | Ringkasan investigasi korporat lintas yurisdiksi (sumber: EN, ZH, JA) | Executive summary ID untuk legal counsel klien Indonesia | Cara lama: outsource ke vendor translasi (3–5 hari, ribuan rupiah per halaman). Cara baru: draft instan, vendor cuma dipakai untuk dokumen high-stakes. |
| **KYC** | Dokumen identitas/korporat asing (akta pendirian, KTP/passport, AML report) | Terjemahan untuk verifikasi compliance lokal | Cara lama: bottleneck di tim KYC saat klien internasional submit dokumen non-EN/ID. Cara baru: turnaround onboarding klien turun signifikan. |
| **ABMS Training** | Policy document & training material klien multinasional | Versi multi-bahasa (ID, EN, MS, JA, ZH) untuk training karyawan klien di berbagai negara | Cara lama: kontrak vendor terjemahan setiap project baru. Cara baru: terjemahan otomatis dengan terminologi compliance yang dijaga konsisten. |
| **HR — SOP & komunikasi internal** | SOP, employee handbook, pengumuman | Versi multi-bahasa untuk karyawan ekspat atau cabang regional | Cara lama: SOP berbahasa Inggris tidak dibaca karyawan non-EN. Cara baru: semua dokumen otomatis tersedia dalam bahasa preferensi karyawan. |
| **Knowledge Base internal** | Artikel knowledge base internal (procedure, troubleshooting) | Auto-translate saat user buka artikel | Cara lama: maintain 2× konten manual (EN + ID), sering drift. Cara baru: satu sumber, auto-translate on-demand. |

> **Catatan:** angka turnaround (jam, hari) di atas adalah klaim kualitatif berbasis pemahaman umum workflow. **Butuh validasi** lewat pilot — lihat Section 7.

---

## 5. Apa yang Sudah Selesai (MVP Scope)

Semua kapabilitas berikut sudah berjalan dan diverifikasi di environment development per 2026-05-20:

- ✅ **Sistem terjemahan dengan profile per departemen.** Setiap departemen bisa punya glossary, tone, dan contoh gaya sendiri. Konfigurasi tersimpan di database dan bisa di-update kapan saja tanpa downtime.
- ✅ **Inheritance multi-level (sampai 4 tingkat).** Profile turunan otomatis dapat semua aturan dari parent-nya; tim cukup override yang berbeda.
- ✅ **Bisa ganti penyedia AI tanpa rewrite besar.** Saat ini pakai Claude (Anthropic). Kalau besok mau pindah ke vendor lain karena alasan harga/kebijakan/kualitas, perubahan terbatas di satu modul kecil — proteksi dari **vendor lock-in**.
- ✅ **Cache otomatis.** Permintaan terjemahan yang sama (teks identik, profile identik, bahasa identik) tidak dibilling lagi ke vendor AI. Smoke test internal: request kedua untuk teks yang sama selesai dalam ~1 milidetik vs ~1.5 detik request pertama.
- ✅ **Sistem tetap jalan kalau cache mati.** Kalau infrastruktur cache (Redis) down, sistem tidak crash — sekadar jalan tanpa cache sampai cache pulih. Tidak ada single point of failure di layer ini.
- ✅ **Webpage internal bisa di-translate hidup.** Tambah satu baris script ke halaman, halaman otomatis multi-bahasa. Sudah ada demo working untuk landing page internal.
- ✅ **Cache di browser** — kunjungan berulang ke halaman yang sama hampir instan, tidak menambah biaya API.
- ✅ **UI ops sederhana** (Streamlit) untuk: preview terjemahan, browsing profile, edit glossary inline, lihat resolved profile (hasil inheritance).
- ✅ **Tracking biaya per request** dengan presisi audit-grade. Setiap terjemahan tercatat biayanya dalam dolar.
- ✅ **Versioning profile.** Setiap perubahan profile menyimpan snapshot versi lama — bisa di-audit kapan saja siapa mengubah apa.
- ✅ **Soft delete.** Profile yang "dihapus" sebenarnya cuma di-nonaktifkan — masih bisa di-audit, masih bisa di-restore kalau perlu.
- ✅ **Evaluation harness.** Sebelum rilis perubahan glossary atau profile, bisa ukur dampaknya secara objektif terhadap dataset terjemahan referensi (kualitas + kepatuhan glossary).
- ✅ **Health endpoints + structured logging.** Tim IT bisa monitor kondisi sistem (Postgres, Redis, provider AI) lewat endpoint standar. Log dalam format JSON, mudah di-ingest ke tool monitoring.

---

## 6. Kapabilitas & Limitasi (Jujur)

Penting untuk membedakan apa yang **sudah bisa sekarang** vs apa yang **belum** — supaya tidak ada surprise saat pilot atau rollout.

| ✅ Bisa sekarang | ❌ Belum bisa / batasan |
|---|---|
| Custom glossary per departemen dengan multi-level inheritance | **Tidak ada autentikasi user.** Sistem MVP single-tenant internal — siapa pun yang bisa akses API bisa pakai. Wajib ditambah sebelum dipakai eksternal atau dibuka ke lebih banyak departemen. |
| Multi-bahasa: terbukti di EN, ID, MS, JA, ZH (dari dataset evaluasi) | **Glossary matching masih exact-match.** Kalau glossary punya "criminal record" tapi teks pakai "criminal records" (plural), match bisa miss. Planned: matching semantik berbasis AI di phase berikutnya. |
| Terjemahan halaman web hidup tanpa modifikasi HTML besar | **Belum ada streaming response.** Request menunggu sampai terjemahan selesai sebelum hasil dikirim. Untuk teks panjang, user lihat loading state. Acceptable untuk MVP, tapi UX bisa lebih baik. |
| Cache otomatis dengan auto-invalidation saat profile berubah | **SDK belum handle markup yang perlu reorder di tengah kalimat.** Misalnya kalimat dengan `<a href>` di tengah yang perlu pindah posisi di bahasa lain — SDK saat ini keep posisi original. |
| Tracking biaya per request, audit-grade precision | **Belum ada UI non-teknis untuk edit profile.** Saat ini cuma Streamlit (untuk ops) + REST API. Tim non-engineer butuh UI yang lebih friendly sebelum self-service feasible. |
| Soft-delete profile dengan history versi | **Belum production-hardened.** Belum ada rate limiting, belum ada alerting otomatis kalau biaya melonjak, belum ada audit log akses, belum ada review keamanan formal. |
| Evaluation harness untuk ukur kualitas | **Belum integrasi dengan SSO/Active Directory kantor.** Tidak bisa langsung pakai akun email kantor untuk login. |
| Graceful degradation: cache down ≠ sistem mati | **Dataset evaluasi masih kecil** (28 entries). Cukup untuk smoke test, tidak cukup untuk monitoring kualitas serius di produksi — perlu ekspansi. |

---

## 7. Metrik Sukses (yang akan diukur saat pilot)

Tidak ada angka baseline yang real saat ini — semua angka berikut akan dikumpulkan saat pilot.

| Kategori | Metrik | Target awal | Sumber data |
|---|---|---|---|
| **Kualitas** | Skor CHRF (kemiripan dengan referensi human) per profile | `[BUTUH BASELINE — kumpulkan saat pilot]` | Evaluation harness, dataset referensi per departemen |
| **Kualitas** | Glossary compliance score (% glossary terms ter-honor di output) | > 90% per profile | Eval harness (signal sudah ada di runtime, tinggal aggregate) |
| **Performa** | P95 latency terjemahan (uncached) | `[BUTUH BASELINE]` | Log API per-request |
| **Performa** | P95 latency terjemahan (cached) | < 50 ms | Log API per-request |
| **Adopsi** | Jumlah departemen aktif pakai sistem | 2 di akhir pilot (4–6 minggu) | API logs grouped by profile |
| **Adopsi** | Request per minggu | `[BUTUH BASELINE]` | API logs |
| **Biaya** | Rata-rata cost per terjemahan (uncached) | `[BUTUH BASELINE]` | `cost_usd` per request |
| **Biaya** | Cache hit ratio | > 30% setelah 2 minggu pilot | API logs (`cache_hit` flag per request) |
| **Kualitatif** | User satisfaction dari pilot departments | Survei NPS-style | Survei post-pilot |

> **Yang masih kosong (`BUTUH BASELINE`)** akan diisi setelah pilot berjalan minimal 2 minggu. Jangan commit ke angka ini sebelum data nyata terkumpul.

---

## 8. Biaya & Operasional (Tingkat Tinggi)

### Komponen biaya

| Komponen | Sifat biaya | Catatan |
|---|---|---|
| API AI provider (Claude) | Per token (variable) | Dihitung per request input + output token. Bukti smoke test: ~$0.001545 (~Rp 25) untuk satu request pendek. Request kedua untuk teks sama: hampir nol (hit cache). |
| Infrastruktur (Postgres + Redis + container) | Fixed bulanan | Standard cloud infra — bisa pakai Docker di on-prem atau cloud provider apa saja. |
| Maintenance engineering | 0.5–1 FTE engineer (estimasi) | Untuk scope MVP. Akan naik saat ada lebih banyak departemen + fitur produksi (auth, monitoring, dll). **Estimasi kasar — perlu refine berdasarkan beban aktual.** |

### Pengendalian biaya

- **Cache otomatis** sangat mengurangi biaya untuk konten berulang. Knowledge base internal, training material, FAQ — semua konten yang dibaca berkali-kali — efektif gratis setelah terjemahan pertama.
- **Attribusi per departemen** sudah built-in: setiap request mencatat `tenant_id` + `profile_slug`. Bisa langsung dipakai untuk billing internal atau budget tracking per departemen di masa depan.
- **Cost preview di eval harness**: sebelum jalankan evaluasi besar (yang bisa mahal), sistem menghitung estimasi biaya dan minta konfirmasi eksplisit. Tidak akan ada "bill shock" karena salah trigger.
- **Tracking presisi**: pakai aritmetika presisi tinggi (Decimal), bukan floating-point, supaya biaya per departemen yang nanti dipakai untuk billing internal benar-benar akurat.

### Yang belum di-cover

- **Belum ada budget cap otomatis** — kalau ada penyalahgunaan atau bug yang trigger loop, sistem tidak auto-shutoff. Perlu ditambah sebelum buka ke departemen yang tidak ada engineering oversight.
- **Belum ada dashboard biaya** — data biaya terekam tapi belum ada UI dashboard. Tim ops harus query log untuk insight.

---

## 9. Risiko & Mitigasi

| Kategori | Risiko | Likelihood | Mitigasi sekarang | Tambahan diperlukan sebelum production |
|---|---|---|---|---|
| **Kualitas terjemahan** | Terjemahan salah pada istilah krusial (legal, forensik) tanpa terdeteksi | Medium | Glossary compliance score di-attach ke setiap response — bisa di-monitor | Threshold alert otomatis; mandatory human review untuk dokumen high-stakes (laporan klien final, KYC document) |
| **Privasi data klien** | Data sensitif (PII, identity, laporan investigasi) terkirim ke vendor AI eksternal yang mungkin di-log | **High** | Tidak ada — saat ini semua text dikirim apa adanya ke Claude API | **Review legal/compliance wajib** sebelum produksi. Opsi: zero-retention agreement dengan Anthropic, on-prem deployment, atau redaction layer sebelum kirim ke API |
| **Privasi data klien** | Data residency: Claude API memproses data di datacenter US/EU — apakah compatible dengan kewajiban kepada klien Indonesia? | **High** | Tidak ada — saat ini default | Review legal/compliance, atau pilihan deployment region khusus |
| **Vendor dependency** | Claude API down, harga naik, atau Anthropic ubah ToS | Medium | Arsitektur sudah dirancang multi-provider (proteksi vendor lock-in) — bisa pindah ke OpenAI/Azure/dll tanpa rewrite besar | Test pindah provider sebagai fire drill berkala (mis. tiap kuartal) |
| **Biaya tak terkendali** | Loop bug atau penyalahgunaan trigger ribuan request | Low–Medium | Cache otomatis, tracking biaya akurat | Budget cap per tenant/profile, alert otomatis kalau >X% di atas baseline harian |
| **Security: no auth** | Siapa pun di network bisa akses API + lihat semua profile | **High** | Network-level isolation (internal only) | Autentikasi user + RBAC (siapa boleh lihat/edit profile mana) wajib sebelum buka rollout |
| **Security: SQL injection / API abuse** | Standard web-app risks | Low | FastAPI + Pydantic schema validation di boundary | Security review formal, penetration test sebelum buka eksternal |
| **Kepatuhan internal** | Tidak ada audit trail siapa mengubah glossary kapan | Medium | Versioning profile sudah ada (snapshot per perubahan) | Tambah "changed_by" user di audit log (sekarang anonymous) |
| **Operasional** | Kalau Redis down, sistem auto-degrade (lebih lambat & mahal) — tapi diam-diam | Low | Warning di log + status di `/health/deep` | Alert ops otomatis kalau cache down >5 menit |
| **Kualitas glossary** | Glossary salah/typo dipakai semua departemen child via inheritance | Medium | Eval harness deteksi drift kualitas setelah perubahan | Approval workflow untuk perubahan profile parent (ada lebih dari N children) |

---

## 10. Rencana Berikutnya (Roadmap Bisnis)

Bukan list teknis — diurutkan berdasarkan nilai bisnis dan dependensi.

**Bulan 1–2: Pilot internal (2 departemen)**
- Pilih 2 departemen dengan kebutuhan jelas (rekomendasi: Background Screening + Due Diligence — keduanya volume tinggi, terminologi spesifik).
- Setup profile awal bersama tim departemen (workshop 2× per departemen).
- Pakai di workflow nyata selama 4–6 minggu, kumpulkan metrik & feedback.
- Output: baseline angka metrik (Section 7), validasi value hypothesis.

**Bulan 2–3: Hardening untuk rollout luas**
- Tambah autentikasi (SSO/AD kantor), RBAC per profile.
- Budget cap + alerting biaya.
- Review legal/compliance untuk privasi data klien & data residency.
- Security review formal.

**Bulan 3–4: UI non-teknis untuk profile management**
- Web UI sederhana supaya tim non-engineer bisa edit glossary, tambah style examples, dan preview hasil.
- Approval workflow untuk perubahan profile yang dipakai banyak departemen.

**Bulan 4–6: Rollout bertahap + smarter glossary**
- Onboard departemen 3, 4, 5 berdasarkan urutan readiness.
- Implementasi glossary matching semantik (bukan exact-match) — handle synonym, inflection, plural.
- Dashboard biaya & kualitas per departemen.

**Beyond MVP+ (Q3+)**
- Streaming response untuk dokumen panjang.
- SDK improvements (markup reordering untuk kalimat kompleks).
- Eval expansion dengan metrik tambahan (semantic similarity, LLM-as-judge).
- Eksplorasi: on-prem deployment kalau review legal mensyaratkan.

---

## 11. FAQ

**Q: Apa bedanya dengan Google Translate / DeepL?**
A: Tiga hal pokok: (1) kita bisa atur **glossary internal per departemen** — Google/DeepL tidak; (2) **kontrol privasi data** — kita pilih vendor, retention policy, dan bisa pindah provider kalau perlu; (3) **konsistensi auditable** — setiap perubahan tersimpan versinya. Untuk terjemahan kasual, Google/DeepL tetap layak; untuk dokumen yang harus konsisten dan kelihatan profesional, sistem internal lebih cocok.

**Q: Data internal yang dikirim ke Claude API, gimana privasi & residensi data-nya?**
A: Jujur — **ini concern paling penting dan belum sepenuhnya selesai.** Saat ini text dikirim apa adanya ke Claude API (datacenter US/EU). Untuk pilot internal dengan data non-sensitif, ini acceptable. Sebelum dipakai untuk data klien (background check reports, KYC documents, whistleblower identity), wajib ada review legal/compliance dan kemungkinan: zero-retention agreement dengan Anthropic, deployment region khusus, atau redaction layer. Lihat Section 9 baris pertama tentang privasi.

**Q: Kalau Claude API down, sistem mati total atau degrade?**
A: Sistem **tidak crash** — request akan return error dengan retry guidance, tapi infrastruktur lain (database, cache, web layer) tetap jalan. Halaman web yang sudah pernah di-translate (cache hit) tetap tampil normal dari cache browser. Untuk produksi nanti, perlu fallback strategy: pindah otomatis ke vendor backup, atau queue request untuk retry saat provider pulih.

**Q: Berapa orang yang dibutuhkan untuk maintain ongoing?**
A: Estimasi kasar **0.5–1 engineer** untuk scope MVP (engineer existing yang bangun sistem). Akan naik begitu ada lebih banyak departemen aktif, lebih banyak profile, dan fitur produksi (auth, dashboard, monitoring). Estimasi konkret per fase akan di-refine berdasarkan beban aktual saat pilot.

**Q: Departemen saya mau coba — langkah pertama apa?**
A: (1) Diskusi 1 jam dengan tim teknis untuk identifikasi top 20–50 istilah khusus departemen + 5–10 contoh kalimat yang menggambarkan tone yang diinginkan; (2) Setup profile awal (engineer yang lakukan, ~1 hari); (3) Tim coba pakai di workflow nyata selama 2 minggu, kasih feedback; (4) Refine profile berdasarkan feedback.

**Q: Apakah ini menggantikan penerjemah profesional?**
A: **Tidak untuk dokumen high-stakes.** Untuk laporan final ke klien, dokumen legal binding, atau materi yang akan dipublikasikan, penerjemah profesional tetap diperlukan untuk review. Sistem ini menggantikan terjemahan **draft pertama, terjemahan internal/operasional, dan terjemahan volume tinggi tapi low-stakes** (KB internal, training material, intake whistleblower, dll). Penerjemah profesional pun bisa lebih cepat kalau draft pertama sudah jadi.

**Q: Bagaimana kalau terjemahan salah atau sensitif?**
A: Sistem attach skor "glossary compliance" ke setiap response — kalau skor di bawah threshold, UI bisa flag dan minta human review. Untuk dokumen yang sensitif, rekomendasi: mandatory human review tetap diberlakukan terlepas dari skor. Sistem ini **support keputusan manusia, bukan menggantikan**.

**Q: Kapan siap dipakai produksi?**
A: Bergantung definisi "produksi": (a) **pilot internal di 1–2 departemen dengan data non-sensitif** — siap **sekarang**, butuh ~1 minggu setup profile; (b) **rollout luas ke semua departemen** — perlu autentikasi + UI non-teknis dulu, target ~3 bulan; (c) **dipakai untuk data klien sensitif** — perlu review legal/compliance selesai dulu, timeline tergantung hasil review.

**Q: Bahasa apa saja yang sudah di-test?**
A: Dataset evaluasi internal mencakup EN, ID, MS (Malaysia), JA (Jepang), ZH (Mandarin). Claude (provider AI saat ini) mendukung jauh lebih banyak bahasa — bisa ditambah ke dataset evaluasi berdasarkan kebutuhan departemen.

**Q: Kalau besok kantor mau pindah dari Claude ke vendor AI lain, susah?**
A: Tidak. Sistem dirancang dengan **provider abstraction layer** — modul yang berbicara langsung dengan Claude API terisolasi di satu file. Pindah ke OpenAI, Azure OpenAI, atau provider lain hanya perlu menulis adapter baru untuk modul tersebut. Cache, glossary, profile, SDK — semua tetap berfungsi tanpa perubahan.

**Q: Apakah cocok untuk terjemahan real-time (mis. chat dengan klien)?**
A: Belum optimal. Saat ini request menunggu sampai terjemahan selesai sebelum hasil dikirim (tidak ada streaming). Untuk teks pendek (chat), latency masih acceptable (~1–2 detik). Untuk dokumen panjang, user lihat loading state. Streaming response ada di roadmap.

---

## Asumsi Bisnis yang Saya Pakai (Mohon Dikoreksi)

Dokumen ini disusun dengan asumsi-asumsi berikut. Kalau ada yang **tidak sesuai realita kantor**, dokumen perlu di-update.

1. **Struktur departemen Integrity Indonesia** — saya asumsikan setiap product line (Background Screening, Whistleblowing, Due Diligence, Brand Protection, Claim Protection, KYC, ABMS) adalah unit operasional terpisah dengan workflow & terminologi spesifik. Kalau struktur sebenarnya lebih matrix atau berbeda, mapping use case di Section 3 dan 4 perlu disesuaikan.
2. **Concern utama stakeholder** — saya asumsikan tiga concern dominan: **privasi data klien**, **biaya**, dan **kualitas/akurasi**. Kalau ada concern lain yang lebih dominan di leadership (mis. **time-to-market**, **kepatuhan regulasi spesifik**, **kompatibilitas dengan tool existing**), Section 9 (Risiko) perlu di-restructure.
3. **Volume terjemahan** — saya tidak punya data konkret tentang berapa dokumen/laporan per minggu yang dihasilkan tiap departemen. Estimasi biaya & ROI di Section 8 perlu di-refine dengan data aktual.
4. **Posisi vs translator profesional** — saya asumsikan kantor saat ini menggunakan kombinasi penerjemah internal + outsource untuk dokumen klien, dan AI translation ini diposisikan sebagai **augmentation, bukan replacement**. Kalau strategi sebenarnya memang mau replace penerjemah profesional, FAQ perlu lebih hati-hati.
5. **Timeline pilot** — angka 4–6 minggu di Section 10 adalah rule-of-thumb, bukan komitmen. Bergantung availability tim departemen yang jadi pilot site.
6. **Audience reading order** — saya susun dengan asumsi leadership baca Section 1 saja (executive summary), department heads baca 1–6, IT/ops baca 6–11. Kalau audience-nya berbeda (mis. ada review board investor), perlu section tambahan untuk konteks itu.
