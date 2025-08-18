import streamlit as st
from ingestion import ingest_data, chain, get_relevant_qa

# --- Streamlit UI ---
st.set_page_config(page_title="Healthcare QA Assistant", page_icon="🔬", layout="wide")

# ---- Custom CSS ----
st.markdown("""
    <style>
        .main-title { font-size: 40px; font-weight: 700; text-align: center; }
        .sub-header { font-size: 20px; font-weight: 600; color: #34495e; margin-top: 25px; }
        .answer-box {
            background-color: #2d3436;
            color: #ffffff;
            padding: 20px;
            border-radius: 12px;
            font-size: 17px;
            line-height: 1.6;
            margin-bottom: 20px;
        }
        .expander-header {
            font-size: 16px !important;
            font-weight: 600 !important;
            color: #2c3e50 !important;
        }
    </style>
""", unsafe_allow_html=True)

# ---- Title ----
st.markdown('<h1 class="main-title">🔬 Healthcare QA Assistant</h1>', unsafe_allow_html=True)
st.markdown("---")

# --- Sidebar: Topic Ingestion ---
st.sidebar.header("🔍 Ingest PubMed Articles")

if "articles_ingested" not in st.session_state:
    st.session_state.articles_ingested = False

topics_input = st.sidebar.text_area(
    "Enter topics (comma-separated):",
    placeholder="e.g., intermittent fasting diabetes, hypertension lifestyle"
)

if st.sidebar.button("Ingest Articles"):
    if topics_input.strip():
        topics = [t.strip() for t in topics_input.split(",") if t.strip()]
        with st.spinner("Fetching and ingesting articles..."):
            ingest_data(topics)
        st.session_state.articles_ingested = True

# --- Show persistent status ---
if st.session_state.articles_ingested:
    st.sidebar.success("✅ Articles ingested successfully.")


# --- Main Area: Query Bar ---
st.markdown("### 💡 Ask a Question")
query = st.text_input("Type your medical question here:")

if st.button("Get Answer"):
    if query.strip():
        with st.spinner("Generating answer..."):
            answer = chain(query)

            # Show Answer styled
            st.markdown("### 🧠 Answer")
            st.markdown(f'<div class="answer-box">{answer}</div>', unsafe_allow_html=True)

            # Supporting Evidence
            result = get_relevant_qa(query)  # Assuming this returns the relevant articles

            seen_titles = set()
            unique_articles = []

            for meta in result["metadatas"][0]:
                title = meta.get("title", "Untitled Article")
                if title not in seen_titles:
                    seen_titles.add(title)
                    unique_articles.append(meta)

            st.subheader("📖 Supporting Evidence (from PubMed abstracts)")
            for meta in unique_articles:
                with st.expander("📄 " + meta.get("title", "Untitled Article")):
                    st.write(f"**Journal:** {meta.get('journal', 'N/A')}")
                    st.write(f"**Authors:** {meta.get('authors', [])}")
                    st.write(f"**Publication Date:** {meta.get('publication_date', 'N/A')}")
    else:
        st.warning("Please enter a question.")
