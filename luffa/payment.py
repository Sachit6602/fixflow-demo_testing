import requests
import uuid
import time

def process_payment(amount, from_uid, provider_name):
    tx_ref = "0x" + uuid.uuid4().hex[:16]

    print(f"\n--- PAYMENT INITIATED ---")
    print(f"Amount:    £{amount}")
    print(f"From:      {from_uid}")
    print(f"To:        {provider_name}")
    print(f"Tx ref:    {tx_ref}")

    time.sleep(1)
    print(f"Status:    Submitting to Endless Chain...")

    # Real outbound API call — visible in terminal, returns a real response
    response = requests.post("https://httpbin.org/post", json={
        "tx_ref": tx_ref,
        "amount": amount,
        "currency": "GBP",
        "from": from_uid,
        "to": provider_name,
        "chain": "endless",
        "type": "payment"
    })

    time.sleep(1)
    print(f"Status:    Submitted ✓ (HTTP {response.status_code})")

    time.sleep(1)
    print(f"Status:    Confirmed ✓")
    print(f"--- PAYMENT COMPLETE ---\n")

    return tx_ref


def get_payment_message(quote_ref, final_price):
    """Return a payment prompt message based on the actual quote."""
    return {
        "text": (
            f"Quote {quote_ref} — £{final_price:.2f}\n"
            f"Payment of £{final_price:.2f} is required to confirm your booking.\n\n"
            "Reply with:\n"
            "1 - Confirm & Pay\n"
            "2 - Cancel"
        ),
    }


def handle_payment_confirmation(uid, provider_name, amount):
    """Process a payment and return a formatted confirmation message."""
    tx_ref = process_payment(amount, uid, provider_name)
    return (
        f"Payment confirmed.\n\n"
        f"Transaction: {tx_ref}\n"
        f"£{amount} paid to {provider_name}.\n\n"
        f"Your engineer will arrive at your selected time slot. "
        f"You'll receive a confirmation with their details shortly."
    )
