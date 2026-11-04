from src.tenant_provisioning import PaymentEvent, decide_payment


def test_new_tenant_high_value_payment_is_reviewed():
    event = PaymentEvent("clinic-7", 600_000, "USD", "US", 2)
    assert decide_payment(event).status == "review"
