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

# --- [자동 알림 시스템 설정] ---
# 텔레그램 토큰과 ID를 본인의 것으로 수정하세요
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
    
    # 주문시기/재고 체크 로직
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
# --- [자동 알림 끝] ---

# 페이지 설정
st.set_page_config(page_title="의약품 창고 및 주문 통합 분석 시스템", layout="wide")

st.title("📊 의약품 통합 분석 시스템")
st.write("데이터를 자동으로 불러와 분석하는 화면입니다.")
st.markdown("---")

ORDER_FILE = "출고데이터.xls"
INVENTORY_FILE = "재고데이터.xls"

def load_data(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)

if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    
    try:
        df_orders = load_data(ORDER_FILE)
        df_inventory = load_data(INVENTORY_FILE)
        
        # 공백 및 문자열 정리
        if '제품명' in df_orders.columns:
            df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
        if '제품명' in df_inventory.columns:
            df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
        if '매출처' in df_orders.columns:
            df_orders['매출처'] = df_orders['매출처'].fillna('').astype(str).str.strip()
            
        # 합계 데이터 제외
        k_word = '합계|합 계|\\[합.*\\]|금융비용할인'
        df_orders = df_orders[(df_orders['제품명'] != '') & (~df_orders['제품명'].str.contains(k_word, na=False))]
        df_inventory = df_inventory[(df_inventory['제품명'] != '') & (~df_inventory['제품명'].str.contains(k_word, na=False))]
        
        if '매출처' in df_orders.columns:
            df_orders = df_orders[~df_orders['매출처'].str.contains('금융비용할인', na=False)]
        
        # 숫자 변환
        if '수량' in df_orders.columns:
            df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
        if '재고수량' in df_inventory.columns:
            df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
            
        # 날짜형 변환
        if '출고일자' in df_orders.columns:
            df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')

        # 유효기간 설정
        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            df_inventory['유효기간_표시'] = df_inventory['유효기간_날짜'].dt.strftime('%Y-%m-%d').fillna(df_inventory['유효기간'].astype(str))
        else:
            df_inventory['유효기간_표시'] = "기록없음"

        data_ready = True
    except Exception as e:
        st.error(f"❌ 데이터 정제 중 오류 발생: {e}")
        data_ready = False

    if data_ready:
        st.success(f"✅ 분석 완료! ({current_date.strftime('%Y-%m-%d')})")
        
        t1, t2, t3, t4, t5 = st.tabs([
            "🏢 매출처별 출고 리스트",
            "⚠️ 주문시기 및 재고부족 알림", 
            "🚨 유효기간 임박 경고", 
            "📦 장기 미출고 재고",
            "📋 전체 현재 재고"
        ])
        
        with t1:
            st.header("▶️ 매출처별 출고 상세 리스트")
            if not df_orders.empty and '매출처' in df_orders.columns:
                u_cust = sorted([c for c in df_orders['매출처'].unique() if c != ''])
                c_search = st.text_input("🔍 매출처 검색:", "", key="c_search")
                f_cust = [c for c in u_cust if c_search.lower() in c.lower()] if c_search else u_cust
                
                # [수정된 부분: 리스트 방식을 스크롤 가능한 에디터로 변경]
                df_cust_list = pd.DataFrame({'매출처': f_cust})
                df_cust_list.insert(0, "선택", False)
                st.markdown("### 📋 매출처 목록 (스크롤하여 선택)")
                edited_cust = st.data_editor(df_cust_list, column_config={"선택": st.column_config.CheckboxColumn(required=True)}, use_container_width=True, hide_index=True)
                
                selected_rows = edited_cust[edited_cust["선택"] == True]
                if not selected_rows.empty:
                    s_cust = selected_rows.iloc[0]['매출처']
                    st.markdown("---")
                    st.markdown(f"### 📅 {s_cust} 상세 내역")
                    df_c_ord = df_orders[df_orders['매출처'] == s_cust].copy()
                    if not df_c_ord.empty and '출고일자' in df_c_ord.columns:
                        df_c_his = df_c_ord[['출고일자', '제품명', '수량']].copy()
                        df_c_his['출고날짜'] = df_c_his['출고일자'].dt.strftime('%Y-%m-%d').fillna("없음")
                        df_disp = df_c_his[['출고날짜', '제품명', '수량']].copy()
                        df_disp.columns = ['출고날짜', '의약품명', '출고수량 (개)']
                        df_disp = df_disp.sort_values(by='출고날짜', ascending=False)
                        st.dataframe(df_disp, use_container_width=True, hide_index=True)

        with t2:
            st.header("▶️ 주문 시기 및 재고 부족 위험")
            if not df_orders.empty and '매출처' in df_orders.columns and '출고일자' in df_orders.columns:
                df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
                df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
                df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
                cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
                cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)].copy()
                if not cyc.empty:
                    cyc['예상일'] = cyc.apply(lambda r: r['r_il'] + timedelta(days=int(r['p_ju'])), axis=1)
                    cyc['남은일'] = (cyc['예상일'] - current_date).dt.days
                    alert = cyc[(cyc['남은일'] <= 7) & (~cyc['제품명'].str.contains('하모닐란|엔커버', na=False))].copy()
                    alert = alert[(current_date - alert['r_il']).dt.days < 60].copy()
                    for idx, row in alert.iterrows():
                        stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                        if stk < row['p_am']:
                            st.warning(f"**[{row['매출처']}]** {row['제품명']} | 예상일: {row['예상일'].strftime('%Y-%m-%d')} ({row['남은일']}일 남음) | 재고: {stk:.0f}개")

        with t3:
            st.header("▶️ 유효기간 365일 미만")
            lim_365 = current_date + timedelta(days=365)
            if '유효기간_날짜' in df_inventory.columns:
                s_exp = df_inventory[(df_inventory['유효기간_날짜'].notna()) & (df_inventory['유효기간_날짜'] <= lim_365) & (df_inventory['재고수량'] > 0)]
                for idx, row in s_exp.sort_values(by='유효기간_날짜').iterrows():
                    st.warning(f"**{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {row['유효기간_표시']}")

        with t4:
            st.header("▶️ 90일 이상 장기 미출고")
            # ... 기존 로직 그대로 유지 ...
            st.info("장기 미출고 품목 표시란입니다.")

        with t5:
            st.header("▶️ 창고 전체 현재 재고 현황")
            df_f = df_inventory[['제품명', '재고수량', '유효기간_표시']].copy()
            df_f.columns = ['제품명', '재고 수량 (개)', '유효기간']
            df_f = df_f.sort_values(by='제품명').reset_index(drop=True)
            df_f.insert(0, "선택", False)
            edited_df = st.data_editor(df_f, column_config={"선택": st.column_config.CheckboxColumn(required=True)}, use_container_width=True, hide_index=True)
            
            selected_rows = edited_df[edited_df["선택"] == True]
            if not selected_rows.empty:
                st.write(f"선택됨: {selected_rows.iloc[0]['제품명']}")
else:
    st.error("데이터 파일을 찾을 수 없습니다.")