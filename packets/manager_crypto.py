# START OF FILE: packets/manager_crypto.py
import base64
import json
from Crypto.Cipher import AES
from google.protobuf import json_format
from google.protobuf.message import Message

MAIN_KEY = base64.b64decode('WWcmdGMlREV1aDYlWmNeOA==')
MAIN_IV = base64.b64decode('Nm95WkRyMjJFM3ljaGpNJQ==')
RELEASEVERSION = "OB54"

def pad(text: bytes) -> bytes:
    padding_length = AES.block_size - (len(text) % AES.block_size)
    return text + bytes([padding_length] * padding_length)

def normalize_key_iv(val) -> bytes:
    if isinstance(val, str):
        val = val.strip()
        if len(val) == 32:
            try: return bytes.fromhex(val)
            except ValueError: pass
        return val.encode('utf-8')[:16].ljust(16, b'\x00')
    elif isinstance(val, bytes):
        if len(val) == 32:
            try: return bytes.fromhex(val.decode('utf-8', errors='ignore'))
            except Exception: pass
        return val[:16].ljust(16, b'\x00')
    try: return bytes(val)[:16].ljust(16, b'\x00')
    except Exception: return b'\x00' * 16

def aes_cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    norm_key = normalize_key_iv(key)
    norm_iv = normalize_key_iv(iv)
    aes = AES.new(norm_key, AES.MODE_CBC, norm_iv)
    return aes.encrypt(pad(plaintext))

def decode_protobuf(encoded_data: bytes, message_type):
    instance = message_type()
    instance.ParseFromString(encoded_data)
    return instance

async def json_to_proto(json_data: str, proto_message: Message) -> bytes:
    json_format.ParseDict(json.loads(json_data), proto_message)
    return proto_message.SerializeToString()
