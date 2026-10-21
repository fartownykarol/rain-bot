#!/usr/bin/env python3
"""Bot deszczowy dla Zduńskiej Woli.

Co uruchomienie (zalecane: co 5 minut z crona):
  1. pobiera prognozę opadów w odstępach 15 min z Open-Meteo (bez klucza API),
  2. sprawdza, czy deszcz zacznie padać w ciągu najbliższych 15 minut,
  3. jeśli tak - wysyła powiadomienie na Telegram z przewidywanym końcem opadów.

Zmienne środowiskowe:
  TELEGRAM_BOT_TOKEN   token od @BotFather               (wymagane)
  TELEGRAM_CHAT_ID     id czatu, do którego wysyłać      (wymagane)
  RAIN_THRESHOLD_MM    próg opadu na 15 min, domyślnie 0.1
  STATE_FILE           plik stanu (anty-duplikaty), domyślnie rain_state.json obok skryptu

Opcje:
  --dry-run   nie wysyła na Telegram, tylko wypisuje wynik
  --test      wysyła wiadomość testową na Telegram i kończy
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

CITY = "Zduńska Wola"
LAT, LON = 51.5993, 18.9391
TZ = ZoneInfo("Europe/Warsaw")

SLOT = timedelta(minutes=15)
LOOKAHEAD = timedelta(minutes=15)       # jak daleko w przód szukamy początku deszczu
THRESHOLD_MM = float(os.environ.get("RAIN_THRESHOLD_MM", "0.1"))  # mm / 15 min
STATE_FILE = Path(os.environ.get("STATE_FILE", Path(__file__).with_name("rain_state.json")))


def fetch_forecast():
    params = {
        "latitude": LAT,
        "longitude": LON,
        "minutely_15": "precipitation",
        "past_minutely_15": 4,
        "forecast_minutely_15": 48,      # 12 godzin w przód
        "timezone": "Europe/Warsaw",
    }
    url = "https://api.open-meteo.com/v1/forecast?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "rain-bot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)

    times = data["minutely_15"]["time"]
    precip = data["minutely_15"]["precipitation"]
    slots = []
    for t, p in zip(times, precip):
        # Open-Meteo: wartość = suma opadu z POPRZEDNICH 15 min względem znacznika czasu
        end = datetime.fromisoformat(t).replace(tzinfo=TZ)
        slots.append({"start": end - SLOT, "end": end, "mm": p or 0.0})
    return slots


def analyze(slots, now):
    """Zwraca dict z danymi o nadchodzącym deszczu albo None."""
    wet = [s["mm"] >= THRESHOLD_MM for s in slots]
    n = len(slots)

    # pierwszy przedział, który jeszcze się nie skończył (obejmuje "teraz")
    idx = next((i for i, s in enumerate(slots) if s["end"] > now), None)
    if idx is None:
        return None

    # szukamy pierwszego mokrego przedziału zaczynającego się w oknie [teraz, teraz+15 min]
    start_i = None
    for i in range(idx, n):
        if slots[i]["start"] > now + LOOKAHEAD:
            break
        if wet[i]:
            start_i = i
            break
    if start_i is None:
        return None

    # jeśli poprzedni przedział też był mokry, deszcz już pada - to nie jest "początek"
    if start_i > 0 and wet[start_i - 1]:
        return None

    # koniec opadów: kolejne mokre przedziały, tolerujemy jedną suchą przerwę (15 min)
    end_i = start_i
    i = start_i + 1
    while i < n:
        if wet[i]:
            end_i = i
            i += 1
        elif i + 1 < n and wet[i + 1]:
            i += 1
        else:
            break

    block = slots[start_i:end_i + 1]
    return {
        "start": max(slots[start_i]["start"], now),
        "end": slots[end_i]["end"],
        "open_ended": end_i == n - 1,   # prognoza kończy się, a deszcz nadal pada
        "total_mm": sum(s["mm"] for s in block),
        "peak_mm_h": max(s["mm"] for s in block) * 4,
    }


def intensity_label(mm_h):
    if mm_h < 0.5:
        return "kropi / słaby deszcz"
    if mm_h < 2.5:
        return "słaby deszcz"
    if mm_h < 7.5:
        return "umiarkowany deszcz"
    return "silny deszcz"


def build_message(ev, now):
    start = ev["start"].astimezone(TZ)
    end = ev["end"].astimezone(TZ)
    minutes = max(0, round((start - now).total_seconds() / 60))
    when = "lada chwila" if minutes <= 1 else f"za ok. {minutes} min (ok. {start:%H:%M})"
    if ev["open_ended"]:
        end_txt = f"nie wcześniej niż {end:%H:%M} (prognoza nie widzi jeszcze końca)"
    else:
        end_txt = f"ok. {end:%H:%M}"
    return (
        f"🌧️ {CITY}: zapowiada się deszcz!\n"
        f"Początek: {when}\n"
        f"Przewidywany koniec: {end_txt}\n"
        f"Natężenie: {intensity_label(ev['peak_mm_h'])} "
        f"(max ok. {ev['peak_mm_h']:.1f} mm/h, łącznie ok. {ev['total_mm']:.1f} mm)"
    )


def send_telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    body = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=body), timeout=20) as resp:
        resp.read()


def load_state():
    try:
        return json.loads(STATE_FILE.read_text())
    except Exception:
        return {}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state))


def main():
    dry = "--dry-run" in sys.argv

    if "--test" in sys.argv:
        send_telegram(f"✅ Bot deszczowy dla miejscowości {CITY} działa.")
        print("Wysłano wiadomość testową.")
        return

    now = datetime.now(TZ)
    ev = analyze(fetch_forecast(), now)
    if ev is None:
        print(f"[{now:%H:%M}] brak deszczu w najbliższych 15 min")
        return

    # anty-duplikaty: nie wysyłaj ponownie o tym samym deszczu
    state = load_state()
    last = state.get("last_rain_start")
    if last:
        last_dt = datetime.fromisoformat(last)
        if abs((ev["start"] - last_dt).total_seconds()) < 3 * 3600 and now - last_dt < timedelta(hours=3):
            print(f"[{now:%H:%M}] ten deszcz był już zgłoszony")
            return

    msg = build_message(ev, now)
    print(msg)
    if not dry:
        send_telegram(msg)
        state["last_rain_start"] = ev["start"].isoformat()
        save_state(state)


if __name__ == "__main__":
    main()
