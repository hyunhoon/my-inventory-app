import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os  # 파일이 창고에 잘 있는지 확인하기 위한 기능

# 웹페이지 기본 설정
st.set_page_config(page_title="의약품 창고 및 주문 분석 시스템", layout="wide")

st.title("📊 의약품 창고 및 주문 통합 분석 시스템")
st.write("깃허브 창고에 저장된 최신 데이터를 자동으로 불러와 분석하는 전광판입니다.")
st.markdown("---")

# 📌 [확정] 사장님 요청에 따라 .xls 확장자로 고정 완료했습니다.
ORDER_FILE = "출고데이터.xls"
INVENTORY_FILE = "재고데이터.xls"

# 안전하게 파일 읽는 함수
def load_data(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    else:
        return pd.read_excel(file_path)

# 두 파일이 모두 깃허브 창고에 존재할 때 자동으로 분석 시작
if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    try:
        with st.spinner("🔄 창고에서 최신 데이터를 가져와 정밀 분석 중입니다. 잠시만 기다려 주세요..."):
            df_orders = load_data(ORDER_FILE)
            df_inventory = load_data(INVENTORY_FILE)
            
            current_date = datetime.now()
            
            # 🚨 [긴급 보완] 숫자/문자 혼합으로 인한 정렬 오류('<' not supported) 원천 차단
            # 텍스트가 들어가야 하는 컬럼들은 무조건 '문자열(str)'로 타입을 강제 통일합니다.
            if '매출처' in df_orders.columns:
                df_orders['매출처'] = df_orders['매출처'].astype(str).str.strip()
            if '제품명' in df_orders.columns:
                df_orders['제품명'] = df_orders['제품명'].astype(str).str.strip()
            if '제품명' in df_inventory.columns:
                df_inventory['제품명'] = df_inventory['제품명'].astype(str).str.strip()
                
            # 수량 데이터도 문자가 섞여있을 경우를 대비해 숫자로 강제 변환 (에러는 0으로 대체)
            if '수량' in df_orders.columns:
                df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
            if '재고수량' in df_inventory.columns:
                df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
            
            # 날짜 형식 정리
            df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
            
            # 데이터 빈 행이나 에러 텍스트('nan') 정제
            df_orders = df_orders[(df_orders['제품명'] != '') & (df_orders['제품명'].str.lower() != 'nan')]
            df_orders = df_orders[(df_orders['매출처'] != '') & (df_orders['매출처'].str.lower() != 'nan')]
            df_inventory = df_inventory[(df_inventory['제품명'] != '') & (df_inventory['제품명'].str.lower() != 'nan')]
            
            # 재고 파일에서 완판되어 사라진 품목 자동 추적 및 수량 0으로 복원
            existing_products = df_inventory['제품명'].unique()  # 현재 재고 파일에 있는 품목
            all_handled_products = df_orders['제품명'].unique()  # 전체 출고 이력에 있는 품목
            
            # 출고 이력엔 있으나 현재 재고 파일엔 없는 품목 추출
            missing_products = [p for p in all_handled_products if p not in existing_products]
            
            if missing_products:
                missing_df = pd.DataFrame({
                    '제품명': missing_products,
                    '재고수량': 0,
                    '유효기간': '소진 (기록없음)'
                })
                df_inventory = pd.concat([df_inventory, missing_df], ignore_index=True)
            
            # 유효기간 날짜 정리 프로세스
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            
        st.success(f"✅ 분석 완료! (기준일자: {current_date.strftime('%Y-%m-%d')})")
        
        # 4개의 결과를 탭(Tab) 형태로 분리
        tab1, tab2, tab3, tab4 = st.tabs([
            "⚠️ 주문시기 및 재고부족 알림", 
            "🚨 유효기간 임박 경고", 
            "📦 장기 미출고 재고",
            "📋 전체 현재 재고"
        ])
        
        ### [기능 1] 주문 시기 및 재고 부족 (하모닐란, 엔커버 제외) ###
        with tab1:
            st.header("▶️ 주문 시기 도래 및 창고 재고 부족 위험 (예상주문일 많이 남은 순서)")
            df_orders = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
            df_orders['이전출고일'] = df_orders.groupby(['매출처', '제품명'])['출고일자'].shift(1)
            df_orders['주문간격'] = (df_orders['출고일자'] - df_orders['이전출고일']).dt.days

            cycle_info = df_orders.groupby(['매출처', '제품명']).agg(
                평균주문주기=('주문간격', 'mean'),
                최근출고일=('출고일자', 'max'),
                평균주문량=('수량', 'mean')
            ).reset_index()

            cycle_info = cycle_info[cycle_info['평균주문주기'].notna() & (cycle_info['평균주문주기'] > 0)].copy()
            
            cycle_info['예상주문일'] = cycle_info.apply(lambda row: row['최근출고일'] + timedelta(days=int(row['평균주문주기'])), axis=1)
            cycle_info