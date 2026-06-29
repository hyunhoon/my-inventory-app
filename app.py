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
            df_counts = df_orders.groupby(['매출처', '제품명']).size().reset_index(name='order_count')
            df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
            df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
            df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
            cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
            cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)].copy()
            cyc = cyc[~cyc['제품명'].str.contains('하모닐란|엔커버', na=False)]
            cyc = pd.merge(cyc, df_counts, on=['매출처', '제품명'], how='left')
            
            def get_sort_key(row):
                expected = row['r_il'] + timedelta(days=int(row['p_ju']))
                days = (expected - current_date).days
                stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                is_low_stock = stk < row['p_am']
                if days < 0: return (3, days)
                if row['order_count'] > 3 and is_low_stock: return (0, days)
                if is_low_stock: return (1, days)
                return (2, days)

            cyc['sort_key'] = cyc.apply(get_sort_key, axis=1)
            cyc = cyc.sort_values('sort_key')
            
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
            st.header("▶️ 유효기간 365일 미만 의약품 목록")
            lim_365 = current_date + timedelta(days=365)
            if '유효기간_날짜' in df_inventory.columns:
                s_exp = df_inventory[(df_inventory['유효기간_날짜'].notna()) & 
                                     (df_inventory['유효기간_날짜'] <= lim_365) & 
                                     (df_inventory['재고수량'] > 0) & 
                                     (~df_inventory['제품명'].str.contains('하모닐란|엔커버', na=False))].sort_values(by='유효기간_날짜')
                for _, row in s_exp.iterrows():
                    rem_d = (row['유효기간_날짜'] - current_date).days
                    if rem_d < 180: st.error(f"💥 **[초긴급 - 180일 미만]** **{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {row['유효기간_표시']} (**{rem_d}일 남음**)")
                    else: st.warning(f"⚠️ **[주의 - 1년 미만]** **{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {row['유효기간_표시']} ({rem_d}일 남음)")

        with t4:
            st.header("▶️ 90일 이상 장기 미출고 의약품")
            if not df_orders.empty and '출고일자' in df_orders.columns:
                df_l = df_orders.groupby('제품명')['출고일자'].max().reset_index()
                df_l.columns = ['제품명', '최종일']
                df_chk = pd.merge(df_inventory, df_l, on='제품명', how='left')
                df_chk = df_chk[df_chk['재고수량'] > 0].copy()
                df_chk['경과일'] = (current_date - df_chk['최종일']).dt.days
                df_chk['기록없음'] = df_chk['최종일'].isna()
                lim_90 = current_date - timedelta(days=90)
                df_filtered = df_chk[df_chk['기록없음'] | (df_chk['최종일'] <= lim_90)].copy()
                if not df_filtered.empty:
                    df_filtered = df_filtered.sort_values(by=['기록없음', '경과일'], ascending=[False, False])
                    for idx, row in df_filtered.iterrows():
                        yuhyo = row['유효기간_표시'] if '유효기간_표시' in row and str(row['유효기간_표시']) != 'nan' else "기록없음"
                        if row['기록없음']:
                            st.info(f"**{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {yuhyo} • 출고 기록 없음")
                        else:
                            st.info(f"**{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {yuhyo} • 최종일: {row['최종일'].strftime('%Y-%m-%d')} (**{int(row['경과일'])}일 경과**)")

        with t5:
            st.header("▶️ 창고 전체 현재 재고 현황")
            # 1. 검색 및 단일 선택 로직 (데이터 편집기 대신 selectbox 사용)
            p_search = st.text_input("🔍 제품명 검색:", "", key="p_search_t5")
            df_f = df_inventory[['제품명', '재고수량', '유효기간_표시']].copy()
            
            # 검색 필터링
            if p_search:
                df_f_filtered = df_f[df_f['제품명'].str.contains(p_search, case=False, na=False)]
            else:
                df_f_filtered = df_f
            
            # 제품 리스트 추출
            product_list = df_f_filtered['제품명'].unique().tolist()
            
            if product_list:
                s_prod = st.selectbox("조회할 제품을 선택하세요:", product_list)
                
                # 전체 목록 보기 (참고용)
                st.dataframe(df_f, use_container_width=True, hide_index=True)
                
                st.markdown("---")
                st.markdown(f"### 📊 [{s_prod}] 출고 이력 상세")
                
                # 상세 조회
                df_p_ord = df_orders[df_orders['제품명'] == s_prod].copy()
                if not df_p_ord.empty:
                    df_h = df_p_ord[['매출처', '출고일자', '수량']].copy()
                    df_h['출고일자'] = df_h['출고일자'].dt.strftime('%Y-%m-%d')
                    st.dataframe(df_h.sort_values(by='출고일자', ascending=False), use_container_width=True, hide_index=True)
                else:
                    st.info("해당 제품의 출고 이력이 없습니다.")
            else:
                st.warning("검색된 제품이 없습니다.")
else:
    st.error("데이터 파일을 찾을 수 없습니다.")