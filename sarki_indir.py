import os
import shutil
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
import yt_dlp
from supabase import create_client, Client

app = FastAPI()

# ==========================================
# SUPABASE BAĞLANTI AYARLARI
# ==========================================
SUPABASE_URL = "BURAYA_SUPABASE_PROJECT_URL_YAZ"
SUPABASE_KEY = "BURAYA_SUPABASE_ANON_KEY_YAZ"
BUCKET_NAME = "musicfiles"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Render üzerinde geçici işlemler için kullanılacak klasör
TMP_DIR = "/tmp/musicfiles"
os.makedirs(TMP_DIR, exist_ok=True)

class LinkModel(BaseModel):
    url: str

class GuncellemeModel(BaseModel):
    eski_sarki_adi: str  
    yeni_baslik: str     

class SilmeModel(BaseModel):
    sarki_adi: str  

# Yardımcı Fonksiyon: Supabase'deki tüm dosyaları listeler
def supabase_dosyalari_listele():
    try:
        res = supabase.storage.from_(BUCKET_NAME).list("", {"limit": 1000})
        return [item['name'] for item in res]
    except Exception:
        return []

@app.post("/indir")
def youtube_indir(data: LinkModel):
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{TMP_DIR}/%(title)s.%(ext)s',
        'writethumbnail': True, 
        'postprocessors': [
            {
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }
        ],
        'noplaylist': True,
    }
    try:
        # 1. Şarkıyı geçici olarak Render diskine indir
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(data.url, download=True)
            filename = ydl.prepare_filename(info)
            
        temiz_ad = os.path.splitext(os.path.basename(filename))[0]
        
        # Geçici dizindeki dosyaları tara ve Supabase'e yükle
        gecici_dosyalar = os.listdir(TMP_DIR)
        for dosya in gecici_dosyalar:
            if dosya.startswith(temiz_ad):
                dosya_yolu = os.path.join(TMP_DIR, dosya)
                
                # 2. Supabase Storage'a yükle
                with open(dosya_yolu, 'rb') as f:
                    supabase.storage.from_(BUCKET_NAME).upload(
                        path=dosya,
                        file=f,
                        file_options={"cache-control": "3600", "upsert": "true"}
                    )
                # 3. İşlem bitince Render diskinden sil (Yer kaplamasın)
                os.remove(dosya_yolu)
                
        return {"durum": "basarili", "mesaj": "Sarki ve kapak resmi basariyla buluta yuklendi!"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Indirme hatasi: {str(e)}")

@app.get("/sarkilar")
def sarkilari_listele():
    try:
        dosyalar = supabase_dosyalari_listele()
        mp3_dosyalari = [f for f in dosyalar if f.endswith('.mp3')]
        
        havuz = []
        for mp3 in mp3_dosyalari:
            sarki_adi = mp3.replace('.mp3', '')
            
            kapak_adi = None
            for ext in ['.jpg', '.jpeg', '.png', '.webp']:
                if f"{sarki_adi}{ext}" in dosyalar:
                    kapak_adi = f"{sarki_adi}{ext}"
                    break
            
            # Doğrudan Supabase üzerindeki public linkleri oluşturuyoruz
            kapak_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{kapak_adi}" if kapak_adi else None
            
            havuz.append({
                "sarki_adi": mp3,
                "baslik": sarki_adi,
                "kapak_url": kapak_url
            })
            
        return {"sarkilar": sorted(havuz, key=lambda x: x['baslik'])}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/dinle/{sarki_adi}")
def sarki_dinle(sarki_adi: str):
    # Şarkıyı Render üzerinden akıtmak yerine doğrudan Supabase public URL'ine yönlendiriyoruz (Hızlı ve Hatasız)
    sarki_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{sarki_adi}"
    return RedirectResponse(url=sarki_url)

@app.get("/kapak/{resim_adi}")
def kapak_resmi_getir(resim_adi: str):
    resim_url = f"{SUPABASE_URL}/storage/v1/object/public/{BUCKET_NAME}/{resim_adi}"
    return RedirectResponse(url=resim_url)

@app.get("/ara")
def youtube_ara(isim: str):
    if not isim:
        raise HTTPException(status_code=400, detail="Arama metni bos olamaz.")
    ydl_opts = {'format': 'bestaudio/best', 'noplaylist': True, 'extract_flat': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            arama_sonucu = ydl.extract_info(f"ytsearch5:{isim}", download=False)
        sonuclar = []
        if 'entries' in arama_sonucu:
            for entry in arama_sonucu['entries']:
                sonuclar.append({
                    "baslik": entry.get("title"),
                    "url": f"https://www.youtube.com/watch?v={entry.get('id')}"
                })
        return {"sonuclar": sonuclar}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Arama hatasi: {str(e)}")

@app.post("/guncelle/bilgi")
def sarki_bilgi_guncelle(data: GuncellemeModel):
    if not data.eski_sarki_adi.endswith('.mp3'):
        raise HTTPException(status_code=400, detail="Eski sarki adi .mp3 ile bitmelidir.")
        
    dosyalar = supabase_dosyalari_listele()
    if data.eski_sarki_adi not in dosyalar:
        raise HTTPException(status_code=404, detail="Sarki bulutta bulunamadi.")
        
    eski_temiz_ad = data.eski_sarki_adi.replace('.mp3', '')
    yeni_temiz_ad = data.yeni_baslik.strip()
    
    try:
        # 1. MP3 Adını Taşı (Move/Rename)
        supabase.storage.from_(BUCKET_NAME).move(data.eski_sarki_adi, f"{yeni_temiz_ad}.mp3")
        
        # 2. Varsa Kapağı Taşı
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            eski_kapak = f"{eski_temiz_ad}{ext}"
            if eski_kapak in dosyalar:
                supabase.storage.from_(BUCKET_NAME).move(eski_kapak, f"{yeni_temiz_ad}{ext}")
                break
                
        return {"durum": "basarili", "mesaj": "Buluttaki sarki ve kapak ismi guncellendi."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/guncelle/kapak")
def sarki_kapak_guncelle(sarki_adi: str, file: UploadFile = File(...)):
    if not sarki_adi.endswith('.mp3'):
        raise HTTPException(status_code=400, detail="Sarki adi .mp3 ile bitmelidir.")
        
    temiz_ad = sarki_adi.replace('.mp3', '')
    dosya_uzantisi = os.path.splitext(file.filename)[1].lower()
    
    try:
        dosyalar = supabase_dosyalari_listele()
        # Eski kapakları sil
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            eski_kapak = f"{temiz_ad}{ext}"
            if eski_kapak in dosyalar:
                supabase.storage.from_(BUCKET_NAME).remove([eski_kapak])
                
        # Yeni kapağı yükle
        yeni_kapak_adi = f"{temiz_ad}{dosya_uzantisi}"
        supabase.storage.from_(BUCKET_NAME).upload(
            path=yeni_kapak_adi,
            file=file.file.read(),
            file_options={"content-type": file.content_type, "upsert": "true"}
        )
        return {"durum": "basarili", "mesaj": "Kapak resmi bulutta yenilendi."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/sil")
def sarki_sil(data: SilmeModel):
    if not data.sarki_adi.endswith('.mp3'):
        raise HTTPException(status_code=400, detail="Sarki adi .mp3 ile bitmelidir.")
        
    temiz_ad = data.sarki_adi.replace('.mp3', '')
    
    try:
        dosyalar = supabase_dosyalari_listele()
        silinecekler = []
        
        if data.sarki_adi in dosyalar:
            silinecekler.append(data.sarki_adi)
            
        for ext in ['.jpg', '.jpeg', '.png', '.webp']:
            kapak_adi = f"{temiz_ad}{ext}"
            if kapak_adi in dosyalar:
                silinecekler.append(kapak_adi)
                break
                
        if silinecekler:
            supabase.storage.from_(BUCKET_NAME).remove(silinecekler)
            
        return {"durum": "basarili", "mesaj": "Sarki ve ilisikleri buluttan temizlendi."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
