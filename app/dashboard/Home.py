import streamlit as st
import pandas as pd
import plotly.express as px
import logging
from typing import List, Dict

from app.data_ingestion.embeddings import VectorStore
from app.watchdog.agent import call_llm
from app.prompts.templates import CHAT_SYSTEM_PROMPT

# Configure basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

st.set_page_config(
    page_title="CitizenGov | Chat-to-Chart",
    page_icon="🏛️",
    layout="wide"
)

st.title("🏛️ CitizenGov Public Procurement Navigator")
st.markdown("Ask questions about public spending and instantly visualize the data.")

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
        # If there's a chart data payload, render it
        if "chart_data" in message:
            fig = px.pie(message["chart_data"], values='budget', names='category', title='Spending by Category (Retrieved Context)')
            st.plotly_chart(fig, use_container_width=True)

if prompt := st.chat_input("E.g., Which municipalities spend the most on IT services?"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("Searching knowledge base...")
        
        # 1. Semantic Search
        relevant_contracts = vs.search_contracts(prompt, n_results=10)
        
        if not relevant_contracts:
            response_text = "I couldn't find any relevant contracts matching your query."
            message_placeholder.markdown(response_text)
            st.session_state.messages.append({"role": "assistant", "content": response_text})
        else:
            # 2. Build Context
            context_text = "Retrieved Contracts:\n"
            for c in relevant_contracts:
                context_text += f"- [{c['category']}] {c['contractor']} (€{c['budget']}): {c['description']} (Municipality: {c['municipality']})\n"
                
            user_prompt = f"Context:\n{context_text}\n\nQuestion: {prompt}"
            
            # 3. Ask LLM
            message_placeholder.markdown("Analyzing data...")
            try:
                answer = call_llm(CHAT_SYSTEM_PROMPT, user_prompt)
            except Exception as e:
                logger.error(f"Chat LLM Error: {e}")
                answer = f"Sorry, I encountered an error communicating with the AI. \n\nContext found:\n{context_text}"
                
            # 4. Render output and chart
            message_placeholder.markdown(answer)
            
            # Create a dataframe from retrieved contracts for the dynamic chart
            df = pd.DataFrame(relevant_contracts)
            if not df.empty and 'budget' in df.columns and 'category' in df.columns:
                fig = px.pie(df, values='budget', names='category', title='Spending Breakdown (Context)')
                st.plotly_chart(fig, use_container_width=True)
                
                # Save to history
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": answer,
                    "chart_data": df[['category', 'budget']].copy()
                })
            else:
                st.session_state.messages.append({"role": "assistant", "content": answer})

st.sidebar.info("""
### Welcome to CitizenGov
This dashboard is powered by:
- **ChromaDB** for vector storage
- **Sentence-Transformers** for semantic search
- **OpenRouter** (Llama/Mistral) for chatting
- **Plotly** for native interactive charts

Navigate to the **Watchdog Map** tab on the left to see anomaly detection in action!
""")
