import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# 페이지 설정
st.set_page_config(page_title="의약품 통합 분석 시스템", layout="wide")

# 다우오피스 스타일 CSS 적용
st.markdown("""
    <style>
    /* 전체 배경색 및 폰트 */
    .main { background-color: #F8F9FA; }
    
    /* 탭 스타일 변경 */
    div[data-testid="stTabs"] button {
        background-color: #FFFFFF;
        color: #4A5568;
        border-radius: 8px 8px 0 0;
        border: 1px solid #E2E8F0;
        font-weight: 600;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        background-color: #EBF4FF;
        color: #3182CE;
        border-bottom: 2px solid #3182CE;
    }
    
    /* 데이터프레임 및 카드 스타일 */
    .stDataFrame { border: 1px solid #E2E8F0; border-radius: 10px; }
    
    /* 버튼 스타일 (다우오피스 블루) */
    div.stButton > button {
        background-color: #3182CE !important;
        color: white !important;
        border-radius: 6px !important;
        border: none !important;
    }
    
    /* 경고창/안내창 파스텔톤 */
    div.stWarning { background-color: #FEFCBF; border-left: 5px solid #ECC94B; }
    div.stInfo { background-color: #EBF8FF; border-left: 5px solid #63B3ED; }
    div.stError { background-color: #FFF5F5; border-left: 5px solid #F56565; }
    
    h1, h2, h3 { color: #2D3748; }
    </style>
    """, unsafe_allow_html=True)

st.title("📊 의약품 통합 분석 시스템")
st.write("다우오피스 테마가 적용된 데이터 분석 화면입니다.")
st.markdown("---")

ORDER_FILE = "출고데이터.xls"
INVENTORY_FILE = "재고데이터.xls"

def load_data(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)

if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    
    # ... (데이터 로드 및 정제 로직은 기존과 동일하게 유지) ...
    try:
        df_orders = load_data(ORDER_FILE)
        df_inventory = load_data(INVENTORY_FILE)
        
        # 공백 및 문자열 정리
        if '제품명' in df_orders.columns: df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
        if '제품명' in df_inventory.columns: df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
        
        # 날짜 및 숫자 변환
        if '출고일자' in df_orders.columns: df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
        if '재고수량' in df_inventory.columns: df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
        
        # 유효기간 파싱
        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            df_inventory['유효기간_표시'] = df_inventory['유효기간_날짜'].dt.strftime('%Y-%m-%d').fillna(df_inventory['유효기간'].astype(str))
        else:
            df_inventory['유효기간_표시'] = "기록없음"
            
        data_ready = True
    except Exception:
        data_ready = False

    if data_ready:
        t1, t2, t3, t4, t5 = st.tabs(["🏢 매출처별 출고", "⚠️ 주문시기/재고부족", "🚨 유효기간 임박", "📦 장기 미출고", "📋 전체 현재 재고"])
        
        # [탭 5: 수정된 체크박스 방식 + 파스텔 테마]
        with t5:
            st.header("📋 창고 전체 현재 재고 현황")
            df_f = df_inventory[['제품명', '재고수량', '유효기간_표시']].copy()
            df_f.columns = ['제품명', '재고 수량 (개)', '유효기간']
            
            p_search = st.text_input("🔍 품목명 검색", "", key="p_search")
            if p_search: df_f = df_f[df_f['제품명'].str.contains(p_search, case=False, na=False)]
            
            df_f.insert(0, "선택", False)
            edited_df = st.data_editor(df_f, column_config={"선택": st.column_config.CheckboxColumn(required=True)}, use_container_width=True, hide_index=True)
            
            selected_rows = edited_df[edited_df["선택"] == True]
            if not selected_rows.empty:
                target = selected_rows.iloc[0]['제품명']
                st.markdown(f"### 📍 선택 품목: **{target}** 상세 이력")
                df_p = df_orders[df_orders['제품명'] == target].sort_values('출고일자', ascending=False)
                if not df_p.empty:
                    df_p['출고일자'] = df_p['출고일자'].dt.strftime('%Y-%m-%d')
                    st.dataframe(df_p[['출고일자', '매출처', '수량']], use_container_width=True, hide_index=True)
                else:
                    st.warning("출고 기록이 없습니다.")
else:
    st.error("파일을 찾을 수 없습니다.")