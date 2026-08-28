import sqlite3
import hashlib
import datetime
import io
import json
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import google.generativeai as genai
import qrcode
from PIL import Image

# ----------------- LUXURY FINTECH THEME CONFIG -----------------
st.set_page_config(
    page_title="VaultCFO Pro — Autonomous Wealth Engine",
    layout="wide",
    page_icon="⚡",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap');
    * { font-family: 'Plus Jakarta Sans', sans-serif; }
    .stApp { background-color: #090D16; color: #F8FAFC; }
    .glass-card {
        background: linear-gradient(135deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.8) 100%);
        backdrop-filter: blur(16px);
        -webkit-backdrop-filter: blur(16px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        border-radius: 20px;
        padding: 24px;
        margin-bottom: 20px;
    }
    .metric-hero {
        background: linear-gradient(135deg, rgba(14, 165, 233, 0.15) 0%, rgba(99, 102, 241, 0.1) 100%);
        border: 1px solid rgba(56, 189, 248, 0.3);
        border-radius: 18px;
        padding: 20px;
        text-align: left;
    }
    .metric-value {
        font-size: 32px;
        font-weight: 800;
        background: linear-gradient(90deg, #FFFFFF 0%, #E2E8F0 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin: 6px 0;
    }
    .metric-label {
        font-size: 13px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: #94A3B8;
    }
    .badge-green {
        background: rgba(16, 185, 129, 0.15);
        color: #34D399;
        padding: 4px 10px;
        border-radius: 30px;
        font-size: 12px;
        font-weight: 700;
        border: 1px solid rgba(52, 211, 153, 0.3);
    }
    .badge-cyan {
        background: rgba(56, 189, 248, 0.15);
        color: #38BDF8;
        padding: 4px 10px;
        border-radius: 30px;
        font-size: 12px;
        font-weight: 700;
        border: 1px solid rgba(56, 189, 248, 0.3);
    }
    .stTabs [data-baseweb="tab-list"] { gap: 12px; background-color: transparent; padding: 8px 0; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 12px;
        padding: 10px 22px;
        background: rgba(30, 41, 59, 0.6);
        border: 1px solid rgba(255, 255, 255, 0.05);
        color: #94A3B8;
        font-weight: 600;
        font-size: 14px;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #0284C7 0%, #2563EB 100%) !important;
        color: #FFFFFF !important;
        border: 1px solid #38BDF8 !important;
        box-shadow: 0 4px 20px rgba(2, 132, 199, 0.4);
    }
    .stButton>button {
        border-radius: 12px;
        background: linear-gradient(135deg, #0284C7 0%, #2563EB 100%);
        color: white;
        font-weight: 700;
        border: none;
        padding: 12px 24px;
        box-shadow: 0 4px 14px rgba(2, 132, 199, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# ----------------- DATABASE SCHEMA -----------------
conn = sqlite3.connect("cfo_enterprise_v5.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password_hash TEXT
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    category TEXT,
    sub_type TEXT,
    identifier TEXT,
    quantity REAL,
    unit TEXT,
    buy_price REAL,
    current_price REAL,
    monthly_income REAL,
    purchase_year INTEGER,
    currency TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS liabilities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    category TEXT,
    principal_outstanding REAL,
    interest_rate REAL,
    monthly_emi REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")
conn.commit()

# ----------------- 1. LIVE AMFI MASTER DIRECTORY & LOOKUP -----------------
@st.cache_data(ttl=86400)
def load_amfi_scheme_directory():
    """Fetches full AMFI mutual fund master list for instant search autocomplete."""
    try:
        url = "https://api.mfapi.in/mf"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            # Return dict mapping: 'Scheme Name' -> Scheme Code
            return {f"{item['schemeName']} [{item['schemeCode']}]": str(item['schemeCode']) for item in data}
    except Exception:
        pass
    # Fallback popular funds if offline
    return {
        "Parag Parikh Flexi Cap Fund - Direct Plan - Growth [122639]": "122639",
        "HDFC Top 100 Fund - Direct Plan - Growth [118989]": "118989",
        "Mirae Asset Large Cap Fund - Direct Plan - Growth [118834]": "118834",
        "Quant Small Cap Fund - Direct Plan - Growth [120828]": "120828",
        "Nippon India Small Cap Fund - Direct Plan - Growth [118778]": "118778",
        "SBI Bluechip Fund - Direct Plan - Growth [119598]": "119598"
    }

AMFI_DIRECTORY = load_amfi_scheme_directory()

@st.cache_data(ttl=600)
def fetch_mf_nav(scheme_code):
    try:
        url = f"https://api.mfapi.in/mf/{scheme_code}/latest"
        res = requests.get(url, timeout=4).json()
        if res.get("status") == "SUCCESS" and res.get("data"):
            return float(res["data"][0]["nav"]), res.get("meta", {}).get("scheme_name", scheme_code)
    except Exception:
        pass
    return None, None

# ----------------- LIVE MARKET DATA ENGINE -----------------
@st.cache_data(ttl=300)
def fetch_live_fx_rates():
    rates = {"USD": 87.50, "AED": 23.83}
    try:
        usd_data = yf.Ticker("USDINR=X").history(period="1d")
        if not usd_data.empty:
            rates["USD"] = round(float(usd_data["Close"].iloc[-1]), 2)
    except Exception:
        pass
    try:
        aed_data = yf.Ticker("AEDINR=X").history(period="1d")
        if not aed_data.empty:
            rates["AED"] = round(float(aed_data["Close"].iloc[-1]), 2)
        else:
            rates["AED"] = round(rates["USD"] / 3.6725, 2)
    except Exception:
        rates["AED"] = round(rates["USD"] / 3.6725, 2)
    return rates

live_fx = fetch_live_fx_rates()
USD_TO_INR = live_fx["USD"]
AED_TO_INR = live_fx["AED"]

# ----------------- SECRETS & AI SETUP -----------------
api_key = ""
if "GEMINI_API_KEY" in st.secrets:
    api_key = str(st.secrets["GEMINI_API_KEY"]).strip()

ai_ready = False
if api_key:
    try:
        genai.configure(api_key=api_key)
        ai_ready = True
    except Exception as e:
        st.sidebar.error(f"AI Config Error: {e}")

def hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

@st.cache_data(ttl=300)
def fetch_live_market_price(ticker):
    if not ticker:
        return 0.0
    try:
        t = yf.Ticker(ticker)
        todays_data = t.history(period="1d")
        if not todays_data.empty:
            return round(float(todays_data["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return 0.0

def generate_qr_image(url: str):
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#0F172A", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# ----------------- AUTHENTICATION -----------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.username = ""

if not st.session_state.authenticated:
    st.markdown("""
        <div style="text-align: center; margin: 40px auto; max-width: 600px;">
            <div style="background: linear-gradient(135deg, #0284C7 0%, #6366F1 100%); width: 70px; height: 70px; border-radius: 20px; display: flex; align-items: center; justify-content: center; margin: 0 auto 20px auto; font-size: 36px; box-shadow: 0 10px 30px rgba(2, 132, 199, 0.4);">
                ⚡
            </div>
            <h1 style="font-size: 38px; font-weight: 800; letter-spacing: -1px; margin-bottom: 8px;">VaultCFO <span style="background: linear-gradient(90deg, #38BDF8, #818CF8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">PRO</span></h1>
            <p style="color: #94A3B8; font-size: 16px; margin-bottom: 30px;">Institutional Autonomous Wealth Copilot & Real-Time Net Worth Engine</p>
        </div>
    """, unsafe_allow_html=True)
    
    col_auth_center = st.columns([1, 1.4, 1])[1]
    with col_auth_center:
        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        tab_log, tab_reg = st.tabs(["⚡ Sign In", "✨ Create Account"])
        with tab_log:
            u = st.text_input("Username", key="l_u")
            p = st.text_input("Password", type="password", key="l_p")
            if st.button("Access Your Vault", use_container_width=True):
                cursor.execute("SELECT id FROM users WHERE username = ? AND password_hash = ?", (u, hash_pw(p)))
                res = cursor.fetchone()
                if res:
                    st.session_state.authenticated = True
                    st.session_state.user_id = res[0]
                    st.session_state.username = u
                    st.rerun()
                else:
                    st.error("Invalid credentials.")
        with tab_reg:
            ru = st.text_input("Choose Username", key="reg_u")
            rp = st.text_input("Choose Password", type="password", key="reg_p")
            if st.button("Initialize Encrypted Vault", use_container_width=True):
                if ru and rp:
                    try:
                        cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (ru, hash_pw(rp)))
                        conn.commit()
                        st.success("Account created successfully! You may now sign in.")
                    except sqlite3.IntegrityError:
                        st.error("Username already registered.")
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()

# ----------------- LOGGED IN APPLICATION -----------------
uid = st.session_state.user_id
current_year = datetime.datetime.now().year

# Header Bar
st.markdown("""
    <div style="display: flex; align-items: center; justify-content: space-between; background: linear-gradient(135deg, rgba(30, 41, 59, 0.6) 0%, rgba(15, 23, 42, 0.7) 100%); padding: 18px 28px; border-radius: 20px; border: 1px solid rgba(255, 255, 255, 0.08); margin-bottom: 25px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
        <div style="display: flex; align-items: center; gap: 16px;">
            <div style="background: linear-gradient(135deg, #0284C7 0%, #2563EB 100%); padding: 12px 16px; border-radius: 14px; font-size: 26px; box-shadow: 0 4px 15px rgba(2, 132, 199, 0.4);">⚡</div>
            <div>
                <h2 style="margin: 0; font-size: 24px; font-weight: 800; letter-spacing: -0.5px;">VaultCFO <span style="background: linear-gradient(90deg, #38BDF8, #818CF8); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">PRO</span></h2>
                <p style="margin: 0; color: #94A3B8; font-size: 13px; font-weight: 500;">Autonomous Financial Intelligence & Multi-Asset Ledger</p>
            </div>
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
            <span class="badge-green">● AI Copilot Active</span>
            <span class="badge-cyan">● AMFI & FX Synced</span>
        </div>
    </div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown(f"""
        <div style="padding: 12px 0 20px 0;">
            <span style="font-size: 12px; color: #94A3B8; text-transform: uppercase; font-weight: 700;">Account</span>
            <h3 style="margin: 2px 0 0 0; font-size: 20px; font-weight: 800;">{st.session_state.username}</h3>
        </div>
    """, unsafe_allow_html=True)
    if st.button("Log Out of Session", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.rerun()
    st.divider()
    
    st.markdown("**Live Currency Rates**")
    c_fx1, c_fx2 = st.columns(2)
    c_fx1.metric("USD / INR", f"₹{USD_TO_INR:,.2f}")
    c_fx2.metric("AED / INR", f"₹{AED_TO_INR:,.2f}")
    st.caption("Live quotes refreshed automatically.")

# Fetch Data
assets_raw = pd.read_sql(f"SELECT * FROM assets WHERE user_id = {uid}", conn)
liabs_raw = pd.read_sql(f"SELECT * FROM liabilities WHERE user_id = {uid}", conn)

processed_assets = []
total_invested_inr = 0.0
total_current_inr = 0.0
annual_rental_cashflow = 0.0
liquid_capital_inr = 0.0

for _, row in assets_raw.iterrows():
    qty = row["quantity"]
    buy_p = row["buy_price"]
    curr_p = row["current_price"]
    currency = row["currency"]
    multiplier = AED_TO_INR if currency == "AED" else (USD_TO_INR if currency == "USD" else 1.0)
    
    invested_val = (qty * buy_p) * multiplier
    current_unit_val = curr_p
    asset_name = row["name"]

    if row["category"] == "Mutual Funds" and row["identifier"]:
        nav, s_name = fetch_mf_nav(row["identifier"])
        if nav:
            current_unit_val = nav
            if s_name:
                asset_name = s_name
    elif row["category"] in ["Indian Equities (NSE/BSE)", "US Equities"] and row["identifier"]:
        live_p = fetch_live_market_price(row["identifier"])
        if live_p > 0:
            current_unit_val = live_p

    current_val = (qty * current_unit_val) * multiplier
    pnl = current_val - invested_val
    pnl_pct = (pnl / invested_val * 100) if invested_val > 0 else 0.0

    if row["category"] in ["Savings / Liquid Cash", "Bullion (Gold / Silver)", "Indian Equities (NSE/BSE)", "Mutual Funds"]:
        liquid_capital_inr += current_val

    holding_yrs = max(1, current_year - (row["purchase_year"] or current_year))
    cagr = (((current_val / invested_val) ** (1 / holding_yrs)) - 1) * 100 if invested_val > 0 and row["category"] == "Real Estate" else 0.0

    if row["monthly_income"] and row["monthly_income"] > 0:
        annual_rental_cashflow += (row["monthly_income"] * 12) * multiplier

    total_invested_inr += invested_val
    total_current_inr += current_val

    processed_assets.append({
        "ID": row["id"],
        "Name": asset_name,
        "Category": row["category"],
        "Sub-Type": row["sub_type"],
        "Holdings": f"{qty:,.2f} {row['unit']}",
        "Invested (INR)": invested_val,
        "Current Value (INR)": current_val,
        "P&L (INR)": pnl,
        "P&L (%)": pnl_pct,
        "CAGR (%)": f"{cagr:.1f}%" if row["category"] == "Real Estate" else "—",
        "Rental Yield": f"{(row['monthly_income']*12*multiplier / current_val * 100):.2f}%" if (row["monthly_income"] and current_val > 0) else "—"
    })

assets_df = pd.DataFrame(processed_assets)
total_liabilities = liabs_raw["principal_outstanding"].sum() if not liabs_raw.empty else 0.0
net_worth = total_current_inr - total_liabilities
unrealized_pnl = total_current_inr - total_invested_inr
unrealized_pnl_pct = (unrealized_pnl / total_invested_inr * 100) if total_invested_inr > 0 else 0.0

# Hero Metrics
c1, c2, c3, c4 = st.columns(4)
with c1:
    st.markdown(f"""
        <div class="metric-hero">
            <span class="metric-label">True Net Worth</span>
            <div class="metric-value">₹{net_worth:,.0f}</div>
            <span class="badge-green">{unrealized_pnl_pct:+.2f}% Overall Return</span>
        </div>
    """, unsafe_allow_html=True)
with c2:
    st.markdown(f"""
        <div class="metric-hero">
            <span class="metric-label">Total Assets</span>
            <div class="metric-value">₹{total_current_inr:,.0f}</div>
            <span style="font-size: 13px; color: #94A3B8;">₹{total_invested_inr:,.0f} Invested</span>
        </div>
    """, unsafe_allow_html=True)
with c3:
    st.markdown(f"""
        <div class="metric-hero">
            <span class="metric-label">Total Liabilities</span>
            <div class="metric-value" style="-webkit-text-fill-color: #F87171;">₹{total_liabilities:,.0f}</div>
            <span style="font-size: 13px; color: #F87171;">{len(liabs_raw)} Active Debts</span>
        </div>
    """, unsafe_allow_html=True)
with c4:
    st.markdown(f"""
        <div class="metric-hero">
            <span class="metric-label">Liquid Capital</span>
            <div class="metric-value" style="-webkit-text-fill-color: #38BDF8;">₹{liquid_capital_inr:,.0f}</div>
            <span class="badge-cyan">Emergency Pool</span>
        </div>
    """, unsafe_allow_html=True)

st.write("")

# ----------------- APP NAVIGATION TABS -----------------
tab_ai, tab_port, tab_add, tab_cas, tab_debt, tab_sim, tab_share = st.tabs([
    "💬 AI CFO Copilot",
    "📊 Portfolio & Yields",
    "➕ Add Asset (AMFI Search)",
    "📥 CAMS/CAS Auto-Sync",
    "💳 Debt & Liabilities",
    "🎯 Dynamic FIRE Simulator",
    "📲 Mobile App & QR"
])

# TAB 1: AI COPILOT
with tab_ai:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("🤖 Autonomous AI Financial Expert")
    st.caption("Context-aware intelligence inspecting your real estate yield, bullion weight, mutual funds, and liabilities[cite: 1].")
    
    st.markdown("**Quick Audit Chips:**")
    cp1, cp2, cp3, cp4 = st.columns(4)
    q_preset = ""
    if cp1.button("🔍 Audit Mutual Funds", use_container_width=True):
        q_preset = "Audit my mutual funds and equity holdings. Do I have overlapping funds, excessive risk, or style biases?"
    if cp2.button("⏳ Calculate Cash Runway", use_container_width=True):
        q_preset = "Based on my liquid capital of INR " + str(round(liquid_capital_inr, 2)) + " and active debt, how many months of runway do I have?"
    if cp3.button("🔥 Review FIRE Readiness", use_container_width=True):
        q_preset = "Analyze my net worth of INR " + str(round(net_worth, 2)) + " against inflation. What is my optimal retirement plan?"
    if cp4.button("💳 Inspect Debt & EMIs", use_container_width=True):
        q_preset = "Inspect my debt-to-asset ratio. Should I prepay high-interest loans or deploy surplus cash into equities/gold?"

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "I am your AI CFO. I have live access to your asset ledger, real estate rental yield, bullion weights, and debts. Ask me anything or select a prompt above!"}
        ]

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    query = st.chat_input("Ask your AI CFO anything about your wealth, investments, or cash allocation...")
    active_query = q_preset if q_preset else query

    if active_query:
        st.session_state.messages.append({"role": "user", "content": active_query})
        with st.chat_message("user"):
            st.markdown(active_query)

        with st.chat_message("assistant"):
            if not ai_ready:
                err_msg = "⚠️ Gemini API key not found in Streamlit Secrets. Please configure `GEMINI_API_KEY`."
                st.warning(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
            else:
                with st.spinner("Analyzing ledger and calculating mathematical models..."):
                    context = f"""
                    You are an institutional Personal AI CFO (comparable to 1% Club Pro and Kubera).
                    Live FX: USD/INR = {USD_TO_INR}, AED/INR = {AED_TO_INR}
                    User Portfolio Snapshot:
                    - True Net Worth: INR {net_worth:,.2f}
                    - Total Assets: INR {total_current_inr:,.2f}
                    - Liquid Capital: INR {liquid_capital_inr:,.2f}
                    - Total Invested: INR {total_invested_inr:,.2f}
                    - Unrealized Gain/Loss: INR {unrealized_pnl:,.2f} ({unrealized_pnl_pct:.2f}%)
                    - Total Debt: INR {total_liabilities:,.2f}
                    - Annual Rental Cash Flow: INR {annual_rental_cashflow:,.2f}
                    - Holdings Breakdown: {assets_df.to_dict(orient='records') if not assets_df.empty else 'No assets recorded.'}
                    - Debt Breakdown: {liabs_raw.to_dict(orient='records') if not liabs_raw.empty else 'No debt active.'}
                    """
                    
                    full_prompt = f"{context}\n\nUser Question: {active_query}"
                    candidate_models = ["gemini-1.5-flash-latest", "gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro"]
                    response_text = ""
                    success = False
                    
                    for m_name in candidate_models:
                        try:
                            model = genai.GenerativeModel(m_name)
                            res = model.generate_content(full_prompt)
                            if res and res.text:
                                response_text = res.text
                                success = True
                                break
                        except Exception:
                            continue

                    if not success:
                        try:
                            for m in genai.list_models():
                                if "generateContent" in m.supported_generation_methods:
                                    try:
                                        dynamic_model = genai.GenerativeModel(m.name)
                                        res = dynamic_model.generate_content(full_prompt)
                                        if res and res.text:
                                            response_text = res.text
                                            success = True
                                            break
                                    except Exception:
                                        continue
                        except Exception as list_err:
                            response_text = f"API Error: {str(list_err)}"

                    if success:
                        st.markdown(response_text)
                        st.session_state.messages.append({"role": "assistant", "content": response_text})
                    else:
                        err_out = "❌ Could not initialize AI model. Please verify API access."
                        st.error(err_out)
                        st.session_state.messages.append({"role": "assistant", "content": err_out})
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 2: PORTFOLIO & YIELDS
with tab_port:
    if not assets_df.empty:
        col_g1, col_g2 = st.columns([1.2, 1])
        with col_g1:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            fig_alloc = px.pie(
                assets_df,
                values="Current Value (INR)",
                names="Category",
                hole=0.6,
                color_discrete_sequence=["#0284C7", "#38BDF8", "#10B981", "#F59E0B", "#8B5CF6", "#EC4899"],
                title="Asset Allocation Distribution"
            )
            fig_alloc.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#F8FAFC", family="Plus Jakarta Sans"),
                legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5)
            )
            st.plotly_chart(fig_alloc, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        with col_g2:
            st.markdown('<div class="glass-card">', unsafe_allow_html=True)
            debt_ratio = (total_liabilities / max(1.0, total_current_inr)) * 100
            health_score = max(10, min(100, int(100 - debt_ratio + (unrealized_pnl_pct * 0.5))))
            
            fig_gauge = go.Figure(go.Indicator(
                mode="gauge+number",
                value=health_score,
                title={'text': "Portfolio Health Score", 'font': {'size': 18, 'color': "#F8FAFC"}},
                number={'suffix': "/100", 'font': {'size': 32, 'color': "#38BDF8"}},
                gauge={
                    'axis': {'range': [0, 100], 'tickcolor': "#94A3B8"},
                    'bar': {'color': "#0284C7"},
                    'steps': [
                        {'range': [0, 40], 'color': "rgba(239, 68, 68, 0.3)"},
                        {'range': [40, 75], 'color': "rgba(245, 158, 11, 0.3)"},
                        {'range': [75, 100], 'color': "rgba(16, 185, 129, 0.3)"}
                    ]
                }
            ))
            fig_gauge.update_layout(
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#F8FAFC", family="Plus Jakarta Sans"),
                height=300
            )
            st.plotly_chart(fig_gauge, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown('<div class="glass-card">', unsafe_allow_html=True)
        st.subheader("📋 Comprehensive Asset Ledger")
        st.dataframe(assets_df, use_container_width=True, hide_index=True)

        col_del1, _ = st.columns([1, 2])
        del_id = col_del1.number_input("Delete Holding by ID", min_value=1, step=1)
        if col_del1.button("Remove Entry"):
            cursor.execute("DELETE FROM assets WHERE id = ? AND user_id = ?", (del_id, uid))
            conn.commit()
            st.success("Asset removed.")
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("No assets tracked yet. Add mutual funds, bullion, or properties to initialize your ledger.")

# TAB 3: DYNAMIC ASSET ENGINE WITH AMFI AUTOCOMPLETE
with tab_add:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("➕ Dynamic Asset Setup (With Automated Search)")
    
    cat = st.selectbox("Asset Class", [
        "Mutual Funds",
        "Bullion (Gold / Silver)",
        "Indian Equities (NSE/BSE)",
        "Real Estate",
        "Fixed Deposit / EPF / Sukanya",
        "Savings / Liquid Cash"
    ])
    cur = st.radio("Denomination Currency", ["INR", "AED", "USD"], horizontal=True)

    with st.form("dynamic_asset_form"):
        if cat == "Mutual Funds":
            st.markdown("#### 🔍 Mutual Fund Direct Search (AMFI Database)")
            selected_fund_label = st.selectbox("Search & Select Mutual Fund", list(AMFI_DIRECTORY.keys()))
            matched_amfi_code = AMFI_DIRECTORY[selected_fund_label]
            st.caption(f"Mapped AMFI Code: `{matched_amfi_code}` (Live NAV will sync automatically)")
            
            name_input = selected_fund_label.split(" [")[0]
            sub_type = "Mutual Fund Direct"
            identifier = matched_amfi_code
            qty = st.number_input("Total Units Held", min_value=0.001, step=1.0, format="%.3f")
            buy_price = st.number_input(f"Average Purchase NAV ({cur})", min_value=0.01, step=1.0)
            curr_price = buy_price
            monthly_rent = 0.0
            p_year = current_year
            unit = "units"

        elif cat == "Real Estate":
            name_input = st.text_input("Property Label (e.g. Tolichowki 3BHK, Dubai Marina Apt)")
            sub_type = st.selectbox("Property Type", ["Residential Apartment", "Commercial Office/Shop", "Villa", "Plot / Land"])
            col_r1, col_r2 = st.columns(2)
            area = col_r1.number_input("Area (Sq. Ft / Sq. Yards)", min_value=1.0, value=1500.0, step=50.0)
            p_year = col_r2.number_input("Year of Purchase", min_value=1990, max_value=current_year, value=2021)
            col_v1, col_v2 = st.columns(2)
            buy_price = col_v1.number_input(f"Total Purchase Cost ({cur})", min_value=10000.0, step=50000.0)
            curr_price = col_v2.number_input(f"Current Market Estimate ({cur})", min_value=10000.0, step=50000.0)
            monthly_rent = st.number_input(f"Monthly Rental Cashflow ({cur})", min_value=0.0, step=2000.0)
            identifier = ""
            qty = area
            unit = "sq_ft"

        elif cat == "Bullion (Gold / Silver)":
            name_input = st.text_input("Bullion Label (e.g. 24K Gold Bar, Silver Coins)")
            sub_type = st.selectbox("Metal Type", ["Gold 24K", "Gold 22K", "Silver 999"])
            grams = st.number_input("Weight in Grams", min_value=0.0001, step=1.0, format="%.4f")
            buy_price = st.number_input(f"Purchase Rate per Gram ({cur})", min_value=0.1, step=50.0)
            curr_price = st.number_input(f"Current Spot Market Rate per Gram ({cur})", min_value=0.1, step=50.0)
            monthly_rent = 0.0
            p_year = current_year
            identifier = "GC=F" if "Gold" in sub_type else "SI=F"
            qty = grams
            unit = "grams"

        elif cat == "Indian Equities (NSE/BSE)":
            name_input = st.text_input("Stock Name (e.g. Reliance Industries, TCS)")
            sub_type = "Equity Stock"
            identifier = st.text_input("Ticker Symbol (e.g. RELIANCE.NS, TCS.NS, ARVSMART.NS)")
            qty = st.number_input("Shares Quantity", min_value=1.0, step=1.0)
            buy_price = st.number_input(f"Average Buy Price per Share ({cur})", min_value=0.1, step=1.0)
            curr_price = buy_price
            monthly_rent = 0.0
            p_year = current_year
            unit = "shares"

        else:
            name_input = st.text_input("Account Label / Bank Name (e.g. HDFC Savings, Fixed Deposit)")
            sub_type = "Liquid / Fixed Income"
            identifier = ""
            qty = 1.0
            buy_price = st.number_input(f"Principal Balance ({cur})", min_value=100.0, step=5000.0)
            curr_price = buy_price
            monthly_rent = 0.0
            p_year = current_year
            unit = "lump_sum"

        if st.form_submit_button("Save Asset to Portfolio", use_container_width=True):
            cursor.execute("""
            INSERT INTO assets (user_id, name, category, sub_type, identifier, quantity, unit, buy_price, current_price, monthly_income, purchase_year, currency)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (uid, name_input, cat, sub_type, identifier, qty, unit, buy_price, curr_price, monthly_rent, p_year, cur))
            conn.commit()
            st.success(f"{name_input} recorded successfully.")
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 4: CAMS / KFINTECH CAS STATEMENT AUTO-SYNC
with tab_cas:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("📥 CAMS / KFintech Consolidated Statement Auto-Sync")
    st.caption("Auto-import mutual fund portfolios from standardized CAMS/CAS export files.")

    cas_file = st.file_uploader("Upload CAMS / CAS CSV Export", type=["csv"])
    if cas_file:
        try:
            cas_df = pd.read_csv(cas_file)
            st.write("Preview of Uploaded Holdings:")
            st.dataframe(cas_df.head(5), use_container_width=True)

            if st.button("Auto-Import Holdings to Vault"):
                # Detect columns flexibly
                imported_count = 0
                for _, row in cas_df.iterrows():
                    scheme_name = str(row.get("Scheme Name", row.get("scheme", row.get("Fund Name", "Mutual Fund"))))
                    units = float(row.get("Units", row.get("units", row.get("Quantity", 1.0))))
                    buy_nav = float(row.get("Purchase NAV", row.get("nav", row.get("Buy Price", 100.0))))
                    
                    # Try matching AMFI code
                    mapped_code = ""
                    for label, code in AMFI_DIRECTORY.items():
                        if scheme_name.lower() in label.lower():
                            mapped_code = code
                            break

                    cursor.execute("""
                    INSERT INTO assets (user_id, name, category, sub_type, identifier, quantity, unit, buy_price, current_price, monthly_income, purchase_year, currency)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (uid, scheme_name, "Mutual Funds", "Mutual Fund Direct", mapped_code, units, "units", buy_nav, buy_nav, 0.0, current_year, "INR"))
                    imported_count += 1

                conn.commit()
                st.success(f"Successfully imported {imported_count} mutual fund schemes.")
                st.rerun()
        except Exception as e:
            st.error(f"Error parsing CAS file: {e}")
    else:
        st.info("Upload your monthly Consolidated Account Statement (CAS) export to sync all folios in one click.")
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 5: DEBT & LIABILITIES
with tab_debt:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("💳 Liabilities, Mortgages & EMIs")
    with st.form("debt_form"):
        l_name = st.text_input("Liability Name (e.g. HDFC Home Loan, Auto Loan)")
        l_cat = st.selectbox("Type", ["Home Loan", "Vehicle Loan", "Personal Loan", "Credit Card Debt", "Builder Installment Plan"])
        l_prin = st.number_input("Outstanding Principal (INR)", min_value=0.0, step=25000.0)
        l_rate = st.number_input("Interest Rate (%)", min_value=0.0, value=8.5, step=0.1)
        l_emi = st.number_input("Monthly EMI (INR)", min_value=0.0, step=1000.0)
        if st.form_submit_button("Save Liability Record", use_container_width=True):
            cursor.execute("INSERT INTO liabilities (user_id, name, category, principal_outstanding, interest_rate, monthly_emi) VALUES (?, ?, ?, ?, ?, ?)",
                           (uid, l_name, l_cat, l_prin, l_rate, l_emi))
            conn.commit()
            st.success("Liability updated.")
            st.rerun()

    if not liabs_raw.empty:
        st.dataframe(liabs_raw[["id", "name", "category", "principal_outstanding", "interest_rate", "monthly_emi"]], use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 6: DYNAMIC FIRE & GOAL-BASED SIMULATOR
with tab_sim:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("🎯 Dynamic FIRE & Milestone Engine")
    st.caption("Custom inflation, dynamic withdrawal rates, and capital outflow milestones.")

    col_f1, col_f2, col_f3 = st.columns(3)
    current_age = col_f1.number_input("Current Age", min_value=18, max_value=80, value=35, step=1)
    target_fire_age = col_f2.number_input("Target Retirement Age", min_value=current_age + 1, max_value=90, value=50, step=1)
    monthly_living_exp = col_f3.number_input("Monthly Living Expenses (INR)", min_value=10000.0, value=75000.0, step=5000.0)

    col_p1, col_p2, col_p3 = st.columns(3)
    monthly_sip_alloc = col_p1.number_input("Monthly Investment Allocation (INR)", min_value=0.0, value=50000.0, step=5000.0)
    expected_cagr = col_p2.slider("Expected Pre-Retirement CAGR (%)", 6.0, 18.0, 12.0, 0.5)
    inflation_rate = col_p3.slider("Annual Inflation Rate (%)", 3.0, 10.0, 6.0, 0.5)

    col_swr1, col_swr2 = st.columns(2)
    swr_pct = col_swr1.slider("Safe Withdrawal Rate (SWR %)", 2.5, 5.0, 4.0, 0.1, help="4% = 25x rule, 3.3% = 30x conservative rule")
    years_to_fire = target_fire_age - current_age

    st.markdown("#### 🚩 Milestone Goals / Capital Outflows")
    with st.expander("➕ Configure Intermediate Goals"):
        col_g1, col_g2, col_g3 = st.columns(3)
        goal_1_name = col_g1.text_input("Goal 1 Name", value="Real Estate Down Payment")
        goal_1_years = col_g2.number_input("Occurs in (Years)", min_value=1, max_value=max(1, years_to_fire), value=min(4, max(1, years_to_fire)))
        goal_1_amount = col_g3.number_input("Goal 1 Amount (INR)", min_value=0.0, value=2500000.0, step=100000.0)

        col_g4, col_g5, col_g6 = st.columns(3)
        goal_2_name = col_g4.text_input("Goal 2 Name", value="Higher Education / Wedding")
        goal_2_years = col_g5.number_input("Occurs in (Years)", min_value=1, max_value=max(1, years_to_fire), value=min(8, max(1, years_to_fire)))
        goal_2_amount = col_g6.number_input("Goal 2 Amount (INR)", min_value=0.0, value=1500000.0, step=100000.0)

    current_annual_exp = monthly_living_exp * 12
    future_annual_exp = current_annual_exp * ((1 + (inflation_rate / 100)) ** years_to_fire)
    target_fire_corpus = future_annual_exp / (swr_pct / 100)

    monthly_r = (expected_cagr / 100) / 12
    total_months = years_to_fire * 12
    running_corpus = total_current_inr
    projection_records = []
    goal_outflows_dict = {
        goal_1_years * 12: (goal_1_name, goal_1_amount),
        goal_2_years * 12: (goal_2_name, goal_2_amount)
    }

    for m in range(1, total_months + 1):
        running_corpus = (running_corpus + monthly_sip_alloc) * (1 + monthly_r)
        
        if m in goal_outflows_dict and goal_outflows_dict[m][1] > 0:
            running_corpus = max(0.0, running_corpus - goal_outflows_dict[m][1])

        if m % 12 == 0:
            year_num = m // 12
            sim_age = current_age + year_num
            inflated_annual_cost = current_annual_exp * ((1 + (inflation_rate / 100)) ** year_num)
            required_corpus_at_yr = inflated_annual_cost / (swr_pct / 100)
            
            projection_records.append({
                "Year": year_num,
                "Age": sim_age,
                "Projected Wealth (INR)": round(running_corpus, 2),
                "Required FIRE Corpus (INR)": round(required_corpus_at_yr, 2)
            })

    sim_df = pd.DataFrame(projection_records)
    final_corpus = sim_df.iloc[-1]["Projected Wealth (INR)"] if not sim_df.empty else 0.0
    corpus_delta = final_corpus - target_fire_corpus

    st.divider()
    m1, m2, m3 = st.columns(3)
    m1.metric(f"Projected Corpus at Age {target_fire_age}", f"₹{final_corpus:,.0f}")
    m2.metric("Target FIRE Number", f"₹{target_fire_corpus:,.0f}")
    m3.metric("Surplus / Shortfall", f"₹{corpus_delta:,.0f}", delta=f"{'Surplus' if corpus_delta >= 0 else 'Shortfall'}")

    if not sim_df.empty:
        fig_fire = go.Figure()
        fig_fire.add_trace(go.Scatter(
            x=sim_df["Age"],
            y=sim_df["Projected Wealth (INR)"],
            mode='lines+markers',
            name='Projected Corpus',
            line=dict(color='#38BDF8', width=3),
            fill='tozeroy',
            fillcolor='rgba(56, 189, 248, 0.08)'
        ))
        fig_fire.add_trace(go.Scatter(
            x=sim_df["Age"],
            y=sim_df["Required FIRE Corpus (INR)"],
            mode='lines',
            name='Required FIRE Threshold',
            line=dict(color='#F43F5E', width=2, dash='dash')
        ))
        fig_fire.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#F8FAFC", family="Plus Jakarta Sans"),
            title="Portfolio Growth vs Inflation-Adjusted FIRE Target",
            xaxis_title="Age",
            yaxis_title="INR (₹)",
            hovermode="x unified"
        )
        st.plotly_chart(fig_fire, use_container_width=True)

    if corpus_delta >= 0:
        st.success(f"🎉 **FIRE Achievable:** At age {target_fire_age}, your projected portfolio (₹{final_corpus:,.2f}) covers your estimated living expense of ₹{future_annual_exp:,.2f}/yr at a {swr_pct}% safe withdrawal rate.")
    else:
        n = max(1, total_months)
        r = monthly_r
        future_val_existing = total_current_inr * ((1 + r) ** n)
        remaining_gap = max(0.0, target_fire_corpus - future_val_existing + (goal_1_amount + goal_2_amount))
        required_monthly_sip = remaining_gap * (r / (((1 + r) ** n) - 1)) if r > 0 else (remaining_gap / n)
        st.warning(f"⚠️ **Target Gap:** Shortfall of ₹{abs(corpus_delta):,.2f}. To reach FIRE by age {target_fire_age} while funding your goals, consider increasing monthly allocation to **₹{required_monthly_sip:,.2f} / month**.")
    st.markdown('</div>', unsafe_allow_html=True)

# TAB 7: MOBILE APP & QR CODE
with tab_share:
    st.markdown('<div class="glass-card">', unsafe_allow_html=True)
    st.subheader("📲 Install & Distribute VaultCFO")
    st.caption("Access your private wealth portal across iPhone, iPad, and Android[cite: 1].")
    
    app_url = st.text_input("Hosted App Web Link", value="https://vaultcfoai.streamlit.app/")
    
    col_qr1, col_qr2 = st.columns([1, 2])
    with col_qr1:
        qr_bytes = generate_qr_image(app_url)
        st.image(qr_bytes, caption="Scan on Mobile to Launch", width=220)
        st.download_button(
            label="📥 Download Marketing QR Code",
            data=qr_bytes,
            file_name="vaultcfo_qr.png",
            mime="image/png"
        )
    with col_qr2:
        st.markdown(f"""
        **Direct Link:** [{app_url}]({app_url})
        
        ### 📱 Progressive Web App (PWA) Setup
        * **iPhone / iOS (Safari):** Tap **Share** $\rightarrow$ Select **"Add to Home Screen"**[cite: 1].
        * **Android (Chrome):** Tap **Menu (3 Dots)** $\rightarrow$ Select **"Install App"** / **"Add to Home Screen"**.
        
        ### 💼 Commercial App Store Packaging
        * **Google Play Store:** Wrap the hosted URL with **Bubblewrap / Trusted Web Activities (TWA)** for standard Android submission.
        * **Apple App Store:** Package using **Capacitor** with In-App Subscriptions (IAP) enabled[cite: 1].
        """)
    st.markdown('</div>', unsafe_allow_html=True)
