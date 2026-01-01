import streamlit as st
import google.generativeai as genai
import os
import time
from dotenv import load_dotenv

# --- 1. CONFIGURATION ---
st.set_page_config(
    page_title="TaxGuide AI", 
    page_icon="🇮🇳", 
    layout="centered",
    initial_sidebar_state="collapsed"
)

load_dotenv()

# --- 2. API KEY SETUP ---
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    try:
        api_key = st.secrets["GEMINI_API_KEY"]
    except:
        st.error("🔑 API Key Missing.")
        st.stop()

genai.configure(api_key=api_key)

# --- 3. HELPER: ROBUST RETRY LOGIC (Prevents Crashes) ---
def send_message_with_retry(chat_session, prompt, retries=3):
    """
    Sends a message and waits if the server is busy (429 Error).
    Does NOT use streaming, to prevent UI freezing.
    """
    for i in range(retries):
        try:
            return chat_session.send_message(prompt)
        except Exception as e:
            if "429" in str(e):
                # Wait 2s, 4s, 8s...
                time.sleep(2 ** (i + 1))
                continue
            else:
                raise e
    raise Exception("⚠️ The AI is currently overwhelmed. Please wait 1 minute and try again.")

# --- 4. CALCULATOR ENGINE ---
def calculate_tax_logic(age, salary, business_income, rent_paid, inv_80c, med_80d):
    std_deduction_new = 75000 
    std_deduction_old = 50000
    
    taxable_business = business_income * 0.50
    basic = salary * 0.50
    hra = max(0, rent_paid * 12 - (0.10 * basic))
    
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

# --- 5. LOAD KNOWLEDGE ---
@st.cache_resource
def load_knowledge():
    library = []
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

# --- 6. THE CONSULTANT BRAIN ---
sys_instruction = """
You are "TaxGuide AI", an expert and empathetic Indian Tax Consultant.

**Your Goal:**
Discover the user's tax situation conversationally.

**PHASE 1: DISCOVERY**
- Ask: "How do you earn your income? (Salary, Freelancing, or both?)"
- Wait for the answer.

**PHASE 2: DEEP DIVE**
- Ask for details **ONE BY ONE**.
- Ask for Age.
- Ask for Income.
- Ask guiding questions about Deductions (Rent, Insurance).

**PHASE 3: CALCULATION**
- Only when you have all numbers, output strictly:
  `CALCULATE(age=..., salary=..., business=..., rent=..., inv80c=..., med80d=...)`
"""

# --- 7. HEADER & DISCLAIMER ---
col1, col2 = st.columns([5, 1])
with col1:
    st.markdown("### 🇮🇳 TaxGuide AI")
with col2:
    if st.button("🔄", help="Reset Chat"):
        st.session_state.chat_session = None
        st.rerun()

st.warning("⚠️ **Disclaimer:** I am an AI Assistant. Verify figures with a CA.", icon="⚠️")
st.divider()

# --- 8. CHAT LOGIC ---
if "chat_session" not in st.session_state:
    history = []
    if pdf_library:
        history.append({"role": "user", "parts": pdf_library + ["Here is your tax library."]})
        history.append({"role": "model", "parts": ["I have studied the library."]})
    
    # Use Gemini 2.0
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=sys_instruction)
    st.session_state.chat_session = model.start_chat(history=history)

# --- 9. WELCOME HINTS (RESTORED) ---
# Check if history is empty (ignoring hidden system messages)
if len(st.session_state.chat_session.history) <= 2:
    st.markdown("#### 👋 Hello! I can help you save tax.")
    st.info("👇 **Try saying:** *\"I earn 18 Lakhs salary\"* or *\"I am a freelancer\"*")

# --- 10. DISPLAY CHAT ---
start_idx = 2 if pdf_library else 0
for msg in st.session_state.chat_session.history[start_idx:]:
    role = "user" if msg.role == "user" else "assistant"
    avatar = "👤" if role == "user" else "🤖"
    
    # Simple display logic
    with st.chat_message(role, avatar=avatar):
        st.markdown(msg.parts[0].text)

# --- 11. INPUT HANDLING ---
if prompt := st.chat_input("Type your answer..."):
    st.chat_message("user", avatar="👤").markdown(prompt)
    
    with st.spinner("Analyzing..."):
        try:
            # NON-STREAMING (Safe) Call
            response = send_message_with_retry(st.session_state.chat_session, prompt)
            text = response.text
            
            # Check for Calculator Trigger
            if "CALCULATE(" in text:
                try:
                    params = text.split("CALCULATE(")[1].split(")")[0]
                    data = {"age":30, "salary":0, "business":0, "rent":0, "inv80c":0, "med80d":0}
                    
                    for part in params.split(","):
                        if "=" in part:
                            key, val = part.split("=")
                            val_clean = ''.join(filter(str.isdigit, val.strip()))
                            if val_clean:
                                data[key.strip()] = int(val_clean)
                    
                    tn, to = calculate_tax_logic(
                        data['age'], data['salary'], data['business'], 
                        data['rent'], data['inv80c'], data['med80d']
                    )
                    
                    savings = abs(tn - to)
                    winner = "New Regime" if tn < to else "Old Regime"
                    
                    # Display the Table
                    st.chat_message("assistant", avatar="🤖").markdown(f"""
                    ### 🧾 Your Tax Report
                    
                    | Regime | Tax Payable |
                    | :--- | :--- |
                    | **New Regime** | **₹{tn:,}** |
                    | **Old Regime** | **₹{to:,}** |
                    
                    🏆 **Recommendation:** Choose **{winner}**.
                    You save **₹{savings:,}**!
                    """)
                    
                    # Save a clean version to history
                    st.session_state.chat_session.history.append({
                        "role": "model",
                        "parts": [f"Result shown: New={tn}, Old={to}"]
                    })

                except Exception as e:
                    st.error(f"Calculation Error: {e}")
            else:
                # Normal Response
                st.chat_message("assistant", avatar="🤖").markdown(text)
                
        except Exception as e:
            st.error(f"Error: {e}")