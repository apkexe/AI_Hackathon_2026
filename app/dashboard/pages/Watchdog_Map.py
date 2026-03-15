import streamlit as st
import pandas as pd
import plotly.express as px

from app.data_ingestion.embeddings import VectorStore

st.set_page_config(page_title="Χάρτης Ελέγχου | CitizenGov", page_icon="🏛️", layout="wide")

# --- Gov.gr-inspired theme ---
st.markdown("""
<style>
    :root {
        --gov-blue: #046EC5;
        --gov-green: #00703c;
        --gov-light-gray: #f4f4f4;
        --gov-border: #cccccc;
        --gov-dark: #1d1d1b;
    }
    .stApp { background-color: #f4f4f4; }

    .gov-header {
        background-color: #046EC5;
        color: white;
        padding: 1.5rem 2rem;
        border-radius: 0 0 8px 8px;
        margin: -1rem -1rem 1.5rem -1rem;
    }
    .gov-header h1 { color: white !important; font-size: 1.8rem; margin: 0; font-weight: 600; }
    .gov-header p { color: rgba(255,255,255,0.85); font-size: 1rem; margin: 0.3rem 0 0 0; }

    /* KPI cards */
    [data-testid="stMetric"] {
        background-color: white;
        border: 1px solid #cccccc;
        border-radius: 6px;
        padding: 1rem;
    }
    [data-testid="stMetricLabel"] { color: #1d1d1b !important; font-weight: 600; }

    /* Sidebar */
    section[data-testid="stSidebar"] { background-color: #1d1d1b; }
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] li,
    section[data-testid="stSidebar"] h3,
    section[data-testid="stSidebar"] span { color: white !important; }

    a { color: #046EC5; }
    a:hover { color: #00703c; }
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="gov-header">
    <h1>Χάρτης Ελέγχου</h1>
    <p>Αυτόνομο σύστημα ελέγχου με ΤΝ &mdash; εντοπισμός πιθανής απάτης και σπατάλης σε 7 Ελληνικά Υπουργεία</p>
</div>
""", unsafe_allow_html=True)


@st.cache_data(ttl=600)
def load_all_data():
    vs = VectorStore()
    result = vs.collection.get(include=["metadatas", "documents"])
    if not result or not result.get("ids"):
        return pd.DataFrame()
    contracts = []
    for i, doc_id in enumerate(result["ids"]):
        c = result["metadatas"][i].copy()
        c["id"] = doc_id
        doc_text = result["documents"][i] if result["documents"] else ""
        c["description"] = doc_text.split("Description: ")[-1].split(" Municipality:")[0] if doc_text else ""
        contracts.append(c)
    return pd.DataFrame(contracts)


df = load_all_data()

if df.empty:
    st.warning("Δεν βρέθηκαν δεδομένα στη βάση. Εκτελέστε πρώτα το ingestion script.")
else:
    # KPI Cards
    col1, col2, col3 = st.columns(3)

    high_count = len(df[df['risk_level'] == 'High']) if 'risk_level' in df.columns else 0
    med_count = len(df[df['risk_level'] == 'Medium']) if 'risk_level' in df.columns else 0

    col1.metric("Αποφάσεις υπό Παρακολούθηση", f"{len(df):,}")
    col2.metric("Υψηλού Κινδύνου", high_count)
    col3.metric("Μεσαίου Κινδύνου", med_count)

    # --- Filters ---
    st.markdown("---")
    filter_col1, filter_col2 = st.columns(2)

    # Greek labels for risk levels
    RISK_LABEL = {"Υψηλός": "High", "Μεσαίος": "Medium", "Χαμηλός": "Low"}
    RISK_LABEL_REV = {v: k for k, v in RISK_LABEL.items()}

    with filter_col1:
        risk_filter_gr = st.multiselect(
            "Επίπεδο Κινδύνου",
            options=["Υψηλός", "Μεσαίος", "Χαμηλός"],
            default=["Υψηλός", "Μεσαίος"],
        )
        risk_filter = [RISK_LABEL[r] for r in risk_filter_gr]
    with filter_col2:
        ministry_options = sorted(df['municipality'].unique()) if 'municipality' in df.columns else []
        ministry_filter = st.multiselect(
            "Υπουργείο",
            options=ministry_options,
            default=ministry_options,
        )

    # Apply filters
    filtered_df = df.copy()
    if risk_filter:
        filtered_df = filtered_df[filtered_df['risk_level'].isin(risk_filter)]
    if ministry_filter and 'municipality' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['municipality'].isin(ministry_filter)]

    st.markdown(f"### Αποτελέσματα Ελέγχου ({len(filtered_df):,} αποφάσεις)")

    # Ensure columns exist
    expected_cols = ['id', 'contractor', 'budget', 'municipality', 'risk_level', 'risk_summary', 'date']
    for col in expected_cols:
        if col not in filtered_df.columns:
            if col == 'risk_level':
                filtered_df[col] = 'Low'
            else:
                filtered_df[col] = ''

    display_df = filtered_df[['contractor', 'budget', 'municipality', 'risk_level', 'risk_summary', 'date']].copy()
    display_df['risk_level'] = display_df['risk_level'].map(RISK_LABEL_REV).fillna(display_df['risk_level'])
    display_df = display_df.rename(columns={
        'contractor': 'Ανάδοχος',
        'budget': 'Προϋπολογισμός',
        'municipality': 'Υπουργείο',
        'risk_level': 'Κίνδυνος',
        'risk_summary': 'Αιτιολόγηση',
        'date': 'Ημερομηνία',
    })

    def highlight_risk(row):
        color = ''
        risk = row['Κίνδυνος']
        if risk == 'Υψηλός':
            color = 'background-color: rgba(200, 50, 50, 0.15)'
        elif risk == 'Μεσαίος':
            color = 'background-color: rgba(200, 150, 0, 0.15)'
        elif risk == 'Χαμηλός':
            color = 'background-color: rgba(0, 112, 60, 0.08)'
        return [color] * len(row)

    st.dataframe(
        display_df.style.apply(highlight_risk, axis=1),
        use_container_width=True,
        height=400,
    )

    # Charts
    if high_count > 0 or med_count > 0:
        st.markdown("---")
        chart_col1, chart_col2 = st.columns(2)

        gov_colors = {'Υψηλός': '#c83232', 'Μεσαίος': '#c89600', 'Χαμηλός': '#00703c'}

        # Translate risk levels for charts
        chart_df = df.copy()
        chart_df['risk_gr'] = chart_df['risk_level'].map(RISK_LABEL_REV).fillna(chart_df['risk_level'])

        with chart_col1:
            st.markdown("### Επισημάνσεις ανά Υπουργείο")
            anomaly_df = chart_df[chart_df['risk_level'].isin(['High', 'Medium'])]
            fig_bar = px.bar(
                anomaly_df,
                x='municipality',
                y='budget',
                color='risk_gr',
                hover_data=['contractor'],
                color_discrete_map=gov_colors,
                labels={'municipality': 'Υπουργείο', 'budget': 'Ποσό (€)', 'risk_gr': 'Κίνδυνος'},
            )
            fig_bar.update_layout(
                plot_bgcolor='white',
                paper_bgcolor='#f4f4f4',
                xaxis_tickangle=-25,
                font=dict(color='#1d1d1b'),
                legend_title_text='Κίνδυνος',
            )
            st.plotly_chart(fig_bar, use_container_width=True)

        with chart_col2:
            st.markdown("### Κατανομή Κινδύνου")
            risk_counts = chart_df['risk_gr'].value_counts().reset_index()
            risk_counts.columns = ['Κίνδυνος', 'Πλήθος']
            fig_pie = px.pie(
                risk_counts,
                values='Πλήθος',
                names='Κίνδυνος',
                color='Κίνδυνος',
                color_discrete_map=gov_colors,
            )
            fig_pie.update_layout(
                paper_bgcolor='#f4f4f4',
                font=dict(color='#1d1d1b'),
                legend_title_text='Κίνδυνος',
            )
            st.plotly_chart(fig_pie, use_container_width=True)
