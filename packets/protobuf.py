# START OF FILE: packets/protobuf.py
import json
from protobuf_decoder.protobuf_decoder import Parser
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.timestamp_pb2 import Timestamp

_sym_db = _symbol_database.Default()
_xkeys_globals = globals()

# ==========================================
# 🛑 1. MyMessage (Login/Key/Iv)
# ==========================================
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(
    b'\n\x10my_message.proto\">\n\tMyMessage\x12\x0f\n\x07\x66ield21\x18\x15 \x01(\x03'
    b'\x12\x0f\n\x07\x66ield22\x18\x16 \x01(\x0c\x12\x0f\n\x07\x66ield23\x18\x17 \x01(\x0c\x62\x06proto3'
)
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _xkeys_globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'xKEys', _xkeys_globals)
MyMessage = _xkeys_globals['MyMessage']

def GeT_Key_Iv(serialized_data):
    msg = MyMessage()
    msg.ParseFromString(serialized_data)
    ts = Timestamp()
    ts.FromNanoseconds(msg.field21)
    return ts.seconds * 1_000_000_000 + ts.nanos, msg.field22, msg.field23

# ==========================================
# 🛑 2. SpecialFriendResponse (Dynamic Duo)
# ==========================================
DESC_DUO = _descriptor_pool.Default().AddSerializedFile(
    b'\n\nBeta.proto\"u\n\x0e\x44ynamicDuoData\x12\x13\n\x0bpartner_uid\x18\x01 \x01(\x03\x12\r\n\x05score\x18\x03 \x01(\x05\x12\x1a\n\x12\x63reation_timestamp\x18\x04 \x01(\x03\x12\x13\n\x0b\x64\x61ys_active\x18\x05 \x01(\x05\x12\x0e\n\x06status\x18\x06 \x01(\x05\":\n\x15SpecialFriendResponse\x12!\n\x08\x64uo_info\x18\x01 \x01(\x0b\x32\x0f.DynamicDuoDatab\x06proto3'
)
_builder.BuildMessageAndEnumDescriptors(DESC_DUO, _xkeys_globals)
_builder.BuildTopDescriptorsAndMessages(DESC_DUO, 'Beta_pb2', _xkeys_globals)
SpecialFriendResponse = _xkeys_globals['SpecialFriendResponse']

# ==========================================
# প্যাকেট জেনারেটর এবং ডিকোডার লজিক
# ==========================================
def EnC_Vr(N):
    if N < 0: return b''
    H = []
    while True:
        BesTo = N & 0x7F; N >>= 7
        if N: BesTo |= 0x80
        H.append(BesTo)
        if not N: break
    return bytes(H)

def CrEaTe_VarianT(f, v): 
    return EnC_Vr((f << 3) | 0) + EnC_Vr(v)

def CrEaTe_LenGTh(f, v): 
    encoded = v.encode() if isinstance(v, str) else v
    return EnC_Vr((f << 3) | 2) + EnC_Vr(len(encoded)) + encoded

def CrEaTe_ProTo(fields):
    packet = bytearray()
    for field, value in fields.items():
        if isinstance(value, dict): packet.extend(CrEaTe_LenGTh(field, CrEaTe_ProTo(value)))
        elif isinstance(value, int): packet.extend(CrEaTe_VarianT(field, value))
        elif isinstance(value, (str, bytes)): packet.extend(CrEaTe_LenGTh(field, value))
    return packet

def Fix_PackEt(parsed_results):
    result_dict = {}
    for result in parsed_results:
        fd = {'wire_type': result.wire_type}
        if result.wire_type in ["varint", "string", "bytes"]: fd['data'] = result.data
        elif result.wire_type == 'length_delimited': fd["data"] = Fix_PackEt(result.data.results)
        result_dict[result.field] = fd
    return result_dict

def DeCode_PackEt(input_text):
    try: return json.dumps(Fix_PackEt(Parser().parse(input_text)))
    except: return None

# END OF FILE: packets/protobuf.py
