"""
LangGraph agent — two-node pipeline:
  1. extract_invoice  → Uses GPT-4o vision to read the uploaded invoice image
  2. draft_email      → Generates a professional email from the extracted data
"""

import json
import base64
from typing import Any, Dict, TypedDict, List
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage
from langgraph.graph import StateGraph, END
import streamlit as st
import config
from prompts import INVOICE_VISION_PROMPT, EMAIL_DRAFT_PROMPT, GENERAL_CHAT_SYSTEM_PROMPT
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

def chat_with_agent(messages: List[Dict], has_invoice: bool = False) -> str:
    """General conversational chat using gpt-oss-120b."""
    llm = _get_llm()
    
    # Prepare messages for LangChain
    lc_messages = [SystemMessage(content=GENERAL_CHAT_SYSTEM_PROMPT + f"\n\nContext: user_has_uploaded_invoice={has_invoice}")]
    
    for m in messages:
        if m["role"] == "user":
            lc_messages.append(HumanMessage(content=m["content"]))
        elif m["role"] == "assistant":
            lc_messages.append(AIMessage(content=m["content"]))
            
    try:
        response = llm.invoke(lc_messages)
        return response.content
    except Exception as e:
        return f"I'm sorry, I'm having trouble connecting right now. Error: {e}"

# ─── Graph State ──────────────────────────────────────────
class GraphState(TypedDict, total=False):
    image_data: List[str]         # list of base64-encoded images
    extracted_data: dict
    email_subject: str
    email_body: str
    error: str


# ─── LLM ─────────────────────────────────────────────────
def _get_llm():
    return ChatGroq(
        api_key=st.secrets["GROQ_API_KEY"],
        model="openai/gpt-oss-120b",
        temperature=config.TEMPERATURE,
       
    )


def _strip_json(text: str) -> str:
    """Remove markdown code fences if the LLM wraps its JSON."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1]
        text = text.rsplit("```", 1)[0]
    return text.strip()

# ─── NODE 1: Extract invoice data (Groq-compatible) ─────────────
def extract_invoice(state: GraphState) -> Dict[str, Any]:
    llm = _get_llm()
    images = state.get("image_data", [])

    try:
        from file_utils import image_to_text

        full_extracted_text = ""
        # Explicit type cast for linting
        image_list: List[str] = images 
        
        for idx, img_b64 in enumerate(image_list):
            img_bytes = base64.b64decode(img_b64)
            text = image_to_text(img_bytes)
            if text.strip():
                full_extracted_text += f"\n--- Page/Image {idx+1} ---\n{text}\n"

        if not full_extracted_text.strip():
            return {"error": "OCR failed to extract text from any of the provided images."}

        prompt = INVOICE_VISION_PROMPT + "\n\nExtracted invoice text:\n" + full_extracted_text

        response = llm.invoke(prompt)

        data = json.loads(_strip_json(response.content))
        return {"extracted_data": data}

    except Exception as e:
        return {"error": f"Failed to read invoice(s): {e}"}

# ─── NODE 2: Draft the email ─────────────────────────────
def draft_email(state: GraphState) -> Dict[str, Any]:
    """Generate a professional email from extracted invoice data."""
    if state.get("error"):
        return {}

    data = state["extracted_data"]
    llm = _get_llm()

    # Format line items for the prompt
    items_str = ""
    for item in data.get("line_items", []):
        if isinstance(item, dict):
            items_str += f"  - {item.get('description', '?')}: {item.get('amount', '?')}\n"
        else:
            items_str += f"  - {item}\n"

    # Sender Name from extracted data or config
    sender_name = data.get("sender_name") or config.SENDER_NAME or "the Billing Dept"

    prompt = EMAIL_DRAFT_PROMPT.format(
        sender_name=sender_name,
        company_name=config.COMPANY_NAME or "Our Company",
        sender_phone=config.SENDER_PHONE or "N/A",
        sender_email=config.SENDER_EMAIL or config.SMTP_EMAIL or "N/A",
        client_name=data.get("client_name", "Customer"),
        invoice_id=data.get("invoice_id", "N/A"),
        line_items=items_str.strip(),
        total_amount=data.get("total_amount", "N/A"),
    )

    try:
        response = llm.invoke(prompt)
        email = json.loads(_strip_json(response.content))
        return {
            "email_subject": email.get("subject", ""),
            "email_body": email.get("body", ""),
        }
    except Exception as e:
        return {"error": f"Failed to draft email: {e}"}


# ─── Build Graph ─────────────────────────────────────────
def build_graph():
    graph = StateGraph(GraphState)
    graph.add_node("extract_invoice", extract_invoice)
    graph.add_node("draft_email", draft_email)
    graph.set_entry_point("extract_invoice")
    graph.add_edge("extract_invoice", "draft_email")
    graph.add_edge("draft_email", END)
    return graph.compile()


def run_agent(image_data: List[str]) -> Dict[str, Any]:
    """Run the full pipeline. `image_data` is a list of base64-encoded images."""
    app = build_graph()
    return app.invoke({"image_data": image_data})
