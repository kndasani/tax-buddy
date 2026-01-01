import streamlit as st
import google.generativeai as genai
import os
import time
from dotenv import load_dotenv

# --- CONFIGURATION ---
load_dotenv() # Load local .env file

# Try getting key from Environment (Local) OR Streamlit Secrets (Cloud)
api_key = os.getenv("GEMINI_API_KEY")

if not api_key:
    try:
        # Check Streamlit Cloud Secrets
        api_key = st.secrets["GEMINI_API_KEY"]
    except FileNotFoundError:
        # If neither works, stop
        st.error("🔑 API Key Missing! Please add 'GEMINI_API_KEY' to your .env file (local) or Streamlit Secrets (cloud).")
        st.stop()

genai.configure(api_key=api_key)

# --- 1. THE CALCULATOR ENGINES (Python Math) ---

def calculate_salary_tax(salary, rent_paid, inv_80c, med_80d):
    """Engine for Salaried Employees"""
    std_deduction_new = 75000  # FY 25-26
    std_deduction_old = 50000
    
    # HRA Logic (Simplified: Rent - 10% Basic)
    basic = salary * 0.50
    hra = max(0, rent_paid * 12 - (0.10 * basic))
    
    # Taxable Income
    inc_old = salary - std_deduction_old - min(inv_80c, 150000) - med_80d - hra
    inc_new = salary - std_deduction_new 
    
    return compute_tax_slabs(inc_new, inc_old)

def calculate_freelance_tax(gross_receipts, expenses_claimed, inv_80c, med_80d):
    """Engine for Freelancers (Section 44ADA)"""
    # Section 44ADA: Deemed Income is 50% of Receipts
    presumptive_income = gross_receipts * 0.50
    
    # Old Regime Deductions
    inc_old = presumptive_income - min(inv_80c, 150000) - med_80d
    # New Regime (No deductions)
    inc_new = presumptive_income 
    
    return compute_tax_slabs(inc_new, inc_old)

def compute_tax_slabs(inc_new, inc_old):
    """Shared Logic for Tax Slabs FY 2025-26"""
    # --- NEW REGIME (FY 25-26 Updated) ---
    tax_new = 0
    temp = inc_new
    if temp > 2400000: tax_new += (temp - 2400000) * 0.30; temp = 2400000
    if temp > 2000000: tax_new += (temp - 2000000) * 0.25; temp = 2000000
    if temp > 1600000: tax_new += (temp - 1600000) * 0.20; temp = 1600000
    if temp > 1200000: tax_new += (temp - 1200000) * 0.15; temp = 1200000
    if temp > 800000:  tax_new += (temp - 800000)  * 0.10; temp = 800000
    if temp > 400000:  tax_new += (temp - 400000)  * 0.05
    
    # Rebate 87A (New): Zero Tax if Taxable Income <= 12 Lakhs
    if inc_new <= 1200000: tax_new = 0

    # --- OLD REGIME (Unchanged) ---
    tax_old = 0
    temp = inc_old
    if temp > 1000000: tax_old += (temp - 1000000) * 0.30; temp = 1000000
    if temp > 500000:  tax_old += (temp - 500000)  * 0.20; temp = 500000
    if temp > 250000:  tax_old += (temp - 250000)  * 0.05
    
    # Rebate 87A (Old): Zero Tax if Taxable Income <= 5 Lakhs
    if inc_old <= 500000: tax_old = 0
        
    return int(tax_new * 1.04), int(tax_old * 1.04) # +4% Cess

# --- 2. LOAD THE LIBRARY (All 3 PDFs) ---
@st.cache_resource
def load_rag_data():
    folder_path = "." 
    library = []
    
    # Map filenames to "Nice Names" for Gemini
    target_files = {
        "salary_rules.pdf": "Salary Rules",
        "freelancer_rules.pdf": "Freelancer Rules",
        "capital_gains.pdf": "Capital Gains Rules"
    }
    
    for filename, display_name in target_files.items():
        if os.path.exists(filename):
            try:
                f = genai.upload_file(path=filename, display_name=display_name)
                while f.state.name == "PROCESSING":
                    time.sleep(1)
                    f = genai.get_file(f.name)
                library.append(f)
                print(f"✅ Loaded: {filename}")
            except Exception as e:
                st.error(f"Failed to load {filename}: {e}")
    
    return library

pdf_library = load_rag_data()

# --- 3. SIDEBAR & PERSONA LOGIC ---
with st.sidebar:
    st.title("👤 Your Profile")
    user_type = st.radio(
        "I am a:",
        ["Salaried Employee", "Freelancer / Doctor / Tech", "Investor / Trader"]
    )
    
    st.markdown("---")
    if user_type == "Salaried Employee":
        st.info("ℹ️ **Features:**\n- HRA & Standard Deduction\n- Form 16 Help\n- Old vs New Comparison")
    elif user_type == "Freelancer / Doctor / Tech":
        st.info("ℹ️ **Features:**\n- Section 44ADA (50% Tax)\n- Invoice-based Calc\n- Audit Rules")
    else:
        st.info("ℹ️ **Features:**\n- Capital Gains (LTCG/STCG)\n- Stock Market Rules\n- **Advisory Only (No Calc)**")

# --- 4. DEFINE THE BRAIN ---
sys_instruction = ""

if user_type == "Salaried Employee":
    sys_instruction = """
    Role: Expert Tax Assistant for Salaried Employees (FY 2025-26).
    Knowledge Base: Use 'Salary Rules' PDF.
    Goal: Get 4 numbers: Salary, Rent, 80C, 80D.
    Output Trigger: `CALCULATE_SALARY(salary=..., rent=..., inv80c=..., med80d=...)`
    """
elif user_type == "Freelancer / Doctor / Tech":
    sys_instruction = """
    Role: Expert Tax Assistant for Freelancers (Section 44ADA).
    Knowledge Base: Use 'Freelancer Rules' PDF.
    Context: 44ADA applies to Doctors, Engineers, Architects, Lawyers, IT Consultants.
    Goal: Get 3 numbers: Gross Receipts, 80C, 80D.
    Output Trigger: `CALCULATE_FREELANCE(receipts=..., inv80c=..., med80d=...)`
    """
else:
    sys_instruction = """
    Role: Expert Tax Advisor for Investors.
    Knowledge Base: Use 'Capital Gains Rules' PDF.
    Constraint: DO NOT CALCULATE TAX. Explain rules, rates (12.5% vs 20%), and grandfathering clauses.
    """

# --- 5. CHAT INTERFACE ---
st.title(f"🇮🇳 TaxGuide AI: {user_type}")

# Reset chat if persona changes
if "last_persona" not in st.session_state or st.session_state.last_persona != user_type:
    st.session_state.chat_session = None
    st.session_state.last_persona = user_type

if "chat_session" not in st.session_state or st.session_state.chat_session is None:
    history = []
    if pdf_library:
        # Pass ALL PDFs to the model so it can reference any rule if needed
        history.append({
            "role": "user", 
            "parts": pdf_library + ["Here is the Tax Library. Answer based on my selected profile."]
        })
        history.append({"role": "model", "parts": ["Understood. I will use the relevant documents for your profile."]})
    
    model = genai.GenerativeModel('gemini-1.5-flash', system_instruction=sys_instruction)
    st.session_state.chat_session = model.start_chat(history=history)

# Display Chat
start_idx = 2 if pdf_library else 0
for msg in st.session_state.chat_session.history[start_idx:]:
    role = "user" if msg.role == "user" else "assistant"
    st.chat_message(role).markdown(msg.parts[0].text)

# Handle Input
if prompt := st.chat_input("Ask about tax..."):
    st.chat_message("user").markdown(prompt)
    
    with st.spinner("Analyzing..."):
        try:
            response = st.session_state.chat_session.send_message(prompt)
            text = response.text
            
            # --- TRIGGER HANDLERS ---
            if "CALCULATE_SALARY" in text:
                try:
                    params = text.split("CALCULATE_SALARY(")[1].split(")")[0]
                    s = int(params.split("salary=")[1].split(",")[0])
                    r = int(params.split("rent=")[1].split(",")[0])
                    i = int(params.split("inv80c=")[1].split(",")[0])
                    m = int(params.split("med80d=")[1].split(")")[0])
                    
                    tn, to = calculate_salary_tax(s, r, i, m)
                    st.chat_message("assistant").markdown(f"""
                    ### 💰 Tax Calculation (Salaried)
                    | Regime | Tax Payable |
                    | :--- | :--- |
                    | **New (FY26)** | **₹{tn:,}** |
                    | **Old** | **₹{to:,}** |
                    *Verdict: You save ₹{abs(tn-to):,} by choosing the {'New' if tn < to else 'Old'} regime.*
                    """)
                except: st.chat_message("assistant").markdown(text)
                
            elif "CALCULATE_FREELANCE" in text:
                try:
                    params = text.split("CALCULATE_FREELANCE(")[1].split(")")[0]
                    g = int(params.split("receipts=")[1].split(",")[0])
                    i = int(params.split("inv80c=")[1].split(",")[0])
                    m = int(params.split("med80d=")[1].split(")")[0])
                    
                    tn, to = calculate_freelance_tax(g, 0, i, m)
                    st.chat_message("assistant").markdown(f"""
                    ### 💼 Tax Calculation (Freelancer 44ADA)
                    *Assumed 50% Profit Margin*
                    
                    | Regime | Tax Payable |
                    | :--- | :--- |
                    | **New (FY26)** | **₹{tn:,}** |
                    | **Old** | **₹{to:,}** |
                    """)
                except: st.chat_message("assistant").markdown(text)
                
            else:
                st.chat_message("assistant").markdown(text)
                
        except Exception as e:
            st.error(f"⚠️ Error: {e}")