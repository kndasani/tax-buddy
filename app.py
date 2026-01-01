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

# --- 2. HELPER: RETRY LOGIC (Crucial) ---
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

# --- 4. CALCULATOR ENGINE ---
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

# --- 5. THE PATIENT BRAIN (Updated Prompt) ---
sys_instruction = """
You are "TaxGuide AI", a friendly, patient, and non-judgmental Indian Tax Expert.
**Core Rule:** Talk like a human, not a form. Avoid jargon.

**LOGIC FLOW:**

1. **START:** Ask gently: "To get started, how do you earn your living? (e.g., A Salary, Freelancing, or your own Business?)"

2. **DETECT & LOAD (Invisible Step):**
   - If User says "Salary" -> Output: `LOAD(SALARY)`
   - If User says "Freelance/Business" -> Output: `LOAD(BUSINESS)`
   - If User says "Stocks" -> Output: `LOAD(CAPITAL_GAINS)`

3. **THE INTERVIEW (After Loading):**
   - **CRITICAL:** Ask questions **ONE BY ONE**. Wait for the answer before asking the next.
   - **Step 1 (Age):** "First, could you tell me your age? (This helps me check for Senior Citizen benefits)."
   - **Step 2 (Income):** "Thanks! What is your total annual income roughly?"
   - **Step 3 (Deductions - The Guide):**
     - Do NOT ask "What is your 80C?".
     - **Ask:** "Do you live in a rented house? If yes, how much rent do you pay?"
     - **Then Ask:** "Do you have any long-term savings like PF, PPF, or Life Insurance?" (Internal Note: Map this to 80C).
     - **Then Ask:** "Do you pay for medical insurance for yourself or parents?" (Internal Note: Map this to 80D).

4. **CALCULATE:**
   - Only when you have the full picture, output: `CALCULATE(age=..., salary=..., business=..., rent=..., inv80c=..., med80d=...)`
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
    st.info("I'm here to simplify your taxes. Choose a path:")
    
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💰 Calculate My Tax", use_container_width=True):
            st.session_state.mode = "CALC"
            model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction)
            st.session_state.chat_session = model.start_chat(history=[])
            # Friendly Starter
            st.session_state.chat_session.history.append({"role": "model", "parts": ["Hi there! Let's work out your taxes together. First, do you earn a Salary, run a Business, or work as a Freelancer?"]})
            st.rerun()
            
    with c2:
        if st.button("📚 Ask Tax Rules", use_container_width=True):
            st.session_state.mode = "RULES"
            model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction)
            st.session_state.chat_session = model.start_chat(history=[])
            st.session_state.chat_session.history.append({"role": "model", "parts": ["I can explain tax rules simply. What topic are you curious about?"]})
            st.rerun()

# SCREEN 2: CHAT
else:
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

    if prompt := st.chat_input("Type your answer..."):
        st.chat_message("user", avatar="👤").markdown(prompt)
        
        with st.spinner("Thinking..."):
            try:
                response = send_message_with_retry(st.session_state.chat_session, prompt)
                text = response.text
                
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
                            # Gentle Re-prompt
                            response = send_message_with_retry(st.session_state.chat_session, "Context loaded. Please gently ask for their Age now.")
                            text = response.text

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
                        ### 🧾 Your Tax Report
                        **Recommendation:** Go with **{winner}** (Save ₹{savings:,})
                        
                        | | **New Regime** | **Old Regime** |
                        | :--- | :--- | :--- |
                        | Taxable Income | ₹{net_new:,} | ₹{net_old:,} |
                        | **Total Tax** | **₹{tn:,}** | **₹{to:,}** |
                        """)
                        st.session_state.chat_session.history.append({"role": "model", "parts": [f"Result: New={tn}, Old={to}"]})
                    except: st.error("Calculation Failed")

                else:
                    if "LOAD(" not in text:
                        st.chat_message("assistant", avatar="🤖").markdown(text)

            except Exception as e: st.error(f"Error: {e}")