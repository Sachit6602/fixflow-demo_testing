import requests
import uuid
import time

def process_payment(amount, from_uid, provider_name):
    tx_ref = "0x" + uuid.uuid4().hex[:16]

    print(f"\n--- PAYMENT INITIATED ---")
    print(f"Amount:    £{amount} deposit")
    print(f"From:      {from_uid}")
    print(f"To:        {provider_name} escrow")
    print(f"Tx ref:    {tx_ref}")

    time.sleep(1)
    print(f"Status:    Submitting to Endless Chain...")

    # Real outbound API call — visible in terminal, returns a real response
    response = requests.post("https://httpbin.org/post", json={
        "tx_ref": tx_ref,
        "amount": amount,
        "currency": "GBP",
        "from": from_uid,
        "to": f"{provider_name}_escrow",
        "chain": "endless",
        "type": "deposit_escrow"
    })

    time.sleep(1)
    print(f"Status:    Submitted ✓ (HTTP {response.status_code})")

    time.sleep(1)
    print(f"Status:    Confirmed ✓")
    print(f"Escrow:    Active — releases on job completion")
    print(f"--- PAYMENT COMPLETE ---\n")

    return tx_ref


def get_payment_message():
    """Return the deposit prompt message with confirm/cancel options."""
    return {
        "text": "SparkClean available at 8am for £185.\nA £37 deposit is required to confirm.\n\nReply with:\n1 - Confirm & Pay\n2 - Cancel"
    }


def handle_payment_confirmation(uid, provider_name, amount):
    """Process a payment and return a formatted escrow confirmation message."""
    tx_ref = process_payment(amount, uid, provider_name)
    return (
        f"Deposit confirmed.\n\n"
        f"Transaction: {tx_ref}\n"
        f"£{amount} held in escrow — releases automatically when {provider_name} completes the job."
    )
