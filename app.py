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
    now = datetime.now()
    if now.weekday() >= 5 or now in kr_holidays: return
    
    ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"
    if not (os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE)): return
    
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)
    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
    df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
    
    df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
    df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
    df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
    cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
    cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)]
    for _, row in cyc.iterrows():
        expected = row['r_il'] + timedelta(days=int(row['p_ju']))
        days_left = (expected - now).days
        if days_left == 5:
            stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
            if stk < row['p_am']:
                msg = f"⚠️ [주문 알림] {row['매출처']} - {row['제품명']}\n예상일: {expected.strftime('%Y-%m-%d')}\n재고: {stk:.0f} < 주문량: {row['p_am']:.0f}"
                check_and_send(f"{now.strftime('%Y-%m-%d')}_{row['매출처']}_{row['제품명']}_ORDER", msg)

def scheduler_thread():
    schedule.every().day.at("09:30").do(run_automated_check)
    while True:
        schedule.run_pending()
        time.sleep(60)

threading.Thread(target=scheduler_thread, daemon=True).start()

# --- [UI 메인 코드] ---
st.set_page_config(page_title="의약품 창고 및 주문 통합 분석 시스템", layout="wide")
st.title("📊 의약품 통합 분석 시스템")
st.write("데이터를 자동으로 불러와 분석하는 화면입니다.")
st.markdown("---")

ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"

def load_data(file_path):
    if file_path.endswith('.csv'): return pd.read_csv(file_path)
    return pd.read_excel(file_path)

if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    try:
        df_orders = load_data(ORDER_FILE)
        df_inventory = load_data(INVENTORY_FILE)
        df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
        df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
        df_orders['매출처'] = df_orders['매출처'].fillna('').astype(str).str.strip()
        df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
        df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
        df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
        
        # 유효기간 설정
        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            df_inventory['유효기간_표시'] = df_inventory['유효기간_날짜'].dt.strftime('%Y-%m-%d').fillna(df_inventory['유효기간'].astype(str))
        else: df_inventory['유효기간_표시'] = "기록없음"
        data_ready = True
    except Exception as e:
        st.error(f"❌ 데이터 정제 중 오류 발생: {e}")
        data_ready = False

    if data_ready:
        t1, t2, t3, t4, t5 = st.tabs(["🏢 매출처별 출고 리스트", "⚠️ 주문시기 및 재고부족 알림", "🚨 유효기간 임박 경고", "📦 장기 미출고 재고", "📋 전체 현재 재고"])
        
        with t1:
            u_cust = sorted([c for c in df_orders['매출처'].unique() if c != ''])
            c_search = st.text_input("🔍 매출처 검색:", "", key="c_search")
            f_cust = [c for c in u_cust if c_search.lower() in c.lower()] if c_search else u_cust
            df_cust_list = pd.DataFrame({'매출처': f_cust})
            df_cust_list.insert(0, "선택", False)
            edited_cust = st.data_editor(df_cust_list, column_config={"선택": st.column_config.CheckboxColumn(required=True)}, use_container_width=True, hide_index=True)
            selected_rows = edited_cust[edited_cust["선택"] == True]
            if not selected_rows.empty:
                s_cust = selected_rows.iloc[0]['매출처']
                st.markdown(f"### 📅 {s_cust} 상세 내역")
                df_c_ord = df_orders[df_orders['매출처'] == s_cust].copy()
                st.dataframe(df_c_ord.sort_values(by='출고일자', ascending=False), use_container_width=True, hide_index=True)

        with t2:
            st.header("▶️ 주문 시기 및 재고 부족 위험 (우선순위 정렬)")
            # 1. 주문 횟수 계산 및 병합
            df_counts = df_orders.groupby(['매출처', '제품명']).size().reset_index(name='order_count')
            
            # 2. 주기 계산
            df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
            df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
            df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
            cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
            cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)].copy()
            cyc = pd.merge(cyc, df_counts, on=['매출처', '제품명'], how='left')
            
            # 3. 정렬 로직
            def get_sort_key(row):
                expected = row['r_il'] + timedelta(days=int(row['p_ju']))
                days = (expected - current_date).days
                stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                is_low_stock = stk < row['p_am']
                
                # 우선순위 부여
                if days < 0: return (3, days) # 3순위: 날짜 지남 (맨 아래)
                if row['order_count'] > 3 and is_low_stock: return (0, days) # 1순위: 단골 & 재고부족 & 임박
                if is_low_stock: return (1, days) # 2순위: 재고부족 & 임박
                return (2, days) # 기타

            cyc['sort_key'] = cyc.apply(get_sort_key, axis=1)
            cyc = cyc.sort_values('sort_key')
            
            # 4. 출력
            for _, row in cyc.iterrows():
                expected = row['r_il'] + timedelta(days=int(row['p_ju']))
                days = (expected - current_date).days
                stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                if days < 0:
                    st.error(f"❌ **[날짜 경과]** {row['매출처']} - {row['제품명']} (예상일: {expected.strftime('%Y-%m-%d')})")
                elif stk < row['p_am']:
                    msg = f"**[{'★단골' if row['order_count'] > 3 else '일반'}]** {row['매출처']} - {row['제품명']}\n• 예상일: {expected.strftime('%Y-%m-%d')} ({days}일 남음)\n• 재고: {stk:.0f} < 주문량: {row['p_am']:.0f}"
                    if row['order_count'] > 3: st.warning(f"🔥 {msg}")
                    else: st.info(f"💡 {msg}")

        with t3:
            st.header("▶️ 유효기간 365일 미만")
            if '유효기간_날짜' in df_inventory.columns:
                s_exp = df_inventory[(df_inventory['유효기간_날짜'].notna()) & (df_inventory['재고수량'] > 0)].sort_values('유효기간_날짜')
                for _, row in s_exp.iterrows():
                    st.warning(f"**{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {row['유효기간_표시']}")

        with t4:
            st.info("장기 미출고 품목 표시란입니다.")
        with t5:
            st.header("▶️ 창고 전체 현재 재고 현황")
            df_f = df_inventory[['제품명', '재고수량', '유효기간_표시']].copy()
            df_f.insert(0, "선택", False)
            st.data_editor(df_f, use_container_width=True, hide_index=True)
else: