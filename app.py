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

# --- [자동 알림 시스템] ---
TELEGRAM_TOKEN = "8738343974:AAFrFB26q547kfnj9-xRwHnyVj1qRs0KdlI"
TELEGRAM_CHAT_ID = "-1004415384295"
LOG_FILE = "alert_log.json"

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

def run_automated_check():
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    today = now_kst.strftime("%Y-%m-%d")
    if not (now_kst.hour == 9 and now_kst.minute == 30): return
    logs = load_logs()
    if logs.get("LAST_RUN_DATE") == today: return
    ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"
    if not (os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE)): return
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)
    for df in [df_orders, df_inventory]:
        if '운송비' in df.columns: df.drop(columns=['운송비'], inplace=True)
    df_orders = df_orders[df_orders['제품명'].astype(str) != '운송비']
    df_inventory = df_inventory[df_inventory['제품명'].astype(str) != '운송비']
    logs["LAST_RUN_DATE"] = today
    save_logs(logs)

threading.Thread(target=run_automated_check, daemon=True).start()

# --- [탭 기능 함수] ---
@st.fragment
def render_t1(df_orders):
    st.header("🏢 매출처별 출고 리스트")
    # 오류 방지: 매출처를 문자열로 변환하고 결측치 처리
    df_orders['매출처'] = df_orders['매출처'].fillna('').astype(str)
    u_cust = sorted([c for c in df_orders['매출처'].unique() if c.strip() != ''])
    c_search = st.text_input("🔍 매출처 검색:", "", key="c_search_t1")
    f_cust = [c for c in u_cust if c_search.lower() in c.lower()] if c_search else u_cust
    df_cust_list = pd.DataFrame({'매출처': f_cust})
    df_cust_list.insert(0, "선택", False)
    df_cust_list['선택'] = df_cust_list['매출처'] == st.session_state.get('selected_customer')
    edited_cust = st.data_editor(df_cust_list, column_config={"선택": st.column_config.CheckboxColumn(required=True)}, use_container_width=True, hide_index=True)
    changed = edited_cust[edited_cust['선택'] != df_cust_list['선택']]
    if not changed.empty:
        new_checked = changed[changed['선택'] == True]
        st.session_state['selected_customer'] = new_checked.iloc[0]['매출처'] if not new_checked.empty else None
    if st.session_state.get('selected_customer'):
        s_cust = st.session_state['selected_customer']
        st.markdown(f"### 📅 {s_cust} 상세 내역")
        df_c_ord = df_orders[df_orders['매출처'] == s_cust].copy()
        st.dataframe(df_c_ord.sort_values(by='출고일자', ascending=False), use_container_width=True, hide_index=True)

@st.fragment
def render_medical_device(df_orders):
    st.header("🏥 의료기기 월별 출고 현황")
    df_med = df_orders[df_orders['제품명'].str.contains('의료기', na=False)].copy()
    if df_med.empty:
        st.info("데이터 내에 '의료기' 관련 항목이 없습니다.")
    else:
        df_med['출고월'] = df_med['출고일자'].dt.to_period('M')
        monthly_pivot = df_med.pivot_table(index='제품명', columns='출고월', values='수량', aggfunc='sum', fill_value=0)
        st.dataframe(monthly_pivot, use_container_width=True)

# --- [메인 실행] ---
st.set_page_config(page_title="의약품 통합 분석 시스템", layout="wide")
st.title("📊 의약품 통합 분석 시스템")
ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"
if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)
    
    # 1. 운송비 제거
    for df in [df_orders, df_inventory]:
        if '운송비' in df.columns: df.drop(columns=['운송비'], inplace=True)
    df_orders = df_orders[df_orders['제품명'].astype(str) != '운송비']
    df_inventory = df_inventory[df_inventory['제품명'].astype(str) != '운송비']
    
    # 2. 데이터 정제
    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    df_orders['매출처'] = df_orders['매출처'].fillna('').astype(str).str.strip()
    df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
    
    # 탭 구성
    tabs = st.tabs(["🏢 출고리스트", "⚠️ 주문시기", "🚨 유효기간", "📦 장기미출고", "📋 전체재고", "🏥 의료기기"])
    with tabs[0]: render_t1(df_orders)
    # 다른 탭들도 위와 같은 방식으로 호출
    with tabs[5]: render_medical_device(df_orders)
else:
    st.error("데이터 파일을 찾을 수 없습니다.")