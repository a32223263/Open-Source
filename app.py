import time
from flask import Flask, render_template, request, url_for
from kma_api import get_yesterday_seoul_temp
from datetime import datetime

# kma_api 모듈에서 날씨 조회 및 데이터 처리에 필요한 함수들과 서울 지역구 좌표 데이터를 임포트함
from kma_api import (
    get_forecast, get_satellite_image_url, get_hourly_forecast, 
    get_live_weather, get_weather_warning, get_radar_image_url, 
    get_mid_term_forecast, get_radar_value_for_district, get_weather_comment,
    SEOUL_DISTRICTS
)

app = Flask(__name__)
# 기상청 API 호출을 위한 인증 키를 설정함
KMA_API_KEY = "2fqF3fBYST-6hd3wWEk_RA" 

# API에서 수신한 하늘 상태 코드와 강수 형태 코드를 사람이 읽기 쉬운 한글 텍스트로 변환함
def get_sky_status(sky_code: str, pty_code: str) -> str:
    if pty_code != 0:
        pty_map = {1: '비', 2: '비/눈', 3: '눈', 4: '소나기', 5: '빗방울', 6: '빗방울/눈날림', 7: '눈날림'}
        return pty_map.get(pty_code, "알 수 없는 강수")
    else:
        sky_map = {'1': '맑음', '3': '구름많음', '4': '흐림'}
        return sky_map.get(sky_code, "알 수 없음")

# 현재 기온 데이터를 기준으로 사용자에게 적합한 옷차림을 추천하는 문자열을 반환함
def get_clothing_recommendation(temp):
    if temp >= 28: return "민소매, 반바지, 원피스 (더위 조심!)"
    elif 23 <= temp < 28: return "반팔, 얇은 셔츠, 반바지, 면바지"
    elif 20 <= temp < 23: return "블라우스, 긴팔 티, 면바지, 슬랙스"
    elif 17 <= temp < 20: return "얇은 가디건, 니트, 맨투맨, 후드, 긴 바지"
    elif 12 <= temp < 17: return "자켓, 가디건, 야상, 스타킹, 청바지, 면바지"
    elif 9 <= temp < 12: return "트렌치 코트, 야상, 점퍼, 스타킹, 기모 바지"
    elif 5 <= temp < 9: return "울 코트, 히트텍, 가죽 옷, 기모"
    else: return "패딩, 두꺼운 코트, 목도리, 장갑 (한파 대비)"

# 기온, 습도, 강수 정보 등의 데이터를 종합적으로 분석하여 빨래 지수와 세차 지수를 계산함
def calculate_lifestyle_indices(temp, humidity, rain_prob, pty_code):
    laundry_score = 0
    laundry_msg = ""
    
    # 강수가 있거나 강수 확률이 높으면 빨래 지수를 낮게 설정하고 경고 메시지를 생성함
    if pty_code > 0 or rain_prob > 30:
        laundry_score = 10 
        laundry_msg = "실내 건조 필수 (비/눈)"
    else:
        # 습도가 낮을수록 빨래 건조에 유리하므로 높은 점수를 부여함
        if humidity < 40: laundry_score = 90; laundry_msg = "뽀송뽀송 잘 마름"
        elif humidity < 60: laundry_score = 70; laundry_msg = "적당히 잘 마름"
        elif humidity < 80: laundry_score = 40; laundry_msg = "다소 눅눅함"
        else: laundry_score = 20; laundry_msg = "잘 안 마름"

    # 강수 유무를 판단하여 세차 지수와 추천 메시지를 생성함
    carwash_score = 0
    carwash_msg = ""
    if pty_code > 0 or rain_prob > 20:
        carwash_score = 10
        carwash_msg = "하지 마세요 (비/눈)"
    else:
        carwash_score = 90
        carwash_msg = "세차하기 딱 좋은 날"
        
    return {
        "laundry": {"score": laundry_score, "msg": laundry_msg},
        "carwash": {"score": carwash_score, "msg": carwash_msg}
    }

# 시간별 예보 데이터를 순회하며 등교(09시) 및 하교(18시) 시간대의 날씨 위험도를 분석함
def analyze_commute(hourly_data):
    report = {
        "morning": {"status": "정보 없음", "msg": "데이터 부족", "icon": "dash", "score": 0},
        "evening": {"status": "정보 없음", "msg": "데이터 부족", "icon": "dash", "score": 0}
    }
    current_hour = datetime.now().hour
    
    for row in hourly_data:
        try:
            fcst_h = int(row['hour'].split(':')[0])
            is_rainy = row['rain_prob'] >= 30
            wind_strong = row['wind_spd'] >= 4.0
            temp = row['temp']
            
            # 강수, 풍속, 기온 조건을 복합적으로 체크하여 상태 메시지와 아이콘, 점수를 결정함
            status = "좋음"
            msg = "날씨 걱정 없어요"
            icon = "emoji-smile-fill text-success"
            score = 90
            
            if is_rainy and wind_strong:
                status = "악천후"
                msg = "비바람 몰아침! 큰 우산 필수"
                icon = "umbrella-fill text-danger"
                score = 20
            elif is_rainy:
                status = "비"
                msg = f"강수확률 {int(row['rain_prob'])}%. 우산 챙기세요"
                icon = "cloud-rain-fill text-primary"
                score = 40
            elif temp <= 3:
                status = "추움"
                msg = "등하교길 매우 추워요. 롱패딩 추천"
                icon = "snow2 text-info"
                score = 50
            elif wind_strong:
                status = "강풍"
                msg = "바람이 매서워요. 머리스타일 주의"
                icon = "wind text-secondary"
                score = 60
                
            # 09시 데이터는 등교 정보로, 18시 데이터는 하교 정보로 매핑하여 저장함
            if fcst_h == 9: 
                report["morning"] = {"status": status, "msg": msg, "icon": icon, "score": score}
            if fcst_h == 18:
                if current_hour >= 19:
                    report["evening"] = {"status": "완료", "msg": "하루 고생하셨습니다!", "icon": "moon-stars-fill text-warning", "score": 100}
                else:
                    report["evening"] = {"status": status, "msg": msg, "icon": icon, "score": score}
        except: continue
    return report

# 레이더 반사도(dBZ) 수치를 입력받아 기상학적 기준에 따라 강수 강도와 위험 등급을 분석함
def analyze_radar_intensity(dbz):
    if dbz is None or dbz < -10:
        return {
            "level": "관측 불가", "desc": "데이터 수신 불가", 
            "type": "-", "impact": "-", "color": "secondary", "percent": 0
        }
    
    # dBZ 구간별로 강수 형태(없음, 약한 비, 보통 비, 폭우 등)를 분류하고 설명을 반환함
    if dbz <= 0:
        return {
            "level": "Clear", 
            "desc": "강수 에코 없음 (맑음/구름)", 
            "type": "비구름 없음", 
            "impact": "야외 활동에 지장 없습니다.", 
            "color": "secondary", "percent": 5
        }
    elif dbz < 20:
        return {
            "level": "Weak Echo", 
            "desc": "매우 약한 에코 (안개/연무 가능성)", 
            "type": "비로 닿지 않을 수 있음", 
            "impact": "우산 없이도 이동 가능합니다.", 
            "color": "info", "percent": 20
        }
    elif dbz < 30:
        return {
            "level": "Light Rain", 
            "desc": "약한 비 (시간당 1~3mm)", 
            "type": "층상형 강수 (넓게 퍼짐)", 
            "impact": "옷이 젖을 수 있으니 우산을 챙기세요.", 
            "color": "success", "percent": 40
        }
    elif dbz < 40:
        return {
            "level": "Moderate", 
            "desc": "보통 비 (시간당 3~10mm)", 
            "type": "일반적인 강우", 
            "impact": "빗소리가 들리며 웅덩이가 고입니다.", 
            "color": "primary", "percent": 60
        }
    elif dbz < 50:
        return {
            "level": "Heavy Rain", 
            "desc": "강한 비 (시간당 10~30mm)", 
            "type": "대류형 강수 (소나기성)", 
            "impact": "시야 확보가 어렵고 신발이 젖습니다.", 
            "color": "warning", "percent": 80
        }
    else: 
        return {
            "level": "Severe Storm", 
            "desc": "폭우/우박 (시간당 30mm+)", 
            "type": "뇌우 동반 가능성 높음", 
            "impact": "매우 위험! 안전한 실내로 대피하세요.", 
            "color": "danger", "percent": 100
        }
    
# 메인 페이지('/') 요청 시 실행되며, 현재 날씨 및 각종 생활 지표를 수집하여 렌더링함
@app.route('/')
def index():
    # URL 파라미터로 전달된 지역명을 확인하고 해당 지역의 격자 좌표(NX, NY)를 가져옴
    selected_district = request.args.get('district', '종로구')
    coords = SEOUL_DISTRICTS.get(selected_district, {"nx": 60, "ny": 127})
    nx, ny = coords['nx'], coords['ny']

    # 단기 예보, 실시간 날씨, 기상 특보, 날씨 해설 등 외부 API 함수들을 호출함
    forecast_data = get_forecast(KMA_API_KEY, nx, ny)
    live_data = get_live_weather(KMA_API_KEY, nx, ny)
    warning_msg = get_weather_warning(KMA_API_KEY)
    satellite_url = get_satellite_image_url(KMA_API_KEY)
    expert_comment = get_weather_comment(KMA_API_KEY)
    
    # 향후 24시간의 시간별 예보 데이터를 가져와 차트 및 등하교 분석에 사용함
    short_term_all = get_hourly_forecast(KMA_API_KEY, nx, ny, hours=24) or []
    commute_report = analyze_commute(short_term_all)

    # 예보 데이터 로딩에 실패했을 경우 에러 페이지를 반환함
    if not forecast_data:
        return render_template('error.html', message="데이터 로딩 실패")

    # 기본 예보 데이터를 변수에 할당하고, 실시간 관측 데이터가 있다면 이를 우선하여 덮어씀
    temp = float(forecast_data.get('temp', '0'))
    wind_speed = float(forecast_data.get('wind_speed', '0'))
    humidity = float(forecast_data.get('humidity', '0'))
    pty_value = int(forecast_data.get('pty', '0'))
    sky_value = forecast_data.get('sky', '1')
    wind_dir_val = float(forecast_data.get('wind_dir', '0')) 

    if live_data:
        temp = live_data.get('T1H', temp)
        wind_speed = live_data.get('WSD', wind_speed)
        humidity = live_data.get('REH', humidity)
        pty_value = int(live_data.get('PTY', pty_value))
        if 'VEC' in live_data: wind_dir_val = live_data['VEC']

    # 현재 기온을 바탕으로 옷차림을 추천하고 생활 지수(빨래, 세차)를 계산함
    clothing_recs = get_clothing_recommendation(temp)
    indices = calculate_lifestyle_indices(temp, humidity, 0, pty_value)

    # 어제 동시간대 기온을 조회하여 오늘 기온과 비교 분석 메시지를 생성함
    yesterday_temp = get_yesterday_seoul_temp(KMA_API_KEY)
    temp_diff_info = {"diff": 0, "msg": "데이터 없음", "icon": "dash"}
    
    if yesterday_temp is not None:
        diff = round(temp - yesterday_temp, 1)
        if diff > 0:
            msg = f"어제보다 {abs(diff)}°C 높아요"
            icon = "caret-up-fill text-danger"
        elif diff < 0:
            msg = f"어제보다 {abs(diff)}°C 낮아요"
            icon = "caret-down-fill text-primary"
        else:
            msg = "어제와 기온이 같아요"
            icon = "dash-lg text-secondary"
            
        temp_diff_info = {
            "diff": diff,
            "msg": msg,
            "icon": icon,
            "yesterday_temp": yesterday_temp
        }

    # 템플릿 렌더링에 필요한 모든 데이터를 딕셔너리로 구성함
    processed_data = {
        "location": f"서울 {selected_district}",
        "T1H": temp,
        "SENSIBLE_TEMP": round(13.12 + 0.6215*temp - 11.37*(wind_speed**0.16) + 0.3965*temp*(wind_speed**0.16), 1),
        "RN1": live_data.get('RN1', 0) if live_data else forecast_data.get('precip', 0),
        "REH": humidity,
        "WSD": wind_speed,
        "VEC": wind_dir_val, 
        "VEC_STR": get_wind_direction_str(wind_dir_val),
        "SKY": sky_value,
        "PTY": pty_value,
        "date": datetime.now().strftime('%m월 %d일'),
        "time": datetime.now().strftime('%H:%M'),
        "temp_diff": temp_diff_info,
        "clothing": clothing_recs,
        "laundry": indices['laundry'],
        "carwash": indices['carwash'],
        "comment": expert_comment,
        "commute": commute_report,
    }

    context = {
        "page_title": "현재 날씨",
        "data": processed_data,
        "sky_status": get_sky_status(processed_data['SKY'], processed_data['PTY']),
        "satellite_url": satellite_url,
        "warning_msg": warning_msg,
        "districts": SEOUL_DISTRICTS.keys(),
        "current_district": selected_district,
        "mini_chart_data": short_term_all[:6] 
    }
    return render_template('index.html', **context)

# 상세 예보 페이지('/forecast') 요청 시 실행되며, 단기 및 중기 예보 데이터를 병합하여 전달함
@app.route('/forecast')
def forecast():
    selected_district = request.args.get('district', '종로구')
    coords = SEOUL_DISTRICTS.get(selected_district, {"nx": 60, "ny": 127})
    nx, ny = coords['nx'], coords['ny']

    # 시간별 단기 예보와 주간 중기 예보 데이터를 각각 조회하고 하나로 합침
    short_term_all = get_hourly_forecast(KMA_API_KEY, nx, ny, hours=None) or []
    mid_term_data = get_mid_term_forecast(KMA_API_KEY)
    weekly_data = short_term_all + mid_term_data

    # 그래프 시각화를 위해 기온 데이터의 최소값과 최대값을 동적으로 계산함
    y_min, y_max = 0, 30
    if weekly_data:
        temps = [d['temp'] for d in weekly_data if 'temp' in d]
        if temps:
            y_min = min(temps)
            y_max = max(temps)

    context = {
        "page_title": "상세 예보",
        "districts": SEOUL_DISTRICTS.keys(),
        "current_district": selected_district,
        "short_term_data": short_term_all[:12], 
        "weekly_data": weekly_data,
        "graph_min": y_min,
        "graph_max": y_max
    }
    return render_template('forecast.html', **context)

# 레이더 영상 페이지('/radar') 요청 시 실행되며, 영상 URL과 정밀 분석 데이터를 전달함
@app.route('/radar')
def radar():
    selected_district = request.args.get('district', '종로구')
    satellite_url = get_satellite_image_url(KMA_API_KEY)
    radar_url = get_radar_image_url(KMA_API_KEY)
    
    # 선택된 지역의 레이더 반사도 수치를 조회하고 분석 알고리즘을 수행함
    radar_val = get_radar_value_for_district(KMA_API_KEY, selected_district)
    analysis = analyze_radar_intensity(radar_val)
    
    radar_val_str = f"{radar_val} dBZ" if radar_val is not None else "수신 대기"

    context = {
        "page_title": "기상 영상 분석",
        "districts": SEOUL_DISTRICTS.keys(),
        "current_district": selected_district,
        "satellite_url": satellite_url,
        "radar_url": radar_url,
        "radar_val": radar_val_str,
        "radar_class": analysis['color'],
        "radar_analysis": analysis['desc'], 
        "analysis": analysis 
    }
    return render_template('radar.html', **context)

# 풍향 각도(0~360)를 16방위 한글 텍스트(북서풍)로 변환하여 반환함
def get_wind_direction_str(vec_val):
    try:
        vec = float(vec_val)
        directions = ["북", "북북동", "북동", "동북동", "동", "동남동", "남동", "남남동", "남", "남남서", "남서", "서남서", "서", "서북서", "북서", "북북서", "북"]
        index = int((vec + 11.25) / 22.5)
        return f"{directions[index % 16]}풍"
    except:
        return ""