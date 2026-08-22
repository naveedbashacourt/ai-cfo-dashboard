import sqlite3
import hashlib
import pandas as pd
import plotly.express as px
import streamlit as st
import yfinance as yf

st.set_page_config(page_title="Personal AI CFO Pro", layout="wide", page_icon="📈")

# ----------------- DATABASE INITIALIZATION -----------------
conn = sqlite3.connect("cfo_platform.db", check_same_thread=False)
cursor = conn.cursor()

# Users Table
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE,
    password_hash TEXT
)
""")

# Assets Table linked to user_id
cursor.execute("""
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    name TEXT,
    category TEXT,
    ticker TEXT,
    quantity REAL,
    unit TEXT,
    buy_price REAL,
    current_price REAL,
    currency TEXT,
    total_inr REAL,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
""")

# Transactions Table linked to user_id
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

# ----------------- HELPER FUNCTIONS -----------------
AED_TO_INR = 22.80

def hash_pw(password):
    return hashlib.sha256(password.encode()).hexdigest()

def get_live_asset_price(ticker, default_price):
    if not ticker:
        return default_price
    try:
        data = yf.Ticker(ticker)
        todays_data = data.history(period='1d')
        if not todays_data.empty:
            return round(float(todays_data['Close'].iloc[-1]), 2)
    except Exception:
        pass
    return default_price

# ----------------- AUTHENTICATION MODULE -----------------
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.user_id = None
    st.session_state.username = ""

def login_register_page():
    st.title("🔒 Personal AI CFO — Sign In / Register")
    st.caption("All financial data is private and encrypted to your individual account.")
    
    tab1, tab2 = st.tabs(["Login", "Create Account"])
    
    with tab1:
        u_login = st.text_input("Username", key="login_u")
        p_login = st.text_input("Password", type="password", key="login_p")
        if st.button("Log In", use_container_width=True):
            cursor.execute("SELECT id FROM users WHERE username = ? AND password_hash = ?", (u_login, hash_pw(p_login)))
            res = cursor.fetchone()
            if res:
                st.session_state.authenticated = True
                st.session_state.user_id = res[0]
                st.session_state.username = u_login
                st.rerun()
            else:
                st.error("Invalid username or password.")

    with tab2:
        u_reg = st.text_input("Choose Username", key="reg_u")
        p_reg = st.text_input("Choose Password", type="password", key="reg_p")
        if st.button("Register Account", use_container_width=True):
            if u_reg and p_reg:
                try:
                    cursor.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (u_reg, hash_pw(p_reg)))
                    conn.commit()
                    st.success("Account created successfully! You can now log in.")
                except sqlite3.IntegrityError:
                    st.error("Username already taken.")
            else:
                st.warning("Please fill in both fields.")

if not st.session_state.authenticated:
    login_register_page()
    st.stop()

# ----------------- MAIN APP (AUTHENTICATED) -----------------
user_id = st.session_state.user_id

with st.sidebar:
    st.write(f"Logged in as: **{st.session_state.username}**")
    if st.button("Logout"):
        st.session_state.authenticated = False
        st.session_state.user_id = None
        st.rerun()

st.title("💼 Personal AI CFO Dashboard")

# Fetch User-Specific Data
assets_df = pd.read_sql(f"SELECT * FROM assets WHERE user_id = {user_id}", conn)
trans_df = pd.read_sql(f"SELECT * FROM transactions WHERE user_id = {user_id}", conn)

# Recalculate Live Net Worth
if not assets_df.empty:
    for idx, row in assets_df.iterrows():
        if row['ticker']:
            live_price = get_live_asset_price(row['ticker'], row['current_price'])
            unit_val = live_price if live_price > 0 else row['current_price']
            total = (row['quantity'] * unit_val) * (AED_TO_INR if row['currency'] == 'AED' else 1.0)
            assets_df.at[idx, 'current_price'] = unit_val
            assets_df.at[idx, 'total_inr'] = total

total_net_worth = assets_df["total_inr"].sum() if not assets_df.empty else 0.0

# Calculate Burn Rate and Runway
if not trans_df.empty and "type" in trans_df.columns:
    debits = trans_df[trans_df["type"] == "DEBIT"]
    unique_months = max(1, len(trans_df["date"].astype(str).str.slice(0, 7).unique()))
    monthly_burn = debits["amount"].sum() / unique_months
else:
    monthly_burn = 0.0

liquid_cats = ["Savings/Bank", "Bullion (Gold/Silver)", "Stocks / Demat", "Mutual Funds"]
liquid_assets = assets_df[assets_df["category"].isin(liquid_cats)]["total_inr"].sum() if not assets_df.empty else 0.0
runway = (liquid_assets / monthly_burn) if monthly_burn > 0 else 0.0

# ----------------- TOP METRIC TILES -----------------
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Net Worth", f"₹{total_net_worth:,.2f}")
col2.metric("Liquid Capital", f"₹{liquid_assets:,.2f}")
col3.metric("Est. Monthly Burn", f"₹{monthly_burn:,.2f}")
col4.metric("Emergency Runway", f"{runway:.1f} Months" if monthly_burn > 0 else "N/A")

st.divider()

# ----------------- MAIN LAYOUT -----------------
col_left, col_right = st.columns([1, 1.2])

with col_left:
    st.subheader("➕ Add New Asset")
    category = st.selectbox(
        "Asset Class",
        ["Bullion (Gold/Silver)", "Stocks / Demat", "Mutual Funds", "Savings/Bank", "Fixed Deposit", "Real Estate"]
    )
    
    name = st.text_input("Asset Label / Institution (e.g., Ogold, Zerodha, HDFC, Emaar)")
    currency = st.radio("Base Currency", ["INR (₹)", "AED (Dhs)"], horizontal=True)
    curr_code = "AED" if "AED" in currency else "INR"

    if category == "Bullion (Gold/Silver)":
        metal = st.selectbox("Metal Type", ["Gold (24K)", "Silver"])
        grams = st.number_input("Weight in Grams", min_value=0.001, step=1.0, format="%.4f")
        price_g = st.number_input(f"Price per Gram ({curr_code})", min_value=0.1, value=7200.0 if "Gold" in metal else 88.0)
        total_val = (grams * price_g) * (AED_TO_INR if curr_code == "AED" else 1.0)
        
        if st.button("Save Bullion Entry", use_container_width=True):
            cursor.execute(
                "INSERT INTO assets (user_id, name, category, ticker, quantity, unit, buy_price, current_price, currency, total_inr) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, f"{name} ({metal})", category, "", grams, "grams", price_g, price_g, curr_code, total_val)
            )
            conn.commit()
            st.rerun()

    elif category in ["Stocks / Demat", "Mutual Funds"]:
        ticker = st.text_input("Yahoo Finance Ticker (optional for live price, e.g. RELIANCE.NS, INFOSYS.BO)")
        units = st.number_input("Shares / NAV Units", min_value=0.001, step=1.0, format="%.3f")
        price = st.number_input(f"Purchase Price / NAV ({curr_code})", min_value=0.1, step=10.0)
        total_val = (units * price) * (AED_TO_INR if curr_code == "AED" else 1.0)

        if st.button("Save Investment Entry", use_container_width=True):
            cursor.execute(
                "INSERT INTO assets (user_id, name, category, ticker, quantity, unit, buy_price, current_price, currency, total_inr) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, name, category, ticker, units, "units", price, price, curr_code, total_val)
            )
            conn.commit()
            st.rerun()

    else:
        amount = st.number_input(f"Total Value / Balance ({curr_code})", min_value=0.0, step=5000.0)
        total_val = amount * (AED_TO_INR if curr_code == "AED" else 1.0)

        if st.button("Save Asset Entry", use_container_width=True):
            cursor.execute(
                "INSERT INTO assets (user_id, name, category, ticker, quantity, unit, buy_price, current_price, currency, total_inr) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (user_id, name, category, "", 1, "lump_sum", amount, amount, curr_code, total_val)
            )
            conn.commit()
            st.rerun()

    st.divider()
    st.subheader("📥 Upload Statement (CSV)")
    uploaded_file = st.file_uploader("Upload Bank or Card CSV", type=["csv"])
    if uploaded_file and st.button("Parse & Import Transactions", use_container_width=True):
        df = pd.read_csv(uploaded_file)
        df['user_id'] = user_id
        df.to_sql("transactions", conn, if_exists="append", index=False)
        st.success("Transactions loaded into your private ledger.")
        st.rerun()

with col_right:
    st.subheader("📊 Portfolio Breakdown")
    if not assets_df.empty:
        # Donut Chart for Asset Allocation
        fig = px.pie(assets_df, values="total_inr", names="category", hole=0.45, title="Asset Allocation Breakdown")
        fig.update_layout(margin=dict(t=30, b=0, l=0, r=0))
        st.plotly_chart(fig, use_container_width=True)

        # Asset Table
        display_df = assets_df.copy()
        display_df["Total (INR)"] = display_df["total_inr"].apply(lambda x: f"₹{x:,.2f}")
        display_df["Holding"] = display_df.apply(lambda r: f"{r['quantity']} {r['unit']}", axis=1)
        st.dataframe(
            display_df[["id", "name", "category", "Holding", "currency", "Total (INR)"]],
            use_container_width=True,
            hide_index=True
        )

        del_id = st.number_input("Remove Entry by ID", min_value=1, step=1)
        if st.button("Delete Entry"):
            cursor.execute("DELETE FROM assets WHERE id = ? AND user_id = ?", (del_id, user_id))
            conn.commit()
            st.success("Asset removed.")
            st.rerun()
    else:
        st.info("No assets tracked yet. Add bullion, equities, or accounts on the left.")

    st.subheader("💳 Expense Insights")
    if not trans_df.empty:
        cat_exp = trans_df[trans_df["type"] == "DEBIT"].groupby("category")["amount"].sum().reset_index()
        fig_bar = px.bar(cat_exp, x="category", y="amount", title="Spending by Category (INR)")
        st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.caption("Upload debit transactions to generate spending charts.")
