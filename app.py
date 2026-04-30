"""
Streamlit app — Agentic Invoice Dispatcher

The agent (powered by create_tool_calling_agent + AgentExecutor) autonomously
decides what actions to take based on user messages. No hardcoded regex routing.

Flow:
  1. User chats naturally → Agent decides if tools are needed
  2. "Send this to x@y.com" → Agent calls extract_invoice → draft_email
  3. "Yes / send it" → Agent calls send_email
  4. General questions → Agent responds directly (no tools)
"""

import json
import streamlit as st
import os

from agent import run_agent_chat
import config
from email_sender import send_email

# ─── Page config ──────────────────────────────────────────
st.set_page_config(
    page_title="Invoice Dispatcher",
    page_icon="📨",
    layout="centered",
)

# ─── Minimal custom CSS ──────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .block-container { max-width: 720px; }

    .step-label {
        display: inline-block;
        background: #2563eb;
        color: white;
        border-radius: 50%;
        width: 28px; height: 28px;
        text-align: center;
        line-height: 28px;
        font-weight: 600;
        font-size: 0.85rem;
        margin-right: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ─── Sidebar — settings ──────────────────────────────────
with st.sidebar:
    st.header("Settings")

    st.markdown("---")
    st.subheader("Email Details") 

    st.text_input(
        "Your Email (Required)", 
        key="smtp_email", 
        help="The email address you'll use to send invoices."
    )
    st.text_input(
        "App Password (Required)", 
        type="password", 
        key="smtp_password", 
        help="Your email provider's App Password (not your regular login password)."
    )

    st.markdown("---")
    st.subheader("Sender Details")
    st.text_input("Company Name", key="company_name")
    st.text_input("Your Name", key="sender_name")
    st.text_input("Phone Number", key="sender_phone")
    st.text_input(
        "Sender Email (for sign-off)", 
        key="sender_email", 
        help="Defaults to your login email if left empty."
    )

# ─── Title ────────────────────────────────────────────────
st.title("Invoice Dispatcher Agent")
st.caption("Upload an invoice → AI drafts an email → Review & send.")
st.markdown("---")

# ─── Session state init ──────────────────────────────────
# User-specific settings (initialized from config defaults)
if "smtp_email" not in st.session_state:
    st.session_state["smtp_email"] = config.SMTP_EMAIL
if "smtp_password" not in st.session_state:
    st.session_state["smtp_password"] = config.SMTP_PASSWORD
if "company_name" not in st.session_state:
    st.session_state["company_name"] = config.COMPANY_NAME
if "sender_name" not in st.session_state:
    st.session_state["sender_name"] = config.SENDER_NAME
if "sender_phone" not in st.session_state:
    st.session_state["sender_phone"] = config.SENDER_PHONE
if "sender_email" not in st.session_state:
    st.session_state["sender_email"] = config.SENDER_EMAIL or config.SMTP_EMAIL

for key in ["subject", "body", "step", "file_bytes", "file_name", "customer_email", 
            "chat_messages", "all_files", "extracted_invoice_data", "email_subject", "email_body"]:
    if key not in st.session_state:
        if key in ("chat_messages", "all_files"):
            st.session_state[key] = []
        else:
            st.session_state[key] = None

if "step" not in st.session_state or st.session_state["step"] is None:
    st.session_state["step"] = "upload"

# ─── Extra CSS for Premium Chat Experience ─────────────────────
st.markdown("""
<style>
    /* Main container smoothing */
    .stChatMessage {
        animation: fadeIn 0.4s ease-out;
        margin-bottom: 12px !important;
        padding: 0 !important;
        background-color: transparent !important;
    }

    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(10px); }
        to { opacity: 1; transform: translateY(0); }
    }

    /* General message content styling */
    [data-testid="stChatMessageContent"] {
        padding: 12px 18px !important;
        font-size: 0.95rem;
        line-height: 1.5;
    }

    [data-testid="stChatMessageContent"] p {
        margin-bottom: 0 !important;
    }

    /* --- ALIGNMENT FIX (USER RIGHT, AI LEFT) --- */
    
    /* Global message container fix */
    [data-testid="stChatMessage"] {
        background-color: transparent !important;
    }

    /* Target BOTH div and section variants */
    div[data-testid="stChatMessage"]:has([aria-label*="user" i]),
    section[data-testid="stChatMessage"]:has([aria-label*="user" i]),
    div[data-testid="stChatMessage"]:has([data-testid*="user" i]),
    section[data-testid="stChatMessage"]:has([data-testid*="user" i]) {
        flex-direction: row-reverse !important;
    }

    /* Force children of user message row-reverse */
    div[data-testid="stChatMessage"]:has([aria-label*="user" i]) > div,
    section[data-testid="stChatMessage"]:has([aria-label*="user" i]) > div {
        flex-direction: row-reverse !important;
    }

    /* --- MESSAGE BUBBLE AESTHETICS --- */
    
    /* General Content (shared padding/font) */
    [data-testid="stChatMessageContent"] {
        padding:25px !important;
        font-size: 0.95rem !important;
        line-height: 1.5 !important;
    }

    /* User Message Style (Right) */
    [data-testid="stChatMessage"]:has([aria-label*="user" i]) [data-testid="stChatMessageContent"] {
        background-color: #f1f5f9 !important;
        color: #1e293b !important;
        border-radius: 20px 20px 4px 20px !important;
        border: 1px solid #e2e8f0 !important;
        margin-left: auto !important;
        max-width: 80% !important;
    }

    /* Assistant Message Style (Left) */
    [data-testid="stChatMessage"]:has([aria-label*="assistant" i]) [data-testid="stChatMessageContent"] {
        background-color: #ffffff !important;
        color: #1e293b !important;
        border-radius: 20px 18px 18px 4px !important;
        border: 1px solid #e2e8f0 !important;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03) !important;
        margin-right: auto !important;
        max-width: 80% !important;
    }

    /* Hide redundant avatar backgrounds */
    [data-testid*="chatAvatarIcon"] {
        background-color: transparent !important;
    }

    /* Chat input container styling */
    .stChatInputContainer {
        border-radius: 12px !important;
        box-shadow: 0 -4px 12px rgba(0,0,0,0.03) !important;
        background-color: white !important;
        padding-bottom: 10px !important;
    }

    /* Smooth transitions for buttons and inputs */
    button, input, textarea {
        transition: all 0.2s ease !important;
    }
</style>
""", unsafe_allow_html=True)

# ─── Title ────────────────────────────────────────────────

st.caption("Chat with AI to Process Invoices and Send Emails.")
st.caption("Just say 'Send this to customer@gmail.com' and the agent handles everything! 🚀")

# ═══════════════════════════════════════════════════════════
# CHATBOT INTERFACE
# ═══════════════════════════════════════════════════════════

# Display chat messages
for msg in st.session_state["chat_messages"]:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])
        if "attachment" in msg:
            st.info(f"📄 Attached: {msg['attachment']}")

# --- Check if credentials are filled ---
credentials_filled = bool(st.session_state["smtp_email"] and st.session_state["smtp_password"])

if not credentials_filled:
    st.warning("⚠️ **Credentials Needed**: Please provide your **Email** and **App Password** in the sidebar to send invoices.")

# --- Chat input with File Attachment (Built-in) ----
prompt_res = st.chat_input(
    "Ask anything...",
    accept_file=True,
    file_type=["pdf", "png", "jpg", "jpeg"],
    disabled=not credentials_filled
)

if prompt_res:
    # 1. Handle uploaded files
    new_files = getattr(prompt_res, "files", [])
    if not new_files and isinstance(prompt_res, dict):
        new_files = prompt_res.get("files", [])
        
    if new_files:
        for f in new_files:
            if not any(existing['name'] == f.name for existing in st.session_state["all_files"]):
                file_bytes = f.read()
                st.session_state["all_files"].append({"name": f.name, "bytes": file_bytes})
                st.session_state["chat_messages"].append({
                    "role": "user", 
                    "content": f"Attached invoice: {f.name}",
                    "attachment": f.name
                })
        
        # Update primary file pointers for backward compatibility
        if st.session_state["all_files"]:
            st.session_state["file_bytes"] = st.session_state["all_files"][0]["bytes"]
            st.session_state["file_name"] = st.session_state["all_files"][0]["name"]
        
        st.toast(f"{len(new_files)} file(s) added! Ready for processing.")

    # 2. Handle text prompt
    prompt = getattr(prompt_res, "text", "")
    if not prompt and isinstance(prompt_res, dict):
        prompt = prompt_res.get("text", "")
    elif not prompt and isinstance(prompt_res, str):
        prompt = prompt_res

    if prompt:
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.write(prompt)

        # ─── AGENTIC EXECUTION ─────────────────────────────
        # The agent autonomously decides what to do based on user input.
        # No regex matching or hardcoded routing — the LLM reasons about intent.
        with st.chat_message("assistant"):
            with st.status("Agent is thinking...", expanded=True) as status:
                try:
                    result = run_agent_chat(
                        user_input=prompt,
                        chat_history=st.session_state["chat_messages"][:-1],  # exclude current msg
                    )

                    tools_used = result.get("tools_used", [])
                    response = result["output"]

                    # Update status based on what tools the agent used
                    if tools_used:
                        tool_labels = []
                        for t in tools_used:
                            if t == "extract_invoice_tool":
                                tool_labels.append("Extracted invoice data")
                            elif t == "draft_email_tool":
                                tool_labels.append("Drafted email")
                            elif t == "send_email_tool":
                                tool_labels.append("Sent email")
                        status.update(
                            label=" → ".join(tool_labels) + " ✅",
                            state="complete"
                        )
                    else:
                        status.update(label="💬 Response ready", state="complete")

                except Exception as e:
                    response = f"I ran into an issue: {e}"
                    status.update(label="⚠️ Something went wrong", state="error")

            st.markdown(response)

            # Show review hint if a draft was created
            if st.session_state.get("step") == "review":
                st.info("💡 You can review and edit the draft below, or just say 'Yes' to send it.")

        st.session_state["chat_messages"].append({"role": "assistant", "content": response})


# ═══════════════════════════════════════════════════════════
# REVIEW & SENDING AREA
# ═══════════════════════════════════════════════════════════
if st.session_state["step"] == "review":
    st.markdown("---")
    st.markdown("### Review Email Draft")
    with st.container(border=True):
        st.markdown(f"**To:** {st.session_state.get('customer_email', '')}")
        
        # Use email_subject/email_body (set by agent tools) with fallback
        subject_val = st.session_state.get("email_subject") or st.session_state.get("subject") or ""
        body_val = st.session_state.get("email_body") or st.session_state.get("body") or ""
        
        st.session_state["email_subject"] = st.text_input("Subject", value=subject_val)
        st.session_state["email_body"] = st.text_area("Email Body", value=body_val, height=300)
        # Keep old keys in sync for backward compat
        st.session_state["subject"] = st.session_state["email_subject"]
        st.session_state["body"] = st.session_state["email_body"]

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🚀 Send Email", use_container_width=True, type="primary", disabled=not credentials_filled):
                st.session_state["step"] = "sending"
                st.rerun()
        with col2:
            if st.button("✖️ Cancel", use_container_width=True):
                st.session_state["step"] = "upload"
                st.rerun()

elif st.session_state["step"] == "sending":
    with st.spinner("Dispatching email..."):
        result_msg = send_email(
            to_email=st.session_state["customer_email"],
            subject=st.session_state.get("email_subject") or st.session_state.get("subject", ""),
            body=st.session_state.get("email_body") or st.session_state.get("body", ""),
            smtp_user=st.session_state["smtp_email"],
            smtp_password=st.session_state["smtp_password"],
            attachments=st.session_state.get("all_files", []),
        )
    if result_msg == "ok":
        st.session_state["step"] = "done"
        st.rerun()
    else:
        st.error(result_msg)
        st.session_state["step"] = "review"

elif st.session_state["step"] == "done":
    st.success(f"✅ Email sent successfully to {st.session_state['customer_email']}!")
    if st.button("Start New Case"):
        for key in ["subject", "body", "customer_email", "chat_messages", "file_bytes", 
                     "file_name", "all_files", "extracted_invoice_data", "email_subject", "email_body"]:
            st.session_state[key] = None if key not in ("chat_messages", "all_files") else []
        st.session_state["step"] = "upload"
        st.rerun()



