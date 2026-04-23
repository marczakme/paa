"""
PAA Extractor - Streamlit app.

Pobiera People Also Ask z DataForSEO SERP API i opcjonalnie klasteryzuje
pytania przez Claude API (Anthropic).

Uruchomienie lokalne:
    pip install -r requirements.txt
    streamlit run paa_app.py

Deploy: Streamlit Community Cloud (https://streamlit.io/cloud)
"""

import base64
import csv
import io
import json
import time
from datetime import datetime

import requests
import streamlit as st


# ---------------- Konfiguracja ----------------

LOCATIONS = {
    "Polska (pl)": {"code": 2616, "lang": "pl"},
    "USA (en)": {"code": 2840, "lang": "en"},
    "UK (en)": {"code": 2826, "lang": "en"},
    "Niemcy (de)": {"code": 2276, "lang": "de"},
    "Francja (fr)": {"code": 2250, "lang": "fr"},
    "Hiszpania (es)": {"code": 2724, "lang": "es"},
    "Włochy (it)": {"code": 2380, "lang": "it"},
    "Czechy (cs)": {"code": 2203, "lang": "cs"},
}

DATAFORSEO_ENDPOINT = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
ANTHROPIC_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_MODEL = "claude-sonnet-4-5-20250929"


# ---------------- Ochrona hasłem (opcjonalna) ----------------

def check_password():
    """
    Prosta ochrona hasłem. Jeśli w secrets.toml nie ma 'app_password',
    ochrona jest wyłączona (tryb lokalny/dev).
    """
    if "app_password" not in st.secrets:
        return True  # brak hasła w secrets -> aplikacja otwarta

    if st.session_state.get("password_ok"):
        return True

    st.title("🔒 PAA Extractor")
    pwd = st.text_input("Hasło dostępu", type="password")
    if st.button("Zaloguj"):
        if pwd == st.secrets["app_password"]:
            st.session_state["password_ok"] = True
            st.rerun()
        else:
            st.error("Nieprawidłowe hasło")
    return False


# ---------------- Logika API ----------------

def fetch_paa(keyword, location, click_depth, login, password):
    """Pobiera PAA dla pojedynczej frazy z DataForSEO."""
    auth = base64.b64encode(f"{login}:{password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }
    payload = [{
        "keyword": keyword.strip(),
        "location_code": location["code"],
        "language_code": location["lang"],
        "device": "desktop",
        "people_also_ask_click_depth": click_depth,
    }]

    response = requests.post(DATAFORSEO_ENDPOINT, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()

    if data.get("status_code") != 20000:
        raise RuntimeError(f"DataForSEO: {data.get('status_message')}")

    task = (data.get("tasks") or [{}])[0]
    if task.get("status_code") != 20000:
        raise RuntimeError(f"Task: {task.get('status_message')}")

    items = (task.get("result") or [{}])[0].get("items") or []
    paa_blocks = [i for i in items if i.get("type") == "people_also_ask"]

    questions = []
    seen = set()
    for block in paa_blocks:
        for item in block.get("items") or []:
            if item.get("type") == "people_also_ask_element" and item.get("title"):
                q = item["title"].strip()
                key = q.lower()
                if key not in seen:
                    seen.add(key)
                    questions.append({
                        "question": q,
                        "seed_question": item.get("seed_question") or "",
                    })
    return questions


def cluster_with_claude(all_questions, anthropic_key):
    """Klasteryzuje pytania przez Claude API."""
    questions_list = "\n".join(
        f'{i+1}. [{q["keyword"]}] {q["question"]}'
        for i, q in enumerate(all_questions)
    )

    prompt = f"""Jesteś ekspertem SEO specjalizującym się w semantycznym SEO i Answer Engine Optimization. Otrzymasz listę pytań z sekcji "People Also Ask" Google. Twoim zadaniem jest:

1. Pogrupować pytania w klastry tematyczne (intencje użytkownika)
2. Dla każdego klastra podać:
   - krótką nazwę (2-4 słowa)
   - dominującą intencję (informacyjna / transakcyjna / nawigacyjna / komercyjna)
   - listę pytań należących do klastra
   - krótką rekomendację, jak pokryć ten klaster w treści (1-2 zdania)

Odpowiedz TYLKO w formacie JSON, bez żadnego wstępu, bez markdown, bez bloków kodu. Struktura:
{{
  "clusters": [
    {{
      "name": "...",
      "intent": "...",
      "questions": ["...", "..."],
      "recommendation": "..."
    }}
  ]
}}

Lista pytań:
{questions_list}"""

    headers = {
        "x-api-key": anthropic_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 8000,
        "messages": [{"role": "user", "content": prompt}],
    }

    response = requests.post(ANTHROPIC_ENDPOINT, headers=headers, json=payload, timeout=120)
    response.raise_for_status()
    data = response.json()

    text = "".join(b["text"] for b in data["content"] if b["type"] == "text")
    clean = text.replace("```json", "").replace("```", "").strip()
    return json.loads(clean).get("clusters", [])


# ---------------- Helpers CSV ----------------

def results_to_csv(results):
    buf = io.StringIO()
    buf.write("\ufeff")  # BOM dla Excela
    writer = csv.writer(buf)
    writer.writerow(["keyword", "question", "seed_question"])
    for r in results:
        if r.get("error"):
            writer.writerow([r["keyword"], f"ERROR: {r['error']}", ""])
        elif not r["questions"]:
            writer.writerow([r["keyword"], "(brak PAA)", ""])
        else:
            for q in r["questions"]:
                writer.writerow([r["keyword"], q["question"], q["seed_question"]])
    return buf.getvalue()


def clusters_to_csv(clusters):
    buf = io.StringIO()
    buf.write("\ufeff")
    writer = csv.writer(buf)
    writer.writerow(["cluster", "intent", "recommendation", "question"])
    for c in clusters:
        for q in c.get("questions", []):
            writer.writerow([c.get("name", ""), c.get("intent", ""), c.get("recommendation", ""), q])
    return buf.getvalue()


# ---------------- UI ----------------

def main():
    st.set_page_config(page_title="PAA Extractor", page_icon="🔍", layout="wide")

    if not check_password():
        st.stop()

    st.title("🔍 PAA Extractor")
    st.caption("People Also Ask z DataForSEO + klasteryzacja przez Claude")

    # --- Sidebar: credentials + ustawienia ---
    with st.sidebar:
        st.header("⚙️ Ustawienia")

        st.subheader("DataForSEO")
        df_login = st.text_input("Login (email)", key="df_login")
        df_password = st.text_input("Hasło API", type="password", key="df_password")
        st.caption("Znajdziesz w panelu app.dataforseo.com → API Access")

        st.divider()

        st.subheader("Claude (opcjonalnie)")
        anthropic_key = st.text_input(
            "Anthropic API key",
            type="password",
            key="anthropic_key",
            help="Potrzebne tylko jeśli chcesz klasteryzować pytania. console.anthropic.com"
        )

        st.divider()

        st.subheader("Parametry zapytania")
        location_name = st.selectbox("Lokalizacja", list(LOCATIONS.keys()), index=0)
        location = LOCATIONS[location_name]
        click_depth = st.select_slider(
            "Click depth",
            options=[1, 2, 3, 4],
            value=2,
            help="Jak głęboko rozwijać PAA. Mnoży koszt × depth."
        )

    # --- Main: input fraz ---
    tab1, tab2 = st.tabs(["Pojedyncza fraza", "Lista fraz (bulk)"])

    keywords = []
    with tab1:
        single = st.text_input("Fraza", placeholder="np. semantyczne seo", key="single_kw")
        if single.strip():
            keywords = [single.strip()]

    with tab2:
        bulk = st.text_area(
            "Frazy (jedna na linię)",
            height=200,
            placeholder="semantyczne seo\naeo\nanswer engine optimization",
            key="bulk_kw"
        )
        uploaded = st.file_uploader("...albo wgraj plik .txt", type=["txt"], key="upload")
        if uploaded:
            content = uploaded.read().decode("utf-8")
            bulk = content
            st.text_area("Wgrany plik:", value=content, height=100, disabled=True)

        bulk_list = [k.strip() for k in bulk.split("\n") if k.strip()]
        if bulk_list and not keywords:
            keywords = bulk_list

    # --- Szacunkowy koszt ---
    if keywords:
        est_cost = len(keywords) * 0.002 * click_depth
        st.info(f"📊 Fraz: **{len(keywords)}** · Szacowany koszt DataForSEO: **~${est_cost:.4f}** (Live mode × depth {click_depth})")

    # --- Przycisk Fetch ---
    fetch = st.button("🚀 Pobierz PAA", type="primary", disabled=not keywords)

    if fetch:
        if not df_login or not df_password:
            st.error("Uzupełnij dane logowania DataForSEO w sidebarze")
            st.stop()

        progress = st.progress(0, text="Rozpoczynam...")
        results = []

        for i, kw in enumerate(keywords):
            progress.progress(
                (i) / len(keywords),
                text=f"[{i+1}/{len(keywords)}] {kw}"
            )
            try:
                questions = fetch_paa(kw, location, click_depth, df_login, df_password)
                results.append({"keyword": kw, "questions": questions})
            except Exception as e:
                results.append({"keyword": kw, "questions": [], "error": str(e)})
            time.sleep(0.3)

        progress.progress(1.0, text="Gotowe!")
        time.sleep(0.3)
        progress.empty()

        st.session_state["results"] = results
        st.session_state["clusters"] = None  # reset przy nowym fetch

    # --- Wyświetlanie wyników ---
    results = st.session_state.get("results")
    if results:
        total_q = sum(len(r["questions"]) for r in results)
        errors = sum(1 for r in results if r.get("error"))

        col1, col2, col3 = st.columns(3)
        col1.metric("Frazy", len(results))
        col2.metric("Pytań PAA", total_q)
        col3.metric("Błędy", errors)

        # Pobierz CSV
        csv_data = results_to_csv(results)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        st.download_button(
            "📥 Pobierz CSV z pytaniami",
            data=csv_data,
            file_name=f"paa_{timestamp}.csv",
            mime="text/csv"
        )

        # Szczegóły per fraza
        st.subheader("Wyniki")
        for r in results:
            with st.expander(
                f"**{r['keyword']}** — {len(r['questions'])} pytań"
                + (" ⚠️" if r.get("error") else "")
            ):
                if r.get("error"):
                    st.error(f"Błąd: {r['error']}")
                elif not r["questions"]:
                    st.info("Brak PAA dla tej frazy")
                else:
                    for q in r["questions"]:
                        if q["seed_question"]:
                            st.markdown(f"- {q['question']}  \n  <sub>← z: *{q['seed_question']}*</sub>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"- {q['question']}")

        # --- Klasteryzacja ---
        if total_q > 0:
            st.divider()
            st.subheader("🧠 Klasteryzacja tematyczna przez Claude")

            if not anthropic_key:
                st.caption("Wprowadź Anthropic API key w sidebarze, żeby włączyć klasteryzację")
            else:
                if st.button("✨ Klasteryzuj pytania"):
                    all_q = [
                        {"keyword": r["keyword"], "question": q["question"]}
                        for r in results for q in r["questions"]
                    ]
                    with st.spinner(f"Claude analizuje {len(all_q)} pytań..."):
                        try:
                            clusters = cluster_with_claude(all_q, anthropic_key)
                            st.session_state["clusters"] = clusters
                        except Exception as e:
                            st.error(f"Błąd klasteryzacji: {e}")

            clusters = st.session_state.get("clusters")
            if clusters:
                st.success(f"Utworzono {len(clusters)} klastrów")

                # Download buttons
                col1, col2 = st.columns(2)
                col1.download_button(
                    "📥 Klastry (CSV)",
                    data=clusters_to_csv(clusters),
                    file_name=f"paa_{timestamp}_clusters.csv",
                    mime="text/csv"
                )
                col2.download_button(
                    "📥 Klastry (JSON)",
                    data=json.dumps({"clusters": clusters}, ensure_ascii=False, indent=2),
                    file_name=f"paa_{timestamp}_clusters.json",
                    mime="application/json"
                )

                # Render klastrów
                for c in clusters:
                    with st.expander(
                        f"**{c.get('name', 'Bez nazwy')}** · "
                        f"{c.get('intent', '?')} · "
                        f"{len(c.get('questions', []))} pytań"
                    ):
                        st.markdown(f"💡 *{c.get('recommendation', '')}*")
                        st.markdown("**Pytania:**")
                        for q in c.get("questions", []):
                            st.markdown(f"- {q}")


if __name__ == "__main__":
    main()
