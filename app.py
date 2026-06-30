# -*- coding: utf-8 -*-
# START OF FILE app.py

import os
from web.utils import app
import web.routes  # এটি ইমপোর্ট করলেই সব রাউট রেজিস্টার হয়ে যাবে
from web.services import init_files

if __name__ == '__main__':
    # সার্ভার চালুর আগে ফোল্ডার ও ফাইল রেডি করে নেওয়া
    init_files()
    
    port = int(os.environ.get('PORT', 20669))
    print(f"🚀 Dashboard Starting on Port: {port}")
    
    # সার্ভার রান
    app.run(host='0.0.0.0', port=port)

# END OF FILE app.py
