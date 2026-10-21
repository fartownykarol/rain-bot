# Bot deszczowy – Zduńska Wola

Co 5 minut (GitHub Actions) sprawdza prognozę opadów z Open-Meteo i jeśli deszcz ma zacząć padać
w ciągu najbliższych 15 minut, wysyła powiadomienie na Telegram wraz z przewidywanym końcem opadów.

## Konfiguracja

1. **Bot Telegram**: napisz do @BotFather `/newbot`, zapisz token. Wyślij dowolną wiadomość do
   swojego bota, a potem otwórz `https://api.telegram.org/bot<TOKEN>/getUpdates` i odczytaj `chat.id`.
2. **Sekrety**: Settings → Secrets and variables → Actions → New repository secret:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
3. **Start**: zakładka Actions → „Rain alert" → Run workflow (ręczny test). Dalej działa sam.

## Uwagi

- GitHub bywa opóźniony z harmonogramem (zdarza się kilka–kilkanaście minut), więc ostrzeżenie
  czasem przyjdzie później niż idealnie.
- Jeśli w repo przez 60 dni nie będzie żadnej aktywności, GitHub wyłącza zaplanowane workflow
  w publicznych repo – wystarczy je włączyć ponownie w zakładce Actions.
- Próg czułości: zmienna `RAIN_THRESHOLD_MM` (domyślnie 0.1 mm / 15 min).
- Test lokalny: `python rain_bot.py --dry-run`, test Telegrama: `python rain_bot.py --test`.
