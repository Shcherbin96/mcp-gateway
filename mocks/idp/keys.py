"""Static key material for the mock IdP service.

Generates an RSA keypair on import and exposes PEM-encoded private/public bytes,
plus the kid used in JWS headers and JWKS responses.
"""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


KID = "mock-idp-key-1"

KEY: rsa.RSAPrivateKey = rsa.generate_private_key(public_exponent=65537, key_size=2048)

PUBLIC_PEM: str = KEY.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

PRIVATE_PEM: bytes = KEY.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
