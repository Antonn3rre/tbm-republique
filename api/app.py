import json
import os
import requests
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()

# Configuration
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TBM_KEY = os.environ["TBM_KEY"]

# Les deux arrêts à surveiller
STOP_REPUBLIQUE = "bordeaux:StopPoint:BP:9145:LOC"
STOP_BORDS_DE_JALLES = "bordeaux:StopPoint:BP:9149:LOC"
MON_CHAT_ID = int(os.environ["MON_CHAT_ID"])

def fetch_passages(stop_ref):
    """Retourne juste une liste d'heures de passage pour la 901"""
    url = f"https://bdx.mecatran.com/utw/ws/siri/2.0/bordeaux/stop-monitoring.json?AccountKey={TBM_KEY}&MonitoringRef={stop_ref}&PreviewInterval=PT1H"
    headers = {"Accept": "application/json"}
    heures = []
    try:
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        delivery = data["Siri"]["ServiceDelivery"]["StopMonitoringDelivery"][0]
        visits = delivery.get("MonitoredStopVisit", [])
        
        for visit in visits:
            journey = visit["MonitoredVehicleJourney"]
            dest = journey["DestinationName"][0]["value"]
            # On cible bien la ligne 901 direction Gare St-Jean
            if "GARE ST-JEAN" in dest.upper():
                time_str = journey["MonitoredCall"].get("ExpectedArrivalTime")
                if time_str:
                    time_obj = datetime.strptime(time_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    heures.append(time_obj)
    except Exception as e:
        print(f"Erreur arrêt {stop_ref}: {e}")
    return sorted(heures)

def get_passages_smart():
    maintenant_utc = datetime.now(timezone.utc)
    
    heures_rep = fetch_passages(STOP_REPUBLIQUE)
    heures_bj = fetch_passages(STOP_BORDS_DE_JALLES)
    
    # Filtrer pour ne garder que les bus à venir
    heures_rep = [h for h in heures_rep if h > maintenant_utc]
    heures_bj = [h for h in heures_bj if h > maintenant_utc]
    
    if not heures_bj:
        return "📌 *Infos Ligne 901 :*\nAucun bus en approche à Bords de Jalles. 🚌"
        
    message = "📌 *Horaires Ligne 901 (Gare St-Jean) :*\n\n"
    
    for t_bj in heures_bj[:3]:
        heure_bj_str = f"{(t_bj.hour + 2) % 24:02d}:{t_bj.minute:02d}"
        
        bus_normal_trouve = False
        heure_rep_str = ""
        
        for t_rep in heures_rep:
            # République est censé être placé 2 à 5 minutes AVANT Bords de Jalles
            ecart_minutes = (t_bj - t_rep).total_seconds() / 60
            
            # Si l'écart est cohérent, c'est le même bus
            if 1 <= ecart_minutes <= 6:
                bus_normal_trouve = True
                heure_rep_str = f"{(t_rep.hour + 2) % 24:02d}:{t_rep.minute:02d}"
                break
        
        if bus_normal_trouve:
            message += f"✅ *Trajet Normal* (Ligne 901)\n"
            message += f"📍 République : *{heure_rep_str}*\n"
            message += f"📋 Bords de Jalles : {heure_bj_str}\n\n"
        else:
            # Pas de correspondance horaire à République -> Déviation détectée
            t_estime_rep = t_bj - timedelta(minutes=4)
            heure_estime_rep = f"{(t_estime_rep.hour + 2) % 24:02d}:{t_estime_rep.minute:02d}"
            message += f"⚠️ *Déviation / Arrêt temporaire !* (Ligne 901)\n"
            message += f"❌ Le bus évite l'arrêt République normal.\n"
            message += f"📍 République (Arrêt temp.) : *{heure_estime_rep}*\n"
            message += f"📋 Bords de Jalles : {heure_bj_str}\n\n"
            
    return message

def send_to_telegram(chat_id, text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try: requests.post(url, json=payload, timeout=5)
    except: pass

def app(environ, start_response):
    if environ.get("REQUEST_METHOD") == "POST":
        try:
            content_length = int(environ.get("CONTENT_LENGTH", 0))
            body = json.loads(environ["wsgi.input"].read(content_length))
            if "message" in body:
                chat_id = body["message"]["chat"]["id"]
                text = get_passages_smart()
                send_to_telegram(chat_id, text)
        except Exception as e:
            print(f"Webhook error: {e}")
    start_response("200 OK", [("Content-Type", "text/plain")])
    return [b"OK"]

if __name__ == "__main__":
    texte = get_passages_smart()
    send_to_telegram(MON_CHAT_ID, texte)
    print("Horaires envoyés !")
