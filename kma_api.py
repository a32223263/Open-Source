import requests
import email.utils
from datetime import datetime, timedelta
import re

# 서울 각 자치구의 기상청 격자 좌표(NX, NY)와 행정구역 코드를 매핑함
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

# 구글 서버 헤더를 이용해 정확한 한국 표준시(KST)를 가져옴 (시스템 시간 오차 방지)
def get_real_kst_now():
    try:
        res = requests.head("https://www.google.com", timeout=1)
        date_str = res.headers['Date']
        utc_now = email.utils.parsedate_to_datetime(date_str)
        return utc_now + timedelta(hours=9)
    except:
        return datetime.utcnow() + timedelta(hours=9)

# 초단기실황 API 호출을 위한 기준 시간(Base Time)을 계산함 (매시 40분 기준 갱신)
def get_base_time_for_ultrasrt_ncst():
    now = get_real_kst_now()
    if now.minute < 40:
        target = now - timedelta(hours=1)
    else:
        target = now
    return target.strftime('%Y%m%d'), target.strftime('%H00')

# 기상청 초단기실황 API를 호출하여 현재 날씨 데이터를 가져옴
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
        for item in items: 
            live_data[item['category']] = float(item['obsrValue'])
        return live_data
    except: return None

# 현재 발효 중인 기상 특보를 조회하고 서울 지역 해당 사항을 필터링함
def get_weather_warning(api_key: str):
    endpoint = "https://apihub.kma.go.kr/api/typ01/url/wrn_now_data.php"
    try:
        res = requests.get(endpoint, params={'fe': 'f', 'disp': '0', 'authKey': api_key}, timeout=5)
        lines = res.text.split('\n')
        seoul_warnings = []
        for line in lines:
            if "서울" in line:
                warning_type = "기상특보"
                # 특보 코드를 한글 명칭으로 변환함
                if "W" in line: warning_type = "강풍"
                elif "R" in line: warning_type = "호우"
                elif "H" in line: warning_type = "폭염"
                elif "S" in line: warning_type = "대설"
                elif "D" in line: warning_type = "건조"
                elif "C" in line: warning_type = "한파"
                elif "Y" in line: warning_type = "황사"
                
                level = "경보" if "1" in line else "주의보"
                seoul_warnings.append(f"{warning_type}{level}")
                
        if seoul_warnings:
            return ", ".join(list(set(seoul_warnings))) + " 발효 중"
        return None
    except: return None

# 기상청 예보관이 작성한 날씨 해설(통보문)을 조회하여 핵심 문장을 추출함
def get_weather_comment(api_key: str):
    """
    사용자에게 "왜 비가 오는지", "언제 그치는지" 등 깊이 있는 정보를 제공
    """
    endpoint = "https://apihub.kma.go.kr/api/typ01/url/wthr_cmt_rpt.php"
    
    # 최근 24시간 이내의 해설 검색
    now = get_real_kst_now()
    tmfc2 = now.strftime("%Y%m%d%H%M")
    tmfc1 = (now - timedelta(hours=24)).strftime("%Y%m%d%H%M")
    
    # stn=108 (전국/서울 본청 기준)
    params = {
        'tmfc1': tmfc1, 'tmfc2': tmfc2, 'stn': '108', 
        'disp': '0', 'help': '0', 'authKey': api_key
    }
    
    try:
        res = requests.get(endpoint, params=params, timeout=5)
        lines = res.text.strip().split('\n')
        comments = []
        
        for line in lines:
            # 유의미한 키워드가 포함된 문장만 필터링하고 특수문자를 제거함
            if len(line) > 15 and any(keyword in line for keyword in ["기온", "비", "구름", "안개", "바람", "맑음"]):
                # 특수문자 일부 제거하여 깔끔하게 만들기
                clean_line = re.sub(r'[^가-힣a-zA-Z0-9\s\.\,\~\-]', '', line).strip()
                comments.append(clean_line)
        
        # 가장 최근의 유의미한 해설 1~2문장 반환 (너무 길면 잘라서)
        if comments:
            full_comment = " ".join(comments[-2:])
            if len(full_comment) > 120:
                return full_comment[:120] + "..."
            return full_comment
            
        return "특이사항이 없는 대체로 평온한 날씨가 예상됩니다."
        
    except Exception as e:
        print(f"날씨 해설 조회 오류: {e}")
        return None

# 기상청 단기예보 API를 호출하여 미래 날씨 데이터를 가져옴
def get_forecast(api_key: str, nx: int, ny: int):
    endpoint = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst"
    
    # 안정적인 데이터 확보를 위해 3시간 전 데이터를 기준으로 요청함
    now = get_real_kst_now()
    target_time = now - timedelta(hours=3)
    base_date = target_time.strftime('%Y%m%d')
    hour = target_time.hour
    
    # 기상청 예보 발표 시각(Base Time)에 맞춰 시간을 조정함
    time_mapping = {2:'0200', 5:'0500', 8:'0800', 11:'1100', 14:'1400', 17:'1700', 20:'2000', 23:'2300'}
    base_time = '2300'
    for h in sorted(time_mapping.keys()):
        if hour < h: break
        base_time = time_mapping[h]
    if hour < 2: base_date = (target_time - timedelta(days=1)).strftime('%Y%m%d')

    params = {
        'pageNo': '1', 
        'numOfRows': '1000', 
        'dataType': 'JSON', 
        'base_date': base_date, 
        'base_time': base_time, 
        'nx': str(nx), 
        'ny': str(ny), 
        'authKey': api_key
    }
    
    try:
        # SSL 인증서 검증을 무시하고 요청을 보냄 (verify=False)
        res = requests.get(endpoint, params=params, timeout=10, verify=False)
        
        # [디버깅] API 응답 코드가 200이 아니면 오류 정보를 출력하고 None을 반환함
        if res.status_code != 200:
            print(f"============== [API 오류] ==============")
            print(f"상태 코드: {res.status_code}")
            print(f"응답 본문: {res.text[:200]}")
            print(f"요청 URL: {res.url}")
            print("========================================")
            return None

        # [디버깅] JSON 파싱 시도
        try:
            json_data = res.json()
        except ValueError:
            print(f"============== [JSON 파싱 오류] ==============")
            print(f"API가 JSON이 아닌 텍스트를 반환했습니다.")
            print(f"응답 내용: {res.text[:200]}")
            print("============================================")
            return None

        items = json_data.get('response', {}).get('body', {}).get('items', {}).get('item')
        if not items:
            print(f"============== [데이터 없음] ==============")
            print(f"응답은 성공했으나 items 데이터가 비어있습니다.")
            print(f"헤더 메시지: {json_data.get('response', {}).get('header', {})}")
            print("=========================================")
            return None
            
        weather_data = {}
        
        # 필요한 카테고리(기온, 강수, 하늘상태 등) 데이터를 추출하여 저장
        needed_cats = ['TMP', 'PCP', 'SKY', 'PTY', 'WSD', 'REH', 'VEC'] 
        
        for item in items:
            cat = item.get('category')
            val = item.get('fcstValue')
            
            if cat == 'TMP' and 'temp' not in weather_data: weather_data['temp'] = val
            elif cat == 'PCP' and 'precip' not in weather_data: weather_data['precip'] = val
            elif cat == 'SKY' and 'sky' not in weather_data: weather_data['sky'] = val
            elif cat == 'PTY' and 'pty' not in weather_data: weather_data['pty'] = val
            elif cat == 'WSD' and 'wind_speed' not in weather_data: weather_data['wind_speed'] = val
            elif cat == 'REH' and 'humidity' not in weather_data: weather_data['humidity'] = val
            elif cat == 'VEC' and 'wind_dir' not in weather_data: weather_data['wind_dir'] = val
            
            if len(weather_data) >= 7: break
            
        return weather_data

    except Exception as e:
        print(f"============== [시스템 예외 발생] ==============")
        print(f"에러 메시지: {e}")
        print("==============================================")
        return None

# 천리안 위성 영상 URL을 생성함 (최근 20분 전 영상 기준)
def get_satellite_image_url(api_key: str):
    base_url = "https://apihub.kma.go.kr/api/typ03/cgi/sat/nph-gk2a_img"
    now = get_real_kst_now() - timedelta(minutes=20)
    minute = (now.minute // 10) * 10
    tm = now.replace(minute=minute, second=0, microsecond=0).strftime("%Y%m%d%H%M")
    return f"{base_url}?tm={tm}&obs=ir105&map=HR&grid=2&legend=0&size=600&authKey={api_key}"

# 시간대별 상세 예보 데이터를 리스트 형태로 반환함
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

        # 시간대별로 데이터를 그룹화함
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
            # 필요한 데이터만 추출하여 리스트에 추가함
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

# 중기 예보(3일~10일 후) 데이터를 가져옴
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

# 레이더 영상 URL을 생성함
def get_radar_image_url(api_key: str):
    base_url = "https://apihub.kma.go.kr/api/typ03/cgi/rdr/nph-rdr_cmp1_img"
    now = get_real_kst_now() - timedelta(minutes=20)
    minute = (now.minute // 5) * 5
    tm = now.replace(minute=minute, second=0, microsecond=0).strftime("%Y%m%d%H%M")
    return f"{base_url}?tm={tm}&cmp=HSR&qcd=HSLP&obs=ECHD&color=C4&map=HR&grid=2&legend=1&size=600&itv=5&authKey={api_key}"

# 특정 행정구역의 레이더 반사도(dBZ) 수치를 가져옴
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

# 24시간 전 서울의 과거 기온 데이터를 텍스트 파싱하여 가져옴
def get_yesterday_seoul_temp(api_key: str):
    # 어제 시간 구하기 (현재 시간 - 24시간)
    now = get_real_kst_now()
    yesterday = now - timedelta(hours=24)
    tm = yesterday.strftime("%Y%m%d%H00") # 예: 202511281400
    
    # 기상청 지상 관측(과거 자료) API 호출
    # stn=108은 서울 종로구 송월동(기상청 본청) 기준 관측소
    endpoint = "https://apihub.kma.go.kr/api/typ01/url/kma_sfctm2.php"
    params = {
        'tm': tm, 
        'stn': '108', # 서울 대표 관측소
        'help': '0',  # 도움말 끄기
        'authKey': api_key
    }
    
    try:
        res = requests.get(endpoint, params=params, timeout=5)
        
        # 텍스트 데이터 파싱
        lines = res.text.strip().split('\n')
        
        # 데이터가 너무 짧으면 실패 처리
        if len(lines) < 2: return None
        
        # 헤더 라인 찾기 (TM, STN, ... TA ... 등)
        headers = []
        data_values = []
        
        # #으로 시작하는 주석 라인 제거하고 실제 데이터 찾기
        valid_lines = [line for line in lines if not line.startswith('#')]
        
        if len(valid_lines) < 2: return None
        
        # 첫 번째 줄은 헤더, 두 번째 줄은 데이터
        # 공백 기준으로 분리 (split()은 다중 공백도 처리함)
        headers = valid_lines[0].split()
        data_values = valid_lines[1].split()
        
        # 'TA' (Temperature Air, 기온) 컬럼의 인덱스 찾기
        if 'TA' in headers:
            idx = headers.index('TA')
            if idx < len(data_values):
                temp_str = data_values[idx]
                return float(temp_str)
                
        return None
        
    except Exception as e:
        print(f"어제 날씨 조회 실패: {e}")
        return None