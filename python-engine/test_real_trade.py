
import requests
import json
import time

# Endpoint URL (Pastikan Python Engine running di port 8001)
url_entry = "http://127.0.0.1:8001/execute/entry"
url_close = "http://127.0.0.1:8001/execute/close"

# 1. SETUP PARAMETER (Margin $1)
margin_usdt = 1.0
leverage = 20
notional_value = margin_usdt * leverage  # $20

payload = {
    "symbol": "DOGE/USDT", 
    "side": "SHORT",       
    "amount_usdt": notional_value, 
    "leverage": leverage
}

print(f"\n🚀 TEST REAL TRADE: Margin ${margin_usdt} x {leverage} = Notional ${notional_value}")
print("==================================================")

# 2. EXECUTE ENTRY
try:
    print(f"📡 Sending Entry Order: {payload['side']} {payload['symbol']}...")
    resp = requests.post(url_entry, json=payload)
    
    if resp.status_code == 200:
        data = resp.json()
        print("✅ Entry SUCCESS!")
        print(json.dumps(data, indent=2))
        
        executed_qty = data.get("executedQty")
        if not executed_qty:
            print("❌ No qty returned, cannot close.")
            exit()
            
        print("\n⏳ Waiting 5 seconds before closing...")
        time.sleep(5)
        
        # 3. EXECUTE CLOSE (Opsional - biar gak nyangkut)
        close_payload = {
            "symbol": payload["symbol"],
            "side": "BUY", # Lawan dari SHORT
            "quantity": float(executed_qty)
        }
        print(f"\n📡 Closing Position: {close_payload['side']} {executed_qty} {payload['symbol']}...")
        close_resp = requests.post(url_close, json=close_payload)
        print("✅ Close Result:", json.dumps(close_resp.json(), indent=2))
        
    else:
        print("❌ Entry FAILED:", resp.text)

except Exception as e:
    print("❌ Fatal Error:", e)

print("==================================================")
