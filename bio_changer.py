# -*- coding: utf-8 -*-
# START OF FILE bio_changer.py

from packets.central_login import Execute_MajorLogin
from packets.bio_duo_api import check_duo, update_bio

async def check_player_duo(bot_uid, bot_pass, target_uid):
    """API Gateway for Web Dynamic Duo Check"""
    
    # 🚀 ১ লাইনে Garena Authentication + MajorLogin!
    login_data, err = await Execute_MajorLogin(bot_uid, bot_pass)
    
    if not login_data:
        return False, err
        
    # 🚀 টোকেন ব্যবহার করে Duo Check
    success, data = await check_duo(login_data["token"], target_uid, login_data["auth_url"])
    return success, data

async def change_bot_bio(bot_uid, bot_pass, bio_text):
    """API Gateway for Web Signature Update"""
    
    # 🚀 ১ লাইনে Garena Authentication + MajorLogin!
    login_data, err = await Execute_MajorLogin(bot_uid, bot_pass)
    
    if not login_data:
        return False, err
        
    # 🚀 টোকেন ব্যবহার করে Bio Update
    success, msg = await update_bio(login_data["token"], bio_text, login_data["auth_url"])
    return success, msg

# END OF FILE bio_changer.py
