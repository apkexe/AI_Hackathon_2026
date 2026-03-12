import streamlit as st
import pandas as pd
import plotly.express as px

from app.data_ingestion.embeddings import VectorStore

st.set_page_config(page_title="Watchdog Map", page_icon="🚨", layout="wide")

st.title("🚨 The Watchdog Map")
st.markdown("Autonomous AI auditing system flagging potential fraud and waste.")

@st.cache_data(ttl=60)
def load_all_data():
    vs = VectorStore()
    # Pull all documents (simulated by querying an empty string with a high n_results)
    contracts = vs.search_contracts("", n_results=100)
    return pd.DataFrame(contracts)

df = load_all_data()

if df.empty:
    st.warning("No data found in the Vector Database. Please run the ingestion script first.")
else:
    # KPI Cards
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Contracts Monitored", len(df))
    
    # Calculate risk counts
    high_count = len(df[df['risk_level'] == 'High']) if 'risk_level' in df.columns else 0
    med_count = len(df[df['risk_level'] == 'Medium']) if 'risk_level' in df.columns else 0
    
    col2.metric("High Risk Flags", high_count, delta_color="inverse")
    col3.metric("Medium Risk Flags", med_count, delta_color="inverse")
    
    st.markdown("### 📋 Contract Audit Log")
    
    # Ensure columns exist even if some metadata is missing
    expected_cols = ['id', 'contractor', 'budget', 'category', 'risk_level', 'risk_summary', 'date']
    for col in expected_cols:
        if col not in df.columns:
            if col == 'risk_level':
                df[col] = 'Low'
            else:
                df[col] = ''
                
    # Reorder columns for display
    display_df = df[['contractor', 'budget', 'category', 'risk_level', 'risk_summary', 'date']]
    
    # Conditional formatting function
    def highlight_risk(row):
        color = ''
        if row['risk_level'] == 'High':
            color = 'background-color: rgba(255, 75, 75, 0.2)'
        elif row['risk_level'] == 'Medium':
            color = 'background-color: rgba(255, 204, 0, 0.2)'
        elif row['risk_level'] == 'Low':
            color = 'background-color: rgba(75, 255, 75, 0.1)'
        return [color] * len(row)
        
    # Display the styled dataframe
    st.dataframe(
        display_df.style.apply(highlight_risk, axis=1),
        use_container_width=True,
        height=400
    )
    
    # Charting anomalies
    if high_count > 0 or med_count > 0:
        st.markdown("### 📊 Anomalies by Category")
        anomaly_df = df[df['risk_level'].isin(['High', 'Medium'])]
        fig = px.bar(
            anomaly_df, 
            x='category', 
            y='budget', 
            color='risk_level',
            hover_data=['contractor'],
            title='Flagged Budgets by Category',
            color_discrete_map={'High': 'red', 'Medium': 'orange'}
        )
        st.plotly_chart(fig, use_container_width=True)
