import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os  # 파일이 창고에 잘 있는지 확인하기 위한 기능

# 웹페이지 기본 설정
st.set_page_config(page_title="의약품 창고 및 주문 분석 시스템", layout="wide")

st.title("📊 의약품 창고 및 주문 통합 분석 시스템")
st.write("깃허브 창고에 저장된 최신 데이터를 자동으로 불러와 분석하는 전광판입니다.")
st.markdown("---")

# 📌 엑셀 파일 이름 (.xlsx 확장자 적용)
ORDER_FILE = "출고데이터.xlsx"
INVENTORY_FILE = "재고데이터.xlsx"

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
            
            # 날짜 형식 정리 및 텍스트 공백 제거
            df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
            df_orders['제품명'] = df_orders['제품명'].astype(str).str.strip()
            df_inventory['제품명'] = df_inventory['제품명'].astype(str).str.strip()
            
            # 데이터 빈 행이나 에러 텍스트 정제
            df_orders = df_orders[df_orders['제품명'] != '']
            df_orders = df_orders[df_orders['제품명'].str.lower() != 'nan']
            df_inventory = df_inventory[df_inventory['제품명'] != '']
            df_inventory = df_inventory[df_inventory['제품명'].str.lower() != 'nan']
            
            # 재고 파일에서 완판되어 사라진 품목 자동 추적 및 수량 0으로 복원
            existing_products = df_inventory['제품명'].unique()  # 현재 재고 파일에 있는 품목
            all_handled_products = df_orders['제품명'].unique()  # 전체 출고 이력에 있는 품목
            
            # 출고 이력엔 있으나 현재 재고 파일엔 없는 품목(=재고가 0이 되어 사라진 품목) 추출
            missing_products = [p for p in all_handled_products if p not in existing_products]
            
            if missing_products:
                missing_df = pd.DataFrame({
                    '제품명': missing_products,
                    '재고수량': 0,
                    '유효기간': '소진 (기록없음)'
                })
                # 기존 재고 리스트 아래에 재고 0짜리 품목들을 강제로 결합
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
        
        ### [기능 1] 주문 시기 및 재고 부족 (많이 남은 순 정렬 & 하모닐란, 엔커버 제외) ###
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
            cycle_info['남은일수'] = (cycle_info['예상주문일'] - current_date).dt.days

            # 7일 이내 항목 중 '하모닐란'과 '엔커버' 문구가 포함된 제품은 제외
            alert_info = cycle_info[
                (cycle_info['남은일수'] <= 7) & 
                (~cycle_info['제품명'].str.contains('하모닐란|엔커버', na=False))
            ].copy()
            
            alert_info = alert_info.sort_values(by='남은일수', ascending=False)

            has_order_alert = False
            for idx, row in alert_info.iterrows():
                inv_stock = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                
                if inv_stock < row['평균주문량']:
                    has_order_alert = True
                    st.warning(f"**[{row['매출처']}]** {row['제품명']}  \n"
                               f"• 예상 주문일: {row['예상주문일'].strftime('%Y-%m-%d')} (**{row['남은일수']}일 남음**)  \n"
                               f"• 거래처 평균 주문량: **{row['평균주문량']:.0f}개** | 현재 창고 재고: **{inv_stock:.0f}개**")
                               
            if not has_order_alert:
                st.info("✅ 주문 시기가 다가왔으나 재고가 부족한 품목이 없습니다. 안전합니다.")

        ### [기능 2] 유효기간 10개월 미만 ###
        with tab2:
            st.header("▶️ 유효기간 10개월 미만 의약품 목록 (남은 기간이 짧은 순서)")