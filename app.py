import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# 웹페이지 기본 설정
st.set_page_config(
    page_title="의약품 창고 및 주문 분석 시스템", 
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

# 두 파일이 모두 존재할 때 실행
if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    
    # 1. 데이터 불러오기 및 정제
    try:
        df_orders = load_data(ORDER_FILE)
        df_inventory = load_data(INVENTORY_FILE)
        
        # 텍스트 컬럼 문자열 변환 및 공백 제거
        for df in [df_orders, df_inventory]:
            if '제품명' in df.columns:
                df['제품명'] = (
                    df['제품명'].fillna('').astype(str).str.strip()
                )
        
        if '매출처' in df_orders.columns:
            df_orders['매출처'] = (
                df_orders['매출처'].fillna('').astype(str).str.strip()
            )
            
        # 빈 행 및 원본 파일의 [합 계] 데이터 완벽 제외 처리
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
            df_orders['수량'] = (
                pd.to_numeric(df_orders['수량'], errors='coerce')
                .fillna(0)
            )
        if '재고수량' in df_inventory.columns:
            df_inventory['재고수량'] = (
                pd.to_numeric(df_inventory['재고수량'], errors='coerce')
                .fillna(0)
            )
            
        # 출고일자 날짜형 변환
        if '출고일자' in df_orders.columns:
            df_orders['출고일자'] = (
                pd.to_datetime(df_orders['출고일자'], errors='coerce')
            )

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
            df_inventory = pd.concat(
                [df_inventory, missing_df], 
                ignore_index=True
            )

        # 유효기간 날짜 파싱
        if '유효기간' in df_inventory.columns:
            df_inventory['유효기간_정리'] = (
                df_inventory['유효기간']
                .astype(str).str.strip().str.split('.').str[0]
            )
            df_inventory['유효기간_날짜'] = pd.to_datetime(
                df_inventory['유효기간_정리'], 
                format='%Y%m%d', 
                errors='coerce'
            )
        else:
            df_inventory['유효기간_날짜'] = pd.NaT

        data_ready = True
    except Exception as e:
        st.error(f"❌ 데이터 정제 중 오류 발생: {e}")
        data_ready = False

    # 2. UI 렌더링 영역
    if data_ready:
        st.success(
            f"✅ 분석 완료! (기준일자: {current_date.strftime('%Y-%m-%d')})"
        )
        
        # 탭 레이아웃 생성
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🏢 매출처별 출고 리스트",
            "⚠️ 주문시기 및 재고부족 알림", 
            "🚨 유효기간 임박 경고", 
            "📦 장기 미출고 재고",
            "📋 전체 현재 재고"
        ])
        
        # --- [탭 1] 매출처별 출고 리스트 (버전 크래시 방지 보완) ---
        with tab1:
            st.header("▶️ 매출처별 출고 상세 리스트")
            
            if not df_orders.empty and '매출처' in df_orders.columns:
                # 가나다 순으로 정렬된 전체 매출처 목록 추출
                unique_customers = sorted(
                    [c for c in df_orders['매출처'].unique() if c != '']
                )
                
                # 1. 매출처 검색 기능
                cust_search = st.text_input(
                    "🔍 매출처 검색 (찾으시는 거래처명의 일부를 입력하세요)", 
                    "", key="cust_search_input"
                )
                
                # 검색어에 맞게 리스트 필터링
                if cust_search:
                    filtered_customers = [
                        c for c in unique_customers 
                        if cust_search.lower() in c.lower()
                    ]
                else:
                    filtered_customers = unique_customers
                
                # 2. 안전한 드롭다운 선택 상자 제공
                if filtered_customers:
                    selected_customer = st.selectbox(
                        f"🏢 조회할 매출처를 선택하세요 (검색된 매출처: {len(filtered_customers)}곳)",
                        filtered_customers,
                        key="cust_selectbox"
                    )
                    
                    st.markdown("---")
                    st.markdown(f"### 📅 **{selected_customer}**의 날짜별 상세 출고 내역")
                    
                    # 선택된 매출처 데이터 추출
                    df_cust_orders = df_orders[
                        df_orders['매출처'] == selected_customer
                    ].copy()
                    
                    if (not df_cust_orders.empty and 
                        '출고일자' in df_cust_orders.columns):
                        
                        df_cust_history = df_cust_orders[
                            ['출고일자', '제품명', '수량']
                        ].copy()
                        
                        df_cust_history['출고날짜'] = (
                            df_cust_history['출고일자']
                            .dt.strftime('%Y-%m-%d')
                            .fillna("날짜 없음")
                        )
                        
                        df_cust_display = df_cust_history[
                            ['출고날짜', '제품명', '수량']
                        ].copy()
                        
                        df_cust_display.columns = [
                            '출고날짜', '의약품명', '출고수량 (개)'
                        ]
                        
                        # 날짜 최신순 정렬
                        df_cust_display = df_cust_display.sort_values(
                            by='출고날짜', ascending=False
                        )
                        
                        st.dataframe(
                            df_cust_display,
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.info("✨ 해당 매출처로 출고된 기록이 없습니다.")
                else:
                    st.warning("🔍 검색 결과와 일치하는 매출처가 없습니다.")
            else:
                st.info("✅ 분석할 매출처 출고 데이터가 없습니다.")

        # --- [탭 2] 주문 시기 및 재고 부족 ---
        with tab2:
            st.header("▶️ 주문 시기 도래 및 창고 재고 부족 위험")
            if (not df_orders.empty and 
                '매출처' in df_orders.columns and 
                '출고일자' in df_orders.columns):
                
                df_orders_sorted = df_orders.sort_values(
                    by=['매출처', '제품명', '출고일자']
                )
                df_orders_sorted['이전출고일'] = (
                    df_orders_sorted.groupby(['매출처', '제품명'])['출고일자']
                    .shift(1)
                )
                df_orders_sorted['주문간격'] = (
                    (df_orders_sorted['출고일자'] - 
                     df_orders_sorted['이전출고일']).dt.days
                )

                cycle_info = df_orders_sorted.groupby(['매출처', '제품명']).agg(
                    평균주문주기=('주문간격', 'mean'),
                    최근출고일=('출고일자', 'max'),
                    평균주문량=('수량', 'mean')
                ).reset_index()

                cycle_info = cycle_info[
                    cycle_info['평균주문주기'].notna() & 
                    (cycle_info['평균주문주기'] > 0)
                ].copy()
                
                if not cycle_info.empty:
                    cycle_info['예상주문일'] = cycle_info.apply(
                        lambda r: r['최근출고일'] + 
                        timedelta(days=int(r['평균주문주기'])), 
                        axis=1
                    )
                    cycle_info['남은일수'] = (
                        (cycle_info['예상주문일'] - current_date).dt.days
                    )

                    alert_info = cycle_info[
                        (cycle_info['남은일수'] <= 7) & 
                        (~cycle_info['제품명'].str.contains(
                            '하모닐란|엔커버', na=False
                        ))
                    ].copy()
                    
                    alert_info = alert_info.sort_values(
                        by='남은일수', ascending=False
                    )

                    has_order_alert = False
                    for idx, row in alert_info.iterrows():
                        inv_stock = df_inventory[
                            df_inventory['제품명'] == row['제품명']
                        ]['재고수량'].sum()
                        
                        if inv_stock < row['평균주문량']:
                            has_order_alert = True
                            st.warning(
                                f"**[{row['매출처']}]** {row['제품명']}\n"
                                f"• 예상 주문일: {row['예상주문일'].strftime('%Y-%m-%d')} "
                                f"(**{row['남은일수']}일 남음**)\n"
                                f"• 거래처 평균 주문량: **{row['평균주문량']:.0f}개** "
                                f"| 현재 창고 재고: **{inv_stock:.0f}개**"
                            )
                                       
                    if not has_order_alert:
                        st.info("✅ 주문 위험 품목이 없습니다. 안전합니다.")
                else:
                    st.info("✅ 분석할 수 있는 주기적인 주문 패턴이 없습니다.")
            else:
                st.info("✅ 출고 데이터가 부족하여 주문 시기를 계산할 수 없습니다.")

        # --- [탭 3] 유효기간 10개월 미만 ---
        with tab3:
            st.header("▶️ 유효기간 10개월 미만 의약품 목록")
            limit_10_months = current_date + timedelta(days=30 * 10)
            if '유효기간_날짜' in df_inventory.columns:
                short_expiry = df_inventory[
                    df_inventory['유효기간_날짜'].notna() & 
                    (df_inventory['유효기간_날짜'] <= limit_10_months) & 
                    (df_inventory['재고수량'] > 0)
                ]
                if not short_expiry.empty:
                    short_expiry = short_expiry.sort_values(
                        by='유효기간_날짜', ascending=True
                    )
                    for idx, row in short_expiry.iterrows():
                        remaining_days = (row['유효기간_날짜'] - current_date).days
                        remaining_months = remaining_days // 30
                        st.error(
                            f"**{row['제품명']}** (현재고: {row['재고수량']:.0f}개)\n"
                            f"• 유효기간: {row['유효기간_날짜'].strftime('%Y-%m-%d')} "
                            f"(약 {remaining_months}개월, {remaining_days}일 남음)"
                        )
                else:
                    st.info("✅ 유효기간 10개월 미만 품목이 없습니다.")

        # --- [탭 4] 3개월 이상 미출고 ---
        with tab4:
            st.header("▶️ 3개월 이상 장기 미출고 의약품")
            if not df_orders.empty and '출고일자' in df_orders.columns:
                df_last_out = (
                    df_orders.groupby('제품명')['출고일자'].max().reset_index()
                )
                df_last_out.columns = ['제품명', '최종출고일']

                df_inventory_check = pd.merge(
                    df_inventory, df_last_out, on='제품명', how='left'
                )
                df_inventory_check = df_inventory_check.sort_values(
                    by='최종출고일', ascending=True, na_position='first'
                )
                
                limit_3_months = current_date - timedelta(days=30 * 3)
                has_no_outflow_alert = False

                for idx, row in df_inventory_check.iterrows():
                    if row['재고수량'] <= 0:
                        continue
                    if pd.isna(row['최종출고일']):
                        has_no_outflow_alert = True
                        st.info(
                            f"**{row['제품명']}** (현재고: {row['재고수량']:.0f}개)\n"
                            f"• ⚠️ 경고: 최근 출고 리스트에 나간 기록이 전혀 없습니다."
                        )
                    elif row['최종출고일'] <= limit_3_months:
                        has_no_outflow_alert = True
                        no_outflow_days = (current_date - row['최종출고일']).days
                        st.info(
                            f"**{row['제품명']}** (현재고: {row['재고수량']:.0f}개)\n"
                            f"• 최종 출고일: {row['최종출고일'].strftime('%Y-%m-%d')} "
                            f"({no_outflow_days}일 동안 출고 없음)"
                        )

                if not has_no_outflow_alert:
                    st.info("✅ 장기 체화 재고가 없습니다.")
            else:
                st.info("✅ 출고 기록이 없어 분석할 수 없습니다.")

        # --- [탭 5] 전체 현재 재고 및 상세 조회 (버전 크래시 방지 보완) ---
        with tab5:
            st.header("▶️ 창고 전체 현재 재고 현황")
            
            search_term = st.text_input(
                "🔍 의약품 검색 (찾으시는 제품명을 입력하세요)", "", key="prod_search"
            )
            
            df_all_inv = df_inventory.copy()
            if '유효기간_날짜' in df_all_inv.columns:
                df_all_inv['유효기간_표시'] = (
                    df_all_inv['유효기간_날짜'].dt.strftime('%Y-%m-%d')
                )
                df_all_inv['유효기간_표시'] = (
                    df_all_inv['유효기간_표시']
                    .fillna(df_all_inv['유효기간'].astype(str))
                )
            else:
                df_all_inv['유효기간_표시'] = df_all_inv['유효기간'].astype(str)
                
            df_inv_filtered = df_all_inv[
                ['제품명', '재고수량', '유효기간_표시']
            ].copy()
            df_inv_filtered.columns = ['제품명', '재고 수량 (개)', '유효기간']
            
            if search_term:
                df_inv_filtered = df_inv_filtered[
                    df_inv_filtered['제품명']
                    .str.contains(search_term, case=False, na=False)
                ]
            
            st.markdown(f"📊 **현재 창고 재고 목록:** 총 `{len(df_inv_filtered)}`건")
            
            # 메인 재고 표 (버전 타지 않는 안전한 방식으로 출력)
            st.dataframe(df_inv_filtered, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.subheader("🔍 의약품별 거래처 출고 이력 상세 조회")
            
            # 버전 충돌을 피하기 위해 안전한 드롭다운 선택상자 방식으로 조회
            selectable_products = sorted(df_inv_filtered['제품명'].unique())
            
            if selectable_products:
                selected_product = st.selectbox(
                    "📦 출고 이력을 추