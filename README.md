#Eksperimen Naive Bayes untuk Klasifikasi SMS Spam
Proyek ini merupakan bagian dari Ujian Tengah Semester yang bertujuan untuk menerapkan algoritma Naive Bayes dalam mengklasifikasikan pesan SMS sebagai Spam atau Ham (bukan spam). Dataset yang digunakan adalah koleksi pesan SMS dalam Bahasa Inggris yang sudah diberi label, dan berasal dari dataset publik SMS Spam Collection.

✨ #Tujuan Proyek
Melakukan eksplorasi data terhadap pesan-pesan SMS.

Melakukan pembersihan dan preprocessing teks seperti case-folding, penghapusan tanda baca, stemming, dan stopword removal.

Menggunakan TF-IDF Vectorization untuk mengubah teks menjadi representasi numerik.

Melatih model klasifikasi menggunakan dua varian Naive Bayes: MultinomialNB dan BernoulliNB.

Mengevaluasi model dengan akurasi, confusion matrix, dan cross-validation.

Menyediakan visualisasi data (WordCloud, distribusi panjang pesan, dan lainnya) untuk membantu pemahaman.

📁 #Isi Proyek
eksperimen_naive_bayes_sms_bahasa_indonesia_lengkap.ipynb: Notebook utama yang berisi seluruh eksperimen dan penjelasan dalam Bahasa Indonesia.

smspam.csv: Dataset pesan SMS yang sudah dilabeli.

🧪 #Metodologi
Eksplorasi Data
Menampilkan distribusi label, panjang pesan, dan frekuensi kata.

Preprocessing
Membersihkan data teks menggunakan regular expression, stopwords removal, dan stemming.

Vectorization
Konversi teks ke bentuk numerik menggunakan TF-IDF.

Training dan Evaluasi Model
Pelatihan model Naive Bayes dan evaluasi menggunakan akurasi, confusion matrix, dan validasi silang.

📈 #Hasil Sementara
Model MultinomialNB menghasilkan akurasi yang tinggi untuk mendeteksi spam, dengan performa yang cukup konsisten saat diuji menggunakan cross-validation.

👩‍💻 #Teknologi yang Digunakan
Python

Scikit-learn

Matplotlib & Seaborn

WordCloud

NLTK

🧑‍🏫 #Catatan
Proyek ini dikerjakan sebagai tugas UTS untuk mata kuliah Data Mining dan difokuskan pada penerapan pembelajaran mesin untuk klasifikasi teks.
