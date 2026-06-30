# -*- coding: utf-8 -*-
# START OF FILE: packets/status_parser.py

from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

class SimpleProtobufDecoder:
    @staticmethod
    def parse(hex_data):
        data = bytes.fromhex(hex_data) if isinstance(hex_data, str) else hex_data
        return SimpleProtobufDecoder._parse_bytes(data)
        
    @staticmethod
    def _parse_bytes(data):
        results = {}
        idx = 0
        length = len(data)
        while idx < length:
            try:
                tag, idx = SimpleProtobufDecoder._read_varint(data, idx)
                field_number = str(tag >> 3)
                wire_type = tag & 0x07
                if wire_type == 0:
                    value, idx = SimpleProtobufDecoder._read_varint(data, idx)
                    results[field_number] = {"data": value}
                elif wire_type == 2:
                    chunk_len, idx = SimpleProtobufDecoder._read_varint(data, idx)
                    chunk = data[idx : idx + chunk_len]
                    idx += chunk_len
                    try: 
                        results[field_number] = {"data": SimpleProtobufDecoder._parse_bytes(chunk) or chunk.decode('utf-8', errors='ignore')}
                    except: 
                        results[field_number] = {"data": chunk.decode('utf-8', errors='ignore')}
                else: 
                    return results 
            except: 
                break
        return results
        
    @staticmethod
    def _read_varint(data, idx):
        result = 0; shift = 0
        while True:
            b = data[idx]; idx += 1
            result |= (b & 0x7F) << shift
            if not (b & 0x80): return result, idx
            shift += 7

# 🚀 FIXED: Garena থেকে প্রাপ্ত প্রোটোবাফ মেসেজের অত্যন্ত নিরাপদ পার্সিং লজিক
def parse_status_response(packet_bytes):
    try:
        start_index = -1
        for i in range(min(10, len(packet_bytes))):
            if packet_bytes[i] == 0x08:
                start_index = i
                break
        packet_body = packet_bytes[start_index:] if start_index != -1 else packet_bytes[5:]
        
        decoded = SimpleProtobufDecoder.parse(packet_body)
        core_data = decoded.get("5", {}).get("data", {}).get("1", {}).get("data", {})
        if not core_data: return None
        
        target_uid = str(core_data.get("1", {}).get("data", "Unknown"))
        status_code = core_data.get("3", {}).get("data", 0)
        status_map = {1: "SOLO", 2: "IN SQUAD", 3: "PLAYING", 4: "IN ROOM", 5: "PLAYING", 6: "SOCIAL ISLAND", 7: "SOCIAL ISLAND"}
        status_str = status_map.get(status_code, "OFFLINE")
        
        leader_uid = "N/A"
        squad_size = "N/A"
        room_id = "N/A"
        
        # 🚀 ওল্ড কোডের মতো কন্ডিশনাল চেকিং এর মাধ্যমে নিরাপদ স্কোয়াড সাইজ ডিফাইন করা হচ্ছে
        if status_code != 1 and status_str != "OFFLINE":
            leader_uid = str(core_data.get("8", {}).get("data", "N/A"))
            if "9" in core_data:
                curr = core_data["9"]["data"]
                if "10" in core_data:
                    maxx = core_data["10"]["data"] + 1
                    squad_size = f"{curr}/{maxx}"
                else:
                    squad_size = f"{curr}"
        
        if status_code == 4:
            room_id = str(core_data.get("4", {}).get("data", "N/A"))
            
        return {"uid": target_uid, "status": status_str, "leader": leader_uid, "squad_size": squad_size, "room_id": room_id}
    except: return None

def Encrypt_Varint(number):
    number = int(number)
    encoded_bytes = []
    while True:
        byte = number & 0x7F
        number >>= 7
        if number: byte |= 0x80
        encoded_bytes.append(byte)
        if not number: break
    return bytes(encoded_bytes).hex()

def dec_to_hex(decimal):
    hex_str = hex(decimal)[2:]
    return hex_str.upper() if len(hex_str) % 2 == 0 else '0' + hex_str.upper()

def create_status_check_packet(target_uid, key, iv):
    try:
        ida = Encrypt_Varint(target_uid)
        packet = f"080112090A05{ida}1005"
        
        cipher = AES.new(key, AES.MODE_CBC, iv)
        encrypted_packet_hex = cipher.encrypt(pad(bytes.fromhex(packet), AES.block_size)).hex()
        
        header_lenth = len(encrypted_packet_hex) // 2
        header_lenth_final = dec_to_hex(header_lenth)
        
        if len(header_lenth_final) == 2: final_packet = "0F15000000" + header_lenth_final + encrypted_packet_hex
        elif len(header_lenth_final) == 3: final_packet = "0F1500000" + header_lenth_final + encrypted_packet_hex
        elif len(header_lenth_final) == 4: final_packet = "0F150000" + header_lenth_final + encrypted_packet_hex
        else: final_packet = "0F15000" + header_lenth_final + encrypted_packet_hex
            
        return bytes.fromhex(final_packet)
    except: return None