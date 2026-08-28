import sqlite3
import hashlib
import datetime
import io
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
import google.generativeai as genai
import qrcode
from PIL import Image

# ----------------- BRANDING & PAGE CONFIG -----------------
st.set_page_config(
    page_title="VaultCFO — Autonomous Wealth Copilot",
    layout="wide",
    page_icon="🛡️"
)

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

# ----------------- LIVE REAL-TIME FOREX ENGINE -----------------
@st.cache_data(ttl=300)
def fetch_live_fx_rates():
    """Fetches real-time market exchange rates for USD/INR and AED/INR with fallback."""
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
        <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 25px;">
            <div style="background-color: #1E293B; padding: 14px 18px; border-radius: 14px; font-size: 32px;">🛡️</div>
            <div>
                <h1 style="margin: 0; font-size: 30px; font-weight: 700;">VaultCFO <span style="color: #38BDF8; font-size: 18px; font-weight: 600;">PRO</span></h1>
                <p style="margin: 0; color: #94A3B8; font-size: 15px;">Autonomous Multi-Asset Intelligence & Wealth Copilot</p>
            </div>
        </div>
    """, unsafe_allow_html=True)
    
    tab_log, tab_reg = st.tabs(["Login", "Create Private Account"])
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
                st.error("Invalid username or password.")
    with tab_reg:
        ru = st.text_input("New Username", key="reg_u")
        rp = st.text_input("New Password", type="password", key="reg_p")
        if st.button("Register Account", use_container_width=True):
            if ru and rp:
                try:
                    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (ru, hash_pw(rp)))
                    conn.commit()
                    st.success("Account created successfully! Please log in.")
                except sqlite3.IntegrityError:
                    st.error("Username already exists.")
    st.stop()

# ----------------- LOGGED IN APPLICATION -----------------
uid = st.session_state.user_id
current_year = datetime.datetime.now().year

# Header with Logo & Brand
st.markdown("""
    <div style="display: flex; align-items: center; gap: 15px; margin-bottom: 20px;">
        <div style="background-color: #1E293B; padding: 12px 18px; border-radius: 12px; font-size: 28px;">🛡️</div>
        <div>
            <h1 style="margin: 0; font-size: 28px; font-weight: 700;">VaultCFO <span style="color: #38BDF8; font-size: 18px; font-weight: 500;">ENTERPRISE</span></h1>
            <p style="margin: 0; color: #94A3B8; font-size: 14px;">Autonomous Multi-Asset Intelligence & Wealth Copilot</p>
        </div>
    </div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.title(f"👤 {st.session_state.username}")
    if st.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.rerun()
    st.divider()
    if ai_ready:
        st.success("⚡ Gemini AI Active")
    else:
        st.warning("⚠️ Add GEMINI_API_KEY in Secrets")
    
    st.subheader("🌐 Live Exchange Rates")
    st.metric(label="USD / INR", value=f"₹{USD_TO_INR:,.2f}")
    st.metric(label="AED / INR", value=f"₹{AED_TO_INR:,.2f}")
    st.caption("Live feed via FX Market")

# Fetch User Data
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

# Top KPI Row
c1, c2, c3, c4 = st.columns(4)
c1.metric("True Net Worth", f"₹{net_worth:,.2f}", delta=f"{unrealized_pnl_pct:.2f}% Return")
c2.metric("Total Assets", f"₹{total_current_inr:,.2f}", f"₹{total_invested_inr:,.2f} Invested")
c3.metric("Total Debt", f"₹{total_liabilities:,.2f}", delta_color="inverse")
c4.metric("Annual Rental Income", f"₹{annual_rental_cashflow:,.2f}")

st.divider()

# Navigation Tabs
tab_ai, tab_port, tab_add, tab_debt, tab_sim, tab_share = st.tabs([
    "💬 AI CFO Copilot",
    "📊 Portfolio & Yields",
    "➕ Add Asset (Dynamic)",
    "💳 Liabilities & Debt",
    "🎯 8–10 Yr FIRE Simulator",
    "📲 Share & QR Code"
])

# TAB 1: AI COPILOT
with tab_ai:
    st.subheader("🤖 Autonomous AI Wealth Copilot")

    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "I am your AI CFO. I have live context on your bullion, real estate yields, stocks, mutual funds, and debt. What would you like to analyze or project today?"}
        ]

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    if query := st.chat_input("e.g. Analyze my asset allocation and suggest what to optimize:"):
        st.session_state.messages.append({"role": "user", "content": query})
        with st.chat_message("user"):
            st.markdown(query)

        with st.chat_message("assistant"):
            if not ai_ready:
                err_msg = "⚠️ Gemini API key not found in Streamlit Secrets. Please check your App Settings -> Secrets."
                st.warning(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
            else:
                with st.spinner("AI CFO analyzing your financial ledger..."):
                    context = f"""
                    You are an institutional Personal AI CFO.
                    Live FX: USD/INR = {USD_TO_INR}, AED/INR = {AED_TO_INR}
                    User Portfolio Snapshot:
                    - True Net Worth: INR {net_worth:,.2f}
                    - Total Assets: INR {total_current_inr:,.2f}
                    - Total Invested: INR {total_invested_inr:,.2f}
                    - Unrealized Gain/Loss: INR {unrealized_pnl:,.2f} ({unrealized_pnl_pct:.2f}%)
                    - Total Debt: INR {total_liabilities:,.2f}
                    - Annual Rental Cash Flow: INR {annual_rental_cashflow:,.2f}
                    - Holdings Breakdown: {assets_df.to_dict(orient='records') if not assets_df.empty else 'No assets recorded.'}
                    - Debt Breakdown: {liabs_raw.to_dict(orient='records') if not liabs_raw.empty else 'No debt active.'}
                    """
                    
                    full_prompt = f"{context}\n\nUser Question: {query}"
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
                            response_text = f"API Resolution Error: {str(list_err)}"

                    if success:
                        st.markdown(response_text)
                        st.session_state.messages.append({"role": "assistant", "content": response_text})
                    else:
                        err_out = "❌ Could not initialize an active Gemini model. Please check your API key at aistudio.google.com."
                        st.error(err_out)
                        st.session_state.messages.append({"role": "assistant", "content": err_out})

# TAB 2: PORTFOLIO & YIELDS
with tab_port:
    if not assets_df.empty:
        col1, col2 = st.columns([1.2, 1])
        with col1:
            fig_alloc = px.pie(assets_df, values="Current Value (INR)", names="Category", hole=0.5, title="Asset Allocation Breakdown")
            st.plotly_chart(fig_alloc, use_container_width=True)
        with col2:
            fig_bar = px.bar(assets_df, x="Category", y="Current Value (INR)", color="Category", title="Capital by Asset Class")
            st.plotly_chart(fig_bar, use_container_width=True)

        st.subheader("Asset Holdings Ledger")
        st.dataframe(assets_df, use_container_width=True, hide_index=True)

        del_id = st.number_input("Delete Holding by ID", min_value=1, step=1)
        if st.button("Delete Entry"):
            cursor.execute("DELETE FROM assets WHERE id = ? AND user_id = ?", (del_id, uid))
            conn.commit()
            st.success("Entry removed.")
            st.rerun()
    else:
        st.info("No assets configured. Use the 'Add Asset' tab to initialize your portfolio.")

# TAB 3: DYNAMIC ASSET ENGINE
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

        elif cat == "Mutual Funds":
            sub_type = "Mutual Fund Direct"
            identifier = st.text_input("AMFI Scheme Code (e.g. 122639 for Parag Parikh Flexi Cap)")
            qty = st.number_input("Units Held", min_value=0.001, step=1.0, format="%.3f")
            buy_price = st.number_input(f"Average Buy NAV ({cur})", min_value=0.01, step=1.0)
            curr_price = buy_price
            monthly_rent = 0.0
            p_year = current_year
            unit = "units"

        elif cat == "Indian Equities (NSE/BSE)":
            sub_type = "Equity Stock"
            identifier = st.text_input("Yahoo Ticker (e.g. RELIANCE.NS, TCS.NS, ARVSMART.NS)")
            qty = st.number_input("Shares Quantity", min_value=1.0, step=1.0)
            buy_price = st.number_input(f"Average Buy Price per Share ({cur})", min_value=0.1, step=1.0)
            curr_price = buy_price
            monthly_rent = 0.0
            p_year = current_year
            unit = "shares"

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
            st.success(f"{name_input} recorded.")
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

# TAB 5: DYNAMIC FIRE & GOAL-BASED SIMULATOR
with tab_sim:
    st.subheader("🎯 Dynamic FIRE & Goal-Adjusted Wealth Engine")
    st.caption("Calculate your exact Financial Independence number with custom inflation, withdrawal rates, and intermediate milestone goals.")

    col_f1, col_f2, col_f3 = st.columns(3)
    current_age = col_f1.number_input("Current Age", min_value=18, max_value=80, value=35, step=1)
    target_fire_age = col_f2.number_input("Target Retirement / FIRE Age", min_value=current_age + 1, max_value=90, value=50, step=1)
    monthly_living_exp = col_f3.number_input("Current Monthly Expenses (INR)", min_value=10000.0, value=75000.0, step=5000.0)

    col_p1, col_p2, col_p3 = st.columns(3)
    monthly_sip_alloc = col_p1.number_input("Monthly Investment SIP (INR)", min_value=0.0, value=50000.0, step=5000.0)
    expected_cagr = col_p2.slider("Expected Pre-Retirement CAGR (%)", 6.0, 18.0, 12.0, 0.5)
    inflation_rate = col_p3.slider("Annual Inflation Rate (%)", 3.0, 10.0, 6.0, 0.5)

    col_swr1, col_swr2 = st.columns(2)
    swr_pct = col_swr1.slider("Safe Withdrawal Rate (SWR %)", 2.5, 5.0, 4.0, 0.1, help="4% = 25x rule, 3.3% = 30x conservative rule")
    years_to_fire = target_fire_age - current_age

    st.markdown("#### 🚩 Intermediate Capital Outflows / Goals")
    st.caption("Add milestone deductions (e.g., buying real estate, children's higher education, car purchase) to evaluate timeline impact.")

    with st.expander("➕ Configure Milestone Goals"):
        col_g1, col_g2, col_g3 = st.columns(3)
        goal_1_name = col_g1.text_input("Goal 1 Name", value="Real Estate Down Payment")
        goal_1_years = col_g2.number_input("Occurs in (Years from now)", min_value=1, max_value=max(1, years_to_fire), value=min(4, max(1, years_to_fire)))
        goal_1_amount = col_g3.number_input("Goal 1 Outflow (INR)", min_value=0.0, value=2500000.0, step=100000.0)

        col_g4, col_g5, col_g6 = st.columns(3)
        goal_2_name = col_g4.text_input("Goal 2 Name", value="Higher Education / Wedding")
        goal_2_years = col_g5.number_input("Occurs in (Years from now)", min_value=1, max_value=max(1, years_to_fire), value=min(8, max(1, years_to_fire)))
        goal_2_amount = col_g6.number_input("Goal 2 Outflow (INR)", min_value=0.0, value=1500000.0, step=100000.0)

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
    m1.metric("Projected Corpus at Age " + str(target_fire_age), f"₹{final_corpus:,.2f}")
    m2.metric("Target FIRE Number", f"₹{target_fire_corpus:,.2f}", help="Based on inflated future expenses and your chosen SWR")
    m3.metric("Corpus Surplus / Shortfall", f"₹{corpus_delta:,.2f}", delta=f"{'Surplus (Ready to FIRE)' if corpus_delta >= 0 else 'Shortfall'}")

    if not sim_df.empty:
        fig_fire = go.Figure()
        fig_fire.add_trace(go.Scatter(x=sim_df["Age"], y=sim_df["Projected Wealth (INR)"], mode='lines+markers', name='Projected Portfolio Value', line=dict(color='#38BDF8', width=3)))
        fig_fire.add_trace(go.Scatter(x=sim_df["Age"], y=sim_df["Required FIRE Corpus (INR)"], mode='lines', name='Required FIRE Threshold', line=dict(color='#F43F5E', width=2, dash='dash')))
        fig_fire.update_layout(title="Wealth Accumulation vs. Inflation-Adjusted FIRE Requirement", xaxis_title="Age", yaxis_title="INR (₹)", hovermode="x unified")
        st.plotly_chart(fig_fire, use_container_width=True)

    if corpus_delta >= 0:
        st.success(f"🎉 **On Track:** At age {target_fire_age}, your projected portfolio (₹{final_corpus:,.2f}) covers your estimated annual living expense of ₹{future_annual_exp:,.2f} indefinitely at a {swr_pct}% withdrawal rate.")
    else:
        n = max(1, total_months)
        r = monthly_r
        future_val_existing = total_current_inr * ((1 + r) ** n)
        remaining_gap = max(0.0, target_fire_corpus - future_val_existing + (goal_1_amount + goal_2_amount))
        required_monthly_sip = remaining_gap * (r / (((1 + r) ** n) - 1)) if r > 0 else (remaining_gap / n)
        
        st.warning(f"⚠️ **Gap Identified:** You have a projected shortfall of ₹{abs(corpus_delta):,.2f}. To reach FIRE by age {target_fire_age} while funding your goals, consider increasing your monthly investment allocation to **₹{required_monthly_sip:,.2f} / month**.")

# TAB 6: SHARE & QR CODE
with tab_share:
    st.subheader("📲 Share VaultCFO")
    st.caption("Generate dynamic QR codes and direct links to share your application.")
    
    app_url = st.text_input("Application Web Link", value="https://vaultcfoai.streamlit.app/")
    
    col_qr1, col_qr2 = st.columns([1, 2])
    with col_qr1:
        qr_bytes = generate_qr_image(app_url)
        st.image(qr_bytes, caption="Scan to open VaultCFO on mobile", width=220)
        st.download_button(
            label="📥 Download QR Code PNG",
            data=qr_bytes,
            file_name="vaultcfo_qr.png",
            mime="image/png"
        )
    with col_qr2:
        st.markdown(f"""
        **Direct Link:** [{app_url}]({app_url})
        
        * **Mobile Access:** Open camera and scan this code to access your portfolio on iOS/Android.
        * **PWA Setup:** In Safari/Chrome on mobile, tap **Share** $\rightarrow$ **Add to Home Screen** to install it like a native app.
        """)
