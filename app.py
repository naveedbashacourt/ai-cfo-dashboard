import sqlite3
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Personal AI CFO", layout="wide", page_icon="💼")

# Connect to database
conn = sqlite3.connect("finances.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    category TEXT,
    quantity REAL,
    unit TEXT,
    unit_price REAL,
    currency TEXT,
    total_inr REAL
)
""")
cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date DATE,
    description TEXT,
    category TEXT,
    amount REAL,
    type TEXT
)
""")
conn.commit()

# Default Exchange Rate & Commodity Benchmarks
AED_TO_INR = 22.80

def calculate_inr(quantity, unit_price, currency):
    val = quantity * unit_price
    return val * AED_TO_INR if currency == "AED" else val

st.title("💼 Personal AI CFO Dashboard")

# ----------------- TOP METRICS -----------------
assets_df = pd.read_sql("SELECT * FROM assets", conn)
trans_df = pd.read_sql("SELECT * FROM transactions", conn)

total_net_worth = assets_df["total_inr"].sum() if not assets_df.empty else 0.0

if not trans_df.empty and "type" in trans_df.columns:
    debits = trans_df[trans_df["type"] == "DEBIT"]
    unique_months = max(1, len(trans_df["date"].astype(str).str.slice(0, 7).unique()))
    monthly_burn = debits["amount"].sum() / unique_months
else:
    monthly_burn = 0.0

# Liquid assets: Cash, Bank, Bullion (instant redeem)
liquid_categories = ["Savings/Bank", "Bullion (Gold/Silver)", "Demat/Stocks/MF"]
liquid_assets = assets_df[assets_df["category"].isin(liquid_categories)]["total_inr"].sum() if not assets_df.empty else 0.0
runway = (liquid_assets / monthly_burn) if monthly_burn > 0 else 0.0

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Net Worth", f"₹{total_net_worth:,.2f}")
col2.metric("Liquid Capital", f"₹{liquid_assets:,.2f}")
col3.metric("Est. Monthly Burn", f"₹{monthly_burn:,.2f}")
col4.metric("Cash Runway", f"{runway:.1f} Months" if monthly_burn > 0 else "N/A")

st.divider()

# ----------------- MAIN LAYOUT -----------------
col_left, col_right = st.columns([1, 1.2])

with col_left:
    st.subheader("➕ Add / Manage Assets")
    
    category = st.selectbox(
        "Asset Category",
        ["Bullion (Gold/Silver)", "Demat/Stocks/MF", "Savings/Bank", "Real Estate", "Other"]
    )
    
    name = st.text_input("Asset Name / Platform (e.g. Ogold 24k, Islamicly Gold, HDFC, Zerodha)")
    currency = st.radio("Currency", ["INR (₹)", "AED (Dhs)"], horizontal=True)
    curr_code = "AED" if "AED" in currency else "INR"

    if category == "Bullion (Gold/Silver)":
        metal_type = st.selectbox("Metal", ["Gold", "Silver"])
        default_price = 7200.0 if metal_type == "Gold" else 88.0
        if curr_code == "AED":
            default_price = default_price / AED_TO_INR

        grams = st.number_input("Quantity (in Grams)", min_value=0.0001, step=1.0, format="%.4f")
        price_per_g = st.number_input(f"Price per Gram ({curr_code})", min_value=0.1, value=float(default_price), step=1.0)
        
        calculated_total = calculate_inr(grams, price_per_g, curr_code)
        st.info(f"Asset Value: {curr_code} {grams * price_per_g:,.2f} | **₹{calculated_total:,.2f} INR**")

        if st.button("Save Bullion Asset", use_container_width=True):
            cursor.execute(
                "INSERT INTO assets (name, category, quantity, unit, unit_price, currency, total_inr) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"{name} ({metal_type})", category, grams, "grams", price_per_g, curr_code, calculated_total)
            )
            conn.commit()
            st.rerun()

    elif category == "Demat/Stocks/MF":
        units = st.number_input("Quantity / Units", min_value=0.001, step=1.0, format="%.3f")
        nav_price = st.number_input(f"Current Price / NAV ({curr_code})", min_value=0.1, step=1.0)
        calculated_total = calculate_inr(units, nav_price, curr_code)
        st.info(f"Asset Value: {curr_code} {units * nav_price:,.2f} | **₹{calculated_total:,.2f} INR**")

        if st.button("Save Equity/MF Asset", use_container_width=True):
            cursor.execute(
                "INSERT INTO assets (name, category, quantity, unit, unit_price, currency, total_inr) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, category, units, "units", nav_price, curr_code, calculated_total)
            )
            conn.commit()
            st.rerun()

    else:
        # Cash, Real Estate, Lump Sum
        amount = st.number_input(f"Total Amount ({curr_code})", min_value=0.0, step=5000.0)
        calculated_total = amount * (AED_TO_INR if curr_code == "AED" else 1.0)
        st.info(f"Asset Value: **₹{calculated_total:,.2f} INR**")

        if st.button("Save Asset", use_container_width=True):
            cursor.execute(
                "INSERT INTO assets (name, category, quantity, unit, unit_price, currency, total_inr) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (name, category, 1, "lump_sum", amount, curr_code, calculated_total)
            )
            conn.commit()
            st.rerun()

    st.divider()
    st.subheader("📥 Upload Statement (CSV)")
    uploaded_file = st.file_uploader("Drop Bank/Card CSV (date, description, category, amount, type)", type=["csv"])
    if uploaded_file and st.button("Process & Import CSV", use_container_width=True):
        df = pd.read_csv(uploaded_file)
        df.to_sql("transactions", conn, if_exists="append", index=False)
        st.success(f"Loaded {len(df)} transactions successfully.")
        st.rerun()

with col_right:
    st.subheader("📊 Portfolio Breakdown")
    if not assets_df.empty:
        # Asset table with formatted values
        display_df = assets_df.copy()
        display_df["Total (INR)"] = display_df["total_inr"].apply(lambda x: f"₹{x:,.2f}")
        display_df["Qty & Unit"] = display_df.apply(lambda r: f"{r['quantity']} {r['unit']}", axis=1)
        
        st.dataframe(
            display_df[["id", "name", "category", "Qty & Unit", "currency", "Total (INR)"]],
            use_container_width=True,
            hide_index=True
        )

        # Asset Category Chart
        cat_group = assets_df.groupby("category")["total_inr"].sum()
        st.bar_chart(cat_group)

        # Asset Deletion
        del_id = st.number_input("Enter Asset ID to remove incorrect entries:", min_value=1, step=1)
        if st.button("Delete Asset Entry"):
            cursor.execute("DELETE FROM assets WHERE id = ?", (del_id,))
            conn.commit()
            st.success(f"Asset #{del_id} removed.")
            st.rerun()
    else:
        st.info("No assets tracked yet. Add bullion, savings, or investments on the left.")

    st.subheader("💳 Expense Insights")
    if not trans_df.empty:
        cat_exp = trans_df[trans_df["type"] == "DEBIT"].groupby("category")["amount"].sum()
        st.bar_chart(cat_exp)
    else:
        st.caption("Upload debit transactions to generate spending charts.")
