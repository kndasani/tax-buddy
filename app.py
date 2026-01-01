import streamlit as st
import google.generativeai as genai
import os
import time
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv()
st.set_page_config(
    page_title="TaxGuide AI", 
    page_icon="🇮🇳", 
    layout="centered",
    initial_sidebar_state="collapsed" # Hide sidebar by default
)

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except:
        st.error("🔑 API Key Missing.")
        st.stop()

genai.configure(api_key=api_key)

# --- 1. MOBILE CSS HACKS ---
# This block lifts the chat input and styles it for mobile
st.markdown("""
<style>
    /* 1. Lift the Chat Input Container */
    [data-testid="stChatInput"] {
        bottom: 40px !important; /* Lift it above nav bars */
        padding-bottom: 0px !important;
    }
    
    /* 2. Style the Input Box (The Bubble Look) */
    .stChatInputContainer textarea {
        border-radius: 25px !important; /* Round corners */
        border: 2px solid #ddd !important;
        font-size: 16px !important; /* Bigger text */
        padding: 12px !important;
        box-shadow: 0px 4px 10px rgba(0,0,0,0.1);
    }
    
    /* 3. Hide the default Streamlit footer/hamburger if desired */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* 4. Make the Send button bigger/easier to tap */
    button[data-testid="stChatInputSubmitButton"] {
        border-radius: 50% !important;
        width: 40px !important;
        height: 40px !important;
    }
</style>
""", unsafe_allow_html=True)

# --- 2. THE CALCULATOR ENGINE ---
def calculate_tax_logic(age, salary, business_income, rent_paid, inv_80c, med_80d):
    std_deduction_new = 75000 
    std_deduction_old = 50000
    
    # Business (44ADA - 50%)
    taxable_business = business_income * 0.50
    
    # Salary
    basic = salary * 0.50
    hra = max(0, rent_paid * 12 - (0.10 * basic))
    
    # Totals
    gross_old = (salary - std_deduction_old - hra) + taxable_business
    taxable_old = max(0, gross_old - min(inv_80c, 150000) - med_80d)
    taxable_new = max(0, (salary - std_deduction_new) + taxable_business)

    return compute_slabs(taxable_new, taxable_old, age)

def compute_slabs(inc_new, inc_old, age):
    # New Regime
    tax_new = 0
    t = inc_new
    if t > 2400000: tax_new += (t - 2400000) * 0.30; t = 2400000
    if t > 2000000: tax_new += (t - 2000000) * 0.25; t = 2000000
    if t > 1600000: tax_new += (t - 1600000) * 0.20; t = 1600000
    if t > 1200000: tax_new += (t - 1200000) * 0.15; t = 1200000
    if t > 800000:  tax_new += (t - 800000)  * 0.10; t = 800000
    if t > 400000:  tax_new += (t - 400000)  * 0.05
    if inc_new <= 1200000: tax_new = 0

    # Old Regime
    limit = 500000 if age >= 80 else (300000 if age >= 60 else 250000)