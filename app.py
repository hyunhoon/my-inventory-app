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

# --- [구글 시트 연동 설정 - Streamlit Secrets JSON 통째로 읽기 방식] ---
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
        
        if df.empty:
            return pd.DataFrame(columns=["완료", "주문일", "수주처", "품목", "수량", "재고량", "부족량", "특이사항"])
            
        if "완료" in df.columns: 
            df["완료"] = df["완료"].astype(str).str.lower() == 'true'
        return df
    except Exception as e:
        st.error(f"구글 시트 연동 오류: {e}")
        return pd.DataFrame(columns=["완료", "주문일", "수주처", "품목", "수량", "재고량", "부족량", "특이사항"])

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
        주문 등록 시점의 재고량이 고정되어 실시간 변경이 반영되지 않는 것은, 재고/주문 관리 시스템에서 흔히 발생하는 전형적인 구조적 문제입니다. 

이 문제는 주문 내역(Order) 데이터베이스에 '주문 당시의 재고량'과 '부족량'을 **고정된 값으로 저장(Insert)했기 때문에 발생**합니다. 이를 해결하려면 데이터를 저장하는 방식과 조회하는 방식을 완전히 바꾸어야 합니다.

요청하신 대로 **기존 코드를 전부 지우고 바로 붙여넣어 사용할 수 있는 '완성된 전체 코드'를 제공해 드리기 위해**, 먼저 범용적인 해결 원리를 보여드린 후 필요한 추가 정보를 요청드리겠습니다.

---

## 🛠 실시간 재고 반영을 위한 핵심 변경 로직

기존 코드를 삭제한 뒤, 새로 작성할 코드의 핵심 뼈대는 다음과 같아야 합니다.

### 1. 데이터베이스 저장 방식 변경 (고정값 삭제)
주문 테이블에는 오직 **'주문 수량'**만 저장해야 합니다. 재고량과 부족량은 DB에 저장하지 않습니다.

*   **기존 (잘못된 구조):** `주문수량(10)`, `등록시점재고(5)`, `부족량(5)`를 모두 DB에 저장.
*   **변경 (올바른 구조):** `주문수량(10)`만 저장. 재고는 '상품(Product)' 테이블에서 실시간으로 가져옴.

### 2. 데이터 조회(SELECT) 시 실시간 계산 적용
요약 페이지를 불러올 때, 주문 데이터와 상품 데이터(현재 재고)를 결합(JOIN)하여 **부족량을 즉석에서 계산**해 보여줍니다. 

**[실시간 계산 SQL 쿼리 예시]**
```sql
SELECT 
    o.order_id,
    p.product_name,
    o.order_quantity AS "주문수량",
    p.current_stock AS "실시간 재고량",
    -- 주문수량이 재고보다 많으면 그 차이를 부족량으로, 아니면 0으로 계산
    CASE 
        WHEN o.order_quantity > p.current_stock THEN (o.order_quantity - p.current_stock)
        ELSE 0 
    END AS "부족량"
FROM Orders o
JOIN Products p ON o.product_id = p.product_id;