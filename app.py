import sqlite3
import hashlib
import requests
import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import google.generativeai as genai

st.set_page_config(page_title="AI CFO Enterprise — Autonomous Wealth Platform", layout="wide", page_icon="🏛️")

# ----------------- DATABASE SCHEMA -----------------
conn = sqlite3.connect("cfo_enterprise_v2.db", check_same_thread=False)
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

AED_TO_INR = 22.85
USD_TO_INR = 86.50

def hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

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

# ----------------- AUTHENTICATION -----------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.username = ""

if not st.session_state.authenticated:
    st.title("🔒 Institutional AI CFO — Sign In")
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
        if st.button("Register Account", use_container_width=True):
            if ru and rp:
                try:
                    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (ru, hash_pw(rp)))
                    conn.commit()
                    st.success("Account initialized! Please log in.")
                except sqlite3.IntegrityError:
                    st.error("Username already registered.")
    st.stop()

# ----------------- LOGGED IN APP -----------------
uid = st.session_state.user_id
current_year = datetime.datetime.now().year

with st.sidebar:
    st.title(f"👤 {st.session_state.username}")
    if st.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.rerun()
    st.divider()
    st.subheader("🔑 AI Brain")
    gemini_key = st.text_input("Gemini API Key", type="password")
    if gemini_key:
        genai.configure(api_key=gemini_key)

# Fetch Records
assets_raw = pd.read_sql(f"SELECT * FROM assets WHERE user_id = {uid}", conn)
liabs_raw = pd.read_sql(f"SELECT * FROM liabilities WHERE user_id = {uid}", conn)

processed_assets = []
total_invested_inr = 0.0
total_current_inr = 0.0
annual_rental_cashflow = 0.0

for _, row in assets_raw.iterrows():
    qty = row["quantity"]
    buy_p = row["buy_price"]
    curr_p = row["current_price"]
    currency = row["currency"]
    multiplier = AED_TO_INR if currency == "AED" else (USD_TO_INR if currency == "USD" else 1.0)
    
    invested_val = (qty * buy_p) * multiplier
    current_unit_val = curr_p
    asset_name = row["name"]

    # Live Lookups
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

    # Real Estate CAGR Calculation
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

# ----------------- MAIN VIEW -----------------
st.title("💼 AI CFO Enterprise Hub")

c1, c2, c3, c4 = st.columns(4)
c1.metric("True Net Worth", f"₹{net_worth:,.2f}", delta=f"{unrealized_pnl_pct:.2f}% Return")
c2.metric("Total Assets", f"₹{total_current_inr:,.2f}", f"₹{total_invested_inr:,.2f} Invested")
c3.metric("Total Debt", f"₹{total_liabilities:,.2f}", delta_color="inverse")
c4.metric("Annual Rental Income", f"₹{annual_rental_cashflow:,.2f}")

st.divider()

tab_ai, tab_port, tab_add, tab_debt, tab_sim = st.tabs([
    "💬 AI CFO Copilot",
    "📊 Wealth & Real Estate Analytics",
    "➕ Add Asset (Dynamic Engine)",
    "💳 Debt & Liabilities",
    "🎯 8–10 Yr Growth Simulator"
])

# TAB 1: AI COPILOT
with tab_ai:
    st.subheader("🤖 Autonomous AI CFO")
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "I am your AI CFO. I have full context on your bullion, real estate CAGR, rental yields, mutual funds, and liabilities. Ask me for portfolio reviews or strategic advice!"}]

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if query := st.chat_input("e.g. Analyze my real estate returns and suggest rebalancing options:"):
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            if not gemini_key:
                st.warning("Please enter your Gemini API Key in the left sidebar.")
            else:
                with st.spinner("Analyzing portfolio ledger..."):
                    try:
                        model = genai.GenerativeModel("gemini-1.5-flash")
                        context = f"User Data: Assets: {assets_df.to_dict(orient='records')}, Debt: {liabs_raw.to_dict(orient='records')}, Net Worth: INR {net_worth}"
                        res = model.generate_content(f"{context}\n\nUser Question: {query}")
                        st.markdown(res.text)
                        st.session_state.messages.append({"role": "assistant", "content": res.text})
                    except Exception as e:
                        st.error(f"Error: {e}")

# TAB 2: PORTFOLIO & REAL ESTATE ANALYTICS
with tab_port:
    if not assets_df.empty:
        col1, col2 = st.columns([1.2, 1])
        with col1:
            fig_alloc = px.pie(assets_df, values="Current Value (INR)", names="Category", hole=0.5, title="Asset Allocation")
            st.plotly_chart(fig_alloc, use_container_width=True)
        with col2:
            fig_bar = px.bar(assets_df, x="Category", y="Current Value (INR)", color="Category", title="Capital by Asset Class")
            st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("Asset Holdings & Yield Ledger")
        st.dataframe(assets_df, use_container_width=True, hide_index=True)

        del_id = st.number_input("Delete Holding by ID", min_value=1, step=1)
        if st.button("Delete Entry"):
            cursor.execute("DELETE FROM assets WHERE id = ? AND user_id = ?", (del_id, uid))
            conn.commit()
            st.success("Entry removed.")
            st.rerun()
    else:
        st.info("No assets configured. Use the 'Add Asset' tab to initialize your portfolio.")

# TAB 3: DYNAMIC ASSET CREATION ENGINE
with tab_add:
    st.subheader("➕ Dynamic Asset Setup Engine")
    cat = st.selectbox("Asset Class", [
        "Real Estate",
        "Bullion (Gold / Silver)",
        "Mutual Funds",
        "Indian Equities (NSE/BSE)",
        "Fixed Deposit / EPF / Sukanya",
        "Savings / Liquid Cash"
    ])
    cur = st.radio("Denomination Currency", ["INR", "AED", "USD"], horizontal=True)

    with st.form("dynamic_asset_form"):
        name_input = st.text_input("Asset Label / Property Name / Institution")

        # Dynamic Real Estate Fields
        if cat == "Real Estate":
            sub_type = st.selectbox("Property Type", ["Residential Apartment", "Commercial Office/Shop", "Independent House/Villa", "Plot / Land"])
            col_r1, col_r2 = st.columns(2)
            area = col_r1.number_input("Area (Sq. Ft / Sq. Yards)", min_value=1.0, value=1500.0, step=50.0)
            p_year = col_r2.number_input("Year of Purchase", min_value=1990, max_value=current_year, value=2021)
            
            col_v1, col_v2 = st.columns(2)
            buy_price = col_v1.number_input(f"Total Purchase Price + Reg ({cur})", min_value=10000.0, step=50000.0)
            curr_price = col_v2.number_input(f"Current Estimated Market Value ({cur})", min_value=10000.0, step=50000.0)
            
            monthly_rent = st.number_input(f"Monthly Rental Income ({cur}, 0 if self-occupied)", min_value=0.0, step=2000.0)
            identifier = ""
            qty = area
            unit = "sq_ft"

        # Dynamic Bullion Fields
        elif cat == "Bullion (Gold / Silver)":
            sub_type = st.selectbox("Metal Type", ["Gold 24K", "Gold 22K", "Silver 999"])
            grams = st.number_input("Weight in Grams", min_value=0.0001, step=1.0, format="%.4f")
            buy_price = st.number_input(f"Purchase Price per Gram ({cur})", min_value=0.1, step=50.0)
            curr_price = st.number_input(f"Current Spot Market Price per Gram ({cur})", min_value=0.1, step=50.0)
            monthly_rent = 0.0
            p_year = current_year
            identifier = "GC=F" if "Gold" in sub_type else "SI=F"
            qty = grams
            unit = "grams"

        # Dynamic Mutual Fund Fields
        elif cat == "Mutual Funds":
            sub_type = "Mutual Fund Direct"
            identifier = st.text_input("AMFI Scheme Code (e.g. 122639 for Parag Parikh Flexi Cap)")
            qty = st.number_input("Units Held", min_value=0.001, step=1.0, format="%.3f")
            buy_price = st.number_input(f"Average Buy NAV ({cur})", min_value=0.01, step=1.0)
            curr_price = buy_price
            monthly_rent = 0.0
            p_year = current_year
            unit = "units"

        # Dynamic Stock Fields
        elif cat == "Indian Equities (NSE/BSE)":
            sub_type = "Equity Stock"
            identifier = st.text_input("Yahoo Ticker (e.g. RELIANCE.NS, TCS.NS, ARVSMART.NS)")
            qty = st.number_input("Shares Quantity", min_value=1.0, step=1.0)
            buy_price = st.number_input(f"Average Buy Price per Share ({cur})", min_value=0.1, step=1.0)
            curr_price = buy_price
            monthly_rent = 0.0
            p_year = current_year
            unit = "shares"

        # Fixed Income / Cash
        else:
            sub_type = "Fixed Income / Liquid"
            identifier = ""
            qty = 1.0
            buy_price = st.number_input(f"Principal Balance / Valuation ({cur})", min_value=100.0, step=5000.0)
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
            st.success(f"{name_input} added successfully.")
            st.rerun()

# TAB 4: DEBT & LIABILITIES
with tab_debt:
    st.subheader("Manage Liabilities & EMIs")
    with st.form("debt_form"):
        l_name = st.text_input("Loan / Debt Name (e.g. HDFC Home Loan, Car Loan)")
        l_cat = st.selectbox("Type", ["Home Loan", "Vehicle Loan", "Personal Loan", "Credit Card Debt", "Builder Installment Plan"])
        l_prin = st.number_input("Outstanding Principal (INR)", min_value=0.0, step=25000.0)
        l_rate = st.number_input("Interest Rate (%)", min_value=0.0, value=8.5, step=0.1)
        l_emi = st.number_input("Monthly EMI (INR)", min_value=0.0, step=1000.0)
        if st.form_submit_button("Save Liability", use_container_width=True):
            cursor.execute("INSERT INTO liabilities (user_id, name, category, principal_outstanding, interest_rate, monthly_emi) VALUES (?, ?, ?, ?, ?, ?)",
                           (uid, l_name, l_cat, l_prin, l_rate, l_emi))
            conn.commit()
            st.success("Liability updated.")
            st.rerun()

    if not liabs_raw.empty:
        st.dataframe(liabs_raw[["id", "name", "category", "principal_outstanding", "interest_rate", "monthly_emi"]], use_container_width=True)

# TAB 5: SIMULATOR
with tab_sim:
    st.subheader("🎯 8–10 Year Wealth & Goal Simulator")
    s1, s2, s3 = st.columns(3)
    sip = s1.number_input("Monthly Allocation (INR)", value=50000, step=5000)
    cagr = s2.slider("Expected CAGR (%)", 6.0, 20.0, 12.0, 0.5)
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
        st.success(f"Estimated Corpus at Year {yrs}: **₹{df_p.iloc[-1]['Projected Corpus (INR)']:,.2f} INR**")
