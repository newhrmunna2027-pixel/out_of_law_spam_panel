# -*- coding: utf-8 -*-
# START OF FILE: packets/generators.py

import random
from packets.protobuf import CrEaTe_ProTo
from packets.crypto import EnC_PacKeT, DecodE_HeX

def GeneRaTePk(Pk, N, K, V):
    PkEnc = EnC_PacKeT(Pk, K, V)
    _ = DecodE_HeX(int(len(PkEnc) // 2))
    head = N + ("000000" if len(_) == 2 else "00000" if len(_) == 3 else "0000")
    return bytes.fromhex(head + _ + PkEnc)

def xBunnEr():
    return random.choice([10001, 10002, 10003, 10004, 10005])

def Build_Initial_Team_Packet(bot_uid, region, key, iv, team_size=5):
    try:
        packet_id = "0515"
        if region:
            if region.lower() == "bd": packet_id = "0519"
            elif region.lower() == "ind": packet_id = "0514"
            
        fields_open = {1: 1, 2: {2: "\u0001", 3: 1, 4: 1, 5: "en", 9: 1, 11: 1, 13: 1, 14: {2: 5756, 6: 11, 8: "1.126.1", 9: 2, 10: 4}}}
        open_sq_packet = GeneRaTePk(CrEaTe_ProTo(fields_open).hex(), packet_id, key, iv)
        
        game_mode = random.choice([1, 2, 62, 73])
        fields_change = {1: 17, 2: {1: int(bot_uid), 2: 1, 3: int(team_size - 1), 4: int(game_mode), 5: "\u001a", 8: 5, 13: 329}}
        change_sq_packet = GeneRaTePk(CrEaTe_ProTo(fields_change).hex(), packet_id, key, iv)
        
        return [open_sq_packet, change_sq_packet]
    except Exception:
        return []

def Simple_Invite_Packet(target_uid, region, key, iv):
    packet_id = '0515'
    if region == 'BD': packet_id = '0519'
    elif region == 'IND': packet_id = '0514'
    fields = {1: 2, 2: {1: int(target_uid), 2: region, 4: 1}}
    return GeneRaTePk(str(CrEaTe_ProTo(fields).hex()), packet_id, key, iv)

def Leave_Team_Packet(uid, region, key, iv):
    packet_id = '0515'
    if region == 'BD': packet_id = '0519'
    elif region == 'IND': packet_id = '0514'
    fields = {1: 7, 2: {1: int(uid)}}
    return GeneRaTePk(str(CrEaTe_ProTo(fields).hex()), packet_id, key, iv)

def Open_Room_Packet(K, V):
    fields = {
        1: 2,  
        2: {   
            1: 1, 2: 15, 3: 5, 4: "Xyron", 5: "1", 6: 12, 7: 1, 8: 1, 9: 1,
            11: 1, 12: 2, 14: 36981056,
            15: {1: "IDC3", 2: 126, 3: "ME"},
            16: "\u0001\u0003\u0004\u0007\t\n\u000b\u0012\u000f\u000e\u0016\u0019\u001a \u001d",
            18: 2368584, 27: 1, 34: "\u0000\u0001", 40: "en", 48: 1,
            49: {1: 21},
            50: {1: 36981056, 2: 2368584, 5: 2}
        }
    }
    return GeneRaTePk(str(CrEaTe_ProTo(fields).hex()), '0E15', K, V)

def Room_Invite_Packet(target_uid, K, V):
    fields = {1: 22, 2: {1: int(target_uid)}}
    return GeneRaTePk(str(CrEaTe_ProTo(fields).hex()), '0E15', K, V)

# 🚀 FIXED: Garena Fake Joining-এর জন্য পূর্ণাঙ্গ ও নিখুঁত ওল্ড কমপ্লেক্স প্রোটোকল ফিল্ডস
def Fake_Profile_Join(target_uid, region, K, V):
    packet_id = '0515'
    if region == 'BD': packet_id = '0519'
    elif region == 'IND': packet_id = '0514'

    badge_list = [64, 4096, 8192, 16384, 32768, 1048576]
    selected_badge = random.choice(badge_list)
    random_rank_score = random.choice([1000, 9999, 20000, 5000, 3210])
    fake_team_id = random.randint(2000000000, 3000000000)

    fields = {
        1: 33, 
        2: {
            1: int(target_uid),
            2: region if region else "BD",
            3: int(fake_team_id),  
            4: 2,                  
            5: bytes([1, 7, 9, 10, 11, 18, 25, 26, 32]), 
            6: "[FF0000]System[FFFF00]Error", 
            7: 330,
            8: random_rank_score, 
            9: 100,
            10: "DZ",
            11: bytes([49, 97, 99, 52, 98, 56, 48, 101, 99, 102, 48, 52, 55, 56, 97, 52, 52, 50, 48, 51, 98, 102, 56, 102, 97, 99, 54, 49, 50, 48, 102, 53]), 
            12: 1,
            13: int(target_uid),
            14: {
                1: 2203434355,
                2: 8,
                3: b"\x10\x15\x08\n\x0b\x13\x0c\x0f\x11\x04\x07\x02\x03\r\x0e\x12\x01\x05\x06"
            },
            16: 1, 17: 1, 18: 312, 19: 46,
            23: bytes([16, 1, 24, 1]), 
            24: xBunnEr(), 
            26: "", 28: "",
            31: {1: 1, 2: selected_badge}, 
            32: selected_badge,
            34: {
                1: int(target_uid), 
                2: 8, 
                3: bytes([15,6,21,8,10,11,19,12,17,4,14,20,7,2,1,5,16,3,13,18])
            }
        }
    }
    return GeneRaTePk(str(CrEaTe_ProTo(fields).hex()), packet_id, K, V)