# packets/config.py
Key = bytes([89, 103, 38, 116, 99, 37, 68, 69, 117, 104, 54, 37, 90, 99, 94, 56])
Iv = bytes([54, 111, 121, 90, 68, 114, 50, 50, 69, 51, 121, 99, 104, 106, 77, 37])

DEVICE_PROFILES = [
    {
     "os": "Android OS 12 / API-31",
     "cpu_short": "exynos2100",
     "cpu_long": "Exynos 2100 | 8 cores",
     "gpu": "Mali-G78 MP14",
     "opengl": "OpenGL ES 3.2 v1.r26p0",
     "width": 1080,
     "height": 2400,
     "dpi": "420",
     "ram": 8192,
     "operator": "Grameenphone"
    },
  
    {
     "os": "Android OS 11 / API-30",
     "cpu_short": "sm7150",
     "cpu_long": "Qualcomm Snapdragon 732G | 8 cores",
     "gpu": "Adreno (TM) 618",
     "opengl": "OpenGL ES 3.2 V@502.0",
     "width": 1080, "height": 2400,
     "dpi": "440", "ram": 6144,
     "operator": "Robi"
    },
  
    {
     "os": "Android OS 13 / API-33",
     "cpu_short": "sm8350",
     "cpu_long": "Qualcomm Snapdragon 888 | 8 cores",
     "gpu": "Adreno (TM) 660",
     "opengl": "OpenGL ES 3.2 V@512.0",
     "width": 1440, "height": 3216,
     "dpi": "520", "ram": 12288,
     "operator": "Banglalink"
    }
]
