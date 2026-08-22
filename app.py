import sqlite3
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Personal AI CFO", layout="wide")

# Initialize Database
conn = sqlite3.connect("finances.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    account_type TEXT,
    balance REAL
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_name TEXT,
    date DATE,
    description TEXT,
    category TEXT,
    amount REAL,
    type TEXT
)
""")
conn.commit()

st.title("💼 Personal AI CFO Dashboard")

# Top KPI Row
accounts_df = pd.read_sql("SELECT * FROM accounts", conn)
total_assets = accounts_df["balance"].sum() if not accounts_df.empty else 0.0

trans_df = pd.read_sql("SELECT * FROM transactions", conn)
if not trans_df.empty and "type" in trans_df.columns:
    monthly_burn = trans_df[trans_df["type"] == "DEBIT"]["amount"].sum() / max(1, len(trans_df["date"].str.slice(0,7).unique()))
else:
    monthly_burn = 0.0

runway = (total_assets / monthly_burn) if monthly_burn > 0 else 0.0

col1, col2, col3 = st.columns(3)
col1.metric("Total Liquid Assets", f"₹{total_assets:,.2f}")
col2.metric("Est. Monthly Burn", f"₹{monthly_burn:,.2f}")
col3.metric("Cash Runway", f"{runway:.1f} Months")

st.divider()

# Left Column: Data Ingestion | Right Column: Analysis
left_col, right_col = st.columns([1, 1])

with left_col:
    st.subheader("1. Add Account Balance")
    with st.form("acc_form"):
        name = st.text_input("Account / Asset Name (e.g. HDFC, Gold, Demat)")
        acc_type = st.selectbox("Type", ["Savings", "Credit Card", "Demat/Equity", "Bullion", "Real Estate"])
        bal = st.number_input("Current Balance / Value", min_value=0.0, step=1000.0)
        if st.form_submit_button("Save Asset"):
            cursor.execute("INSERT INTO accounts (name, account_type, balance) VALUES (?, ?, ?)", (name, acc_type, bal))
            conn.commit()
            st.rerun()

    st.subheader("2. Upload Statement (CSV)")
    uploaded_file = st.file_uploader("Upload CSV (date, description, category, amount, type)", type=["csv"])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        if st.button("Import Transactions"):
            df.to_sql("transactions", conn, if_exists="append", index=False)
            st.success(f"Imported {len(df)} transactions successfully!")
            st.rerun()

with right_col:
    st.subheader("3. Portfolio Breakdown")
    if not accounts_df.empty:
        st.dataframe(accounts_df[["name", "account_type", "balance"]], use_container_width=True)
    else:
        st.info("No accounts added yet.")

    st.subheader("4. Expense Categories")
    if not trans_df.empty:
        cat_summary = trans_df[trans_df["type"] == "DEBIT"].groupby("category")["amount"].sum().reset_index()
        st.bar_chart(cat_summary.set_index("category"))
    else:
        st.info("Upload transactions to visualize spending.")
