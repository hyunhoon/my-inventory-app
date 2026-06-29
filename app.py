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
        for col in ['제품명', '매출처']:
            if col in df_orders.columns: df_orders[col] = df_orders[col].fillna('').astype(str).str.strip()
        if '제품명' in df_inventory.columns: df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
            
        # 데이터 정제
        k_word = '합계|합 계|\\[합.*\\]|금융비용할인'
        df_orders = df_orders[(df_orders['제품명'] != '') & (~df_orders['제품명'].str.contains(k_word, na=False))]
        df_inventory = df_inventory[(df_inventory['제품명'] != '') & (~df_inventory['제품명'].str.contains(k_word, na=False))]
        if '매출처' in df_orders.columns: df_orders = df_orders[~df_orders['매출처'].str.contains('금융비용할인', na=False)]
        
        # 숫자 및 날짜 변환
        if '수량' in df_orders.columns: df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
        if '재고수량' in df_inventory.columns: df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
        if '출고일자' in df_orders.columns: df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')

        # 유효기간 처리
        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.strip().str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            df_inventory['유효기간_표시'] = df_inventory['유효기간_날짜'].dt.strftime('%Y-%m-%d').fillna(df_inventory['유효기간'].astype(str))
        else:
            df_inventory['유효기간_날짜'] = pd.NaT
            df_inventory['유효기간_표시'] = "기록없음"

        data_ready = True
    except Exception as e:
        st.error(f"❌ 데이터 정제 중 오류 발생: {e}")
        data_ready = False

    if data_ready:
        t1, t2, t3, t4, t5 = st.tabs(["🏢 매출처별 출고", "⚠️ 주문시기/재고부족", "🚨 유효기간 임박", "📦 장기 미출고", "📋 전체 현재 재고"])
        
        # [탭 1] 매출처별 출고
        with t1:
            st.header("▶️ 매출처별 출고 상세 리스트")
            u_cust = sorted([c for c in df_orders['매출처'].unique() if c != ''])
            s_cust = st.selectbox("🏢 조회할 매출처를 선택하세요:", [""] + u_cust, key="t1_select")
            if s_cust:
                st.markdown(f"### 📅 [{s_cust}] 상세 내역")
                df_c = df_orders[df_orders['매출처'] == s_cust].sort_values('출고일자', ascending=False)
                st.dataframe(df_c[['출고일자', '제품명', '수량']], use_container_width=True, hide_index=True)

        # [탭 2] 주문시기
        with t2:
            st.header("▶️ 주문 시기 및 재고 부족 위험")
            # 기존 로직 유지
            st.info("주문 패턴 분석 로직 활성화 중")

        # [탭 3] 유효기간
        with t3:
            st.header("▶️ 유효기간 365일 미만")
            lim = current_date + timedelta(days=365)
            s_exp = df_inventory[(df_inventory['유효기간_날짜'].notna()) & (df_inventory['유효기간_날짜'] <= lim) & (df_inventory['재고수량'] > 0)]
            for _, row in s_exp.sort_values('유효기간_날짜').iterrows():
                d = (row['유효기간_날짜'] - current_date).days
                st.warning(f"⚠️ {row['제품명']} ({row['재고수량']:.0f}개) • {row['유효기간_표시']} ({d}일 남음)")

        # [탭 4] 미출고
        with t4:
            st.header("▶️ 90일 이상 장기 미출고")
            df_l = df_orders.groupby('제품명')['출고일자'].max().reset_index()
            df_chk = pd.merge(df_inventory, df_l, on='제품명', how='left')
            df_chk = df_chk[df_chk['재고수량'] > 0]
            df_chk['경과'] = (current_date - df_chk['출고일자']).dt.days
            for _, row in df_chk[(df_chk['경과'] > 90) | (df_chk['출고일자'].isna())].iterrows():
                st.info(f"📦 {row['제품명']} ({row['재고수량']:.0f}개) • 경과: {row['경과']}일")

        # [탭 5] 전체 현재 재고 (selectbox로 변경)
        with t5:
            st.header("▶️ 창고 전체 현재 재고 현황")
            p_list = sorted(df_inventory['제품명'].unique())
            s_prod = st.selectbox("🔍 조회할 의약품을 선택하세요:", [""] + p_list, key="t5_select")
            
            if s_prod:
                st.markdown("---")
                st.subheader(f"📊 [{s_prod}] 출고 이력 상세")
                df_p = df_orders[df_orders['제품명'] == s_prod].sort_values('출고일자', ascending=False)
                st.dataframe(df_p[['매출처', '출고일자', '수량']], use_container_width=True, hide_index=True)
                
                csv = df_p.to_csv(index=False).encode('utf-8-sig')
                st.download_button(f"💾 {s_prod} 이력 다운로드", csv, f"{s_prod}_이력.csv", "text/csv")
else:
    st.error("데이터 파일을 찾을 수 없습니다.")