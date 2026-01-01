import streamlit as st
import google.generativeai as genai
import os
import time
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="TaxGuide AI", page_icon="🇮🇳", layout="centered", initial_sidebar_state="collapsed")
load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try: api_key = st.secrets["GEMINI_API_KEY"]
    except: st.error("🔑 API Key Missing."); st.stop()

genai.configure(api_key=api_key)

# --- 2. HELPER: RETRY LOGIC ---
def send_message_with_retry(chat_session, prompt, retries=3):
    for i in range(retries):
        try:
            return chat_session.send_message(prompt)
        except Exception as e:
            if "429" in str(e):
                time.sleep(2 ** (i + 1))
                continue
            else:
                raise e
    raise Exception("⚠️ Server busy. Please wait 1 minute.")

# --- 3. SMART KNOWLEDGE LOADER ---
@st.cache_resource
def get_pdf_file(filename):
    if os.path.exists(filename):
        try:
            f = genai.upload_file(path=filename, display_name=filename)
            while f.state.name == "PROCESSING": time.sleep(1); f = genai.get_file(f.name)
            return f
        except: return None
    return None

def inject_knowledge(persona_type):
    if persona_type == "SALARY": return get_pdf_file("salary_rules.pdf")
    elif persona_type == "BUSINESS": return get_pdf_file("freelancer_rules.pdf")
    elif persona_type == "CAPITAL_GAINS": return get_pdf_file("capital_gains.pdf")
    return None

# --- 4. PROFESSIONAL CALCULATOR ENGINE ---
def calculate_tax_detailed(age, salary, business_income, rent_paid, inv_80c, med_80d):
    std_deduction_new = 75000; std_deduction_old = 50000
    
    # Income Logic
    taxable_business = business_income * 0.50
    basic = salary * 0.50
    hra = max(0, rent_paid * 12 - (0.10 * basic))
    
    gross = salary + taxable_business
    deductions_old = std_deduction_old + hra + min(inv_80c, 150000) + med_80d
    net_old = max(0, gross - deductions_old)
    net_new = max(0, gross - std_deduction_new)

    # Calculate Breakdown
    breakdown_new = compute_tax_breakdown(net_new, age, "new")
    breakdown_old = compute_tax_breakdown(net_old, age, "old")
    
    return breakdown_new, breakdown_old, net_new, net_old

def compute_tax_breakdown(income, age, regime):
    """
    Returns a dictionary with: {base_tax, surcharge, cess, total}
    """
    tax = 0
    # 1. SLAB CALCULATION
    if regime == "new":
        t = income
        if t > 2400000: tax += (t-2400000)*0.30; t=2400000
        if t > 2000000: tax += (t-2000000)*0.25; t=2000000
        if t > 1600000: tax += (t-1600000)*0.20; t=1600000
        if t > 1200000: tax += (t-1200000)*0.15; t=1200000
        if t > 800000:  tax += (t-800000)*0.10;  t=800000
        if t > 400000:  tax += (t-400000)*0.05
        if income <= 1200000: tax = 0 # Rebate u/s 87A
    else:
        limit = 500000 if age >= 80 else (300000 if age >= 60 else 250000)
        t = income
        if t > 1000000: tax += (t-1000000)*0.30; t=1000000
        if t > 500000:  tax += (t-500000)*0.20;  t=500000
        if t > limit:   tax += (t-limit)*0.05
        if income <= 500000: tax = 0 # Rebate u/s 87A

    # 2. SURCHARGE LOGIC
    surcharge = 0
    if income > 5000000: # > 50 Lakhs
        rate = 0.10
        if income > 10000000: rate = 0.15 # > 1 Cr
        if income > 20000000: rate = 0.25 # > 2 Cr
        if regime == "old" and income > 50000000: rate = 0.37 # > 5 Cr (Old only)
        # New regime surcharge is capped at 25%
        surcharge = tax * rate

    # 3. CESS LOGIC (4% on Tax + Surcharge)
    cess = (tax + surcharge) * 0.04
    
    total_tax = int(tax + surcharge + cess)
    
    return {
        "base_tax": int(tax),
        "surcharge": int(surcharge),
        "cess": int(cess),
        "total": total_tax
    }

# --- 5. THE BRAIN ---
sys_instruction = """
You are "TaxGuide AI". Talk like a human consultant.

**LOGIC FLOW:**
1. **START:** Ask: "How do you earn your living? (Salary, Business?)"
2. **DETECT & LOAD:**
   - If User says "Salary" -> Output: `LOAD(SALARY)`
   - If User says "Freelance/Business" -> Output: `LOAD(BUSINESS)`
3. **INTERVIEW (Slowly):**
   - Ask Age.
   - Ask Income.
   - Ask Deductions (Rent, 80C, 80D) **ONE BY ONE**.
4. **CALCULATE:**
   - Output: `CALCULATE(age=..., salary=..., business=..., rent=..., inv80c=..., med80d=...)`
"""

# --- 6. UI HEADER ---
col1, col2 = st.columns([5, 1])
with col1: st.markdown("### 🇮🇳 TaxGuide AI")
with col2: 
    if st.button("🔄", help="Reset"):
        st.session_state.clear()
        st.rerun()

# --- 7. FORK LOGIC ---
if "mode" not in st.session_state:
    st.session_state.mode = None
    st.session_state.chat_session = None
    st.session_state.loaded_persona = None

# SCREEN 1: BUTTONS
if st.session_state.mode is None:
    st.markdown("#### 👋 How can I help you today?")
    st.info("Choose a path:")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💰 Calculate My Tax", use_container_width=True):
            st.session_state.mode = "CALC"
            model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction)
            st.session_state.chat_session = model.start_chat(history=[])
            st.session_state.chat_session.history.append({"role": "model", "parts": ["Hi! Let's calculate. Do you earn a Salary or run a Business?"]})
            st.rerun()
    with c2:
        if st.button("📚 Ask Tax Rules", use_container_width=True):
            st.session_state.mode = "RULES"
            model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction)
            st.session_state.chat_session = model.start_chat(history=[])
            st.session_state.chat_session.history.append({"role": "model", "parts": ["I can explain rules. What topic?"]})
            st.rerun()

# SCREEN 2: CHAT
else:
    # History Display
    for msg in st.session_state.chat_session.history:
        text, role = "", ""
        if isinstance(msg, dict):
            role = msg.get("role")
            parts = msg.get("parts", [])
            if parts:
                first = parts[0]
                if isinstance(first, str): text = first
                elif hasattr(first, "text"): text = first.text
        else:
            role = msg.role
            text = msg.parts[0].text

        if text and "LOAD" not in text and "Result:" not in text:
            role_name = "user" if role == "user" else "assistant"
            avatar = "👤" if role == "user" else "🤖"
            with st.chat_message(role_name, avatar=avatar):
                st.markdown(text)

    # Input Handling
    if prompt := st.chat_input("Type here..."):
        st.chat_message("user", avatar="👤").markdown(prompt)
        
        with st.spinner("Thinking..."):
            try:
                response = send_message_with_retry(st.session_state.chat_session, prompt)
                text = response.text
                
                # Logic for LOAD...
                if "LOAD(" in text:
                    persona = text.split("LOAD(")[1].split(")")[0]
                    if st.session_state.loaded_persona != persona:
                        file_ref = inject_knowledge(persona)
                        if file_ref:
                            hist = st.session_state.chat_session.history[:-1]
                            hist.append({"role": "user", "parts": [file_ref, "Rules loaded."]})
                            hist.append({"role": "model", "parts": ["Understood."]})
                            model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction)
                            st.session_state.chat_session = model.start_chat(history=hist)
                            st.session_state.loaded_persona = persona
                            st.toast(f"📚 Context Loaded: {persona}", icon="✅")
                            time.sleep(2)
                            response = send_message_with_retry(st.session_state.chat_session, "Context loaded. Gently ask for Age.")
                            text = response.text

                # Logic for CALCULATE...
                if "CALCULATE(" in text:
                    try:
                        params = text.split("CALCULATE(")[1].split(")")[0]
                        data = {"age":30, "salary":0, "business":0, "rent":0, "inv80c":0, "med80d":0}
                        for part in params.split(","):
                            if "=" in part:
                                k, v = part.split("="); 
                                vc = ''.join(filter(str.isdigit, v.strip()))
                                if vc: data[k.strip()] = int(vc)
                        
                        # --- GET DETAILED BREAKDOWN ---
                        bd_new, bd_old, net_new, net_old = calculate_tax_detailed(
                            data['age'], data['salary'], data['business'], 
                            data['rent'], data['inv80c'], data['med80d']
                        )
                        
                        tn = bd_new['total']
                        to = bd_old['total']
                        winner = "New Regime" if tn < to else "Old Regime"
                        savings = abs(tn - to)
                        
                        st.chat_message("assistant", avatar="🤖").markdown(f"""
                        ### 🧾 Final Tax Analysis
                        **Recommendation:** Go with **{winner}** (Save ₹{savings:,})
                        
                        | Component | **New Regime** | **Old Regime** |
                        | :--- | :--- | :--- |
                        | Taxable Income | ₹{net_new:,} | ₹{net_old:,} |
                        | Base Tax | ₹{bd_new['base_tax']:,} | ₹{bd_old['base_tax']:,} |
                        | Surcharge | ₹{bd_new['surcharge']:,} | ₹{bd_old['surcharge']:,} |
                        | Cess (4%) | ₹{bd_new['cess']:,} | ₹{bd_old['cess']:,} |
                        | **TOTAL PAYABLE** | **₹{tn:,}** | **₹{to:,}** |
                        """)
                        
                        # Add a collapsible Details section
                        with st.expander("🔎 See Calculation Details"):
                            st.write("This calculation includes:")
                            st.markdown("- **Slabs:** FY 2025-26 Rates")
                            st.markdown("- **Surcharge:** Applied if income > ₹50L")
                            st.markdown("- **Cess:** 4% Health & Education Cess")
                            st.markdown("")

                        st.session_state.chat_session.history.append({"role": "model", "parts": [f"Result: New={tn}, Old={to}"]})
                    except Exception as e: st.error(f"Calc Error: {e}")

                else:
                    if "LOAD(" not in text:
                        st.chat_message("assistant", avatar="🤖").markdown(text)

            except Exception as e: st.error(f"Error: {e}")