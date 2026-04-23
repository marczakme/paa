# PAA Extractor

Narzędzie do pobierania pytań z sekcji **People Also Ask** Google przez [DataForSEO SERP API](https://dataforseo.com/apis/serp-api) z opcjonalną klasteryzacją tematyczną przez [Claude API](https://docs.claude.com/).

Stworzone z myślą o semantycznym SEO i Answer Engine Optimization — grupuje pytania użytkowników w intencje i sugeruje, jak pokryć je w treści.

## Funkcje

- Pojedyncze frazy lub bulk (textarea / upload pliku .txt)
- Wybór lokalizacji i języka (PL, US, UK, DE, FR, ES, IT, CZ)
- Konfigurowalny `click_depth` (1–4) — ile poziomów PAA rozwijać
- Eksport do CSV (UTF-8 z BOM, otwiera się w Excelu z polskimi znakami)
- Klasteryzacja pytań w intencje przez Claude z rekomendacjami do treści
- Opcjonalna ochrona hasłem aplikacji

## Demo

Po deployu na Streamlit Community Cloud dostaniesz publiczny URL typu:
`https://twoj-user-paa-extractor.streamlit.app`

## Uruchomienie lokalne

```bash
git clone https://github.com/TWOJ_USER/paa-extractor.git
cd paa-extractor
pip install -r requirements.txt
streamlit run paa_app.py
```

Aplikacja otworzy się w przeglądarce pod `http://localhost:8501`.

Lokalnie nie potrzebujesz pliku secrets — ochrona hasłem jest domyślnie wyłączona.

## Deploy na Streamlit Community Cloud

1. **Fork lub push tego repo na swój GitHub** (musi być publiczne dla darmowego planu)
2. Wejdź na [share.streamlit.io](https://share.streamlit.io) i zaloguj się GitHubem
3. Kliknij **New app** → wybierz swoje repo → plik `paa_app.py` → Deploy
4. Po deploy'u: panel aplikacji → **Settings** → **Secrets** → wklej:

   ```toml
   app_password = "wymysl-dlugie-haslo"
   ```

   (opcjonalne, ale **zalecane** jeśli nie chcesz, żeby dowolna osoba z linkiem widziała interfejs)

5. Gotowe. Przy każdym `git push` aplikacja automatycznie się redeploy'uje.

## Credentials — jak to działa

**Świadomie** nie trzymamy credentials w secrets:

- **DataForSEO login/hasło** — każdy user wpisuje swoje w sidebarze. Dzięki temu używa swojego konta i płaci ze swojego budżetu.
- **Anthropic API key** — j.w., wprowadzane w sidebarze tylko do klasteryzacji.
- **`app_password`** — jedyna rzecz w secrets. Kontroluje kto wchodzi do aplikacji.

Gdyby credentials DataForSEO były hardkodowane w secrets, każda osoba z dostępem do URL paliłaby Twój budżet SERP API.

## Koszty

**DataForSEO SERP API (Live mode, Google Organic Advanced):**
- Base: $0.002 / fraza
- Z `click_depth=2`: ~$0.004 / fraza
- 100 fraz × depth 2 = **~$0.40**

**Claude API (klasteryzacja):**
- Model: claude-sonnet-4-5
- Typowa analiza 50–200 pytań: **~$0.02–0.10** za wywołanie

Minimalny budżet DataForSEO: $50 (one-time, nie wygasa).

## Struktura odpowiedzi PAA

Dla każdego pytania zwracamy:

| Pole | Opis |
|---|---|
| `keyword` | fraza wyjściowa |
| `question` | treść pytania z PAA |
| `seed_question` | pytanie "rodzicielskie", z którego to rozwinięto (puste dla pytań początkowych) |

Przy `click_depth > 1` dostajesz też pytania zagnieżdżone — `seed_question` pokazuje hierarchię.

## Klasteryzacja — format wyniku

Claude zwraca klastry w strukturze:

```json
{
  "clusters": [
    {
      "name": "krótka nazwa",
      "intent": "informacyjna | transakcyjna | nawigacyjna | komercyjna",
      "questions": ["...", "..."],
      "recommendation": "jak pokryć ten klaster w treści"
    }
  ]
}
```

Eksportowane do CSV (płaski widok) i JSON (pełna struktura).

## Lokalne pliki secrets (opcjonalne)

Jeśli chcesz włączyć ochronę hasłem lokalnie, stwórz `.streamlit/secrets.toml`:

```toml
app_password = "testowe-haslo"
```

Ten plik jest w `.gitignore` — nie trafi na GitHuba.

## Licencja

MIT

## Autor

Stworzone z pomocą Claude — dla własnych potrzeb SEO research.
