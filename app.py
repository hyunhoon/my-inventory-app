import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import requests

# 텔레그램 설정 (토큰과 ID를 넣어주세요)
TELEGRAM_TOKEN = "8738343974:AAFrFB26q547kfnj9-xRwHnyVj1qRs0KdlI"
TELEGRAM_CHAT_ID = "5953515925"
LOG_FILE = "alert_log.json"

# --- [텔레그램 전송 및 로그 기능] ---
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        requests.get(url, params=params)
    except Exception as e:
        st.error(f"알림 전송 실패: {e}")

def load_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f: return json.load(f)
    return []

def save_log(log):
    with open(LOG_FILE, 'w', encoding='utf-8') as f: json.dump(log, f)

# --- [페이지 설정 및 데이터 로드] ---
st.set_page_config(page_title="의약품 창고 및 주문 통합 분석 시스템", layout="wide")
st.title("📊 의약품 통합 분석 시스템")

ORDER_FILE = "출고데이터.xls"
INVENTORY_FILE = "재고데이터.xls"

if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)
    
    # 데이터 정제
    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
    df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
    
    if '유효기간' in df_inventory.columns:
        df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간'].astype(str).str.split('.').str[0], format='%Y%m%d', errors='coerce')

    # 탭 생성
    t1, t2, t3, t4, t5 = st.tabs(["🏢 매출처별", "⚠️ 재고부족", "🚨 유효기간", "📦 장기미출고", "📋 전체재고"])

    # [탭 1] 매출처별 출고
    with t1:
        st.header("🏢 매출처별 출고 리스트")
        selected_cust = st.selectbox("매출처를 선택하세요", options=df_orders['매출처'].unique())
        st.dataframe(df_orders[df_orders['매출처'] == selected_cust])

    # [탭 2] 재고부족 알림
    with t2:
        st.header("⚠️ 주문시기 및 재고부족 알림")
        alert_log = load_log()
        # 예시 로직: 재고가 10개 미만인 경우
        shortage = df_inventory[df_inventory['재고수량'] < 10]
        st.dataframe(shortage)
        
        for idx, row in shortage.iterrows():
            msg = f"⚠️ [재고부족] {row['제품명']} (현재고: {row['재고수량']})"
            if row['제품명'] not in alert_log:
                send_telegram(msg)
                alert_log.append(row['제품명'])
        save_log(alert_log)

    # [탭 3] 유효기간 알림
    with t3:
        st.header("🚨 유효기간 180일 미만 경고")
        alert_log = load_log()
        target_date = datetime.now() + timedelta(days=180)
        exp_warn = df_inventory[df_inventory['유효기간_날짜'] < target_date]
        st.dataframe(exp_warn)
        
        for idx, row in exp_warn.iterrows():
            msg = f"🚨 [유효기간] {row['제품명']} (만료일: {row['유효기간_날짜'].strftime('%Y-%m-%d')})"
            if row['제품명'] not in alert_log:
                send_telegram(msg)
                alert_log.append(row['제품명'])
        save_log(alert_log)

    # [탭 4, 5] 나머지 탭도 여기서 구현 가능
    with t4: st.write("장기 미출고 데이터 영역입니다.")
    with t5: st.dataframe(df_inventory)

else:
    st.error("데이터 파일(출고데이터.xls, 재고데이터.xls)을 찾을 수 없습니다.")