import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import requests
import time
import threading
import json
import holidays
import pytz

# --- [자동 알림 시스템 설정] ---
TELEGRAM_TOKEN = "8738343974:AAFrFB26q547kfnj9-xRwHnyVj1qRs0KdlI"
TELEGRAM_CHAT_ID = "-1004415384295"
LOG_FILE = "alert_log.json"

# [로그 함수들 생략(기존과 동일)]
def load_logs():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            try: return json.load(f)
            except: return {}
    return {}

def save_logs(logs):
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=4)

def check_and_send(key, msg):
    logs = load_logs()
    today = datetime.now().strftime("%Y-%m-%d")
    if logs.get(key) == today: return False
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        res = requests.get(url, params=params).json()
        if res.get('ok'):
            logs[key] = today
            save_logs(logs)
            return True
    except: pass
    return False

# [자동 알림 체크 로직 (운송비 제거 포함)]
def run_automated_check():
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    today = now_kst.strftime("%Y-%m-%d")
    if not (now_kst.hour == 9 and now_kst.minute == 30): return
    
    ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"
    if not (os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE)): return
    
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)
    
    # [운송비 원천 차단]
    for df in [df_orders, df_inventory]:
        if '운송비' in df.columns: df.drop(columns=['운송비'], inplace=True)
    df_orders = df_orders[df_orders['제품명'].astype(str) != '운송비']
    df_inventory = df_inventory[df_inventory['제품명'].astype(str) != '운송비']
            
    # [데이터 정제]
    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    # (이하 알림 상세 로직은 기존 코드 사용 가능)
    
# [UI 탭 함수들]
@st.fragment
def render_medical_device(df_orders):
    st.header("🏥 의료기기 월별 출고 현황")
    df_med = df_orders[df_orders['제품명'].str.contains('의료기', na=False)].copy()
    if df_med.empty:
        st.info("데이터 내에 '의료기' 관련 항목이 없습니다.")
        return
    df_med['출고월'] = df_med['출고일자'].dt.to_period('M')
    monthly_pivot = df_med.pivot_table(index='제품명', columns='출고월', values='수량', aggfunc='sum', fill_value=0)
    st.dataframe(monthly_pivot, use_container_width=True)

# [메인 실행부]
st.set_page_config(page_title="의약품 창고 통합 분석", layout="wide")
ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"

if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)

    # 1. 운송비 완전 제거
    for df in [df_orders, df_inventory]:
        if '운송비' in df.columns: df.drop(columns=['운송비'], inplace=True)
    df_orders = df_orders[df_orders['제품명'].astype(str) != '운송비']
    df_inventory = df_inventory[df_inventory['제품명'].astype(str) != '운송비']

    # 2. 데이터 정제
    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
    
    # 3. 탭 생성
    tabs = st.tabs(["🏢 매출처별 리스트", "📋 전체 재고", "🏥 의료기기 월별 출고"])
    with tabs[0]: st.write("매출처별 리스트 내용...") # 기존 render_t1 사용
    with tabs[1]: st.write("전체 재고 내용...")       # 기존 render_t5 사용
    with tabs[2]: render_medical_device(df_orders)
else:
    st.error("데이터 파일을 찾을 수 없습니다.")