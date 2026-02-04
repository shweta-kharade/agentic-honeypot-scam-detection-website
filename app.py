import httpx
import asyncio
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel
from datetime import datetime
import re
import random
import uvicorn
from typing import Dict, List, Optional
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Agentic Honey-Pot API",
    description="AI-powered scam detection and intelligence extraction system",
    version="2.1",
    docs_url="/docs",
    redoc_url="/redoc"
)

# ========== CONFIGURATION ==========
API_KEYS = {
    os.getenv("API_KEY", "hackathon-submission-2026"): ["admin"]
}

TEAM_KEYS = {
    "hackathon-submission-2026": ["admin"],
    "hackathon-judge-key": ["judge"],
}

API_KEYS.update(TEAM_KEYS)

CALLBACK_URL = os.getenv(
    "CALLBACK_URL",
    "https://mock-scammer-api.example.com/callback"
)

# ========== API KEY AUTH ==========
async def verify_api_key(api_key: str = Header(..., alias="X-API-Key")):
    if api_key not in API_KEYS:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key

# ========== MODELS ==========
class MessageRequest(BaseModel):
    message_text: str
    conversation_id: str = "default"

class ResponseData(BaseModel):
    response_text: str
    scam_detected: bool
    agent_engaged: bool
    confidence: float
    extracted_data: dict
    timestamp: str
    conversation_id: str
    next_action: str
    metrics: Optional[dict] = None

# ========== RATE LIMIT ==========
rate_limits = {}

def check_rate_limit(api_key: str):
    key = f"{api_key}_{datetime.now().strftime('%Y-%m-%d %H:%M')}"
    rate_limits[key] = rate_limits.get(key, 0) + 1
    if rate_limits[key] > 100:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

# ========== SCAM DETECTOR ==========
def detect_scam(text):
    patterns = [
        (r"urgent|verify|account blocked", 0.4),
        (r"http[s]?://|www\.", 0.5),
        (r"upi|bank|transfer|payment", 0.4),
    ]
    score = 0
    triggers = []
    for p, w in patterns:
        if re.search(p, text, re.I):
            score += w
            triggers.append(p)
    return score >= 0.7, min(score, 1.0), triggers

# ========== INTELLIGENCE EXTRACTOR ==========
def extract_intelligence(text):
    raw_upi = re.findall(r'([\w\.-]+@(ybl|axl|okaxis|oksbi|paytm))', text, re.I)
    upi_ids = [u[0] for u in raw_upi]

    return {
        "upi_ids": list(set(upi_ids)),
        "bank_accounts": list(set(re.findall(r'\b\d{9,18}\b', text))),
        "phone_numbers": list(set(re.findall(r'\b[6-9]\d{9}\b', text))),
        "urls": [{"url": u, "is_suspicious": True} for u in re.findall(r'https?://[^\s]+', text)],
        "keywords": [k for k in ["urgent", "verify", "account", "payment", "click"] if k in text.lower()]
    }

# ========== AGENT ==========
def get_agent_response(is_scam, extracted, turn):
    if not is_scam:
        return "Thanks for the message.", False, "end"

    responses = [
        "Can you send the details again?",
        "That didn’t work. Do you have another account?",
        "Please confirm the payment method."
    ]

    should_end = (
        turn >= 4
        and extracted["upi_ids"]
        and extracted["bank_accounts"]
    )

    return random.choice(responses), True, "end" if should_end else "continue"

# ========== CONVERSATION STATE ==========
conversations = {}

def manage_conversation(cid, user_msg, agent_msg, is_scam, extracted):
    if cid not in conversations:
        conversations[cid] = {
            "start_time": datetime.now().isoformat(),
            "messages": [],
            "scam_detected": False,
            "agent_engaged": False,
            "extracted_intelligence": {},
            "callback_sent": False
        }

    conv = conversations[cid]
    conv["messages"].append({"user": user_msg, "agent": agent_msg})

    if is_scam:
        conv["scam_detected"] = True
        conv["agent_engaged"] = True

    for k, v in extracted.items():
        if isinstance(v, list):
            conv["extracted_intelligence"].setdefault(k, [])
            conv["extracted_intelligence"][k] = list(
                set(conv["extracted_intelligence"][k] + v)
            )

    return {
        "turn_count": len(conv["messages"]),
        "scam_detected": conv["scam_detected"]
    }

# ========== CALLBACK ==========
async def send_callback(conversation_id, extracted, total_messages):
    payload = {
        "sessionId": conversation_id,
        "scamDetected": True,
        "totalMessagesExchanged": total_messages,
        "extractedIntelligence": {
            "bankAccounts": extracted.get("bank_accounts", []),
            "upiIds": extracted.get("upi_ids", []),
            "phishingLinks": [u["url"] for u in extracted.get("urls", [])],
            "phoneNumbers": extracted.get("phone_numbers", []),
            "suspiciousKeywords": extracted.get("keywords", [])
        },
        "agentNotes": "Scammer used urgency and payment redirection tactics"
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.post(CALLBACK_URL, json=payload)
            return res.status_code in (200, 201)
    except Exception as e:
        print(f"[CALLBACK ERROR] {e}")
        return False

# ========== MAIN ENDPOINT ==========
@app.post("/api/v1/process", response_model=ResponseData)
async def process_message(req: MessageRequest, api_key: str = Depends(verify_api_key)):
    check_rate_limit(api_key)

    is_scam, confidence, _ = detect_scam(req.message_text)
    extracted = extract_intelligence(req.message_text)

    turn = len(conversations.get(req.conversation_id, {}).get("messages", [])) + 1
    response_text, agent_engaged, next_action = get_agent_response(is_scam, extracted, turn)

    metrics = manage_conversation(
        req.conversation_id,
        req.message_text,
        response_text,
        is_scam,
        extracted
    )

    conv = conversations[req.conversation_id]

    # ✅ FINAL CALLBACK TRIGGER (ONCE)
    if (
        conv["scam_detected"]
        and next_action == "end"
        and not conv["callback_sent"]
    ):
        if await send_callback(
            req.conversation_id,
            conv["extracted_intelligence"],
            len(conv["messages"])
        ):
            conv["callback_sent"] = True

    return ResponseData(
        response_text=response_text,
        scam_detected=is_scam,
        agent_engaged=agent_engaged,
        confidence=confidence,
        extracted_data=extracted,
        timestamp=datetime.now().isoformat(),
        conversation_id=req.conversation_id,
        next_action=next_action,
        metrics=metrics
    )

# ========== RUN ==========
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))





# import httpx  # Add this line
# import asyncio  # Add this line
# from fastapi import FastAPI, HTTPException, Depends, Header
# from pydantic import BaseModel
# from datetime import datetime
# import re
# import random
# import uvicorn
# from typing import Dict, List, Optional
# import os
# from dotenv import load_dotenv
# import secrets

# # Load environment variables
# load_dotenv()

# app = FastAPI(
#     title="Agentic Honey-Pot API",
#     description="AI-powered scam detection and intelligence extraction system",
#     version="2.0",
#     docs_url="/docs",
#     redoc_url="/redoc"
# )

# # ========== CONFIGURATION ==========
# API_KEYS = {
#     os.getenv("API_KEY", "hackathon-submission-2026"): ["admin"]  # Default key for submission
# }

# # Add your team's API keys
# TEAM_KEYS = {
#     "hackathon-submission-2026": ["admin"],
#     "hackathon-judge-key": ["judge"],  # For judges to test
# }

# API_KEYS.update(TEAM_KEYS)

# # ========== API KEY AUTHENTICATION ==========
# async def verify_api_key(api_key: str = Header(..., alias="X-API-Key")):
#     """Verify API key from header"""
#     if api_key not in API_KEYS:
#         raise HTTPException(
#             status_code=403,
#             detail="Invalid API key. Please use a valid key from your team."
#         )
#     return api_key

# # ========== MODELS ==========
# class MessageRequest(BaseModel):
#     message_text: str
#     conversation_id: str = "default"
#     message_id: Optional[str] = None
#     sender_id: Optional[str] = None

# class ResponseData(BaseModel):
#     response_text: str
#     scam_detected: bool
#     agent_engaged: bool
#     confidence: float
#     extracted_data: dict
#     timestamp: str
#     conversation_id: str
#     next_action: str = "continue"
#     metrics: Optional[dict] = None

# class APIKeyResponse(BaseModel):
#     team_name: str
#     api_key: str
#     valid_until: str
#     rate_limit: str

# # ========== RATE LIMITING ==========
# rate_limits = {}

# def check_rate_limit(api_key: str):
#     """Simple rate limiting"""
#     current_minute = datetime.now().strftime("%Y-%m-%d %H:%M")
#     key_minute = f"{api_key}_{current_minute}"
    
#     if key_minute not in rate_limits:
#         rate_limits[key_minute] = 0
    
#     rate_limits[key_minute] += 1
    
#     # Limit to 100 requests per minute per key
#     if rate_limits[key_minute] > 100:
#         raise HTTPException(
#             status_code=429,
#             detail="Rate limit exceeded. Max 100 requests per minute."
#         )
    
#     return True

# # ========== SCAM DETECTOR ==========
# def detect_scam(text):
#     """Improved scam detection"""
#     patterns = [
#         (r"(?i)urgent|immediate|hurry|asap", 0.3),
#         (r"(?i)bank account|upi id|payment|transfer|money", 0.4),
#         (r"(?i)click|http[s]?://|www\.|link", 0.5),
#         (r"(?i)lottery|prize|winner|reward|bonus", 0.6),
#         (r"(?i)password|login|verify|authenticate|credentials", 0.4),
#         (r"(?i)dear|sir|madam|customer|user", 0.2),
#         (r"(?i)kindly|please help|request|cooperate", 0.2),
#         (r"\d{9,18}", 0.3),
#         (r"@(ybl|axl|okaxis|oksbi|paytm)", 0.5),
#     ]
    
#     score = 0
#     triggers = []
    
#     for pattern, weight in patterns:
#         if re.search(pattern, text, re.IGNORECASE):
#             score += weight
#             triggers.append(pattern)
    
#     return score >= 0.7, min(score, 1.0), triggers

# # ========== INTELLIGENCE EXTRACTOR ==========
# def extract_intelligence(text):
#     """Extract useful information"""
#     # UPI IDs
#     upi_patterns = [
#         r'[\w\.-]+@(ybl|axl|okaxis|oksbi|paytm)',
#         r'\b\d{10,12}@(ybl|axl|upi)',
#     ]
#     upi_ids = []
#     for pattern in upi_patterns:
#         upi_ids.extend(re.findall(pattern, text, re.IGNORECASE))
    
#     # Bank accounts
#     accounts = re.findall(r'\b\d{9,18}\b', text)
#     filtered_accounts = [acc for acc in accounts if len(set(acc)) > 1]
    
#     # Phone numbers
#     phones = re.findall(r'\b[6789]\d{9}\b', text)
    
#     # URLs
#     urls = re.findall(r'https?://[^\s<>"\']+|www\.[^\s<>"\']+\.[^\s<>"\']+', text)
#     url_details = []
#     for url in urls:
#         url_details.append({
#             "url": url,
#             "is_suspicious": any(keyword in url.lower() for keyword in ['login', 'verify', 'secure']),
#             "domain": url.split('//')[-1].split('/')[0] if '//' in url else url.split('/')[0]
#         })
    
#     # Keywords
#     keywords = ["urgent", "verify", "password", "login", "account", "prize", 
#                 "winner", "transfer", "payment", "click", "link", "dear"]
#     found_keywords = [word for word in keywords if word in text.lower()]
    
#     # Scammer techniques
#     techniques = []
#     if "kindly" in text.lower():
#         techniques.append("polite_pressure")
#     if "urgent" in text.lower() and "click" in text.lower():
#         techniques.append("urgency_clickbait")
#     if "prize" in text.lower() and "transfer" in text.lower():
#         techniques.append("prize_scam")
    
#     data = {
#         "upi_ids": list(set(upi_ids)),
#         "bank_accounts": filtered_accounts,
#         "phone_numbers": list(set(phones)),
#         "urls": url_details,
#         "keywords": found_keywords,
#         "techniques": techniques
#     }
    
#     return data

# # ========== SCAMMER PROFILER ==========
# def profile_scammer(text, conversation_history=None):
#     score = 0
#     red_flags = []
    
#     # Content analysis
#     if "urgent" in text.lower():
#         score += 1
#         red_flags.append("urgency_tactic")
#     if "upi" in text.lower() or "bank" in text.lower():
#         score += 1
#         red_flags.append("financial_request")
#     if "click" in text.lower() or "http" in text.lower():
#         score += 1
#         red_flags.append("link_sharing")
#     if "prize" in text.lower() or "winner" in text.lower():
#         score += 1
#         red_flags.append("prize_bait")
#     if "kindly" in text.lower() or "dear" in text.lower():
#         score += 0.5
#         red_flags.append("formal_greeting")
    
#     # Context analysis
#     if conversation_history and len(conversation_history) > 0:
#         last_message = conversation_history[-1].get("user", "").lower()
#         if "?" in last_message and "send" in text.lower():
#             score += 1
#             red_flags.append("immediate_followup")
    
#     # Determine risk level
#     if score >= 3:
#         risk_level = "CRITICAL"
#     elif score >= 2:
#         risk_level = "HIGH"
#     elif score >= 1:
#         risk_level = "MEDIUM"
#     else:
#         risk_level = "LOW"
    
#     # Determine scam type
#     scam_type = "unknown"
#     if "upi" in text.lower():
#         scam_type = "upi_fraud"
#     elif "login" in text.lower() and "http" in text.lower():
#         scam_type = "phishing"
#     elif "prize" in text.lower() and "transfer" in text.lower():
#         scam_type = "lottery_scam"
#     elif "bank" in text.lower() and "account" in text.lower():
#         scam_type = "bank_fraud"
    
#     return {
#         "risk_level": risk_level,
#         "intent_score": score,
#         "red_flags": red_flags,
#         "scam_type": scam_type,
#         "timestamp": datetime.now().isoformat()
#     }

# # ========== AGENT RESPONSES ==========
# def get_agent_response(is_scam, extracted, profile, conversation_turn):
#     if not is_scam:
#         return "Thanks for your message.", False, "end"
    
#     # Different responses based on conversation turn
#     if conversation_turn == 1:
#         responses = [
#             "Can you explain how this works? I'm not very tech-savvy.",
#             "This sounds interesting. How do I proceed?",
#             "I've never won anything before! What should I do next?",
#         ]
#     elif conversation_turn == 2:
#         if extracted["upi_ids"]:
#             responses = [
#                 "I tried that UPI ID but it says invalid. Can you check and send again?",
#                 "My phone shows an error for that UPI. Maybe send another one?",
#                 "That UPI isn't working. Do you have a different one?"
#             ]
#         elif extracted["urls"]:
#             responses = [
#                 "The link isn't opening on my phone. Can you resend it?",
#                 "I clicked but it says page not found. Is there another link?",
#                 "My browser says the site is unsafe. Do you have a different website?"
#             ]
#         else:
#             responses = [
#                 "Can you explain this step by step? I'm a bit confused.",
#                 "What app should I use for this? I have Google Pay and PhonePe.",
#                 "Should I do this on mobile or computer?"
#             ]
#     else:
#         if not extracted["bank_accounts"]:
#             responses = [
#                 "For bank transfer, which account should I send to?",
#                 "Can you share the account number and IFSC code?",
#                 "Which bank and branch should I use?"
#             ]
#         elif not extracted["phone_numbers"]:
#             responses = [
#                 "Should I call you to confirm? What's your number?",
#                 "Can I WhatsApp you for quick confirmation?",
#                 "What's the best number to reach you?"
#             ]
#         else:
#             responses = [
#                 "Just to confirm, I should send ₹____ to account ____, right?",
#                 "Let me double-check: UPI ____, phone ____, account ____?",
#                 "I'll proceed now. Is there anything else I need to know?"
#             ]
    
#     response_text = random.choice(responses)
    
#     # Determine if we should end conversation
#     should_end = conversation_turn > 5 or (len(extracted["upi_ids"]) > 0 and len(extracted["bank_accounts"]) > 0)
#     next_action = "end" if should_end else "continue"
    
#     if should_end:
#         response_text += " [I'll proceed with this now. Thank you!]"
    
#     return response_text, True, next_action

# # ========== CONVERSATION MANAGER ==========
# conversations = {}

# def manage_conversation(conv_id, message, response, is_scam, extracted, profile):
#     if conv_id not in conversations:
#         conversations[conv_id] = {
#             "start_time": datetime.now().isoformat(),
#             "messages": [],
#             "scam_detected": False,
#             "agent_engaged": False,
#             "extracted_intelligence": {},
#             "profiles": [],
                
#             "callback_sent": False

#         }
    
#     conv = conversations[conv_id]
#     conv["messages"].append({
#         "user": message,
#         "agent": response,
#         "scam": is_scam,
#         "time": datetime.now().isoformat()
#     })
    
#     if is_scam and not conv["agent_engaged"]:
#         conv["agent_engaged"] = True
#         conv["scam_detected"] = True
    
#     # Merge extracted intelligence
#     if not conv["extracted_intelligence"]:
#         conv["extracted_intelligence"] = extracted
#     else:
#         for key in extracted:
#             if key in conv["extracted_intelligence"]:
#                 existing = conv["extracted_intelligence"][key]
#                 new = extracted[key]
#                 if isinstance(existing, list) and isinstance(new, list):
#                     conv["extracted_intelligence"][key] = list(set(existing + new))
    
#     conv["profiles"].append(profile)
    
#     turn_count = len(conv["messages"])
#     duration = (datetime.now() - datetime.fromisoformat(conv["start_time"])).total_seconds()
    
#     return {
#         "turn_count": turn_count,
#         "duration_seconds": duration,
#         "agent_engaged": conv["agent_engaged"],
#         "scam_detected": conv["scam_detected"],
#         "total_intelligence_items": sum(len(v) if isinstance(v, list) else 0 for v in conv["extracted_intelligence"].values())
#     }

# # ========== MAIN API ENDPOINT (PROTECTED) ==========
# @app.post("/api/v1/process", response_model=ResponseData)
# async def process_message(
#     request: MessageRequest,
#     api_key: str = Depends(verify_api_key)
# ):
#     """Process scam messages - Requires API Key"""
#     try:
#         # Check rate limit
#         check_rate_limit(api_key)
        
#         # Detect scam
#         is_scam, confidence, triggers = detect_scam(request.message_text)
        
#         # Extract intelligence
#         extracted = extract_intelligence(request.message_text)
        
#         # Get conversation history
#         conv_history = []
#         if request.conversation_id in conversations:
#             conv_history = conversations[request.conversation_id]["messages"]
        
#         # Profile scammer
#         profile = profile_scammer(request.message_text, conv_history)
        
#         # Get conversation turn
#         turn_count = len(conv_history) + 1
        
#         # Generate response
#         response_text, agent_engaged, next_action = get_agent_response(is_scam, extracted, profile, turn_count)
        
#         # Manage conversation
#         metrics = manage_conversation(
#             request.conversation_id,
#             request.message_text,
#             response_text,
#             is_scam,
#             extracted,
#             profile
#         )
        
#         # Prepare final extracted data
#         final_extracted = {
#             **extracted,
#             "profile": profile,
#             "triggers": triggers,
#             "detection_confidence": confidence
#         }
        
#         # Return response
#         return ResponseData(
#             response_text=response_text,
#             scam_detected=is_scam,
#             agent_engaged=agent_engaged,
#             confidence=confidence,
#             extracted_data=final_extracted,
#             timestamp=datetime.now().isoformat(),
#             conversation_id=request.conversation_id,
#             next_action=next_action,
#             metrics=metrics
#         )
        
#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))

# # ========== PROTECTED ENDPOINTS ==========
# @app.get("/api/v1/conversations")
# async def get_all_conversations(api_key: str = Depends(verify_api_key)):
#     """Get all active conversations - Requires API Key"""
#     summary = {}
#     for conv_id, conv in conversations.items():
#         summary[conv_id] = {
#             "start_time": conv["start_time"],
#             "message_count": len(conv["messages"]),
#             "scam_detected": conv["scam_detected"],
#             "agent_engaged": conv["agent_engaged"],
#             "last_activity": conv["messages"][-1]["time"] if conv["messages"] else None
#         }
#     return summary

# @app.get("/api/v1/stats")
# async def get_stats(api_key: str = Depends(verify_api_key)):
#     """Get statistics - Requires API Key"""
#     total_scams = sum(1 for conv in conversations.values() if conv["scam_detected"])
#     total_intel = 0
#     for conv in conversations.values():
#         total_intel += sum(len(v) if isinstance(v, list) else 0 
#                           for v in conv["extracted_intelligence"].values())
    
#     return {
#         "total_conversations": len(conversations),
#         "total_scam_conversations": total_scams,
#         "total_messages": sum(len(conv["messages"]) for conv in conversations.values()),
#         "total_intelligence_items": total_intel,
#         "active_api_keys": len(API_KEYS),
#         "uptime": "running"
#     }

# # ========== PUBLIC ENDPOINTS (No API Key Required) ==========
# @app.get("/")
# async def home():
#     """Public home page"""
#     return {
#         "service": "Agentic Honey-Pot API",
#         "version": "2.0",
#         "status": "running",
#         "description": "AI-powered scam detection and intelligence extraction",
#         "documentation": "/docs",
#         "health_check": "/health",
#         "note": "Main endpoint requires API key. Contact team for access."
#     }

# @app.get("/health")
# async def health():
#     """Public health check"""
#     return {
#         "status": "healthy",
#         "timestamp": datetime.now().isoformat(),
#         "service": "agentic-honeypot",
#         "version": "2.0"
#     }

# @app.get("/api/v1/generate-key/{team_name}")
# async def generate_api_key(team_name: str):
#     """Generate a new API key for your team"""
#     # For demo purposes - in production, use proper key generation
#     if team_name.lower() in ["judge", "admin", "hackathon"]:
#         raise HTTPException(status_code=400, detail="Team name reserved")
    
#     new_key = f"{team_name}-{secrets.token_hex(8)}"
#     API_KEYS[new_key] = [team_name]
    
#     return {
#         "team_name": team_name,
#         "api_key": new_key,
#         "message": "Save this key securely!",
#         "endpoint": "Use: POST /api/v1/process with header: X-API-Key: your-key",
#         "rate_limit": "100 requests per minute",
#         "valid_until": "2024-12-31"
#     }

# # ========== CALLBACK FUNCTION ==========
# async def send_callback_endpoint(conversation_id: str, extracted_intelligence: dict, total_messages: int):
#     """
#     Send final callback to the evaluation system
#     This should be called when scam detection is complete
#     """
#     # TODO: Replace with actual callback URL from hackathon
#     callback_url = "https://mock-scammer-api.example.com/callback"
    
#     # Prepare extracted intelligence in required format
#     intelligence = {
#         "bankAccounts": extracted_intelligence.get("bank_accounts", []),
#         "upiIds": extracted_intelligence.get("upi_ids", []),
#         "phishingLinks": [url["url"] for url in extracted_intelligence.get("urls", []) if url.get("is_suspicious")],
#         "phoneNumbers": extracted_intelligence.get("phone_numbers", []),
#         "suspiciousKeywords": extracted_intelligence.get("keywords", [])
#     }
    
#     # Prepare agent notes
#     techniques = extracted_intelligence.get("techniques", [])
#     profile = extracted_intelligence.get("profile", {})
    
#     agent_notes = "Scammer "
#     if techniques:
#         agent_notes += f"used {', '.join(techniques)} techniques. "
#     if profile.get("red_flags"):
#         agent_notes += f"Red flags: {', '.join(profile.get('red_flags', []))}. "
#     if profile.get("risk_level"):
#         agent_notes += f"Risk level: {profile.get('risk_level')}."
    
#     payload = {
#         "sessionId": conversation_id,
#         "scamDetected": True,
#         "totalMessagesExchanged": total_messages,
#         "extractedIntelligence": intelligence,
#         "agentNotes": agent_notes
#     }
    
#     try:
#         async with httpx.AsyncClient(timeout=10.0) as client:
#             response = await client.post(
#                 callback_url,
#                 json=payload,
#                 headers={"Content-Type": "application/json"}
#             )
            
#             if response.status_code in [200, 201]:
#                 print(f"✅ Callback sent for session: {conversation_id}")
#                 return True
#             else:
#                 print(f"❌ Callback failed: {response.status_code}")
#                 return False
                
#     except Exception as e:
#         print(f"❌ Error sending callback: {e}")
#         return False

# # ========== RUN THE SERVER ==========
# if __name__ == "__main__":
#     port = int(os.getenv("PORT", 8000))
    
#     print("\n" + "="*70)
#     print(" AGENTIC HONEY-POT API v2.0")
#     print("="*70)
#     print("\n FEATURES:")
#     print("   • API Key Authentication (X-API-Key header)")
#     print("   • Rate Limiting (100 requests/minute)")
#     print("   • Scam Detection & Intelligence Extraction")
#     print("   • Multi-turn Conversation Management")
#     print("   • Public & Protected Endpoints")
    
#     print("\n API KEYS AVAILABLE:")
#     for key, teams in API_KEYS.items():
#         print(f"   • {key[:20]}... -> Teams: {', '.join(teams)}")
    
#     print("\n ENDPOINTS:")
#     print("   • GET  /                    - Public info")
#     print("   • GET  /health              - Health check")
#     print("   • POST /api/v1/process      - Process messages (requires API key)")
#     print("   • GET  /api/v1/conversations- View conversations (requires API key)")
#     print("   • GET  /api/v1/stats        - Statistics (requires API key)")
#     print("   • GET  /api/v1/generate-key/{team} - Generate API key")
    
#     print("\n TEST COMMAND:")
#     print('   curl -X POST http://localhost:8000/api/v1/process \\')
#     print('     -H "Content-Type: application/json" \\')
#     print('     -H "X-API-Key: hackathon-submission-2024" \\')
#     print('     -d \'{"message_text": "Test scam message", "conversation_id": "test1"}\'')
    
#     print("\n" + "="*70)
#     print(f"Server starting on port {port}...")
#     print("="*70 + "\n")
    

#     uvicorn.run(app, host="0.0.0.0", port=port, reload=False)

