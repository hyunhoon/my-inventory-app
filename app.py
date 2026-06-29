import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import requests
import schedule
import time
import threading
import json
import holidays

# --- [텔레그램 설정] ---
TELEGRAM_TOKEN = "8738343974:AAFrFB26q547kfnj9-xRwHnyVj1qRs0KdlI"
TELEGRAM_CHAT_ID = "-1004415384295"
# --------------------

# --- [자동 알림 로그 관리] ---
LOG_FILE = "alert_log.json"

def load_logs():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_logs(logs):
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(logs, f, ensure_ascii=False, indent=4)

def check_and_send(key, msg):
    logs = load_logs()
    today = datetime.now().strftime("%Y-%m-%d")
    
    # 이미 오늘 전송했거나 기록에 있다면 전송 안함
    if key in logs:
        return False
    
    # 텔레그램 전송
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        res = requests.get(url, params=params).json()
        if res.get('ok'):
            logs[key] = today
            save_logs(logs)
            return True
    except:
        pass
    return False

# --- [데이터 처리 및 자동 알림 로직] ---
def run_automated_check():
    # 휴일/주말 확인
    kr_holidays = holidays.KR()
    today = datetime.now()
    if today.weekday() >= 5 or today in kr_holidays:
        return

    ORDER_FILE = "출고데이터.xls"
    INVENTORY_FILE = "재고데이터.xls"
    if not (os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE)):
        return

    # 데이터 로드
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)

    # 데이터 정제 (기존 로직 동일)
    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
    
    # [조건 1] 주문시기 5일 전 & 재고 부족
    df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
    df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
    df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
    df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
    
    cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
    cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)]
    
    for _, row in cyc.iterrows():
        expected_date = row['r_il'] + timedelta(days=int(row['p_ju']))
        days_left = (expected_date - datetime.now()).days
        
        if 0 <= days_left <= 5: # 5일 전 도래
            stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
            if stk < row['p_am']:
                msg = f"⚠️ [주문 알림] {row['매출처']} - {row['제품명']}\n예상일: {expected_date.strftime('%Y-%m-%d')} ({days_left}일 남음)\n재고: {stk:.0f} < 주문량: {row['p_am']:.0f}"
                check_and_send(f"{datetime.now().strftime('%Y-%m-%d')}_{row['매출처']}_{row['제품명']}_ORDER", msg)

    # [조건 2] 유효기간 180일 미만
    if '유효기간' in df_inventory.columns:
        df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간'].astype(str), format='%Y%m%d', errors='coerce')
        s_exp = df_inventory[(df_inventory['유효기간_날짜'].notna()) & (df_inventory['재고수량'] > 0)]
        for _, row in s_exp.iterrows():
            rem_d = (row['유효기간_날짜'] - datetime.now()).days
            if rem_d < 180:
                msg = f"💥 [유효기간 초긴급] {row['제품명']}\n만료까지 {rem_d}일 남음 ({row['유효기간_날짜'].strftime('%Y-%m-%d')})"
                check_and_send(f"{datetime.now().strftime('%Y-%m-%d')}_{row['제품명']}_EXPIRY", msg)

# 스케줄러 쓰레드 실행
def scheduler_thread():
    schedule.every().day.at("09:30").do(run_automated_check)
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=scheduler_thread, daemon=True).start()

# --- [Streamlit UI 코드 (기존과 동일)] ---
st.set_page_config(page_title="의약품 통합 분석 시스템", layout="wide")
st.title("📊 의약품 통합 분석 시스템")
# ... (이후 기존 UI 코드 계속)