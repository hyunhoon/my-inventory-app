import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

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
        df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
        df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
        df_orders['매출처'] = df_orders['매출처'].fillna('').astype(str).str.strip()
        
        # 데이터 정제
        k_word = '합계|합 계|\\[합.*\\]|금융비용할인'
        df_orders = df_orders[(df_orders['제품명'] != '') & (~df_orders['제품명'].str.contains(k_word, na=False))]
        df_inventory = df_inventory[(df_inventory['제품명'] != '') & (~df_inventory['제품명'].str.contains(k_word, na=False))]
        df_orders = df_orders[~df_orders['매출처'].str.contains('금융비용할인', na=False)]
        
        df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
        df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
        df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')

        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            df_inventory['유효기간_표시'] = df_inventory['유효기간_날짜'].dt.strftime('%Y-%m-%d').fillna(df_inventory['유효기간'].astype(str))
        else:
            df_inventory['유효기간_표시'] = "기록없음"

        data_ready = True
    except Exception as e:
        st.error(f"❌ 데이터 정제 오류: {e}")
        data_ready = False

    if data_ready:
        t1, t2, t3, t4, t5 = st.tabs(["🏢 매출처별 출고", "⚠️ 주문시기/재고부족", "🚨 유효기간 임박", "📦 장기 미출고", "📋 전체 현재 재고"])
        
        with t1:
            st.header("▶️ 매출처별 출고 상세 리스트")
            u_cust = sorted([c for c in df_orders['매출처'].unique() if c != ''])
            df_cust = pd.DataFrame(u_cust, columns=['매출처'])
            c_search = st.text_input("🔍 매출처 검색:", "", key="c_search_t1")
            if c_search: df_cust = df_cust[df_cust['매출처'].str.contains(c_search, case=False, na=False)]
            
            df_cust.insert(0, "선택", False)
            edited_df1 = st.data_editor(
                df_cust, 
                column_config={"선택": st.column_config.CheckboxColumn(required=True, width=50)}, 
                use_container_width=True, hide_index=True
            )
            
            sel1 = edited_df1[edited_df1["선택"] == True]
            if not sel1.empty:
                s_cust = sel1.iloc[0]['매출처']
                st.markdown(f"### 📅 [{s_cust}] 상세 내역")
                df_c = df_orders[df_orders['매출처'] == s_cust].sort_values('출고일자', ascending=False)
                st.dataframe(df_c[['출고일자', '제품명', '수량']], use_container_width=True, hide_index=True)

        with t2:
            st.write("주문시기 및 재고부족 로직입니다.") # 생략된 부분은 기존 로직대로 유지

        with t3:
            st.write("유효기간 로직입니다.")

        with t4:
            st.write("장기 미출고 로직입니다.")

        with t5:
            st.header("▶️ 창고 전체 현재 재고 현황")
            df_f = df_inventory[['제품명', '재고수량', '유효기간_표시']].copy()
            df_f.columns = ['제품명', '재고 수량 (개)', '유효기간']
            df_f = df_f.sort_values(by='제품명').reset_index(drop=True)
            
            p_search = st.text_input("🔍 품목명 검색:", "", key="p_search_t5")
            if p_search: df_f = df_f[df_f['제품명'].str.contains(p_search, case=False, na=False)]
            
            df_f.insert(0, "선택", False)
            edited_df5 = st.data_editor(
                df_f, 
                column_config={"선택": st.column_config.CheckboxColumn(required=True, width=50)}, 
                use_container_width=True, hide_index=True
            )
            
            sel5 = edited_df5[edited_df5["선택"] == True]
            if not sel5.empty:
                target = sel5.iloc[0]['제품명']
                st.markdown(f"### 📊 [{target}] 거래처별 출고 이력")
                df_p = df_orders[df_orders['제품명'] == target].sort_values('출고일자', ascending=False)
                st.dataframe(df_p[['매출처', '출고일자', '수량']], use_container_width=True, hide_index=True)
else:
    st.error("데이터 파일을 찾을 수 없습니다.")