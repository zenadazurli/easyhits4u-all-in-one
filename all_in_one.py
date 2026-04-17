#!/usr/bin/env python3
# all_in_one.py - Login + Autosurf in un unico servizio

import os
import sys
import time
import requests
import numpy as np
import cv2
import json
from datetime import datetime
from supabase import create_client
from datasets import load_dataset
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================ CONFIGURAZIONE ====================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ofijopixtpwahgbwyutc.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

# Database per le chiavi Browserless
BROWSERLESS_SUPABASE_URL = os.environ.get("BROWSERLESS_SUPABASE_URL", "https://lmtmjfrhzbjtayjwcpsq.supabase.co")
BROWSERLESS_SUPABASE_KEY = os.environ.get("BROWSERLESS_SUPABASE_KEY")

# Credenziali account EasyHits4U
EASYHITS_EMAIL = os.environ.get("EASYHITS_EMAIL", "sandrominori50+giovannibarresi@gmail.com")
EASYHITS_PASSWORD = os.environ.get("EASYHITS_PASSWORD", "DDnmVV45!!")
ACCOUNT_NAME = os.environ.get("ACCOUNT_NAME", "giovannibarresi")
REFERER_URL = "https://www.easyhits4u.com/?ref=nicolacaporale"
BROWSERLESS_URL = "https://production-sfo.browserless.io/chrome/bql"

DIM = 64
REQUEST_TIMEOUT = 15
ERRORI_DIR = "errori"
DATASET_REPO = "zenadazurli/easyhits4u-dataset"

os.makedirs(ERRORI_DIR, exist_ok=True)

# ================ GLOBALS ====================
X_fast = None
y_fast = None
classes_fast = None
current_cookie_string = None

# ================ LOG ====================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

# ================ CARICAMENTO DATASET ====================
def load_dataset_from_hf():
    global X_fast, y_fast, classes_fast
    
    log(f"📥 Caricamento dataset da Hugging Face: {DATASET_REPO}")
    
    try:
        dataset = load_dataset(DATASET_REPO, trust_remote_code=True)
        data = dataset["train"] if "train" in dataset else dataset
        
        X = []
        y = []
        class_to_idx = {}
        
        for item in data:
            features = item.get("X")
            label_idx = item.get("y")
            
            if features is None or label_idx is None:
                continue
            
            if hasattr(data.features['y'], 'names'):
                class_name = data.features['y'].names[label_idx]
            else:
                class_name = str(label_idx)
            
            if class_name not in class_to_idx:
                class_to_idx[class_name] = len(class_to_idx)
            
            X.append(np.array(features, dtype=np.float32))
            y.append(class_to_idx[class_name])
        
        if not X:
            log("❌ Nessun dato valido nel dataset")
            return False
        
        X_fast = np.vstack(X).astype(np.float32)
        y_fast = np.array(y, dtype=np.int32)
        classes_fast = {v: k for k, v in class_to_idx.items()}
        
        log(f"✅ Dataset caricato: {X_fast.shape[0]} vettori, {len(classes_fast)} classi")
        return True
        
    except Exception as e:
        log(f"❌ Errore caricamento dataset: {e}")
        return False

# ================ GESTIONE CHIAVI BROWSERLESS ====================
def get_working_keys():
    supabase = create_client(BROWSERLESS_SUPABASE_URL, BROWSERLESS_SUPABASE_KEY)
    resp = supabase.table('browserless_keys')\
        .select('api_key')\
        .eq('status', 'working')\
        .execute()
    
    keys = []
    for row in resp.data:
        clean_key = row['api_key'].strip()
        keys.append(clean_key)
    
    log(f"📋 Trovate {len(keys)} chiavi Browserless 'working'")
    return keys

def get_cf_token(api_key):
    query = """
    mutation {
      goto(url: "https://www.easyhits4u.com/logon/", waitUntil: networkIdle, timeout: 60000) {
        status
      }
      solve(type: cloudflare, timeout: 60000) {
        solved
        token
        time
      }
    }
    """
    url = f"{BROWSERLESS_URL}?token={api_key}"
    try:
        start = time.time()
        response = requests.post(url, json={"query": query}, headers={"Content-Type": "application/json"}, timeout=120)
        if response.status_code != 200:
            return None
        data = response.json()
        if "errors" in data:
            return None
        solve_info = data.get("data", {}).get("solve", {})
        if solve_info.get("solved"):
            token = solve_info.get("token")
            log(f"   ✅ Token ({time.time()-start:.1f}s)")
            return token
        return None
    except Exception as e:
        log(f"   ❌ Errore token: {e}")
        return None

# ================ GENERAZIONE COOKIE ====================
def generate_cookie():
    log("🔄 Generazione nuovo cookie...")
    
    keys = get_working_keys()
    if not keys:
        log("❌ Nessuna chiave Browserless disponibile")
        return None
    
    for api_key in keys:
        log(f"🔑 Tentativo con chiave: {api_key[:15]}...")
        
        session = requests.Session()
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.easyhits4u.com/',
            'Origin': 'https://www.easyhits4u.com',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        }
        
        try:
            session.get("https://www.easyhits4u.com/", headers=headers, verify=False, timeout=15)
            time.sleep(1)
            
            token = get_cf_token(api_key)
            if not token:
                continue
            
            login_headers = headers.copy()
            login_headers['Content-Type'] = 'application/x-www-form-urlencoded'
            login_headers['Referer'] = REFERER_URL
            data = {
                'manual': '1',
                'fb_id': '',
                'fb_token': '',
                'google_code': '',
                'username': EASYHITS_EMAIL,
                'password': EASYHITS_PASSWORD,
                'cf-turnstile-response': token,
            }
            
            login_resp = session.post("https://www.easyhits4u.com/logon/", data=data, headers=login_headers, allow_redirects=True, timeout=30)
            if login_resp.status_code != 200:
                continue
            
            time.sleep(2)
            session.get("https://www.easyhits4u.com/member/", headers=headers, verify=False, timeout=15)
            time.sleep(1)
            session.get("https://www.easyhits4u.com/surf/", headers=headers, verify=False, timeout=15)
            time.sleep(1)
            session.get(REFERER_URL, headers=headers, verify=False, timeout=15)
            
            cookies = session.cookies.get_dict()
            
            if 'user_id' in cookies and 'sesids' in cookies:
                cookie_string = '; '.join([f"{k}={v}" for k, v in cookies.items()])
                log(f"✅ Cookie generato! user_id={cookies['user_id']}, sesids={cookies['sesids']}")
                
                # Salva su Supabase
                supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
                existing = supabase.table('account_cookies').select('id').eq('account_name', ACCOUNT_NAME).execute()
                
                cookie_data = {
                    'account_name': ACCOUNT_NAME,
                    'email': EASYHITS_EMAIL,
                    'password': EASYHITS_PASSWORD,
                    'cookies_string': cookie_string,
                    'user_id': cookies['user_id'],
                    'sesid': cookies['sesids'],
                    'status': 'active',
                    'updated_at': datetime.now().isoformat()
                }
                
                if existing.data:
                    supabase.table('account_cookies').update(cookie_data).eq('account_name', ACCOUNT_NAME).execute()
                else:
                    cookie_data['created_at'] = datetime.now().isoformat()
                    supabase.table('account_cookies').insert(cookie_data).execute()
                
                log("💾 Cookie salvato su Supabase")
                return cookie_string
                
        except Exception as e:
            log(f"   ❌ Errore: {e}")
            continue
    
    log("❌ Impossibile generare cookie")
    return None

# ================ LEGGI COOKIE DA SUPABASE ====================
def get_cookie_from_supabase():
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        resp = supabase.table('account_cookies')\
            .select('cookies_string', 'user_id', 'sesid')\
            .eq('account_name', ACCOUNT_NAME)\
            .eq('status', 'active')\
            .execute()
        
        if resp.data:
            return resp.data[0]['cookies_string']
        return None
    except Exception as e:
        log(f"❌ Errore lettura cookie: {e}")
        return None

# ================ FUNZIONI DI RICONOSCIMENTO ====================
def centra_figura(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return cv2.resize(image, (DIM, DIM))
    cnt = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(cnt)
    crop = image[y:y+h, x:x+w]
    return cv2.resize(crop, (DIM, DIM))

def estrai_descrittori(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 240, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    circularity = 0.0
    aspect_ratio = 0.0
    if contours:
        cnt = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(cnt, True)
        area = cv2.contourArea(cnt)
        if peri != 0:
            circularity = 4.0 * np.pi * area / (peri * peri)
        x, y, w, h = cv2.boundingRect(cnt)
        aspect_ratio = float(w)/h if h != 0 else 0.0

    moments = cv2.moments(thresh)
    hu = cv2.HuMoments(moments).flatten().tolist()

    h, w = img.shape[:2]
    cx, cy = w//2, h//2
    raggi = [int(min(h,w)*r) for r in (0.2, 0.4, 0.6, 0.8)]
    radiale = []
    for r in raggi:
        mask = np.zeros((h,w), np.uint8)
        cv2.circle(mask, (cx,cy), r, 255, -1)
        mean = cv2.mean(img, mask=mask)[:3]
        radiale.extend([m/255.0 for m in mean])

    spaziale = []
    quadranti = [(0,0,cx,cy), (cx,0,w,cy), (0,cy,cx,h), (cx,cy,w,h)]
    for (x1,y1,x2,y2) in quadranti:
        roi = img[y1:y2, x1:x2]
        if roi.size > 0:
            mean = cv2.mean(roi)[:3]
            spaziale.extend([m/255.0 for m in mean])

    vettore = radiale + spaziale + [circularity, aspect_ratio] + hu
    return np.array(vettore, dtype=float)

def get_features(img):
    img_centrata = centra_figura(img)
    return estrai_descrittori(img_centrata)

def predict(img_crop):
    global X_fast, y_fast, classes_fast
    
    if X_fast is None or img_crop is None or img_crop.size == 0:
        return None
    
    features = get_features(img_crop)
    distances = np.linalg.norm(X_fast - features, axis=1)
    best_idx = np.argmin(distances)
    return classes_fast.get(int(y_fast[best_idx]), "errore")

def crop_safe(img, coords):
    try:
        x1, y1, x2, y2 = map(int, coords.split(","))
    except:
        return None
    h, w = img.shape[:2]
    x1 = max(0, min(w-1, x1))
    x2 = max(0, min(w, x2))
    y1 = max(0, min(h-1, y1))
    y2 = max(0, min(h, y2))
    if x2 <= x1 or y2 <= y1:
        return None
    return img[y1:y2, x1:x2]

def salva_errore(qpic, img, picmap, labels, chosen_idx, motivo, urlid=None):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = os.path.join(ERRORI_DIR, f"{timestamp}_{qpic}")
    os.makedirs(folder, exist_ok=True)
    
    full_path = os.path.join(folder, "full.jpg")
    cv2.imwrite(full_path, img)
    
    for i, p in enumerate(picmap):
        crop = crop_safe(img, p.get("coords", ""))
        if crop is not None and crop.size > 0:
            crop_path = os.path.join(folder, f"crop_{i+1}.jpg")
            cv2.imwrite(crop_path, crop)
    
    metadata = {
        "timestamp": timestamp,
        "qpic": qpic,
        "urlid": urlid,
        "motivo": motivo,
        "labels_predette": labels,
        "chosen_idx": chosen_idx,
    }
    
    with open(os.path.join(folder, "metadata.json"), "w") as f:
        json.dump(metadata, f, indent=2)
    
    log(f"📁 Errore salvato in {folder}")

# ================ MAIN ====================
def main():
    global current_cookie_string
    
    log("=" * 50)
    log("🚀 ALL-IN-ONE: Generatore + Autosurf")
    log(f"📧 Account: {EASYHITS_EMAIL}")
    log("=" * 50)
    
    # Carica dataset
    if not load_dataset_from_hf():
        log("❌ Impossibile proseguire senza dataset")
        return
    
    # Loop principale
    while True:
        # Controlla se esiste un cookie valido
        current_cookie_string = get_cookie_from_supabase()
        
        if not current_cookie_string:
            log("⚠️ Nessun cookie valido, genero nuovo cookie...")
            current_cookie_string = generate_cookie()
            
            if not current_cookie_string:
                log("❌ Impossibile generare cookie, riprovo tra 5 minuti")
                time.sleep(300)
                continue
        
        log("✅ Cookie valido, avvio autosurf...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Cookie": current_cookie_string
        }
        session = requests.Session()
        session.headers.update(headers)
        
        captcha_counter = 0
        
        while True:
            try:
                r = session.post(
                    "https://www.easyhits4u.com/surf/?ajax=1&try=1",
                    verify=False, timeout=REQUEST_TIMEOUT
                )
                
                if r.status_code != 200:
                    time.sleep(5)
                    continue
                
                data = r.json()
                urlid = data.get("surfses", {}).get("urlid")
                qpic = data.get("surfses", {}).get("qpic")
                seconds = int(data.get("surfses", {}).get("seconds", 20))
                picmap = data.get("picmap", [])
                
                # Cookie scaduto?
                if not urlid or not qpic or not picmap:
                    log("⚠️ Cookie scaduto, esco per rigenerare...")
                    break  # Esce dal loop interno per rigenerare cookie
                
                # Scarica immagine
                img_data = session.get(f"https://www.easyhits4u.com/simg/{qpic}.jpg", verify=False).content
                img = cv2.imdecode(np.frombuffer(img_data, np.uint8), cv2.IMREAD_COLOR)
                
                # Riconosci figure
                crops = [crop_safe(img, p.get("coords", "")) for p in picmap]
                labels = [predict(c) for c in crops]
                log(f"📋 Labels: {labels}")
                
                # Trova duplicati
                seen = {}
                chosen_idx = None
                for i, label in enumerate(labels):
                    if label and label != "errore":
                        if label in seen:
                            chosen_idx = seen[label]
                            log(f"🎯 Duplicato: '{label}' posizioni {seen[label]}+{i}")
                            break
                        seen[label] = i
                
                # Errore: nessun duplicato
                if chosen_idx is None:
                    log("❌ NESSUN DUPLICATO - Errore riconoscimento")
                    salva_errore(qpic, img, picmap, labels, None, "nessun_duplicato", urlid)
                    log("🛑 FERMO PER ANALISI ERRORI")
                    return  # Esce completamente
                
                # Attendi e invia
                time.sleep(seconds)
                word = picmap[chosen_idx]["value"]
                resp = session.get(
                    f"https://www.easyhits4u.com/surf/?f=surf&urlid={urlid}&surftype=2"
                    f"&ajax=1&word={word}&screen_width=1024&screen_height=768",
                    verify=False
                )
                
                # Errore: wrong choice
                if resp.json().get("warning") == "wrong_choice":
                    log("❌ WRONG CHOICE - Errore riconoscimento")
                    salva_errore(qpic, img, picmap, labels, chosen_idx, "wrong_choice", urlid)
                    log("🛑 FERMO PER ANALISI ERRORI")
                    return  # Esce completamente
                
                # Successo!
                captcha_counter += 1
                log(f"✅ OK #{captcha_counter} - indice {chosen_idx}")
                
                time.sleep(2)
                
            except Exception as e:
                log(f"❌ Errore: {e}")
                time.sleep(5)
                break  # Esce dal loop interno per rigenerare cookie
        
        # Pausa prima di rigenerare cookie
        log("⏳ Pausa 10 secondi prima di rigenerare cookie...")
        time.sleep(10)

if __name__ == "__main__":
    main()