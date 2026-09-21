"""
app.py — Tampilan web Kak Uli pakai Streamlit.

Cara menjalankan (di terminal, BUKAN lewat "python app.py"):
    streamlit run app.py

Pastikan file ini, kak_uli_core.py, dan surabaya_cafes.json ada di folder yang sama.
Tema tampilan (warna, font) diatur di .streamlit/config.toml.
"""

import os
import streamlit as st

import kak_uli_core as core

st.set_page_config(page_title="Kak Uli - Cafe Surabaya", page_icon="🤖", layout="centered")

# ================= CSS TAMBAHAN (font + sedikit polesan visual) =================
# Mengubah tema menjadi lebih mirip dengan referensi gambar (Biru & Modern)
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    /* --- Latar Belakang Aplikasi --- */
    .stApp {
        background-color: #F0F4F8; /* Abu-abu kebiruan terang */
    }
    
    /* --- Sidebar --- */
    [data-testid="stSidebar"] {
        background-color: #FFFFFF;
    }

    /* --- Tombol Standar (Warna Biru) --- */
    .stButton > button, .stDownloadButton > button {
        background-color: #2563EB; /* Biru */
        color: #FFFFFF;
        border: none;
        border-radius: 12px;
        transition: all 0.2s;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        background-color: #1D4ED8;
        color: #FFFFFF;
        box-shadow: 0 4px 6px rgba(37, 99, 235, 0.2);
    }

    /* --- Accent Color (Radio, Toggle) --- */
    [data-testid="stRadio"] label[data-baseweb="radio"] input:checked + div > div,
    input[type="radio"], input[type="checkbox"] {
        accent-color: #2563EB;
    }

    /* --- Card Container Chat Utama --- */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: #FFFFFF;
        border-radius: 16px;
        border: none !important;
        box-shadow: 0 10px 25px rgba(0, 0, 0, 0.05);
        overflow: hidden;
    }

    /* --- Style Input Chat --- */
    div[data-testid="stChatInput"] {
        padding: 1rem;
        background-color: transparent;
    }
    div[data-testid="stChatInput"] textarea {
        border-radius: 24px;
        border: 1px solid #E2E8F0;
        padding-left: 1rem;
    }
    div[data-testid="stChatInput"] textarea:focus {
        border-color: #2563EB;
        box-shadow: 0 0 0 1px #2563EB;
    }
    
    /* --- Tombol Send di Chat Input --- */
    div[data-testid="stChatInput"] button {
        background-color: #2563EB !important;
        color: white !important;
        border-radius: 50% !important;
        width: 36px !important;
        height: 36px !important;
        margin-right: 8px;
        transition: transform 0.2s;
    }
    div[data-testid="stChatInput"] button:hover {
        background-color: #1D4ED8 !important;
        transform: scale(1.05);
    }
    div[data-testid="stChatInput"] button svg {
        fill: white !important;
        color: white !important;
    }

    /* Mengatur jarak konten agar rapi dengan header biru buatan */
    .stChatMessage {
        padding: 0 1.5rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ================= INISIALISASI SESSION STATE =================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "state" not in st.session_state:
    st.session_state.state = core.state_default()

if "cafe_data" not in st.session_state:
    st.session_state.cafe_data = core.muat_dataset()

if "client" not in st.session_state:
    st.session_state.client = None

if "last_api_key" not in st.session_state:
    st.session_state.last_api_key = ""


def proses_dan_tampilkan(prompt_user, tampilkan_bubble_user=True):
    """Kirim prompt_user ke Kak Uli, tampilkan streaming jawabannya, lalu update riwayat."""
    if tampilkan_bubble_user:
        st.session_state.messages.append({"role": "user", "content": prompt_user})
        with st.chat_message("user"):
            st.markdown(prompt_user)

    system_prompt = core.bangun_system_prompt(st.session_state.cafe_data, st.session_state.state)
    messages_lengkap = [{"role": "system", "content": system_prompt}] + st.session_state.messages

    with st.chat_message("assistant"):
        jawaban = st.write_stream(
            core.kirim_pesan_streaming(st.session_state.client, messages_lengkap, st.session_state.state)
        )

    if jawaban and not jawaban.startswith("[Terjadi error") and not jawaban.startswith("\n[Streaming terputus"):
        st.session_state.messages.append({"role": "assistant", "content": jawaban})
    elif tampilkan_bubble_user:
        # Request gagal -> buang pertanyaan tadi supaya riwayat tidak rusak
        st.session_state.messages.pop()


# ================= SIDEBAR =================

with st.sidebar:
    st.header("⚙️ Pengaturan")

    api_key_input = st.text_input(
        "GROQ_API_KEY", type="password",
        value=os.getenv("GROQ_API_KEY", ""),
        help="Bisa juga diisi lewat file .env di folder yang sama.",
    )
    if api_key_input and api_key_input != st.session_state.last_api_key:
        st.session_state.client = core.buat_client(api_key_input)
        st.session_state.last_api_key = api_key_input

    st.metric("Cafe aktif di dataset", len(st.session_state.cafe_data))
    if not st.session_state.cafe_data:
        st.warning("File 'surabaya_cafes.json' tidak ditemukan/kosong. Taruh di folder yang sama dengan app.py.")

    st.divider()
    st.subheader("Preferensi kamu")

    budget_input = st.number_input(
        "Budget (Rp, 0 = belum tau)", min_value=0, step=5000,
        value=st.session_state.state["budget"] or 0,
    )
    st.session_state.state["budget"] = budget_input if budget_input > 0 else None

    area_input = st.text_input("Area acuan", value=st.session_state.state["area"] or "")
    st.session_state.state["area"] = area_input.strip() or None

    st.session_state.state["mode_24jam"] = st.toggle(
        "🌙 Mode begadang (cuma cafe 24 jam)",
        value=st.session_state.state["mode_24jam"],
    )

    st.divider()
    st.subheader("Gaya jawaban Kak Uli")

    gaya = st.radio("Mode", ["Normal", "Serius", "Asik"], horizontal=True, label_visibility="collapsed")
    st.session_state.state["temperature"] = {"Normal": 0.7, "Serius": 0.2, "Asik": 0.9}[gaya]

    panjang_pilihan = st.select_slider(
        "Panjang jawaban", options=["pendek", "sedang", "panjang"], value="sedang",
    )
    st.session_state.state["max_tokens"] = core.PANJANG_MAP[panjang_pilihan]

    st.divider()
    st.subheader("Fitur tambahan")

    col1, col2 = st.columns(2)
    gacha_clicked = col1.button("🎲 Terserah", use_container_width=True)
    rangkum_clicked = col2.button("📝 Rangkum", use_container_width=True)

    if st.button("🗑️ Hapus riwayat sesi ini", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    with st.expander("📊 Statistik percakapan"):
        stats = core.hitung_statistik(st.session_state.messages, st.session_state.cafe_data, st.session_state.state)
        st.write(f"Total pesan kamu: **{stats['total_user']}**")
        st.write(f"Total balasan Kak Uli: **{stats['total_asisten']}**")
        if stats["kata_terpopuler"]:
            st.write("Kata kunci sering muncul:", ", ".join(f"{k} ({j}x)" for k, j in stats["kata_terpopuler"]))
        if stats["area_terpopuler"]:
            st.write("Area sering ditanyakan:", ", ".join(f"{a} ({j}x)" for a, j in stats["area_terpopuler"]))

    with st.expander("💾 Simpan / muat riwayat"):
        nama_simpan = st.text_input("Nama file (opsional)", key="nama_simpan")
        if st.button("Simpan riwayat sekarang"):
            path = core.simpan_riwayat(st.session_state.messages, nama_simpan or None)
            if path:
                st.success(f"Tersimpan ke `{path}`")
            else:
                st.info("Belum ada percakapan untuk disimpan.")

        daftar_file = core.daftar_file_riwayat()
        if daftar_file:
            pilih_file = st.selectbox("Pilih riwayat tersimpan", daftar_file)
            if st.button("Muat riwayat ini"):
                hasil = core.muat_riwayat(pilih_file)
                if hasil is not None:
                    st.session_state.messages = hasil
                    st.rerun()
        else:
            st.caption("Belum ada riwayat tersimpan.")


# ================= AREA CHAT UTAMA =================

status_online = st.session_state.client is not None
status_color = "#4ADE80" if status_online else "#9CA3AF"  # Hijau terang (Online) atau Abu-abu (Offline)
status_text = "Online" if status_online else "Menunggu API key"

with st.container(border=True, height=620):
    # Header biru kustom dengan margin negatif agar menempel di ujung container Streamlit
    header_html = f"""
    <div style="background-color: #2563EB; color: white; padding: 20px; border-radius: 14px 14px 0 0; display: flex; align-items: center; gap: 16px; margin: -1rem -1rem 1.5rem -1rem;">
        <div style="background-color: rgba(255,255,255,0.2); width: 48px; height: 48px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 24px;">
            🤖
        </div>
        <div>
            <div style="font-weight: 600; font-size: 1.2rem; margin-bottom: 2px;">Kak Uli</div>
            <div style="font-size: 0.85rem; display: flex; align-items: center; gap: 6px;">
                <span style="display: inline-block; width: 8px; height: 8px; background-color: {status_color}; border-radius: 50%;"></span>
                {status_text}
            </div>
        </div>
    </div>
    """
    st.markdown(header_html, unsafe_allow_html=True)

    if not status_online:
        st.info("Masukkan **GROQ_API_KEY** di sidebar dulu ya buat mulai ngobrol sama Kak Uli.")
        st.stop()

    # Tampilkan riwayat chat yang sudah ada
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Handle klik tombol fitur tambahan di sidebar
    if gacha_clicked:
        pilihan = core.fitur_terserah(st.session_state.cafe_data, st.session_state.state)
        if pilihan:
            prompt_tersembunyi = (
                f"Aku bingung mau kemana, tolong pilihkan satu tempat buat aku: {pilihan['name']}. "
                "Jelaskan kenapa tempat ini asik buat dicoba."
            )
            proses_dan_tampilkan(prompt_tersembunyi)
        else:
            st.warning("Dataset cafe kosong, Kak Uli nggak bisa gacha nih.")

    if rangkum_clicked:
        hasil_rangkum = core.fitur_rangkum(st.session_state.messages, st.session_state.cafe_data)
        if hasil_rangkum:
            st.success(f"{len(hasil_rangkum)} tempat berhasil dirangkum: {', '.join(hasil_rangkum)}")
            with open(core.FILE_RANGKUMAN, "rb") as f:
                st.download_button("⬇️ Download daftar_nongkrong.txt", data=f, file_name=core.FILE_RANGKUMAN)
        else:
            st.info("Belum ada cafe spesifik yang kebahas nih, ngobrol dulu yuk!")

    # Input chat utama
    prompt = st.chat_input("Type your message...")
    if prompt:
        deteksi = core.ekstrak_preferensi_dari_teks(prompt, st.session_state.cafe_data)
        if "area" in deteksi:
            st.session_state.state["area"] = deteksi["area"]
        if "budget" in deteksi:
            st.session_state.state["budget"] = deteksi["budget"]
        if "mode_24jam" in deteksi:
            st.session_state.state["mode_24jam"] = deteksi["mode_24jam"]

        proses_dan_tampilkan(prompt)