import streamlit as st
import google.generativeai as genai
import pickle
import numpy as np
import os
import time

# 1. PAGE SETUP
st.set_page_config(page_title="TaxGuide AI", page_icon="📊")
st.title("📊 TaxGuide AI: Intelligent Tax Assistant")

# 1.1 DISCLAIMER (Mobile Friendly)
st.warning(
    "⚠️ **DISCLAIMER: Indian Income Tax (FY 2025-26)**\n\n"
    "This AI is a helper, not a substitute for a Chartered Accountant. "
    "Always verify calculations before filing."
)

# 2. SETUP API
if "GOOGLE_API_KEY" in st.secrets:
    api_key = st.secrets["GOOGLE_API_KEY"]
else:
    api_key = st.text_input("Enter Google API Key:", type="password")

if not api_key:
    st.info("Please enter your API Key to continue.")
    st.stop()

genai.configure(api_key=api_key)

# 2.1 UPLOAD TAX RULES (Cached)
@st.cache_resource
def load_tax_rules():
    file_path = "tax_rules.pdf"
    if not os.path.exists(file_path):
        st.error("⚠️ Error: 'tax_rules.pdf' not found in folder!")
        return None
    
    with st.spinner("Uploading Tax Laws to Brain... (This happens once)"):
        # Upload the file to Gemini
        tax_file = genai.upload_file(path=file_path, display_name="Indian Tax Act")
        
        # Verify it is ready
        while tax_file.state.name == "PROCESSING":
            time.sleep(1)
            tax_file = genai.get_file(tax_file.name)
            
    return tax_file

# Load the file into a variable
tax_pdf = load_tax_rules()

# 3. DEFINE THE BRAIN (The Interviewer + Lawyer Logic)
# NOTE: System instruction must be TEXT ONLY. 
system_instruction = """
You are TaxGuide AI, an expert Indian Tax Consultant for FY 2025-26.

--- PHASE 1: THE INTERVIEW (STRICT ORDER) ---
Do NOT ask for everything at once. Ask these ONE BY ONE and wait for the user:
1. "What is your annual salary?"
2. "What is your age?" (Crucial for Senior Citizen slabs).
3. "Do you live in a rented house? If yes, how much is the monthly rent?"
4. "Do you have 80C investments (PPF, LIC, ELSS)?"
5. "Do you pay for medical insurance (80D)?"

--- PHASE 2: THE CALCULATION (STRICT MATH) ---
When calculating, you MUST follow these logic steps:

**STEP 1: SANITIZE & VERIFY (Using PDF)**
- **80C CAP:** Check Section 80C in the provided PDF context. The limit is 1.5 Lakhs. If user input > 1.5L, USE 1.5L.
- **80D CAP:** Check Section 80D. Limit is 25k (Self) or 50k (Senior).
- *Output Requirement:* If you cap a value, explicitly say: "⚠️ *I limited your 80C deduction to ₹1.5 Lakhs as per Section 80C.*"

**STEP 2: HRA TRANSPARENCY**
- Calculate HRA Exemption = Min(Rent Paid - 10% of Basic, 50% of Basic).
- *Assume Basic = 50% of Total Income.*
- **REQUIRED:** You must print the "Show Your Work" math block for HRA so the user sees the numbers.

**STEP 3: TAX SLABS (FY 2025-26)**
- **New Regime:** Standard Deduction 75k.
- **Old Regime:** Standard Deduction 50k.
- Use the PDF to confirm slab rates if needed.

--- GOAL ---
Be friendly during the interview, but be a strict mathematician during the calculation.
"""

# 4. INITIALIZE CHAT MEMORY
if "chat_session" not in st.session_state:
    model = genai.GenerativeModel('gemini-2.0-flash', system_instruction=system_instruction)
    
    # We inject the PDF into the history so the model "sees" it immediately
    initial_history = []
    if tax_pdf:
        initial_history.append({
            "role": "user",
            "parts": [tax_pdf, "Here is the official Income Tax Act. Use this as your source of truth."]
        })
        initial_history.append({
            "role": "model",
            "parts": ["Understood. I have read the Income Tax Act and will use it to verify all deductions and rules."]
        })
        
    st.session_state.chat_session = model.start_chat(history=initial_history)

# --- HELPER: CHECK IF CHAT HAS STARTED ---
# We ignore the first 2 messages if they are the System+PDF injection
start_index = 0
if tax_pdf:
    start_index = 2 

# 5. WELCOME SCREEN (Only if no REAL user messages exist)
if len(st.session_state.chat_session.history) <= start_index:
    with st.container():
        st.markdown("### 👋 Welcome to TaxGuide AI!")
        st.markdown("I can help you choose the best tax regime (Old vs New).")
        st.info("👇 **To get started, just tell me your salary:**")
        st.code("My salary is 18 Lakhs", language=None) 
        st.markdown("*I will ask you about rent and investments later!*")

# 6. DISPLAY CHAT HISTORY (Hide the PDF injection)
# We slice the history to skip the first 2 "hidden" system messages
for message in st.session_state.chat_session.history[start_index:]:
    role = "user" if message.role == "user" else "assistant"
    with st.chat_message(role):
        st.markdown(message.parts[0].text)

# 7. HANDLE USER INPUT
if prompt := st.chat_input("Ask a question..."):
    # Display user message immediately
    st.chat_message("user").markdown(prompt)
    
    with st.spinner("Thinking... (Checking Tax Laws)"):
        try:
            # RETRY LOGIC for 429 Errors
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = st.session_state.chat_session.send_message(prompt)
                    st.chat_message("assistant").markdown(response.text)
                    break # Success! Exit the retry loop
                except Exception as e:
                    # If it's a 429 error, wait and try again
                    if "429" in str(e) and attempt < max_retries - 1:
                        time.sleep(2 * (attempt + 1)) # Wait 2s, then 4s...
                        continue
                    else:
                        raise e # If it's not a 429 (or retries failed), crash for real
                        
        except Exception as e:
            st.error(f"⚠️ An error occurred: {e}")
            if "429" in str(e):
                st.warning("📉 **Server Busy:** We hit the rate limit. Please wait 10 seconds and try again.")