import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os
import json
import requests

# --- 텔레그램 설정 ---
TELEGRAM_TOKEN = "8738343974:AAFrFB26q547kfnj9-xRwHnyVj1qRs0KdlI"
TELEGRAM_CHAT_ID = "5953515925"
LOG_FILE = "alert_log.json"

def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        params = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
        requests.get(url, params=params)
    except Exception as e:
        print(f"알림 전송 실패: {e}")

def load_log():
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_log(log):
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(log, f)

# 페이지 설정
st.set_page_config(page_title="의약품 창고 및 주문 통합 분석 시스템", layout="wide")
st.title("📊 의약품 통합 분석 시스템")
st.write("데이터를 자동으로 불러와 분석하는 화면입니다.")
st.markdown("---")

ORDER_FILE = "출고데이터.xls"
INVENTORY_FILE = "재고데이터.xls"

def load_data(file_path):
    if file_path.endswith('.csv'): return pd.read_csv(file_path)
    return pd.read_excel(file_path)

if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    df_orders = load_data(ORDER_FILE)
    df_inventory = load_data(INVENTORY_FILE)
    
    # 데이터 정제 (기존 로직 유지)
    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
    k_word = '합계|합 계|\\[합.*\\]|금융비용할인'
    df_orders = df_orders[(df_orders['제품명'] != '') & (~df_orders['제품명'].str.contains(k_word, na=False))]
    df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
    df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
    
    if '유효기간' in df_inventory.columns:
        df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
        df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
        df_inventory['유효기간_표시'] = df_inventory['유효기간_날짜'].dt.strftime('%Y-%m-%d').fillna(df_inventory['유효기간'].astype(str))

    t1, t2, t3, t4, t5 = st.tabs(["🏢 매출처별", "⚠️ 재고 부족", "🚨 유효기간", "📦 장기미출고", "📋 전체재고"])
    
    # [탭 1] 기존 로직 (단일 선택)
    with t1:
        st.header("▶️ 매출처별 출고 상세")
        if "t1_selected" not in st.session_state: st.session_state.t1_selected = None
        u_cust = sorted([c for c in df_orders['매출처'].unique() if c != ''])
        df_cust = pd.DataFrame(u_cust, columns=['매출처'])
        df_cust.insert(0, "선택", False)
        if st.session_state.t1_selected in df_cust['매출처'].values:
            df_cust.loc[df_cust['매출처'] == st.session_state.t1_selected, '선택'] = True
        edited_df1 = st.data_editor(df_cust, column_config={"선택": st.column_config.CheckboxColumn(required=True, width=50)}, hide_index=True)
        current_sel1 = edited_df1[edited_df1['선택'] == True]['매출처'].tolist()
        if len(current_sel1) > 0:
            if current_sel1[-1] != st.session_state.t1_selected:
                st.session_state.t1_selected = current_sel1[-1]
                st.rerun()
        elif st.session_state.t1_selected:
            st.session_state.t1_selected = None
            st.rerun()
        if st.session_state.t1_selected:
            st.dataframe(df_orders[df_orders['매출처'] == st.session_state.t1_selected])

    # [탭 2] 재고 부족 + 알림
    with t2:
        st.header("▶️ 주문 시기 및 재고 부족 위험")
        alert_log = load_log()
        # (기존 데이터 분석 로직 생략 - 실행 시 작동)
        # ... [중략: 재고 부족 판단 로직] ...
        # (이 부분에 아래 로직을 넣으세요)
        # if stk < row['p_am']:
        #     msg = f"⚠️ [재고부족] {row['매출처']} - {row['제품명']}"
        #     alert_key = f"order_{row['매출처']}_{row['제품명']}"
        #     if alert_key not in alert_log:
        #         send_telegram(msg)
        #         alert_log.append(alert_key)
        #         save_log(alert_log)

    # [탭 3] 유효기간 + 알림
    with t3:
        st.header("▶️ 유효기간 180일 미만 경고")
        alert_log = load_log()
        # (로직 중)
        # if rem_d < 180:
        #     msg = f"🚨 [유효기간] {row['제품명']} - {rem_d}일 남음"
        #     if row['제품명'] not in alert_log:
        #         send_telegram(msg)
        #         alert_log.append(row['제품명'])
        #         save_log(alert_log)

    # [탭 4, 5] (기존 코드 그대로...)

else:
    st.error("데이터 파일을 찾을 수 없습니다.")