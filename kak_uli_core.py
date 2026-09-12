"""
kak_uli_core.py

Semua logika inti chatbot Kak Uli (di luar tampilan) ditaruh di sini,
supaya bisa dipakai bareng-bareng oleh notebook (console) maupun app.py (Streamlit),
tanpa nulis ulang.
"""

import os
import re
import json
import random
from collections import Counter
from datetime import datetime

from groq import Groq

# ================= KONFIGURASI =================

MODEL_NAME = "qwen/qwen3.8-27b"
DATASET_PATH = "../data/surabaya_cafes.json"
FOLDER_RIWAYAT = "riwayat_chat"
FILE_RANGKUMAN = "daftar_nongkrong.txt"

PANJANG_MAP = {"pendek": 200, "sedang": 600, "panjang": 1000}

STOPWORDS = {
    "yang", "dan", "di", "ke", "dari", "untuk", "dengan", "ini", "itu", "kak",
    "uli", "aku", "kamu", "ya", "nih", "dong", "sih", "gak", "ga", "nggak",
    "banget", "apa", "atau", "ada", "juga", "saya", "kita", "mau", "bisa",
    "kalo", "kalau", "buat", "gimana", "cari", "mana",
}

SYSTEM_PROMPT_TEMPLATE = """Kamu adalah Kak Uli, senior kampus yang ramah dan santai, ngobrol kayak sama adik tingkat.

Fokus kamu HANYA membantu mahasiswa mencari:
- Cafe yang nugas-able (wifi kenceng, ada colokan, suasana nyaman buat lama-lama)
- Tempat makan yang worth it dan ramah kantong mahasiswa

Aturan menjawab:
- Gunakan Bahasa Indonesia santai, boleh pakai sapaan kayak 'bro/sis' secukupnya, jangan kaku/formal.
- JANGAN PERNAH merekomendasikan tempat yang tidak ada di DATA CAFE TERSEDIA di bawah. Kalau datanya kosong/tidak cocok, jujur bilang belum nemu yang pas, jangan mengarang nama tempat.
- Sebutkan harga, jam buka, rating GMaps, dan link-nya kalau ada di data.
- Kalau mahasiswa belum kasih tau budget atau area, tanya dulu sebelum kasih rekomendasi.
- SELALU tutup rekomendasi dengan pengingat singkat kayak 'cek dulu ya di GMaps/medsos, siapa tau jam buka atau harganya udah berubah'.
- Kalau ditanya di luar topik cafe/tempat makan mahasiswa, arahkan balik dengan santai ke topik utama.

Konteks yang kamu ingat dari mahasiswa ini:
- Budget: {budget}
- Area acuan: {area}
- Mode begadang (cuma cafe 24 jam): {mode_24jam}

DATA CAFE TERSEDIA (hasil filter otomatis dari dataset lokal, JANGAN keluar dari daftar ini):
{data_cafe}
"""


def state_default():
    """State awal percakapan: budget, area, mode begadang, dan parameter model."""
    return {
        "budget": None,
        "area": None,
        "mode_24jam": False,
        "temperature": 0.7,
        "max_tokens": PANJANG_MAP["sedang"],
    }


# ================= CLIENT GROQ =================

def buat_client(api_key):
    """Membuat Groq client dari API key yang diberikan."""
    return Groq(api_key=api_key)


# ================= DATASET =================

def muat_dataset(path=DATASET_PATH):
    """
    Membaca surabaya_cafes.json dan hanya mengembalikan cafe yang
    statusnya masih 'Operational' di GMaps.
    Mengembalikan list kosong (bukan error) kalau file tidak ada / rusak,
    supaya chatbot tetap bisa jalan tanpa data lokal.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

    return [c for c in data if c.get("gmaps_status", "").lower() == "operational"]


# ================= FILTER & PENCARIAN =================

def _parse_harga_max(price_range):
    """Ambil angka harga TERTINGGI dari string semisal 'Rp 50-150 rb' -> 150000."""
    if not price_range:
        return None
    angka = re.findall(r"\d+", price_range.replace(".", ""))
    if not angka:
        return None
    angka = [int(a) for a in angka]
    faktor = 1_000_000 if "jt" in price_range.lower() else 1_000
    return max(angka) * faktor


def cari_cafe(data, area=None, budget=None, hanya_24jam=False, fasilitas=None, keyword=None, limit=5):
    """Filter dataset cafe berdasarkan beberapa kriteria sekaligus, urut dari rating tertinggi."""
    hasil = data

    if area:
        hasil = [c for c in hasil if area.lower() in (c.get("area") or "").lower()]

    if budget:
        hasil_budget = []
        for c in hasil:
            harga_max = _parse_harga_max(c.get("price_range", ""))
            if harga_max is None or harga_max <= budget:
                hasil_budget.append(c)
        hasil = hasil_budget

    if hanya_24jam:
        hasil = [c for c in hasil if "24 jam" in (c.get("opening_hours") or "").lower()]

    if fasilitas:
        hasil = [c for c in hasil if any(fasilitas.lower() in f.lower() for f in c.get("facilities", []))]

    if keyword:
        hasil = [
            c for c in hasil
            if keyword.lower() in (c.get("name") or "").lower()
            or keyword.lower() in (c.get("description") or "").lower()
        ]

    hasil = sorted(hasil, key=lambda c: c.get("gmaps_rating") or 0, reverse=True)
    return hasil[:limit]


def format_cafe_untuk_prompt(daftar_cafe):
    """Ubah list dict cafe jadi teks ringkas yang siap disisipkan ke prompt Groq."""
    if not daftar_cafe:
        return "Tidak ada data cafe yang cocok di dataset lokal."

    baris = []
    for c in daftar_cafe:
        fasilitas = ", ".join(c.get("facilities") or []) or "-"
        baris.append(
            f"- {c['name']} | Area: {c.get('area', '-')} | Harga: {c.get('price_range', '-')} "
            f"| Jam: {c.get('opening_hours', '-')} | Rating: {c.get('gmaps_rating', '-')} "
            f"({c.get('gmaps_review_count', 0)} ulasan) | Fasilitas: {fasilitas} | Link: {c.get('gmaps_url', '-')}"
        )
    return "\n".join(baris)


# ================= SYSTEM PROMPT =================

def bangun_system_prompt(cafe_data, state):
    """Menyusun system prompt terbaru: filter dataset sesuai state, lalu sisipkan ke template."""
    hasil = cari_cafe(
        cafe_data,
        area=state["area"],
        budget=state["budget"],
        hanya_24jam=state["mode_24jam"],
    )
    # Kalau hasil ketat kosong, coba lebih longgar (tanpa budget) biar tetap ada opsi
    if not hasil and (state["area"] or state["budget"]):
        hasil = cari_cafe(cafe_data, area=state["area"], hanya_24jam=state["mode_24jam"])

    return SYSTEM_PROMPT_TEMPLATE.format(
        budget=f"Rp {state['budget']:,}".replace(",", ".") if state["budget"] else "belum diketahui",
        area=state["area"] or "belum diketahui",
        mode_24jam="Aktif" if state["mode_24jam"] else "Tidak aktif",
        data_cafe=format_cafe_untuk_prompt(hasil),
    )


# ================= PENGIRIMAN PESAN (STREAMING) =================

def kirim_pesan_streaming(client, messages_lengkap, state):
    """
    Generator yang meng-hit Groq API dengan stream=True dan yield tiap potongan teks.
    Cocok dipakai langsung sebagai argumen st.write_stream() di Streamlit,
    atau di-loop manual (print potongan, flush=True) di versi console.
    Kalau API error, generator berhenti setelah yield 1 pesan error singkat.
    """
    try:
        stream = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_lengkap,
            temperature=state["temperature"],
            max_tokens=state["max_tokens"],
            stream=True,
        )
    except Exception as e:
        yield f"[Terjadi error saat memanggil API: {e}]"
        return

    try:
        for chunk in stream:
            potongan = chunk.choices[0].delta.content or ""
            if potongan:
                yield potongan
    except Exception as e:
        yield f"\n[Streaming terputus di tengah jalan: {e}]"


# ================= RIWAYAT PERCAKAPAN =================

def simpan_riwayat(messages_sesi, nama_file=None, folder=FOLDER_RIWAYAT):
    """Simpan riwayat percakapan (list of dict) ke file JSON. Mengembalikan path, atau None kalau gagal."""
    if not messages_sesi:
        return None

    os.makedirs(folder, exist_ok=True)
    if nama_file is None or not nama_file.strip():
        nama_file = f"riwayat_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    if not nama_file.endswith(".json"):
        nama_file += ".json"
    path = os.path.join(folder, nama_file)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(messages_sesi, f, ensure_ascii=False, indent=2)

    return path


def muat_riwayat(nama_file, folder=FOLDER_RIWAYAT):
    """Muat kembali riwayat percakapan dari file JSON. Mengembalikan list, atau None kalau tidak ditemukan."""
    if not nama_file.endswith(".json"):
        nama_file += ".json"
    path = os.path.join(folder, nama_file)
    if not os.path.exists(path):
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def daftar_file_riwayat(folder=FOLDER_RIWAYAT):
    """Mengembalikan list nama file riwayat (.json) yang tersimpan, urut abjad."""
    if not os.path.isdir(folder):
        return []
    return sorted(f for f in os.listdir(folder) if f.endswith(".json"))


# ================= STATISTIK PERCAKAPAN =================

def hitung_statistik(messages_sesi, cafe_data, state):
    """
    Menghitung ringkasan statistik percakapan.
    Mengembalikan dict (bukan print), supaya bisa dirender bebas di console maupun Streamlit.
    """
    pesan_user = [m["content"] for m in messages_sesi if m["role"] == "user"]
    pesan_asisten = [m["content"] for m in messages_sesi if m["role"] == "assistant"]

    semua_kata = []
    for teks in pesan_user:
        kata = re.findall(r"[a-zA-Z]+", teks.lower())
        semua_kata.extend(k for k in kata if k not in STOPWORDS and len(k) > 2)
    kata_terpopuler = Counter(semua_kata).most_common(5)

    daftar_area = {c.get("area") for c in cafe_data if c.get("area")}
    penyebutan_area = Counter()
    for teks in pesan_user:
        for area in daftar_area:
            if area.lower() in teks.lower():
                penyebutan_area[area] += 1

    return {
        "total_user": len(pesan_user),
        "total_asisten": len(pesan_asisten),
        "budget": state["budget"],
        "area": state["area"],
        "mode_24jam": state["mode_24jam"],
        "kata_terpopuler": kata_terpopuler,
        "area_terpopuler": penyebutan_area.most_common(3),
    }


# ================= FITUR TAMBAHAN TEMATIK =================

def atur_mode_parameter(state, perintah):
    """Command 'mode serius' / 'mode asik' untuk mengubah temperature secara instan."""
    if perintah == "mode serius":
        state["temperature"] = 0.2
    elif perintah == "mode asik":
        state["temperature"] = 0.9


def fitur_terserah(cafe_data, state):
    """Gacha: pilih 1 cafe secara acak, mengikuti budget/area/mode yang lagi aktif."""
    kandidat = cari_cafe(
        cafe_data, area=state["area"], budget=state["budget"],
        hanya_24jam=state["mode_24jam"], limit=50,
    )
    if not kandidat:
        kandidat = cafe_data
    if not kandidat:
        return None
    return random.choice(kandidat)


def fitur_rangkum(messages_sesi, cafe_data, path=FILE_RANGKUMAN):
    """
    Ekstrak nama cafe dari dataset yang kesebut sepanjang chat, simpan ke file .txt.
    Mengembalikan list nama cafe yang ditemukan (list kosong kalau tidak ada).
    """
    teks_gabungan = " ".join(m["content"] for m in messages_sesi)
    ditemukan = []
    for c in cafe_data:
        if c["name"].lower() in teks_gabungan.lower() and c["name"] not in ditemukan:
            ditemukan.append(c["name"])

    if not ditemukan:
        return []

    with open(path, "w", encoding="utf-8") as f:
        f.write("Daftar tempat nongkrong hasil rangkuman chat sama Kak Uli:\n\n")
        for i, nama in enumerate(ditemukan, 1):
            f.write(f"{i}. {nama}\n")

    return ditemukan
