# START OF FILE: packets/bio_duo_api.py
import time
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from packets.central_login import get_http_session
from packets.config import Key, Iv
from packets.crypto import YOuR_FaThER, UNknown
from packets.protobuf import SpecialFriendResponse

def create_long_bio_proto(bio_text):
    field_2 = b'\x10\x11'
    field_5 = b'\x2A\x00'
    field_6 = b'\x32\x00'
    
    bio_bytes = bio_text.encode('utf-8')
    bio_len = len(bio_bytes)
    
    def encode_varint(value):
        encoded = []
        while value > 127:
            encoded.append((value & 0x7F) | 0x80)
            value >>= 7
        encoded.append(value)
        return bytes(encoded)
    
    field_8 = b'\x42' + encode_varint(bio_len) + bio_bytes
    field_9 = b'\x48\x01'
    field_11 = b'\x5A\x00'
    field_12 = b'\x62\x00'
    return field_2 + field_5 + field_6 + field_8 + field_9 + field_11 + field_12

async def update_bio(jwt_token, bio_text, regional_base_url):
    try:
        url = f"{regional_base_url}/UpdateSocialBasicInfo"
        proto_data = create_long_bio_proto(bio_text)
        
        cipher = AES.new(Key, AES.MODE_CBC, Iv)
        encrypted_data = cipher.encrypt(pad(proto_data, 16))
        
        headers = {
            "Expect": "100-continue", "Authorization": f"Bearer {jwt_token}",
            "X-Unity-Version": "2018.4.11f1", "X-GA": "v1 1",
            "ReleaseVersion": "OB54", "Content-Type": "application/x-www-form-urlencoded",
            "Connection": "Keep-Alive", "Accept-Encoding": "gzip"
        }
        
        session = await get_http_session()
        async with session.post(url, headers=headers, data=encrypted_data, ssl=False) as response:
            if response.status == 200: return True, "Signature updated successfully!"
            else: return False, f"HTTP {response.status}"
    except Exception as e:
        return False, str(e)

async def check_duo(jwt_token, target_uid, regional_base_url):
    try:
        url = f"{regional_base_url}/GetSpecialFriendList"
        headers = {
            "Authorization": f"Bearer {jwt_token}", "Content-Type": "application/x-www-form-urlencoded",
            "X-Unity-Version": "2018.4.11f1", "X-GA": "v1 1",
            "ReleaseVersion": "OB54", "Connection": "Keep-Alive"
        }
        payload = YOuR_FaThER(target_uid)
        
        session = await get_http_session()
        async with session.post(url, headers=headers, data=payload, ssl=False) as response:
            if response.status == 200:
                data = await response.read()
                dec_data = UNknown(data)
                
                resp_proto = SpecialFriendResponse()
                resp_proto.ParseFromString(dec_data)
                
                if not resp_proto.HasField("duo_info"):
                    return False, "No Dynamic Duo info found for this player."
                    
                duo = resp_proto.duo_info
                score = duo.score
                if score < 101: lvl = 1
                elif score < 301: lvl = 2
                elif score < 501: lvl = 3
                elif score < 801: lvl = 4
                elif score < 1201: lvl = 5
                else: lvl = 6
                
                status = "Active" if duo.status == 2 else "Inactive"
                creation_time = time.strftime('%B %d, %Y', time.localtime(duo.creation_timestamp))
                
                info = {
                    "Partner UID": str(duo.partner_uid),
                    "Level": lvl, "Score": score, "Active Days": duo.days_active,
                    "Formed On": creation_time, "Status": status
                }
                return True, info
            elif response.status == 500:
                return False, "Private Profile or Invalid UID."
            else:
                return False, f"HTTP Error {response.status}"
    except Exception as e:
        return False, str(e)
