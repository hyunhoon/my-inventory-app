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
            
        # 💡 [위치 수정 완료] 여기서부터 안전장치(try) 내부의 줄 맞춤을 완벽하게 통일했습니다.
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
            limit_10_months = current_date + timedelta(days=30 * 10)
            # 재고가 실제로 남아있는 제품(>0) 중에서만 유효기간 경고 작동
            short_expiry = df_inventory[(df_inventory['유효기간_날짜'] <= limit_10_months) & (df_inventory['재고수량'] > 0)]

            short_expiry = short_expiry.sort_values(by='유효기간_날짜', ascending=True)

            if not short_expiry.empty:
                for idx, row in short_expiry.iterrows():
                    remaining_days = (row['유효기간_날짜'] - current_date).days
                    remaining_months = remaining_days // 30
                    st.error(f"**{row['제품명']}** (현재고: {row['재고수량']:.0f}개)  \n"
                             f"• 유효기간: {row['유효기간_날짜'].strftime('%Y-%m-%d')} (약 {remaining_months}개월, {remaining_days}일 남음)")
            else:
                st.info("✅ 유효기간이 10개월 미만인 품목이 없습니다. 안전합니다.")

        ### [기능 3] 3개월 이상 미출고 ###
        with tab3:
            st.header("▶️ 3개월 이상 장기 미출고 의약품 (최종 출고일이 오래된 순서)")
            df_last_out = df_orders.groupby('제품명')['출고일자'].max().reset_index()
            df_last_out.columns = ['제품명', '최종출고일']

            df_inventory_check = pd.merge(df_inventory, df_last_out, on='제품명', how='left')
            df_inventory_check = df_inventory_check.sort_values(by='최종출고일', ascending=True, na_position='first')
            
            limit_3_months = current_date - timedelta(days=30 * 3)
            has_no_outflow_alert = False

            for idx, row in df_inventory_check.iterrows():
                # 재고가 이미 0인 완판 품목은 장기 미출고(악성 재고) 경고에서 제외
                if row['재고수량'] <= 0:
                    continue
                if pd.isna(row['최종출고일']):
                    has_no_outflow_alert = True
                    st.info(f"**{row['제품명']}** (현재고: {row['재고수량']:.0f}개)  \n"
                            f"• ⚠️ 경고: 최근 출고 리스트에 나간 기록이 전혀 없는 재고입니다.")
                elif row['최종출고일'] <= limit_3_months:
                    has_no_outflow_alert = True
                    no_outflow_days = (current_date - row['최종출고일']).days
                    st.info(f"**{row['제품명']}** (현재고: {row['재고수량']:.0f}개)  \n"
                            f"• 최종 출고일: {row['최종출고일'].strftime('%Y-%m-%d')} ({no_outflow_days}일 동안 출고 없음)")

            if not has_no_outflow_alert:
                st.info("✅ 3개월 이상 창고에 묶여 있는 장기 체화 재고가 없습니다.")

        ### [기능 4] 전체 현재 재고 및 실시간 검색 기능 ###
        with tab4:
            st.header("▶️ 창고 전체 현재 재고 현황")
            st.write("현재 창고에 등록된 모든 의약품 리스트입니다. 제품명을 입력하면 실시간으로 필터링됩니다.")
            
            search_term = st.text_input("🔍 의약품 검색 (찾으시는 제품명을 입력하세요)", "")
            
            df_all_inv = df_inventory.copy()
            df_all_inv['유효기간_표시'] = df_all_inv['유효기간_날짜'].dt.strftime('%Y-%m-%d')
            # 날짜 기록이 없는 '재고 소진' 품목은 글자 그대로 표기
            df_all_inv['유효기간_표시'] = df_all_inv['유효기간_표시'].fillna(df_all_inv['유효기간'].astype(str))
            
            df_inv_filtered = df_all_inv[['제품명', '재고수량', '유효기간_표시']].copy()
            df_inv_filtered.columns = ['제품명', '재고 수량 (개)', '유효기간']
            
            if search_term:
                df_inv_filtered = df_inv_filtered[df_inv_filtered['제품명'].str.contains(search_term, case=False, na=False)]
            
            st.markdown(f"📊 **현재 조회된 품목 (재고 0 포함):** 총 `{len(df_inv_filtered)}`건")
            st.dataframe(df_inv_filtered, use_container_width=True, hide_index=True)

    except Exception as e:
        st.error(f"❌ 파일 분석 중 오류가 발생했습니다. 파일 양식과 헤더(컬럼명)를 확인해 주세요. 오류 내용: {e}")
else:
    st.warning("📢 깃허브 창고에 데이터 파일이 없거나 이름이 일치하지 않습니다.")
    st.info(f"💡 현재 창고에 **'{ORDER_FILE}'** 파일과 **'{INVENTORY_FILE}'** 파일이 모두 올라와 있어야 자동으로 화면이 켜집니다.")