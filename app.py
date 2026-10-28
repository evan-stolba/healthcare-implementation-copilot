"""Healthcare Implementation Copilot: Streamlit front end.

Run:  streamlit run app.py
"""

import json
from pathlib import Path

import anthropic
import pandas as pd
import streamlit as st

from copilot import question_log
from copilot.answer import MODEL, answer_question, extractive_answer, has_api_credentials
from copilot.retrieval import load_index
from scripts.seed_demo_log import CLIENTS

ROOT = Path(__file__).resolve().parent

st.set_page_config(page_title="Healthcare Implementation Copilot", layout="wide")


@st.cache_resource
def get_index():
    return load_index()


try:
    index = get_index()
except FileNotFoundError as e:
    st.error(str(e))
    st.stop()

use_llm = has_api_credentials()

# ---------- Sidebar ----------
with st.sidebar:
    st.header("Session")
    client = st.selectbox("Client account", list(CLIENTS) + ["Internal (TSM team)"])
    st.caption(f"Answer engine: **{MODEL}** with citations" if use_llm
               else "Answer engine: **extractive mode** (set ANTHROPIC_API_KEY to enable Claude)")
    include_demo = st.toggle("Include simulated demo history", value=True)
    st.divider()
    st.caption("Knowledge base: HIPAA and information blocking regulation text (eCFR), "
               "ASTP/ONC guidance, and HL7 FHIR. Not legal advice. No patient data is used.")

st.title("Healthcare Implementation Copilot")
st.caption("Answers client questions during a healthcare software rollout, with a citation for every claim, "
           "and turns those questions into account insights for the success team.")

tab_ask, tab_insights, tab_quality, tab_sources = st.tabs(
    ["Ask the copilot", "Client insights", "Answer quality", "Knowledge base"])

# ---------- Ask ----------
with tab_ask:
    examples = [
        "How long do we have to notify patients after a breach?",
        "Does our vendor need to sign a business associate agreement?",
        "What is FHIR and why does our integration team keep mentioning it?",
    ]
    cols = st.columns(len(examples))
    for col, ex in zip(cols, examples):
        if col.button(ex, use_container_width=True):
            st.session_state["question"] = ex

    question = st.text_input("Ask a question", key="question",
                             placeholder="e.g. How quickly must we respond to a patient's records request?")
    if question:
        with st.spinner("Searching guidance..."):
            try:
                ans = answer_question(index, question) if use_llm else extractive_answer(index, question)
            except anthropic.AuthenticationError:
                st.error("The API key was rejected. Falling back to extractive mode.")
                ans = extractive_answer(index, question)
            except anthropic.APIError as e:
                st.error(f"Claude API error: {e}. Falling back to extractive mode.")
                ans = extractive_answer(index, question)

        # Log each distinct question once per session, even though Streamlit reruns the script.
        logged = st.session_state.setdefault("logged", set())
        if (client, question) not in logged:
            question_log.record(ans, client)
            logged.add((client, question))

        if ans.answered:
            st.markdown(ans.text)
        else:
            st.warning(ans.text)
            st.caption("Logged as a content gap for the success team to follow up on.")
        if ans.note:
            st.caption(ans.note)

        if ans.sources:
            st.subheader("Sources")
            for i, s in enumerate(ans.sources, 1):
                with st.expander(f"[{i}] {s['title']} | {s['section']}"):
                    st.write(s["text"])
                    st.markdown(f"[Open source page]({s['url']}) | retrieval score {s['score']}")

# ---------- Insights ----------
with tab_insights:
    log = pd.DataFrame(question_log.load())
    if not log.empty and not include_demo:
        log = log[~log["demo"]]
    if log.empty:
        st.info("No questions logged yet. Ask one, or run `python -m scripts.seed_demo_log` for demo history.")
    else:
        log["timestamp"] = pd.to_datetime(log["timestamp"], utc=True, format="ISO8601")
        log["week"] = log["timestamp"].dt.tz_convert(None).dt.to_period("W").dt.start_time
        if include_demo and log["demo"].any():
            st.caption("Includes simulated history for fictional client accounts.")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Questions asked", len(log))
        k2.metric("Answered from guidance", f"{log['answered'].mean():.0%}")
        k3.metric("Open content gaps", int((~log["answered"]).sum()))
        k4.metric("Active client accounts", log["client"].nunique())

        left, right = st.columns(2)
        with left:
            st.subheader("Questions per week by client")
            weekly = log.pivot_table(index="week", columns="client", values="question",
                                     aggfunc="count", fill_value=0)
            st.bar_chart(weekly)
        with right:
            st.subheader("What clients ask about")
            topics = log["topic"].value_counts().rename("questions")
            st.bar_chart(topics, horizontal=True)

        st.subheader("Account health")
        health = log.groupby("client").agg(
            questions=("question", "count"),
            answer_rate=("answered", "mean"),
            open_gaps=("answered", lambda s: int((~s).sum())),
            top_topic=("topic", lambda s: s[s != question_log.OUT_OF_SCOPE].mode().iat[0]
                       if (s != question_log.OUT_OF_SCOPE).any() else "n/a"),
            last_activity=("timestamp", "max"),
        ).sort_values("questions", ascending=False)
        health["last_activity"] = health["last_activity"].dt.strftime("%Y-%m-%d")
        st.dataframe(health.style.format({"answer_rate": "{:.0%}"}), use_container_width=True)

        st.subheader("Content gaps: unanswered questions to follow up on")
        gaps = (log[~log["answered"]]
                .groupby("question")
                .agg(times_asked=("client", "count"),
                     clients=("client", lambda s: ", ".join(sorted(set(s)))),
                     last_asked=("timestamp", "max"))
                .sort_values("times_asked", ascending=False))
        gaps["last_asked"] = gaps["last_asked"].dt.strftime("%Y-%m-%d")
        st.dataframe(gaps, use_container_width=True)
        st.caption("Repeated gaps point to missing documentation, training needs, or a topic to raise "
                   "in the next client check-in.")

# ---------- Quality ----------
with tab_quality:
    results_dir = ROOT / "evals" / "results"
    available = [p for p in (results_dir / "latest_full.json", results_dir / "latest_retrieval.json") if p.exists()]
    if not available:
        st.info("No evaluation results yet. Run `python -m evals.run_evals` (or add `--retrieval` for a free run).")
    else:
        data = json.loads(available[0].read_text(encoding="utf-8"))
        s = data["summary"]
        st.caption(f"Latest run: {s['run_at']} | mode: {s['mode']} | {s['questions']} questions")
        labels = {
            "retrieval_hit@1": "Right source ranked #1",
            "retrieval_hit@5": "Right source in top 5",
            "answer_rate": "Answer rate (in scope)",
            "abstention_rate": "Correct abstention (out of scope)",
            "fact_coverage": "Fact coverage",
            "citation_accuracy": "Citation accuracy",
        }
        shown = [(labels[k], s[k]) for k in labels if s.get(k) is not None]
        for col, (label, value) in zip(st.columns(len(shown)), shown):
            col.metric(label, f"{value:.0%}")
        st.dataframe(pd.DataFrame(data["rows"]), use_container_width=True)

# ---------- Sources ----------
with tab_sources:
    manifest_path = ROOT / "data" / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        st.caption(f"Retrieved {manifest['retrieved_at']} | {len(index.chunks)} chunks")
        st.dataframe(pd.DataFrame(manifest["sources"])[["title", "topic", "chunks", "words", "url"]],
                     use_container_width=True,
                     column_config={"url": st.column_config.LinkColumn("url")})
