import sqlite3
import hashlib
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Personal AI CFO Enterprise", layout="wide", page_icon="🏛️")

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
    identifier TEXT, -- Ticker or AMFI Scheme Code
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

# ----------------- LIVE MARKET DATA ENGINES -----------------
AED_TO_INR = 22.85
USD_TO_INR = 86.50

@st.cache_data(ttl=600)
def fetch_mf_nav(scheme_code):
    """Fetches live NAV from AMFI via MFAPI."""
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
    """Fetches live equity/commodity price via Yahoo Finance."""
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

# ----------------- AUTHENTICATION MODULE -----------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.username = ""

def auth_screen():
    st.title("🏛️ Personal AI CFO — Institutional Wealth Platform")
    st.caption("Kuvera & INDmoney-grade asset valuation with bank-grade local session isolation.")
    tab_log, tab_reg = st.tabs(["Secure Login", "Open Private Account"])
    
    with tab_log:
        u = st.text_input("Username", key="login_u")
        p = st.text_input("Password", type="password", key="login_p")
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
        ru = st.text_input("Create Username", key="reg_u")
        rp = st.text_input("Create Password", type="password", key="reg_p")
        if st.button("Create Account", use_container_width=True):
            if ru and rp:
                try:
                    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (ru, hash_pw(rp)))
                    conn.commit()
                    st.success("Account initialized! Please log in.")
                except sqlite3.IntegrityError:
                    st.error("Username already registered.")

if not st.session_state.authenticated:
    auth_screen()
    st.stop()

# ----------------- LOGGED IN DASHBOARD -----------------
uid = st.session_state.user_id

with st.sidebar:
    st.title(f"👤 {st.session_state.username}")
    if st.button("Logout", use_container_width=True):
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.rerun()
    st.divider()
    st.caption("Live Benchmarks:")
    st.caption(f"• USD/INR: ₹{USD_TO_INR}")
    st.caption(f"• AED/INR: ₹{AED_TO_INR}")

# --- DATA FETCHING & LIVE VALUATION ---
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

    # Live Mutual Fund Valuation (AMFI)
    if row["category"] == "Mutual Funds" and row["identifier"]:
        live_nav, scheme_name = fetch_mf_nav(row["identifier"])
        if live_nav:
            current_unit_p = live_nav
            if scheme_name:
                asset_title = scheme_name

    # Live Stock Valuation (NSE / BSE / US)
    elif row["category"] in ["Indian Equities (NSE/BSE)", "US Equities"] and row["identifier"]:
        live_p = fetch_live_market_price(row["identifier"])
        if live_p > 0:
            current_unit_p = live_p

    # Fixed Deposits / EPF / PPF Compounding Accrual
    elif row["category"] in ["Fixed Deposit", "EPF / PPF / Sukanya"]:
        rate = row["interest_rate"] or 7.0
        current_unit_p = buy_p * (1 + (rate / 100)) # 1-year annualized projection
    
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

# ----------------- TOP KPIS -----------------
st.title("💼 Enterprise Wealth & AI CFO Dashboard")

c1, c2, c3, c4 = st.columns(4)
c1.metric("True Net Worth", f"₹{net_worth:,.2f}", delta=f"{unrealized_pnl_pct:.2f}% Overall Return")
c2.metric("Total Asset Value", f"₹{total_current_inr:,.2f}", f"₹{total_invested_inr:,.2f} Invested")
c3.metric("Total Liabilities", f"₹{total_liabilities:,.2f}", delta_color="inverse")
c4.metric("Unrealized Profit/Loss", f"₹{unrealized_pnl:,.2f}", f"{unrealized_pnl_pct:.2f}%")

st.divider()

# ----------------- PLATFORM TABS -----------------
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Portfolio & Analytics",
    "➕ Add Assets (All Classes)",
    "💳 Liabilities & Debt",
    "🎯 8–10 Year Wealth & Goal Simulator",
    "📥 Statement Parser"
])

# TAB 1: PORTFOLIO & ANALYTICS
with tab1:
    if not assets_df.empty:
        col_g1, col_g2 = st.columns([1.2, 1])
        with col_g1:
            fig_alloc = px.pie(assets_df, values="Current Value (INR)", names="Category", hole=0.5, title="Asset Allocation Breakdown")
            st.plotly_chart(fig_alloc, use_container_width=True)
        with col_g2:
            fig_pnl = px.bar(assets_df, x="Category", y="P&L (INR)", color="P&L (INR)", color_continuous_scale="Temps", title="Unrealized Gain/Loss by Class")
            st.plotly_chart(fig_pnl, use_container_width=True)

        st.subheader("Asset Holdings Table")
        st.dataframe(
            assets_df[["ID", "Name", "Category", "Holdings", "Buy Price", "Current Price", "Current Value (INR)", "P&L (%)"]],
            use_container_width=True,
            hide_index=True
        )

        del_id = st.number_input("Delete Holding Entry by ID", min_value=1, step=1)
        if st.button("Delete Entry"):
            cursor.execute("DELETE FROM assets WHERE id = ? AND user_id = ?", (del_id, uid))
            conn.commit()
            st.success("Entry removed.")
            st.rerun()
    else:
        st.info("No assets configured. Use the 'Add Assets' tab to initialize your portfolio.")

# TAB 2: MULTI-ASSET CREATION ENGINE
with tab2:
    st.subheader("Add Asset Across Any Financial Class")
    cat = st.selectbox("Select Asset Category", [
        "Mutual Funds",
        "Indian Equities (NSE/BSE)",
        "Bullion (Gold/Silver)",
        "Fixed Deposit",
        "EPF / PPF / Sukanya",
        "US Equities",
        "Savings / Liquid Cash",
        "Real Estate"
    ])

    cur = st.radio("Currency Denomination", ["INR", "AED", "USD"], horizontal=True)

    with st.form("asset_creation_form"):
        name_input = st.text_input("Asset Label / Platform Name (e.g. Parag Parikh Flexi Cap, Ogold, Zerodha, HDFC Bank)")
        
        if cat == "Mutual Funds":
            st.caption("💡 Enter the AMFI Scheme Code for automated daily NAV tracking (e.g. 122639 for Parag Parikh Flexi Cap).")
            identifier = st.text_input("AMFI Scheme Code (6 digits)")
            qty = st.number_input("Total Units Held", min_value=0.001, step=1.0, format="%.3f")
            buy_p = st.number_input("Average Purchase NAV", min_value=0.01, step=1.0)
            ir = 0.0
            unit = "units"

        elif cat == "Indian Equities (NSE/BSE)":
            st.caption("💡 Add Yahoo Ticker: e.g. RELIANCE.NS, ARVSMART.NS, TCS.NS")
            identifier = st.text_input("NSE/BSE Ticker")
            qty = st.number_input("Number of Shares", min_value=1.0, step=1.0)
            buy_p = st.number_input("Average Buy Price per Share", min_value=0.1, step=1.0)
            ir = 0.0
            unit = "shares"

        elif cat == "Bullion (Gold/Silver)":
            metal = st.selectbox("Metal", ["Gold 24K", "Silver"])
            identifier = "GC=F" if "Gold" in metal else "SI=F"
            qty = st.number_input("Total Grams", min_value=0.0001, step=1.0, format="%.4f")
            buy_p = st.number_input(f"Purchase Price per Gram ({cur})", min_value=0.1, step=10.0)
            ir = 0.0
            unit = "grams"

        elif cat in ["Fixed Deposit", "EPF / PPF / Sukanya"]:
            identifier = ""
            qty = 1.0
            buy_p = st.number_input(f"Principal Deposit Amount ({cur})", min_value=100.0, step=5000.0)
            ir = st.number_input("Annual Interest Rate (%)", min_value=1.0, value=7.1, step=0.1)
            unit = "deposit"

        else:
            identifier = ""
            qty = 1.0
            buy_p = st.number_input(f"Current Estimated Value / Cash Balance ({cur})", min_value=1.0, step=10000.0)
            ir = 0.0
            unit = "lump_sum"

        if st.form_submit_button("Add Asset to Portfolio", use_container_width=True):
            cursor.execute(
                "INSERT INTO assets (user_id, name, category, identifier, quantity, unit, buy_price, interest_rate, currency) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (uid, name_input, cat, identifier, qty, unit, buy_p, ir, cur)
            )
            conn.commit()
            st.success("Asset added to institutional ledger.")
            st.rerun()

# TAB 3: LIABILITIES & DEBT TRACKER
with tab3:
    st.subheader("Liabilities, Loans & EMIs")
    with st.form("liability_form"):
        l_name = st.text_input("Liability Name (e.g. Home Loan HDFC, Auto Loan, Credit Card)")
        l_cat = st.selectbox("Category", ["Home Loan", "Vehicle Loan", "Personal Loan", "Credit Card Debt", "Builder Installment Plan"])
        l_prin = st.number_input("Principal Outstanding Balance (INR)", min_value=0.0, step=25000.0)
        l_rate = st.number_input("Interest Rate (%)", min_value=0.0, value=8.5, step=0.1)
        l_emi = st.number_input("Monthly EMI Amount (INR)", min_value=0.0, step=1000.0)
        
        if st.form_submit_button("Record Liability", use_container_width=True):
            cursor.execute(
                "INSERT INTO liabilities (user_id, name, category, principal_outstanding, interest_rate, monthly_emi) VALUES (?, ?, ?, ?, ?, ?)",
                (uid, l_name, l_cat, l_prin, l_rate, l_emi)
            )
            conn.commit()
            st.success("Liability updated.")
            st.rerun()

    if not liabs_raw.empty:
        st.dataframe(liabs_raw[["id", "name", "category", "principal_outstanding", "interest_rate", "monthly_emi"]], use_container_width=True)

# TAB 4: 8-10 YEAR WEALTH & GOAL SIMULATOR
with tab4:
    st.subheader("🎯 Long-Term Wealth Projection Engine")
    st.caption("Simulate portfolio compounding across an 8–10 year horizon for targeted milestones.")

    col_s1, col_s2, col_s3 = st.columns(3)
    monthly_sip = col_s1.number_input("Monthly Portfolio Addition (INR)", value=50000, step=5000)
    expected_cagr = col_s2.slider("Expected Portfolio CAGR (%)", 6.0, 20.0, 12.0, 0.5)
    horizon_years = col_s3.slider("Time Horizon (Years)", 3, 20, 10)

    # Compounding Calculation
    months = horizon_years * 12
    monthly_rate = (expected_cagr / 100) / 12
    
    projection_data = []
    current_running_val = total_current_inr

    for m in range(1, months + 1):
        current_running_val = (current_running_val + monthly_sip) * (1 + monthly_rate)
        if m % 12 == 0:
            projection_data.append({
                "Year": m // 12,
                "Projected Wealth (INR)": round(current_running_val, 2)
            })

    proj_df = pd.DataFrame(projection_data)
    fig_proj = px.line(proj_df, x="Year", y="Projected Wealth (INR)", markers=True, title=f"Projected Net Worth Over {horizon_years} Years (@ {expected_cagr}% CAGR)")
    st.plotly_chart(fig_proj, use_container_width=True)

    if not proj_df.empty:
        final_val = proj_df.iloc[-1]["Projected Wealth (INR)"]
        st.success(f"Estimated Corpus at Year {horizon_years}: **₹{final_val:,.2f} INR**")

# TAB 5: STATEMENT PARSER
with tab5:
    st.subheader("Automated Statement & Expense Analyzer")
    csv_file = st.file_uploader("Upload Bank/Credit Card Statement CSV", type=["csv"])
    if csv_file and st.button("Parse Transactions"):
        tdf = pd.read_csv(csv_file)
        tdf["user_id"] = uid
        tdf.to_sql("transactions", conn, if_exists="append", index=False)
        st.success(f"Parsed {len(tdf)} records.")
        st.rerun()

    if not trans_raw.empty:
        st.dataframe(trans_raw[["date", "description", "category", "amount", "type"]], use_container_width=True)
