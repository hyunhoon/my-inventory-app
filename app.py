import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os  # 파일이 창고에 잘 있는지 확인하기 위한 기능

# 웹페이지 기본 설정
st.set_page_config(page_title="의약품 창고 및 주문 분석 시스템", layout="wide")

st.title("📊 의약품 창고 및 주문 통합 분석 시스템")
st.write("깃허브 창고에 저장된 최신 데이터를 자동으로 불러와 분석하는 전광판입니다.")
st.markdown("---")

# 📌 깃허브 창고에 올릴 엑셀 파일 이름
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
            
            # 날짜 형식 정리
            df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')
            df_inventory['유효기간_정리'] = df_inventory['유효기간'].astype(str).str.split('.').str[0]
            df_inventory['유효기간_날짜'] = pd.to_datetime(df_inventory['유효기간_정리'], format='%Y%m%d', errors='coerce')
            
        st.success(f"✅ 분석 완료! (기준일자: {current_date.strftime('%Y-%m-%d')})")
        
        # 3개의 결과를 탭(Tab) 형태로 깔끔하게 분리
        tab1, tab2, tab3 = st.tabs(["⚠️ 주문시기 및 재고부족 알림", "🚨 유효기간 임박 경고", "📦 장기 미출고 재고"])
        
        ### [기능 1] 주문 시기 및 재고 부족 ###
        with tab1:
            st.header("▶️ 주문 시기 도래 및 창고 재고 부족 위험")
            df_orders = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
            df_orders['이전출고일'] = df_orders.groupby(['매출처', '제품명'])['출고일자'].shift(1)
            df_orders['주문간격'] = (df_orders['출고일자'] - df_orders['이전출고일']).dt.days

            cycle_info = df_orders.groupby(['매출처', '제품명']).agg(
                평균주문주기=('주문간격', 'mean'),
                최근출고일=('출고일자', 'max'),
                평균주문량=('수량', 'mean')
            ).reset_index()

            has_order_alert = False
            for idx, row in cycle_info.iterrows():
                if pd.isna(row['평균주문주기']) or row['평균주문주기'] <= 0:
                    continue
                next_order_date = row['최근출고일'] + timedelta(days=int(row['평균주문주기']))
                days_to_order = (next_order_date - current_date).days
                
                if days_to_order <= 7:
                    inv_stock = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                    if inv_stock < row['평균주문량']:
                        has_order_alert = True
                        st.warning(f"**[{row['매출처']}]** {row['제품명']}  \n"
                                   f"• 예상 주문일: {next_order_date.strftime('%Y-%m-%d')} ({days_to_order}일 남음)  \n"
                                   f"• 거래처 평균 주문량: **{row['평균주문량']:.0f}개** | 현재 창고 재고: **{inv_stock:.0f}개**")
            if not has_order_alert:
                st.info("✅ 주문 시기가 다가왔으나 재고가 부족한 품목이 없습니다. 안전합니다.")

        ### [기능 2] 유효기간 10개월 미만 (★ 유효기간 짧은 순서 정렬 반영) ###
        with tab2:
            st.header("▶️ 유효기간 10개월 미만 의약품 목록 (남은 기간이 짧은 순서)")
            limit_10_months = current_date + timedelta(days=30 * 10)
            short_expiry = df_inventory[(df_inventory['유효기간_날짜'] <= limit_10_months) & (df_inventory['재고수량'] > 0)]

            # 💡 [수정된 부분] 유효기간 날짜 기준으로 오름차순 정렬 (유효기간이 가장 임박한 것이 맨 위로 옴)
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
            st.header("▶️ 3개월 이상 장기 미출고 의약품 (악성 재고 위험)")
            df_last_out = df_orders.groupby('제품명')['출고일자'].max().reset_index()
            df_last_out.columns = ['제품명', '최종출고일']

            df_inventory_check = pd.merge(df_inventory, df_last_out, on='제품명', how='left')
            limit_3_months = current_date - timedelta(days=30 * 3)
            has_no_outflow_alert = False

            for idx, row in df_inventory_check.iterrows():
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

    except Exception as e:
        st.error(f"❌ 파일 분석 중 오류가 발생했습니다. 파일 양식과 헤더(컬럼명)를 확인해 주세요. 오류 내용: {e}")
else:
    st.warning("📢 깃허브 창고에 데이터 파일이 없거나 이름이 일치하지 않습니다.")
    st.info(f"💡 현재 창고에 **'{ORDER_FILE}'** 파일과 **'{INVENTORY_FILE}'** 파일이 모두 올라와 있어야 자동으로 화면이 켜집니다.")