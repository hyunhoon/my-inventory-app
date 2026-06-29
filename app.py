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

# 페이지 설정
st.set_page_config(page_title="의약품 창고 및 주문 통합 분석 시스템", layout="wide")

# --- [자동 알림 시스템] ---
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
    if key in logs: return False
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
    kr_holidays = holidays.KR()
    today = datetime.now()
    if today.weekday() >= 5 or today in kr_holidays: return
    
    ORDER_FILE = "출고데이터.xls"
    INVENTORY_FILE = "재고데이터.xls"
    if not (os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE)): return
    
    try:
        df_orders = pd.read_excel(ORDER_FILE)
        df_inventory = pd.read_excel(INVENTORY_FILE)
        df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
        df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
        df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
        
        # [주문시기]
        df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
        df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
        df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
        cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
        cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)]
        for _, row in cyc.iterrows():
            expected = row['r_il'] + timedelta(days=int(row['p_ju']))
            days_left = (expected - datetime.now()).days
            if 0 <= days_left <= 5:
                stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                if stk < row['p_am']:
                    msg = f"⚠️ [주문 알림] {row['매출처']} - {row['제품명']}\n예상일: {expected.strftime('%Y-%m-%d')} ({days_left}일 남음)\n재고: {stk:.0f} < 주문량: {row['p_am']:.0f}"
                    check_and_send(f"{datetime.now().strftime('%Y-%m-%d')}_{row['매출처']}_{row['제품명']}_ORDER", msg)
        
        # [유효기간]
        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간'].astype(str), format='%Y%m%d', errors='coerce')
            for _, row in df_inventory[df_inventory['유효기간_날짜'].notna()].iterrows():
                rem_d = (row['유효기간_날짜'] - datetime.now()).days
                if rem_d < 180:
                    msg = f"💥 [유효기간 초긴급] {row['제품명']}\n만료: {row['유효기간_날짜'].strftime('%Y-%m-%d')} ({rem_d}일 남음)"
                    check_and_send(f"{datetime.now().strftime('%Y-%m-%d')}_{row['제품명']}_EXPIRY", msg)
    except: pass

def scheduler_thread():
    schedule.every().day.at("09:30").do(run_automated_check)
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=scheduler_thread, daemon=True).start()

# --- [UI 코드] ---
st.title("📊 의약품 통합 분석 시스템")
ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"

if not (os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE)):
    st.error("파일이 없습니다! '출고데이터.xls'와 '재고데이터.xls' 파일이 GitHub 저장소에 있는지 확인하세요.")
else:
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)
    # 데이터 정리 및 분석 로직 (기존과 동일)
    # ... (생략된 기존 분석 탭 코드들이 여기에 들어감)
    st.success("데이터가 성공적으로 로드되었습니다.")