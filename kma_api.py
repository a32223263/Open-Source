import requests
import email.utils
from datetime import datetime, timedelta

# 기상청 격자 좌표 + 레이더용 행정구역 코드(법정동코드 10자리)
SEOUL_DISTRICTS = {
    "종로구": {"nx": 60, "ny": 127, "code": "1111000000"},
    "중구": {"nx": 60, "ny": 127, "code": "1114000000"},
    "용산구": {"nx": 60, "ny": 126, "code": "1117000000"},
    "성동구": {"nx": 61, "ny": 127, "code": "1120000000"},
    "광진구": {"nx": 62, "ny": 126, "code": "1121500000"},
    "동대문구": {"nx": 61, "ny": 127, "code": "1123000000"},
    "중랑구": {"nx": 62, "ny": 128, "code": "1126000000"},
    "성북구": {"nx": 61, "ny": 127, "code": "1129000000"},
    "강북구": {"nx": 61, "ny": 128, "code": "1130500000"},
    "도봉구": {"nx": 61, "ny": 129, "code": "1132000000"},
    "노원구": {"nx": 62, "ny": 129, "code": "1135000000"},
    "은평구": {"nx": 57, "ny": 128, "code": "1138000000"},
    "서대문구": {"nx": 59, "ny": 127, "code": "1141000000"},
    "마포구": {"nx": 59, "ny": 127, "code": "1144000000"},
    "양천구": {"nx": 58, "ny": 126, "code": "1147000000"},
    "강서구": {"nx": 58, "ny": 126, "code": "1150000000"},
    "구로구": {"nx": 58, "ny": 125, "code": "1153000000"},
    "금천구": {"nx": 59, "ny": 124, "code": "1154500000"},
    "영등포구": {"nx": 58, "ny": 126, "code": "1156000000"},
    "동작구": {"nx": 59, "ny": 125, "code": "1159000000"},
    "관악구": {"nx": 59, "ny": 125, "code": "1162000000"},
    "서초구": {"nx": 61, "ny": 125, "code": "1165000000"},
    "강남구": {"nx": 61, "ny": 126, "code": "1168000000"},
    "송파구": {"nx": 62, "ny": 126, "code": "1171000000"},
    "강동구": {"nx": 62, "ny": 126, "code": "1174000000"}
}

# [핵심] 네트워크 시간 동기화 (KST 기준)
def get_real_kst_now():
    try:
        res = requests.head("https://www.google.com", timeout=1)
        date_str = res.headers['Date']
        utc_now = email.utils.parsedate_to_datetime(date_str)
        return utc_now + timedelta(hours=9)
    except:
        return datetime.utcnow() + timedelta(hours=9)

def get_base_time_for_ultrasrt_ncst():
    now = get_real_kst_now()
    if now.minute < 40:
        target = now - timedelta(hours=1)
    else:
        target = now
    return target.strftime('%Y%m%d'), target.strftime('%H00')

# 1. 현재 날씨 (초단기실황)
def get_live_weather(api_key: str, nx: int, ny: int):
    endpoint = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getUltraSrtNcst"
    base_date, base_time = get_base_time_for_ultrasrt_ncst()
    params = {'pageNo': '1', 'numOfRows': '1000', 'dataType': 'JSON', 'base_date': base_date, 'base_time': base_time, 'nx': str(nx), 'ny': str(ny), 'authKey': api_key}
    try:
        res = requests.get(endpoint, params=params, timeout=5)
        res.raise_for_status()
        items = res.json().get('response', {}).get('body', {}).get('items', {}).get('item')
        if not items: return None
        live_data = {}
        for item in items: live_data[item['category']] = float(item['obsrValue'])
        return live_data
    except: return None

# 2. 특보
def get_weather_warning(api_key: str):
    endpoint = "https://apihub.kma.go.kr/api/typ01/url/wrn_now_data.php"
    try:
        res = requests.get(endpoint, params={'fe': 'f', 'disp': '0', 'authKey': api_key}, timeout=5)
        lines = res.text.split('\n')
        seoul_warnings = []
        for line in lines:
            if "서울" in line:
                warning_type = "기상특보"
                if "W" in line: warning_type = "강풍"
                elif "R" in line: warning_type = "호우"
                elif "H" in line: warning_type = "폭염"
                elif "S" in line: warning_type = "대설"
                elif "D" in line: warning_type = "건조"
                elif "C" in line: warning_type = "한파"
                seoul_warnings.append(f"{warning_type} 발효중")
        return ", ".join(list(set(seoul_warnings))) if seoul_warnings else None
    except: return None

# 3. 단기 예보
def get_forecast(api_key: str, nx: int, ny: int):
    endpoint = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst"
    now = get_real_kst_now()
    target_time = now - timedelta(hours=3)
    base_date = target_time.strftime('%Y%m%d')
    hour = target_time.hour
    
    time_mapping = {2:'0200', 5:'0500', 8:'0800', 11:'1100', 14:'1400', 17:'1700', 20:'2000', 23:'2300'}
    base_time = '2300'
    for h in sorted(time_mapping.keys()):
        if hour < h: break
        base_time = time_mapping[h]
    if hour < 2: base_date = (target_time - timedelta(days=1)).strftime('%Y%m%d')

    params = {'pageNo': '1', 'numOfRows': '1000', 'dataType': 'JSON', 'base_date': base_date, 'base_time': base_time, 'nx': str(nx), 'ny': str(ny), 'authKey': api_key}
    try:
        res = requests.get(endpoint, params=params, timeout=5)
        items = res.json().get('response', {}).get('body', {}).get('items', {}).get('item')
        if not items: return None
        weather_data = {}
        for item in items:
            cat = item.get('category')
            val = item.get('fcstValue')
            if cat == 'TMP' and 'temp' not in weather_data: weather_data['temp'] = val
            elif cat == 'PCP' and 'precip' not in weather_data: weather_data['precip'] = val
            elif cat == 'SKY' and 'sky' not in weather_data: weather_data['sky'] = val
            elif cat == 'PTY' and 'pty' not in weather_data: weather_data['pty'] = val
            elif cat == 'WSD' and 'wind_speed' not in weather_data: weather_data['wind_speed'] = val
            elif cat == 'REH' and 'humidity' not in weather_data: weather_data['humidity'] = val
            if len(weather_data) >= 6: break
        return weather_data
    except: return None

# 4. 위성 영상
def get_satellite_image_url(api_key: str):
    base_url = "https://apihub.kma.go.kr/api/typ03/cgi/sat/nph-gk2a_img"
    now = get_real_kst_now() - timedelta(minutes=20)
    minute = (now.minute // 10) * 10
    tm = now.replace(minute=minute, second=0, microsecond=0).strftime("%Y%m%d%H%M")
    return f"{base_url}?tm={tm}&obs=ir105&map=HR&grid=2&legend=0&size=600&authKey={api_key}"

# 5. 상세 예보 (시간별)
def get_hourly_forecast(api_key, nx, ny, hours=None):
    endpoint = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst"
    now = get_real_kst_now()
    target_time = now - timedelta(hours=3)
    base_date = target_time.strftime('%Y%m%d')
    hour = target_time.hour
    
    time_mapping = {2:'0200', 5:'0500', 8:'0800', 11:'1100', 14:'1400', 17:'1700', 20:'2000', 23:'2300'}
    base_time = '2300'
    for h in sorted(time_mapping.keys()):
        if hour < h: break
        base_time = time_mapping[h]
    if hour < 2: base_date = (target_time - timedelta(days=1)).strftime('%Y%m%d')

    params = {'pageNo': '1', 'numOfRows': '1000', 'dataType': 'JSON', 'base_date': base_date, 'base_time': base_time, 'nx': str(nx), 'ny': str(ny), 'authKey': api_key}
    try:
        res = requests.get(endpoint, params=params, timeout=5)
        items = res.json().get('response', {}).get('body', {}).get('items', {}).get('item')
        if not items: return None
        items.sort(key=lambda x: x['fcstDate'] + x['fcstTime'])
        forecast_map = {}
        for item in items:
            key = item['fcstDate'] + item['fcstTime']
            if key not in forecast_map: forecast_map[key] = {}
            forecast_map[key][item['category']] = item['fcstValue']
        hourly_list = []
        if hours: keys = list(forecast_map.keys())[:hours]
        else: keys = list(forecast_map.keys())
        
        for k in keys:
            row = forecast_map[k]
            try:
                hourly_list.append({
                    "date": f"{k[4:6]}/{k[6:8]}",
                    "hour": f"{k[8:10]}:00",
                    "temp": float(row.get("TMP", 0)),
                    "rain_prob": float(row.get("POP", 0)),
                    "wind_spd": float(row.get("WSD", 0))
                })
            except: continue
        return hourly_list
    except: return None

# 6. 중기 예보
def get_mid_term_forecast(api_key):
    now = get_real_kst_now()
    if now.hour < 6: tmFc = (now - timedelta(days=1)).strftime("%Y%m%d1800")
    elif now.hour < 18: tmFc = now.strftime("%Y%m%d0600")
    else: tmFc = now.strftime("%Y%m%d1800")
    try:
        res_ta = requests.get("https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidTa", params={'pageNo': 1, 'numOfRows': 10, 'dataType': 'JSON', 'regId': '11B10101', 'tmFc': tmFc, 'authKey': api_key})
        item_ta = res_ta.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])[0]
        res_land = requests.get("https://apihub.kma.go.kr/api/typ02/openApi/MidFcstInfoService/getMidLandFcst", params={'pageNo': 1, 'numOfRows': 10, 'dataType': 'JSON', 'regId': '11B00000', 'tmFc': tmFc, 'authKey': api_key})
        item_land = res_land.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])[0]
        mid_list = []
        for day in range(3, 8):
            d_str = (datetime.strptime(tmFc[:8], "%Y%m%d") + timedelta(days=day)).strftime("%m/%d")
            mid_list.append({"date": d_str, "hour": "오전", "temp": float(item_ta.get(f'taMin{day}', 0)), "rain_prob": int(item_land.get(f'rnSt{day}Am', 0)), "wind_spd": "-"})
            mid_list.append({"date": d_str, "hour": "오후", "temp": float(item_ta.get(f'taMax{day}', 0)), "rain_prob": int(item_land.get(f'rnSt{day}Pm', 0)), "wind_spd": "-"})
        return mid_list
    except: return []

# 7. 레이더 영상 URL
def get_radar_image_url(api_key: str):
    base_url = "https://apihub.kma.go.kr/api/typ03/cgi/rdr/nph-rdr_cmp1_img"
    now = get_real_kst_now() - timedelta(minutes=20)
    minute = (now.minute // 5) * 5
    tm = now.replace(minute=minute, second=0, microsecond=0).strftime("%Y%m%d%H%M")
    return f"{base_url}?tm={tm}&cmp=HSR&qcd=HSLP&obs=ECHD&color=C4&map=HR&grid=2&legend=1&size=600&itv=5&authKey={api_key}"

# 8. 레이더 데이터 분석
def get_radar_value_for_district(api_key: str, district_name: str):
    dong_code = SEOUL_DISTRICTS.get(district_name, {}).get("code")
    if not dong_code: return None
    now = get_real_kst_now() - timedelta(minutes=20)
    minute = (now.minute // 5) * 5
    tm = now.replace(minute=minute, second=0, microsecond=0).strftime("%Y%m%d%H%M")
    endpoint = "https://apihub.kma.go.kr/api/typ02/openApi/WthrRadarInfoService/getCompCappiQcdArea"
    params = {'pageNo': 1, 'numOfRows': 10, 'dataType': 'JSON', 'dateTime': tm, 'compType': 'CPP', 'dataTypeCd': 'CZ', 'dongCode': dong_code, 'authKey': api_key}
    try:
        res = requests.get(endpoint, params=params, timeout=5)
        items = res.json().get('response', {}).get('body', {}).get('items', {}).get('item', [])
        if not items: return None
        val = float(items[0].get('value', -999))
        return 0.0 if val < -100 else val
    except: return None