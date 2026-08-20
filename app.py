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
import gspread
from google.oauth2.service_account import Credentials

# --- [필수 컬럼 정의 (열 순서 고정)] ---
REQUIRED_COLUMNS = ["완료", "주문일", "수주처", "품목", "수량", "재고량", "부족량", "특이사항"]

# --- [구글 시트 연동 설정] ---
def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    service_account_info = json.loads(st.secrets["gcp_json"])
    creds = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    client = gspread.authorize(creds)
    return client

def load_saved_orders():
    try:
        client = get_gspread_client()
        sheet = client.open("의약품_주문데이터").worksheet("주문내역")
        data = sheet.get_all_records()
        df = pd.DataFrame(data)
        
        # 빈 시트일 경우 기본 구조 반환
        if df.empty:
            return pd.DataFrame(columns=REQUIRED_COLUMNS)
            
        # KeyError 방지: 필수 컬럼이 빠져있다면 강제로 생성
        for col in REQUIRED_COLUMNS:
            if col not in df.columns:
                df[col] = 0 if col in ["수량", "재고량", "부족량"] else ("" if col != "완료" else False)
                
        if "완료" in df.columns: 
            df["완료"] = df["완료"].astype(str).str.lower() == 'true'
        return df
    except Exception as e:
        st.error(f"구글 시트 연동 오류: {e}")
        return pd.DataFrame(columns=REQUIRED_COLUMNS)

def save_current_orders(df):
    try:
        client = get_gspread_client()
        sheet = client.open("의약품_주문데이터").worksheet("주문내역")
        sheet.clear()
        
        df_to_save = df.copy()
        if "완료" in df_to_save.columns:
            df_to_save["완료"] = df_to_save["완료"].astype(str)
            
        data = [df_to_save.columns.tolist()] + df_to_save.values.tolist()
        sheet.update(data)
    except Exception as e:
        st.error(f"구글 시트 저장 오류: {e}")


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
    if key in logs: return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    params = {"chat_id": TELEGRAM_CHAT_ID, "text": msg}
    try:
        res = requests.get(url, params=params).json()
        if res.get('ok'):
            logs[key] = datetime.now().strftime("%Y-%m-%d") 
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

    kr_holidays = holidays.KR()
    if now_kst.weekday() >= 5 or today in kr_holidays: return

    ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"
    if not (os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE)): return
    
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)
    
    for df in [df_orders, df_inventory]:
        if '운송비' in df.columns: df.drop(columns=['운송비'], inplace=True)
            
    df_orders = df_orders[df_orders['제품명'].astype(str) != '운송비']
    df_inventory = df_inventory[df_inventory['제품명'].astype(str) != '운송비']
            
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
        days_left = (expected - now_kst.replace(tzinfo=None)).days
        if days_left == 5:
            stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
            if stk < row['p_am']:
                msg = f"⚠️ [주문 알림] {row['매출처']} - {row['제품명']}\n예상일: {expected.strftime('%Y-%m-%d')}\n재고: {stk:.0f} < 주문량: {row['p_am']:.0f}"
                order_key = f"{row['매출처']}_{row['제품명']}_{expected.strftime('%Y%m%d')}_ORDER"
                check_and_send(order_key, msg)

    if '유효기간' in df_inventory.columns:
        df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
        df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
        lim_180 = now_kst.replace(tzinfo=None) + timedelta(days=180)
        s_exp = df_inventory[(df_inventory['유효기간_날짜'].notna()) & (df_inventory['유효기간_날짜'] <= lim_180) & (df_inventory['재고수량'] > 0)]
        for _, row in s_exp.iterrows():
            rem_d = (row['유효기간_날짜'] - now_kst.replace(tzinfo=None)).days
            msg = f"🚨 [유효기간 임박] {row['제품명']}\n재고: {row['재고수량']:.0f}개\n남은 기간: {rem_d}일"
            exp_key = f"{row['제품명']}_{row['유효기간_정리']}_EXP"
            check_and_send(exp_key, msg)

    logs = load_logs()
    logs["LAST_RUN_DATE"] = today
    save_logs(logs)

def scheduler_thread():
    while True:
        run_automated_check()
        time.sleep(60)

thread_exists = any(t.name == "AlertScheduler" for t in threading.enumerate())
if not thread_exists:
    t = threading.Thread(target=scheduler_thread, daemon=True, name="AlertScheduler")
    t.start()


# --- [UI 메인 코드] ---
st.set_page_config(page_title="의약품 창고 및 주문 통합 분석 시스템", layout="wide")

st.success("✨ **[구글 시트 연동 완료]** 데이터가 클라우드 구글 시트에 영구 보존됩니다.")

if "order_list" not in st.session_state:
    st.session_state.order_list = load_saved_orders()
elif "완료" not in st.session_state.order_list.columns:
    st.session_state.order_list.insert(0, "완료", False)
    save_current_orders(st.session_state.order_list)

# 열 누락(KeyError) 방지 2차 체크
for col in REQUIRED_COLUMNS:
    if col not in st.session_state.order_list.columns:
        st.session_state.order_list[col] = 0 if col in ["수량", "재고량", "부족량"] else ""

if "reset_counter" not in st.session_state:
    st.session_state.reset_counter = 0

ORDER_FILE, INVENTORY_FILE = "출고데이터.xls", "재고데이터.xls"
if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    df_orders = pd.read_excel(ORDER_FILE)
    df_inventory = pd.read_excel(INVENTORY_FILE)

    for df in [df_orders, df_inventory]:
        if '운송비' in df.columns: df.drop(columns=['운송비'], inplace=True)
    df_orders = df_orders[df_orders['제품명'].astype(str) != '운송비']
    df_inventory = df_inventory[df_inventory['제품명'].astype(str) != '운송비']

    df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
    df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
    if '제품그룹' in df_orders.columns: df_orders['제품그룹'] = df_orders['제품그룹'].fillna('').astype(str).str.strip()
    df_orders['매출처'] = df_orders['매출처'].fillna('').astype(str).str.strip()
    df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
    df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
    df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
    
    if '유효기간' in df_inventory.columns:
        df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
        df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
        df_inventory['유효기간_표시'] = df_inventory['유효기간_날짜'].dt.strftime('%Y-%m-%d').fillna(df_inventory['유효기간'].astype(str))
    else: 
        df_inventory['유효기간_표시'] = "기록없음"
    
    # 사이드바 메뉴
    st.sidebar.title("📌 시스템 메뉴")
    menu = st.sidebar.radio(
        "조회할 항목을 선택하세요:",
        ["📝 신규 주문 등록", "🏢 매출처별 출고 리스트", "⚠️ 주문 시기 및 재고 부족 위험", 
         "🚨 유효기간 임박 경고 (365일 미만)", "📦 장기 미출고 재고 (90일 이상)", 
         "📋 창고 전체 현재 재고 현황", "🏥 의료기기 월별 출고 상세 내역"]
    )
    
    st.sidebar.markdown("---")
    st.sidebar.caption("💡 데이터는 구글 스프레드시트에 실시간 자동 저장됩니다.")

    st.title(menu)
    st.markdown("---")

    # 1. 신규 주문 등록 탭
    if menu == "📝 신규 주문 등록":
        existing_customers = sorted(list(set([str(c) for c in df_orders['매출처'].unique() if str(c).strip() not in ['nan', '']])))
        all_products = set(df_orders['제품명'].unique()).union(set(df_inventory['제품명'].unique()))
        existing_products = sorted(list(set([str(p) for p in all_products if str(p).strip() not in ['nan', '']])))

        st.subheader("새로운 주문(수주) 데이터를 입력하세요.")
        rc = st.session_state.reset_counter

        col1, col2 = st.columns(2)
        with col1: order_date = st.date_input("📅 주문일", datetime.now(), key=f"order_date_{rc}")
        with col2:
            cust_sel = st.selectbox("🏢 수주처 선택", ["선택하세요", "➕ 신규 직접 입력"] + existing_customers, key=f"cust_sel_{rc}")
            if cust_sel == "➕ 신규 직접 입력": cust_input = st.text_input("새로운 수주처명을 입력하세요", key=f"cust_input_{rc}")
            else: cust_input = "" if cust_sel == "선택하세요" else cust_sel

        st.markdown("---")
        st.markdown("### 💊 복수 품목 주문 입력")
        
        prod_sels = st.multiselect("품목을 여러 개 선택하세요", existing_products, key=f"prod_sels_{rc}")
        new_prod_input = st.text_input("➕ [선택사항] 신규 품목이 있다면 쉼표(,)로 구분하여 입력하세요", key=f"new_prod_input_{rc}")

        selected_prods = list(prod_sels)
        if new_prod_input:
            extra_prods = [p.strip() for p in new_prod_input.split(',') if p.strip()]
            for p in extra_prods:
                if p not in selected_prods: selected_prods.append(p)

        order_details = []
        if selected_prods:
            st.markdown("#### 📦 선택한 품목별 수량 및 특이사항 입력")
            for prod in selected_prods:
                current_stock = df_inventory[df_inventory['제품명'] == prod]['재고수량'].sum()
                with st.expander(f"🔹 품목: {prod} (현재 창고 재고: {int(current_stock)}개)", expanded=True):
                    d_col1, d_col2 = st.columns([1, 2])
                    with d_col1: qty = st.number_input(f"주문 수량 ({prod})", min_value=1, step=1, value=1, key=f"qty_{prod}_{rc}")
                    with d_col2: remark = st.text_input(f"특이사항 ({prod})", "", key=f"rem_{prod}_{rc}")
                    
                    order_details.append({
                        "품목": prod, "수량": qty, "재고량": current_stock, "특이사항": remark
                    })

        st.markdown("")
        if st.button("➕ 선택한 모든 품목 주문 목록에 일괄 추가", type="primary"):
            if not cust_input: st.error("⚠️ 수주처를 선택 또는 입력해 주세요.")
            elif not order_details: st.error("⚠️ 주문할 품목을 선택하거나 입력해 주세요.")
            else:
                new_rows_list = []
                for item in order_details:
                    shortage = item["수량"] - item["재고량"]
                    shortage = int(shortage) if shortage > 0 else 0
                    new_rows_list.append({
                        "완료": False, "주문일": order_date.strftime("%m-%d"), "수주처": cust_input,
                        "품목": item["품목"], "수량": int(item["수량"]), "재고량": int(item["재고량"]),
                        "부족량": shortage, "특이사항": item["특이사항"]
                    })
                
                df_new = pd.DataFrame(new_rows_list)
                st.session_state.order_list = pd.concat([st.session_state.order_list, df_new], ignore_index=True)
                save_current_orders(st.session_state.order_list)
                
                st.session_state.reset_counter += 1
                st.success("✅ 주문 목록에 정상적으로 일괄 등록 및 구글 시트 저장 완료!")
                time.sleep(0.5)
                st.rerun()

        st.markdown("---")
        st.markdown("### 📋 등록된 주문 내역 요약 (품목/수량/재고량/특이사항 수정 가능)")
        
        if not st.session_state.order_list.empty:
            # 기존 데이터를 안전하게 수치화
            st.session_state.order_list['수량'] = pd.to_numeric(st.session_state.order_list['수량'], errors='coerce').fillna(0).astype(int)
            st.session_state.order_list['재고량'] = pd.to_numeric(st.session_state.order_list['재고량'], errors='coerce').fillna(0).astype(int)
            
            df_display = st.session_state.order_list.copy()
            
            # 최초주문일 기준 정렬
            if "수주처" in df_display.columns and "주문일" in df_display.columns and not df_display.empty:
                min_dates = df_display.groupby("수주처")["주문일"].min().reset_index()
                min_dates.columns = ["수주처", "최초주문일"]
                df_display = pd.merge(df_display, min_dates, on="수주처", how="left")
                df_display = df_display.sort_values(by=["최초주문일", "수주처", "주문일"]).drop(columns=["최초주문일"]).reset_index(drop=True)

            # 열 순서 고정
            df_display = df_display[REQUIRED_COLUMNS]

            def format_shortage(row):
                try:
                    qty = int(float(row['수량']))
                    stk = int(float(row['재고량']))
                    shortage = qty - stk
                    return f"🚨 {shortage} 부족" if shortage > 0 else "0"
                except:
                    return "0"
            
            df_display['부족량'] = df_display.apply(format_shortage, axis=1)

            # --- [편집 가능한 데이터 테이블 (품목을 드롭다운으로 변경)] ---
            edited_df = st.data_editor(
                df_display, 
                column_config={
                    "완료": st.column_config.CheckboxColumn("✅ 완료", default=False),
                    "품목": st.column_config.SelectboxColumn("품목", options=existing_products, required=True), # Selectbox로 변경 적용
                    "수량": st.column_config.NumberColumn("수량", min_value=0, format="%d"),
                    "재고량": st.column_config.NumberColumn("재고량", min_value=0, format="%d"),
                    "특이사항": st.column_config.TextColumn("특이사항"),
                    "부족량": st.column_config.TextColumn("부족량", disabled=True)
                },
                disabled=["주문일", "수주처", "부족량"], 
                use_container_width=True, 
                hide_index=True
            )
            
            # 변경사항이 감지되면 원본 데이터에 반영 후 자동 재계산
            if not edited_df.equals(df_display):
                
                # [스마트 기능] 사용자가 품목을 다른 것으로 수정하면 재고량을 새 품목에 맞게 자동 업데이트
                for idx in edited_df.index:
                    if edited_df.at[idx, '품목'] != df_display.at[idx, '품목']:
                        new_prod = edited_df.at[idx, '품목']
                        new_stock = df_inventory[df_inventory['제품명'] == new_prod]['재고수량'].sum()
                        edited_df.at[idx, '재고량'] = int(new_stock)

                # 숫자형태로 정리
                edited_df['수량'] = pd.to_numeric(edited_df['수량'], errors='coerce').fillna(0).astype(int)
                edited_df['재고량'] = pd.to_numeric(edited_df['재고량'], errors='coerce').fillna(0).astype(int)
                
                # 원본 저장을 위한 부족량 순수 숫자화 재계산
                shortage_calc = edited_df['수량'] - edited_df['재고량']
                edited_df['부족량'] = shortage_calc.apply(lambda x: int(x) if x > 0 else 0)
                
                # 강제 정렬된 상태로 세션 및 시트에 저장
                st.session_state.order_list = edited_df[REQUIRED_COLUMNS]
                save_current_orders(st.session_state.order_list)
                st.rerun()
            
            completed_rows = edited_df[edited_df["완료"] == True]
            
            col_btn1, col_btn2 = st.columns([1.5, 8.5])
            with col_btn1:
                if not completed_rows.empty:
                    if st.button("🗑️ 선택 항목 삭제", type="primary"):
                        st.session_state.order_list = edited_df[edited_df["완료"] == False].reset_index(drop=True)
                        save_current_orders(st.session_state.order_list)
                        st.rerun()
            with col_btn2:
                if st.button("🚨 요약 내역 전체 초기화"):
                    st.session_state.order_list = pd.DataFrame(columns=REQUIRED_COLUMNS)
                    save_current_orders(st.session_state.order_list)
                    st.rerun()
        else: 
            st.caption("위의 양식에서 주문을 추가하시면 구글 시트에 안전하게 쌓입니다.")

    elif menu == "🏢 매출처별 출고 리스트":
        u_cust = sorted([str(c) for c in df_orders['매출처'].unique() if str(c).strip() != 'nan' and str(c).strip() != ''])
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
            st.dataframe(df_c_ord[['출고일자', '매출처', '제품명', '수량']].sort_values(by='출고일자', ascending=False), use_container_width=True, hide_index=True)

    elif menu == "⚠️ 주문 시기 및 재고 부족 위험":
        df_counts = df_orders.groupby(['매출처', '제품명']).size().reset_index(name='order_count')
        df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
        df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
        df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days
        
        cyc = df_o_srt.groupby(['매출처', '제품명']).agg(p_ju=('주기', 'mean'), r_il=('출고일자', 'max'), p_am=('수량', 'mean')).reset_index()
        cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)].copy()
        cyc = cyc[~cyc['제품명'].str.contains('하모닐란|엔커버', na=False)]
        cyc = pd.merge(cyc, df_counts, on=['매출처', '제품명'], how='left')
        
        cyc['expected'] = cyc['r_il'] + pd.to_timedelta(cyc['p_ju'].astype(int), unit='D')
        cyc['days'] = (cyc['expected'] - current_date).dt.days
        cyc = cyc[(cyc['days'] >= -5) & (cyc['days'] <= 10)]

        def get_sort_key(row):
            days = row['days']
            stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
            is_low_stock = stk < row['p_am']
            if days < 0: return (3, days)
            if row['order_count'] > 3 and is_low_stock: return (0, days)
            if is_low_stock: return (1, days)
            return (2, days)
            
        cyc['sort_key'] = cyc.apply(get_sort_key, axis=1)
        cyc = cyc.sort_values('sort_key')
        
        for _, row in cyc.iterrows():
            expected = row['expected']
            days = row['days']
            stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
            
            if days < 0: st.error(f"❌ **[날짜 경과]** {row['매출처']} - {row['제품명']} (예상일: {expected.strftime('%Y-%m-%d')})")
            elif stk < row['p_am']:
                msg = f"**[{'★단골' if row['order_count'] > 3 else '일반'}]** {row['매출처']} - {row['제품명']}\n• 예상일: {expected.strftime('%Y-%m-%d')} ({days}일 남음)\n• 재고: {stk:.0f} < 주문량: {row['p_am']:.0f}"
                if row['order_count'] > 3: st.warning(f"🔥 {msg}")
                else: st.info(f"💡 {msg}")

    elif menu == "🚨 유효기간 임박 경고 (365일 미만)":
        lim_365 = current_date + timedelta(days=365)
        if '유효기간_날짜' in df_inventory.columns:
            s_exp = df_inventory[
                (df_inventory['유효기간_날짜'].notna()) & 
                (df_inventory['유효기간_날짜'] <= lim_365) & 
                (df_inventory['재고수량'] > 0) & 
                (~df_inventory['제품명'].str.contains('하모닐란|엔커버', na=False))
            ].sort_values(by='유효기간_날짜')
            
            if s_exp.empty:
                st.info("✅ 현재 유효기간이 365일 미만으로 임박한 재고 품목이 없습니다.")
            else:
                for _, row in s_exp.iterrows():
                    rem_d = (row['유효기간_날짜'] - current_date).days
                    if rem_d < 180: 
                        st.error(f"💥 **[초긴급 - 180일 미만]** **{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {row['유효기간_표시']} (**{rem_d}일 남음**)")
                    else: 
                        st.warning(f"⚠️ **[주의 - 1년 미만]** **{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {row['유효기간_표시']} ({rem_d}일 남음)")
        else:
            st.error("⚠️ 재고 데이터에서 '유효기간' 정보 열을 찾을 수 없습니다.")

    elif menu == "📦 장기 미출고 재고 (90일 이상)":
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
                    if row['기록없음']: st.info(f"**{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {yuhyo} • 출고 기록 없음")
                    else: st.info(f"**{row['제품명']}** ({row['재고수량']:.0f}개) • 유효기간: {yuhyo} • 최종일: {row['최종일'].strftime('%Y-%m-%d')} (**{int(row['경과일'])}일 경과**)")

    elif menu == "📋 창고 전체 현재 재고 현황":
        p_search = st.text_input("🔍 제품명 검색:", "", key="p_search_t5")
        
        all_prods = sorted(list(set(df_inventory['제품명'].unique()) | set(df_orders['제품명'].unique())))
        all_prods = [p for p in all_prods if str(p).strip() != '']
        
        df_all = pd.DataFrame({'제품명': all_prods})
        df_inv_info = df_inventory[['제품명', '재고수량', '유효기간_표시']].drop_duplicates(subset=['제품명'])
        
        df_f = pd.merge(df_all, df_inv_info, on='제품명', how='left')
        df_f['재고수량'] = df_f['재고수량'].fillna(0)
        df_f['유효기간_표시'] = df_f['유효기간_표시'].fillna('기록없음')
        
        if p_search: 
            df_f = df_f[df_f['제품명'].str.contains(p_search, case=False, na=False)]
            
        df_f.insert(0, "선택", False)
        df_f['선택'] = df_f['제품명'] == st.session_state.get('selected_product')
        edited_df = st.data_editor(df_f, column_config={"선택": st.column_config.CheckboxColumn(required=True)}, use_container_width=True, hide_index=True)
        changed = edited_df[edited_df['선택'] != df_f['선택']]
        
        if not changed.empty:
            new_checked = changed[changed['선택'] == True]
            st.session_state['selected_product'] = new_checked.iloc[0]['제품명'] if not new_checked.empty else None
            
        if st.session_state.get('selected_product'):
            s_prod = st.session_state['selected_product']
            st.markdown(f"### 📊 [{s_prod}] 출고 이력 상세")
            df_p_ord = df_orders[df_orders['제품명'] == s_prod].copy()
            if not df_p_ord.empty:
                df_h = df_p_ord[['매출처', '출고일자', '수량']].copy()
                df_h['출고일자'] = df_h['출고일자'].dt.strftime('%Y-%m-%d')
                st.dataframe(df_h.sort_values(by='출고일자', ascending=False), use_container_width=True, hide_index=True)
            else:
                st.info("출고 이력이 존재하지 않습니다.")

    elif menu == "🏥 의료기기 월별 출고 상세 내역":
        if '제품그룹' not in df_orders.columns:
            st.error("⚠️ 출고데이터에 '제품그룹' 열(Column)을 찾을 수 없습니다.")
        else:
            df_med = df_orders[df_orders['제품그룹'].str.contains('의료기', na=False)].copy()
            if df_med.empty: st.info("의료기 출고 내역이 없습니다.")
            else:
                df_med['출고일자_표시'] = df_med['출고일자'].dt.strftime('%Y-%m-%d')
                df_med['분류월'] = df_med['출고일자'].dt.strftime('%Y년 %m월')
                window_months = sorted([m for m in df_med['분류월'].unique() if str(m) != 'nan'], reverse=True)
                
                if window_months:
                    selected_month = st.selectbox("📅 조회할 년-월을 선택하세요:", window_months, key="medical_month_select")
                    if selected_month:
                        month_data = df_med[df_med['분류월'] == selected_month].sort_values(by='출고일자', ascending=False)
                        display_data = month_data[['출고일자_표시', '매출처', '제품명', '수량']].copy()
                        display_data.columns = ['출고일자', '매출처', '제품명', '수량']
                        st.dataframe(display_data, use_container_width=True, hide_index=True)

else:
    st.error("데이터 파일을 찾을 수 없습니다. 출고데이터.xls 및 재고데이터.xls 파일을 확인해 주세요.")