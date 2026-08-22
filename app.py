import sqlite3
import hashlib
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import google.generativeai as genai

st.set_page_config(page_title="AI CFO Pro — Autonomous Wealth Platform", layout="wide", page_icon="🤖")

# ----------------- DATABASE SCHEMA -----------------
conn = sqlite3.connect("cfo_enterprise.db", check_same_thread=False)
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
    identifier TEXT,
    quantity REAL,
    unit TEXT,
    buy_price REAL,
    interest_rate REAL,
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
cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    date DATE,
    description TEXT,
    category TEXT,
    amount REAL,
    type TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")
conn.commit()

# ----------------- LIVE MARKET DATA -----------------
AED_TO_INR = 22.85
USD_TO_INR = 86.50

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

def hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

# ----------------- AUTHENTICATION -----------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.username = ""

if not st.session_state.authenticated:
    st.title("🔒 AI CFO — Sign In")
    tab_log, tab_reg = st.tabs(["Login", "Create Account"])
    with tab_log:
        u = st.text_input("Username", key="l_u")
        p = st.text_input("Password", type="password", key="l_p")
        if st.button("Log In", use_container_width=True):
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
        ru = st.text_input("New Username", key="r_u")
        rp = st.text_input("New Password", type="password", key="r_p")
        if st.button("Register", use_container_width=True):
            if ru and rp:
                try:
                    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (ru, hash_pw(rp)))
                    conn.commit()
                    st.success("Account created! Please log in.")
                except sqlite3.IntegrityError:
                    st.error("Username taken.")
    st.stop()

# ----------------- LOGGED IN DASHBOARD -----------------
uid = st.session_state.user_id

# Sidebar: API Key & Configuration
with st.sidebar:
    st.title(f"👤 {st.session_state.username}")
    if st.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.rerun()
    
    st.divider()
    st.subheader("🔑 AI Brain Setup")
    gemini_key = st.text_input("Enter Gemini API Key", type="password", help="Get a free key from aistudio.google.com")
    if gemini_key:
        genai.configure(api_key=gemini_key)
        st.success("Gemini Brain Connected ⚡")
    else:
        st.info("Add your free Gemini API key to activate conversational AI responses.")

# Fetch Records
assets_raw = pd.read_sql(f"SELECT * FROM assets WHERE user_id = {uid}", conn)
liabs_raw = pd.read_sql(f"SELECT * FROM liabilities WHERE user_id = {uid}", conn)
trans_raw = pd.read_sql(f"SELECT * FROM transactions WHERE user_id = {uid}", conn)

processed_assets = []
total_invested_inr = 0.0
total_current_inr = 0.0

for _, row in assets_raw.iterrows():
    qty = row["quantity"]
    buy_p = row["buy_price"]
    currency = row["currency"]
    multiplier = AED_TO_INR if currency == "AED" else (USD_TO_INR if currency == "USD" else 1.0)
    
    invested_val = (qty * buy_p) * multiplier
    current_unit_p = buy_p
    asset_title = row["name"]

    if row["category"] == "Mutual Funds" and row["identifier"]:
        live_nav, scheme_name = fetch_mf_nav(row["identifier"])
        if live_nav:
            current_unit_p = live_nav
            if scheme_name:
                asset_title = scheme_name
    elif row["category"] in ["Indian Equities (NSE/BSE)", "US Equities"] and row["identifier"]:
        live_p = fetch_live_market_price(row["identifier"])
        if live_p > 0:
            current_unit_p = live_p
    elif row["category"] in ["Fixed Deposit", "EPF / PPF / Sukanya"]:
        rate = row["interest_rate"] or 7.0
        current_unit_p = buy_p * (1 + (rate / 100))
    
    current_val = (qty * current_unit_p) * multiplier
    pnl = current_val - invested_val
    pnl_pct = (pnl / invested_val * 100) if invested_val > 0 else 0.0

    total_invested_inr += invested_val
    total_current_inr += current_val

    processed_assets.append({
        "ID": row["id"],
        "Name": asset_title,
        "Category": row["category"],
        "Holdings": f"{qty:,.2f} {row['unit']}",
        "Buy Price": f"{currency} {buy_p:,.2f}",
        "Current Price": f"{currency} {current_unit_p:,.2f}",
        "Invested (INR)": invested_val,
        "Current Value (INR)": current_val,
        "P&L (INR)": pnl,
        "P&L (%)": pnl_pct
    })

assets_df = pd.DataFrame(processed_assets)
total_liabilities = liabs_raw["principal_outstanding"].sum() if not liabs_raw.empty else 0.0
net_worth = total_current_inr - total_liabilities
unrealized_pnl = total_current_inr - total_invested_inr
unrealized_pnl_pct = (unrealized_pnl / total_invested_inr * 100) if total_invested_inr > 0 else 0.0

# ----------------- TOP METRIC BAR -----------------
st.title("💼 AI CFO Enterprise Hub")

c1, c2, c3, c4 = st.columns(4)
c1.metric("True Net Worth", f"₹{net_worth:,.2f}", delta=f"{unrealized_pnl_pct:.2f}% Return")
c2.metric("Total Asset Value", f"₹{total_current_inr:,.2f}", f"₹{total_invested_inr:,.2f} Invested")
c3.metric("Total Debt / Liabilities", f"₹{total_liabilities:,.2f}", delta_color="inverse")
c4.metric("Unrealized Profit/Loss", f"₹{unrealized_pnl:,.2f}", f"{unrealized_pnl_pct:.2f}%")

st.divider()

# ----------------- TABS INTERFACE -----------------
tab_ai, tab_port, tab_add, tab_debt, tab_sim = st.tabs([
    "💬 AI CFO Copilot (Ask Anything)",
    "📊 Portfolio & Asset Analytics",
    "➕ Add Asset (Any Class)",
    "💳 Debt & Liabilities",
    "🎯 8–10 Yr Wealth Simulator"
])

# TAB 1: AI CFO COPILOT (CONVERSATIONAL INTELLIGENCE)
with tab_ai:
    st.subheader("🤖 Your Private AI CFO Assistant")
    st.caption("Ask questions about your real numbers, scenario planning, rebalancing, and debt payoffs.")

    # Context Builder
    financial_context = f"""
    User Financial Profile:
    - Net Worth: INR {net_worth:,.2f}
    - Total Assets: INR {total_current_inr:,.2f} (Invested: INR {total_invested_inr:,.2f}, Unrealized P&L: INR {unrealized_pnl:,.2f} / {unrealized_pnl_pct:.2f}%)
    - Total Liabilities / Debt: INR {total_liabilities:,.2f}
    - Asset Holdings: {assets_df[['Name', 'Category', 'Holdings', 'Current Value (INR)', 'P&L (%)']].to_dict(orient='records') if not assets_df.empty else 'No assets recorded yet.'}
    - Liabilities Details: {liabs_raw[['name', 'category', 'principal_outstanding', 'interest_rate', 'monthly_emi']].to_dict(orient='records') if not liabs_raw.empty else 'Zero debt recorded.'}
    """

    if "ai_messages" not in st.session_state:
        st.session_state.ai_messages = [
            {"role": "assistant", "content": "Hello! I am your AI CFO. I have full real-time access to your portfolio, bullion holdings, equities, and liabilities. Ask me anything about your finances or long-term growth plans!"}
        ]

    for m in st.session_state.ai_messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if user_query := st.chat_input("e.g. How is my asset allocation balanced? What should I optimize next?"):
        st.session_state.ai_messages.append({"role": "user", "content": user_query})
        with st.chat_message("user"):
            st.markdown(user_query)

        with st.chat_message("assistant"):
            if not gemini_key:
                response_text = "⚠️ **Please enter your Gemini API Key in the left sidebar** to enable live AI analysis on your data."
                st.warning(response_text)
            else:
                with st.spinner("Analyzing your financial ledger..."):
                    try:
                        model = genai.GenerativeModel(
                            model_name="gemini-1.5-flash",
                            system_instruction="You are a disciplined, highly competent Personal AI CFO. Provide data-driven financial advice referencing the user's specific assets, debts, and net worth context. Always be concrete with numbers."
                        )
                        prompt = f"{financial_context}\n\nUser Question: {user_query}"
                        ai_res = model.generate_content(prompt)
                        response_text = ai_res.text
                        st.markdown(response_text)
                    except Exception as e:
                        response_text = f"Error communicating with AI: {str(e)}"
                        st.error(response_text)

            st.session_state.ai_messages.append({"role": "assistant", "content": response_text})

# TAB 2: PORTFOLIO ANALYTICS
with tab_port:
    if not assets_df.empty:
        col_g1, col_g2 = st.columns([1.2, 1])
        with col_g1:
            fig_alloc = px.pie(assets_df, values="Current Value (INR)", names="Category", hole=0.5, title="Asset Allocation")
            st.plotly_chart(fig_alloc, use_container_width=True)
        with col_g2:
            fig_pnl = px.bar(assets_df, x="Category", y="P&L (INR)", color="P&L (INR)", title="Unrealized Gains / Loss (INR)")
            st.plotly_chart(fig_pnl, use_container_width=True)

        st.dataframe(
            assets_df[["ID", "Name", "Category", "Holdings", "Buy Price", "Current Price", "Current Value (INR)", "P&L (%)"]],
            use_container_width=True,
            hide_index=True
        )

        del_id = st.number_input("Delete Entry by ID", min_value=1, step=1)
        if st.button("Delete Asset Entry"):
            cursor.execute("DELETE FROM assets WHERE id = ? AND user_id = ?", (del_id, uid))
            conn.commit()
            st.success("Entry removed.")
            st.rerun()
    else:
        st.info("No assets configured yet. Add holdings in the 'Add Asset' tab.")

# TAB 3: ADD ASSET ENGINE
with tab_add:
    st.subheader("Add Any Financial Asset")
    cat = st.selectbox("Asset Class", [
        "Mutual Funds",
        "Indian Equities (NSE/BSE)",
        "Bullion (Gold/Silver)",
        "Fixed Deposit",
        "EPF / PPF / Sukanya",
        "US Equities",
        "Savings / Liquid Cash",
        "Real Estate"
    ])
    cur = st.radio("Base Currency", ["INR", "AED", "USD"], horizontal=True)

    with st.form("add_asset_form"):
        name_input = st.text_input("Asset Label / Institution Name (e.g. Parag Parikh Flexi Cap, Ogold, Zerodha, HDFC)")
        if cat == "Mutual Funds":
            identifier = st.text_input("AMFI Scheme Code (e.g. 122639)")
            qty = st.number_input("Units Held", min_value=0.001, step=1.0, format="%.3f")
            buy_p = st.number_input("Purchase NAV", min_value=0.01, step=1.0)
            ir = 0.0
            unit = "units"
        elif cat == "Indian Equities (NSE/BSE)":
            identifier = st.text_input("Yahoo Ticker (e.g. RELIANCE.NS, TCS.NS)")
            qty = st.number_input("Shares", min_value=1.0, step=1.0)
            buy_p = st.number_input(f"Average Buy Price ({cur})", min_value=0.1, step=1.0)
            ir = 0.0
            unit = "shares"
        elif cat == "Bullion (Gold/Silver)":
            metal = st.selectbox("Metal", ["Gold 24K", "Silver"])
            identifier = "GC=F" if "Gold" in metal else "SI=F"
            qty = st.number_input("Weight in Grams", min_value=0.0001, step=1.0, format="%.4f")
            buy_p = st.number_input(f"Price per Gram ({cur})", min_value=0.1, step=10.0)
            ir = 0.0
            unit = "grams"
        elif cat in ["Fixed Deposit", "EPF / PPF / Sukanya"]:
            identifier = ""
            qty = 1.0
            buy_p = st.number_input(f"Deposit Principal ({cur})", min_value=100.0, step=5000.0)
            ir = st.number_input("Annual Interest Rate (%)", min_value=1.0, value=7.1, step=0.1)
            unit = "deposit"
        else:
            identifier = ""
            qty = 1.0
            buy_p = st.number_input(f"Total Value / Balance ({cur})", min_value=1.0, step=10000.0)
            ir = 0.0
            unit = "lump_sum"

        if st.form_submit_button("Save Asset", use_container_width=True):
            cursor.execute(
                "INSERT INTO assets (user_id, name, category, identifier, quantity, unit, buy_price, interest_rate, currency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, name_input, cat, identifier, qty, unit, buy_p, ir, cur)
            )
            conn.commit()
            st.success("Asset recorded.")
            st.rerun()

# TAB 4: DEBT & LIABILITIES
with tab_debt:
    st.subheader("Manage Liabilities & EMIs")
    with st.form("debt_form"):
        l_name = st.text_input("Loan / Debt Name (e.g. HDFC Home Loan, Car Loan)")
        l_cat = st.selectbox("Type", ["Home Loan", "Vehicle Loan", "Personal Loan", "Credit Card Debt", "Builder Plan"])
        l_prin = st.number_input("Outstanding Balance (INR)", min_value=0.0, step=25000.0)
        l_rate = st.number_input("Interest Rate (%)", min_value=0.0, value=8.5, step=0.1)
        l_emi = st.number_input("Monthly EMI (INR)", min_value=0.0, step=1000.0)
        if st.form_submit_button("Save Liability", use_container_width=True):
            cursor.execute(
                "INSERT INTO liabilities (user_id, name, category, principal_outstanding, interest_rate, monthly_emi) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, l_name, l_cat, l_prin, l_rate, l_emi)
            )
            conn.commit()
            st.success("Liability updated.")
            st.rerun()

    if not liabs_raw.empty:
        st.dataframe(liabs_raw[["id", "name", "category", "principal_outstanding", "interest_rate", "monthly_emi"]], use_container_width=True)

# TAB 5: WEALTH SIMULATOR
with tab_sim:
    st.subheader("🎯 8–10 Year Wealth & Goal Simulator")
    s1, s2, s3 = st.columns(3)
    sip = s1.number_input("Monthly Addition (INR)", value=50000, step=5000)
    cagr = s2.slider("CAGR Return (%)", 6.0, 20.0, 12.0, 0.5)
    yrs = s3.slider("Horizon (Years)", 3, 20, 10)

    months = yrs * 12
    monthly_r = (cagr / 100) / 12
    current_val = total_current_inr
    proj_rows = []

    for m in range(1, months + 1):
        current_val = (current_val + sip) * (1 + monthly_r)
        if m % 12 == 0:
            proj_rows.append({"Year": m // 12, "Projected Corpus (INR)": round(current_val, 2)})

    df_p = pd.DataFrame(proj_rows)
    fig_sim = px.line(df_p, x="Year", y="Projected Corpus (INR)", markers=True, title=f"Compounding Growth Over {yrs} Years")
    st.plotly_chart(fig_sim, use_container_width=True)
    if not df_p.empty:
        st.success(f"Projected Total at Year {yrs}: **₹{df_p.iloc[-1]['Projected Corpus (INR)']:,.2f} INR**")
