import certifi
import stripe

import apps.payments.services  # noqa: F401  (sets stripe.ca_bundle_path on import)

COMPROMISED_EMUDHRA_ROOTS = (
    "emSign ECC Root CA - G3",
    "emSign ECC Root CA - C3",
    "emSign Root CA - C1",
)


def test_stripe_uses_certifi_bundle():
    assert stripe.ca_bundle_path == certifi.where()


def test_stripe_bundle_excludes_compromised_emudhra_roots():
    with open(stripe.ca_bundle_path, encoding="utf-8") as fh:
        bundle = fh.read()
    for root in COMPROMISED_EMUDHRA_ROOTS:
        assert root not in bundle, root
