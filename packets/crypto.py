# packets/crypto.py
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from packets.config import Key, Iv

def EnC_AEs(HeX):
    cipher = AES.new(Key, AES.MODE_CBC, Iv)
    return cipher.encrypt(pad(bytes.fromhex(HeX), AES.block_size)).hex()

def EnC_PacKeT(HeX, K, V):
    return AES.new(K, AES.MODE_CBC, V).encrypt(pad(bytes.fromhex(HeX), 16)).hex()

def DEc_PacKeT(HeX, K, V):
    return unpad(AES.new(K, AES.MODE_CBC, V).decrypt(bytes.fromhex(HeX)), 16).hex()

def DecodE_HeX(H):
    R = hex(H)
    F = str(R)[2:]
    if len(F) == 1: F = "0" + F
    return F

# packets/crypto.py ফাইলে নিচের ফাংশনগুলো যোগ করুন:

def YOuR_FaThER(uid):
    n = int(uid)
    res = bytearray()
    while n >= 0x80:
        res.append((n & 0x7f) | 0x80)
        n >>= 7
    res.append(n)
    
    payload_bytes = b"\x08" + bytes(res)
    cipher = AES.new(Key, AES.MODE_CBC, Iv)
    return cipher.encrypt(pad(payload_bytes, 16))

def UNknown(d):
    try:
        return unpad(AES.new(Key, AES.MODE_CBC, Iv).decrypt(d), 16)
    except:
        return d
