import streamlit as st
import google.generativeai as genai
import os
import time
import math
import re
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

# --- 3. KNOWLEDGE LOADER ---
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

# --- 4. CALCULATOR ENGINES ---

def safe_math_eval(expression):
    try:
        if ":" in expression: expression = expression.split(":")[-1]
        if "=" in expression: expression = expression.split("=")[-1]
        expression = expression.lower().strip()
        expression = expression.replace("\n", " ").replace("\t", " ") 
        expression = expression.replace("`", "").replace("₹", "")       
        expression = expression.replace("%", "*0.01").replace("^", "**")     
        expression = re.sub(r'(\d),(\d)', r'\1\2', expression)
        allowed = set("0123456789+-*/()., <>=abcdefhilmnorstuwx")
        if not set(expression).issubset(allowed): return "Error: Unsafe characters"
        safe_dict = {"min": min, "max": max, "abs": abs, "round": round, "int": int, "float": float, "pow": pow, "ceil": math.ceil, "floor": math.floor}
        result = eval(expression, {"__builtins__": None}, safe_dict)
        if isinstance(result, (int, float)): return f"{int(result):,}"
        return str(result)
    except Exception as e: return f"Error ({e})"

def calculate_hra_exemption(basic_annual, rent_annual, metro=True):
    cond2 = rent_annual - (0.10 * basic_annual)
    cond3 = (0.50 if metro else 0.40) * basic_annual
    return int(max(0, min(cond2, cond3)))

def calculate_tax_detailed(age, salary, business_income, rent_paid, inv_80c, med_80d, home_loan, nps, edu_loan, donations, savings_int, other_deductions, custom_basic=0):
    std_deduction_new = 75000; std_deduction_old = 50000
    
    basic = 0
    if custom_basic > 0:
        if custom_basic < 100: basic = salary * (custom_basic / 100.0)
        else: basic = custom_basic
    else:
        basic = salary * 0.50 

    final_rent = rent_paid
    if rent_paid > 0 and rent_paid < (salary * 0.15):
        final_rent = rent_paid * 12 

    hra_exemption = calculate_hra_exemption(basic, final_rent)
    
    limit_80tta = 50000 if age >= 60 else 10000
    deduction_80tta = min(savings_int, limit_80tta)
    deduction_80e = edu_loan
    deduction_80g = donations
    deduction_home_loan = min(home_loan, 200000)
    deduction_nps = min(nps, 50000)

    taxable_business = business_income * 0.50
    gross = salary + taxable_business
    
    deductions_old = (
        std_deduction_old + hra_exemption + min(inv_80c, 150000) + med_80d + 
        deduction_home_loan + deduction_nps + deduction_80e + 
        deduction_80g + deduction_80tta + other_deductions
    )
    
    net_old = max(0, gross - deductions_old)
    net_new = max(0, gross - std_deduction_new)

    bd_new = compute_tax_breakdown(net_new, age, "new")
    bd_old = compute_tax_breakdown(net_old, age, "old")
    
    return {
        "new": {"breakdown": bd_new, "net": net_new},
        "old": {
            "breakdown": bd_old, 
            "net": net_old, 
            "deductions": {
                "std": std_deduction_old, 
                "hra": hra_exemption, 
                "80c": min(inv_80c, 150000), 
                "80d": med_80d, # Key is "80d"
                "home_loan": deduction_home_loan,
                "nps": deduction_nps,
                "80e": deduction_80e,
                "80g": deduction_80g,
                "80tta": deduction_80tta,
                "other": other_deductions
            }, 
            "assumptions": {"basic": basic, "rent_annual": final_rent}
        }
    }

def compute_tax_breakdown(income, age, regime):
    tax = 0
    if regime == "new":
        t = income
        if t > 2400000: tax += (t-2400000)*0.30; t=2400000
        if t > 2000000: tax += (t-2000000)*0.25; t=2000000
        if t > 1600000: tax += (t-1600000)*0.20; t=1600000
        if t > 1200000: tax += (t-1200000)*0.15; t=1200000
        if t > 800000:  tax += (t-800000)*0.10;  t=800000
        if t > 400000:  tax += (t-400000)*0.05
    else:
        limit = 500000 if age >= 80 else (300000 if age >= 60 else 250000)
        t = income
        if t > 1000000: tax += (t-1000000)*0.30; t=1000000
        if t > 500000:  tax += (t-500000)*0.20;  t=500000
        if t > limit:   tax += (t-limit)*0.05

    surcharge = 0
    if income > 5000000:
        rate = 0.10 if income <= 10000000 else 0.15
        if income > 20000000: rate = 0.25
        if regime == "old" and income > 50000000: rate = 0.37
        surcharge = tax * rate
    
    cess = (tax + surcharge) * 0.04
    return {"base": int(tax), "surcharge": int(surcharge), "cess": int(cess), "total": int(tax + surcharge + cess)}

# --- 5. THE UNIFIED BRAIN ---

sys_instruction_unified = """
You are "TaxGuide AI".

**PHASE 1: THE QUICK SCAN (Estimate)**
1. **Trigger:** User gives Salary (or Salary + Rent).
2. **Action:** `CALCULATE(...)` immediately using defaults for anything missing.
3. **Post-Calc Message:**
   - "I have calculated your tax based on your Salary (and Rent if provided)."
   - "⚠️ **Note:** I assumed you have **0** other investments."
   - "Would you like a **step-by-step guide** to input your investments (like PF, Insurance, Loans) to lower your tax?"

**PHASE 2: THE GUIDED AUDIT (Step-by-Step)**
1. **Trigger:** User says "Yes" or "Guide me".
2. **Action:** Ask about **ONE** category at a time in **SIMPLE ENGLISH**.
   - Q1: "Do you pay any **Rent**? If yes, how much per month?" (Skip if already known)
   - Q2: "Do you contribute to **EPF, PPF, or Life Insurance**? (Limit: 1.5L)"
   - Q3: "Do you pay for **Health Insurance** for yourself or parents?"
   - Q4: "Do you have a **Home Loan** or **Education Loan**?"
3. **After Each Answer:** Run `CALCULATE(...)` again to show the *new* tax savings immediately.

**CRITICAL RULES:**
- **Monthly Math:** Automatically multiply monthly inputs by 12.
- **No Jargon:** Don't say "Section 80CCD(1B)". Say "NPS".
- **Tool Use:** ALWAYS use `CALCULATE` when numbers change.

**OUTPUT FORMAT:**
[Summary]
|||
[Technical Details]
"""

# --- 6. UI SETUP ---
if "chat_started" not in st.session_state:
    st.session_state.chat_started = False
    st.session_state.chat_session = None
    st.session_state.loaded_persona = None

col1, col2 = st.columns([5, 1])
with col1: st.markdown("### 🇮🇳 TaxGuide AI")
with col2: 
    if st.button("🔄", help="Reset App"):
        st.session_state.clear()
        st.rerun()

# --- SCREEN 1: LANDING PAGE ---
if not st.session_state.chat_started:
    st.markdown("#### 👋 How can I help you today?")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("💰 Calculate My Tax", use_container_width=True):
            st.session_state.chat_started = True
            model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction_unified)
            st.session_state.chat_session = model.start_chat(history=[])
            st.session_state.chat_session.history.append({"role": "model", "parts": ["Hi! Let's start with the basics. What is your **Annual Salary**?"]})
            st.rerun()
    with c2:
        if st.button("📚 Ask Tax Rules", use_container_width=True):
            st.session_state.chat_started = True
            model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction_unified)
            st.session_state.chat_session = model.start_chat(history=[])
            st.session_state.chat_session.history.append({"role": "model", "parts": ["Hi! I can explain rules (HRA, Deductions, Capital Gains). What's your question?"]})
            st.rerun()

# --- SCREEN 2: CHAT INTERFACE ---
else:
    def render_message(text, role, avatar):
        with st.chat_message(role, avatar=avatar):
            if "|||" in text:
                summary, details = text.split("|||", 1)
                st.markdown(summary.strip())
                if len(details.strip()) > 5:
                    with st.expander("📝 View Details & Assumptions"):
                        st.markdown(details.strip())
            else:
                st.markdown(text)

    # History Display
    for msg in st.session_state.chat_session.history:
        text = ""
        role_label = ""
        if isinstance(msg, dict):
            role_label = msg.get("role")
            parts = msg.get("parts", [])
            if parts: text = parts[0]
        else:
            role_label = msg.role
            if msg.parts: text = msg.parts[0].text
        
        role_icon = "👤" if role_label == "user" else "🤖"
        if text and not any(x in text for x in ["CALCULATE(", "CALCULATE_MATH(", "LOAD(", "Result:"]):
            render_message(text, role_label, role_icon)

    if prompt := st.chat_input("Ex: Salary 15L..."):
        st.chat_message("user", avatar="👤").markdown(prompt)
        
        with st.spinner("Processing..."):
            try:
                response = send_message_with_retry(st.session_state.chat_session, prompt)
                text = response.text
                
                # --- TOOL 1: MATH SPOT CHECK ---
                if "CALCULATE_MATH(" in text:
                    expr = text.split("CALCULATE_MATH(")[1][:-1]
                    res = safe_math_eval(expr)
                    st.toast(f"🧮 Computed: {res}", icon="✅")
                    send_message_with_retry(st.session_state.chat_session, f"Math Result: {res}. State this exact number.")
                    text = st.session_state.chat_session.history[-1].parts[0].text

                # --- TOOL 2: LOAD KNOWLEDGE ---
                if "LOAD(" in text:
                    persona = text.split("LOAD(")[1].split(")")[0]
                    if st.session_state.loaded_persona != persona:
                        f = inject_knowledge(persona)
                        if f:
                            hist = st.session_state.chat_session.history[:-1]
                            hist.append({"role": "user", "parts": [f, "Context Loaded."]})
                            hist.append({"role": "model", "parts": ["Context received."]}); 
                            model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction_unified)
                            st.session_state.chat_session = model.start_chat(history=hist)
                            st.session_state.loaded_persona = persona
                            st.toast(f"📚 Loaded: {persona}", icon="✅")
                            send_message_with_retry(st.session_state.chat_session, "Context loaded. Proceed.")
                            text = st.session_state.chat_session.history[-1].parts[0].text

                # --- TOOL 3: FULL CALCULATOR ---
                if "CALCULATE(" in text:
                    params = text.split("CALCULATE(")[1].split(")")[0]
                    d = {"age":30, "salary":0, "business":0, "rent":0, "inv80c":0, "med80d":0, "basic":0, "home_loan":0, "nps":0, "edu_loan":0, "donations":0, "savings_int":0, "other":0}
                    for p in params.split(","):
                        if "=" in p:
                            k, v = p.split("=")
                            vc = ''.join(filter(str.isdigit, v))
                            if vc: d[k.strip()] = int(vc)
                    
                    res = calculate_tax_detailed(
                        d['age'], d['salary'], d['business'], d['rent'], 
                        d['inv80c'], d['med80d'], d['home_loan'], d['nps'],
                        d['edu_loan'], d['donations'], d['savings_int'], d['other'], d['basic']
                    )
                    tn, to = res['new']['breakdown']['total'], res['old']['breakdown']['total']
                    
                    if tn < to:
                        winner = "New Regime"
                        savings = to - tn
                        color = "green"
                    else:
                        winner = "Old Regime"
                        savings = tn - to
                        color = "blue"
                    
                    assumed_text = ""
                    if d['rent'] == 0: assumed_text += "- **Rent:** ₹0 (Assumed)\n"
                    if d['inv80c'] == 0: assumed_text += "- **80C Investments:** ₹0 (Assumed)\n"
                    if d['home_loan'] == 0: assumed_text += "- **Home Loan:** ₹0 (Assumed)\n"
                    
                    report = f"""
                    ### 📊 Tax Comparison
                    | | **New Regime** | **Old Regime** |
                    | :--- | :--- | :--- |
                    | **Total Tax** | **₹{tn:,}** | **₹{to:,}** |
                    
                    **:trophy: Winner:** :{color}[**{winner}**] saves you **₹{savings:,}**
                    
                    ---
                    **⚠️ Current Assumptions:**
                    {assumed_text}
                    *To reduce your tax, I can guide you through these missing deductions.*
                    
                    ||| 
                    **Detailed Breakdown:**
                    * **Gross Income:** ₹{d['salary']:,}
                    * **Standard Deduction:** ₹75,000 (New) / ₹50,000 (Old)
                    *  **HRA Exemption:** ₹{res['old']['deductions']['hra']:,}
                    *  **80C (PF/PPF):** ₹{res['old']['deductions']['80c']:,}
                    *  **Home Loan Interest:** ₹{res['old']['deductions']['home_loan']:,}
                    * **Health Ins (80D):** ₹{res['old']['deductions']['80d']:,}
                    * **NPS:** ₹{res['old']['deductions']['nps']:,}
                    """
                    st.chat_message("assistant", avatar="🤖").markdown(report.split("|||")[0])
                    with st.expander("📝 View Full Breakdown"): st.markdown(report.split("|||")[1])
                    
                    st.session_state.chat_session.history.append({"role": "model", "parts": [f"Result shown: New={tn}, Old={to}"]})

                if not any(x in text for x in ["CALCULATE(", "CALCULATE_MATH(", "LOAD(", "Result:"]):
                    render_message(text, "assistant", "🤖")

            except Exception as e: st.error(f"Error: {e}")