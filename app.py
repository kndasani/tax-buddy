import streamlit as st
import google.generativeai as genai
import os
import time
from dotenv import load_dotenv

# --- 1. CONFIGURATION (MUST BE FIRST) ---
st.set_page_config(
    page_title="TaxGuide AI", 
    page_icon="🇮🇳", 
    layout="centered"
)

load_dotenv()

# --- 2. API KEY SETUP ---
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except:
        st.error("🔑 API Key Missing. Please set it in .env or Secrets.")
        st.stop()

genai.configure(api_key=api_key)

# --- 3. THE CALCULATOR ENGINE ---
def calculate_tax_logic(age, salary, business_income, rent_paid, inv_80c, med_80d):
    std_deduction_new = 75000 
    std_deduction_old = 50000
    
    # Business Income (44ADA - 50% Presumptive)
    taxable_business = business_income * 0.50
    
    # Salary Income
    basic = salary * 0.50
    hra = max(0, rent_paid * 12 - (0.10 * basic))
    
    # Net Taxable Income
    gross_old = (salary - std_deduction_old - hra) + taxable_business
    taxable_old = max(0, gross_old - min(inv_80c, 150000) - med_80d)
    taxable_new = max(0, (salary - std_deduction_new) + taxable_business)

    return compute_slabs(taxable_new, taxable_old, age)

def compute_slabs(inc_new, inc_old, age):
    # New Regime (FY 25-26)
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
    tax_old = 0
    t = inc_old
    if t > 1000000: tax_old += (t - 1000000) * 0.30; t = 1000000
    if t > 500000:  tax_old += (t - 500000)  * 0.20; t = 500000
    if t > limit:   tax_old += (t - limit)   * 0.05
    if inc_old <= 500000: tax_old = 0

    return int(tax_new * 1.04), int(tax_old * 1.04)

# --- 4. LOAD KNOWLEDGE ---
@st.cache_resource
def load_knowledge():
    library = []
    # Using 'try-except' to safely ignore missing files without crashing
    files = ["salary_rules.pdf", "freelancer_rules.pdf", "capital_gains.pdf"]
    for f_name in files:
        if os.path.exists(f_name):
            try:
                f = genai.upload_file(path=f_name, display_name=f_name)
                while f.state.name == "PROCESSING": time.sleep(1); f = genai.get_file(f.name)
                library.append(f)
            except: pass
    return library

pdf_library = load_knowledge()

# --- 5. BRAIN INSTRUCTIONS ---
sys_instruction = """
You are a smart, empathetic Tax Consultant. 
Your goal is to *discover* the user's tax situation through conversation.

**PHASE 1: DISCOVERY**
- Start by introducing yourself and asking: "To help you best, could you tell me how you earn your income? (e.g., Salary, Freelancing, Business, or a mix?)"

**PHASE 2: DEEP DIVE**
- Once you know the source, ask for numbers **ONE BY ONE**:
  1. Age (Mandatory)
  2. Income Amounts (Salary / Business Receipts)
  3. Rent Paid (if Salaried)
  4. Investments (80C, 80D)

**PHASE 3: CALCULATION TRIGGER**
- Once you have ALL numbers, output strictly:
  `CALCULATE(age=..., salary=..., business=..., rent=..., inv80c=..., med80d=...)`
"""

# --- 6. CHAT SESSION ---
if "chat_session" not in st.session_state:
    history = []
    if pdf_library:
        history.append({"role": "user", "parts": pdf_library + ["Here is your tax library."]})
        history.append({"role": "model", "parts": ["I have studied the library."]})
    
    # Use the stable model version
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction)
    st.session_state.chat_session = model.start_chat(history=history)

# --- 7. MOBILE-FRIENDLY HEADER ---
# We put the reset button at the top (Main Screen) so no sidebar is needed
col1, col2 = st.columns([4, 1])
with col1:
    st.markdown("### 🇮🇳 TaxGuide AI")
with col2:
    if st.button("🔄", help="Reset Chat"):
        st.session_state.chat_session = None
        st.rerun()

# --- 8. DISPLAY CHAT ---
# Skip the first 2 hidden messages (PDF injection)
start_idx = 2 if pdf_library else 0
for msg in st.session_state.chat_session.history[start_idx:]:
    role = "user" if msg.role == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(msg.parts[0].text)

# --- 9. INPUT HANDLING ---
if prompt := st.chat_input("Start typing..."):
    st.chat_message("user").markdown(prompt)
    
    with st.spinner("Thinking..."):
        try:
            response = st.session_state.chat_session.send_message(prompt)
            text = response.text
            
            if "CALCULATE(" in text:
                try:
                    params = text.split("CALCULATE(")[1].split(")")[0]
                    data = {"age":30, "salary":0, "business":0, "rent":0, "inv80c":0, "med80d":0}
                    for part in params.split(","):
                        if "=" in part:
                            key, val = part.split("=")
                            data[key.strip()] = int(val.strip())
                    
                    tn, to = calculate_tax_logic(
                        data['age'], data['salary'], data['business'], 
                        data['rent'], data['inv80c'], data['med80d']
                    )
                    
                    savings = abs(tn - to)
                    winner = "New Regime" if tn < to else "Old Regime"
                    
                    st.chat_message("assistant").markdown(f"""
                    ### 🧾 Tax Report
                    | Regime | Tax Payable |
                    | :--- | :--- |
                    | **New Regime** | **₹{tn:,}** |
                    | **Old Regime** | **₹{to:,}** |
                    
                    🏆 **Recommendation:** Go with **{winner}**.
                    You save **₹{savings:,}**!
                    """)
                    
                    st.session_state.chat_session.history.append({
                        "role": "model",
                        "parts": [f"Result shown: New={tn}, Old={to}"]
                    })

                except Exception as e:
                    st.error(f"Calculation Error: {e}")
            else:
                st.chat_message("assistant").markdown(text)
                
        except Exception as e:
            st.error(f"Error: {e}")