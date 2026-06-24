import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# 1. 웹페이지 기본 설정
st.set_page_config(
    page_title="의약품 분석 시스템", 
    layout="wide"
)

st.title("📊 의약품 창고 및 주문 통합 분석 시스템")
st.write("깃허브 창고의 데이터를 자동으로 불러와 분석하는 전광판입니다.")
st.markdown("---")

# 파일 설정
ORDER_FILE = "출고데이터.xls"
INVENTORY_FILE = "재고데이터.xls"

def load_data(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    else:
        return pd.read_excel(file_path)

# 두 파일이 존재할 때 실행
if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    
    try:
        df_orders = load_data(ORDER_FILE)
        df_inventory = load_data(INVENTORY_FILE)
        
        # 텍스트 컬럼 문자열 변환 및 공백 제거
        for df in [df_orders, df_inventory]:
            if '제품명' in df.columns:
                df['제품명'] = df['제품명'].fillna('').astype(str).str.strip()
        
        if '매출처' in df_orders.columns:
            df_orders['매출처'] = df_orders['매출처'].fillna('').astype(str).str.strip()
            
        # 원본 파일의 [합 계] 데이터 제외 처리
        filter_keywords = '합계|합 계|\\[합.*\\]'
        df_orders = df_orders[
            (df_orders['제품명'] != '') & 
            (~df_orders['제품명'].str.contains(filter_keywords, na=False))
        ]
        df_inventory = df_inventory[
            (df_inventory['제품명'] != '') & 
            (~df_inventory['제품명'].str.contains(filter_keywords, na=False))
        ]
        
        # 수량 데이터 숫자 변환
        if '수량' in df_orders.columns:
            df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
        if '재고수량' in df_inventory.columns:
            df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
            
        # 출고일자 날짜형 변환
        if '출고일자' in df_orders.columns:
            df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')

        # 재고 소진 품목 처리
        existing_products = df_inventory['제품명'].unique()
        all_handled_products = df_orders['제품명'].unique()
        missing_products = [
            p for p in all_handled_products 
            if p not in existing_products and p != ''
        ]
        
        if missing_products:
            missing_df = pd.DataFrame({
                '제품명': missing_products,
                '재고수량': 0.0,
                '유효기간': '소진 (기록없음)'
            })
            df_inventory = pd.concat([df_inventory, missing_df], ignore_index=True)

        # 유효기간 날짜 파싱
        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_정리'] = (
                df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
            )
            df_inventory['유효기간_날짜'] = pd.to_datetime(
                df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce'
            )
        else:
            df_inventory['유효기간_날짜'] = pd.NaT

        data_ready = True
    except Exception as e:
        st.error(f"❌ 데이터 정제 중 오류 발생: {e}")
        data_ready = False

    # 2. UI 렌더링
    if data_ready:
        st.success(f"✅ 분석 완료! (기준일자: {current_date.strftime('%Y-%m-%d')})")
        
        # 탭 레이아웃 생성
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🏢 매출처별 출고 리스트",
            "⚠️ 주문시기 및 재고부족 알림", 
            "🚨 유효기간 임박 경고", 
            "📦 장기 미출고 재고",
            "📋 전체 현재 재고"
        ])
        
        # --- [탭 1] 매출처별 출고 리스트 ---
        with tab1:
            st.header("▶️ 매출처별 출고 상세 리스트")
            
            if not df_orders.empty and '매출처' in df_orders.columns:
                unique_customers = sorted([c for c in df_orders['매출처'].unique() if c != ''])
                
                # 입력창 및 검색 기능
                cust_search = st.text_input("🔍 매출처 검색:", "", key="cust_search_input")
                
                if cust_search:
                    filtered_customers = [c for c in unique_customers if cust_search.lower() in c.lower()]
                else:
                    filtered_customers = unique_customers
                
                if filtered_customers:
                    selected_customer = st.selectbox(
                        "🏢 조회할 매출처 선택:",
                        filtered_customers,
                        key="cust_selectbox"
                    )
                    
                    st.markdown("---")
                    st.markdown(f"### 📅 **{selected_customer}**의 날짜별 상세 출고 내역")
                    
                    df_cust_orders = df_orders[df_orders['매출처'] == selected_customer].copy()
                    
                    if not df_cust_orders.empty and '출고일자' in df_cust_orders.columns:
                        df_cust_history = df_cust_orders[['출고일자', '제품명', '수량']].copy()
                        df_cust_history['출고날짜'] = (
                            df_cust_history['출고일자'].dt.strftime('%Y-%m-%d').fillna("날짜 없음")
                        )
                        
                        df_cust_display = df_cust_history[['출고날짜', '제품명', '수량']].copy()
                        df_cust_display.columns = ['출고날짜', '의약품명', '출고수량 (개)']
                        df_cust_display = df_cust_display.sort_values(by='출고날짜', ascending=False)
                        
                        st.dataframe(df_cust_display, use_container_width=True