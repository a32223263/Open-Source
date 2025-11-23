import time
from flask import Flask, render_template, request, url_for
from kma_api import (
    get_forecast, get_satellite_image_url, get_hourly_forecast, 
    get_live_weather, get_weather_warning, get_radar_image_url, 
    get_mid_term_forecast, get_radar_value_for_district,
    SEOUL_DISTRICTS
)

app = Flask(__name__)
KMA_API_KEY = "2fqF3fBYST-6hd3wWEk_RA" 

def get_sky_status(sky_code: str, pty_code: str) -> str:
    if pty_code != 0:
        pty_map = {1: '비', 2: '비/눈', 3: '눈', 4: '소나기', 5: '빗방울', 6: '빗방울/눈날림', 7: '눈날림'}
        return pty_map.get(pty_code, "알 수 없는 강수")
    else:
        sky_map = {'1': '맑음', '3': '구름많음', '4': '흐림'}
        return sky_map.get(sky_code, "알 수 없음")

@app.route('/')
def index():
    selected_district = request.args.get('district', '종로구')
    coords = SEOUL_DISTRICTS.get(selected_district, {"nx": 60, "ny": 127})
    nx, ny = coords['nx'], coords['ny']

    forecast_data = get_forecast(KMA_API_KEY, nx, ny)
    live_data = get_live_weather(KMA_API_KEY, nx, ny)
    warning_msg = get_weather_warning(KMA_API_KEY)
    satellite_url = get_satellite_image_url(KMA_API_KEY)

    if not forecast_data:
        return render_template('error.html', message="데이터 로딩 실패")

    temp = float(forecast_data.get('temp', '0'))
    wind_speed = float(forecast_data.get('wind_speed', '0'))
    humidity = float(forecast_data.get('humidity', '0'))
    pty_value = int(forecast_data.get('pty', '0'))
    precip = 0.0

    if live_data:
        temp = live_data.get('T1H', temp)
        humidity = live_data.get('REH', humidity)
        wind_speed = live_data.get('WSD', wind_speed)
        pty_value = int(live_data.get('PTY', pty_value))
        rn1 = live_data.get('RN1', 0)
        if rn1 > 0: precip = rn1

    processed_data = {
        "location": f"서울 {selected_district}",
        "date": time.strftime("%Y년 %m월 %d일"),
        "time": time.strftime("%H:%M"),
        "T1H": temp,
        "RN1": precip,
        "WSD": wind_speed,
        "REH": humidity,
        "SKY": forecast_data.get('sky', '1'),
        "PTY": pty_value,
        "SENSIBLE_TEMP": round(13.12 + 0.6215*temp - 11.37*(wind_speed**0.16) + 0.3965*temp*(wind_speed**0.16), 1),
        "is_live": True if live_data else False
    }

    context = {
        "page_title": "현재 날씨",
        "data": processed_data,
        "sky_status": get_sky_status(processed_data['SKY'], processed_data['PTY']),
        "satellite_url": satellite_url,
        "warning_msg": warning_msg,
        "districts": SEOUL_DISTRICTS.keys(),
        "current_district": selected_district
    }
    return render_template('index.html', **context)

@app.route('/forecast')
def forecast():
    selected_district = request.args.get('district', '종로구')
    coords = SEOUL_DISTRICTS.get(selected_district, {"nx": 60, "ny": 127})
    nx, ny = coords['nx'], coords['ny']
    
    short_term_all = get_hourly_forecast(KMA_API_KEY, nx, ny, hours=None) or []
    short_term_data = short_term_all[:12] if short_term_all else []
    mid_term_data = get_mid_term_forecast(KMA_API_KEY)
    weekly_data = short_term_all + mid_term_data

    if weekly_data:
        temps = [d['temp'] for d in weekly_data if 'temp' in d]
        y_min, y_max = (min(temps) - 5, max(temps) + 5) if temps else (0, 30)
    else:
        y_min, y_max = 0, 30

    context = {
        "page_title": "상세 예보",
        "districts": SEOUL_DISTRICTS.keys(),
        "current_district": selected_district,
        "short_term_data": short_term_data,
        "weekly_data": weekly_data,
        "graph_min": y_min, "graph_max": y_max
    }
    return render_template('forecast.html', **context)

@app.route('/radar')
def radar():
    selected_district = request.args.get('district', '종로구')
    satellite_url = get_satellite_image_url(KMA_API_KEY)
    radar_url = get_radar_image_url(KMA_API_KEY)
    radar_val = get_radar_value_for_district(KMA_API_KEY, selected_district)
    
    radar_analysis = ""
    radar_class = "secondary"
    radar_val_str = "-"
    
    if radar_val is not None:
        radar_val_str = f"{radar_val} dBZ"
        if radar_val <= 0: radar_analysis = "관측된 강수 에코가 없습니다. (비 안옴)"; radar_class = "secondary"
        elif radar_val < 20: radar_analysis = "매우 약한 에코 감지 (흐림/빗방울)"; radar_class = "info"
        elif radar_val < 35: radar_analysis = "약한 비 가능성"; radar_class = "success"
        elif radar_val < 45: radar_analysis = "보통 비"; radar_class = "warning"
        else: radar_analysis = "강한 비(호우) 주의!"; radar_class = "danger"
    else:
        radar_analysis = "데이터 로딩 실패"; radar_val_str = "-"

    context = {
        "page_title": time.strftime("%Y-%m-%d %H:%M"),
        "districts": SEOUL_DISTRICTS.keys(),
        "current_district": selected_district,
        "satellite_url": satellite_url,
        "radar_url": radar_url,
        "radar_val": radar_val_str,
        "radar_analysis": radar_analysis,
        "radar_class": radar_class
    }
    return render_template('radar.html', **context)