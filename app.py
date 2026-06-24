import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import os

# 페이지 설정 (줄바꿈 최적화)
st.set_page_config(
    page_title="분석 시스템", 
    layout="wide"
)

st.title("📊 의약품 통합 분석 시스템")
st.write("데이터를 자동으로 불러와 분석하는 화면입니다.")
st.markdown("---")

ORDER_FILE = "출고데이터.xls"
INVENTORY_FILE = "재고데이터.xls"

def load_data(file_path):
    if file_path.endswith('.csv'):
        return pd.read_csv(file_path)
    return pd.read_excel(file_path)

# 두 파일이 존재할 때 실행
if os.path.exists(ORDER_FILE) and os.path.exists(INVENTORY_FILE):
    current_date = datetime.now()
    
    try:
        df_orders = load_data(ORDER_FILE)
        df_inventory = load_data(INVENTORY_FILE)
        
        # 공백 및 문자열 정리
        if '제품명' in df_orders.columns:
            df_orders['제품명'] = df_orders['제품명'].fillna('').astype(str).str.strip()
        if '제품명' in df_inventory.columns:
            df_inventory['제품명'] = df_inventory['제품명'].fillna('').astype(str).str.strip()
        if '매출처' in df_orders.columns:
            df_orders['매출처'] = df_orders['매출처'].fillna('').astype(str).str.strip()
            
        # [합 계] 데이터 제외 처리
        k_word = '합계|합 계|\\[합.*\\]'
        df_orders = df_orders[
            (df_orders['제품명'] != '') & 
            (~df_orders['제품명'].str.contains(k_word, na=False))
        ]
        df_inventory = df_inventory[
            (df_inventory['제품명'] != '') & 
            (~df_inventory['제품명'].str.contains(k_word, na=False))
        ]
        
        # 숫자 데이터 변환
        if '수량' in df_orders.columns:
            df_orders['수량'] = pd.to_numeric(df_orders['수량'], errors='coerce').fillna(0)
        if '재고수량' in df_inventory.columns:
            df_inventory['재고수량'] = pd.to_numeric(df_inventory['재고수량'], errors='coerce').fillna(0)
            
        # 날짜형 변환
        if '출고일자' in df_orders.columns:
            df_orders['출고일자'] = pd.to_datetime(df_orders['출고일자'], errors='coerce')

        # 재고 소진 품목 보정
        exist_p = df_inventory['제품명'].unique()
        all_p = df_orders['제품명'].unique()
        miss_p = [p for p in all_p if p not in exist_p and p != '']
        
        if miss_p:
            m_df = pd.DataFrame({
                '제품명': miss_p,
                '재고수량': 0.0,
                '유효기간': '소진 (기록없음)'
            })
            df_inventory = pd.concat([df_inventory, m_df], ignore_index=True)

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

    # UI 렌더링 시작
    if data_ready:
        st.success(f"✅ 분석 완료! ({current_date.strftime('%Y-%m-%d')})")
        
        # 탭 레이아웃 생성
        t1, t2, t3, t4, t5 = st.tabs([
            "🏢 매출처별 출고 리스트",
            "⚠️ 주문시기 및 재고부족 알림", 
            "🚨 유효기간 임박 경고", 
            "📦 장기 미출고 재고",
            "📋 전체 현재 재고"
        ])
        
        # --- [탭 1] 매출처별 출고 리스트 ---
        with t1:
            st.header("▶️ 매출처별 출고 상세 리스트")
            if not df_orders.empty and '매출처' in df_orders.columns:
                u_cust = sorted([c for c in df_orders['매출처'].unique() if c != ''])
                
                c_search = st.text_input("🔍 매출처 검색:", "", key="c_search")
                
                if c_search:
                    f_cust = [c for c in u_cust if c_search.lower() in c.lower()]
                else:
                    f_cust = u_cust
                
                if f_cust:
                    s_cust = st.selectbox(
                        "🏢 조회할 매출처 선택:",
                        f_cust,
                        key="c_select"
                    )
                    st.markdown("---")
                    st.markdown(f"### 📅 {s_cust} 상세 내역")
                    
                    df_c_ord = df_orders[df_orders['매출처'] == s_cust].copy()
                    if not df_c_ord.empty and '출고일자' in df_c_ord.columns:
                        df_c_his = df_c_ord[['출고일자', '제품명', '수량']].copy()
                        df_c_his['출고날짜'] = df_c_his['출고일자'].dt.strftime('%Y-%m-%d').fillna("없음")
                        
                        df_disp = df_c_his[['출고날짜', '제품명', '수량']].copy()
                        df_disp.columns = ['출고날짜', '의약품명', '출고수량 (개)']
                        df_disp = df_disp.sort_values(by='출고날짜', ascending=False)
                        
                        st.dataframe(
                            df_disp,
                            use_container_width=True,
                            hide_index=True
                        )
                    else:
                        st.info("✨ 출고 기록이 없습니다.")
                else:
                    st.warning("🔍 검색 결과가 없습니다.")
            else:
                st.info("✅ 분석할 데이터가 없습니다.")

        # --- [탭 2] 주문 시기 및 재고 부족 ---
        with t2:
            st.header("▶️ 주문 시기 및 재고 부족 위험")
            if not df_orders.empty and '매출처' in df_orders.columns and '출고일자' in df_orders.columns:
                df_o_srt = df_orders.sort_values(by=['매출처', '제품명', '출고일자'])
                df_o_srt['이전일'] = df_o_srt.groupby(['매출처', '제품명'])['출고일자'].shift(1)
                df_o_srt['주기'] = (df_o_srt['출고일자'] - df_o_srt['이전일']).dt.days

                cyc = df_o_srt.groupby(['매출처', '제품명']).agg(
                    p_ju=('주기', 'mean'),
                    r_il=('출고일자', 'max'),
                    p_am=('수량', 'mean')
                ).reset_index()

                cyc = cyc[cyc['p_ju'].notna() & (cyc['p_ju'] > 0)].copy()
                
                if not cyc.empty:
                    cyc['예상일'] = cyc.apply(lambda r: r['r_il'] + timedelta(days=int(r['p_ju'])), axis=1)
                    cyc['남은일'] = (cyc['예상일'] - current_date).dt.days

                    alert = cyc[
                        (cyc['남은일'] <= 7) & 
                        (~cyc['제품명'].str.contains('하모닐란|엔커버', na=False))
                    ].copy()
                    alert = alert.sort_values(by='남은일', ascending=False)

                    has_al = False
                    for idx, row in alert.iterrows():
                        stk = df_inventory[df_inventory['제품명'] == row['제품명']]['재고수량'].sum()
                        if stk < row['p_am']:
                            has_al = True
                            st.warning(
                                f"**[{row['매출처']}]** {row['제품명']}\n"
                                f"• 예상일: {row['예상일'].strftime('%Y-%m-%d')} ({row['남은일']}일 남음)\n"
                                f"• 주문량: {row['p_am']:.0f}개 | 재고: {stk:.0f}개"
                            )
                    if not has_al:
                        st.info("✅ 위험 품목이 없습니다.")
                else:
                    st.info("✅ 분석할 패턴이 없습니다.")
            else:
                st.info("✅ 데이터가 부족합니다.")

        # --- [탭 3] 유효기간 10개월 미만 ---
        with t3:
            st.header("▶️ 유효기간 10개월 미만 의약품 목록")
            lim_10 = current_date + timedelta(days=300)
            if '유효기간_날짜' in df_inventory.columns:
                s_exp = df_inventory[
                    df_inventory['유효기간_날짜'].notna() & 
                    (df_inventory['유효기간_날짜'] <= lim_10) & 
                    (df_inventory['재고수량'] > 0)
                ]
                if not s_exp.empty:
                    s_exp = s_exp.sort_values(