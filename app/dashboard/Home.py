import streamlit as st
import logging
from typing import List, Dict

from app.data_ingestion.embeddings import VectorStore
from app.watchdog.agent import call_llm
from app.prompts.templates import RAG_SYSTEM_PROMPT, format_contracts_as_context
from app.rag.query_analyzer import analyze_query

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="CitizenGov | Δημόσιες Προμήθειες",
    page_icon="🏛️",
    layout="wide"
)

# --- Gov.gr-inspired theme ---
st.markdown("""
<style>
    /* Gov.gr color palette */
    :root {
        --gov-blue: #046EC5;
        --gov-green: #00703c;
        --gov-light-gray: #f4f4f4;
        --gov-border: #cccccc;
        --gov-dark: #1d1d1b;
    }

    /* Main background */
    .stApp {
        background-color: #f4f4f4;
    }

    /* Header styling */
    .gov-header {
        background-color: #046EC5;
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 0 0 8px 8px;
        margin: -1rem -1rem 1.5rem -1rem;
    }
    .gov-header h1 {
        color: white !important;
        font-size: 1.8rem;
        margin: 0;
        font-weight: 600;
    }
    .gov-header p {
        color: rgba(255,255,255,0.85);
        font-size: 1rem;
        margin: 0.3rem 0 0 0;
    }

    /* Chat messages */
    .stChatMessage {
        background-color: white;
        border: 1px solid #cccccc;
        border-radius: 6px;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #1d1d1b;
    }
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] li,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] span {
        color: white !important;
    }

    /* Chat input */
    .stChatInput > div {
        border-color: #046EC5 !important;
    }
    .stChatInput > div:focus-within {
        border-color: #046EC5 !important;
        box-shadow: 0 0 0 1px #046EC5 !important;
    }

    /* Links */
    a { color: #046EC5; }
    a:hover { color: #00703c; }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# Header
st.markdown("""
<div class="gov-header">
    <h1>CitizenGov</h1>
    <p>Πλοηγός Δημοσίων Προμηθειών με Τεχνητή Νοημοσύνη &mdash; Ανοιχτά Δεδομένα Διαύγειας</p>
</div>
""", unsafe_allow_html=True)

@st.cache_resource
def get_vector_store():
    return VectorStore()

vs = get_vector_store()

# Chat UI
if "messages" not in st.session_state:
    st.session_state.messages = []

# Display chat history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("Ρωτήστε για δημόσιες δαπάνες... (π.χ. Ποιο υπουργείο έχει τις περισσότερες επισημάνσεις;)"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Αναζήτηση στη βάση γνώσεων...")

        # 1. Query Analysis
        analysis = analyze_query(prompt)
        filters = analysis.get("filters", {})
        semantic_query = analysis.get("semantic_query", prompt)

        if filters:
            logger.info(f"Extracted filters: {filters}")

        # 2. Hybrid Search
        try:
            relevant_contracts = vs.hybrid_search(
                query=semantic_query,
                where_filters=filters if filters else None,
                n_results=20,
            )
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}")
            relevant_contracts = vs.search_contracts(prompt, n_results=10)

        if not relevant_contracts:
            response_text = "Δεν βρέθηκαν σχετικά αποτελέσματα για το ερώτημά σας."
            message_placeholder.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
        else:
            # 3. Re-rank
            relevant_contracts = vs.rerank_results(relevant_contracts, prompt, top_k=10)

            # 4. Format context
            context_text = format_contracts_as_context(relevant_contracts)
            user_prompt = f"Context:\n{context_text}\n\nQuestion: {prompt}"

            # 5. Ask LLM
            message_placeholder.markdown("Ανάλυση δεδομένων...")
            try:
                answer = call_llm(RAG_SYSTEM_PROMPT, user_prompt)
            except Exception as e:
                logger.error(f"Chat LLM Error: {e}")
                answer = f"Σφάλμα επικοινωνίας με το AI.\n\nΔεδομένα που βρέθηκαν:\n{context_text}"

            # 6. Render
            message_placeholder.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})

# Sidebar
st.sidebar.markdown("""
### CitizenGov

Αυτόνομο σύστημα ελέγχου με ΤΝ που παρακολουθεί **~10.000 πραγματικές αποφάσεις** από 7 Ελληνικά Υπουργεία μέσω [Διαύγειας](https://diavgeia.gov.gr/).

---

**Υπουργεία υπό Παρακολούθηση:**
- Υπ. Εθνικής Άμυνας
- Υπ. Οικονομικών
- Υπ. Ψηφιακής Διακυβέρνησης
- Υπ. Προστασίας του Πολίτη
- Υπ. Εσωτερικών
- Υπ. Μετανάστευσης και Ασύλου
- Υπ. Παιδείας

---

**Τεχνολογία:**
- ChromaDB + Sentence-Transformers
- GPT-5.1 Έλεγχος & RAG
- Υβριδική Αναζήτηση + Επανακατάταξη
""")
