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

# --- [설정] ---
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

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        requests.get(url, params=params)
    except:
        pass

def run_automated_check():
    # 1. 한국 시간 설정
    kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(kst)
    today = now_kst.strftime("%Y-%m-%d")
    
    # 2. 9시 30분이 아니면 종료
    if not (now_kst.hour == 9 and now_kst.minute == 30):
        return

    # 3. 오늘 이미 알림 작업을 수행했다면 종료 (중복 방지 핵심)
    logs = load_logs()
    if logs.get("LAST_RUN_DATE") == today:
        return

    # 4. 주말/공휴일 체크
    kr_holidays = holidays.KR()
    if now_kst.weekday() >= 5 or today in kr_holidays:
        return

    # 5. 데이터 파일 확인
    ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"
    if not (os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE)):
        return
    
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)
    
    # 데이터 전처리
    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
    df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
    
    # --- [작업 1: 주문 시기 알림] ---
    df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
    df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
    df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
    cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
    cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)]
    
    for _, row in cyc.iterrows():
        expected = row['r_il'] + timedelta(days=int(row['p_ju']))
        days_left = (expected - now_kst.replace(tzinfo=None)).days
        if days_left == 5:
            stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
            if stk < row['p_am']:
                msg = f"⚠️ [주문 알림]\n{row['매출처']} - {row['제품명']}\n예상일: {expected.strftime('%Y-%m-%d')}\n재고: {stk:.0f} < 주문량: {row['p_am']:.0f}"
                send_telegram(msg)
                time.sleep(1) # 전송 간격 확보

    # --- [작업 2: 유효기간 알림] ---
    if '유효기간' in df_inventory.columns:
        df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간'].astype(str).str.split('.').str[0], format='%Y%m%d', errors='coerce')
        lim_180 = now_kst.replace(tzinfo=None) + timedelta(days=180)
        s_exp = df_inventory[(df_inventory['유효기간_날짜'].notna()) & (df_inventory['유효기간_날짜'] <= lim_180) & (df_inventory['재고수량'] > 0)]
        for _, row in s_exp.iterrows():
            rem_d = (row['유효기간_날짜'] - now_kst.replace(tzinfo=None)).days
            msg = f"🚨 [유효기간 임박]\n{row['제품명']}\n남은 기간: {rem_d}일\n재고: {row['재고수량']:.0f}개"
            send_telegram(msg)
            time.sleep(1) # 전송 간격 확보

    # 6. 완료 기록 저장
    logs["LAST_RUN_DATE"] = today
    save_logs(logs)

# 백그라운드 스레드 시작
threading.Thread(target=lambda: [run_automated_check() or time.sleep(60) for _ in iter(int, 1)], daemon=True).start()

# --- [UI 메인 코드] ---
st.set_page_config(page_title="의약품 창고 및 주문 통합 분석 시스템", layout="wide")
st.title("📊 의약품 통합 분석 시스템")

# [UI 프래그먼트들 생략 가능 - 기존과 동일]
@st.fragment
def render_tabs(df_orders, df_inventory, current_date):
    t1, t2, t3, t4, t5 = st.tabs(["🏢 출고 리스트", "⚠️ 주문시기 알림", "🚨 유효기간 임박", "📦 장기 미출고", "📋 전체 재고"])
    with t1:
        st.header("🏢 매출처별 출고 리스트")
        # (기존 T1 로직 유지)
        c_search = st.text_input("🔍 매출처 검색:", key="c_s")
        st.dataframe(df_orders[df_orders['매출처'].str.contains(c_search, na=False)], use_container_width=True)
    with t2:
        st.header("▶️ 주문 시기 및 재고 부족 위험")
        # (기존 T2 로직 유지)
    with t3:
        st.header("▶️ 유효기간 365일 미만")
        # (기존 T3 로직 유지)
    with t4:
        st.header("▶️ 장기 미출고 재고")
    with t5:
        st.header("▶️ 전체 재고")

# 메인 실행
if os.path.exists("출고데이터.xls") and os.path.exists("재고데이터.xls"):
    df_orders = pd.read_excel("출고데이터.xls")
    df_inventory = pd.read_excel("재고데이터.xls")
    render_tabs(df_orders, df_inventory, datetime.now())
else:
    st.error("데이터 파일을 찾을 수 없습니다.")