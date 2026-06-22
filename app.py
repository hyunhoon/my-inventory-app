import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# 웹페이지 기본 설정
st.set_page_config(page_title="의약품 창고 및 주문 분석 시스템", layout="wide")

st.title("📊 의약품 창고 및 주문 통합 분석 시스템")
st.write("깃허브 창고에 저장된 최신 데이터를 자동으로 불러와 분석하는 전광판입니다.")
st.markdown("---")

# 📌 사장님 요청에 따라 .xls 확장자 완벽 고정
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
    data_loaded = False
    current_date = datetime.now()
    
    # 💡 [구조 개편] 에러 위험이 있는 순수 데이터 정제 프로세스만 딱 묶어서 처리합니다.
    try:
        with st.spinner("🔄 창고에서 최신 데이터를 가져와 정밀 분석 중입니다. 잠시만 기다려 주세요..."):
            df_orders = load_data(ORDER_FILE)
            df_inventory = load_data(INVENTORY_FILE)
            
            # 텍스트 열은 무조건 '문자열(str)'로 강제 통일하여 형식 불일치 정렬 오류 차단
            if '매출처' in df_orders.columns:
                df_orders['매출처'] = df_orders['매출처'].astype(str).str.strip()
            if '제품명' in df_orders.columns:
                df_orders['제품명'] = df_orders['제품명'].astype(str).str.strip()
            if '제품명' in df_inventory.columns:
                df_inventory['제품명'] = df_inventory['제품명'].astype(str).str.strip()
                
            # 수량 데이터 숫자로 완벽 변환 (공백이나 에러 문자는 0으로 대체)
            if '수량' in df_orders.columns:
                df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
            if '재고수량' in df_inventory.columns:
                df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
            
            # 날짜 형식 정리
            df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
            
            # 데이터 빈 행이나 에러 텍스트 행 원천 청소
            df_orders = df_orders[(df_orders['제품명'] != '') & (df_orders['제품명'].str.lower() != 'nan')]
            if '매출처' in df_orders.columns:
                df_orders = df_orders[(df_orders['매출처'] != '') & (df_orders['매출처'].str.lower() != 'nan')]
            df_inventory = df_inventory[(df_inventory['제품명'] != '') & (df_inventory['제품명'].str.lower() != 'nan')]
            
            # 재고 파일에서 완판되어 사라진 품목 자동 추적 및 수량 0으로 리스트 복원
            existing_products = df_inventory['제품명'].unique()
            all_handled_products = df_orders['제품명'].unique()
            missing_products = [p for p in all_handled_products if p not in existing_products]
            
            if missing_products:
                missing_df = pd.DataFrame({
                    '제품명': missing_products,
                    '재고수량': 0.0,
                    '유효기간': '소진 (기록없음)'
                })
                df_inventory = pd.concat([df_inventory, missing_df], ignore_index=True)
            
            # 유효기간 날짜 파싱 프로세스
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            
        data_loaded = True  # 데이터 준비 성공 완료 신호
        
    except Exception as e:
        st.error(f"❌ 파일 분석 중 오류가 발생했습니다. 파일 양식과 헤더(컬럼명)를 확인해 주세요. 오류 내용: {e}")

    # 💡 [안전 구역] try문 밖에 독립 배치하여 들여쓰기 문법 에러(SyntaxError)를 근본적으로 차단합니다.
    if data_loaded:
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
            if not df_orders.empty and '매출처' in df_orders.columns and '제품명' in df_orders.columns and '출고일자' in df_orders.columns:
                df_orders_sorted = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
                df_orders_sorted['이전출고일'] = df_orders_sorted.groupby(['매출처', '제품명'])['출고일자'].shift(1)
                df_orders_sorted['주문간격'] = (df_orders_sorted['출고일자'] - df_orders_sorted['이전출고일']).dt.days

                cycle_info = df_orders_sorted.groupby(['매출처', '제품명']).agg(
                    평균주문주기=('주문간격', 'mean'),
                    최근출고일=('출고일자', 'max'),
                    평균주문량=('수량', 'mean')
                ).reset_index()

                cycle_info = cycle_info[cycle_info['평균주문주기'].notna() & (cycle_info['평균주문주기'] > 0)].copy()
                
                if not cycle_info.empty:
                    cycle_info['예상주문일'] = cycle_info.apply(lambda row: row['최근출고일'] + timedelta(days=int(row['평균주문주기'])), axis=1)
                    cycle_info['남은일수'] = (cycle_info['예상주문일'] - current_date).dt.days

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
                else:
                    st.info("✅ 분석할 수 있는 주기적인 주문 패턴이 없습니다.")
            else:
                st.info("✅