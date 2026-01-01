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

# --- 2. SMART KNOWLEDGE LOADER ---
@st.cache_resource
def get_pdf_file(filename):
    """Uploads a specific PDF only when requested"""
    if os.path.exists(filename):
        try:
            f = genai.upload_file(path=filename, display_name=filename)
            while f.state.name == "PROCESSING": time.sleep(1); f = genai.get_file(f.name)
            return f
        except: return None
    return None

def inject_knowledge(persona_type):
    """Returns the specific file object based on persona"""
    if persona_type == "SALARY":
        return get_pdf_file("salary_rules.pdf")
    elif persona_type == "BUSINESS":
        return get_pdf_file("freelancer_rules.pdf")
    elif persona_type == "CAPITAL_GAINS":
        return get_pdf_file("capital_gains.pdf")
    return None

# --- 3. CALCULATOR ENGINE (Detailed) ---
def calculate_tax_detailed(age, salary, business_income, rent_paid, inv_80c, med_80d):
    std_deduction_new = 75000; std_deduction_old = 50000
    
    taxable_business = business_income * 0.50
    basic = salary * 0.50
    hra = max(0, rent_paid * 12 - (0.10 * basic))
    
    gross = salary + taxable_business
    deductions_old = std_deduction_old + hra + min(inv_80c, 150000) + med_80d
    net_old = max(0, gross - deductions_old)
    net_new = max(0, gross - std_deduction_new)

    tn = compute_tax(net_new, age, "new")
    to = compute_tax(net_old, age, "old")
    
    return tn, to, net_new, net_old

def compute_tax(income, age, regime):
    tax = 0
    if regime == "new":
        t = income
        if t > 2400000: tax += (t-2400000)*0.30; t=2400000
        if t > 2000000: tax += (t-2000000)*0.25; t=2000000
        if t > 1600000: tax += (t-1600000)*0.20; t=1600000
        if t > 1200000: tax += (t-1200000)*0.15; t=1200000
        if t > 800000:  tax += (t-800000)*0.10;  t=800000
        if t > 400000:  tax += (t-400000)*0.05
        if income <= 1200000: tax = 0
    else:
        limit = 500000 if age >= 80 else (300000 if age >= 60 else 250000)
        t = income
        if t > 1000000: tax += (t-1000000)*0.30; t=1000000
        if t > 500000:  tax += (t-500000)*0.20;  t=500000
        if t > limit:   tax += (t-limit)*0.05
        if income <= 500000: tax = 0
    return int(tax * 1.04)

# --- 4. THE SMART BRAIN ---
# Note: We now have a "ROUTER" logic in the prompt
sys_instruction = """
You are "TaxGuide AI". 
**Goal:** Discover the user's persona, LOAD the right rules, then Guide them.

**PHASE 1: PERSONA DETECTION (CRITICAL)**
- If the user mentions "Salary", "Job", "Payslip" -> Output exactly: `LOAD(SALARY)`
- If the user mentions "Freelance", "Business", "Consultant" -> Output exactly: `LOAD(BUSINESS)`
- If the user mentions "Stocks", "Trading", "Capital Gains" -> Output exactly: `LOAD(CAPITAL_GAINS)`

**PHASE 2: GUIDANCE (After Rules are Loaded)**
- Once rules are loaded, ask guiding questions based on that persona.
- Ask Age, Income, and Deductions (Rent, 80C, 80D).

**PHASE 3: CALCULATION**
- Once you have all data, output: `CALCULATE(age=..., salary=..., business=..., rent=..., inv80c=..., med80d=...)`
"""

# --- 5. UI SETUP ---
col1, col2 = st.columns([5, 1])
with col1: st.markdown("### 🇮🇳 TaxGuide AI")
with col2: 
    if st.button("🔄", help="Reset"):
        st.session_state.clear()
        st.rerun()
st.warning("⚠️ **Disclaimer:** I am an AI. Verify with a CA.", icon="⚠️")

# --- 6. CHAT SESSION MANAGEMENT ---
if "chat_session" not in st.session_state:
    # Start with NO PDFs (Lightweight)
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction)
    st.session_state.chat_session = model.start_chat(history=[])
    st.session_state.loaded_persona = None # Track what we have loaded

# --- 7. WELCOME MESSAGE ---
if len(st.session_state.chat_session.history) == 0:
    st.markdown("#### 👋 Hello! How do you earn your income?")
    st.info("👇 **Tell me:** *\"I have a salary\"* or *\"I am a freelancer\"*")

# --- 8. DISPLAY HISTORY ---
for msg in st.session_state.chat_session.history:
    # Hide system injection messages from view
    if getattr(msg.parts[0], "text", "") and "LOAD" not in msg.parts[0].text:
        role = "user" if msg.role == "user" else "assistant"
        avatar = "👤" if role == "user" else "🤖"
        # Hide raw triggers
        if "CALCULATE(" not in msg.parts[0].text and "LOAD(" not in msg.parts[0].text:
            with st.chat_message(role, avatar=avatar):
                st.markdown(msg.parts[0].text)

# --- 9. MAIN LOGIC LOOP ---
if prompt := st.chat_input("Type here..."):
    st.chat_message("user", avatar="👤").markdown(prompt)
    
    with st.spinner("Thinking..."):
        try:
            # Send message to AI
            response = st.session_state.chat_session.send_message(prompt)
            text = response.text
            
            # --- CHECK FOR "LOAD" TRIGGER (The Optimization) ---
            if "LOAD(" in text:
                persona = text.split("LOAD(")[1].split(")")[0]
                
                # If we haven't loaded this yet, do it now
                if st.session_state.loaded_persona != persona:
                    file_ref = inject_knowledge(persona)
                    if file_ref:
                        # TO INJECT: We must restart chat with history + new file
                        # 1. Save current conversation
                        current_history = st.session_state.chat_session.history[:-1] # Exclude the LOAD command
                        
                        # 2. Add File to history (Gemini requires file in 'user' role)
                        current_history.append({"role": "user", "parts": [file_ref, "I have loaded the relevant tax rules. Please continue guiding me."]})
                        current_history.append({"role": "model", "parts": ["Understood. Rules loaded."]})
                        
                        # 3. Restart Session
                        model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction)
                        st.session_state.chat_session = model.start_chat(history=current_history)
                        st.session_state.loaded_persona = persona
                        
                        # 4. Prompt AI to acknowledge
                        response = st.session_state.chat_session.send_message("I have loaded the rules. What is the next question?")
                        text = response.text
                        
                        st.toast(f"📚 Loaded Knowledge: {persona} Rules", icon="✅")

            # --- CHECK FOR "CALCULATE" TRIGGER ---
            if "CALCULATE(" in text:
                try:
                    params = text.split("CALCULATE(")[1].split(")")[0]
                    data = {"age":30, "salary":0, "business":0, "rent":0, "inv80c":0, "med80d":0}
                    for part in params.split(","):
                        if "=" in part:
                            k, v = part.split("="); 
                            vc = ''.join(filter(str.isdigit, v.strip()))
                            if vc: data[k.strip()] = int(vc)
                    
                    tn, to, net_new, net_old = calculate_tax_detailed(
                        data['age'], data['salary'], data['business'], 
                        data['rent'], data['inv80c'], data['med80d']
                    )
                    
                    winner = "New Regime" if tn < to else "Old Regime"
                    savings = abs(tn - to)
                    
                    st.chat_message("assistant", avatar="🤖").markdown(f"""
                    ### 🧾 Tax Analysis
                    **Recommendation:** Go with **{winner}** (Save ₹{savings:,})
                    
                    | | **New Regime** | **Old Regime** |
                    | :--- | :--- | :--- |
                    | Taxable Income | ₹{net_new:,} | ₹{net_old:,} |
                    | **Total Tax** | **₹{tn:,}** | **₹{to:,}** |
                    """)
                    
                    # Clean history
                    st.session_state.chat_session.history.append({"role": "model", "parts": [f"Result: New={tn}, Old={to}"]})

                except Exception as e: st.error(f"Calc Error: {e}")
            
            else:
                # Normal Text (Avoid showing raw triggers)
                if "LOAD(" not in text and "CALCULATE(" not in text:
                    st.chat_message("assistant", avatar="🤖").markdown(text)

        except Exception as e:
            st.error(f"Error: {e}")